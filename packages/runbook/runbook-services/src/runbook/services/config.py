from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, TypeAlias

from runbook.core.utils.hashing import sha256_json
from runbook.data.config import SourceConfig
from runbook.sdk.profiles import ReportProfile

ConfigModel: TypeAlias = SourceConfig | ReportProfile


@dataclass(frozen=True)
class ValidatedConfig:
    kind: str
    config_id: str
    model: ConfigModel
    payload: dict[str, Any]
    config_hash: str


def database_url(value: str | None = None) -> str:
    """Return the configured PostgreSQL URL."""
    if value is not None:
        return value
    return os.environ.get("RUNBOOK_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/runbook")


def store_uri(value: str | None = None) -> str:
    """Return the configured data blob store URI."""
    if value is not None:
        return value
    return os.environ.get("RUNBOOK_DATA_STORE_URI", "file:.runbook")


def reports_root(value: str | None = None) -> str:
    """Return the configured reports root."""
    if value is not None:
        return value
    return os.environ.get("RUNBOOK_REPORTS_ROOT", "reports")


def _without_id(kind: str, config_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Remove and validate the identifier embedded in a config payload."""
    result = dict(payload)
    expected = "source_id" if kind == "source" else "profile_id"
    if expected in result and result[expected] != config_id:
        raise ValueError(f"{expected} must match the path identifier")
    result.pop(expected, None)
    return result


def validate_config(kind: str, config_id: str, payload: dict[str, Any]) -> ValidatedConfig:
    """Validate and canonicalize one source or report configuration."""
    if kind not in {"source", "profile"}:
        raise ValueError(f"unsupported config kind: {kind!r}")
    normalized = _without_id(kind, config_id, payload)
    model: ConfigModel
    if kind == "source":
        model = SourceConfig(source_id=config_id, **normalized)
    else:
        model = ReportProfile(profile_id=config_id, **normalized)
    canonical = model.model_dump(mode="json")
    canonical.pop("source_id", None)
    canonical.pop("profile_id", None)
    return ValidatedConfig(
        kind=kind,
        config_id=config_id,
        model=model,
        payload=canonical,
        config_hash=sha256_json(canonical),
    )


def payload_with_id(kind: str, config_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Add the kind-specific identifier to a stored payload."""
    key = "source_id" if kind == "source" else "profile_id"
    return {key: config_id, **payload}
