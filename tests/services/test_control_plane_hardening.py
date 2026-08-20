from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import runbook.services.app as app_module
from runbook.services.app import create_app
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.models import Run
from runbook.services.repository import RunRepository
from runbook.services.runner import ServiceRunner
from runbook.services.worker_backends import WorkerState


def _source(repository: RunRepository, source_id: str):
    """Create a minimal local-file source revision for control-plane tests."""
    return repository.save_config(
        "source",
        source_id,
        {
            "adapter": "local_file",
            "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
            "datasets": {
                source_id: {
                    "dataset_id": source_id,
                    "parser_id": "csv_timeseries_v1",
                    "update_mode": "full",
                }
            },
            "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
        },
    )


class _Backend:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, run_id: str) -> str:
        self.submitted.append(run_id)
        return f"local:{run_id}"

    def poll(self, _run_id: str) -> WorkerState:
        return WorkerState(running=True)

    def cancel(self, _run_id: str) -> None:
        return None


def test_stop_during_reconciliation_skips_release_and_dispatch(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    backend = _Backend()
    runner = ServiceRunner(database=database, backend=backend)

    def stop(*_args) -> None:
        runner._stop.set()

    runner._reconcile_cancellations = stop
    runner._reconcile_workers = lambda *_args: None
    runner._release_dependencies = lambda *_args: pytest.fail("release ran during shutdown")
    runner._dispatch = lambda *_args, **_kwargs: pytest.fail("dispatch ran during shutdown")
    runner._cycle(datetime.now(timezone.utc), code_version="test")
    assert backend.submitted == []


def test_eligible_queue_finds_unrelated_work_after_500_blocked_rows(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "source_a")
        source_b = _source(repository, "source_b")
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        blocker = repository.queue_run(
            kind="source", target_id="source_a", slot=base, trigger="manual", force=True, config=source_a
        )
        assert repository.claim(blocker.run_id, "local:blocker")
        for index in range(501):
            row = repository.queue_run(
                kind="source",
                target_id="source_a",
                slot=base + timedelta(days=index + 1),
                trigger="manual",
                force=True,
                config=source_a,
            )
            row.requested_at = base + timedelta(seconds=index + 1)
        unrelated = repository.queue_run(
            kind="source", target_id="source_b", slot=base, trigger="manual", force=True, config=source_b
        )
        unrelated.requested_at = base + timedelta(seconds=1000)
        session.commit()
        eligible = repository.eligible_queued_runs(limit=1)
        assert [row.run_id for row in eligible] == [unrelated.run_id]


def test_orphan_reconciliation_covers_all_rows_and_preserves_terminal_races(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "source")
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(501):
            row = repository.queue_run(
                kind="source",
                target_id="source",
                slot=base + timedelta(days=index),
                trigger="manual",
                force=True,
                config=config,
            )
            row.status = "running"
            row.worker_id = f"local:{index}"
            if index == 500:
                row.cancel_requested_at = base
            rows.append(row)
        session.commit()
        runner = ServiceRunner(database=database)
        runner._reconcile_orphans()

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        saved = repository.list_runs(target_id="source", limit=500)
        assert len(saved) == 500
        assert repository.running_runs() == []
        assert repository.get_run(rows[500].run_id).status == "cancelled"

        terminal = repository.get_run(rows[0].run_id)
        assert terminal is not None
        terminal.status = "success"
        session.commit()
        assert repository.reconcile_orphan(rows[0].run_id, reason="race") is False


def test_http_cancellation_lifecycle(monkeypatch) -> None:
    """Exercise every HTTP outcome without requiring an external database."""
    stamp = datetime.now(timezone.utc).replace(microsecond=0)

    def row(run_id: str, status: str, worker_id: str | None = None) -> Run:
        return Run(
            run_id=run_id,
            kind="source",
            target_id="api-source",
            slot=stamp,
            trigger="manual",
            force=True,
            config_revision=1,
            config_hash="hash",
            status=status,
            worker_id=worker_id,
            requested_at=stamp,
            updated_at=stamp,
        )

    rows = {
        "queued": row("queued", "queued"),
        "running": row("running", "running", "local:running"),
        "terminal": row("terminal", "success"),
    }

    class FakeRepository:
        def __init__(self, _session) -> None:
            pass

        async def get_run(self, run_id: str) -> Run | None:
            return rows.get(run_id)

        async def request_cancel(self, run_id: str) -> Run | None:
            saved = rows.get(run_id)
            if saved is None or saved.status not in {"queued", "running"} or saved.cancel_requested_at is not None:
                return saved
            saved.cancel_requested_at = datetime.now(timezone.utc)
            saved.updated_at = saved.cancel_requested_at
            if saved.status == "queued":
                saved.status = "cancelled"
                saved.finished_at = saved.cancel_requested_at
                saved.reason = "cancel requested before worker start"
            return saved

    monkeypatch.setattr(app_module, "AsyncRunRepository", FakeRepository)

    async def exercise() -> None:
        app = create_app(database="postgresql+psycopg://postgres:postgres@localhost/runbook")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.post("/api/v1/runs/missing/cancel")
            assert missing.status_code == 404

            first = await client.post("/api/v1/runs/queued/cancel")
            again = await client.post("/api/v1/runs/queued/cancel")
            assert first.status_code == again.status_code == 202
            assert first.json()["status"] == again.json()["status"] == "cancelled"
            assert first.json()["cancel_requested_at"] == again.json()["cancel_requested_at"]
            assert "cancelling" not in first.json()

            running_first = await client.post("/api/v1/runs/running/cancel")
            running_again = await client.post("/api/v1/runs/running/cancel")
            assert running_first.status_code == running_again.status_code == 202
            assert running_first.json()["status"] == running_again.json()["status"] == "running"
            assert running_first.json()["cancel_requested_at"] == running_again.json()["cancel_requested_at"]

            terminal_response = await client.post("/api/v1/runs/terminal/cancel")
            assert terminal_response.status_code == 202
            assert terminal_response.json()["status"] == "success"

    asyncio.run(exercise())
