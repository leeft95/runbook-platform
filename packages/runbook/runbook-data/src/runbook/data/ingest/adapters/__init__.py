"""Reusable acquisition capabilities owned by ``runbook-data``."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import TypeAlias

from runbook.data.config import SourceConfig
from runbook.data.ingest.adapters.base import (
    HttpAdapter,
    LocalFileAdapter,
    SourceAdapter,
)
from runbook.data.ingest.discovery import (
    EntryPointDiscoveryError,
    find_named_entry_points,
    load_named_entry_point,
)

AdapterType: TypeAlias = type[SourceAdapter]

_ADAPTERS: dict[str, AdapterType] = {
    "http": HttpAdapter,
    "local_file": LocalFileAdapter,
}


def get_adapter(source_config: SourceConfig) -> SourceAdapter:
    """Resolve and validate a built-in or installed adapter."""
    adapter_id = source_config.adapter
    if adapter_id in _ADAPTERS:
        collisions = find_named_entry_points("runbook.adapters", adapter_id)
        if collisions:
            raise ValueError(
                f"adapter {adapter_id!r} is reserved by a built-in; external entry point "
                f"group='runbook.adapters' name={adapter_id!r} cannot shadow it"
            )
        adapter_type = _ADAPTERS[adapter_id]
    else:
        try:
            adapter_type = load_named_entry_point("runbook.adapters", adapter_id)
        except EntryPointDiscoveryError as exc:
            raise ValueError(f"unsupported adapter capability: {adapter_id!r}; {exc}") from None
    if not callable(adapter_type):
        raise ValueError(
            f"incompatible adapter entry point group='runbook.adapters' name={adapter_id!r}: "
            "expected a zero-argument adapter factory"
        )
    try:
        adapter = adapter_type()
    except Exception as exc:
        raise ValueError(
            f"incompatible adapter entry point group='runbook.adapters' name={adapter_id!r}: "
            f"could not instantiate adapter: {exc}"
        ) from None
    missing = [method for method in ("validate", "check", "acquire") if not callable(getattr(adapter, method, None))]
    if missing:
        raise ValueError(
            f"incompatible adapter entry point group='runbook.adapters' name={adapter_id!r}: "
            f"missing methods {', '.join(missing)}"
        )
    parameters: Mapping[str, inspect.Parameter]
    try:
        parameters = inspect.signature(adapter.acquire).parameters
    except (TypeError, ValueError):  # pragma: no cover - uncommon extension callables
        parameters = {}
    if parameters and not (
        "previous_state" in parameters
        or "previous_watermarks" in parameters
        or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    ):
        raise ValueError(
            f"incompatible adapter entry point group='runbook.adapters' name={adapter_id!r}: "
            "acquire must accept previous_state or previous_watermarks"
        )
    try:
        adapter.validate(source_config)
    except Exception as exc:
        raise ValueError(f"adapter validation failed group='runbook.adapters' name={adapter_id!r}: {exc}") from None
    return adapter


__all__ = [
    "HttpAdapter",
    "LocalFileAdapter",
    "SourceAdapter",
    "get_adapter",
]
