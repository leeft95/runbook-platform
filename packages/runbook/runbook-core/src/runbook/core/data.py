"""Small, backend-neutral dataset and snapshot contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import DatasetBinding, ReportProfile, ScheduleSpec, SourceConfig, load_profiles, load_source_configs
from .storage import BlobStore, open_blob_store

__all__ = [
    "BlobStore",
    "DatasetBinding",
    "DatasetFile",
    "DatasetManifest",
    "SnapshotProducer",
    "ReportProfile",
    "ScheduleSpec",
    "Snapshot",
    "SourceConfig",
    "open_blob_store",
    "load_profiles",
    "load_source_configs",
]

_SHA256 = r"^[0-9a-f]{64}$"


class DatasetFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str
    sha256: str
    partition: dict[str, str] = Field(default_factory=dict)
    lineage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        from pathlib import PurePosixPath

        normalized = str(PurePosixPath(value))
        if normalized.startswith("/") or normalized == ".." or normalized.startswith("../") or "/../" in normalized:
            raise ValueError("dataset file ref must be a logical relative POSIX key")
        return normalized

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        import re

        if not re.fullmatch(_SHA256, value):
            raise ValueError("sha256 must be a lowercase full SHA-256 digest")
        return value


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "dataset/1"
    dataset_id: str
    watermark: datetime
    published_at: datetime
    previous: str | None = None
    files: tuple[DatasetFile, ...] = ()

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
            raise ValueError("dataset_id must be a safe lowercase identifier")
        return value


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "snapshot/1"
    snapshot_id: str
    watermark: datetime
    as_of: datetime | None = None
    datasets: dict[str, str]
    producer_provenance: tuple["SnapshotProducer", ...] = ()
    warnings: tuple[str, ...] = ()

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        import re

        if not re.fullmatch(_SHA256, value):
            raise ValueError("snapshot_id must be a lowercase full SHA-256 digest")
        return value

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_warnings(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(sorted({str(item) for item in value}))

    @model_validator(mode="before")
    @classmethod
    def accept_provenance_alias(cls, value: Any) -> Any:
        """Accept the shorter historical ``provenance`` spelling."""
        if (
            isinstance(value, dict)
            and "producer_provenance" not in value
            and ("provenance" in value or "producers" in value or "producer_runs" in value)
        ):
            value = dict(value)
            value["producer_provenance"] = value.pop(
                "provenance", value.pop("producers", value.pop("producer_runs", ()))
            )
        return value

    @property
    def provenance(self) -> tuple["SnapshotProducer", ...]:
        """Backward-compatible short spelling for producer provenance."""
        return self.producer_provenance

    @property
    def producers(self) -> tuple["SnapshotProducer", ...]:
        """Convenient alias used by diagnostics and older integrations."""
        return self.producer_provenance

    @property
    def producer_runs(self) -> tuple["SnapshotProducer", ...]:
        """Alias for callers that describe provenance as producer runs."""
        return self.producer_provenance


class SnapshotProducer(BaseModel):
    """Immutable producer evidence carried by a resolved snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    producer_id: str
    source_run_id: str
    slot: datetime
    aliases: tuple[str, ...]

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            raise ValueError("producer provenance must include at least one alias")
        aliases = tuple(sorted({str(item) for item in value}))
        if not aliases:
            raise ValueError("producer provenance must include at least one alias")
        return aliases
