from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from runbook.data import DatasetPointerUpdate, build_manifest, open_blob_store, write_manifests
from runbook.services import runner as runner_module
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.logging import RunLogIdentity, read_log_tail
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


class _TerminalBackend:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def submit(self, run_id: str) -> str:
        return f"local:{run_id}"

    def poll(self, _run_id: str) -> WorkerState:
        return WorkerState(running=False, exit_code=17)

    def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)


def test_unexpected_exit_reconciles_failure_and_incomplete_log(tmp_path: Path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "unexpected")
        row = repository.queue_run(
            kind="source",
            target_id="unexpected",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(row.run_id, "local:unexpected")
        session.commit()
        runner = ServiceRunner(database=database, data_store=store_uri, backend=_TerminalBackend())
        runner._active[row.run_id] = "local:unexpected"
        runner._reconcile_workers(session, repository)
        assert runner._active == {}
        saved = repository.get_run(row.run_id)
        assert saved is not None
        assert saved.status == "failed"
        assert saved.reason == "worker exited without terminal outcome"
        tail = read_log_tail(
            open_blob_store(store_uri),
            RunLogIdentity(row.run_id, "source", "unexpected", row.slot.replace(tzinfo=timezone.utc)),
        )
        assert tail["incomplete"] is True
        assert "worker exited without terminal outcome" in tail["text"]


def test_restart_reconciles_orphan_with_reason_and_preserves_cancel_intent(tmp_path: Path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "orphan")
        failed = repository.queue_run(
            kind="source",
            target_id="orphan",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        cancelled = repository.queue_run(
            kind="source",
            target_id="orphan",
            slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(failed.run_id, "local:gone")
        assert repository.claim(cancelled.run_id, "local:gone-2")
        assert repository.request_cancel(cancelled.run_id)
        session.commit()
        ServiceRunner(database=database, data_store=store_uri)._reconcile_orphans()

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        assert repository.get_run(failed.run_id).reason == "worker ownership lost / runner restarted"
        assert repository.get_run(cancelled.run_id).status == "cancelled"
        assert repository.get_run(cancelled.run_id).reason == "cancel requested"


def test_shutdown_cancels_only_owned_workers(tmp_path: Path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = _source(repository, "shutdown")
        local = repository.queue_run(
            kind="source",
            target_id="shutdown",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        other = repository.queue_run(
            kind="source",
            target_id="shutdown",
            slot=datetime(2026, 1, 2, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(local.run_id, "local:owned")
        assert repository.claim(other.run_id, "local:other")
        session.commit()
        backend = _TerminalBackend()
        runner = ServiceRunner(database=database, backend=backend)
        runner._active[local.run_id] = "local:owned"
        runner._shutdown()
        assert backend.cancelled == [local.run_id]

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        assert repository.get_run(local.run_id).status == "cancelled"
        assert repository.get_run(other.run_id).status == "running"


def test_tick_and_run_share_cycle_and_lock_refusal_is_structured(tmp_path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    runner = ServiceRunner(database=database)
    calls: list[str] = []

    def cycle(current, *, code_version):
        calls.append(f"{current.tzinfo}:{code_version}")
        runner._stop.set()

    monkeypatch.setattr(runner, "_cycle", cycle)
    assert runner.run(code_version="test")["status"] == "stopped"
    assert calls

    @contextmanager
    def refused(_engine):
        yield False

    monkeypatch.setattr(runner_module, "tick_lock", refused)
    assert runner.tick(now=datetime(2026, 1, 1, tzinfo=timezone.utc)) == [
        {"status": "skipped", "reason": "another tick is running"}
    ]


def test_lifecycle_diagnostics_include_cycle_and_lock_release(tmp_path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    messages: list[str] = []

    class _Logger:
        def info(self, message: str, *_args) -> None:
            messages.append(message)

        def warning(self, *_args) -> None:
            pass

    monkeypatch.setattr(runner_module, "logger", _Logger())
    ServiceRunner(database=database).tick(now=datetime(2026, 1, 1, tzinfo=timezone.utc), code_version="test")
    assert "tick lock acquired" in messages
    assert "cycle started active={} now={}" in messages
    assert "cycle scheduled={} active={}" in messages
    assert "tick lock released" in messages


def test_dependency_release_accepts_staggered_slots_but_rejects_failed_run(tmp_path: Path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old_slot = slot - timedelta(days=1)
    next_slot = slot + timedelta(days=1)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a = _source(repository, "producer_a")
        source_b = _source(repository, "producer_b")
        profile_config = repository.save_config(
            "profile",
            "profile",
            {"report_id": "report", "datasets": {"a": "producer_a", "b": "producer_b"}},
        )
        baseline_a = repository.queue_run(
            kind="source", target_id="producer_a", slot=slot, trigger="manual", force=True, config=source_a
        )
        baseline_b = repository.queue_run(
            kind="source", target_id="producer_b", slot=old_slot, trigger="manual", force=True, config=source_b
        )
        baseline_a.status = baseline_b.status = "success"
        store = open_blob_store(store_uri)
        refs = {}
        for dataset_id, watermark in (("producer_a", slot), ("producer_b", old_slot)):
            manifest, digest = build_manifest(
                dataset_id=dataset_id, watermark=watermark, published_at=watermark, files=[]
            )
            refs[dataset_id] = write_manifests(store, [(manifest, digest)])[dataset_id]
        repository.pointer_registry.publish(
            source_id="producer_a",
            source_run_id=baseline_a.run_id,
            updates=[DatasetPointerUpdate("producer_a", refs["producer_a"], slot, slot)],
        )
        repository.pointer_registry.publish(
            source_id="producer_b",
            source_run_id=baseline_b.run_id,
            updates=[DatasetPointerUpdate("producer_b", refs["producer_b"], old_slot, old_slot)],
        )
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile_config],
            {"producer_a": "producer_a", "producer_b": "producer_b"},
            "test",
        )
        session.flush()
        assert len(repository.list_runs(kind="profile")) == 1
        assert baseline_a.dependencies_released_at is not None
        assert baseline_b.dependencies_released_at is not None

        next_a = repository.queue_run(
            kind="source", target_id="producer_a", slot=next_slot, trigger="manual", force=True, config=source_a
        )
        next_b = repository.queue_run(
            kind="source", target_id="producer_b", slot=next_slot, trigger="manual", force=True, config=source_b
        )
        next_a.status = "success"
        next_b.status = "failed"
        next_refs = {}
        for dataset_id in ("producer_a", "producer_b"):
            manifest, digest = build_manifest(
                dataset_id=dataset_id, watermark=next_slot, published_at=next_slot, files=[]
            )
            next_refs[dataset_id] = write_manifests(store, [(manifest, digest)])[dataset_id]
        repository.pointer_registry.publish(
            source_id="producer_a",
            source_run_id=next_a.run_id,
            updates=[DatasetPointerUpdate("producer_a", next_refs["producer_a"], next_slot, next_slot)],
        )
        repository.pointer_registry.publish(
            source_id="producer_b",
            source_run_id=next_b.run_id,
            updates=[DatasetPointerUpdate("producer_b", next_refs["producer_b"], next_slot, next_slot)],
        )
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile_config],
            {"producer_a": "producer_a", "producer_b": "producer_b"},
            "test",
        )
        session.flush()
        assert len(repository.list_runs(kind="profile")) == 1
        assert next_a.dependencies_released_at is None
        assert next_b.dependencies_released_at is None

        next_b.status = "success"
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile_config],
            {"producer_a": "producer_a", "producer_b": "producer_b"},
            "test",
        )
        session.flush()
        assert len(repository.list_runs(kind="profile")) == 2
        assert next_a.dependencies_released_at is not None
        assert next_b.dependencies_released_at is not None


def test_dependency_release_rolls_back_without_marker_on_profile_queue_failure(tmp_path: Path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source = _source(repository, "rollback-source")
        profile_config = repository.save_config(
            "profile", "rollback-profile", {"report_id": "report", "datasets": {"x": "rollback-source"}}
        )
        source_run = repository.queue_run(
            kind="source", target_id="rollback-source", slot=slot, trigger="manual", force=True, config=source
        )
        source_run.status = "success"
        store = open_blob_store(store_uri)
        manifest, digest = build_manifest(dataset_id="rollback-source", watermark=slot, published_at=slot, files=[])
        ref = write_manifests(store, [(manifest, digest)])["rollback-source"]
        repository.pointer_registry.publish(
            source_id="rollback-source",
            source_run_id=source_run.run_id,
            updates=[DatasetPointerUpdate("rollback-source", ref, slot, slot)],
        )
        session.commit()
        runner = ServiceRunner(database=database, data_store=store_uri)
        profile = runner._model(profile_config)
        producer_map = {"rollback-source": "rollback-source"}

        def fail_queue(**_kwargs):
            raise RuntimeError("injected profile queue failure")

        monkeypatch.setattr(repository, "queue_run", fail_queue)
        with pytest.raises(RuntimeError, match="injected profile queue failure"):
            runner._release_dependencies(repository, [source], [profile_config], producer_map, "test")
        session.rollback()
        assert repository.get_run(source_run.run_id).dependencies_released_at is None
        assert repository.list_runs(kind="profile") == []
        assert profile.profile_id == "rollback-profile"
