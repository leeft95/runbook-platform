"""Translate semantic PDL table columns into safe AG Grid definitions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pyarrow as pa
from runbook.core.pdl.models import PDLColumn, PDLColumnRole
from runbook.core.table.models import (
    ResolvedTableStyle,
    TableFormatDate,
    TableFormatNumber,
    TableFormatString,
)
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

_AG_GRID_COMPONENTS_MARKER = "runbook-ag-grid-components-v1"
_AG_GRID_COMPONENTS_SCRIPT = r"""<script id="runbook-ag-grid-components-v1">
(function () {
    "use strict";

    const components = window.dashAgGridComponentFunctions =
        window.dashAgGridComponentFunctions || {};

    function textValue(params) {
        if (params.valueFormatted != null) {
            return String(params.valueFormatted);
        }
        return params.value == null ? "" : String(params.value);
    }

    function link(href, text, kind) {
        if (!href) {
            return text;
        }
        return React.createElement(
            "a",
            {
                href: String(href),
                "data-runbook-link-kind": kind || "",
                onClick: function (event) {
                    event.stopPropagation();
                },
            },
            text,
        );
    }

    components.runbookCellLinkRenderer = function (params) {
        const field = params.runbookLinksField;
        const links = field && params.data && params.data[field];
        const linkField = params.runbookLinkField;
        const href = links && links[linkField];
        return link(href, textValue(params), params.runbookLinkKind);
    };

    components.runbookIndexLinkRenderer = function (params) {
        const field = params.runbookIndexLinksField;
        const target = field && params.data && params.data[field];
        return link(target && target.href, textValue(params), target && target.kind);
    };

    components.runbookHeaderLinkRenderer = function (params) {
        const text = params.displayName || "";
        return link(
            params.runbookHeaderLink,
            text,
            params.runbookHeaderLinkKind,
        );
    };
})();
</script>"""


def register_ag_grid_components(app: Any) -> None:
    """Register SDK-owned AG Grid components on a host Dash app.

    Dash AG Grid resolves named renderers from this browser global. Injecting
    the tiny registry into the host's normal index keeps it available to
    embedded pages and to layouts that are created after app startup.
    """
    index_string = getattr(app, "index_string", None)
    if not isinstance(index_string, str) or _AG_GRID_COMPONENTS_MARKER in index_string:
        return
    if "</head>" in index_string:
        app.index_string = index_string.replace("</head>", f"{_AG_GRID_COMPONENTS_SCRIPT}</head>", 1)
    else:
        app.index_string = f"{_AG_GRID_COMPONENTS_SCRIPT}{index_string}"


def ag_grid_default_col_def() -> dict[str, Any]:
    """Return renderer defaults for client-side analytical table behaviour."""
    return dict(_DEFAULT_COL_DEF)


def build_ag_grid_column_defs(
    schema: pa.Schema,
    columns: Sequence[PDLColumn] | None = None,
    *,
    resolved: ResolvedTableStyle | None = None,
    cell_style_field: str | None = None,
    cell_links_field: str | None = None,
    cell_link_kinds: dict[str, str] | None = None,
    header_links: dict[str, tuple[str, str]] | None = None,
    index_field: str | None = None,
    index_header_link: tuple[str, str] | None = None,
    index_links_field: str | None = None,
    index_header_name: str = "",
    na_rep: str | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic AG Grid definitions from neutral table semantics.

    The optional resolved metadata is translated here, keeping core unaware of
    AG Grid while ensuring interactive tables use the same style plan as HTML
    and native Dash tables. Link functions are renderer-owned static code.
    """
    definitions: list[dict[str, Any]] = []
    header_style = _header_style(resolved)
    if index_field is not None:
        index_definition: dict[str, Any] = {
            "field": index_field,
            "headerName": index_header_name,
            **_DEFAULT_COL_DEF,
            "filter": "agTextColumnFilter",
            "headerStyle": header_style,
        }
        if index_header_link is not None:
            href, kind = index_header_link
            index_definition.update(
                {
                    "headerComponentParams": {"runbookHeaderLink": href, "runbookHeaderLinkKind": kind},
                    "headerComponent": "runbookHeaderLinkRenderer",
                }
            )
        if index_links_field is not None:
            index_definition.update(
                {
                    "cellRendererParams": {"runbookIndexLinksField": index_links_field},
                    "cellRenderer": "runbookIndexLinkRenderer",
                }
            )
        definitions.append(index_definition)
    for semantic in merge_columns(schema, columns):
        role = semantic.role
        width = resolved.column_width_px.get(semantic.field) if resolved is not None else None
        hidden = semantic.hidden or (resolved is not None and semantic.field in resolved.hidden_columns)
        definition: dict[str, Any] = {
            "field": semantic.field,
            "headerName": semantic.label or semantic.field,
            "hide": hidden,
            **_DEFAULT_COL_DEF,
            "enableRowGroup": role in {PDLColumnRole.dimension, PDLColumnRole.identifier, PDLColumnRole.time},
            "enablePivot": role in {PDLColumnRole.dimension, PDLColumnRole.identifier, PDLColumnRole.time},
            "enableValue": role == PDLColumnRole.measure,
            "headerStyle": header_style,
        }
        if width is not None:
            definition.update({"width": width, "minWidth": width})
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
        format_spec = semantic.format
        if resolved is not None:
            format_spec = resolved.formats.get(semantic.field, format_spec)
        if format_spec is not None:
            definition["valueFormatter"] = _formatter(format_spec, na_rep=na_rep)
        elif resolved is not None and (resolved.precision is not None or resolved.thousands is not None):
            definition["valueFormatter"] = _formatter(
                TableFormatNumber(
                    digits=6 if resolved.precision is None else resolved.precision,
                    thousands=bool(resolved.thousands),
                ),
                na_rep=na_rep,
                thousands_separator=resolved.thousands,
            )
        if cell_style_field is not None:
            definition.update(
                {
                    "cellStyle": {
                        "function": "(params.data && params.data["
                        f"{json.dumps(cell_style_field)}] && params.data[{json.dumps(cell_style_field)}][params.colDef.field]) || null"
                    },
                }
            )
        if cell_links_field is not None and cell_link_kinds and semantic.field in cell_link_kinds:
            definition.update(
                {
                    "cellRendererParams": {
                        "runbookLinksField": cell_links_field,
                        "runbookLinkField": semantic.field,
                        "runbookLinkKind": cell_link_kinds[semantic.field],
                    },
                    "cellRenderer": "runbookCellLinkRenderer",
                }
            )
        if header_links is not None and semantic.field in header_links:
            href, kind = header_links[semantic.field]
            definition.update(
                {
                    "headerComponentParams": {"runbookHeaderLink": href, "runbookHeaderLinkKind": kind},
                    "headerComponent": "runbookHeaderLinkRenderer",
                }
            )
        definitions.append(definition)
    return definitions


