from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa
from runbook.core.pdl.models import (
    PDLAggregation,
    PDLArtifacts,
    PDLColumn,
    PDLColumnFormat,
    PDLColumnRole,
    PDLCurrencyFormat,
    PDLDateFormat,
    PDLDateTimeFormat,
    PDLLinkBlock,
    PDLLinkDestination,
    PDLManifest,
    PDLNumberFormat,
    PDLPage,
    PDLPageType,
    PDLPercentFormat,
    PDLPlotRefBlock,
    PDLStyle,
    PDLTableBlock,
    PDLTableWidth,
    PDLTextBlock,
    PDLTextFormat,
)
from runbook.core.table.models import TableArtifactRef


def _sorted_unique(values: Sequence[str]) -> list[str]:
    """Return stable sorted artifact references without duplicates."""
    return sorted(set(values))


def _build_artifacts(page: PDLPage) -> PDLArtifacts | None:
    """Build artifacts."""
    plots: list[str] = []
    tables: list[str] = []
    files: list[str] = []

    for block in page.blocks:
        if isinstance(block, PDLPlotRefBlock):
            plots.append(block.ref)
            continue
        if isinstance(block, PDLTableBlock):
            tables.append(block.data_ref)
            if block.style_ref:
                files.append(block.style_ref)
            if block.html_ref:
                files.append(block.html_ref)

    if not plots and not tables and not files:
        return None

    return PDLArtifacts(
        plots=_sorted_unique(plots) or None,
        tables=_sorted_unique(tables) or None,
        files=_sorted_unique(files) or None,
    )


