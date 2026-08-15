from __future__ import annotations

from datetime import datetime, timezone

import pytest
from runbook.data import open_blob_store
from runbook.data.config import ScheduleSpec, SourceConfig
from runbook.data.ingest import IngestRequest, RawArtifactRecord
from runbook.data.ingest.adapters import get_adapter
from runbook.data.ingest.models import AcquisitionResult
from runbook.data.ingest.parsers import get_parser
from runbook.data.ingest.runner import run_ingest


def _config(path: str, *, update_mode: str = "append") -> SourceConfig:
    return SourceConfig(
        source_id="synthetic_prices",
        adapter="local_file",
        schedule=ScheduleSpec(cron="0 * * * *"),
        datasets={
            "prices": {
                "dataset_id": "synthetic_prices",
                "parser_id": "csv_timeseries_v1",
                "update_mode": update_mode,
            }
        },
        params={"local_path": path, "timestamp_column": "timestamp"},
    )


def test_public_registries_contain_only_builtin_capabilities() -> None:
    assert type(get_adapter(_config("prices.csv"))).__name__ == "LocalFileAdapter"
    assert get_parser("csv_timeseries_v1").__name__ == "parse_csv_timeseries"
    with pytest.raises(ValueError, match="unsupported adapter"):
        get_adapter(_config("prices.csv").model_copy(update={"adapter": "vendor"}))
    with pytest.raises(ValueError, match="unsupported parser"):
        get_parser("vendor_parser")


def test_csv_parser_sorts_deduplicates_and_requires_timestamp() -> None:
    config = _config("prices.csv")
    acquired = AcquisitionResult(
        record=RawArtifactRecord(
            source_id="synthetic_prices",
            acquisition_run="20260101T000000Z",
            source_filename="prices.csv",
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        payload=(b"timestamp,close\n2026-01-02T00:00:00Z,2\n2026-01-01T00:00:00Z,1\n2026-01-02T00:00:00Z,3\n"),
    )
    frame = get_parser("csv_timeseries_v1")(
        source_config=config,
        dataset_alias="prices",
        acquired=acquired,
    )[0]
    assert frame.frame["close"].tolist() == [1, 3]
    assert frame.frame["timestamp"].dt.tz is not None
    assert frame.watermark == datetime(2026, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="timestamp column"):
        get_parser("csv_timeseries_v1")(
            source_config=config,
            dataset_alias="prices",
            acquired=acquired.model_copy(update={"payload": b"close\n1\n"}),
        )


def test_local_file_ingest_publishes_and_appends_atomically(tmp_path) -> None:
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("timestamp,close\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    store = open_blob_store(f"file:{tmp_path / 'store'}")
    config = _config(str(csv_path))
    first = run_ingest(
        IngestRequest(source_config=config, run_time=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        store=store,
    )
    assert first.status.value == "ready"
    pointer_before = store.get_json("pointers.json")["synthetic_prices"]

    csv_path.write_text(
        "timestamp,close\n2026-01-01T00:00:00Z,1\n2026-01-02T00:00:00Z,2\n",
        encoding="utf-8",
    )
    second = run_ingest(
        IngestRequest(source_config=config, run_time=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        store=store,
    )
    assert second.status.value == "ready"
    assert store.get_json("pointers.json")["synthetic_prices"] != pointer_before
