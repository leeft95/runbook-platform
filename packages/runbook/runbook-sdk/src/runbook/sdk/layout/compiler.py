"""Compile composable layout objects into the canonical pdl-core manifest."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from itertools import count
from typing import Any

from runbook.core.pdl.models import PDLBlock, PDLLinkDestination
from runbook.sdk import ui

from .builder import Report
from .models import GridLayout, HeadingLayout, LayoutBlock, ReportLayout, RowLayout, SectionLayout, StackLayout


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


def _surviving_row(node: object) -> list[RowLayout]:
    """Collect non-empty explicit rows in child order."""
    if isinstance(node, (ReportLayout, SectionLayout)):
        result: list[RowLayout] = []
        for child in node.children:
            result.extend(_surviving_row(child))
        return result
    if isinstance(node, RowLayout):
        return [node] if node.children else []
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
        elif isinstance(node, StackLayout):
            for block_index, block in enumerate(node.children, 1):
                add(_block_name(block, node.name or owner, block_index), block.kind)
        elif isinstance(node, RowLayout):
            for slot_index, child in enumerate(node.children, 1):
                if isinstance(child, StackLayout):
                    for block_index, block in enumerate(child.children, 1):
                        add(_block_name(block, child.name or node.name or owner, block_index), block.kind)
                else:
                    add(_block_name(child, node.name or owner, slot_index), child.kind)
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


def _validate_stack(stack: StackLayout, owner: str) -> None:
    """Validate one explicit vertical composition."""
    if not stack.children:
        raise ValueError(f"Stack '{stack.owner_label or owner}' cannot be empty")
    for block in stack.children:
        if not isinstance(block, LayoutBlock):
            raise ValueError(f"Stack '{stack.owner_label or owner}' accepts only direct blocks")
        if isinstance(block.col_span, bool) or not isinstance(block.col_span, int) or block.col_span < 1:
            raise ValueError(
                f"Stack '{stack.owner_label or owner}' block {block.name or '<unnamed>'!r} "
                f"col_span={block.col_span!r}; expected a positive integer"
            )
        if block.col_span != 1:
            raise ValueError(
                f"Stack '{stack.owner_label or owner}' block {block.name or '<unnamed>'!r} requested "
                f"col_span={block.col_span}; Stack children occupy the stack's full width"
            )
        if isinstance(block.row_span, bool) or not isinstance(block.row_span, int) or block.row_span < 1:
            raise ValueError(
                f"Stack '{stack.owner_label or owner}' block {block.name or '<unnamed>'!r} row_span must be >= 1"
            )


def _validate_row(row: RowLayout, owner: str) -> None:
    """Validate one explicit horizontal composition."""
    if isinstance(row.columns, bool) or not isinstance(row.columns, int) or row.columns < 1:
        raise ValueError(
            f"Row '{row.owner_label or owner}' has invalid columns={row.columns!r}; expected an integer >= 1"
        )
    if len(row.children) > row.columns:
        raise ValueError(
            f"Row '{row.owner_label or owner}' has columns={row.columns}; too many children ({len(row.children)})"
        )
    for child in row.children:
        if isinstance(child, StackLayout):
            _validate_stack(child, row.owner_label or owner)
            continue
        if not isinstance(child, LayoutBlock):
            raise ValueError(f"Row '{row.owner_label or owner}' accepts only direct blocks or Stack children")
        if isinstance(child.col_span, bool) or not isinstance(child.col_span, int) or child.col_span < 1:
            raise ValueError(
                f"Row '{row.owner_label or owner}' block {child.name or '<unnamed>'!r} "
                f"col_span={child.col_span!r}; expected a positive integer"
            )
        if child.col_span != 1:
            raise ValueError(
                f"Row '{row.owner_label or owner}' block {child.name or '<unnamed>'!r} requested "
                f"col_span={child.col_span}; Row children occupy one logical slot"
            )
        if isinstance(child.row_span, bool) or not isinstance(child.row_span, int) or child.row_span < 1:
            raise ValueError(
                f"Row '{row.owner_label or owner}' block {child.name or '<unnamed>'!r} row_span must be >= 1"
            )


def _validate_composition(node: object, owner: str) -> None:
    """Validate authoring-only composition nodes before width normalization."""
    if isinstance(node, (ReportLayout, SectionLayout)):
        for child in node.children:
            _validate_composition(child, owner)
    elif isinstance(node, GridLayout):
        _validate_grid(node, node.name or owner)
    elif isinstance(node, RowLayout):
        _validate_row(node, node.name or owner)
    elif isinstance(node, StackLayout):
        _validate_stack(node, node.name or owner)


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


def _validate_direct_block(block: LayoutBlock) -> None:
    """Reject horizontal spans that direct blocks cannot express."""
    if block.col_span != 1:
        raise ValueError(
            f"Direct block {block.name or '<unnamed>'!r} cannot specify "
            f"col_span={block.col_span}; place the block inside a Grid "
            "to control horizontal span."
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
    if block.kind == "link":
        if block.label is None or not isinstance(block.value, PDLLinkDestination):
            raise TypeError("link layout blocks require a label and static destination")
        return ui.link(
            name=name,
            label=block.label,
            destination=block.value,
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
    """Compile a Report into a validated pdl-core manifest."""
    layout = _layout(report)
    _validate_composition(layout, layout.title)
    grids = _surviving_grid(layout)
    rows = _surviving_row(layout)
    widths = [grid.columns for grid in grids] + [row.columns for row in rows]
    columns = math.lcm(*widths) if widths else 1
    configured_limit = _configured_limit(ctx)
    if columns > configured_limit:
        values = ", ".join(str(width) for width in widths)
        raise ValueError(
            f"Report '{layout.title}' requires columns={columns} for logical grids/rows ({values}), "
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
        _validate_direct_block(block)
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

    def add_stack(stack: StackLayout, owner: str, *, col: int = 1, col_span: int = columns) -> None:
        """Emit a stack's direct blocks vertically at one page position."""
        nonlocal row_cursor, auto_index
        _validate_stack(stack, stack.name or owner)
        local_row = row_cursor + 1
        for block_index, block in enumerate(stack.children, 1):
            auto_index += 1
            name = _block_name(block, stack.name or owner, auto_index)
            pdl_blocks.append(
                _lower_block(
                    block,
                    name=name,
                    row=local_row,
                    col=col,
                    row_span=block.row_span,
                    col_span=col_span,
                )
            )
            local_row += block.row_span
        row_cursor = local_row - 1

    def add_row(row: RowLayout, owner: str) -> None:
        """Emit one explicit row with deterministic slot heights."""
        nonlocal row_cursor, auto_index
        _validate_row(row, row.name or owner)
        if not row.children:
            return
        factor = columns // row.columns
        heights = [
            (sum(block.row_span for block in child.children) if isinstance(child, StackLayout) else child.row_span)
            for child in row.children
        ]
        physical_height = max(heights)
        start_row = row_cursor + 1
        for slot_index, child in enumerate(row.children):
            slot_col = slot_index * factor + 1
            if isinstance(child, StackLayout):
                local_row = start_row
                for block_index, block in enumerate(child.children, 1):
                    auto_index += 1
                    name = _block_name(block, child.name or row.name or owner, auto_index)
                    pdl_blocks.append(
                        _lower_block(
                            block,
                            name=name,
                            row=local_row,
                            col=slot_col,
                            row_span=block.row_span,
                            col_span=factor,
                        )
                    )
                    local_row += block.row_span
                continue
            auto_index += 1
            name = _block_name(child, row.name or owner, auto_index)
            pdl_blocks.append(
                _lower_block(
                    child,
                    name=name,
                    row=start_row,
                    col=slot_col,
                    row_span=physical_height,
                    col_span=factor,
                )
            )
        row_cursor += physical_height

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
            elif isinstance(child, GridLayout):
                add_grid(child, section_owner)
            elif isinstance(child, RowLayout):
                add_row(child, section_owner)
            else:
                add_stack(child, section_owner)

    for child_index, child in enumerate(layout.children, 1):
        if isinstance(child, SectionLayout):
            add_section(child, layout.title, child_index)
        elif isinstance(child, LayoutBlock):
            add_direct(child, layout.title)
        elif isinstance(child, HeadingLayout):
            add_heading(child, layout.title)
        elif isinstance(child, GridLayout):
            add_grid(child, layout.title)
        elif isinstance(child, RowLayout):
            add_row(child, layout.title)
        else:
            add_stack(child, layout.title)

    if not pdl_blocks:
        raise ValueError(f"Report '{layout.title}' has no blocks to compile; add at least one block")
    page = ui.grid(rows=row_cursor, columns=columns, blocks=pdl_blocks)
    return ui.manifest(ctx, title=layout.title, page=page, extensions=getattr(report, "extensions", None))


__all__ = ["compile_layout"]
