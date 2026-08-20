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
        self.terminal: set[str] = set()

    def submit(self, run_id: str) -> str:
        self.submitted.append(run_id)
        return f"local:{run_id}"

    def poll(self, run_id: str) -> WorkerState:
        return WorkerState(running=run_id not in self.terminal, exit_code=0 if run_id in self.terminal else None)

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


def test_dispatch_capacity_is_durable_and_releases_after_exit(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "capacity_a")
        source_b = _source(repository, "capacity_b")
        slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = repository.queue_run(
            kind="source", target_id="capacity_a", slot=slot, trigger="manual", force=True, config=source_a
        )
        second = repository.queue_run(
            kind="source", target_id="capacity_b", slot=slot, trigger="manual", force=True, config=source_b
        )
        session.commit()
        backend = _Backend()
        runner = ServiceRunner(database=database, backend=backend, workers=1)

        runner._dispatch(session, repository, code_version="test")
        assert backend.submitted == [first.run_id]
        assert len(runner._active) == 1
        assert repository.get_run(second.run_id).status == "queued"

        runner._dispatch(session, repository, code_version="test")
        assert backend.submitted == [first.run_id]
        backend.terminal.add(first.run_id)
        runner._reconcile_workers(session, repository)
        assert runner._active == {}
        assert repository.get_run(first.run_id).status == "failed"

        runner._dispatch(session, repository, code_version="test")
        assert backend.submitted == [first.run_id, second.run_id]
        assert repository.get_run(second.run_id).status == "running"


def test_cancellation_reconciliation_targets_only_local_owner(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "cancel-owner")
        local = repository.queue_run(
            kind="source",
            target_id="cancel-owner",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        other = repository.queue_run(
            kind="source",
            target_id="cancel-owner",
            slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(local.run_id, "local:1")
        assert repository.claim(other.run_id, "local:2")
        assert repository.request_cancel(local.run_id)
        assert repository.request_cancel(other.run_id)
        session.commit()
        backend = _Backend()
        runner = ServiceRunner(database=database, backend=backend, workers=1)
        runner._active[local.run_id] = "local:1"
        runner._reconcile_cancellations(session, repository)
        assert backend.cancelled == [local.run_id]
        assert runner._active == {}
        assert repository.get_run(local.run_id).status == "cancelled"
        assert repository.get_run(other.run_id).status == "running"


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
        repository.pointer_registry.publish(
            source_id="source_a",
            source_run_id=run_a.run_id,
            updates=[DatasetPointerUpdate("source_a", refs["source_a"], stamp, stamp)],
        )
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


def test_dependency_release_ignores_future_generation_work(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source = _source(repository, "generation-source")
        profile_config = repository.save_config(
            "profile", "generation-profile", {"report_id": "report", "datasets": {"x": "generation-source"}}
        )
        source_run = repository.queue_run(
            kind="source", target_id="generation-source", slot=slot, trigger="manual", force=True, config=source
        )
        source_run.status = "success"
        future = repository.queue_run(
            kind="source",
            target_id="generation-source",
            slot=slot + timedelta(days=1),
            trigger="manual",
            force=True,
            config=source,
        )
        store = open_blob_store(store_uri)
        manifest, digest = build_manifest(dataset_id="generation-source", watermark=slot, published_at=slot, files=[])
        ref = write_manifests(store, [(manifest, digest)])["generation-source"]
        repository.pointer_registry.publish(
            source_id="generation-source",
            source_run_id=source_run.run_id,
            updates=[DatasetPointerUpdate("generation-source", ref, slot, slot)],
        )
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(
            repository,
            [source],
            [profile_config],
            {"generation-source": "generation-source"},
            "test",
        )
        session.flush()
        assert len(repository.list_runs(kind="profile")) == 1
        assert repository.get_run(future.run_id).status == "queued"


def test_dependency_release_does_not_mix_newer_and_older_producer_generations(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    old_slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_slot = old_slot + timedelta(days=1)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "generation-a")
        source_b = _source(repository, "generation-b")
        profile_config = repository.save_config(
            "profile",
            "generation-profile",
            {"report_id": "report", "datasets": {"a": "generation-a", "b": "generation-b"}},
        )
        run_a = repository.queue_run(
            kind="source", target_id="generation-a", slot=new_slot, trigger="manual", force=True, config=source_a
        )
        run_b = repository.queue_run(
            kind="source", target_id="generation-b", slot=old_slot, trigger="manual", force=True, config=source_b
        )
        run_a.status = run_b.status = "success"
        store = open_blob_store(store_uri)
        refs = {}
        for dataset_id, watermark in (("generation-a", new_slot), ("generation-b", old_slot)):
            manifest, digest = build_manifest(
                dataset_id=dataset_id, watermark=watermark, published_at=watermark, files=[]
            )
            refs[dataset_id] = write_manifests(store, [(manifest, digest)])[dataset_id]
        repository.pointer_registry.publish(
            source_id="generation-a",
            source_run_id=run_a.run_id,
            updates=[DatasetPointerUpdate("generation-a", refs["generation-a"], new_slot, new_slot)],
        )
        repository.pointer_registry.publish(
            source_id="generation-b",
            source_run_id=run_b.run_id,
            updates=[DatasetPointerUpdate("generation-b", refs["generation-b"], old_slot, old_slot)],
        )
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile_config],
            {"generation-a": "generation-a", "generation-b": "generation-b"},
            "test",
        )
        session.flush()
        assert repository.list_runs(kind="profile") == []


def test_dependency_release_rejects_pointer_overwritten_by_newer_generation(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer_slot = slot + timedelta(days=1)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "overwrite-a")
        source_b = _source(repository, "overwrite-b")
        profile_config = repository.save_config(
            "profile",
            "overwrite-profile",
            {"report_id": "report", "datasets": {"a": "overwrite-a", "b": "overwrite-b"}},
        )
        a_old = repository.queue_run(
            kind="source", target_id="overwrite-a", slot=slot, trigger="manual", force=True, config=source_a
        )
        a_new = repository.queue_run(
            kind="source", target_id="overwrite-a", slot=newer_slot, trigger="manual", force=True, config=source_a
        )
        b_old = repository.queue_run(
            kind="source", target_id="overwrite-b", slot=slot, trigger="manual", force=True, config=source_b
        )
        a_old.status = a_new.status = b_old.status = "success"
        store = open_blob_store(store_uri)
        refs = {}
        for name, dataset_id, watermark in (
            ("a_old", "overwrite-a", slot),
            ("a_new", "overwrite-a", newer_slot),
            ("b_old", "overwrite-b", slot),
        ):
            manifest, digest = build_manifest(
                dataset_id=dataset_id, watermark=watermark, published_at=watermark, files=[]
            )
            refs[name] = write_manifests(store, [(manifest, digest)])[dataset_id]
        repository.pointer_registry.publish(
            source_id="overwrite-a",
            source_run_id=a_old.run_id,
            updates=[DatasetPointerUpdate("overwrite-a", refs["a_old"], slot, slot)],
        )
        repository.pointer_registry.publish(
            source_id="overwrite-a",
            source_run_id=a_new.run_id,
            updates=[DatasetPointerUpdate("overwrite-a", refs["a_new"], newer_slot, newer_slot)],
        )
        repository.pointer_registry.publish(
            source_id="overwrite-b",
            source_run_id=b_old.run_id,
            updates=[DatasetPointerUpdate("overwrite-b", refs["b_old"], slot, slot)],
        )
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile_config],
            {"overwrite-a": "overwrite-a", "overwrite-b": "overwrite-b"},
            "test",
        )
        session.flush()
        assert repository.list_runs(kind="profile") == []

        repository.pointer_registry.publish(
            source_id="overwrite-a",
            source_run_id=a_old.run_id,
            updates=[DatasetPointerUpdate("overwrite-a", refs["a_old"], slot, slot)],
        )
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile_config],
            {"overwrite-a": "overwrite-a", "overwrite-b": "overwrite-b"},
            "test",
        )
        session.flush()
        profiles = repository.list_runs(kind="profile")
        assert len(profiles) == 1
        assert profiles[0].snapshot_payload["datasets"] == {
            "a": refs["a_old"],
            "b": refs["b_old"],
        }


