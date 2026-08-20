from __future__ import annotations

import importlib.metadata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from runbook.core import ReportProfile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import database_url, reports_root, store_uri, validate_config
from .db import async_engine
from .repository import AsyncRunRepository, ConflictError
from .routers.ui import mount_ui
from .schemas import ConfigView, ConfigWrite, RunRequest, RunView, VersionView


def _version(distribution_name: str) -> str:
    """Read an installed distribution version with a source-tree fallback."""
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.2"


def version_payload() -> dict[str, str]:
    """Return the stable root version response."""
    return {"ui_version": _version("runbook-services")}


def _config_view(row: Any) -> ConfigView:
    """Convert a configuration row to its API representation."""
    key = "source_id" if row.kind == "source" else "profile_id"
    return ConfigView(
        kind=row.kind,
        config_id=row.config_id,
        revision=row.revision,
        config_hash=row.config_hash,
        config={key: row.config_id, **dict(row.payload)},
        created_at=row.created_at,
    )


def _run_view(row: Any) -> RunView:
    """Convert a run row to its API representation."""
    return RunView.model_validate({name: getattr(row, name) for name in row.__table__.columns.keys()})


def create_app(
    *,
    database: str | None = None,
    data_store: str | None = None,
    report_root: str | None = None,
) -> FastAPI:
    """Create the FastAPI API and mount the Dash UI."""
    url = database_url(database)
    engine = async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Dispose the database engine when the application stops."""
        yield
        await engine.dispose()

    app = FastAPI(
        title="Runbook services",
        version=version_payload()["ui_version"],
        lifespan=lifespan,
    )
    api = APIRouter(prefix="/api/v1")

    async def get_session() -> AsyncIterator[AsyncSession]:
        """Provide a request-scoped database session."""
        async with sessions() as session:
            yield session

    @app.get("/", response_model=VersionView)
    async def root() -> dict[str, str]:
        return version_payload()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
        """Report database readiness."""
        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - driver-specific errors
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        return {"status": "ready"}

    async def list_configs(kind: str, session: AsyncSession) -> list[ConfigView]:
        """List the newest revisions for one configuration kind."""
        rows = await AsyncRunRepository(session).list_latest_configs(kind)
        return [_config_view(row) for row in rows]

    async def get_config(kind: str, config_id: str, session: AsyncSession) -> ConfigView:
        """Fetch one configuration or return HTTP 404."""
        row = await AsyncRunRepository(session).latest_config(kind, config_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown {kind}: {config_id}")
        return _config_view(row)

    async def put_config(
        kind: str,
        config_id: str,
        body: ConfigWrite,
        session: AsyncSession,
    ) -> ConfigView:
        """Validate and persist one configuration revision."""
        try:
            if kind == "profile":
                profile = validate_config(kind, config_id, body.config).model
                if not isinstance(profile, ReportProfile):
                    raise ValueError("profile configuration has an invalid model")
            async with session.begin():
                row = await AsyncRunRepository(session).save_config(
                    kind,
                    config_id,
                    body.config,
                    body.expected_revision,
                )
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _config_view(row)

    @api.get("/sources", response_model=list[ConfigView])
    async def sources(session: AsyncSession = Depends(get_session)) -> list[ConfigView]:
        return await list_configs("source", session)

    @api.get("/sources/{source_id}", response_model=ConfigView)
    async def source(source_id: str, session: AsyncSession = Depends(get_session)) -> ConfigView:
        return await get_config("source", source_id, session)

    @api.put("/sources/{source_id}", response_model=ConfigView)
    async def put_source(source_id: str, body: ConfigWrite, session: AsyncSession = Depends(get_session)) -> ConfigView:
        return await put_config("source", source_id, body, session)

    @api.get("/profiles", response_model=list[ConfigView])
    async def profiles(
        session: AsyncSession = Depends(get_session),
    ) -> list[ConfigView]:
        return await list_configs("profile", session)

    @api.get("/profiles/{profile_id}", response_model=ConfigView)
    async def profile(profile_id: str, session: AsyncSession = Depends(get_session)) -> ConfigView:
        return await get_config("profile", profile_id, session)

    @api.put("/profiles/{profile_id}", response_model=ConfigView)
    async def put_profile(
        profile_id: str, body: ConfigWrite, session: AsyncSession = Depends(get_session)
    ) -> ConfigView:
        return await put_config("profile", profile_id, body, session)

    async def queue(kind: str, config_id: str, body: RunRequest | None, session: AsyncSession) -> RunView:
        """Queue a pinned manual run."""
        repository = AsyncRunRepository(session)
        request = body or RunRequest()
        slot = request.slot or datetime.now(timezone.utc).replace(second=0, microsecond=0)
        if slot.tzinfo is None:
            raise HTTPException(status_code=422, detail="slot must include a timezone")
        async with session.begin():
            config = await repository.latest_config(kind, config_id)
            if config is None:
                raise HTTPException(status_code=404, detail=f"unknown {kind}: {config_id}")
            row = await repository.queue_run(
                kind=kind,
                target_id=config_id,
                slot=slot,
                trigger="manual",
                force=request.force,
                config=config,
            )
        return _run_view(row)

    @api.post(
        "/sources/{source_id}/runs",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_source(
        source_id: str, body: RunRequest | None = None, session: AsyncSession = Depends(get_session)
    ) -> RunView:
        return await queue("source", source_id, body, session)

    @api.post(
        "/profiles/{profile_id}/runs",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_profile(
        profile_id: str, body: RunRequest | None = None, session: AsyncSession = Depends(get_session)
    ) -> RunView:
        return await queue("profile", profile_id, body, session)

    @api.get("/runs", response_model=list[RunView])
    async def runs(
        kind: str | None = Query(default=None),
        target_id: str | None = Query(default=None),
        run_status: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ) -> list[RunView]:
        """List recent runs using bounded query filters."""
        rows = await AsyncRunRepository(session).list_runs(
            kind=kind,
            target_id=target_id,
            status=run_status,
            limit=limit,
        )
        return [_run_view(row) for row in rows]

    @api.get("/runs/{run_id}", response_model=RunView)
    async def run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunView:
        """Fetch one run by ID."""
        row = await AsyncRunRepository(session).get_run(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown run")
        return _run_view(row)

    app.include_router(api)
    mount_ui(
        app,
        sessions=sessions,
        data_store=store_uri(data_store),
        reports_root=reports_root(report_root),
    )
    return app


app = create_app()
