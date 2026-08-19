from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ReportProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    report_id: str
    title: str | None = None
    enabled: bool = True
    datasets: dict[str, str] = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    layout: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("datasets")
    @classmethod
    def validate_datasets(cls, value: dict[str, str]) -> dict[str, str]:
        for alias, dataset_id in value.items():
            if not isinstance(alias, str) or not _ID.fullmatch(alias) or not isinstance(dataset_id, str) or not _ID.fullmatch(dataset_id):
                raise ValueError(f"invalid dataset binding: {alias!r} -> {dataset_id!r}")
        return value

    @model_validator(mode="after")
    def normalize(self) -> "ReportProfile":
        if not _ID.fullmatch(self.profile_id) or not _ID.fullmatch(self.report_id):
            raise ValueError("profile_id and report_id must be safe lowercase identifiers")
        if not self.title:
            object.__setattr__(self, "title", self.report_id)
        for namespace, extension in self.extensions.items():
            if not isinstance(namespace, str) or not namespace or not isinstance(extension, dict):
                raise ValueError("extensions must map names to objects")
        modes = self.extensions.get("modes", {})
        if not isinstance(modes, dict):
            raise ValueError("extensions.modes must be an object")
        for name, mode in modes.items():
            if not isinstance(mode, dict) or not isinstance(mode.get("enabled", False), bool):
                raise ValueError(f"extensions.modes.{name} must contain boolean enabled")
            if mode.get("enabled"):
                raise ValueError(f"renderer extension {name!r} is not implemented; HTML is the only renderer")
        return self

    def execution_config(self) -> dict[str, Any]:
        """Handle execution config."""
        return {
            "report_id": self.report_id,
            "title": self.title,
            "datasets": self.datasets,
            "params": self.params,
            "layout": self.layout,
            "extensions": self.extensions,
        }


def load_profiles(path: str | Path) -> dict[str, ReportProfile]:
    """Load profiles."""
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
    """Resolve report path."""
    if not _ID.fullmatch(report_id):
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
