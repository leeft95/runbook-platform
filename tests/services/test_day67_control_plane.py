from __future__ import annotations

from datetime import datetime, timedelta, timezone

from runbook.data import DatasetPointerUpdate, build_manifest, open_blob_store, write_manifests
from runbook.services import cli
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository
from runbook.services.runner import ServiceRunner
from runbook.services.worker_backends import WorkerState


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


def test_eligible_queue_skips_blocked_source_without_head_of_line_blocking(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "source_a")
        source_b = _source(repository, "source_b")
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        older = repository.queue_run(
            kind="source", target_id="source_a", slot=base, trigger="manual", force=True, config=source_a
        )
        blocked = repository.queue_run(
            kind="source",
            target_id="source_a",
            slot=base + timedelta(days=1),
            trigger="manual",
            force=True,
            config=source_a,
        )
        unrelated = repository.queue_run(
            kind="source", target_id="source_b", slot=base, trigger="manual", force=True, config=source_b
        )
        older.requested_at = base
        blocked.requested_at = base + timedelta(seconds=1)
        unrelated.requested_at = base + timedelta(seconds=2)
        session.flush()
        eligible = repository.eligible_queued_runs()
        assert [row.run_id for row in eligible] == [older.run_id, unrelated.run_id]


def test_running_source_blocks_an_older_backfill_for_the_same_source(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source = _source(repository, "source")
        later = repository.queue_run(
            kind="source",
            target_id="source",
            slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=source,
        )
        assert repository.claim(later.run_id, "local:later")
        repository.queue_run(
            kind="source",
            target_id="source",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=source,
        )
        session.flush()
        assert repository.eligible_queued_runs() == []


def test_worker_state_contract_is_nonblocking() -> None:
    assert WorkerState(running=True).running
    assert WorkerState(running=False, exit_code=0).exit_code == 0


def test_run_cli_rejects_invalid_capacity_and_interval(capsys) -> None:
    assert cli.main(["run", "--workers", "0"]) == 1
    assert cli.main(["run", "--poll-interval", "0"]) == 1
    assert "poll interval" in capsys.readouterr().out


def test_dependency_release_waits_for_all_required_producers_and_is_idempotent(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "source_a")
        source_b = _source(repository, "source_b")
        profile = repository.save_config(
            "profile",
            "profile",
            {"report_id": "report", "datasets": {"a": "source_a", "b": "source_b"}},
        )
        store = open_blob_store(store_uri)
        refs = {}
        for dataset_id, published in (("source_a", stamp), ("source_b", stamp - timedelta(days=1))):
            manifest, digest = build_manifest(
                dataset_id=dataset_id, watermark=published, published_at=published, files=[]
            )
            refs[dataset_id] = write_manifests(store, [(manifest, digest)])[dataset_id]
        repository.pointer_registry.publish(
            source_id="source_a",
            source_run_id="run-a",
            updates=[DatasetPointerUpdate("source_a", refs["source_a"], stamp, stamp)],
        )
        # Publish the settled old B pointer, then keep B's refresh running.
        repository.pointer_registry.publish(
            source_id="source_b",
            source_run_id="old-b",
            updates=[
                DatasetPointerUpdate("source_b", refs["source_b"], stamp - timedelta(days=1), stamp - timedelta(days=1))
            ],
        )
        run_a = repository.queue_run(
            kind="source", target_id="source_a", slot=stamp, trigger="manual", force=True, config=source_a
        )
        run_b = repository.queue_run(
            kind="source", target_id="source_b", slot=stamp, trigger="manual", force=True, config=source_b
        )
        run_a.status = "success"
        run_b.status = "running"
        run_b.worker_id = "local:b"
        session.flush()
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(
            repository, [source_a, source_b], [profile], {"source_a": "source_a", "source_b": "source_b"}, "test"
        )
        session.flush()
        assert repository.list_runs(kind="profile") == []

        run_b.status = "success"
        repository.pointer_registry.publish(
            source_id="source_b",
            source_run_id=run_b.run_id,
            updates=[DatasetPointerUpdate("source_b", refs["source_b"], stamp, stamp)],
        )
        runner._release_dependencies(
            repository, [source_a, source_b], [profile], {"source_a": "source_a", "source_b": "source_b"}, "test"
        )
        session.flush()
        assert len(repository.list_runs(kind="profile")) == 1
        runner._release_dependencies(
            repository, [source_a, source_b], [profile], {"source_a": "source_a", "source_b": "source_b"}, "test"
        )
        assert len(repository.list_runs(kind="profile")) == 1
