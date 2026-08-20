from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import runbook.services.app as app_module
from runbook.services.app import create_app
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.models import Run
from runbook.services.repository import RunRepository


def _source(repository: RunRepository, source_id: str):
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


def test_cancellation_is_conditional_and_idempotent(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "prices")
        row = repository.queue_run(
            kind="source",
            target_id="prices",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.request_cancel(row.run_id)
        session.commit()
        saved = repository.get_run(row.run_id)
        assert saved is not None and saved.status == "cancelled"
        stamp = saved.cancel_requested_at
        assert not repository.request_cancel(row.run_id)
        assert repository.get_run(row.run_id).cancel_requested_at == stamp

        running = repository.queue_run(
            kind="source",
            target_id="prices",
            slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(running.run_id, "local:1")
        assert repository.request_cancel(running.run_id)
        assert repository.cancel_owned(running.run_id, "local:2") is False
        assert repository.cancel_owned(running.run_id, "local:1") is True
        session.commit()
        assert repository.get_run(running.run_id).status == "cancelled"


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
