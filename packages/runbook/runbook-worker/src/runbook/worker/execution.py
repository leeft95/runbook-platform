"""Durable run execution owned exclusively by the worker process."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from runbook.core import ReportProfile, Snapshot, SourceConfig, open_blob_store
from runbook.data.ingest import run_stage1_acquire
from runbook.data.ingest.runner import load_previous_append_state
from runbook.data.ingest.runners import run_stage2_curate
from runbook.sdk import execute_report, resolve_code_version
from runbook.services.config import validate_config
from runbook.services.db import sync_sessions
from runbook.services.logging import RunLogIdentity, capture_worker_logs
from runbook.services.pointers import DatasetPointerUpdate
from runbook.services.repository import RunRepository


def _utc(value: datetime) -> datetime:
    """Normalize a database timestamp to UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def wait_for_claim(run_id: str, *, timeout: float = 10.0) -> str | None:
    """Wait for the service to persist this process's ``local:<pid>`` claim."""
    expected = f"local:{os.getpid()}"
    database = os.environ.get("RUNBOOK_DATABASE_URL")
    if not database:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with sync_sessions(database)() as session:
            row = RunRepository(session).get_run(run_id)
            if (
                row is not None
                and row.status == "running"
                and row.worker_id == expected
                and row.cancel_requested_at is None
            ):
                return expected
            if row is not None and row.status in {"cancelled", "failed", "success", "skipped", "waiting", "not_ready"}:
                return None
        time.sleep(0.05)
    return None


def _identity(row, model: SourceConfig | ReportProfile) -> RunLogIdentity:
    """Build stable log identity from a durable run row."""
    return RunLogIdentity(
        run_id=row.run_id,
        kind=row.kind,
        target_id=row.target_id,
        slot=_utc(row.slot),
        report_id=model.report_id if isinstance(model, ReportProfile) else None,
    )


def _source(row, config: SourceConfig, identity: RunLogIdentity) -> dict[str, Any]:
    """Execute source acquisition and curation, returning only JSON data."""
    store = open_blob_store(os.environ.get("RUNBOOK_DATA_STORE_URI"))
    with capture_worker_logs(os.environ.get("RUNBOOK_DATA_STORE_URI"), identity) as log:
        try:
            with sync_sessions(os.environ.get("RUNBOOK_DATABASE_URL"))() as session:
                repository = RunRepository(session)
                pointers = repository.pointer_registry.get(binding.dataset_id for binding in config.datasets.values())
            # Previous append state is execution state.  Keep its validation
            # inside the worker log boundary so stale pointers produce a
            # useful failed run instead of an unexplained process exit.
            previous_state = load_previous_append_state(store, config, pointers)
            slot = _utc(row.slot)
            acquired = run_stage1_acquire(source_config=config, slot=slot, store=store, previous_state=previous_state)
            if acquired.status.value != "ready" or acquired.acquired is None:
                return {
                    "source_id": config.source_id,
                    "status": acquired.status.value,
                    "reason": acquired.message,
                    "log_ref": log.log_ref,
                }
            curated = run_stage2_curate(
                store=store,
                source_config=config,
                acquired=acquired.acquired,
                published_at=slot,
                previous_pointers=pointers,
            )
            return {
                "source_id": config.source_id,
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
                "expected_pointer_source_runs": {
                    item.dataset_id: (pointers[item.dataset_id].source_run_id if item.dataset_id in pointers else None)
                    for item in curated.pointer_updates
                },
                "log_ref": log.log_ref,
            }
        except Exception as exc:
            logger.exception("source worker failed run_id={}", identity.run_id)
            return {"source_id": config.source_id, "status": "failed", "reason": str(exc), "log_ref": log.log_ref}


