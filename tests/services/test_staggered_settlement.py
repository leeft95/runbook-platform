from __future__ import annotations

from datetime import datetime, timezone

from runbook.data import DatasetPointerUpdate, build_manifest, open_blob_store, write_manifests
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository
from runbook.services.runner import ServiceRunner


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


def _publish(repository, store, source, run, watermark):
    manifest, digest = build_manifest(
        dataset_id=source.config_id,
        watermark=watermark,
        published_at=watermark,
        files=[],
    )
    ref = write_manifests(store, [(manifest, digest)])[source.config_id]
    repository.pointer_registry.publish(
        source_id=source.config_id,
        source_run_id=run.run_id,
        updates=[DatasetPointerUpdate(source.config_id, ref, watermark, watermark)],
    )
    return ref


def test_staggered_sources_establish_and_advance_one_profile(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    a_slot = datetime(2026, 1, 1, 7, tzinfo=timezone.utc)
    b_slot = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_a, source_b = _source(repository, "stagger-a"), _source(repository, "stagger-b")
        profile = repository.save_config(
            "profile",
            "stagger-profile",
            {"report_id": "report", "datasets": {"a": source_a.config_id, "b": source_b.config_id}},
        )
        store = open_blob_store(store_uri)
        a0 = repository.queue_run(
            kind="source", target_id=source_a.config_id, slot=a_slot, trigger="schedule", force=True, config=source_a
        )
        b0 = repository.queue_run(
            kind="source", target_id=source_b.config_id, slot=b_slot, trigger="schedule", force=True, config=source_b
        )
        a0.status = b0.status = "success"
        _publish(repository, store, source_a, a0, a_slot)
        _publish(repository, store, source_b, b0, b_slot)
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile],
            {source_a.config_id: source_a.config_id, source_b.config_id: source_b.config_id},
            "test",
        )
        automatic = repository.list_runs(kind="profile")
        assert len(automatic) == 1
        assert automatic[0].snapshot_payload["producer_provenance"]

        a1_slot = datetime(2026, 1, 2, 7, tzinfo=timezone.utc)
        a1 = repository.queue_run(
            kind="source", target_id=source_a.config_id, slot=a1_slot, trigger="schedule", force=True, config=source_a
        )
        a1.status = "success"
        _publish(repository, store, source_a, a1, a1_slot)
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile],
            {source_a.config_id: source_a.config_id, source_b.config_id: source_b.config_id},
            "test",
        )
        assert len(repository.list_runs(kind="profile")) == 1

        b1_slot = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
        b1 = repository.queue_run(
            kind="source", target_id=source_b.config_id, slot=b1_slot, trigger="schedule", force=True, config=source_b
        )
        b1.status = "success"
        _publish(repository, store, source_b, b1, b1_slot)
        runner._release_dependencies(
            repository,
            [source_a, source_b],
            [profile],
            {source_a.config_id: source_a.config_id, source_b.config_id: source_b.config_id},
            "test",
        )
        assert len(repository.list_runs(kind="profile")) == 2


def test_manual_profile_pinning_records_barrier_warning(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source = _source(repository, "manual-source")
        profile = repository.save_config(
            "profile", "manual-profile", {"report_id": "report", "datasets": {"data": source.config_id}}
        )
        store = open_blob_store(store_uri)
        source_run = repository.queue_run(
            kind="source", target_id=source.config_id, slot=stamp, trigger="schedule", force=True, config=source
        )
        source_run.status = "success"
        _publish(repository, store, source, source_run, stamp)
        runner = ServiceRunner(database=database, data_store=store_uri)
        runner._release_dependencies(repository, [source], [profile], {source.config_id: source.config_id}, "test")
        manual = repository.queue_run(
            kind="profile", target_id=profile.config_id, slot=stamp, trigger="manual", force=True, config=profile
        )
        model = runner._model(profile)
        assert runner._pin_profile(repository, manual, model)
        assert any("bypassed" in warning for warning in manual.snapshot_payload["warnings"])
        assert manual.snapshot_payload["producer_provenance"]
