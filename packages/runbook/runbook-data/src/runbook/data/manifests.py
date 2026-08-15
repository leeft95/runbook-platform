from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Iterable

import pandas as pd
from runbook.core.data import DatasetFile, DatasetManifest, Snapshot
from runbook.core.utils.hashing import canonical_json, sha256_bytes, sha256_json
from runbook.data.store import BlobStore

POINTERS_KEY = "pointers.json"


def _utc(value: datetime) -> datetime:
    """Normalize an aware datetime to UTC, rejecting ambiguous naive input."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _path_segment(value: str, *, label: str) -> str:
    """Handle path segment."""
    if not value or value in {".", ".."} or "/" in value or "\\" in value or "=" in value:
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def _revision(ref: str) -> int | None:
    """Extract a positive numeric parquet revision from a logical ref."""
    stem = PurePosixPath(ref).stem
    return int(stem) if stem.isdigit() and int(stem) >= 1 else None


def _curated_ref(
    dataset_id: str,
    schema_version: str,
    partition: dict[str, str],
    revision: int,
) -> str:
    """Handle curated ref."""
    parts = [
        f"curated/{_path_segment(dataset_id, label='dataset_id')}",
        f"version={_path_segment(schema_version, label='schema_version')}",
    ]
    for key, value in partition.items():
        parts.append(f"{_path_segment(key, label='partition key')}={_path_segment(value, label='partition value')}")
    parts.append(f"{revision}.parquet")
    return "/".join(parts)


def write_dataframe(
    store: BlobStore,
    dataset_id: str,
    frame: pd.DataFrame,
    *,
    partition: dict[str, str] | None = None,
    schema_version: str = "v1",
    previous: DatasetFile | None = None,
) -> tuple[str, str]:
    """Serialize a curated frame and publish it under an immutable revision."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", dataset_id):
        raise ValueError(f"invalid dataset id: {dataset_id!r}")
    partition = dict(partition or {})
    payload = frame.to_parquet(index=True)
    digest = sha256_bytes(payload)
    first_ref = _curated_ref(dataset_id, schema_version, partition, 1)
    prefix = first_ref.rsplit("/", 1)[0] + "/"
    if previous is not None and previous.sha256 == digest and previous.ref.startswith(prefix):
        return previous.ref, digest

    previous_revision = _revision(previous.ref) if previous is not None and previous.ref.startswith(prefix) else None
    revision = previous_revision + 1 if previous_revision is not None else 1
    while True:
        ref = _curated_ref(dataset_id, schema_version, partition, revision)
        if not store.exists(ref):
            store.put_immutable(ref, payload)
            return ref, digest
        existing = store.get(ref)
        if sha256_bytes(existing) == digest:
            return ref, digest
        revision += 1


def read_dataframe(store: BlobStore, ref: str, *, expected_sha256: str | None = None) -> pd.DataFrame:
    """Read a curated parquet blob and optionally verify its digest."""
    import io

    payload = store.get(ref)
    if expected_sha256 is not None and sha256_bytes(payload) != expected_sha256:
        raise IOError(f"dataset file verification failed: {ref}")
    return pd.read_parquet(io.BytesIO(payload))


def build_manifest(
    *,
    dataset_id: str,
    watermark: datetime,
    published_at: datetime,
    files: Iterable[DatasetFile],
    previous: str | None = None,
) -> tuple[DatasetManifest, str]:
    """Build a canonical immutable dataset manifest and return its digest."""
    ordered = tuple(sorted(files, key=lambda item: (canonical_json(item.partition), item.ref)))
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        watermark=_utc(watermark),
        published_at=_utc(published_at),
        previous=previous,
        files=ordered,
    )
    digest = sha256_json(manifest.model_dump(mode="json"))
    return manifest, digest


def load_manifest(store: BlobStore, ref: str, *, expected_dataset_id: str | None = None) -> DatasetManifest:
    """Load and verify a content-addressed manifest reference."""
    payload = store.get(ref)
    match = re.search(r"sha256=([0-9a-f]{64})\.json$", ref)
    if match and sha256_bytes(payload) != match.group(1):
        raise IOError(f"manifest digest verification failed: {ref}")
    manifest = DatasetManifest.model_validate(json.loads(payload.decode("utf-8")))
    expected_prefix = f"curated/{manifest.dataset_id}/manifests/"
    if not ref.startswith(expected_prefix):
        raise ValueError(f"manifest reference does not match dataset identity: {ref}")
    if expected_dataset_id is not None and manifest.dataset_id != expected_dataset_id:
        raise ValueError(f"manifest dataset mismatch: expected={expected_dataset_id!r}, actual={manifest.dataset_id!r}")
    if manifest.previous is not None and not manifest.previous.startswith(expected_prefix):
        raise ValueError(f"manifest history reference does not match dataset identity: {manifest.previous!r}")
    return manifest


