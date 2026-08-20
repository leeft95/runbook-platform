"""Source configuration compatibility imports and file loading."""

from __future__ import annotations

import json
from pathlib import Path

from runbook.core import DatasetBinding, ScheduleSpec, SourceConfig


def load_source_configs(path: str | Path) -> dict[str, SourceConfig]:
    """Load and validate source configs, preserving the public data API."""
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
                raise ValueError(f"dataset {dataset_id!r} has multiple producers: {previous!r}")
        configs[source_id] = config
    return configs


__all__ = ["DatasetBinding", "ScheduleSpec", "SourceConfig", "load_source_configs"]
