from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from runbook.core.pdl.models import (
    PDLArtifacts,
    PDLManifest,
    PDLPage,
    PDLPageType,
    PDLPlotRefBlock,
    PDLStyle,
    PDLTableBlock,
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
    extensions: dict[str, dict[str, Any]] | None = None,
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

    return PDLManifest(
        title=resolved_title,
        snapshot_id=ctx.snapshot.snapshot_id,
        as_of=ctx.snapshot.as_of or ctx.snapshot.watermark,
        style=style,
        page=page,
        artifacts=_build_artifacts(page),
        extensions=extensions,
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


def table(
    *,
    name: str,
    ref: TableArtifactRef,
    row: int,
    col: int,
    title: str | None = None,
    row_span: int = 1,
    col_span: int = 1,
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
        row=row,
        col=col,
        row_span=row_span,
        col_span=col_span,
        extensions=extensions,
    )


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