def publish_manifests(store: BlobStore, manifests: Iterable[tuple[DatasetManifest, str]]) -> dict[str, str]:
    """Publish immutable manifests and update the single pointer document."""
    prepared = list(manifests)
    pointers = store.get_json(POINTERS_KEY) if store.exists(POINTERS_KEY) else {}
    if not isinstance(pointers, dict):
        raise ValueError("pointers.json must contain an object")
    next_pointers = dict(pointers)
    for manifest, digest in prepared:
        ref = f"curated/{manifest.dataset_id}/manifests/sha256={digest}.json"
        store.put_immutable(ref, canonical_json(manifest.model_dump(mode="json")).encode("utf-8"))
        next_pointers[manifest.dataset_id] = ref
    if next_pointers != pointers:
        store.put_json(POINTERS_KEY, next_pointers)
    return {manifest.dataset_id: next_pointers[manifest.dataset_id] for manifest, _ in prepared}


def resolve_snapshot(
    store: BlobStore,
    bindings: dict[str, str],
    *,
    as_of: datetime | None = None,
) -> Snapshot:
    """Resolve dataset bindings to one deterministic latest or historical snapshot."""
    pointers = store.get_json(POINTERS_KEY) if store.exists(POINTERS_KEY) else {}
    if not isinstance(pointers, dict):
        raise ValueError("pointers.json must contain an object")
    selected: dict[str, str] = {}
    manifests: list[DatasetManifest] = []
    for alias, dataset_id in sorted(bindings.items()):
        ref = pointers.get(dataset_id)
        if not isinstance(ref, str):
            raise ValueError(f"no pointer exists for dataset {dataset_id!r}")
        manifest = load_manifest(store, ref, expected_dataset_id=dataset_id)
        visited = {ref}
        if as_of is not None:
            cutoff = _utc(as_of)
            while manifest.published_at > cutoff and manifest.previous:
                ref = manifest.previous
                if ref in visited:
                    raise ValueError(f"cyclic manifest history for dataset {dataset_id!r}")
                visited.add(ref)
                manifest = load_manifest(store, ref, expected_dataset_id=dataset_id)
            if manifest.published_at > cutoff:
                raise ValueError(f"dataset {dataset_id!r} has no manifest at or before {cutoff.isoformat()}")
        selected[alias] = ref
        manifests.append(manifest)
    watermark = min((manifest.watermark for manifest in manifests), default=datetime(1970, 1, 1, tzinfo=timezone.utc))
    payload = {
        "schema_version": "snapshot/1",
        "watermark": _utc(watermark).isoformat(),
        "as_of": _utc(as_of).isoformat() if as_of is not None else None,
        "datasets": selected,
    }
    normalized_as_of = _utc(as_of) if as_of is not None else None
    return Snapshot(snapshot_id=sha256_json(payload), watermark=watermark, as_of=normalized_as_of, datasets=selected)


def _partition_matches(partition: Mapping[str, str], filters: Mapping[str, object]) -> bool:
    """Handle partition matches."""
    for key, expected in filters.items():
        values = expected if isinstance(expected, (list, tuple, set, frozenset)) else (expected,)
        expected_values = {str(value) for value in values}
        if str(partition.get(key)) not in expected_values:
            return False
    return True


def load_snapshot_dataset(
    store: BlobStore,
    snapshot: Snapshot,
    alias: str,
    *,
    filters: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Load snapshot dataset."""
    ref = snapshot.datasets.get(alias)
    if ref is None:
        raise KeyError(f"unknown snapshot dataset alias: {alias!r}")
    manifest = load_manifest(store, ref)
    selected = [item for item in manifest.files if filters is None or _partition_matches(item.partition, filters)]
    frames = [read_dataframe(store, item.ref, expected_sha256=item.sha256) for item in selected]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
