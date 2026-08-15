from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .config import validate_config
from .models import ConfigRevision, Run


def now_utc() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _config_payload(row: ConfigRevision) -> dict[str, Any]:
    """Copy a stored configuration payload."""
    return dict(row.payload)


def _run_view(row: Run) -> dict[str, Any]:
    """Convert a run row to a plain mapping."""
    return {name: getattr(row, name) for name in Run.__table__.columns.keys()}


class ConflictError(ValueError):
    pass


class ConfigNotFound(LookupError):
    pass


class RunRepository:
    """Small synchronous repository used by the external tick runner."""

    def __init__(self, session: Session):
        self.session = session

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
        current = self.latest_config(kind, config_id)
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            raise ConflictError("configuration revision is stale")
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
        return self.session.get(Run, run_id)

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
    ) -> Run:
        """Queue a manual or scheduled run, reusing an active duplicate."""
        if slot.tzinfo is None:
            raise ValueError("slot must include a timezone")
        identity_key = f"{kind}:{target_id}:{slot.astimezone(timezone.utc).isoformat()}:{config.config_hash}"
        if not force:
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
        stamp = now_utc()
        row = Run(
            run_id=uuid4().hex,
            kind=kind,
            target_id=target_id,
            slot=slot.astimezone(timezone.utc),
            trigger=trigger,
            force=force,
            config_revision=config.revision,
            config_hash=config.config_hash,
            status="queued",
            identity_key=identity_key,
            requested_at=stamp,
            updated_at=stamp,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def queued_runs(self, limit: int = 100) -> list[Run]:
        """Return queued runs in FIFO order."""
        return list(
            self.session.scalars(
                select(Run).where(Run.status == "queued").order_by(Run.requested_at, Run.run_id).limit(limit)
            ).all()
        )

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
                    .where(ConfigRevision.kind == kind, ConfigRevision.config_id == config_id)
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
        current = await self.latest_config(kind, config_id)
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            raise ConflictError("configuration revision is stale")
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
        return await self.session.get(Run, run_id)

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

    async def queue_run(self, **kwargs: Any) -> Run:
        """Queue one run asynchronously."""
        config = kwargs.pop("config")
        slot = kwargs["slot"]
        if slot.tzinfo is None:
            raise ValueError("slot must include a timezone")
        kind = kwargs["kind"]
        target_id = kwargs["target_id"]
        force = kwargs["force"]
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
        row = Run(
            run_id=uuid4().hex,
            kind=kind,
            target_id=target_id,
            slot=slot.astimezone(timezone.utc),
            trigger=kwargs["trigger"],
            force=force,
            config_revision=config.revision,
            config_hash=config.config_hash,
            status="queued",
            identity_key=f"{kind}:{target_id}:{slot.astimezone(timezone.utc).isoformat()}:{config.config_hash}",
            requested_at=stamp,
            updated_at=stamp,
        )
        self.session.add(row)
        await self.session.flush()
        return row
