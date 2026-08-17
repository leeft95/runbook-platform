"""Small data-package contracts for source ingestion.

The old implementation mixed ingestion models with platform runtime and
database settings.  These models deliberately describe only the source
boundary and the result of acquiring bytes; storage and publication are
owned by :mod:`runbook.data`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from runbook.data.config import SourceConfig
from runbook.data.pointers import DatasetPointerUpdate


@dataclass(frozen=True)
class CuratedFrame:
    """A parser output with its deterministic identity and watermark."""

    output_alias: str
    frame: Any
    watermark: datetime
    partition: dict[str, str]
    merge_keys: tuple[str, ...] = ()


class ReadinessStatus(StrEnum):
    ready = "ready"
    not_ready = "not_ready"
    failed = "failed"


class ReadinessResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    acquisition_run: str
    status: ReadinessStatus
    observed_at: datetime
    message: str | None = None
    remote_filename: str | None = None
    remote_locator: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    acquisition_run: str
    artifact_ref: str = ""
    content_sha256: str = ""
    source_filename: str
    source_locator: str | None = None
    fetched_at: datetime
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcquisitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record: RawArtifactRecord
    payload: bytes


class AcquisitionStageResult(BaseModel):
    """Result of checking, acquiring, and persisting one source payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    acquisition_run: str
    status: ReadinessStatus
    readiness: ReadinessResult
    acquired: AcquisitionResult | None = None
    message: str | None = None


@dataclass(frozen=True)
class CurationResult:
    """Immutable curation output awaiting an atomic pointer commit."""

    datasets: dict[str, str]
    pointer_updates: tuple[DatasetPointerUpdate, ...]


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str | None = None
    source_config: SourceConfig | None = None
    run_time: datetime | None = None
    store_uri: str | None = None
    source_config_file: str = "data/contract/source_configs.json"


class IngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    acquisition_run: str
    status: ReadinessStatus
    readiness: ReadinessResult
    raw_record: RawArtifactRecord | None = None
    datasets: dict[str, str] = Field(default_factory=dict)
    message: str | None = None


__all__ = [
    "AcquisitionResult",
    "AcquisitionStageResult",
    "CurationResult",
    "CuratedFrame",
    "IngestRequest",
    "IngestResult",
    "RawArtifactRecord",
    "ReadinessResult",
    "ReadinessStatus",
    "SourceConfig",
]
