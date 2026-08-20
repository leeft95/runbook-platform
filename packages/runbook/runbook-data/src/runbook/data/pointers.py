from __future__ import annotations

import os
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, func, select
from sqlalchemy.engine import Connection, Engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/runbook"

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
    """Normalize an aware pointer timestamp to UTC."""
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
    """Database-backed current-pointer registry for immutable dataset manifests."""

    def __init__(self, bind: Engine | Connection):
        self.bind = bind

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[Connection]:
        """Yield a caller-owned connection or manage an engine connection."""
        if isinstance(self.bind, Connection):
            if write:
                with self.bind.begin_nested():
                    yield self.bind
            else:
                yield self.bind
        elif write:
            with self.bind.begin() as connection:
                yield connection
        else:
            with self.bind.connect() as connection:
                yield connection

    def get(self, dataset_ids: Iterable[str]) -> dict[str, DatasetPointer]:
        """Load the current pointer for each requested dataset that exists."""
        requested = sorted(set(dataset_ids))
        if not requested:
            return {}
        with self._connection() as connection:
            rows = connection.execute(
                select(dataset_pointers).where(dataset_pointers.c.dataset_id.in_(requested))
            ).mappings()
            return {row["dataset_id"]: DatasetPointer(**dict(row)) for row in rows}

    def all(self) -> dict[str, DatasetPointer]:
        """Load every current dataset pointer."""
        with self._connection() as connection:
            rows = connection.execute(select(dataset_pointers).order_by(dataset_pointers.c.dataset_id)).mappings()
            return {row["dataset_id"]: DatasetPointer(**dict(row)) for row in rows}

    def is_empty(self) -> bool:
        """Return whether the registry contains no dataset pointers."""
        with self._connection() as connection:
            count = connection.scalar(select(func.count()).select_from(dataset_pointers))
            return count == 0

    def publish(
        self,
        *,
        source_id: str,
        source_run_id: str,
        updates: Iterable[DatasetPointerUpdate],
        updated_at: datetime | None = None,
    ) -> None:
        """Atomically publish one source's current dataset pointers."""
        prepared = list(updates)
        if len({item.dataset_id for item in prepared}) != len(prepared):
            raise ValueError("pointer publication contains duplicate dataset ids")
        stamp = _utc(updated_at or datetime.now(timezone.utc))
        values_by_dataset = {
            item.dataset_id: {
                "source_id": source_id,
                "manifest_ref": item.manifest_ref,
                "watermark": _utc(item.watermark),
                "published_at": _utc(item.published_at),
                "source_run_id": source_run_id,
                "updated_at": stamp,
            }
            for item in prepared
        }
        with self._connection(write=True) as connection:
            existing = self._get_with_connection(connection, [item.dataset_id for item in prepared])
            conflicts = {
                dataset_id: pointer.source_id
                for dataset_id, pointer in existing.items()
                if pointer.source_id != source_id
            }
            if conflicts:
                details = ", ".join(f"{dataset_id}={owner}" for dataset_id, owner in sorted(conflicts.items()))
                raise ValueError(f"datasets already belong to another source: {details}")
            for item in prepared:
                values = values_by_dataset[item.dataset_id]
                if item.dataset_id in existing:
                    connection.execute(
                        dataset_pointers.update()
                        .where(dataset_pointers.c.dataset_id == item.dataset_id)
                        .values(**values)
                    )
                else:
                    connection.execute(dataset_pointers.insert().values(dataset_id=item.dataset_id, **values))

    @staticmethod
    def _get_with_connection(connection: Connection, dataset_ids: Iterable[str]) -> dict[str, DatasetPointer]:
        """Load requested pointers without changing transaction ownership."""
        requested = sorted(set(dataset_ids))
        if not requested:
            return {}
        rows = connection.execute(
            select(dataset_pointers).where(dataset_pointers.c.dataset_id.in_(requested))
        ).mappings()
        return {row["dataset_id"]: DatasetPointer(**dict(row)) for row in rows}


def open_pointer_registry(value: str | None = None) -> DatabasePointerRegistry:
    """Open a database-backed pointer registry."""
    return DatabasePointerRegistry(
        create_engine(value or os.environ.get("RUNBOOK_DATABASE_URL", DEFAULT_DATABASE_URL), pool_pre_ping=True)
    )


def create_pointer_schema(bind: Engine | Connection) -> None:
    """Create the pointer table for metadata-based development upgrades."""
    pointer_metadata.create_all(bind)


__all__ = [
    "DatabasePointerRegistry",
    "DatasetPointer",
    "DatasetPointerUpdate",
    "create_pointer_schema",
    "dataset_pointers",
    "open_pointer_registry",
]