def _header_style(resolved: ResolvedTableStyle | None) -> dict[str, str]:
    """Translate the renderer-neutral header style to AG Grid CSS names."""
    if resolved is None:
        return {}
    global_style = resolved.global_style
    return {
        "borderBottom": global_style.header_border_bottom,
        "fontFamily": global_style.font_family,
        "fontSize": global_style.font_size,
        "textAlign": global_style.header_text_align,
    }


def _formatter(
    format_model: Any,
    *,
    na_rep: str | None = None,
    thousands_separator: str | None = None,
) -> dict[str, str]:
    """Return one of the renderer-owned formatters; never accept user JS."""
    kind = format_model.kind
    decimals = getattr(format_model, "decimals", getattr(format_model, "digits", None))
    thousands = getattr(format_model, "thousands", True)
    number_spec = ("," if thousands else "") + ("~g" if decimals is None else f".{decimals}f")
    null_text = json.dumps("" if na_rep is None else na_rep, ensure_ascii=False)
    if kind == "number":
        if thousands_separator not in (None, ",") and thousands:
            locale = json.dumps(
                {
                    "decimal": ".",
                    "thousands": thousands_separator,
                    "grouping": [3],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            format_spec = "~g" if decimals is None else f".{decimals}f"
            formatter = f"d3.formatLocale({locale}).format({json.dumps(format_spec)})(params.value)"
        else:
            formatter = f"d3.format({json.dumps(number_spec)})(params.value)"
        source = f"params.value == null ? {null_text} : {formatter}"
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
        source = f"params.value == null ? {null_text} : d3.formatLocale({locale}).format({json.dumps('$' + number_spec)})(params.value)"
    elif kind == "percent":
        percent_spec = ".2%" if decimals is None else f".{decimals}%"
        source = f"params.value == null ? {null_text} : d3.format({json.dumps(percent_spec)})(params.value)"
    elif kind == "date":
        pattern = format_model.pattern if isinstance(format_model, TableFormatDate) else "%b %-d, %Y"
        source = f"params.value == null ? {null_text} : d3.timeFormat({json.dumps(pattern)})(d3.timeParse('%Y-%m-%d')(params.value))"
    elif kind == "datetime":
        source = f"params.value == null ? {null_text} : d3.timeFormat('%b %-d, %Y %H:%M')(d3.isoParse(params.value))"
    elif kind == "string" and isinstance(format_model, TableFormatString):
        source = f"params.value == null ? {null_text} : String(params.value)"
    else:
        raise ValueError(f"unsupported PDL column format: {kind!r}")
    return {"function": source}


__all__ = ["ag_grid_default_col_def", "build_ag_grid_column_defs", "register_ag_grid_components"]
