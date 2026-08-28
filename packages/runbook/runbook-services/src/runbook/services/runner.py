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
from runbook.core import ReportProfile, Snapshot, SnapshotProducer, SourceConfig, open_blob_store
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
            logger.info("tick lock acquired")
            self._reconcile_orphans()
            first = True
            while first or self._active:
                first = False
                self._cycle(current, code_version=code_version)
                if self._active:
                    time.sleep(0.02)
        logger.info("tick lock released")
        return sorted(self._outcomes, key=lambda item: (item.get("requested_at", ""), item["run_id"]))

    def run(self, *, code_version: str | None = None) -> dict[str, Any]:
        """Run the durable polling loop until SIGINT/SIGTERM requests shutdown."""
        self._stop.clear()
        self._outcomes.clear()
        with tick_lock(sync_engine(self.database)) as acquired:
            if not acquired:
                logger.info("runner skipped: runner lock is held")
                return {"status": "skipped", "reason": "another runner is running"}
            logger.info("runner lock acquired")
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
        logger.info("runner lock released")
        return {"status": "stopped", "outcomes": sorted(self._outcomes, key=lambda item: item["run_id"])}

    def _cycle(self, current: datetime, *, code_version: str | None) -> None:
        """Execute one explicit schedule -> cancel -> poll -> release -> dispatch cycle."""
        logger.info("cycle started active={} now={}", len(self._active), current.isoformat())
        with sync_sessions(self.database)() as session:
            repository = RunRepository(session)
            source_configs = repository.list_latest_configs("source")
            profile_configs = repository.list_latest_configs("profile", enabled_only=True)
            producer_by_dataset = self._producer_map(source_configs)
            self._import_legacy_pointers(repository, source_configs, current)
            scheduled = 0
            if not self._stop.is_set():
                scheduled = self._schedule_sources(repository, source_configs, current)
            session.commit()
            logger.info("cycle scheduled={} active={}", scheduled, len(self._active))

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
                write_failure_log(
                    self.data_store,
                    self._log_identity(repository, row),
                    RuntimeError("worker ownership lost / runner restarted"),
                    incomplete=True,
                )
                repository.reconcile_orphan(
                    row.run_id,
                    reason="worker ownership lost / runner restarted",
                )
                logger.warning(
                    "orphan reconciled run_id={} status={}",
                    row.run_id,
                    "cancelled" if row.cancel_requested_at else "failed",
                )
            session.commit()

    def _schedule_sources(self, repository: RunRepository, configs: list[ConfigRevision], current: datetime) -> int:
        """Queue one idempotent scheduled run for each enabled source."""
        count = 0
        for config in configs:
            if self._stop.is_set():
                return count
            model = self._model(config)
            if not isinstance(model, SourceConfig) or not model.enabled:
                continue
            slot = latest_due_slot(model.schedule.cron, model.schedule.timezone, current)
            repository.queue_run(
                kind="source", target_id=config.config_id, slot=slot, trigger="schedule", force=False, config=config
            )
            count += 1
        return count

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
            if row.trigger == "manual":
                snapshot = self._manual_snapshot(repository, row, profile)
            else:
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

    def _pointer_provenance(
        self,
        repository: RunRepository,
        profile: ReportProfile,
        *,
        require_success: bool,
        expected_producers: dict[str, str] | None = None,
    ) -> tuple[SnapshotProducer, ...] | None:
        """Validate current pointers and collect one run per producer."""
        pointers = repository.pointer_registry.get(profile.datasets.values(), for_update=True)
        aliases: dict[str, list[str]] = defaultdict(list)
        runs: dict[str, Run] = {}
        for alias, dataset_id in sorted(profile.datasets.items()):
            pointer = pointers.get(dataset_id)
            if pointer is None:
                return None
            producer = pointer.source_id
            if expected_producers is not None and expected_producers.get(dataset_id) != producer:
                return None
            aliases[producer].append(alias)
            prior = runs.get(producer)
            if prior is not None and prior.run_id != pointer.source_run_id:
                # All aliases owned by one source must describe one durable run.
                return None
            source_run = repository.get_run(pointer.source_run_id)
            if source_run is None or source_run.kind != "source" or source_run.target_id != producer:
                return None
            if require_success and source_run.status != "success":
                return None
            runs[producer] = source_run
        return tuple(
            SnapshotProducer(
                producer_id=producer,
                source_run_id=runs[producer].run_id,
                slot=_aware_utc(runs[producer].slot),
                aliases=tuple(aliases[producer]),
            )
            for producer in sorted(runs)
        )

    def _manual_snapshot(self, repository: RunRepository, row: Run, profile: ReportProfile) -> Snapshot:
        """Pin latest pointers and preserve an explicit barrier-bypass notice."""
        store = open_blob_store(self.data_store)
        expected = self._configured_producers(repository, profile)
        provenance = self._pointer_provenance(
            repository,
            profile,
            require_success=True,
            expected_producers=expected,
        )
        if provenance is None:
            raise ValueError("current pointer provenance is incomplete")
        baseline = repository.latest_automatic_profile(profile.profile_id, row.config_revision, row.config_hash)
        warnings = ["Automatic dependency barrier bypassed by manual profile run."]
        if baseline is None:
            warnings.append("Automatic baseline unavailable; producer advancement was not checked.")
        else:
            base = self._snapshot_from_run(baseline)
            if base is None:
                warnings.append("Automatic baseline unavailable; producer advancement was not checked.")
            else:
                current = resolve_snapshot(
                    store,
                    profile.datasets,
                    pointer_registry=repository.pointer_registry,
                    producer_provenance=provenance,
                )
                for producer in self._non_advanced_producers(current, base):
                    warnings.append(f"Producer {producer!r} did not advance beyond the latest automatic baseline.")
        return resolve_snapshot(
            store,
            profile.datasets,
            pointer_registry=repository.pointer_registry,
            producer_provenance=provenance,
            warnings=warnings,
        )

    def _configured_producers(self, repository: RunRepository, profile: ReportProfile) -> dict[str, str]:
        """Resolve configured ownership for every dataset used by a profile."""
        owners: dict[str, str] = {}
        for config in repository.list_latest_configs("source"):
            model = self._model(config)
            if not isinstance(model, SourceConfig):
                continue
            for binding in model.datasets.values():
                owners.setdefault(binding.dataset_id, model.source_id)
        return {dataset_id: owners[dataset_id] for dataset_id in profile.datasets.values() if dataset_id in owners}

    @staticmethod
    def _snapshot_from_run(row: Run) -> Snapshot | None:
        """Parse one persisted pinned snapshot, tolerating legacy payloads."""
        if not isinstance(row.snapshot_payload, dict):
            return None
        try:
            return Snapshot.model_validate(row.snapshot_payload)
        except ValueError:
            return None

    @staticmethod
    def _non_advanced_producers(
        current: Snapshot,
        baseline: Snapshot,
    ) -> list[str]:
        """Return producer IDs whose current provenance/ref did not advance."""
        current_by_id = {item.producer_id: item for item in current.producer_provenance}
        baseline_by_id = {item.producer_id: item for item in baseline.producer_provenance}
        if baseline_by_id:
            return sorted(
                producer
                for producer in set(current_by_id) | set(baseline_by_id)
                if producer not in current_by_id
                or producer not in baseline_by_id
                or current_by_id[producer].source_run_id == baseline_by_id[producer].source_run_id
            )
        # Legacy snapshots have no producer evidence. Compare each producer's
        # aliases to the old manifest refs instead.
        result: list[str] = []
        for producer, evidence in current_by_id.items():
            baseline_refs = {alias: baseline.datasets.get(alias) for alias in evidence.aliases}
            current_refs = {alias: current.datasets.get(alias) for alias in evidence.aliases}
            if current_refs == baseline_refs:
                result.append(producer)
        return result

    def _reconcile_cancellations(self, session: Any, repository: RunRepository) -> None:
        """Stop only locally owned workers with durable cancellation intent."""
        backend = self._backend()
        for run_id, worker_id in list(self._active.items()):
            row = repository.get_run(run_id)
            if row is None or row.status != "running" or row.cancel_requested_at is None:
                continue
            write_failure_log(
                self.data_store,
                self._log_identity(repository, row),
                RuntimeError("worker cancellation requested"),
                incomplete=True,
            )
            try:
                backend.cancel(run_id)
            except KeyError:
                pass
            cancelled = repository.cancel_owned(run_id, worker_id)
            if cancelled:
                self._outcomes.append(self._outcome(repository.get_run(run_id) or row))
                logger.info("worker cancelled run_id={} worker_id={}", run_id, worker_id)
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
                    write_failure_log(
                        self.data_store,
                        self._log_identity(repository, row),
                        RuntimeError("worker exited after cancellation request"),
                        incomplete=True,
                    )
                    repository.cancel_owned(run_id, worker_id)
                else:
                    write_failure_log(
                        self.data_store,
                        self._log_identity(repository, row),
                        RuntimeError("worker exited without terminal outcome"),
                        incomplete=True,
                    )
                    repository.finish_owned(
                        run_id, worker_id, status="failed", reason="worker exited without terminal outcome"
                    )
                    logger.warning("worker exited without outcome run_id={} worker_id={}", run_id, worker_id)
            if row is not None:
                row = repository.get_run(run_id) or row
                if row.status not in {"queued", "running"}:
                    self._outcomes.append(self._outcome(row))
            self._active.pop(run_id, None)
            logger.info("worker handle released run_id={} exit_code={}", run_id, state.exit_code)
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
        for source_row in repository.unreleased_successful_sources():
            if self._stop.is_set():
                return
            affected: list[tuple[ConfigRevision, ReportProfile, set[str | None]]] = []
            for config in profile_configs:
                if self._stop.is_set():
                    return
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
                # Resolve and validate the current identity before applying
                # the baseline barrier. This also makes a second source row
                # in one reconciliation see a snapshot queued by the first.
                snapshot = self._settled_snapshot(repository, profile, producers)
                if snapshot is None:
                    all_represented = False
                    continue
                if self._stop.is_set():
                    return
                identity = (
                    f"profile:{profile.profile_id}:revision={config.revision}:hash={config.config_hash}:"
                    f"snapshot={snapshot.snapshot_id}"
                )
                existing = repository.get_identity(identity)
                if existing is None:
                    baseline_row = repository.latest_automatic_profile(
                        profile.profile_id,
                        config.revision,
                        config.config_hash,
                    )
                    baseline = self._snapshot_from_run(baseline_row) if baseline_row is not None else None
                    if baseline is not None and self._non_advanced_producers(snapshot, baseline):
                        all_represented = False
                        continue
                    if self._stop.is_set():
                        return
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
                    logger.info(
                        "dependency release profile={} snapshot={} source_run_id={}",
                        profile.profile_id,
                        snapshot.snapshot_id,
                        source_row.run_id,
                    )
            if all_represented:
                source_row.dependencies_released_at = datetime.now(timezone.utc)

    def _settled_snapshot(
        self,
        repository: RunRepository,
        profile: ReportProfile,
        producers: set[str | None],
    ) -> Snapshot | None:
        """Resolve current pointers with durable provenance and no slot gate."""
        if None in producers:
            return None
        provenance = self._pointer_provenance(
            repository,
            profile,
            require_success=True,
            expected_producers=self._configured_producers(repository, profile),
        )
        if provenance is None or {item.producer_id for item in provenance} != {item for item in producers if item}:
            return None
        try:
            return resolve_snapshot(
                open_blob_store(self.data_store),
                profile.datasets,
                pointer_registry=repository.pointer_registry,
                producer_provenance=provenance,
            )
        except (OSError, TypeError, ValueError):
            return None

    def _dispatch(self, session: Any, repository: RunRepository, *, code_version: str | None) -> None:
        """Claim and spawn no more than the configured local capacity."""
        backend = self._backend()
        while len(self._active) < self.workers:
            if self._stop.is_set():
                return
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
            if self._stop.is_set():
                return
            # Spawn failures are ordinary preflight failures.  Once a process
            # exists, however, a claim/commit error is a database failure: the
            # row must remain queued and the original exception must escape.
            # Treating that error as a worker preflight failure loses the
            # distinction between an unclaimed row and a failed run.
            try:
                worker_id = backend.submit(row.run_id)
            except Exception as exc:
                self._fail_preflight(repository, row, str(exc))
                self._outcomes.append(self._outcome(row))
                continue
            if self._stop.is_set():
                try:
                    backend.cancel(row.run_id)
                except KeyError:
                    pass
                return

            try:
                claimed = repository.claim(row.run_id, worker_id)
            except Exception:
                session.rollback()
                try:
                    backend.cancel(row.run_id)
                except Exception:  # preserve the original database error
                    pass
                raise
            if not claimed:
                session.rollback()
                try:
                    backend.cancel(row.run_id)
                except KeyError:
                    pass
                continue

            try:
                session.commit()
            except Exception:
                session.rollback()
                try:
                    backend.cancel(row.run_id)
                except Exception:  # preserve the original database error
                    pass
                raise
            self._active[row.run_id] = worker_id
            logger.info("worker dispatched run_id={} worker_id={}", row.run_id, worker_id)

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
                write_failure_log(
                    self.data_store,
                    self._log_identity(repository, row),
                    RuntimeError("runner shutdown"),
                    incomplete=True,
                )
                try:
                    self._backend().cancel(run_id)
                except KeyError:
                    pass
                repository.cancel_owned(run_id, worker_id, reason="runner shutdown")
                logger.info("worker cancelled for shutdown run_id={} worker_id={}", run_id, worker_id)
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
            "mode": row.mode or "normal",
            "start_date": row.start_date.isoformat() if row.start_date else None,
            "end_date": row.end_date.isoformat() if row.end_date else None,
            "slot": _aware_utc(row.slot).isoformat(),
            "requested_at": _aware_utc(row.requested_at).isoformat(),
            "status": row.status,
            "reason": row.reason,
            "artifact_id": row.artifact_id,
            "log_ref": (row.result or {}).get("log_ref"),
        }

    def _log_identity(self, repository: RunRepository, row: Run) -> RunLogIdentity:
        """Use the same report-aware log path as the worker when available."""
        report_id = None
        if row.kind == "profile":
            config = repository.get_config(row.kind, row.target_id, row.config_revision)
            if config is not None:
                try:
                    model = self._model(config)
                except Exception:
                    model = None
                if isinstance(model, ReportProfile):
                    report_id = model.report_id
        return RunLogIdentity(
            run_id=row.run_id,
            kind=row.kind,
            target_id=row.target_id,
            slot=_aware_utc(row.slot),
            report_id=report_id,
        )
