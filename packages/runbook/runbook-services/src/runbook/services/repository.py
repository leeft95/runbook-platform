from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from runbook.core import SourceConfig
from sqlalchemy import Select, and_, case, desc, exists, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, aliased

from .config import validate_config
from .models import ConfigRevision, Run

if TYPE_CHECKING:
    from .pointers import DatabasePointerRegistry


def now_utc() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _config_payload(row: ConfigRevision) -> dict[str, Any]:
    """Copy a stored configuration payload."""
    return dict(row.payload)


def _run_view(row: Run) -> dict[str, Any]:
    """Convert a run row to a plain mapping."""
    return {name: getattr(row, name) for name in Run.__table__.columns.keys()}


def _validate_source_ownership(
    config_id: str,
    model: SourceConfig,
    configs: list[ConfigRevision],
    pointer_owners: dict[str, str],
) -> None:
    """Reject ambiguous producers and unsupported ownership transfers."""
    dataset_ids = {binding.dataset_id for binding in model.datasets.values()}
    for row in configs:
        if row.config_id == config_id:
            continue
        other = validate_config("source", row.config_id, dict(row.payload)).model
        if not isinstance(other, SourceConfig):  # pragma: no cover - fixed by kind
            continue
        overlap = dataset_ids.intersection(binding.dataset_id for binding in other.datasets.values())
        if overlap:
            dataset_id = min(overlap)
            raise ConflictError(f"dataset {dataset_id!r} already has configured producer {other.source_id!r}")
    for dataset_id, owner in pointer_owners.items():
        if dataset_id in dataset_ids and owner != config_id:
            raise ConflictError(f"dataset {dataset_id!r} is owned by source {owner!r}")
        if owner == config_id and dataset_id not in dataset_ids:
            raise ConflictError(f"published dataset {dataset_id!r} cannot be removed from source {config_id!r}")


class ConflictError(ValueError):
    pass


class ConfigNotFound(LookupError):
    pass


