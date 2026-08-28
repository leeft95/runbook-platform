from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import dash
import httpx
import pytest
import runbook.services.app as app_module
from runbook.data import HistoricalExecutionContext, open_blob_store
from runbook.data.ingest import AcquisitionResult, RawArtifactRecord, ReadinessResult, ReadinessStatus
from runbook.data.manifests import load_manifest
from runbook.data.pointers import DatasetPointerUpdate
from runbook.services.app import create_app
from runbook.services.dash import source_detail
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.models import Run
from runbook.services.repository import RunRepository
from runbook.services.schemas import HistoricalRunRequest
from runbook.worker.execution import execute_run


def _payload(path: str = "unused.csv", *, adapter: str = "local_file") -> dict:
    return {
        "adapter": adapter,
        "enabled": False,
        "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
        "datasets": {
            "prices": {
                "dataset_id": "historical-prices",
                "parser_id": "csv_timeseries_v1",
                "update_mode": "full",
            }
        },
        "params": {"local_path": path, "timestamp_column": "timestamp"},
    }


class _HistoricalWorkerAdapter:
    def validate(self, source_config) -> None:
        del source_config

    def check(
        self,
        *,
        source_config,
        acquisition_run,
        observed_at,
        previous_state=None,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> ReadinessResult:
        assert previous_state is None
        assert execution_context is not None
        return ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=acquisition_run,
            status=ReadinessStatus.ready,
            observed_at=observed_at,
            remote_filename="historical.csv",
        )

    def acquire(
        self,
        *,
        source_config,
        readiness,
        fetched_at,
        previous_state=None,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> AcquisitionResult:
        assert previous_state is None
        assert execution_context is not None
        rows: list[str] = []
        current = execution_context.start_date
        value = 0
        while current <= execution_context.end_date:
            rows.append(f"{current.isoformat()}T00:00:00Z,{value}\n")
            current += timedelta(days=1)
            value += 1
        return AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=readiness.acquisition_run,
                source_filename="historical.csv",
                fetched_at=fetched_at,
            ),
            payload=("timestamp,value\n" + "".join(rows)).encode(),
        )


