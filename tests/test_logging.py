from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from loguru import logger
from runbook.data.config import SourceConfig
from runbook.data.ingest import IngestRequest, run_ingest
from runbook.data.ingest.adapters.base.http import HttpAdapter
from runbook.data.store import BlobStore
from runbook.sdk.logging import resolve_log_level


def _capture(level: str) -> tuple[io.StringIO, int]:
    """Capture Loguru messages at one level for a single test."""
    sink = io.StringIO()
    token = logger.add(sink, level=level, format="{message}")
    return sink, token


def test_blob_store_logs_writes_and_immutable_noop(tmp_path) -> None:
    """Log mutable writes, immutable writes, and identical immutable no-ops."""
    sink, token = _capture("DEBUG")
    try:
        store = BlobStore(f"file:{tmp_path}")
        store.put("pointers.json", b"{}")
        store.put_immutable("raw.bin", b"payload")
        store.put_immutable("raw.bin", b"payload")
    finally:
        logger.remove(token)
    output = sink.getvalue()
    assert "mode=mutable key=pointers.json bytes=2" in output
    assert "mode=immutable key=raw.bin bytes=7" in output
    assert "write skipped backend=file mode=immutable key=raw.bin reason=identical" in output


def test_http_query_logs_redact_url_query_parameters() -> None:
    """Log HTTP request progress without exposing URL query secrets."""

    class Response:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"payload"

        def close(self) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

    class Session:
        def get(self, *_args, **_kwargs):
            return Response()

    config = SourceConfig(
        source_id="http_logging",
        adapter="http",
        schedule={"cron": "0 * * * *", "timezone": "UTC"},
        datasets={"data": {"dataset_id": "http_data", "parser_id": "csv_timeseries_v1"}},
        params={"download_url": "https://example.test/file?token=secret"},
    )
    observed = datetime(2026, 8, 10, tzinfo=timezone.utc)
    sink, token = _capture("INFO")
    try:
        adapter = HttpAdapter(session=Session())
        readiness = adapter.check(source_config=config, acquisition_run="slot", observed_at=observed)
        adapter.acquire(source_config=config, readiness=readiness, fetched_at=observed)
    finally:
        logger.remove(token)
    output = sink.getvalue()
    assert "operation=http-readiness" in output
    assert "operation=http-download" in output
    assert "token=secret" not in output


def test_ingest_logs_stage_order_and_local_query(tmp_path, pointer_registry) -> None:
    """Expose readiness, acquisition, curation, and writes in order."""
    config = SourceConfig(
        source_id="fixture_logging",
        adapter="local_file",
        schedule={"cron": "0 * * * *", "timezone": "UTC"},
        datasets={"prices": {"dataset_id": "logging_prices", "parser_id": "csv_timeseries_v1"}},
        params={"local_path": str(tmp_path / "source.csv"), "timestamp_column": "timestamp"},
    )
    (tmp_path / "source.csv").write_text("timestamp,close\n2026-08-10T00:00:00Z,82.5\n", encoding="utf-8")
    slot = datetime(2026, 8, 10, tzinfo=timezone.utc)
    sink, token = _capture("INFO")
    try:
        run_ingest(
            IngestRequest(source_config=config, run_time=slot),
            store=BlobStore(f"file:{tmp_path}"),
            pointer_registry=pointer_registry,
        )
    finally:
        logger.remove(token)
    output = sink.getvalue()
    assert output.index("stage=1A readiness") < output.index("stage=1B acquire") < output.index("stage=2 curate")
    assert "stage=2 raw verified" in output
    assert "stage=2 parsed" in output
    assert "stage=2 writing" in output
    assert "stage=2 wrote" in output
    assert "mode=immutable" in output


def test_local_file_acquisition_logs_query(tmp_path, pointer_registry) -> None:
    """Log local source reads with their byte count."""
    source = tmp_path / "source.csv"
    source.write_text("timestamp,close\n2026-08-10T00:00:00Z,82.5\n", encoding="utf-8")
    config = SourceConfig(
        source_id="local_logging",
        adapter="local_file",
        schedule={"cron": "0 * * * *", "timezone": "UTC"},
        datasets={
            "prices": {
                "dataset_id": "local_prices",
                "parser_id": "csv_timeseries_v1",
            }
        },
        params={"local_path": str(source), "timestamp_column": "timestamp"},
    )
    sink, token = _capture("INFO")
    try:
        run_ingest(
            IngestRequest(
                source_config=config,
                run_time=datetime(2026, 8, 10, tzinfo=timezone.utc),
            ),
            store=BlobStore(f"file:{tmp_path / 'store'}"),
            pointer_registry=pointer_registry,
        )
    finally:
        logger.remove(token)
    output = sink.getvalue()
    assert "operation=local-read" in output
    assert "bytes=" in output


def test_log_level_flag_env_precedence(monkeypatch) -> None:
    """Prefer explicit levels and reject unsupported values."""
    monkeypatch.setenv("RUNBOOK_LOG_LEVEL", "DEBUG")
    assert resolve_log_level() == "DEBUG"
    assert resolve_log_level("WARNING") == "WARNING"
    with pytest.raises(ValueError, match="invalid log level"):
        resolve_log_level("TRACE")