class RunRepository:
    """Small synchronous repository used by the external tick runner."""

    def __init__(self, session: Session):
        self.session = session

    @property
    def pointer_registry(self) -> DatabasePointerRegistry:
        """Return a pointer registry using this session's transaction connection.

        The registry deliberately receives the caller-owned connection, so pointer
        reads and publications participate in the repository transaction and can be
        committed atomically with service run state.
        """
        from .pointers import DatabasePointerRegistry

        return DatabasePointerRegistry(self.session.connection())

    def latest_config(self, kind: str, config_id: str) -> ConfigRevision | None:
        """Return the newest revision for a configuration."""
        return self.session.scalar(
            select(ConfigRevision)
            .where(ConfigRevision.kind == kind, ConfigRevision.config_id == config_id)
            .order_by(desc(ConfigRevision.revision))
            .limit(1)
        )

    def get_config(self, kind: str, config_id: str, revision: int) -> ConfigRevision | None:
        """Return an exact pinned configuration revision."""
        return self.session.scalar(
            select(ConfigRevision).where(
                ConfigRevision.kind == kind,
                ConfigRevision.config_id == config_id,
                ConfigRevision.revision == revision,
            )
        )

    def list_latest_configs(self, kind: str, *, enabled_only: bool = False) -> list[ConfigRevision]:
        """Return one newest revision per configuration ID."""
        rows = self.session.scalars(
            select(ConfigRevision)
            .where(ConfigRevision.kind == kind)
            .order_by(ConfigRevision.config_id, desc(ConfigRevision.revision))
        ).all()
        latest: dict[str, ConfigRevision] = {}
        for row in rows:
            latest.setdefault(row.config_id, row)
        if enabled_only:
            return [row for row in latest.values() if bool(row.payload.get("enabled", True))]
        return list(latest.values())

    def list_config_revisions(self, kind: str, config_id: str) -> list[ConfigRevision]:
        """Return all revisions for one configuration, newest first."""
        return list(
            self.session.scalars(
                select(ConfigRevision)
                .where(ConfigRevision.kind == kind, ConfigRevision.config_id == config_id)
                .order_by(desc(ConfigRevision.revision))
            ).all()
        )

    def save_config(
        self,
        kind: str,
        config_id: str,
        payload: dict[str, Any],
        expected_revision: int | None = None,
    ) -> ConfigRevision:
        """Validate and append a configuration revision."""
        validated = validate_config(kind, config_id, payload)
        if isinstance(validated.model, SourceConfig) and self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('runbook-source-config-ownership'))"))
        current = self.latest_config(kind, config_id)
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            raise ConflictError("configuration revision is stale")
        if isinstance(validated.model, SourceConfig):
            pointer_owners = {
                dataset_id: pointer.source_id for dataset_id, pointer in self.pointer_registry.all().items()
            }
            _validate_source_ownership(
                config_id,
                validated.model,
                self.list_latest_configs("source"),
                pointer_owners,
            )
        if current is not None and current.config_hash == validated.config_hash:
            return current
        revision = (current.revision if current else 0) + 1
        row = ConfigRevision(
            kind=kind,
            config_id=config_id,
            revision=revision,
            payload=validated.payload,
            config_hash=validated.config_hash,
            created_at=now_utc(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_run(self, run_id: str) -> Run | None:
        """Return one run by ID."""
        return self.session.get(Run, run_id, populate_existing=True)

    def list_runs(
        self,
        *,
        kind: str | None = None,
        target_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Run]:
        """List recent runs with bounded filters."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        query: Select[tuple[Run]] = select(Run)
        if kind:
            query = query.where(Run.kind == kind)
        if target_id:
            query = query.where(Run.target_id == target_id)
        if status:
            query = query.where(Run.status == status)
        return list(self.session.scalars(query.order_by(desc(Run.requested_at)).limit(limit)).all())

    def successful(
        self,
        kind: str,
        target_id: str,
        slot: datetime,
        config_hash: str | None = None,
        artifact_id: str | None = None,
    ) -> bool:
        """Return whether an equivalent run already succeeded."""
        conditions = [
            Run.kind == kind,
            Run.target_id == target_id,
            Run.slot == slot,
            Run.status == "success",
        ]
        if config_hash is not None:
            conditions.append(Run.config_hash == config_hash)
        if artifact_id is not None:
            conditions.append(Run.artifact_id == artifact_id)
        count = self.session.scalar(select(func.count()).select_from(Run).where(and_(*conditions)))
        return count is not None and count > 0

    def queue_run(
        self,
        *,
        kind: str,
        target_id: str,
        slot: datetime,
        trigger: str,
        force: bool,
        config: ConfigRevision,
        identity_key: str | None = None,
        snapshot_id: str | None = None,
        snapshot_payload: dict[str, Any] | None = None,
        context_hash: str | None = None,
        code_version: str | None = None,
        mode: str = "normal",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Run:
        """Queue a manual or scheduled run, reusing an active duplicate."""
        if mode not in {"normal", "historical"}:
            raise ValueError("mode must be 'normal' or 'historical'")
        if mode == "historical":
            if kind != "source":
                raise ValueError("historical mode is only supported for source runs")
            if start_date is None or end_date is None:
                raise ValueError("historical runs require start_date and end_date")
            if end_date < start_date:
                raise ValueError("end_date must be on or after start_date")
            assert start_date is not None and end_date is not None
        elif start_date is not None or end_date is not None:
            raise ValueError("normal runs cannot include historical dates")
        if slot.tzinfo is None:
            raise ValueError("slot must include a timezone")
        stamp = now_utc()
        if mode == "historical":
            assert start_date is not None and end_date is not None
            default_identity = (
                f"historical:{target_id}:start={start_date.isoformat()}:end={end_date.isoformat()}:"
                f"requested={stamp.isoformat()}"
            )
        else:
            default_identity = f"{kind}:{target_id}:{slot.astimezone(timezone.utc).isoformat()}:{config.config_hash}"
        identity_key = identity_key or default_identity
        if not force and trigger == "schedule":
            existing = self.session.scalar(select(Run).where(Run.identity_key == identity_key).limit(1))
            if existing is not None:
                return existing
        elif not force:
            existing = self.session.scalar(
                select(Run)
                .where(
                    Run.kind == kind,
                    Run.target_id == target_id,
                    Run.slot == slot,
                    Run.config_hash == config.config_hash,
                    Run.status.in_(["queued", "running"]),
                )
                .order_by(desc(Run.requested_at))
                .limit(1)
            )
            if existing is not None:
                return existing
        row = Run(
            run_id=uuid4().hex,
            kind=kind,
            target_id=target_id,
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            slot=slot.astimezone(timezone.utc),
            trigger=trigger,
            force=force,
            config_revision=config.revision,
            config_hash=config.config_hash,
            status="queued",
            identity_key=identity_key,
            snapshot_id=snapshot_id,
            snapshot_payload=snapshot_payload,
            context_hash=context_hash,
            code_version=code_version,
            requested_at=stamp,
            updated_at=stamp,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def queue_historical_run(
        self,
        source_id: str,
        *,
        start_date: date,
        end_date: date,
        expected_revision: int | None = None,
    ) -> Run:
        """Pin the latest source revision and queue one inclusive date-range run."""
        config = self.latest_config("source", source_id)
        if config is None:
            raise ConfigNotFound(f"unknown source: {source_id}")
        if expected_revision is not None and config.revision != expected_revision:
            raise ConflictError("source configuration revision changed after review")
        return self.queue_run(
            kind="source",
            target_id=source_id,
            slot=now_utc().replace(second=0, microsecond=0),
            trigger="manual",
            force=True,
            config=config,
            mode="historical",
            start_date=start_date,
            end_date=end_date,
        )

    def queued_runs(self, limit: int = 100) -> list[Run]:
        """Return queued runs in FIFO order."""
        return list(
            self.session.scalars(
                select(Run).where(Run.status == "queued").order_by(Run.requested_at, Run.run_id).limit(limit)
            ).all()
        )

    def eligible_queued_runs(self, limit: int = 100) -> list[Run]:
        """Return FIFO work not blocked by an earlier queued/running source."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        earlier = aliased(Run)
        earlier_source_work = exists(
            select(1).where(
                earlier.run_id != Run.run_id,
                earlier.kind == "source",
                earlier.target_id == Run.target_id,
                earlier.status.in_(["queued", "running"]),
                or_(
                    earlier.slot < Run.slot,
                    and_(earlier.slot == Run.slot, earlier.requested_at < Run.requested_at),
                    and_(
                        earlier.slot == Run.slot,
                        earlier.requested_at == Run.requested_at,
                        earlier.run_id < Run.run_id,
                    ),
                ),
            )
        )
        running_source_work = exists(
            select(1).where(
                earlier.run_id != Run.run_id,
                earlier.kind == "source",
                earlier.target_id == Run.target_id,
                earlier.status == "running",
            )
        )
        return list(
            self.session.scalars(
                select(Run)
                .where(
                    Run.status == "queued",
                    or_(Run.kind != "source", and_(~running_source_work, ~earlier_source_work)),
                )
                .order_by(Run.requested_at, Run.run_id)
                .limit(limit)
            ).all()
        )

    def get_identity(self, identity_key: str) -> Run | None:
        """Return the run with an exact effective identity, in any lifecycle state."""
        return self.session.scalar(select(Run).where(Run.identity_key == identity_key).limit(1))

    def latest_automatic_profile(self, profile_id: str, config_revision: int, config_hash: str) -> Run | None:
        """Return the newest dataset-triggered profile snapshot for one revision."""
        return self.session.scalar(
            select(Run)
            .where(
                Run.kind == "profile",
                Run.target_id == profile_id,
                Run.trigger == "dataset",
                Run.config_revision == config_revision,
                Run.config_hash == config_hash,
                Run.snapshot_payload.is_not(None),
            )
            .order_by(desc(Run.requested_at), desc(Run.run_id))
            .limit(1)
        )

    def unreleased_successful_sources(self) -> list[Run]:
        """Return successful source roots whose durable release marker is unset."""
        return list(
            self.session.scalars(
                select(Run)
                .where(
                    Run.kind == "source",
                    Run.status == "success",
                    Run.mode == "normal",
                    Run.dependencies_released_at.is_(None),
                )
                .order_by(Run.finished_at, Run.run_id)
            ).all()
        )

    def running_runs(self) -> list[Run]:
        """Return every running row for startup reconciliation."""
        return list(self.session.scalars(select(Run).where(Run.status == "running")).all())

    def reconcile_orphan(self, run_id: str, *, reason: str) -> bool:
        """Conditionally terminalize one orphan using its current cancel intent."""
        stamp = now_utc()
        result = self.session.execute(
            update(Run)
            .where(Run.run_id == run_id, Run.status == "running")
            .values(
                status=case((Run.cancel_requested_at.is_not(None), "cancelled"), else_="failed"),
                reason=case((Run.cancel_requested_at.is_not(None), "cancel requested"), else_=reason),
                finished_at=stamp,
                updated_at=stamp,
            )
        )
        self.session.flush()
        return int(getattr(result, "rowcount", 0)) == 1

    def claim(self, run_id: str, worker_id: str) -> bool:
        """Atomically claim a queued run for one worker process."""
        stamp = now_utc()
        result = self.session.execute(
            update(Run)
            .where(
                Run.run_id == run_id, Run.status == "queued", Run.worker_id.is_(None), Run.cancel_requested_at.is_(None)
            )
            .values(status="running", worker_id=worker_id, started_at=stamp, updated_at=stamp)
        )
        self.session.flush()
        return int(getattr(result, "rowcount", 0)) == 1

    def request_cancel(self, run_id: str) -> bool:
        """Persist cancellation intent for a queued or running run."""
        stamp = now_utc()
        queued = self.session.execute(
            update(Run)
            .where(Run.run_id == run_id, Run.status == "queued", Run.cancel_requested_at.is_(None))
            .values(
                cancel_requested_at=stamp,
                status="cancelled",
                finished_at=stamp,
                reason="cancel requested before worker start",
                updated_at=stamp,
            )
        )
        running = self.session.execute(
            update(Run)
            .where(Run.run_id == run_id, Run.status == "running", Run.cancel_requested_at.is_(None))
            .values(cancel_requested_at=stamp, updated_at=stamp)
        )
        self.session.flush()
        return int(getattr(queued, "rowcount", 0)) + int(getattr(running, "rowcount", 0)) == 1

    def cancel_owned(self, run_id: str, worker_id: str, *, reason: str = "cancel requested") -> bool:
        """Terminalize only an owned running row with durable cancellation intent."""
        stamp = now_utc()
        result = self.session.execute(
            update(Run)
            .where(
                Run.run_id == run_id,
                Run.status == "running",
                Run.worker_id == worker_id,
                Run.cancel_requested_at.is_not(None),
            )
            .values(status="cancelled", finished_at=stamp, updated_at=stamp, reason=reason)
        )
        self.session.flush()
        return int(getattr(result, "rowcount", 0)) == 1

    def cancel(self, run_id: str) -> bool:
        """Cancel a queued run immediately or mark a running run for cancellation."""
        row = self.get_run(run_id)
        if row is None or row.status not in {"queued", "running"}:
            return False
        stamp = now_utc()
        row.cancel_requested_at = stamp
        row.updated_at = stamp
        if row.status == "queued":
            row.status = "cancelled"
            row.finished_at = stamp
            row.reason = "cancel requested before worker start"
        self.session.flush()
        return True

    def finish_owned(
        self,
        run_id: str,
        worker_id: str,
        *,
        status: str,
        outcome: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> bool:
        """Write a terminal outcome only while ownership and cancellation are valid."""
        if status not in {"success", "failed", "waiting", "not_ready", "skipped"}:
            raise ValueError(f"invalid worker terminal status: {status!r}")
        stamp = now_utc()
        values: dict[str, Any] = {
            "status": status,
            "result": outcome,
            "reason": reason,
            "finished_at": stamp,
            "updated_at": stamp,
        }
        for key in ("snapshot_id", "context_hash", "code_version", "artifact_id"):
            if outcome and key in outcome:
                values[key] = outcome[key]
        result = self.session.execute(
            update(Run)
            .where(
                Run.run_id == run_id,
                Run.status == "running",
                Run.worker_id == worker_id,
                Run.cancel_requested_at.is_(None),
            )
            .values(**values)
        )
        self.session.flush()
        return int(getattr(result, "rowcount", 0)) == 1

    def mark_running(self, row: Run) -> None:
        """Mark a run as started."""
        stamp = now_utc()
        row.status = "running"
        row.started_at = stamp
        row.updated_at = stamp
        self.session.flush()

    def finish(
        self,
        row: Run,
        *,
        status: str,
        outcome: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        """Persist a terminal run outcome."""
        if row.status in {"success", "failed", "waiting", "not_ready", "skipped", "cancelled"}:
            return
        stamp = now_utc()
        row.status = status
        row.result = outcome
        row.reason = reason
        row.finished_at = stamp
        row.updated_at = stamp
        if outcome:
            for key in ("snapshot_id", "context_hash", "code_version", "artifact_id"):
                if key in outcome:
                    setattr(row, key, outcome[key])
        self.session.flush()

    def recover_stale(self, *, older_than: datetime) -> int:
        """Mark rows left running before the cutoff as crashed failures."""
        rows = self.session.scalars(select(Run).where(Run.status == "running", Run.updated_at < older_than)).all()
        for row in rows:
            self.finish(
                row,
                status="failed",
                reason="service runner stopped while run was active",
            )
        return len(rows)


class AsyncRunRepository:
    """Async API repository; each method uses the caller-owned transaction."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def latest_config(self, kind: str, config_id: str) -> ConfigRevision | None:
        """Return the newest revision asynchronously."""
        return (
            await self.session.scalars(
                select(ConfigRevision)
                .where(ConfigRevision.kind == kind, ConfigRevision.config_id == config_id)
                .order_by(desc(ConfigRevision.revision))
                .limit(1)
            )
        ).first()

    async def get_config(self, kind: str, config_id: str, revision: int) -> ConfigRevision | None:
        """Return an exact pinned revision asynchronously."""
        return (
            await self.session.scalars(
                select(ConfigRevision).where(
                    ConfigRevision.kind == kind,
                    ConfigRevision.config_id == config_id,
                    ConfigRevision.revision == revision,
                )
            )
        ).first()

    async def list_latest_configs(self, kind: str) -> list[ConfigRevision]:
        """Return newest revisions asynchronously."""
        rows = (
            await self.session.scalars(
                select(ConfigRevision)
                .where(ConfigRevision.kind == kind)
                .order_by(ConfigRevision.config_id, desc(ConfigRevision.revision))
            )
        ).all()
        latest: dict[str, ConfigRevision] = {}
        for row in rows:
            latest.setdefault(row.config_id, row)
        return list(latest.values())

    async def list_config_revisions(self, kind: str, config_id: str) -> list[ConfigRevision]:
        """Return all revisions for one configuration, newest first."""
        return list(
            (
                await self.session.scalars(
                    select(ConfigRevision)
                    .where(
                        ConfigRevision.kind == kind,
                        ConfigRevision.config_id == config_id,
                    )
                    .order_by(desc(ConfigRevision.revision))
                )
            ).all()
        )

    async def save_config(
        self,
        kind: str,
        config_id: str,
        payload: dict[str, Any],
        expected_revision: int | None = None,
    ) -> ConfigRevision:
        """Validate and append a revision asynchronously."""
        validated = validate_config(kind, config_id, payload)
        if isinstance(validated.model, SourceConfig) and self.session.get_bind().dialect.name == "postgresql":
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('runbook-source-config-ownership'))")
            )
        current = await self.latest_config(kind, config_id)
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            raise ConflictError("configuration revision is stale")
        if isinstance(validated.model, SourceConfig):
            from .pointers import dataset_pointers

            pointer_rows = (await self.session.execute(select(dataset_pointers))).mappings()
            pointer_owners = {row["dataset_id"]: row["source_id"] for row in pointer_rows}
            _validate_source_ownership(
                config_id,
                validated.model,
                await self.list_latest_configs("source"),
                pointer_owners,
            )
        if current is not None and current.config_hash == validated.config_hash:
            return current
        row = ConfigRevision(
            kind=kind,
            config_id=config_id,
            revision=(current.revision if current else 0) + 1,
            payload=validated.payload,
            config_hash=validated.config_hash,
            created_at=now_utc(),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_run(self, run_id: str) -> Run | None:
        """Return one run asynchronously."""
        return await self.session.get(Run, run_id, populate_existing=True)

    async def request_cancel(self, run_id: str) -> Run | None:
        """Persist cancellation intent without touching a worker process."""
        stamp = now_utc()
        await self.session.execute(
            update(Run)
            .where(Run.run_id == run_id, Run.status == "queued", Run.cancel_requested_at.is_(None))
            .values(
                cancel_requested_at=stamp,
                status="cancelled",
                finished_at=stamp,
                reason="cancel requested before worker start",
                updated_at=stamp,
            )
        )
        await self.session.execute(
            update(Run)
            .where(Run.run_id == run_id, Run.status == "running", Run.cancel_requested_at.is_(None))
            .values(cancel_requested_at=stamp, updated_at=stamp)
        )
        await self.session.flush()
        return await self.session.get(Run, run_id, populate_existing=True)

    async def queue_historical_run(
        self,
        source_id: str,
        *,
        start_date: date,
        end_date: date,
        expected_revision: int | None = None,
    ) -> Run:
        """Pin the latest source revision and queue one inclusive date-range run."""
        config = await self.latest_config("source", source_id)
        if config is None:
            raise ConfigNotFound(f"unknown source: {source_id}")
        if expected_revision is not None and config.revision != expected_revision:
            raise ConflictError("source configuration revision changed after review")
        return await self.queue_run(
            kind="source",
            target_id=source_id,
            slot=now_utc().replace(second=0, microsecond=0),
            trigger="manual",
            force=True,
            config=config,
            mode="historical",
            start_date=start_date,
            end_date=end_date,
        )

    async def cancel_owned(self, run_id: str, worker_id: str, *, reason: str = "cancel requested") -> bool:
        """Terminalize only an owned running row with durable cancellation intent."""
        stamp = now_utc()
        result = await self.session.execute(
            update(Run)
            .where(
                Run.run_id == run_id,
                Run.status == "running",
                Run.worker_id == worker_id,
                Run.cancel_requested_at.is_not(None),
            )
            .values(status="cancelled", finished_at=stamp, updated_at=stamp, reason=reason)
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0)) == 1

    async def list_runs(self, **kwargs: Any) -> list[Run]:
        """List runs asynchronously."""
        kind = kwargs.get("kind")
        target_id = kwargs.get("target_id")
        status = kwargs.get("status")
        limit = kwargs.get("limit", 100)
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        query: Select[tuple[Run]] = select(Run)
        if kind:
            query = query.where(Run.kind == kind)
        if target_id:
            query = query.where(Run.target_id == target_id)
        if status:
            query = query.where(Run.status == status)
        return list((await self.session.scalars(query.order_by(desc(Run.requested_at)).limit(limit))).all())

    async def status_counts(self, statuses: set[str], *, since: datetime | None = None) -> dict[str, int]:
        """Count statuses in the database without a dashboard row limit."""
        query = select(Run.status, func.count()).where(Run.status.in_(statuses))
        if since is not None:
            query = query.where(Run.requested_at >= since)
        rows = (await self.session.execute(query.group_by(Run.status))).all()
        return {status: int(count) for status, count in rows}

    async def list_active_runs(self, limit: int = 100) -> list[Run]:
        """List active rows separately from unbounded active status counts."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        return list(
            (
                await self.session.scalars(
                    select(Run)
                    .where(Run.status.in_(["queued", "running"]))
                    .order_by(desc(Run.requested_at))
                    .limit(limit)
                )
            ).all()
        )

    async def list_attention_runs(self, since: datetime, limit: int = 20) -> list[Run]:
        """List recent failed/waiting/not-ready rows within the given window."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        return list(
            (
                await self.session.scalars(
                    select(Run)
                    .where(
                        Run.requested_at >= since,
                        Run.status.in_(["failed", "waiting", "not_ready"]),
                    )
                    .order_by(desc(Run.requested_at))
                    .limit(limit)
                )
            ).all()
        )

    async def list_pointers(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return current dataset pointers for the operations dashboard."""
        from .pointers import dataset_pointers

        query = select(dataset_pointers).order_by(dataset_pointers.c.dataset_id)
        if limit is not None:
            if limit < 1 or limit > 500:
                raise ValueError("limit must be between 1 and 500")
            query = query.limit(limit)
        rows = (await self.session.execute(query)).mappings()
        return [dict(row) for row in rows]

    async def queue_run(self, **kwargs: Any) -> Run:
        """Queue one run asynchronously."""
        config = kwargs.pop("config")
        slot = kwargs["slot"]
        if slot.tzinfo is None:
            raise ValueError("slot must include a timezone")
        kind = kwargs["kind"]
        target_id = kwargs["target_id"]
        force = kwargs["force"]
        mode = kwargs.get("mode", "normal")
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        if mode not in {"normal", "historical"}:
            raise ValueError("mode must be 'normal' or 'historical'")
        if mode == "historical":
            if kind != "source":
                raise ValueError("historical mode is only supported for source runs")
            if start_date is None or end_date is None:
                raise ValueError("historical runs require start_date and end_date")
            if end_date < start_date:
                raise ValueError("end_date must be on or after start_date")
            assert start_date is not None and end_date is not None
        elif start_date is not None or end_date is not None:
            raise ValueError("normal runs cannot include historical dates")
        if not force:
            existing = (
                await self.session.scalars(
                    select(Run)
                    .where(
                        Run.kind == kind,
                        Run.target_id == target_id,
                        Run.slot == slot,
                        Run.config_hash == config.config_hash,
                        Run.status.in_(["queued", "running"]),
                    )
                    .order_by(desc(Run.requested_at))
                    .limit(1)
                )
            ).first()
            if existing is not None:
                return existing
        stamp = now_utc()
        if mode == "historical":
            assert start_date is not None and end_date is not None
            default_identity = (
                f"historical:{target_id}:start={start_date.isoformat()}:end={end_date.isoformat()}:"
                f"requested={stamp.isoformat()}"
            )
        else:
            default_identity = f"{kind}:{target_id}:{slot.astimezone(timezone.utc).isoformat()}:{config.config_hash}"
        row = Run(
            run_id=uuid4().hex,
            kind=kind,
            target_id=target_id,
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            slot=slot.astimezone(timezone.utc),
            trigger=kwargs["trigger"],
            force=force,
            config_revision=config.revision,
            config_hash=config.config_hash,
            status="queued",
            identity_key=default_identity,
            requested_at=stamp,
            updated_at=stamp,
        )
        self.session.add(row)
        await self.session.flush()
        return row
