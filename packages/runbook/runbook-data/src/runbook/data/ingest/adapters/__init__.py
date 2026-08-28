"""Reusable acquisition capabilities owned by ``runbook-data``."""

from __future__ import annotations

import inspect
from typing import Any, TypeAlias

from runbook.data.config import SourceConfig
from runbook.data.ingest.adapters.base import (
    HistoricalSourceAdapter,
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


def _bind_adapter_method(
    adapter_id: str, method_name: str, method: Any, *args: Any, **kwargs: Any
) -> inspect.Signature:
    """Require that a public adapter method accepts its actual call shape."""
    try:
        signature = inspect.signature(method)
        signature.bind(*args, **kwargs)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"incompatible adapter entry point group='runbook.adapters' name={adapter_id!r}: "
            f"{method_name} cannot accept the public keyword/argument contract ({exc})"
        ) from None
    return signature


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
    _bind_adapter_method(adapter_id, "validate", adapter.validate, object())
    _bind_adapter_method(
        adapter_id,
        "check",
        adapter.check,
        source_config=object(),
        acquisition_run="",
        observed_at=object(),
    )
    acquire_signature = _bind_adapter_method(
        adapter_id,
        "acquire",
        adapter.acquire,
        source_config=object(),
        readiness=object(),
        fetched_at=object(),
    )
    acquire_base = {"source_config": object(), "readiness": object(), "fetched_at": object()}
    accepts_previous_state = True
    try:
        acquire_signature.bind(**acquire_base, previous_state=None)
    except TypeError:
        accepts_previous_state = False
    accepts_previous_watermarks = True
    try:
        acquire_signature.bind(**acquire_base, previous_watermarks={})
    except TypeError:
        accepts_previous_watermarks = False
    if not accepts_previous_state and not accepts_previous_watermarks:
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
    "HistoricalSourceAdapter",
    "HttpAdapter",
    "LocalFileAdapter",
    "SourceAdapter",
    "get_adapter",
]
