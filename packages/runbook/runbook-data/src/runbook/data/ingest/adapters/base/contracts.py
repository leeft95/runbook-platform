"""Contracts for the two source-facing stages of ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from runbook.data.config import SourceConfig
from runbook.data.ingest.models import AcquisitionResult, ReadinessResult


class SourceAdapter(Protocol):
    def validate(self, source_config: SourceConfig) -> None: ...

    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
    ) -> ReadinessResult: ...

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_watermarks: Mapping[str, datetime] | None = None,
    ) -> AcquisitionResult: ...


__all__ = ["SourceAdapter"]
