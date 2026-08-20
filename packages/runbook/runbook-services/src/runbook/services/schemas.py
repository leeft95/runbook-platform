from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfigWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]
    expected_revision: int | None = Field(default=None, ge=1)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: datetime | None = None
    force: bool = False


class ConfigView(BaseModel):
    kind: Literal["source", "profile"]
    config_id: str
    revision: int
    config_hash: str
    config: dict[str, Any]
    created_at: datetime


class RunView(BaseModel):
    run_id: str
    kind: Literal["source", "profile"]
    target_id: str
    slot: datetime
    trigger: str
    force: bool
    config_revision: int
    config_hash: str
    status: str
    worker_id: str | None = None
    cancel_requested_at: datetime | None = None
    cancelling: bool = False
    identity_key: str | None = None
    snapshot_id: str | None = None
    context_hash: str | None = None
    code_version: str | None = None
    artifact_id: str | None = None
    result: dict[str, Any] | None = None
    reason: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class VersionView(BaseModel):
    ui_version: str
