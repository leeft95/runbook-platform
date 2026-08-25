"""Service-owned current dataset pointers and snapshot coordination."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from runbook.core import BlobStore, DatasetManifest, Snapshot, SnapshotProducer
from runbook.core.utils.hashing import sha256_json
from sqlalchemy import Column, DateTime, MetaData, String, Table, func, select
from sqlalchemy.engine import Connection, Engine

pointer_metadata = MetaData()
dataset_pointers = Table(
    "dataset_pointers",
    pointer_metadata,
    Column("dataset_id", String(255), primary_key=True),
    Column("source_id", String(255), nullable=False, index=True),
    Column("manifest_ref", String(1024), nullable=False),
    Column("watermark", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("source_run_id", String(64), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def _utc(value: datetime) -> datetime:
    """Normalize one aware timestamp to UTC."""
    if value.tzinfo is None:
        raise ValueError("pointer timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class DatasetPointer:
    dataset_id: str
    source_id: str
    manifest_ref: str
    watermark: datetime
    published_at: datetime
    source_run_id: str
    updated_at: datetime


@dataclass(frozen=True)
class DatasetPointerUpdate:
    dataset_id: str
    manifest_ref: str
    watermark: datetime
    published_at: datetime


class DatabasePointerRegistry:
    """Current-pointer repository owned by services."""

    def __init__(self, bind: Engine | Connection):
        self.bind = bind

    def _connection(self, *, write: bool = False):
        """Yield a caller-owned connection while preserving its transaction."""
        if isinstance(self.bind, Connection):
            if write:
                return _NestedConnection(self.bind)
            return _NoopContext(self.bind)
        return self.bind.begin() if write else self.bind.connect()

    def get(self, dataset_ids: Iterable[str], *, for_update: bool = False) -> dict[str, DatasetPointer]:
        """Load requested current pointers, optionally locking them for update."""
        requested = sorted(set(dataset_ids))
        if not requested:
            return {}
        with self._connection() as connection:
            statement = (
                select(dataset_pointers)
                .where(dataset_pointers.c.dataset_id.in_(requested))
                .order_by(dataset_pointers.c.dataset_id)
            )
            if for_update:
                statement = statement.with_for_update()
            rows = connection.execute(statement).mappings()
            return {row["dataset_id"]: DatasetPointer(**dict(row)) for row in rows}

    def all(self) -> dict[str, DatasetPointer]:
        """Load all current pointers."""
        with self._connection() as connection:
            rows = connection.execute(select(dataset_pointers).order_by(dataset_pointers.c.dataset_id)).mappings()
            return {row["dataset_id"]: DatasetPointer(**dict(row)) for row in rows}

    def is_empty(self) -> bool:
        """Return whether the pointer registry is empty."""
        with self._connection() as connection:
            return connection.scalar(select(func.count()).select_from(dataset_pointers)) == 0

    def publish(
        self,
        *,
        source_id: str,
        source_run_id: str,
        updates: Iterable[DatasetPointerUpdate],
        updated_at: datetime | None = None,
        expected_source_run_ids: Mapping[str, str | None] | None = None,
    ) -> None:
        """Atomically publish one source's current pointers.

        ``expected_source_run_ids`` gives workers a small compare-and-set
        guard: a stale worker may not overwrite a pointer published after it
        loaded its prior state.  Omitting the mapping preserves the generic
        registry's existing unconditional publication API.
        """
        prepared = sorted(updates, key=lambda item: item.dataset_id)
        if len({item.dataset_id for item in prepared}) != len(prepared):
            raise ValueError("pointer publication contains duplicate dataset ids")
        stamp = _utc(updated_at or datetime.now(timezone.utc))
        with self._connection(write=True) as connection:
            existing = self._get_with_connection(connection, [item.dataset_id for item in prepared], for_update=True)
            conflicts = {key: value.source_id for key, value in existing.items() if value.source_id != source_id}
            if conflicts:
                details = ", ".join(f"{key}={value}" for key, value in sorted(conflicts.items()))
                raise ValueError(f"datasets already belong to another source: {details}")
            if expected_source_run_ids is not None:
                changed = {
                    item.dataset_id: (
                        expected_source_run_ids[item.dataset_id],
                        existing[item.dataset_id].source_run_id if item.dataset_id in existing else None,
                    )
                    for item in prepared
                    if item.dataset_id in expected_source_run_ids
                    and expected_source_run_ids[item.dataset_id]
                    != (existing[item.dataset_id].source_run_id if item.dataset_id in existing else None)
                }
                if changed:
                    details = ", ".join(
                        f"{dataset_id}: expected={expected!r}, actual={actual!r}"
                        for dataset_id, (expected, actual) in sorted(changed.items())
                    )
                    raise ValueError(f"pointer compare-and-set conflict: {details}")
            for item in prepared:
                values = {
                    "source_id": source_id,
                    "manifest_ref": item.manifest_ref,
                    "watermark": _utc(item.watermark),
                    "published_at": _utc(item.published_at),
                    "source_run_id": source_run_id,
                    "updated_at": stamp,
                }
                if item.dataset_id in existing:
                    connection.execute(
                        dataset_pointers.update()
                        .where(dataset_pointers.c.dataset_id == item.dataset_id)
                        .values(**values)
                    )
                else:
                    connection.execute(dataset_pointers.insert().values(dataset_id=item.dataset_id, **values))

    @staticmethod
    def _get_with_connection(
        connection: Connection,
        dataset_ids: Iterable[str],
        *,
        for_update: bool = False,
    ) -> dict[str, DatasetPointer]:
        """Read pointers without changing transaction ownership."""
        requested = sorted(set(dataset_ids))
        if not requested:
            return {}
        statement = (
            select(dataset_pointers)
            .where(dataset_pointers.c.dataset_id.in_(requested))
            .order_by(dataset_pointers.c.dataset_id)
        )
        if for_update:
            statement = statement.with_for_update()
        rows = connection.execute(statement).mappings()
        return {row["dataset_id"]: DatasetPointer(**dict(row)) for row in rows}


class _NoopContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return False


class _NestedConnection:
    """Context manager for a nested transaction on a caller-owned connection."""

    def __init__(self, connection: Connection):
        self.connection = connection
        self.transaction = None

    def __enter__(self):
        self.transaction = self.connection.begin_nested()
        return self.connection

    def __exit__(self, *args):
        assert self.transaction is not None
        return self.transaction.__exit__(*args)


def create_pointer_schema(bind: Engine | Connection) -> None:
    """Create the service-owned pointer table for local metadata upgrades."""
    pointer_metadata.create_all(bind)


def load_manifest(store: BlobStore, ref: str, *, expected_dataset_id: str | None = None) -> DatasetManifest:
    """Load and verify one immutable dataset manifest."""
    payload = store.get(ref)
    if ref.startswith("curated/") and "/manifests/" not in ref:
        raise ValueError(f"invalid manifest reference: {ref}")
    if "sha256=" in ref and hashlib.sha256(payload).hexdigest() != ref.rsplit("sha256=", 1)[1].removesuffix(".json"):
        raise IOError(f"manifest digest verification failed: {ref}")
    manifest = DatasetManifest.model_validate(json.loads(payload.decode()))
    if expected_dataset_id is not None and manifest.dataset_id != expected_dataset_id:
        raise ValueError(f"manifest dataset mismatch: expected={expected_dataset_id!r}, actual={manifest.dataset_id!r}")
    return manifest


def resolve_snapshot(
    store: BlobStore,
    bindings: dict[str, str],
    *,
    pointer_registry: DatabasePointerRegistry,
    as_of: datetime | None = None,
    producer_provenance: Iterable[SnapshotProducer] = (),
    warnings: Iterable[str] = (),
    provenance: Iterable[SnapshotProducer] | None = None,
) -> Snapshot:
    """Resolve current pointers into a deterministic immutable snapshot."""
    pointers = pointer_registry.get(bindings.values())
    selected: dict[str, str] = {}
    manifests: list[DatasetManifest] = []
    for alias, dataset_id in sorted(bindings.items()):
        pointer = pointers.get(dataset_id)
        if pointer is None:
            raise ValueError(f"no pointer exists for dataset {dataset_id!r}")
        ref = pointer.manifest_ref
        manifest = load_manifest(store, ref, expected_dataset_id=dataset_id)
        if as_of is not None:
            cutoff = _utc(as_of)
            seen = {ref}
            while manifest.published_at > cutoff and manifest.previous:
                ref = manifest.previous
                if ref in seen:
                    raise ValueError(f"cyclic manifest history for dataset {dataset_id!r}")
                seen.add(ref)
                manifest = load_manifest(store, ref, expected_dataset_id=dataset_id)
        selected[alias] = ref
        manifests.append(manifest)
    watermark = min((manifest.watermark for manifest in manifests), default=datetime(1970, 1, 1, tzinfo=timezone.utc))
    if provenance is not None:
        producer_provenance = provenance
    normalized_provenance = tuple(sorted(producer_provenance, key=lambda item: (item.producer_id, item.source_run_id)))
    normalized_warnings = tuple(sorted({str(item) for item in warnings}))
    payload: dict[str, Any] = {
        "schema_version": "snapshot/1",
        "watermark": _utc(watermark).isoformat(),
        "as_of": _utc(as_of).isoformat() if as_of else None,
        "datasets": selected,
    }
    if normalized_provenance:
        payload["producer_provenance"] = [item.model_dump(mode="json") for item in normalized_provenance]
    if normalized_warnings:
        payload["warnings"] = list(normalized_warnings)
    return Snapshot(
        snapshot_id=sha256_json(payload),
        watermark=watermark,
        as_of=_utc(as_of) if as_of else None,
        datasets=selected,
        producer_provenance=normalized_provenance,
        warnings=normalized_warnings,
    )


__all__ = [
    "DatabasePointerRegistry",
    "DatasetPointer",
    "DatasetPointerUpdate",
    "create_pointer_schema",
    "dataset_pointers",
    "load_manifest",
    "resolve_snapshot",
]
