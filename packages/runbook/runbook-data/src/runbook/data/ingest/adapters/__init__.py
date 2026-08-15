"""Reusable acquisition capabilities owned by ``runbook-data``."""

from __future__ import annotations

from typing import TypeAlias

from runbook.data.config import SourceConfig
from runbook.data.ingest.adapters.base import (
    HttpAdapter,
    LocalFileAdapter,
    SourceAdapter,
)

AdapterType: TypeAlias = type[SourceAdapter]

_ADAPTERS: dict[str, AdapterType] = {
    "http": HttpAdapter,
    "local_file": LocalFileAdapter,
}


def get_adapter(source_config: SourceConfig) -> SourceAdapter:
    """Return adapter."""
    try:
        adapter_type = _ADAPTERS[source_config.adapter]
    except KeyError as exc:
        raise ValueError(f"unsupported adapter capability: {source_config.adapter!r}") from exc
    adapter = adapter_type()
    adapter.validate(source_config)
    return adapter


__all__ = [
    "HttpAdapter",
    "LocalFileAdapter",
    "SourceAdapter",
    "get_adapter",
]