def test_historical_queue_pins_latest_revision_and_records_immutable_range(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            first = repository.save_config("source", "prices", _payload())
            latest = repository.save_config("source", "prices", {**_payload(), "enabled": True})
            row = repository.queue_historical_run(
                "prices",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            )
        assert first.revision == 1
        assert latest.revision == 2
        assert row.mode == "historical"
        assert row.start_date == date(2026, 1, 1)
        assert row.end_date == date(2026, 3, 31)
        assert row.config_revision == latest.revision
        assert row.config_hash == latest.config_hash
        assert [item.revision for item in repository.list_config_revisions("source", "prices")] == [2, 1]


def test_historical_queue_rejects_invalid_range_before_enqueue(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            repository.save_config("source", "prices", _payload())
            with pytest.raises(ValueError, match="end_date must be on or after start_date"):
                repository.queue_historical_run(
                    "prices",
                    start_date=date(2026, 2, 1),
                    end_date=date(2026, 1, 1),
                )
        assert repository.list_runs() == []


def test_historical_review_revision_is_checked_before_enqueue(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            first = repository.save_config("source", "prices", _payload())
        with session.begin():
            repository.save_config("source", "prices", {**_payload(), "enabled": True})
        with session.begin(), pytest.raises(ValueError, match="changed after review"):
            repository.queue_historical_run(
                "prices",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
                expected_revision=first.revision,
            )
        assert repository.list_runs() == []


def test_historical_success_does_not_release_dependencies_or_advance_pointer(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config("source", "prices", _payload())
            row = repository.queue_run(
                kind="source",
                target_id="prices",
                slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
                mode="historical",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )
            row.status = "success"
        assert repository.unreleased_successful_sources() == []
        assert repository.pointer_registry.all() == {}


def test_historical_runs_keep_existing_same_source_serialization(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config("source", "prices", _payload())
            first = repository.queue_run(
                kind="source",
                target_id="prices",
                slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
                mode="historical",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
            )
            second = repository.queue_run(
                kind="source",
                target_id="prices",
                slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
                mode="historical",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 2),
            )
        assert [item.run_id for item in repository.eligible_queued_runs()] == [first.run_id]
        assert second.mode == "historical"


def test_historical_cancellation_and_reconciliation_use_existing_lifecycle(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config("source", "prices", _payload())
            cancelled = repository.queue_historical_run(
                "prices",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
            )
            orphan = repository.queue_run(
                kind="source",
                target_id="prices",
                slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
                mode="historical",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 2),
            )
            assert repository.claim(cancelled.run_id, "local:cancel")
            assert repository.request_cancel(cancelled.run_id)
            assert repository.cancel_owned(cancelled.run_id, "local:cancel")
            assert repository.claim(orphan.run_id, "local:orphan")
            assert repository.reconcile_orphan(orphan.run_id, reason="worker ownership lost")
        assert repository.get_run(cancelled.run_id).status == "cancelled"
        saved_orphan = repository.get_run(orphan.run_id)
        assert saved_orphan is not None
        assert saved_orphan.status == "failed"
        assert saved_orphan.mode == "historical"
        assert saved_orphan.start_date == date(2026, 2, 1)


def test_historical_ui_review_then_submit_queues_reviewed_request(monkeypatch) -> None:
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def begin(self):
            return self

    class Sessions:
        def __call__(self):
            return Session()

    class Repository:
        queued: list[dict[str, object]] = []

        def __init__(self, _session):
            pass

        async def latest_config(self, _kind: str, _source_id: str):
            return SimpleNamespace(config_id="prices", revision=4)

        async def queue_historical_run(self, source_id: str, **kwargs):
            self.queued.append({"source_id": source_id, **kwargs})
            return SimpleNamespace(run_id="historical-run")

    repository = Repository(None)
    monkeypatch.setattr(source_detail, "AsyncRunRepository", lambda _session: repository)
    app = dash.Dash(__name__, use_pages=True, pages_folder="")
    source_detail.register(app, Sessions())
    key = next(key for key in app.callback_map if key.startswith(f"..{source_detail.PREFIX}-historical-modal.opened"))
    callback = app.callback_map[key]["callback"].__wrapped__

    monkeypatch.setattr(source_detail, "ctx", SimpleNamespace(triggered_id=f"{source_detail.PREFIX}-historical-open"))
    opened = asyncio.run(callback(1, None, None, None, None, "/ui/sources/prices", None, None, None))
    assert opened[0] is True

    monkeypatch.setattr(source_detail, "ctx", SimpleNamespace(triggered_id=f"{source_detail.PREFIX}-historical-review"))
    reviewed = asyncio.run(
        callback(
            None,
            None,
            1,
            None,
            None,
            "/ui/sources/prices",
            "2026-01-01",
            "2026-01-03",
            None,
        )
    )
    assert reviewed[1] == {"display": "none"}
    assert reviewed[4] == {"display": "block"}
    review_text = str(reviewed[3])
    assert "Mode: Historical" in review_text
    assert "Date range: 2026-01-01 → 2026-01-03 (inclusive)" in review_text
    assert "Pointer update: No" in review_text
    assert "Overrides: None" in review_text
    assert reviewed[6] == {
        "source_id": "prices",
        "revision": 4,
        "start_date": "2026-01-01",
        "end_date": "2026-01-03",
    }

    monkeypatch.setattr(source_detail, "ctx", SimpleNamespace(triggered_id=f"{source_detail.PREFIX}-historical-submit"))
    submitted = asyncio.run(
        callback(
            None,
            None,
            None,
            None,
            1,
            "/ui/sources/prices",
            "2026-01-01",
            "2026-01-03",
            reviewed[6],
        )
    )
    assert submitted[0] is False
    assert "Queued historical run historical-run." == submitted[5]
    assert repository.queued[0]["expected_revision"] == 4


def test_historical_request_schema_requires_dates_and_order() -> None:
    assert HistoricalRunRequest(start_date="2026-01-01", end_date="2026-01-02").end_date == date(2026, 1, 2)
    with pytest.raises(ValueError, match="end_date must be on or after start_date"):
        HistoricalRunRequest(start_date="2026-01-02", end_date="2026-01-01")


def test_historical_api_queues_identified_run_and_handles_unknown_source(monkeypatch) -> None:
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    queued = Run(
        run_id="historical-run",
        kind="source",
        target_id="prices",
        mode="historical",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        slot=stamp,
        trigger="manual",
        force=True,
        config_revision=4,
        config_hash="hash",
        status="queued",
        requested_at=stamp,
        updated_at=stamp,
    )

    class FakeRepository:
        def __init__(self, _session) -> None:
            pass

        async def queue_historical_run(self, source_id: str, *, start_date: date, end_date: date) -> Run:
            if source_id == "missing":
                raise LookupError(source_id)
            assert (start_date, end_date) == (date(2026, 1, 1), date(2026, 1, 2))
            return queued

    monkeypatch.setattr(app_module, "AsyncRunRepository", FakeRepository)

    async def exercise() -> None:
        app = create_app(database="postgresql+psycopg://postgres:postgres@localhost/runbook")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/sources/prices/historical-runs",
                json={"start_date": "2026-01-01", "end_date": "2026-01-02"},
            )
            assert response.status_code == 202
            assert response.json()["run_id"] == "historical-run"
            assert response.json()["mode"] == "historical"
            assert response.json()["start_date"] == "2026-01-01"
            missing = await client.post(
                "/api/v1/sources/missing/historical-runs",
                json={"start_date": "2026-01-01", "end_date": "2026-01-02"},
            )
            assert missing.status_code == 404

    asyncio.run(exercise())


def test_historical_run_view_serializes_legacy_normal_rows() -> None:
    from runbook.services.app import _run_view

    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = Run(
        run_id="legacy",
        kind="source",
        target_id="prices",
        slot=stamp,
        trigger="manual",
        force=False,
        config_revision=1,
        config_hash="hash",
        status="queued",
        requested_at=stamp,
        updated_at=stamp,
    )
    assert _run_view(row).mode == "normal"


def test_historical_worker_uses_normal_path_and_fails_unsupported_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    source_path = tmp_path / "prices.csv"
    source_path.write_text("timestamp,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            repository.save_config("source", "prices", _payload(str(source_path)))
            row = repository.queue_historical_run(
                "prices",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
            )
            assert repository.claim(row.run_id, f"local:{os.getpid()}")
    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)
    assert execute_run(row.run_id) == 0
    with sync_sessions(database)() as session:
        saved = RunRepository(session).get_run(row.run_id)
        assert saved is not None
        assert saved.status == "failed"
        assert saved.reason == "Source 'prices' does not support historical date-range execution."
        assert RunRepository(session).pointer_registry.all() == {}


def test_historical_worker_durable_execution_writes_manifest_without_pointer_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    monkeypatch.setattr("runbook.data.ingest.runner.get_adapter", lambda _config: _HistoricalWorkerAdapter())
    stage2_calls: list[dict[str, object]] = []
    import runbook.worker.execution as worker_execution

    original_stage2 = worker_execution.run_stage2_curate

    def capture_stage2(**kwargs):
        stage2_calls.append(kwargs)
        return original_stage2(**kwargs)

    monkeypatch.setattr(worker_execution, "run_stage2_curate", capture_stage2)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            repository.save_config("source", "prices", _payload(adapter="historical_fixture"))
            repository.pointer_registry.publish(
                source_id="prices",
                source_run_id="baseline-run",
                updates=[
                    DatasetPointerUpdate(
                        dataset_id="historical-prices",
                        manifest_ref="curated/historical-prices/manifests/sha256=baseline.json",
                        watermark=stamp,
                        published_at=stamp,
                    )
                ],
                updated_at=stamp,
            )
            row = repository.queue_historical_run(
                "prices",
                start_date=date(2026, 1, 2),
                end_date=date(2026, 1, 3),
            )
            assert repository.claim(row.run_id, f"local:{os.getpid()}")
        baseline = repository.pointer_registry.all()["historical-prices"]

    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)
    assert execute_run(row.run_id) == 0

    store = open_blob_store(store_uri)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        saved = repository.get_run(row.run_id)
        assert saved is not None
        assert saved.status == "success"
        assert saved.result is not None
        assert saved.result["mode"] == "historical"
        assert saved.result["start_date"] == "2026-01-02"
        assert saved.result["end_date"] == "2026-01-03"
        manifest_ref = saved.result["datasets"]["historical-prices"]
        assert manifest_ref.startswith("curated/historical-prices/manifests/sha256=")
        assert store.exists(manifest_ref)
        manifest = load_manifest(store, manifest_ref, expected_dataset_id="historical-prices")
        assert len(manifest.files) == 1
        current = repository.pointer_registry.all()["historical-prices"]
        assert current == baseline
        assert manifest_ref != baseline.manifest_ref
        assert repository.unreleased_successful_sources() == []
    assert stage2_calls[0]["previous_pointers"] == {}
