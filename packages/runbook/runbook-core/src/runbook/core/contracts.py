"""Shared immutable configuration contracts used by Runbook packages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ScheduleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cron: str
    timezone: str = "UTC"


class DatasetBinding(BaseModel):
    """Storage and curation settings for one source output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    schema_version: str = "v1"
    partition_keys: tuple[str, ...] = ()
    parser_id: str
    update_mode: Literal["append", "full"] = "append"

    @field_validator("dataset_id", "schema_version")
    @classmethod
    def validate_segment(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            raise ValueError(f"invalid dataset path segment: {value!r}")
        return value

    @field_validator("partition_keys")
    @classmethod
    def validate_partition_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("partition_keys must not contain duplicates")
        for key in value:
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", key):
                raise ValueError(f"invalid partition key: {key!r}")
        return value

    @field_validator("parser_id")
    @classmethod
    def validate_parser_id(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError(f"invalid parser id: {value!r}")
        return value


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    adapter: str
    enabled: bool = True
    schedule: ScheduleSpec
    datasets: dict[str, DatasetBinding] = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_update_mode_location(self) -> "SourceConfig":
        if "update_mode" in self.params:
            raise ValueError("update_mode belongs in each dataset binding, not source params")
        dataset_ids = [binding.dataset_id for binding in self.datasets.values()]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError(f"source {self.source_id!r} maps multiple aliases to one dataset")
        return self

    @field_validator("source_id", "adapter")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError(f"invalid identifier: {value!r}")
        return value

    @field_validator("datasets", mode="before")
    @classmethod
    def normalize_datasets(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("datasets must be an object")
        for alias, binding in value.items():
            if not _ID.fullmatch(alias):
                raise ValueError(f"invalid dataset alias: {alias!r}")
            if not isinstance(binding, dict):
                raise ValueError(f"dataset binding must be an object with parser_id: {alias!r}")
        return value


def _recipient_values(value: Any, field_name: str) -> tuple[str, ...]:
    """Normalize recipient values without claiming to validate mailbox syntax."""
    if value is None:
        if field_name == "cc":
            return ()
        raise ValueError("to must contain at least one recipient")
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of recipient strings")
    recipients = tuple(item.strip() if isinstance(item, str) else item for item in value)
    if any(not isinstance(item, str) or not item for item in recipients):
        raise ValueError(f"{field_name} must not contain empty recipients")
    folded = [item.casefold() for item in recipients]
    if len(folded) != len(set(folded)):
        raise ValueError(f"{field_name} must not contain duplicate recipients")
    return recipients


class EmailDeliverySpec(BaseModel):
    """Profile-level email policy; transport configuration stays in the deployment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    to: tuple[str, ...] = Field(min_length=1)
    cc: tuple[str, ...] = ()
    subject: str | None = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("provider must be a safe lowercase identifier")
        return value

    @field_validator("to", "cc", mode="before")
    @classmethod
    def normalize_recipients(cls, value: Any, info: Any) -> tuple[str, ...]:
        return _recipient_values(value, info.field_name)

    @model_validator(mode="after")
    def reject_cross_field_duplicates(self) -> "EmailDeliverySpec":
        recipients = [item.casefold() for item in (*self.to, *self.cc)]
        if len(recipients) != len(set(recipients)):
            raise ValueError("to and cc must not contain duplicate recipients")
        return self


class ReportDeliverySpec(BaseModel):
    """Optional delivery policy attached to a report profile revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    email: EmailDeliverySpec | None = None


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
    delivery: ReportDeliverySpec | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("delivery", mode="before")
    @classmethod
    def normalize_delivery(cls, value: Any) -> Any:
        return None if value == {} else value

    @field_validator("datasets")
    @classmethod
    def validate_datasets(cls, value: dict[str, str]) -> dict[str, str]:
        for alias, dataset_id in value.items():
            if (
                not isinstance(alias, str)
                or not _ID.fullmatch(alias)
                or not isinstance(dataset_id, str)
                or not _ID.fullmatch(dataset_id)
            ):
                raise ValueError(f"invalid dataset binding: {alias!r} -> {dataset_id!r}")
        return value

    @model_validator(mode="after")
    def normalize(self) -> "ReportProfile":
        if not _ID.fullmatch(self.profile_id) or not _ID.fullmatch(self.report_id):
            raise ValueError("profile_id and report_id must be safe lowercase identifiers")
        if not self.title:
            object.__setattr__(self, "title", self.report_id)
        if self.delivery is not None and self.delivery.email is None:
            object.__setattr__(self, "delivery", None)
        for namespace, extension in self.extensions.items():
            if not isinstance(namespace, str) or not namespace or not isinstance(extension, dict):
                raise ValueError("extensions must map names to objects")
        modes = self.extensions.get("modes", {})
        if not isinstance(modes, dict):
            raise ValueError("extensions.modes must be an object")
        for name, mode in modes.items():
            if not isinstance(mode, dict) or not isinstance(mode.get("enabled", False), bool):
                raise ValueError(f"extensions.modes.{name} must contain boolean enabled")
            if mode.get("enabled") and name != "dash":
                raise ValueError(f"renderer extension {name!r} is not implemented; HTML is the only renderer")
        return self

    def execution_config(self) -> dict[str, Any]:
        """Return the immutable report execution configuration."""
        return {
            "report_id": self.report_id,
            "title": self.title,
            "datasets": self.datasets,
            "params": self.params,
            "layout": self.layout,
            "extensions": self.extensions,
        }


__all__ = [
    "DatasetBinding",
    "EmailDeliverySpec",
    "ReportDeliverySpec",
    "ReportProfile",
    "ScheduleSpec",
    "SourceConfig",
]


def load_source_configs(path: str | Path) -> dict[str, SourceConfig]:
    """Load source configuration without importing execution adapters."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source_configs.json must contain an object")
    result: dict[str, SourceConfig] = {}
    for source_id, raw in payload.items():
        if not isinstance(source_id, str) or not isinstance(raw, dict) or "source_id" in raw:
            raise ValueError("source configs must be an object keyed by source id")
        result[source_id] = SourceConfig(source_id=source_id, **raw)
    return result


def load_profiles(path: str | Path) -> dict[str, ReportProfile]:
    """Load report profiles without importing report execution."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("report_profiles.json must contain an object")
    result: dict[str, ReportProfile] = {}
    for profile_id, raw in payload.items():
        if not isinstance(raw, dict) or "profile_id" in raw:
            raise ValueError(f"profile {profile_id!r} must be an object without profile_id")
        result[profile_id] = ReportProfile(profile_id=profile_id, **raw)
    return result


__all__ += ["load_profiles", "load_source_configs"]