def manifest(
    ctx: Any,
    *,
    page: PDLPage,
    title: str | None = None,
    style: PDLStyle | None = None,
    extensions: dict[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
) -> PDLManifest:
    """Build a canonical PDL manifest from context and page structure."""
    resolved_title = title
    if not resolved_title:
        config_title = getattr(ctx, "config", {}).get("title")
        if isinstance(config_title, str) and config_title.strip():
            resolved_title = config_title.strip()
    if not resolved_title:
        report_id = getattr(ctx, "report_id", None)
        if isinstance(report_id, str) and report_id.strip():
            resolved_title = report_id.strip()
    if not resolved_title:
        resolved_title = "Report"

    serialized_extensions: dict[str, dict[str, Any]] | None = None
    if extensions is not None:
        serialized_extensions = {}
        for namespace, extension in extensions.items():
            dump = getattr(extension, "model_dump", None)
            value = dump(mode="json") if callable(dump) else extension
            if not isinstance(value, dict):
                raise TypeError(f"PDL extension {namespace!r} must serialize to an object")
            serialized_extensions[namespace] = value

    requires_v02 = any(
        isinstance(block, PDLLinkBlock)
        or (isinstance(block, PDLTableBlock) and (bool(block.links) or block.width != "fill"))
        for block in page.blocks
    )
    return PDLManifest(
        schema_version="pdl-core/0.2" if requires_v02 else "pdl-core/0.1",
        title=resolved_title,
        snapshot_id=ctx.snapshot.snapshot_id,
        as_of=ctx.snapshot.as_of or ctx.snapshot.watermark,
        style=style,
        page=page,
        artifacts=_build_artifacts(page),
        warnings=warnings or (),
        extensions=serialized_extensions,
    )


def grid(*, rows: int, columns: int, blocks: list[Any]) -> PDLPage:
    """Create a fixed grid page from its blocks."""
    return PDLPage(
        page_type=PDLPageType.grid,
        rows=rows,
        columns=columns,
        blocks=blocks,
    )


def flex_grid(*, rows: int, columns: int, blocks: list[Any]) -> PDLPage:
    """Create a flexible grid page from its blocks."""
    return PDLPage(
        page_type=PDLPageType.flex_grid,
        rows=rows,
        columns=columns,
        blocks=blocks,
    )


def text(
    *,
    name: str,
    text: str,
    row: int,
    col: int,
    title: str | None = None,
    row_span: int = 1,
    col_span: int = 1,
    format: PDLTextFormat | None = None,
    extensions: dict[str, dict[str, Any]] | None = None,
) -> PDLTextBlock:
    """Create a positioned text block."""
    return PDLTextBlock(
        name=name,
        title=title,
        text=text,
        row=row,
        col=col,
        row_span=row_span,
        col_span=col_span,
        format=format,
        extensions=extensions,
    )


def link(
    *,
    name: str,
    label: str,
    destination: PDLLinkDestination,
    row: int,
    col: int,
    title: str | None = None,
    row_span: int = 1,
    col_span: int = 1,
    extensions: dict[str, dict[str, Any]] | None = None,
) -> PDLLinkBlock:
    """Create a positioned standalone link block."""
    if not isinstance(destination, PDLLinkDestination):
        raise TypeError(f"link(..., destination=...) expects PDLLinkDestination, got {type(destination)!r}")
    return PDLLinkBlock(
        name=name,
        title=title,
        label=label,
        destination=destination,
        row=row,
        col=col,
        row_span=row_span,
        col_span=col_span,
        extensions=extensions,
    )


def table(
    *,
    name: str,
    ref: TableArtifactRef,
    row: int,
    col: int,
    title: str | None = None,
    row_span: int = 1,
    col_span: int = 1,
    columns: list[PDLColumn] | None = None,
    width: PDLTableWidth = "fill",
    extensions: dict[str, dict[str, Any]] | None = None,
) -> PDLTableBlock:
    """Create a positioned table block from an artifact reference."""
    if not isinstance(ref, TableArtifactRef):
        raise TypeError(f"table(..., ref=...) expects TableArtifactRef, got {type(ref)!r}")
    return PDLTableBlock(
        name=name,
        title=title,
        data_ref=ref.data_ref,
        style_ref=ref.style_ref,
        html_ref=ref.html_ref,
        style_key=ref.style_key,
        links=ref.links,
        row=row,
        col=col,
        row_span=row_span,
        col_span=col_span,
        columns=columns,
        width=width,
        extensions=extensions,
    )


def column(
    field: str,
    *,
    label: str | None = None,
    role: PDLColumnRole | str | None = None,
    aggregation: PDLAggregation | str | None = None,
    format: PDLColumnFormat | None = None,
    hidden: bool = False,
) -> PDLColumn:
    """Build semantic metadata for one table column."""
    return PDLColumn(
        field=field,
        label=label,
        role=PDLColumnRole(role) if isinstance(role, str) else role,
        aggregation=PDLAggregation(aggregation) if isinstance(aggregation, str) else aggregation,
        format=format,
        hidden=hidden,
    )


def number(decimals: int | None = None) -> PDLNumberFormat:
    """Build a numeric display format."""
    return PDLNumberFormat(decimals=decimals)


def currency(currency_code: str, *, decimals: int | None = None) -> PDLCurrencyFormat:
    """Build a currency display format."""
    return PDLCurrencyFormat(currency=currency_code, decimals=decimals)


def percent(decimals: int | None = None) -> PDLPercentFormat:
    """Build a percentage display format."""
    return PDLPercentFormat(decimals=decimals)


def date() -> PDLDateFormat:
    """Build a date display format."""
    return PDLDateFormat()


def datetime() -> PDLDateTimeFormat:
    """Build a date-time display format."""
    return PDLDateTimeFormat()


def infer_columns(schema: pa.Schema) -> list[PDLColumn]:
    """Infer deterministic semantic columns from an Arrow schema."""
    result: list[PDLColumn] = []
    for field in schema:
        arrow_type = field.type
        if pa.types.is_dictionary(arrow_type):
            column = PDLColumn(field=field.name, role=PDLColumnRole.dimension)
        elif pa.types.is_string(arrow_type) or pa.types.is_boolean(arrow_type):
            column = PDLColumn(field=field.name, role=PDLColumnRole.dimension)
        elif pa.types.is_integer(arrow_type) or pa.types.is_floating(arrow_type) or pa.types.is_decimal(arrow_type):
            column = PDLColumn(
                field=field.name,
                role=PDLColumnRole.measure,
                aggregation=PDLAggregation.sum,
            )
        elif pa.types.is_date(arrow_type):
            column = PDLColumn(field=field.name, role=PDLColumnRole.time, format=PDLDateFormat())
        elif pa.types.is_timestamp(arrow_type):
            column = PDLColumn(field=field.name, role=PDLColumnRole.time, format=PDLDateTimeFormat())
        else:
            column = PDLColumn(field=field.name)
        result.append(column)
    return result


def merge_columns(schema: pa.Schema | None, columns: Sequence[PDLColumn] | None) -> list[PDLColumn]:
    """Merge explicit semantics over inferred Arrow fields and validate references."""
    explicit = list(columns or [])
    fields = [column.field for column in explicit]
    if len(fields) != len(set(fields)):
        raise ValueError("table columns must not contain duplicate fields")
    if schema is None:
        return explicit

    physical = {field.name for field in schema}
    unknown = [field for field in fields if field not in physical]
    if unknown:
        raise ValueError(f"table columns reference unknown fields: {unknown!r}")
    inferred = infer_columns(schema)
    overrides = {column.field: column for column in explicit}
    merged: list[PDLColumn] = []
    for item in inferred:
        override = overrides.get(item.field)
        if override is None:
            merged.append(item)
            continue
        updates = {
            name: getattr(override, name)
            for name in override.model_fields_set
            if name != "field" and (getattr(override, name) is not None or name == "hidden")
        }
        # model_copy(update=...) deliberately skips validation. Revalidate the
        # complete merged payload so an inferred dimension cannot acquire a
        # measure-only aggregation through an explicit partial override.
        merged.append(PDLColumn.model_validate({**item.model_dump(mode="python"), **updates}))
    return merged


def plot(
    *,
    name: str,
    ref: str,
    row: int,
    col: int,
    title: str | None = None,
    row_span: int = 1,
    col_span: int = 1,
    extensions: dict[str, dict[str, Any]] | None = None,
) -> PDLPlotRefBlock:
    """Create a positioned plot-reference block."""
    return PDLPlotRefBlock(
        name=name,
        title=title,
        ref=ref,
        row=row,
        col=col,
        row_span=row_span,
        col_span=col_span,
        extensions=extensions,
    )
