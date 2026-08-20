"""Report profile compatibility helpers."""

from __future__ import annotations

import json
from pathlib import Path

from runbook.core import ReportProfile


def load_profiles(path: str | Path) -> dict[str, ReportProfile]:
    """Load report profiles from their public JSON map format."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("report_profiles.json must contain an object")
    profiles: dict[str, ReportProfile] = {}
    for profile_id, raw in payload.items():
        if not isinstance(raw, dict):
            raise ValueError(f"profile {profile_id!r} must be an object")
        if "profile_id" in raw:
            raise ValueError("profile_id belongs only in the report profile map key")
        profile = ReportProfile(profile_id=profile_id, **raw)
        if profile.profile_id != profile_id:
            raise ValueError("profile_id must be the JSON map key")
        profiles[profile_id] = profile
    return profiles


def resolve_report_path(report_id: str, reports_root: str | Path = "reports") -> Path:
    """Resolve a report module below the configured reports root."""
    import re

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", report_id):
        raise ValueError(f"invalid report id: {report_id!r}")
    path = (Path(reports_root) / f"{report_id}.py").resolve()
    root = Path(reports_root).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("report path escaped reports root") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


__all__ = ["ReportProfile", "load_profiles", "resolve_report_path"]
