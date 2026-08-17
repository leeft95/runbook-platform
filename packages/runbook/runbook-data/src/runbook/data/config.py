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
    def validate_update_mode_location(self) -> SourceConfig:
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


def load_source_configs(path: str | Path) -> dict[str, SourceConfig]:
    """Load source configs."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source_configs.json must contain an object")
    configs: dict[str, SourceConfig] = {}
    producers: dict[str, str] = {}
    for source_id, raw in payload.items():
        if not isinstance(source_id, str) or not isinstance(raw, dict):
            raise ValueError("source configs must be an object keyed by source id")
        if "source_id" in raw:
            raise ValueError("source_id belongs only in the source config map key")
        config = SourceConfig(source_id=source_id, **raw)
        if config.source_id != source_id:
            raise ValueError("source_id must be the JSON map key")
        from runbook.data.ingest.adapters import get_adapter
        from runbook.data.ingest.parsers import get_parser

        get_adapter(config)
        for binding in config.datasets.values():
            get_parser(binding.parser_id)
        for dataset_id in (binding.dataset_id for binding in config.datasets.values()):
            previous = producers.setdefault(dataset_id, source_id)
            if previous != source_id:
                raise ValueError(f"dataset {dataset_id!r} has multiple producers: {previous!r}, {source_id!r}")
        configs[source_id] = config
    return configs
