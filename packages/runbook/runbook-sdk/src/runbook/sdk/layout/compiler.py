"""Compile composable layout objects into the canonical pdl-core manifest."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from itertools import count
from typing import Any

from runbook.core.pdl.models import PDLBlock
from runbook.sdk import ui

from .builder import Report
from .models import GridLayout, HeadingLayout, LayoutBlock, ReportLayout, SectionLayout


def _layout(value: Report | ReportLayout) -> ReportLayout:
    """Return the underlying report dataclass."""
    if isinstance(value, Report):
        return value._layout
    if isinstance(value, ReportLayout):
        return value
    raise TypeError(f"compile_layout(...) expects Report, got {type(value)!r}")


def _slug(value: object) -> str:
    """Build a stable readable owner label."""
    result = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip().lower()).strip("-._")
    return result or "section"


def _surviving_grid(node: object) -> list[GridLayout]:
    """Collect non-empty grids in child order."""
    if isinstance(node, (ReportLayout, SectionLayout)):
        result: list[GridLayout] = []
        for child in node.children:
            result.extend(_surviving_grid(child))
        return result
    if isinstance(node, GridLayout):
        return [node] if node.blocks else []
    return []


def _has_content(section: SectionLayout) -> bool:
    """Return whether a section has content after empty-grid omission."""
    return any(not isinstance(child, GridLayout) or bool(child.blocks) for child in section.children)


def _block_name(block: LayoutBlock, owner: str, index: int) -> str:
    """Resolve an explicit or fallback block name."""
    if block.name:
        return block.name
    return f"{owner}-{block.kind}-{index:03d}"


def _validate_names(layout: ReportLayout) -> None:
    """Reject duplicate names among the blocks that will be emitted."""
    names: set[str] = set()

    def add(name: str, kind: str) -> None:
        """Record one name and reject a duplicate."""
        if name in names:
            raise ValueError(f"duplicate layout block name {name!r} ({kind})")
        names.add(name)

    def walk(node: object, owner: str, index: int = 0) -> None:
        """Walk one layout node for name validation."""
        if isinstance(node, LayoutBlock):
            add(_block_name(node, owner, len(names) + 1), node.kind)
        elif isinstance(node, HeadingLayout):
            add(node.name or f"{owner}-heading-{len(names) + 1:03d}", "heading")
        elif isinstance(node, GridLayout):
            for block_index, block in enumerate(node.blocks, 1):
                add(_block_name(block, node.name or owner, block_index), block.kind)
        elif isinstance(node, SectionLayout):
            if _has_content(node):
                section_owner = f"{_slug(node.title or owner)}-section-{index:03d}"
                if node.title:
                    add(f"{section_owner}-title", "section title")
                for child_index, section_child in enumerate(node.children, 1):
                    walk(section_child, section_owner, child_index)
        elif isinstance(node, ReportLayout):
            for child_index, report_child in enumerate(node.children, 1):
                walk(report_child, owner, child_index)

    walk(layout, layout.title)


def _validate_grid(grid: GridLayout, owner: str) -> None:
    """Validate grid and block span constraints with context."""
    if isinstance(grid.columns, bool) or not isinstance(grid.columns, int) or grid.columns < 1:
        raise ValueError(f"Grid '{owner}' has invalid columns={grid.columns!r}; expected an integer >= 1")
    for block in grid.blocks:
        if isinstance(block.col_span, bool) or not isinstance(block.col_span, int) or block.col_span < 1:
            raise ValueError(
                f"Grid '{owner}' block {block.name or '<unnamed>'!r} requested col_span={block.col_span}; expected >= 1"
            )
        if isinstance(block.row_span, bool) or not isinstance(block.row_span, int) or block.row_span < 1:
            raise ValueError(
                f"Grid '{owner}' block {block.name or '<unnamed>'!r} requested row_span={block.row_span}; expected >= 1"
            )
        if block.col_span > grid.columns:
            raise ValueError(
                f"Grid '{owner}' has columns={grid.columns} but block "
                f"{block.name or '<unnamed>'!r} requested col_span={block.col_span}"
            )


def _configured_limit(ctx: Any) -> int:
    """Read and validate the optional report page-width limit."""
    config = getattr(ctx, "config", {})
    layout_config = config.get("layout", {}) if isinstance(config, Mapping) else {}
    if layout_config is None:
        layout_config = {}
    if not isinstance(layout_config, Mapping):
        raise ValueError("ctx.config['layout'] must be a mapping when provided")
    configured_limit = layout_config.get("max_columns", 12)
    if isinstance(configured_limit, bool) or not isinstance(configured_limit, int) or configured_limit < 1:
        raise ValueError(f"layout.max_columns must be a positive integer, got {configured_limit!r}")
    return configured_limit


def _place_grid(grid: GridLayout, owner: str) -> list[tuple[LayoutBlock, int, int]]:
    """Place blocks with deterministic first-fit occupancy scanning."""
    _validate_grid(grid, owner)
    occupied: set[tuple[int, int]] = set()
    placed: list[tuple[LayoutBlock, int, int]] = []
    for block in grid.blocks:
        for row in count(1):
            for col in range(1, grid.columns + 1):
                cells = {
                    (row + row_offset, col + col_offset)
                    for row_offset in range(block.row_span)
                    for col_offset in range(block.col_span)
                }
                if any(cell[1] > grid.columns for cell in cells) or cells & occupied:
                    continue
                occupied.update(cells)
                placed.append((block, row, col))
                break
            else:
                continue
            break
    return placed


def _lower_block(
    block: LayoutBlock,
    *,
    name: str,
    row: int,
    col: int,
    row_span: int,
    col_span: int,
) -> PDLBlock:
    """Lower one positioned draft through the existing SDK UI helpers."""
    if block.kind == "table":
        return ui.table(
            name=name,
            ref=block.value,
            row=row,
            col=col,
            title=block.title,
            row_span=row_span,
            col_span=col_span,
            columns=block.columns,
            extensions=block.extensions,
        )
    if block.kind == "plot":
        return ui.plot(
            name=name,
            ref=block.value,
            row=row,
            col=col,
            title=block.title,
            row_span=row_span,
            col_span=col_span,
            extensions=block.extensions,
        )
    return ui.text(
        name=name,
        text=block.value,
        row=row,
        col=col,
        title=block.title,
        row_span=row_span,
        col_span=col_span,
        extensions=block.extensions,
    )


def _lower_heading(heading: HeadingLayout, *, name: str, row: int, columns: int) -> PDLBlock:
    """Lower a heading to a full-width PDL text block."""
    return ui.text(name=name, text="", title=heading.text, row=row, col=1, col_span=columns)


def compile_layout(ctx: Any, report: Report | ReportLayout) -> Any:
    """Compile a Report into a validated pdl-core/0.1 manifest."""
    layout = _layout(report)
    grids = _surviving_grid(layout)
    for grid in grids:
        _validate_grid(grid, grid.name or "grid")
    columns = math.lcm(*(grid.columns for grid in grids)) if grids else 1
    configured_limit = _configured_limit(ctx)
    if columns > configured_limit:
        values = ", ".join(str(grid.columns) for grid in grids)
        raise ValueError(
            f"Report '{layout.title}' requires columns={columns} for logical grids ({values}), "
            f"which exceeds layout.max_columns={configured_limit}; "
            "set ctx.config['layout']['max_columns'] explicitly for an ultrawide report"
        )
    _validate_names(layout)

    pdl_blocks: list[PDLBlock] = []
    row_cursor = 0
    auto_index = 0

    def add_direct(block: LayoutBlock, owner: str) -> None:
        """Append one direct full-width block."""
        nonlocal row_cursor, auto_index
        auto_index += 1
        name = _block_name(block, owner, auto_index)
        pdl_blocks.append(
            _lower_block(
                block,
                name=name,
                row=row_cursor + 1,
                col=1,
                row_span=block.row_span,
                col_span=columns,
            )
        )
        row_cursor += block.row_span

    def add_heading(heading: HeadingLayout, owner: str) -> None:
        """Append one full-width heading."""
        nonlocal row_cursor, auto_index
        auto_index += 1
        name = heading.name or f"{owner}-heading-{auto_index:03d}"
        pdl_blocks.append(_lower_heading(heading, name=name, row=row_cursor + 1, columns=columns))
        row_cursor += 1

    def add_grid(grid: GridLayout, owner: str) -> None:
        """Place and append one non-empty logical grid."""
        nonlocal row_cursor, auto_index
        if not grid.blocks:
            return
        placed = _place_grid(grid, grid.name or owner)
        factor = columns // grid.columns
        max_row = 0
        for block, local_row, local_col in placed:
            auto_index += 1
            name = _block_name(block, grid.name or owner, auto_index)
            pdl_row = row_cursor + local_row
            pdl_col = (local_col - 1) * factor + 1
            pdl_row_span = block.row_span
            pdl_col_span = block.col_span * factor
            pdl_blocks.append(
                _lower_block(
                    block,
                    name=name,
                    row=pdl_row,
                    col=pdl_col,
                    row_span=pdl_row_span,
                    col_span=pdl_col_span,
                )
            )
            max_row = max(max_row, local_row + block.row_span - 1)
        row_cursor += max_row

    def add_section(section: SectionLayout, owner: str, section_index: int) -> None:
        """Append a surviving section and its ordered children."""
        nonlocal row_cursor
        if not _has_content(section):
            return
        section_owner = f"{_slug(section.title or owner)}-section-{section_index:03d}"
        if section.title:
            add_heading(HeadingLayout(section.title, f"{section_owner}-title"), section_owner)
        for child in section.children:
            if isinstance(child, LayoutBlock):
                add_direct(child, section_owner)
            elif isinstance(child, HeadingLayout):
                add_heading(child, section_owner)
            else:
                add_grid(child, section_owner)

    for child_index, child in enumerate(layout.children, 1):
        if isinstance(child, SectionLayout):
            add_section(child, layout.title, child_index)
        elif isinstance(child, LayoutBlock):
            add_direct(child, layout.title)
        elif isinstance(child, HeadingLayout):
            add_heading(child, layout.title)
        else:
            add_grid(child, layout.title)

    if not pdl_blocks:
        raise ValueError(f"Report '{layout.title}' has no blocks to compile; add at least one block")
    page = ui.grid(rows=row_cursor, columns=columns, blocks=pdl_blocks)
    return ui.manifest(ctx, title=layout.title, page=page, extensions=getattr(report, "extensions", None))


__all__ = ["compile_layout"]
