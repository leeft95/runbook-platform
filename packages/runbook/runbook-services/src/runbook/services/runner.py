"""Small durable scheduler and reconciliation loop for local workers."""

from __future__ import annotations

import os
import signal
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Event
from typing import Any

from loguru import logger
from runbook.core import ReportProfile, SourceConfig, open_blob_store
from runbook.core.keying import build_context_hash

from .config import database_url, reports_root, store_uri, validate_config
from .db import sync_engine, sync_sessions, tick_lock
from .logging import RunLogIdentity, write_failure_log
from .models import ConfigRevision, Run
from .pointers import DatasetPointerUpdate, load_manifest, resolve_snapshot
from .repository import RunRepository
from .schedule import latest_due_slot
from .worker_backends import LocalProcessBackend, WorkerState


def _aware_utc(value: datetime) -> datetime:
    """Normalize database timestamps, including SQLite's naive round-trip."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ServiceRunner:
    """Schedule, reconcile, release, and dispatch one local worker per run."""

    def __init__(
        self,
        *,
        database: str | None = None,
        data_store: str | None = None,
        report_root: str | None = None,
        workers: int = 4,
        poll_interval: float = 5.0,
        backend: Any | None = None,
    ):
        if workers < 1:
            raise ValueError("workers must be at least 1")
        if poll_interval <= 0:
            raise ValueError("poll interval must be greater than 0")
        self.database = database
        self.data_store = store_uri(data_store)
        self.report_root = reports_root(report_root)
        self.workers = workers
        self.poll_interval = poll_interval
        self.backend = backend
        self._active: dict[str, str] = {}
        self._outcomes: list[dict[str, Any]] = []
        self._stop = Event()

    @staticmethod
    def _model(config: ConfigRevision) -> SourceConfig | ReportProfile:
        """Reconstruct a validated model from an exact stored revision."""
        return validate_config(config.kind, config.config_id, dict(config.payload)).model

    def _backend(self):
        """Build one persistent process backend for this runner lifetime."""
        if self.backend is None:
            self.backend = LocalProcessBackend(
                env={
                    "RUNBOOK_DATABASE_URL": database_url(self.database),
                    "RUNBOOK_DATA_STORE_URI": self.data_store,
                    "RUNBOOK_REPORTS_ROOT": self.report_root,
                }
            )
        return self.backend

    def tick(self, *, now: datetime | None = None, code_version: str | None = None) -> list[dict[str, Any]]:
        """Run shared cycles until locally owned work is idle, then return outcomes."""
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("tick time must include a timezone")
        self._stop.clear()
        self._outcomes.clear()
        with tick_lock(sync_engine(self.database)) as acquired:
            if not acquired:
                logger.info("tick skipped: runner lock is held")
                return [{"status": "skipped", "reason": "another tick is running"}]
            self._reconcile_orphans()
            first = True
            while first or self._active:
                first = False
                self._cycle(current, code_version=code_version)
                if self._active:
                    time.sleep(0.02)
        return sorted(self._outcomes, key=lambda item: (item.get("requested_at", ""), item["run_id"]))

    def run(self, *, code_version: str | None = None) -> dict[str, Any]:
        """Run the durable polling loop until SIGINT/SIGTERM requests shutdown."""
        self._stop.clear()
        self._outcomes.clear()
        with tick_lock(sync_engine(self.database)) as acquired:
            if not acquired:
                logger.info("runner skipped: runner lock is held")
                return {"status": "skipped", "reason": "another tick is running"}
            logger.info("runner started workers={} poll_interval={}", self.workers, self.poll_interval)
            try:
                previous = {name: signal.getsignal(name) for name in (signal.SIGINT, signal.SIGTERM)}
                for name in previous:
                    signal.signal(name, lambda _signum, _frame: self._stop.set())
            except ValueError:  # signal handlers can only be installed by the main thread
                previous = {}
            try:
                self._reconcile_orphans()
                while not self._stop.is_set():
                    self._cycle(datetime.now(timezone.utc), code_version=code_version)
                    self._stop.wait(self.poll_interval)
                self._shutdown()
                logger.info("runner stopped")
            finally:
                for name, handler in previous.items():
                    signal.signal(name, handler)
        return {"status": "stopped", "outcomes": sorted(self._outcomes, key=lambda item: item["run_id"])}

    def _cycle(self, current: datetime, *, code_version: str | None) -> None:
        """Execute one explicit schedule -> cancel -> poll -> release -> dispatch cycle."""
        with sync_sessions(self.database)() as session:
            repository = RunRepository(session)
            source_configs = repository.list_latest_configs("source")
            profile_configs = repository.list_latest_configs("profile", enabled_only=True)
            producer_by_dataset = self._producer_map(source_configs)
            self._import_legacy_pointers(repository, source_configs, current)
            if not self._stop.is_set():
                self._schedule_sources(repository, source_configs, current)
            session.commit()

            self._reconcile_cancellations(session, repository)
            self._reconcile_workers(session, repository)
            session.commit()

            if self._stop.is_set():
                return
            self._release_dependencies(repository, source_configs, profile_configs, producer_by_dataset, code_version)
            session.commit()

            if self._stop.is_set():
                return
            self._dispatch(session, repository, code_version=code_version)
            session.commit()

    def _reconcile_orphans(self) -> None:
        """Fail or cancel running rows not owned by this backend after restart."""
        with sync_sessions(self.database)() as session:
            repository = RunRepository(session)
            for row in repository.running_runs():
                if row.run_id in self._active:
                    continue
                repository.reconcile_orphan(
                    row.run_id,
                    reason="worker ownership lost / runner restarted",
                )
            session.commit()

    def _schedule_sources(self, repository: RunRepository, configs: list[ConfigRevision], current: datetime) -> None:
        """Queue one idempotent scheduled run for each enabled source."""
        for config in configs:
            if self._stop.is_set():
                return
            model = self._model(config)
            if not isinstance(model, SourceConfig) or not model.enabled:
                continue
            slot = latest_due_slot(model.schedule.cron, model.schedule.timezone, current)
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
        """Resolve and persist an exact report snapshot before dispatch."""
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

    def _reconcile_cancellations(self, session: Any, repository: RunRepository) -> None:
        """Stop only locally owned workers with durable cancellation intent."""
        backend = self._backend()
        for run_id, worker_id in list(self._active.items()):
            row = repository.get_run(run_id)
            if row is None or row.status != "running" or row.cancel_requested_at is None:
                continue
            try:
                backend.cancel(run_id)
            except KeyError:
                pass
            cancelled = repository.cancel_owned(run_id, worker_id)
            if cancelled:
                self._outcomes.append(self._outcome(repository.get_run(run_id) or row))
            self._active.pop(run_id, None)
        session.commit()

    def _reconcile_workers(self, session: Any, repository: RunRepository) -> None:
        """Poll locally owned handles and trust terminal database outcomes."""
        backend = self._backend()
        for run_id, worker_id in list(self._active.items()):
            try:
                state: WorkerState = backend.poll(run_id)
            except KeyError:
                self._active.pop(run_id, None)
                continue
            if state.running:
                continue
            row = repository.get_run(run_id)
            if row is not None and row.status == "running" and row.worker_id == worker_id:
                if row.cancel_requested_at is not None:
                    repository.cancel_owned(run_id, worker_id)
                else:
                    write_failure_log(
                        self.data_store,
                        RunLogIdentity(
                            run_id=run_id,
                            kind=row.kind,
                            target_id=row.target_id,
                            slot=_aware_utc(row.slot),
                        ),
                        RuntimeError("worker exited without terminal outcome"),
                        incomplete=True,
                    )
                    repository.finish_owned(
                        run_id, worker_id, status="failed", reason="worker exited without terminal outcome"
                    )
            if row is not None:
                row = repository.get_run(run_id) or row
                if row.status not in {"queued", "running"}:
                    self._outcomes.append(self._outcome(row))
            self._active.pop(run_id, None)
        session.commit()

    def _release_dependencies(
        self,
        repository: RunRepository,
        source_configs: list[ConfigRevision],
        profile_configs: list[ConfigRevision],
        producer_by_dataset: dict[str, str],
        code_version: str | None,
    ) -> None:
        """Durably release settled source dependencies and pin profile snapshots."""
        store = open_blob_store(self.data_store)
        for source_row in repository.unreleased_successful_sources():
            affected: list[tuple[ConfigRevision, ReportProfile, set[str | None]]] = []
            for config in profile_configs:
                profile = self._model(config)
                if not isinstance(profile, ReportProfile):
                    continue
                producers: set[str | None] = {
                    producer_by_dataset.get(dataset_id) for dataset_id in profile.datasets.values()
                }
                if source_row.target_id in producers:
                    affected.append((config, profile, producers))
            if not affected:
                source_row.dependencies_released_at = datetime.now(timezone.utc)
                continue
            all_represented = True
            for config, profile, producers in affected:
                if None in producers or repository.has_queued_or_running_source({item for item in producers if item}):
                    all_represented = False
                    continue
                try:
                    snapshot = resolve_snapshot(store, profile.datasets, pointer_registry=repository.pointer_registry)
                except ValueError:
                    all_represented = False
                    continue
                identity = (
                    f"profile:{profile.profile_id}:revision={config.revision}:hash={config.config_hash}:"
                    f"snapshot={snapshot.snapshot_id}"
                )
                existing = repository.get_identity(identity)
                if existing is None:
                    repository.queue_run(
                        kind="profile",
                        target_id=profile.profile_id,
                        slot=snapshot.watermark,
                        trigger="dataset",
                        force=True,
                        config=config,
                        identity_key=identity,
                        snapshot_id=snapshot.snapshot_id,
                        snapshot_payload=snapshot.model_dump(mode="json"),
                        context_hash=build_context_hash(profile.execution_config()),
                        code_version=code_version or os.environ.get("RUNBOOK_CODE_VERSION") or "local",
                    )
            if all_represented:
                source_row.dependencies_released_at = datetime.now(timezone.utc)

    def _dispatch(self, session: Any, repository: RunRepository, *, code_version: str | None) -> None:
        """Claim and spawn no more than the configured local capacity."""
        backend = self._backend()
        while len(self._active) < self.workers:
            rows = repository.eligible_queued_runs(limit=500)
            row = next((item for item in rows if item.run_id not in self._active), None)
            if row is None:
                return
            config = repository.get_config(row.kind, row.target_id, row.config_revision)
            if config is None:
                self._fail_preflight(repository, row, "pinned configuration revision is unavailable")
                self._outcomes.append(self._outcome(row))
                continue
            try:
                model = self._model(config)
                if row.kind == "profile":
                    if not isinstance(model, ReportProfile) or not self._pin_profile(repository, row, model):
                        self._outcomes.append(self._outcome(row))
                        continue
                    if row.code_version is None:
                        row.code_version = code_version or os.environ.get("RUNBOOK_CODE_VERSION") or "local"
                elif not isinstance(model, SourceConfig):
                    raise ValueError("pinned source configuration is invalid")
            except Exception as exc:
                self._fail_preflight(repository, row, str(exc))
                self._outcomes.append(self._outcome(row))
                continue
            try:
                worker_id = backend.submit(row.run_id)
                if not repository.claim(row.run_id, worker_id):
                    backend.cancel(row.run_id)
                    session.rollback()
                    continue
                session.commit()
            except Exception as exc:
                session.rollback()
                try:
                    backend.cancel(row.run_id)
                except KeyError:
                    pass
                row = repository.get_run(row.run_id) or row
                self._fail_preflight(repository, row, str(exc))
                self._outcomes.append(self._outcome(row))
                session.commit()
                continue
            self._active[row.run_id] = worker_id

    def _shutdown(self) -> None:
        """Durably cancel and terminate only this runner's workers."""
        if not self._active:
            return
        with sync_sessions(self.database)() as session:
            repository = RunRepository(session)
            for run_id, worker_id in list(self._active.items()):
                row = repository.get_run(run_id)
                if row is None or row.status != "running":
                    self._active.pop(run_id, None)
                    continue
                repository.request_cancel(run_id)
                try:
                    self._backend().cancel(run_id)
                except KeyError:
                    pass
                repository.cancel_owned(run_id, worker_id, reason="runner shutdown")
                self._active.pop(run_id, None)
            session.commit()

    @staticmethod
    def _fail_preflight(repository: RunRepository, row: Run, reason: str) -> None:
        """Persist a terminal failure raised before a worker can start."""
        row.status = "failed"
        row.reason = reason
        row.result = {"status": "failed", "reason": reason}
        row.finished_at = datetime.now(timezone.utc)
        row.updated_at = row.finished_at

    @staticmethod
    def _outcome(row: Run) -> dict[str, Any]:
        """Return the compact JSON outcome used by CLI callers."""
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
