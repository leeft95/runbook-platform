"""Small data-package contracts for source ingestion.

The old implementation mixed ingestion models with platform runtime and
database settings.  These models deliberately describe only the source
boundary and the result of acquiring bytes; storage and publication are
owned by :mod:`runbook.data`.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable, SupportsIndex

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from runbook.data.config import SourceConfig
from runbook.data.pointers import DatasetPointerUpdate


class _FrozenDict(dict[str, Any]):
    """A JSON-compatible mapping that rejects all mutation."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        """Reject mutation attempts."""
        raise TypeError("previous acquisition state is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _immutable  # type: ignore[assignment]

    def __ior__(self, _other: Any, /) -> "_FrozenDict":  # type: ignore[override,misc]
        self._immutable()
        return self


class _FrozenList(list[Any]):
    """A JSON-compatible sequence that rejects all mutation."""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        """Reject mutation attempts."""
        raise TypeError("previous acquisition state is immutable")

    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = _immutable  # type: ignore[assignment]

    def __iadd__(self, _other: Iterable[Any], /) -> "_FrozenList":  # type: ignore[override,misc]
        self._immutable()
        return self

    def __imul__(self, _count: SupportsIndex, /) -> "_FrozenList":  # type: ignore[override,misc]
        self._immutable()
        return self


def _freeze_json(value: Any) -> Any:
    """Recursively freeze a value while retaining JSON serialization."""
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze_json(item) for item in value)
    return value


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


class PreviousAcquisitionState(BaseModel):
    """Generic state from the previous successful source acquisition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    watermark: datetime | dict[str, datetime] | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> "PreviousAcquisitionState":
        """Copy through validation so updates retain recursive immutability."""
        data = self.model_dump(mode="python")
        if deep:
            data = deepcopy(data)
        if update:
            data.update(update)
        return type(self).model_validate(data)

    def model_post_init(self, __context: Any) -> None:
        """Freeze nested mappings and lists as well as model attributes."""
        del __context
        object.__setattr__(self, "watermark", _freeze_json(self.watermark))
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))


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
    "PreviousAcquisitionState",
    "RawArtifactRecord",
    "ReadinessResult",
    "ReadinessStatus",
    "SourceConfig",
]
