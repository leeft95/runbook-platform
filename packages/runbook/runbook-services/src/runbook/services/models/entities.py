from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ConfigRevision(Base):
    __tablename__ = "config_revisions"
    __table_args__ = (UniqueConstraint("kind", "config_id", "revision", name="uq_config_revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    config_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slot: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    identity_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    context_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