def test_stop_mid_dependency_release_does_not_queue_later_profiles(tmp_path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source = _source(repository, "stop-release-source")
        profiles = [
            repository.save_config(
                "profile",
                profile_id,
                {"report_id": "report", "datasets": {"x": "stop-release-source"}},
            )
            for profile_id in ("stop-release-a", "stop-release-b")
        ]
        source_run = repository.queue_run(
            kind="source", target_id="stop-release-source", slot=slot, trigger="manual", force=True, config=source
        )
        source_run.status = "success"
        store = open_blob_store(store_uri)
        manifest, digest = build_manifest(dataset_id="stop-release-source", watermark=slot, published_at=slot, files=[])
        ref = write_manifests(store, [(manifest, digest)])["stop-release-source"]
        repository.pointer_registry.publish(
            source_id="stop-release-source",
            source_run_id=source_run.run_id,
            updates=[DatasetPointerUpdate("stop-release-source", ref, slot, slot)],
        )
        runner = ServiceRunner(database=database, data_store=store_uri)
        original_queue = repository.queue_run

        def queue_and_stop(**kwargs):
            row = original_queue(**kwargs)
            runner._stop.set()
            return row

        monkeypatch.setattr(repository, "queue_run", queue_and_stop)
        runner._release_dependencies(
            repository,
            [source],
            profiles,
            {"stop-release-source": "stop-release-source"},
            "test",
        )
        session.flush()
        assert len(repository.list_runs(kind="profile")) == 1
        assert source_run.dependencies_released_at is None


def test_stop_mid_dispatch_does_not_spawn_later_workers(tmp_path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source = _source(repository, "stop-dispatch-source")
        rows = [
            repository.queue_run(
                kind="source",
                target_id="stop-dispatch-source",
                slot=datetime(2026, 1, day, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=source,
            )
            for day in (1, 2)
        ]
        session.commit()
        backend = _Backend()
        runner = ServiceRunner(database=database, backend=backend, workers=2)
        original_submit = _Backend.submit

        def submit_and_stop(worker: _Backend, run_id: str) -> str:
            worker_id = original_submit(worker, run_id)
            runner._stop.set()
            return worker_id

        monkeypatch.setattr(_Backend, "submit", submit_and_stop)
        runner._dispatch(session, repository, code_version="test")
        assert backend.submitted == [rows[0].run_id]
        assert backend.cancelled == [rows[0].run_id]
        assert runner._active == {}
        assert [repository.get_run(row.run_id).status for row in rows] == ["queued", "queued"]
