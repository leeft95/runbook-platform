from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from runbook.data.config import SourceConfig
from runbook.data.ingest.models import (
    AcquisitionResult,
    HistoricalExecutionContext,
    PreviousAcquisitionState,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)


class ExternalTestAdapter:
    def validate(self, source_config: SourceConfig) -> None:
        if not source_config.params.get("external_state_path"):
            raise ValueError("test_external requires params.external_state_path")

    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> ReadinessResult:
        self.validate(source_config)
        return ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=acquisition_run,
            status=ReadinessStatus.ready,
            observed_at=observed_at,
            remote_filename="external.csv",
            metadata=(
                {
                    "historical_start_date": execution_context.start_date.isoformat(),
                    "historical_end_date": execution_context.end_date.isoformat(),
                }
                if execution_context is not None
                else {}
            ),
        )

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_state: PreviousAcquisitionState | None = None,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> AcquisitionResult:
        self.validate(source_config)
        state = previous_state.model_dump(mode="json") if previous_state is not None else None
        if execution_context is not None:
            state = {
                "historical_start_date": execution_context.start_date.isoformat(),
                "historical_end_date": execution_context.end_date.isoformat(),
            }
        Path(str(source_config.params["external_state_path"])).write_text(
            json.dumps(state, sort_keys=True),
            encoding="utf-8",
        )
        payload = b"timestamp,value\n2026-01-01T00:00:00Z,42\n"
        return AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=readiness.acquisition_run,
                source_filename="external.csv",
                fetched_at=fetched_at,
            ),
            payload=payload,
        )


class LegacyExternalTestAdapter:
    """Legacy adapter shape used to guard ordinary-run compatibility."""

    def validate(self, source_config: SourceConfig) -> None:
        if not source_config.params.get("external_state_path"):
            raise ValueError("test_external_legacy requires params.external_state_path")

    def check(self, *, source_config: SourceConfig, acquisition_run: str, observed_at: datetime) -> ReadinessResult:
        self.validate(source_config)
        return ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=acquisition_run,
            status=ReadinessStatus.ready,
            observed_at=observed_at,
            remote_filename="external.csv",
        )

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_state: PreviousAcquisitionState | None = None,
    ) -> AcquisitionResult:
        self.validate(source_config)
        state = previous_state.model_dump(mode="json") if previous_state is not None else None
        Path(str(source_config.params["external_state_path"])).write_text(
            json.dumps(state, sort_keys=True),
            encoding="utf-8",
        )
        return AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=readiness.acquisition_run,
                source_filename="external.csv",
                fetched_at=fetched_at,
            ),
            payload=b"timestamp,value\n2026-01-01T00:00:00Z,7\n",
        )
