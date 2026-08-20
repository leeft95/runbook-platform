from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository
from runbook.services.runner import ServiceRunner


def _source_config():
    return {
        "adapter": "local_file",
        "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
        "datasets": {
            "prices": {
                "dataset_id": "prices",
                "parser_id": "csv_timeseries_v1",
                "update_mode": "full",
            }
        },
        "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
    }


def test_claim_is_single_owner_and_terminal_write_is_guarded(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("source", "prices", _source_config())
        row = repository.queue_run(
            kind="source",
            target_id="prices",
            slot=slot,
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(row.run_id, "local:101")
        assert not repository.claim(row.run_id, "local:202")
        session.commit()

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        assert repository.finish_owned(row.run_id, "local:202", status="success") is False
        assert repository.finish_owned(row.run_id, "local:101", status="success") is True
        session.commit()

    with sync_sessions(database)() as session:
        saved = RunRepository(session).get_run(row.run_id)
        assert saved is not None
        assert saved.status == "success"
        assert saved.worker_id == "local:101"


def test_cancelled_run_cannot_be_claimed(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("source", "prices", _source_config())
        row = repository.queue_run(
            kind="source",
            target_id="prices",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.cancel(row.run_id)
        assert not repository.claim(row.run_id, "local:101")
        session.commit()
        assert row.status == "cancelled"


def test_tick_executes_a_source_in_a_fresh_worker_process(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    config_payload = _source_config()
    config_payload["enabled"] = False
    config_payload["params"]["local_path"] = str(Path("data/fixtures/daily_prices.csv").resolve())
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("source", "prices", config_payload)
        repository.queue_run(
            kind="source",
            target_id="prices",
            slot=slot,
            trigger="manual",
            force=True,
            config=config,
        )
        session.commit()

    outcomes = ServiceRunner(database=database, data_store=store, workers=1).tick(now=slot)

    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "success"
    with sync_sessions(database)() as session:
        saved = RunRepository(session).list_runs(limit=1)[0]
        assert saved.status == "success"
        assert saved.worker_id and saved.worker_id.startswith("local:")
        assert RunRepository(session).pointer_registry.get(["prices"])["prices"].source_run_id == saved.run_id
