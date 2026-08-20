from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
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


class _Backend:
    def __init__(self) -> None:
        self.submitted: list[str] = []
        self.cancelled: list[str] = []

    def submit(self, run_id: str) -> str:
        self.submitted.append(run_id)
        return f"local:{run_id}"

    def poll(self, _run_id: str) -> WorkerState:
        return WorkerState(running=True)

    def cancel(self, _run_id: str) -> None:
        self.cancelled.append(_run_id)


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


def test_run_cli_rejects_invalid_capacity_and_interval(capsys) -> None:
    assert cli.main(["run", "--workers", "0"]) == 1
    assert cli.main(["run", "--poll-interval", "0"]) == 1
    assert "poll interval" in capsys.readouterr().out


def test_dispatch_commit_failure_cleans_only_spawned_worker_and_preserves_queue(tmp_path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "commit_failure")
        row = repository.queue_run(
            kind="source",
            target_id="commit_failure",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        session.commit()
        worker = _Backend()
        runner = ServiceRunner(database=database, backend=worker, workers=1)
        original_commit = session.commit

        def fail_commit() -> None:
            raise RuntimeError("injected claim commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected claim commit failure"):
            runner._dispatch(session, repository, code_version="test")
        monkeypatch.setattr(session, "commit", original_commit)
        session.rollback()
        assert worker.submitted == [row.run_id]
        assert worker.cancelled == [row.run_id]

    assert worker.submitted == [row.run_id]
    with sync_sessions(database)() as session:
        saved = RunRepository(session).get_run(row.run_id)
        assert saved is not None
        assert saved.status == "queued"
        assert saved.worker_id is None


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
