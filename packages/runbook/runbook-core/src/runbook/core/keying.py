from __future__ import annotations

from typing import Any, Mapping

from runbook.core.utils.hashing import (
    canonical_json,
    sha256_hexdigest,
)


def _binding_field(binding: object, key: str) -> Any:
    """Handle binding field."""
    if isinstance(binding, Mapping):
        return binding.get(key)
    return getattr(binding, key, None)


def _as_mapping(payload: object) -> Mapping[str, Any]:
    """Handle as mapping."""
    if isinstance(payload, Mapping):
        return payload
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        maybe = model_dump(mode="python")
        if isinstance(maybe, Mapping):
            return maybe
    raise TypeError(f"Unsupported config payload type: {type(payload)!r}")


def _normalize_context_payload(config_payload: object) -> dict[str, Any]:
    """Normalize context payload."""
    cfg = _as_mapping(config_payload)
    datasets = cfg.get("datasets", {})
    if not isinstance(datasets, Mapping):
        datasets = {}

    normalized_datasets: dict[str, Any] = {}
    for alias in sorted(str(k) for k in datasets.keys()):
        binding = datasets[alias]
        dataset_id = _binding_field(binding, "dataset_id")
        normalized_datasets[alias] = dataset_id if dataset_id is not None else binding

    params = cfg.get("params", {})
    if not isinstance(params, Mapping):
        params = {}
    layout = cfg.get("layout", {})
    if not isinstance(layout, Mapping):
        layout = {}

    return {
        "report_id": cfg.get("report_id"),
        "title": cfg.get("title") or cfg.get("report_id"),
        "datasets": normalized_datasets,
        "params": dict(params),
        "layout": dict(layout),
        "extensions": cfg.get("extensions") or {},
    }


def build_context_hash(config_payload: object) -> str:
    """Deterministic context hash from canonical execution config payload."""
    normalized = _normalize_context_payload(config_payload)
    return sha256_hexdigest(canonical_json(normalized))
