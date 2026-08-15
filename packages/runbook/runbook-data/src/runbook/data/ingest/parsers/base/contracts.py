"""Contracts for source-blind Stage 2 parsing."""

from __future__ import annotations

from typing import Protocol

from runbook.data.config import SourceConfig
from runbook.data.ingest.models import AcquisitionResult, CuratedFrame


class Stage2Parser(Protocol):
    def __call__(
        self,
        *,
        source_config: SourceConfig,
        dataset_alias: str,
        acquired: AcquisitionResult,
    ) -> list[CuratedFrame]: ...


__all__ = ["Stage2Parser"]
