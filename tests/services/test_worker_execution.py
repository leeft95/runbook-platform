from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository
from runbook.worker.execution import execute_run


def _source_payload(path: str, *, update_mode: str = "full") -> dict:
    return {
        "adapter": "local_file",
        "enabled": False,
        "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
        "datasets": {
            "prices": {
                "dataset_id": "worker_prices",
                "parser_id": "csv_timeseries_v1",
                "update_mode": update_mode,
            }
        },
        "params": {"local_path": path, "timestamp_column": "timestamp"},
    }


def test_real_worker_source_success_and_pointer_failure_roll_back_together(tmp_path: Path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    source = tmp_path / "prices.csv"
    source.write_text("timestamp,close\n2026-01-01T00:00:00Z,100\n", encoding="utf-8")
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("source", "worker_prices", _source_payload(str(source)))
        row = repository.queue_run(
            kind="source",
            target_id="worker_prices",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(row.run_id, f"local:{os.getpid()}")
        session.commit()

    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)

    def fail_publication(*_args, **_kwargs):
        raise RuntimeError("injected pointer publication failure")

    monkeypatch.setattr("runbook.services.pointers.DatabasePointerRegistry.publish", fail_publication)
    with pytest.raises(RuntimeError, match="injected pointer publication failure"):
        execute_run(row.run_id)

    with sync_sessions(database)() as session:
        saved = RunRepository(session).get_run(row.run_id)
        assert saved is not None and saved.status == "running"
        assert RunRepository(session).pointer_registry.all() == {}