def _report(row, profile: ReportProfile, identity: RunLogIdentity) -> dict[str, Any]:
    """Execute the exact snapshot persisted by the service before dispatch."""
    with capture_worker_logs(os.environ.get("RUNBOOK_DATA_STORE_URI"), identity) as log:
        try:
            payload = row.snapshot_payload
            if not isinstance(payload, dict):
                raise ValueError("report run has no pinned snapshot payload")
            snapshot = Snapshot.model_validate(payload)
            if row.snapshot_id is not None and snapshot.snapshot_id != row.snapshot_id:
                raise ValueError("report snapshot payload does not match the pinned snapshot ID")
            code_version = resolve_code_version(row.code_version)
            result = execute_report(
                store=open_blob_store(os.environ.get("RUNBOOK_DATA_STORE_URI")),
                profile=profile,
                snapshot=snapshot,
                code_version=code_version,
                reports_root=os.environ.get("RUNBOOK_REPORTS_ROOT", "reports"),
            )
            outcome = result.model_dump(mode="json")
            outcome.update({"status": "success", "log_ref": log.log_ref, "snapshot": snapshot.model_dump(mode="json")})
            return outcome
        except ValueError as exc:
            return {
                "status": "waiting" if str(exc).startswith("no pointer exists") else "failed",
                "reason": str(exc),
                "log_ref": log.log_ref,
            }
        except Exception as exc:
            logger.exception("report worker failed run_id={}", identity.run_id)
            return {"status": "failed", "reason": str(exc), "log_ref": log.log_ref}


def execute_run(run_id: str) -> int:
    """Claim, execute, and conditionally persist one durable run."""
    worker_id = wait_for_claim(run_id)
    if worker_id is None:
        return 2
    database = os.environ.get("RUNBOOK_DATABASE_URL")
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        row = repository.get_run(run_id)
        if row is None or row.worker_id != worker_id or row.status != "running" or row.cancel_requested_at is not None:
            return 2
        config = repository.get_config(row.kind, row.target_id, row.config_revision)
        if config is None:
            outcome = {"status": "failed", "reason": "pinned configuration revision is unavailable"}
            repository.finish_owned(run_id, worker_id, status="failed", outcome=outcome, reason=outcome["reason"])
            session.commit()
            return 0
        try:
            validated = validate_config(row.kind, row.target_id, dict(config.payload))
            if validated.config_hash != row.config_hash:
                raise ValueError("pinned configuration hash does not match the run")
            model = validated.model
        except Exception as exc:
            identity = RunLogIdentity(
                run_id=row.run_id,
                kind=row.kind,
                target_id=row.target_id,
                slot=_utc(row.slot),
            )
            with capture_worker_logs(os.environ.get("RUNBOOK_DATA_STORE_URI"), identity) as log:
                logger.exception("worker configuration validation failed run_id={}", run_id)
                outcome = {"status": "failed", "reason": str(exc), "log_ref": log.log_ref}
            repository.finish_owned(run_id, worker_id, status="failed", outcome=outcome, reason=outcome["reason"])
            session.commit()
            return 0
        identity = _identity(row, model)
    outcome = _source(row, model, identity) if isinstance(model, SourceConfig) else _report(row, model, identity)
    status = str(outcome.get("status", "failed"))
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        finished = repository.finish_owned(
            run_id,
            worker_id,
            status=status,
            outcome=outcome,
            reason=outcome.get("reason"),
        )
        if not finished:
            session.rollback()
            return 0
        if status == "success" and isinstance(model, SourceConfig):
            raw_updates = outcome.get("pointer_updates", ())
            updates: list[DatasetPointerUpdate] = []
            if isinstance(raw_updates, list):
                for item in raw_updates:
                    if not isinstance(item, dict):
                        continue
                    updates.append(
                        DatasetPointerUpdate(
                            dataset_id=str(item["dataset_id"]),
                            manifest_ref=str(item["manifest_ref"]),
                            watermark=datetime.fromisoformat(str(item["watermark"])),
                            published_at=datetime.fromisoformat(str(item["published_at"])),
                        )
                    )
            expected = outcome.get("expected_pointer_source_runs")
            repository.pointer_registry.publish(
                source_id=model.source_id,
                source_run_id=run_id,
                updates=updates,
                expected_source_run_ids=expected if isinstance(expected, dict) else None,
            )
        session.commit()
    return 0
