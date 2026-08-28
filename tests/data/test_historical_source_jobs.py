from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from runbook.data import HistoricalExecutionContext, open_blob_store
from runbook.data.config import ScheduleSpec, SourceConfig
from runbook.data.ingest import (
    AcquisitionResult,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
    run_stage1_acquire,
)
from runbook.data.ingest.runners import run_stage2_curate
from runbook.data.manifests import load_manifest, read_dataframe


def _config() -> SourceConfig:
    return SourceConfig(
        source_id="historical_fixture",
        adapter="fixture",
        schedule=ScheduleSpec(cron="0 * * * *"),
        datasets={
            "prices": {
                "dataset_id": "historical_fixture_prices",
                "parser_id": "csv_timeseries_v1",
                "update_mode": "full",
            }
        },
        params={"timestamp_column": "timestamp"},
    )


class HistoricalFixtureAdapter:
    """Small fixture adapter proving the public historical context seam."""

    def validate(self, source_config: SourceConfig) -> None:
        del source_config

    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> ReadinessResult:
        assert execution_context is not None
        return ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=acquisition_run,
            status=ReadinessStatus.ready,
            observed_at=observed_at,
            remote_filename="fixture.csv",
        )

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> AcquisitionResult:
        assert execution_context is not None
        dates = []
        current = execution_context.start_date
        while current <= execution_context.end_date:
            dates.append(current)
            current += timedelta(days=1)
        payload = "timestamp,value\n" + "".join(
            f"{item.isoformat()}T00:00:00Z,{index}\n" for index, item in enumerate(dates)
        )
        return AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=readiness.acquisition_run,
                source_filename="fixture.csv",
                fetched_at=fetched_at,
            ),
            payload=payload.encode(),
        )


def test_fixture_adapter_executes_bounded_historical_range_end_to_end(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("runbook.data.ingest.runner.get_adapter", lambda _config: HistoricalFixtureAdapter())
    store = open_blob_store(f"file:{tmp_path / 'store'}")
    result = run_stage1_acquire(
        source_config=_config(),
        slot=datetime(2026, 8, 1, tzinfo=timezone.utc),
        store=store,
        execution_context=HistoricalExecutionContext(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        ),
    )
    assert result.acquired is not None
    assert result.acquired.record.artifact_ref
    curated = run_stage2_curate(
        store=store,
        source_config=_config(),
        acquired=result.acquired,
    )
    manifest = load_manifest(store, curated.datasets["historical_fixture_prices"])
    frame = read_dataframe(store, manifest.files[0].ref, expected_sha256=manifest.files[0].sha256)
    assert frame["timestamp"].dt.date.tolist() == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    assert frame["value"].tolist() == [0, 1, 2]


def test_unsupported_adapter_fails_before_readiness_or_acquisition(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    class Unsupported:
        def validate(self, _source_config):
            pass

        def check(self, **_kwargs):
            calls.append("check")
            raise AssertionError("historical readiness should not run")

        def acquire(self, **_kwargs):
            calls.append("acquire")
            raise AssertionError("historical acquisition should not run")

    monkeypatch.setattr("runbook.data.ingest.runner.get_adapter", lambda _config: Unsupported())
    with pytest.raises(
        ValueError, match="Source 'historical_fixture' does not support historical date-range execution"
    ):
        run_stage1_acquire(
            source_config=_config(),
            slot=datetime(2026, 8, 1, tzinfo=timezone.utc),
            store=open_blob_store(f"file:{tmp_path / 'store'}"),
            execution_context=HistoricalExecutionContext(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 3),
            ),
        )
    assert calls == []
