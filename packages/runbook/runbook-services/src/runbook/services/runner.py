"""Scheduling and reconciliation for the durable run queue."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from runbook.core import ReportProfile, SourceConfig, open_blob_store
from runbook.core.keying import build_context_hash

from .config import database_url, reports_root, store_uri, validate_config
from .db import sync_engine, sync_sessions, tick_lock
from .models import ConfigRevision, Run
from .pointers import DatasetPointerUpdate, load_manifest, resolve_snapshot
from .repository import RunRepository
from .schedule import latest_due_slot
from .worker_backends import LocalProcessBackend, WorkerState


def _aware_utc(value: datetime) -> datetime:
    """Normalize database timestamps, including SQLite's naive round-trip."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _slot_key(value: datetime) -> str:
    """Format a run slot as a canonical UTC key."""
    return _aware_utc(value).strftime("%Y%m%dT%H%M%SZ")


class ServiceRunner:
    """Schedule runs and reconcile one process-backed worker per run."""

    def __init__(
        self,
        *,
        database: str | None = None,
        data_store: str | None = None,
        report_root: str | None = None,
        workers: int = 4,
        backend: Any | None = None,
    ):
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.database = database
        self.data_store = store_uri(data_store)
        self.report_root = reports_root(report_root)
        self.workers = workers
        self.backend = backend

    @staticmethod
    def _model(config: ConfigRevision) -> SourceConfig | ReportProfile:
        """Reconstruct a validated model from an exact stored revision."""
        return validate_config(config.kind, config.config_id, dict(config.payload)).model

    def _backend(self):
        """Build the configured process backend."""
        if self.backend is not None:
            return self.backend
        return LocalProcessBackend(
            env={
                "RUNBOOK_DATABASE_URL": database_url(self.database),
                "RUNBOOK_DATA_STORE_URI": self.data_store,
                "RUNBOOK_REPORTS_ROOT": self.report_root,
            }
        )

    def tick(self, *, now: datetime | None = None, code_version: str | None = None) -> list[dict[str, Any]]:
        """Schedule due sources, claim capacity, and poll workers to terminal state."""
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("tick time must include a timezone")
        engine = sync_engine(self.database)
        with tick_lock(engine) as acquired:
            if not acquired:
                return [{"status": "skipped", "reason": "another tick is running"}]
            with sync_sessions(self.database)() as session:
                repository = RunRepository(session)
                repository.recover_stale(older_than=current - timedelta(hours=1))
                source_configs = repository.list_latest_configs("source")
                profile_configs = repository.list_latest_configs("profile", enabled_only=True)
                producer_by_dataset = self._producer_map(source_configs)
                self._import_legacy_pointers(repository, source_configs, current)
                self._schedule_sources(repository, source_configs, current)
                session.commit()
                return self._run_queue(
                    session,
                    repository,
                    profile_configs,
                    producer_by_dataset,
                    code_version=code_version,
                )

    def _schedule_sources(self, repository: RunRepository, configs: list[ConfigRevision], current: datetime) -> None:
        """Queue the latest due slot for every enabled source."""
        for config in configs:
            model = self._model(config)
            if not isinstance(model, SourceConfig) or not model.enabled:
                continue
            slot = latest_due_slot(model.schedule.cron, model.schedule.timezone, current)
            active = repository.list_runs(kind="source", target_id=config.config_id, limit=20)
            if any(_aware_utc(row.slot) == slot and row.status in {"queued", "running"} for row in active):
                continue
            repository.queue_run(
                kind="source", target_id=config.config_id, slot=slot, trigger="schedule", force=False, config=config
            )

    def _producer_map(self, configs: list[ConfigRevision]) -> dict[str, str]:
        """Build the one-source-per-dataset ownership map."""
        producers: dict[str, str] = {}
        for config in configs:
            model = self._model(config)
            if not isinstance(model, SourceConfig):
                continue
            for binding in model.datasets.values():
                owner = producers.setdefault(binding.dataset_id, model.source_id)
                if owner != model.source_id:
                    raise ValueError(
                        f"dataset {binding.dataset_id!r} has multiple producers: {owner!r}, {model.source_id!r}"
                    )
        return producers

    def _import_legacy_pointers(
        self, repository: RunRepository, source_configs: list[ConfigRevision], current: datetime
    ) -> None:
        """Import the old root pointer document once into the service registry."""
        registry = repository.pointer_registry
        if not registry.is_empty():
            return
        store = open_blob_store(self.data_store)
        if not store.exists("pointers.json"):
            return
        payload = store.get_json("pointers.json")
        if not isinstance(payload, dict):
            raise ValueError("legacy pointers.json must contain an object")
        producers = self._producer_map(source_configs)
        grouped: dict[str, list[DatasetPointerUpdate]] = defaultdict(list)
        for dataset_id, ref in sorted(payload.items()):
            source_id = producers.get(dataset_id)
            if source_id is None or not isinstance(ref, str):
                raise ValueError(f"legacy pointer has no configured producer: {dataset_id!r}")
            manifest = load_manifest(store, ref, expected_dataset_id=dataset_id)
            grouped[source_id].append(
                DatasetPointerUpdate(
                    dataset_id=dataset_id,
                    manifest_ref=ref,
                    watermark=manifest.watermark,
                    published_at=manifest.published_at,
                )
            )
        for source_id, updates in grouped.items():
            registry.publish(
                source_id=source_id, source_run_id="legacy-pointer-import", updates=updates, updated_at=current
            )

    def _pin_profile(self, repository: RunRepository, row: Run, profile: ReportProfile) -> bool:
        """Resolve and persist the exact snapshot before a profile worker starts."""
        if isinstance(row.snapshot_payload, dict):
            return True
        try:
            snapshot = resolve_snapshot(
                open_blob_store(self.data_store), profile.datasets, pointer_registry=repository.pointer_registry
            )
        except ValueError as exc:
            if str(exc).startswith("no pointer exists"):
                repository.finish(row, status="waiting", reason=str(exc))
                return False
            raise
        if row.trigger != "manual" and snapshot.watermark < _aware_utc(row.slot):
            repository.finish(row, status="waiting", reason="dataset watermark is behind report slot")
            return False
        row.snapshot_id = snapshot.snapshot_id
        row.snapshot_payload = snapshot.model_dump(mode="json")
        row.context_hash = build_context_hash(profile.execution_config())
        return True

    def _run_queue(
        self,
        session,
        repository: RunRepository,
        profile_configs: list[ConfigRevision],
        producer_by_dataset: dict[str, str],
        *,
        code_version: str | None,
    ) -> list[dict[str, Any]]:
        """Drain queued work with bounded capacity and same-source serialization."""
        backend = self._backend()
        active: dict[str, str] = {}
        terminal: list[dict[str, Any]] = []
        while True:
            made_progress = False
            for row in repository.queued_runs(limit=500):
                if len(active) >= self.workers or row.run_id in active:
                    break
                if any(
                    active_row_target == row.target_id for active_row_target in self._active_targets(repository, active)
                ):
                    continue
                config = repository.get_config(row.kind, row.target_id, row.config_revision)
                if config is None:
                    self._fail_preflight(repository, row, "pinned configuration revision is unavailable")
                    session.commit()
                    terminal.append(self._outcome(row))
                    made_progress = True
                    continue
                try:
                    model = self._model(config)
                    if row.kind == "profile":
                        if not isinstance(model, ReportProfile) or not self._pin_profile(repository, row, model):
                            session.commit()
                            terminal.append(self._outcome(row))
                            made_progress = True
                            continue
                        if row.code_version is None:
                            row.code_version = code_version or os.environ.get("RUNBOOK_CODE_VERSION") or "local"
                    elif not isinstance(model, SourceConfig):
                        raise ValueError("pinned source configuration is invalid")
                except Exception as exc:
                    self._fail_preflight(repository, row, str(exc))
                    session.commit()
                    terminal.append(self._outcome(row))
                    made_progress = True
                    continue

                try:
                    worker_id = backend.submit(row.run_id)
                except Exception as exc:
                    self._fail_preflight(repository, row, str(exc))
                    session.commit()
                    terminal.append(self._outcome(row))
                    made_progress = True
                    continue
                try:
                    claimed = repository.claim(row.run_id, worker_id)
                except Exception:
                    session.rollback()
                    backend.cancel(row.run_id)
                    raise
                if not claimed:
                    backend.cancel(row.run_id)
                    session.rollback()
                    repository.get_run(row.run_id)
                    continue
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                    backend.cancel(row.run_id)
                    raise
                active[row.run_id] = worker_id
                made_progress = True
            if not active:
                if not made_progress:
                    break
                continue
            done: list[str] = []
            for run_id in list(active):
                state: WorkerState = backend.poll(run_id)
                if state.running:
                    continue
                done.append(run_id)
                active_row = repository.get_run(run_id)
                if active_row is None:
                    continue
                if active_row.status == "running" and active_row.worker_id == active[run_id]:
                    status = "cancelled" if active_row.cancel_requested_at is not None else "failed"
                    repository.finish(active_row, status=status, reason="worker exited without terminal outcome")
                if active_row.kind == "source" and active_row.status == "success":
                    self._release_profiles(repository, active_row, profile_configs, producer_by_dataset)
                terminal.append(self._outcome(active_row))
            if done:
                for run_id in done:
                    active.pop(run_id, None)
                session.commit()
                continue
            time.sleep(0.02)
        return sorted(terminal, key=lambda item: (item.get("requested_at", ""), item["run_id"]))

    def _release_profiles(
        self,
        repository: RunRepository,
        source_row: Run,
        profile_configs: list[ConfigRevision],
        producer_by_dataset: dict[str, str],
    ) -> None:
        """Release dataset-triggered profiles once their durable pointers resolve."""
        store = open_blob_store(self.data_store)
        for config in profile_configs:
            profile = self._model(config)
            if not isinstance(profile, ReportProfile):
                continue
            producers = {
                producer_by_dataset.get(dataset_id)
                for dataset_id in profile.datasets.values()
                if producer_by_dataset.get(dataset_id) is not None
            }
            if source_row.target_id not in producers:
                continue
            try:
                snapshot = resolve_snapshot(store, profile.datasets, pointer_registry=repository.pointer_registry)
            except ValueError:
                continue
            if repository.successful("profile", profile.profile_id, snapshot.watermark, config_hash=config.config_hash):
                continue
            row = repository.queue_run(
                kind="profile",
                target_id=profile.profile_id,
                slot=snapshot.watermark,
                trigger="dataset",
                force=False,
                config=config,
            )
            row.dependencies_released_at = datetime.now(timezone.utc)

    @staticmethod
    def _active_targets(repository: RunRepository, active: dict[str, str]) -> set[str]:
        """Return targets currently owned by this tick's workers."""
        return {row.target_id for row in repository.list_runs(status="running", limit=500) if row.run_id in active}

    @staticmethod
    def _fail_preflight(repository: RunRepository, row: Run, reason: str) -> None:
        """Persist a terminal preflight failure."""
        row.status = "failed"
        row.reason = reason
        row.result = {"status": "failed", "reason": reason}
        row.finished_at = datetime.now(timezone.utc)
        row.updated_at = row.finished_at

    @staticmethod
    def _outcome(row: Run) -> dict[str, Any]:
        """Return the compact CLI outcome for one run."""
        return {
            "run_id": row.run_id,
            "kind": row.kind,
            "target_id": row.target_id,
            "slot": _aware_utc(row.slot).isoformat(),
            "requested_at": _aware_utc(row.requested_at).isoformat(),
            "status": row.status,
            "reason": row.reason,
            "artifact_id": row.artifact_id,
            "log_ref": (row.result or {}).get("log_ref"),
        }
