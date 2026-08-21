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

_CURRENCY_SYMBOLS = {
    "GBP": "£",
    "USD": "$",
    "EUR": "€",
    "JPY": "¥",
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
            # Keep both endpoints in a client-side in-range date filter. The
            # renderer owns this option; PDL does not expose AG Grid config.
            definition["filterParams"] = {"inRangeInclusive": True}
            # Row data is serialized JSON, so AG Grid's string date types keep
            # client-side sorting/filtering deterministic without Date objects
            # or user-provided JavaScript. Inference supplies the format kind;
            # an explicit time column without one uses the date contract.
            definition["cellDataType"] = (
                "dateTimeString" if semantic.format is not None and semantic.format.kind == "datetime" else "dateString"
            )
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


def _formatter(format_model: Any) -> dict[str, str]:
    """Return one of the renderer-owned formatters; never accept user JS."""
    kind = format_model.kind
    decimals = getattr(format_model, "decimals", None)
    number_spec = ",~g" if decimals is None else f",.{decimals}f"
    if kind == "number":
        source = f"params.value == null ? '' : d3.format({json.dumps(number_spec)})(params.value)"
    elif kind == "currency":
        currency_code = str(format_model.currency).upper()
        symbol = _CURRENCY_SYMBOLS.get(currency_code, f"{currency_code} ")
        locale = json.dumps(
            {
                "decimal": ".",
                "thousands": ",",
                "grouping": [3],
                "currency": [symbol, ""],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        source = f"params.value == null ? '' : d3.formatLocale({locale}).format({json.dumps('$' + number_spec)})(params.value)"
    elif kind == "percent":
        percent_spec = ".2%" if decimals is None else f".{decimals}%"
        source = f"params.value == null ? '' : d3.format({json.dumps(percent_spec)})(params.value)"
    elif kind == "date":
        source = "params.value == null ? '' : d3.timeFormat('%b %-d, %Y')(d3.timeParse('%Y-%m-%d')(params.value))"
    elif kind == "datetime":
        source = "params.value == null ? '' : d3.timeFormat('%b %-d, %Y %H:%M')(d3.isoParse(params.value))"
    else:
        raise ValueError(f"unsupported PDL column format: {kind!r}")
    return {"function": source}


__all__ = ["ag_grid_default_col_def", "build_ag_grid_column_defs"]
