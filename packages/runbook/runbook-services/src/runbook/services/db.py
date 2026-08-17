from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from .config import database_url


def sync_engine(url: str | None = None) -> Engine:
    """Create a synchronous SQLAlchemy engine."""
    return create_engine(database_url(url), pool_pre_ping=True)


def async_engine(url: str | None = None) -> AsyncEngine:
    """Create an asynchronous SQLAlchemy engine."""
    return create_async_engine(database_url(url), pool_pre_ping=True)


def sync_sessions(url: str | None = None) -> sessionmaker[Session]:
    """Create a synchronous session factory."""
    return sessionmaker(sync_engine(url), expire_on_commit=False)


def async_sessions(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Create an asynchronous session factory."""
    return async_sessionmaker(async_engine(url), expire_on_commit=False)


def upgrade_with_metadata(url: str | None = None) -> None:
    """Create tables for source checkouts without Alembic installed.

    The CLI uses Alembic when available. This small fallback keeps a source
    checkout usable for local smoke tests and is safe because it only creates
    service-owned tables.
    """
    from runbook.data import create_pointer_schema

    from .models import Base

    engine = sync_engine(url)
    Base.metadata.create_all(engine)
    create_pointer_schema(engine)


@contextmanager
def tick_lock(engine: Engine) -> Iterator[bool]:
    """Hold the single-writer PostgreSQL advisory lock for one tick."""
    if engine.dialect.name != "postgresql":
        yield True
        return
    with engine.connect() as connection:
        acquired = bool(
            connection.execute(text("SELECT pg_try_advisory_lock(hashtext('runbook-services-tick'))")).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(hashtext('runbook-services-tick'))"))
