"""Small, backend-neutral dataset and snapshot contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        import re

        if not re.fullmatch(_SHA256, value):
            raise ValueError("snapshot_id must be a lowercase full SHA-256 digest")
        return value
