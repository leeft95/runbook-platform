from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context
from typing import Any

from loguru import logger
from runbook.core import Snapshot
from runbook.core.keying import build_context_hash
from runbook.core.utils.hashing import sha256_json
from runbook.data import (
    DatasetPointer,
    DatasetPointerUpdate,
    load_manifest,
    open_blob_store,
    resolve_snapshot,
)
from runbook.data.config import SourceConfig
from runbook.data.ingest import run_stage1_acquire
from runbook.data.ingest.runner import load_previous_append_state
from runbook.data.ingest.runners import run_stage2_curate
from runbook.data.pipeline import slot_key
from runbook.platform.report_run import run_report
from runbook.platform.schedule import latest_due_slot
from runbook.sdk import ReportProfile, resolve_code_version

from .config import reports_root, store_uri, validate_config
from .db import sync_engine, sync_sessions, tick_lock
from .logging import RunLogIdentity, capture_worker_logs, write_failure_log
from .models import ConfigRevision, Run
from .repository import RunRepository


def _aware_utc(value: datetime) -> datetime:
    """Normalize database timestamps, including SQLite's naive round-trip."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _pointer_payload(pointer: DatasetPointer) -> dict[str, Any]:
    """Serialize one current pointer for a source worker."""
    return {
        "dataset_id": pointer.dataset_id,
        "source_id": pointer.source_id,
        "manifest_ref": pointer.manifest_ref,
        "watermark": pointer.watermark.isoformat(),
        "published_at": pointer.published_at.isoformat(),
        "source_run_id": pointer.source_run_id,
        "updated_at": pointer.updated_at.isoformat(),
    }


@dataclass(frozen=True)
class _SourceTask:
    run_id: str
    config: SourceConfig
    pointers: dict[str, DatasetPointer]
    identity: RunLogIdentity


@dataclass(frozen=True)
class _ReportTask:
    run_id: str
    identity: RunLogIdentity
    snapshot: dict[str, Any]


def _source_worker(
    config_payload: dict[str, Any],
    slot_value: str,
    store_uri: str,
    previous_watermarks: dict[str, str],
    pointers_payload: dict[str, dict[str, Any]],
    identity_payload: dict[str, Any],
) -> dict[str, Any]:
    """Run source readiness, acquisition, persistence, and curation in one process."""
    config = SourceConfig.model_validate(config_payload)
    slot = datetime.fromisoformat(slot_value)
    identity = RunLogIdentity(
        run_id=identity_payload["run_id"],
        kind=identity_payload["kind"],
        target_id=identity_payload["target_id"],
        slot=datetime.fromisoformat(identity_payload["slot"]),
        report_id=identity_payload.get("report_id"),
    )
    pointers = {
        key: DatasetPointer(
            dataset_id=value["dataset_id"],
            source_id=value["source_id"],
            manifest_ref=value["manifest_ref"],
            watermark=datetime.fromisoformat(value["watermark"]),
            published_at=datetime.fromisoformat(value["published_at"]),
            source_run_id=value["source_run_id"],
            updated_at=datetime.fromisoformat(value["updated_at"]),
        )
        for key, value in pointers_payload.items()
    }
    watermarks = {key: datetime.fromisoformat(value) for key, value in previous_watermarks.items()}
    with capture_worker_logs(store_uri, identity) as log:
        try:
            store = open_blob_store(store_uri)
            acquisition = run_stage1_acquire(
                source_config=config,
                slot=slot,
                store=store,
                previous_watermarks=watermarks,
            )
            if acquisition.status.value != "ready" or acquisition.acquired is None:
                return {
                    "source_id": config.source_id,
                    "slot": slot_key(slot),
                    "status": acquisition.status.value,
                    "datasets": None,
                    "reason": acquisition.message,
                    "log_ref": log.log_ref,
                }
            logger.info(
                "stage=2 curate source={} slot={} datasets={}",
                config.source_id,
                slot_key(slot),
                sorted(config.datasets),
            )
            curated = run_stage2_curate(
                store=store,
                source_config=config,
                acquired=acquisition.acquired,
                published_at=slot,
                previous_pointers=pointers,
            )
            logger.info(
                "stage=2 complete source={} slot={} datasets={}",
                config.source_id,
                slot_key(slot),
                sorted(curated.datasets),
            )
            return {
                "source_id": config.source_id,
                "slot": slot_key(slot),
                "status": "success",
                "datasets": dict(curated.datasets),
                "pointer_updates": [
                    {
                        "dataset_id": item.dataset_id,
                        "manifest_ref": item.manifest_ref,
                        "watermark": item.watermark.isoformat(),
                        "published_at": item.published_at.isoformat(),
                    }
                    for item in curated.pointer_updates
                ],
                "reason": None,
                "log_ref": log.log_ref,
            }
        except Exception as exc:
            logger.exception("source worker failed run_id={}", identity.run_id)
            return {
                "source_id": config.source_id,
                "slot": slot_key(slot),
                "status": "failed",
                "datasets": None,
                "reason": str(exc),
                "log_ref": log.log_ref,
            }


def _report_worker(
    profile_payload: dict[str, Any],
    slot_value: str,
    code_version: str,
    reports_root: str,
    snapshot_payload: dict[str, Any],
    store_uri: str,
    identity_payload: dict[str, Any],
) -> dict[str, Any]:
    """Run one pinned report with only serializable worker arguments."""
    profile = ReportProfile.model_validate(profile_payload)
    identity = RunLogIdentity(
        run_id=identity_payload["run_id"],
        kind=identity_payload["kind"],
        target_id=identity_payload["target_id"],
        slot=datetime.fromisoformat(identity_payload["slot"]),
        report_id=identity_payload.get("report_id"),
    )
    with capture_worker_logs(store_uri, identity) as log:
        try:
            outcome = run_report(
                store=open_blob_store(store_uri),
                profile=profile,
                slot=datetime.fromisoformat(slot_value),
                code_version=code_version,
                reports_root=reports_root,
                snapshot=(Snapshot.model_validate(snapshot_payload) if isinstance(snapshot_payload, dict) else snapshot_payload),
            ).as_dict()
            outcome["log_ref"] = log.log_ref
            return outcome
        except Exception as exc:
            logger.exception("report worker failed run_id={}", identity.run_id)
            return {
                "profile_id": profile.profile_id,
                "slot": slot_key(datetime.fromisoformat(slot_value)),
                "status": "failed",
                "reason": str(exc),
                "log_ref": log.log_ref,
            }


class ServiceRunner:
    """Execute source-to-curation-to-report DAGs from the PostgreSQL run queue."""

    def __init__(
        self,
        *,
        database: str | None = None,
        data_store: str | None = None,
        report_root: str | None = None,
        workers: int = 4,
        executor_factory: Any | None = None,
    ):
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.database = database
        self.data_store = store_uri(data_store)
        self.report_root = reports_root(report_root)
        self.workers = workers
        self.executor_factory = executor_factory

    def _executor(self):
        """Build the spawn pool or an explicitly injected test executor."""
        if self.executor_factory is not None:
            return self.executor_factory(self.workers)
        return ProcessPoolExecutor(max_workers=self.workers, mp_context=get_context("spawn"))

    def tick(self, *, now: datetime | None = None, code_version: str | None = None) -> list[dict[str, Any]]:
        """Schedule source roots and drain one dependency-aware worker DAG."""
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("tick time must include a timezone")
        engine = sync_engine(self.database)
        with tick_lock(engine) as acquired:
            if not acquired:
                return [{"status": "skipped", "reason": "another tick is running"}]
            sessions = sync_sessions(self.database)
            with sessions() as session:
                repository = RunRepository(session)
                repository.recover_stale(older_than=current - timedelta(hours=1))
                source_configs = repository.list_latest_configs("source")
                profile_configs = repository.list_latest_configs("profile", enabled_only=True)
                producer_by_dataset = self._producer_map(source_configs)
                self._import_legacy_pointers(repository, source_configs, current)
                self._schedule_sources(repository, source_configs, current)
                session.commit()
                return self._run_dag(
                    session,
                    repository,
                    repository.queued_runs(),
                    profile_configs,
                    producer_by_dataset,
                    code_version=code_version,
                )

    @staticmethod
    def _model(config: ConfigRevision) -> SourceConfig | ReportProfile:
        """Reconstruct a validated model from a stored revision."""
        return validate_config(config.kind, config.config_id, dict(config.payload)).model

    def _schedule_sources(
        self,
        repository: RunRepository,
        configs: list[ConfigRevision],
        current: datetime,
    ) -> None:
        """Queue the latest due slot for every enabled source; profiles are dataset-triggered."""
        for config in configs:
            model = self._model(config)
            if not isinstance(model, SourceConfig) or not model.enabled:
                continue
            slot = latest_due_slot(model.schedule.cron, model.schedule.timezone, current)
            active = repository.list_runs(kind="source", target_id=config.config_id, limit=20)
            if any(row.slot == slot and row.status in {"queued", "running"} for row in active):
                continue
            repository.queue_run(
                kind="source",
                target_id=config.config_id,
                slot=slot,
                trigger="schedule",
                force=False,
                config=config,
            )

    def _producer_map(self, configs: list[ConfigRevision]) -> dict[str, str]:
        """Build and validate the current one-source-per-dataset ownership map."""
        producers: dict[str, str] = {}
        for config in configs:
            model = self._model(config)
            if not isinstance(model, SourceConfig):  # pragma: no cover - validated by config kind
                continue
            for binding in model.datasets.values():
                previous = producers.setdefault(binding.dataset_id, model.source_id)
                if previous != model.source_id:
                    raise ValueError(f"dataset {binding.dataset_id!r} has multiple producers: {previous!r}, {model.source_id!r}")
        return producers

    def _import_legacy_pointers(
        self,
        repository: RunRepository,
        source_configs: list[ConfigRevision],
        current: datetime,
    ) -> None:
        """Import a v0.0.1 root pointer document into an empty database registry."""
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
            if source_id is None:
                raise ValueError(f"legacy pointer dataset has no configured producer: {dataset_id!r}")
            if not isinstance(ref, str):
                raise ValueError(f"legacy pointer must be a manifest reference: {dataset_id!r}")
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
                source_id=source_id,
                source_run_id="legacy-pointer-import",
                updates=updates,
                updated_at=current,
            )
        logger.info("imported legacy dataset pointers count={}", len(payload))

    def _run_dag(
        self,
        session,
        repository: RunRepository,
        queued: list[Run],
        profile_configs: list[ConfigRevision],
        producer_by_dataset: dict[str, str],
        *,
        code_version: str | None,
    ) -> list[dict[str, Any]]:
        """Drain queued roots and dynamically release dependent profile work."""
        source_rows: dict[str, deque[Run]] = defaultdict(deque)
        source_models: dict[str, SourceConfig] = {}
        profile_roots: list[Run] = []
        terminal: list[tuple[datetime, str, dict[str, Any]]] = []

        def row_identity(row: Run, model: ReportProfile | None = None) -> RunLogIdentity:
            return RunLogIdentity(
                run_id=row.run_id,
                kind=row.kind,
                target_id=row.target_id,
                slot=_aware_utc(row.slot),
                report_id=model.report_id if model is not None else None,
            )

        def fail_preflight(row: Run, exc: Exception, model: ReportProfile | None = None) -> None:
            """Persist unexpected parent-side failures with a diagnostic log."""
            logger.exception("run preflight failed run_id={}", row.run_id)
            identity = row_identity(row, model)
            log_ref = write_failure_log(self.data_store, identity, exc)
            outcome = {"status": "failed", "reason": str(exc), "log_ref": log_ref}
            repository.finish(row, status="failed", outcome=outcome, reason=str(exc))
            terminal.append((row.requested_at, row.run_id, self._outcome(row)))

        for row in sorted(queued, key=lambda item: (_aware_utc(item.requested_at), item.run_id)):
            config = repository.get_config(row.kind, row.target_id, row.config_revision)
            if config is None:
                fail_preflight(
                    row,
                    RuntimeError("pinned configuration revision is unavailable"),
                )
                continue
            try:
                model = self._model(config)
            except Exception as exc:
                fail_preflight(row, exc)
                continue
            if row.kind == "source":
                if not isinstance(model, SourceConfig):
                    fail_preflight(row, ValueError("pinned source configuration is invalid"))
                    continue
                source_rows[row.target_id].append(row)
                source_models[row.run_id] = model
            else:
                profile_roots.append(row)
        for source_id, rows in source_rows.items():
            source_rows[source_id] = deque(
                sorted(
                    rows,
                    key=lambda item: (
                        _aware_utc(item.slot),
                        _aware_utc(item.requested_at),
                        item.run_id,
                    ),
                )
            )
        session.commit()

        participating_sources = set(source_rows)
        profile_models: dict[str, ReportProfile] = {}
        remaining_dependencies: dict[str, set[str]] = {}
        profiles_by_source: dict[str, set[str]] = defaultdict(set)
        profile_revision_by_id: dict[str, ConfigRevision] = {}
        for config in profile_configs:
            model = self._model(config)
            if not isinstance(model, ReportProfile):
                continue
            dependencies = {producer_by_dataset[dataset_id] for dataset_id in model.datasets.values() if producer_by_dataset.get(dataset_id) in participating_sources}
            if not dependencies:
                continue
            profile_models[model.profile_id] = model
            profile_revision_by_id[model.profile_id] = config
            remaining_dependencies[model.profile_id] = set(dependencies)
            for source_id in dependencies:
                profiles_by_source[source_id].add(model.profile_id)

        futures: dict[Future[Any], _SourceTask | _ReportTask] = {}
        with self._executor() as executor:

            def finish_terminal(row: Run) -> None:
                terminal.append((row.requested_at, row.run_id, self._outcome(row)))

            def fail_submission(row: Run, identity: RunLogIdentity, exc: Exception) -> None:
                """Persist startup/broken-pool failures as ordinary run outcomes."""
                logger.error("worker submission failed run_id={} reason={}", row.run_id, exc)
                log_ref = write_failure_log(self.data_store, identity, exc)
                outcome = {"status": "failed", "reason": str(exc), "log_ref": log_ref}
                repository.finish(row, status="failed", outcome=outcome, reason=str(exc))
                session.commit()
                finish_terminal(row)

            def submit_report(row: Run, snapshot=None) -> None:
                """Prepare and submit one pinned report worker task."""
                if row.status != "queued":
                    return
                config = repository.get_config(row.kind, row.target_id, row.config_revision)
                if config is None:
                    fail_preflight(
                        row,
                        RuntimeError("pinned configuration revision is unavailable"),
                    )
                    session.commit()
                    return
                try:
                    model = self._model(config)
                except Exception as exc:
                    fail_preflight(row, exc)
                    session.commit()
                    return
                if not isinstance(model, ReportProfile):
                    fail_preflight(row, ValueError("pinned profile configuration is invalid"))
                    session.commit()
                    return
                identity = row_identity(row, model)
                try:
                    pinned = snapshot or resolve_snapshot(
                        open_blob_store(self.data_store),
                        model.datasets,
                        pointer_registry=repository.pointer_registry,
                    )
                    resolved_code = resolve_code_version(code_version)
                except ValueError as exc:
                    status = "waiting" if str(exc).startswith("no pointer exists for dataset") else "failed"
                    if status == "waiting":
                        repository.finish(row, status=status, reason=str(exc))
                    else:
                        log_ref = write_failure_log(self.data_store, identity, exc)
                        outcome = {
                            "status": status,
                            "reason": str(exc),
                            "log_ref": log_ref,
                        }
                        repository.finish(row, status=status, outcome=outcome, reason=str(exc))
                    session.commit()
                    finish_terminal(row)
                    return
                except Exception as exc:
                    log_ref = write_failure_log(self.data_store, identity, exc)
                    outcome = {
                        "status": "failed",
                        "reason": str(exc),
                        "log_ref": log_ref,
                    }
                    repository.finish(row, status="failed", outcome=outcome, reason=str(exc))
                    session.commit()
                    finish_terminal(row)
                    return
                run_slot = _aware_utc(row.slot)
                if row.trigger != "manual" and pinned.watermark < run_slot:
                    repository.finish(
                        row,
                        status="waiting",
                        reason="dataset watermark is behind report slot",
                    )
                    session.commit()
                    finish_terminal(row)
                    return
                context_hash = build_context_hash(model.execution_config())
                expected_artifact = sha256_json(
                    {
                        "report_id": model.report_id,
                        "snapshot_id": pinned.snapshot_id,
                        "code_version": resolved_code,
                        "context_hash": context_hash,
                    }
                )
                row.snapshot_id = pinned.snapshot_id
                row.context_hash = context_hash
                row.code_version = resolved_code
                if not row.force and repository.successful(
                    row.kind,
                    row.target_id,
                    row.slot,
                    artifact_id=expected_artifact,
                ):
                    repository.finish(row, status="skipped", reason="identity already succeeded")
                    session.commit()
                    finish_terminal(row)
                    return
                repository.mark_running(row)
                session.commit()
                identity = row_identity(row, model)
                snapshot_payload = pinned.model_dump(mode="json") if hasattr(pinned, "model_dump") else pinned
                try:
                    future = executor.submit(
                        _report_worker,
                        model.model_dump(mode="json"),
                        run_slot.isoformat(),
                        resolved_code,
                        self.report_root,
                        snapshot_payload,
                        self.data_store,
                        {
                            "run_id": identity.run_id,
                            "kind": identity.kind,
                            "target_id": identity.target_id,
                            "slot": identity.slot.isoformat(),
                            "report_id": identity.report_id,
                        },
                    )
                except Exception as exc:
                    fail_submission(row, identity, exc)
                    return
                futures[future] = _ReportTask(row.run_id, identity, snapshot_payload)

            def submit_generated_profile(profile_id: str) -> None:
                """Queue a dataset-triggered profile once its snapshot is complete."""
                model = profile_models[profile_id]
                try:
                    snapshot = resolve_snapshot(
                        open_blob_store(self.data_store),
                        model.datasets,
                        pointer_registry=repository.pointer_registry,
                    )
                except ValueError as exc:
                    if str(exc).startswith("no pointer exists for dataset"):
                        logger.info(
                            "profile fanout blocked profile={} reason={}",
                            profile_id,
                            exc,
                        )
                        return
                    logger.error("profile fanout failed profile={} reason={}", profile_id, exc)
                    return
                except Exception as exc:
                    logger.error("profile fanout failed profile={} reason={}", profile_id, exc)
                    return
                row = repository.queue_run(
                    kind="profile",
                    target_id=profile_id,
                    slot=snapshot.watermark,
                    trigger="dataset",
                    force=False,
                    config=profile_revision_by_id[profile_id],
                )
                session.commit()
                submit_report(row, snapshot=snapshot)

            def settle_source(source_id: str) -> None:
                """Release profiles whose participating source dependencies settled."""
                for profile_id in sorted(profiles_by_source.get(source_id, ())):
                    remaining = remaining_dependencies[profile_id]
                    remaining.discard(source_id)
                    if not remaining:
                        submit_generated_profile(profile_id)

            def start_next_source(source_id: str) -> None:
                """Submit the next ordered run for one source pipeline."""
                rows = source_rows[source_id]
                while rows:
                    row = rows.popleft()
                    model = source_models[row.run_id]
                    if not row.force and repository.successful(
                        row.kind,
                        row.target_id,
                        row.slot,
                        row.config_hash,
                    ):
                        repository.finish(row, status="skipped", reason="identity already succeeded")
                        session.commit()
                        finish_terminal(row)
                        continue
                    try:
                        pointer_ids = [binding.dataset_id for binding in model.datasets.values()]
                        pointers = repository.pointer_registry.get(pointer_ids)
                        store = open_blob_store(self.data_store)
                        watermarks, _tickers = load_previous_append_state(
                            store,
                            model,
                            pointers,
                        )
                    except Exception as exc:
                        identity = RunLogIdentity(
                            run_id=row.run_id,
                            kind="source",
                            target_id=model.source_id,
                            slot=_aware_utc(row.slot),
                        )
                        log_ref = write_failure_log(self.data_store, identity, exc)
                        outcome = {
                            "status": "failed",
                            "reason": str(exc),
                            "log_ref": log_ref,
                        }
                        repository.finish(row, status="failed", outcome=outcome, reason=str(exc))
                        session.commit()
                        finish_terminal(row)
                        continue
                    repository.mark_running(row)
                    session.commit()
                    run_slot = _aware_utc(row.slot)
                    identity = RunLogIdentity(
                        run_id=row.run_id,
                        kind="source",
                        target_id=model.source_id,
                        slot=run_slot,
                    )
                    try:
                        future = executor.submit(
                            _source_worker,
                            model.model_dump(mode="json"),
                            run_slot.isoformat(),
                            self.data_store,
                            {key: value.isoformat() for key, value in watermarks.items()},
                            {key: _pointer_payload(value) for key, value in pointers.items()},
                            {
                                "run_id": identity.run_id,
                                "kind": identity.kind,
                                "target_id": identity.target_id,
                                "slot": identity.slot.isoformat(),
                            },
                        )
                    except Exception as exc:
                        fail_submission(row, identity, exc)
                        continue
                    futures[future] = _SourceTask(row.run_id, model, pointers, identity)
                    return
                settle_source(source_id)

            for row in profile_roots:
                submit_report(row)
            for source_id in sorted(source_rows):
                start_next_source(source_id)

            while futures:
                done, _pending = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    task = futures.pop(future)
                    task_row = repository.get_run(task.run_id)
                    if task_row is None:  # pragma: no cover - run rows are not deleted
                        continue
                    row = task_row
                    if isinstance(task, _ReportTask):
                        try:
                            result = future.result()
                            result["snapshot"] = task.snapshot
                            repository.finish(
                                row,
                                status=result["status"],
                                outcome=result,
                                reason=result.get("reason"),
                            )
                        except Exception as exc:
                            logger.exception("report worker failed run_id={}", row.run_id)
                            log_ref = write_failure_log(
                                self.data_store,
                                task.identity,
                                exc,
                                incomplete=True,
                            )
                            result = {
                                "status": "failed",
                                "reason": str(exc),
                                "log_ref": log_ref,
                                "snapshot": task.snapshot,
                            }
                            repository.finish(row, status="failed", outcome=result, reason=str(exc))
                        session.commit()
                        finish_terminal(row)
                        continue

                    source_id = task.config.source_id
                    try:
                        result = future.result()
                        if result["status"] != "success":
                            repository.finish(
                                row,
                                status=result["status"],
                                outcome=result,
                                reason=result.get("reason"),
                            )
                        else:
                            updates = tuple(
                                DatasetPointerUpdate(
                                    dataset_id=item["dataset_id"],
                                    manifest_ref=item["manifest_ref"],
                                    watermark=datetime.fromisoformat(item["watermark"]),
                                    published_at=datetime.fromisoformat(item["published_at"]),
                                )
                                for item in result.get("pointer_updates", ())
                            )
                            with session.begin_nested():
                                repository.pointer_registry.publish(
                                    source_id=source_id,
                                    source_run_id=row.run_id,
                                    updates=updates,
                                )
                                repository.finish(row, status="success", outcome=result)
                    except Exception as exc:
                        logger.exception("source worker failed run_id={}", row.run_id)
                        log_ref = write_failure_log(self.data_store, task.identity, exc, incomplete=True)
                        result = {
                            "source_id": source_id,
                            "slot": slot_key(_aware_utc(row.slot)),
                            "status": "failed",
                            "datasets": None,
                            "reason": str(exc),
                            "log_ref": log_ref,
                        }
                        repository.finish(row, status="failed", outcome=result, reason=str(exc))
                    session.commit()
                    finish_terminal(row)
                    start_next_source(source_id)

        ordered = sorted(terminal, key=lambda item: (_aware_utc(item[0]), item[1]))
        return [outcome for _requested_at, _run_id, outcome in ordered]

    @staticmethod
    def _outcome(row: Run) -> dict[str, Any]:
        """Return the compact CLI outcome for a run."""
        return {
            "run_id": row.run_id,
            "kind": row.kind,
            "target_id": row.target_id,
            "slot": _aware_utc(row.slot).isoformat(),
            "status": row.status,
            "reason": row.reason,
            "artifact_id": row.artifact_id,
            "log_ref": (row.result or {}).get("log_ref"),
        }
