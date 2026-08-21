"""Translate semantic PDL table columns into safe AG Grid definitions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pyarrow as pa
from runbook.core.pdl.models import PDLColumn, PDLColumnRole
from runbook.sdk.ui import merge_columns

_DEFAULT_COL_DEF: dict[str, Any] = {
    "sortable": True,
    "filter": True,
    "resizable": True,
    "suppressMovable": False,
}


def ag_grid_default_col_def() -> dict[str, Any]:
    """Return renderer defaults for client-side analytical table behaviour."""
    return dict(_DEFAULT_COL_DEF)


def build_ag_grid_column_defs(
    schema: pa.Schema,
    columns: Sequence[PDLColumn] | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic AG Grid column definitions from Arrow plus PDL semantics."""
    definitions: list[dict[str, Any]] = []
    for semantic in merge_columns(schema, columns):
        role = semantic.role
        definition: dict[str, Any] = {
            "field": semantic.field,
            "headerName": semantic.label or semantic.field,
            "hide": semantic.hidden,
            **_DEFAULT_COL_DEF,
            "enableRowGroup": role in {PDLColumnRole.dimension, PDLColumnRole.identifier, PDLColumnRole.time},
            "enablePivot": role in {PDLColumnRole.dimension, PDLColumnRole.identifier, PDLColumnRole.time},
            "enableValue": role == PDLColumnRole.measure,
        }
        if role == PDLColumnRole.measure:
            definition["filter"] = "agNumberColumnFilter"
            definition["aggFunc"] = semantic.aggregation.value if semantic.aggregation else "sum"
        elif role == PDLColumnRole.time:
            definition["filter"] = "agDateColumnFilter"
            definition["cellDataType"] = "date"
        elif role == PDLColumnRole.identifier:
            definition["filter"] = "agTextColumnFilter"
        elif role == PDLColumnRole.dimension:
            definition["filter"] = "agTextColumnFilter"
        else:
            definition["filter"] = "agTextColumnFilter"
        if semantic.format is not None:
            definition["valueFormatter"] = _formatter(semantic.format)
        definitions.append(definition)
    return definitions


def _formatter(format_model: Any) -> str:
    """Return one of the renderer-owned formatters; never accept user JS."""
    kind = format_model.kind
    decimals = getattr(format_model, "decimals", None)
    digits = "undefined" if decimals is None else str(decimals)
    if kind == "number":
        return f"params.value == null ? '' : Number(params.value).toLocaleString(undefined, {{maximumFractionDigits: {digits}}})"
    if kind == "currency":
        currency = json.dumps(format_model.currency)
        return (
            "params.value == null ? '' : Number(params.value).toLocaleString(undefined, "
            f"{{style: 'currency', currency: {currency}, maximumFractionDigits: {digits}}})"
        )
    if kind == "percent":
        return f"params.value == null ? '' : Number(params.value).toLocaleString(undefined, {{style: 'percent', maximumFractionDigits: {digits}}})"
    if kind == "date":
        return "params.value == null ? '' : new Date(params.value).toLocaleDateString()"
    if kind == "datetime":
        return "params.value == null ? '' : new Date(params.value).toLocaleString()"
    raise ValueError(f"unsupported PDL column format: {kind!r}")


__all__ = ["ag_grid_default_col_def", "build_ag_grid_column_defs"]
