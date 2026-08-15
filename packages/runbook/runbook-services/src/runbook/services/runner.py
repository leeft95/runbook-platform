from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from runbook.core.keying import build_context_hash
from runbook.core.utils.hashing import sha256_json
from runbook.data import open_blob_store, resolve_snapshot
from runbook.platform.report_run import run_report
from runbook.platform.schedule import latest_due_slot
from runbook.platform.source_run import run_source
from runbook.sdk import resolve_code_version

from .config import reports_root, store_uri, validate_config
from .db import sync_engine, sync_sessions, tick_lock
from .models import ConfigRevision, Run
from .repository import RunRepository


class ServiceRunner:
    """Sequentially execute queued and scheduled runs from PostgreSQL."""

    def __init__(
        self,
        *,
        database: str | None = None,
        data_store: str | None = None,
        report_root: str | None = None,
    ):
        self.database = database
        self.data_store = store_uri(data_store)
        self.report_root = reports_root(report_root)

    def tick(self, *, now: datetime | None = None, code_version: str | None = None) -> list[dict[str, Any]]:
        """Run queued work and latest due schedules under one advisory lock."""
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
                outcomes: list[dict[str, Any]] = []
                repository.recover_stale(older_than=current - timedelta(hours=1))
                session.commit()
                queued = sorted(
                    repository.queued_runs(),
                    key=lambda row: (row.trigger != "manual", row.requested_at, row.run_id),
                )
                for row in queued:
                    outcomes.append(self._execute(session, repository, row, code_version=code_version))
                    session.commit()
                outcomes.extend(self._schedule(session, repository, current, code_version))
                session.commit()
                return outcomes

    def _schedule(
        self,
        session,
        repository: RunRepository,
        current: datetime,
        code_version: str | None,
    ) -> list[dict[str, Any]]:
        """Queue and execute enabled source and profile schedules."""
        outcomes: list[dict[str, Any]] = []
        for kind in ("source", "profile"):
            for config in repository.list_latest_configs(kind, enabled_only=True):
                model = self._model(config)
                slot = latest_due_slot(model.schedule.cron, model.schedule.timezone, current)
                if any(
                    row.kind == kind
                    and row.target_id == config.config_id
                    and row.slot == slot
                    and row.status in {"queued", "running"}
                    for row in repository.list_runs(kind=kind, target_id=config.config_id, limit=20)
                ):
                    continue
                row = repository.queue_run(
                    kind=kind,
                    target_id=config.config_id,
                    slot=slot,
                    trigger="schedule",
                    force=False,
                    config=config,
                )
                if row.status == "queued":
                    outcomes.append(self._execute(session, repository, row, code_version=code_version))
                    session.commit()
        return outcomes

    @staticmethod
    def _model(config: ConfigRevision):
        """Reconstruct a validated model from a stored revision."""
        return validate_config(config.kind, config.config_id, dict(config.payload)).model

    def _execute(self, session, repository: RunRepository, row: Run, *, code_version: str | None) -> dict[str, Any]:
        """Execute one pinned run and persist its terminal result."""
        config = repository.get_config(row.kind, row.target_id, row.config_revision)
        if config is None:
            repository.finish(row, status="failed", reason="pinned configuration revision is unavailable")
            return self._outcome(row)
        model = self._model(config)
        blob_store = open_blob_store(self.data_store)
        if (
            row.kind == "source"
            and not row.force
            and repository.successful(row.kind, row.target_id, row.slot, row.config_hash)
        ):
            repository.finish(row, status="skipped", reason="identity already succeeded")
            return self._outcome(row)
        snapshot = None
        resolved_code: str | None = None
        if row.kind == "profile":
            try:
                snapshot = resolve_snapshot(blob_store, model.datasets)
                resolved_code = resolve_code_version(code_version)
            except ValueError as exc:
                status = "waiting" if str(exc).startswith("no pointer exists for dataset") else "failed"
                repository.finish(row, status=status, reason=str(exc))
                return self._outcome(row)
            except Exception as exc:
                repository.finish(row, status="failed", reason=str(exc))
                return self._outcome(row)
            if snapshot.watermark < row.slot:
                repository.finish(
                    row,
                    status="waiting",
                    reason="dataset watermark is behind report slot",
                )
                return self._outcome(row)
            context_hash = build_context_hash(model.execution_config())
            expected_artifact = sha256_json(
                {
                    "report_id": model.report_id,
                    "snapshot_id": snapshot.snapshot_id,
                    "code_version": resolved_code,
                    "context_hash": context_hash,
                }
            )
            row.snapshot_id = snapshot.snapshot_id
            row.context_hash = context_hash
            row.code_version = resolved_code
            if not row.force and repository.successful(
                row.kind, row.target_id, row.slot, artifact_id=expected_artifact
            ):
                repository.finish(row, status="skipped", reason="identity already succeeded")
                return self._outcome(row)
        repository.mark_running(row)
        session.commit()
        try:
            if row.kind == "source":
                result = run_source(
                    store=blob_store,
                    config=model,
                    slot=row.slot,
                ).as_dict()
            else:
                result = run_report(
                    store=blob_store,
                    profile=model,
                    slot=row.slot,
                    code_version=resolved_code,
                    reports_root=self.report_root,
                    snapshot=snapshot,
                ).as_dict()
            repository.finish(
                row,
                status=result["status"],
                outcome=result,
                reason=result.get("reason"),
            )
        except Exception as exc:
            logger.exception("service run failed run_id={}", row.run_id)
            repository.finish(row, status="failed", reason=str(exc))
        return self._outcome(row)

    @staticmethod
    def _outcome(row: Run) -> dict[str, Any]:
        """Return the compact CLI outcome for a run."""
        return {
            "run_id": row.run_id,
            "kind": row.kind,
            "target_id": row.target_id,
            "slot": row.slot.isoformat(),
            "status": row.status,
            "reason": row.reason,
            "artifact_id": row.artifact_id,
        }
