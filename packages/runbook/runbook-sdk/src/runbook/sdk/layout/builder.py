"""Small, explicit builders for report, section, and grid composition."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable

from runbook.core.pdl.models import PDLColumn
from runbook.core.table.models import TableArtifactRef

from .models import GridLayout, HeadingLayout, LayoutBlock, LayoutNode, ReportLayout, SectionLayout

_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _slug(value: object) -> str:
    """Build a stable readable owner label."""
    result = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip().lower()).strip("-._")
    return result or "report"


def _name(value: str | None, *, kind: str = "block") -> str | None:
    """Validate an optional explicit PDL-safe name."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or not _NAME_RE.fullmatch(value.strip()):
        raise ValueError(f"{kind} name must contain only letters, numbers, '.', '_', or '-': {value!r}")
    return value.strip()


def _span(value: int, *, kind: str, minimum: int = 1) -> int:
    """Validate one positive integer span or column count."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{kind} must be an integer >= {minimum}, got {value!r}")
    return value


def _rebase_generated(node: LayoutBlock | HeadingLayout, old: str, new: str) -> None:
    """Rebase one generated name while preserving explicit names."""
    if node.generated_name and node.name:
        node.name = f"{new}-{node.name.removeprefix(old + '-')}"


def _layout_counts(children: Iterable[object]) -> tuple[int, int, int]:
    """Count sections, grids, and blocks recursively for compact repr output."""
    sections = grids = blocks = 0
    for child in children:
        if isinstance(child, SectionLayout):
            sections += 1
            if child.title:
                blocks += 1
            nested_sections, nested_grids, nested_blocks = _layout_counts(child.children)
            sections += nested_sections
            grids += nested_grids
            blocks += nested_blocks
        elif isinstance(child, GridLayout):
            grids += 1
            blocks += len(child.blocks)
        elif isinstance(child, (LayoutBlock, HeadingLayout)):
            blocks += 1
    return sections, grids, blocks


def table(
    ref: TableArtifactRef,
    *,
    name: str | None = None,
    title: str | None = None,
    col_span: int = 1,
    row_span: int = 1,
    columns: list[PDLColumn] | None = None,
    extensions: dict[str, dict[str, Any]] | None = None,
) -> LayoutBlock:
    """Create a thin table block from an existing artifact reference."""
    if not isinstance(ref, TableArtifactRef):
        raise TypeError(f"table(...) expects TableArtifactRef, got {type(ref)!r}")
    return LayoutBlock(
        kind="table",
        value=ref,
        name=_name(name),
        title=title,
        col_span=_span(col_span, kind="col_span"),
        row_span=_span(row_span, kind="row_span"),
        columns=list(columns) if columns is not None else None,
        extensions=dict(extensions) if extensions is not None else None,
    )


def plot(
    ref: str,
    *,
    name: str | None = None,
    title: str | None = None,
    col_span: int = 1,
    row_span: int = 1,
    extensions: dict[str, dict[str, Any]] | None = None,
) -> LayoutBlock:
    """Create a thin plot-reference block from an artifact reference."""
    if not isinstance(ref, str) or not ref.strip():
        raise TypeError(f"plot(...) expects a non-empty artifact reference, got {ref!r}")
    return LayoutBlock(
        kind="plot",
        value=ref,
        name=_name(name),
        title=title,
        col_span=_span(col_span, kind="col_span"),
        row_span=_span(row_span, kind="row_span"),
        extensions=dict(extensions) if extensions is not None else None,
    )


def text(
    value: str | None = None,
    *,
    text: str | None = None,
    name: str | None = None,
    title: str | None = None,
    col_span: int = 1,
    row_span: int = 1,
    extensions: dict[str, dict[str, Any]] | None = None,
) -> LayoutBlock:
    """Create a plain text block."""
    if value is not None and text is not None:
        raise TypeError("text(...) accepts either a positional value or text=, not both")
    resolved = text if text is not None else value
    if not isinstance(resolved, str):
        raise TypeError(f"text(...) expects a string, got {type(resolved)!r}")
    return LayoutBlock(
        kind="text",
        value=resolved,
        name=_name(name),
        title=title,
        col_span=_span(col_span, kind="col_span"),
        row_span=_span(row_span, kind="row_span"),
        extensions=dict(extensions) if extensions is not None else None,
    )


class Report:
    """An ordered report layout with explicit child ownership."""

    def __init__(
        self,
        title: str,
        children: Iterable[object] | None = None,
        *,
        sections: Iterable[object] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Report title must be a non-empty string")
        self._layout = ReportLayout(title=title.strip())
        self.extensions = dict(extensions) if extensions is not None else None
        self._label = _slug(title)
        self._block_counter = 0
        self._section_counter = 0
        self._grid_counter = 0
        if children is not None:
            self.extend(children)
        if sections is not None:
            self.extend(sections)

    @property
    def title(self) -> str:
        """Return the report title."""
        return self._layout.title

    @property
    def children(self) -> list[LayoutNode]:
        """Return ordered top-level child dataclasses."""
        return self._layout.children

    def __repr__(self) -> str:
        sections, grids, blocks = _layout_counts(self.children)
        return f"Report({self.title!r}, sections={sections}, grids={grids}, blocks={blocks})"

    def add(self, child: object) -> object:
        """Append one owned report child and assign an auto name if needed."""
        if isinstance(child, Section):
            self._section_counter += 1
            child._set_label(f"{self._label}-section-{self._section_counter:03d}")
            child = child._layout
        elif isinstance(child, Grid):
            self._grid_counter += 1
            child._set_label(f"{self._label}-grid-{self._grid_counter:03d}")
            child = child._layout
        if not isinstance(child, (SectionLayout, GridLayout, LayoutBlock, HeadingLayout)):
            raise TypeError("Report.add(...) expects a Section, Grid, block, or heading")
        if isinstance(child, LayoutBlock):
            self._block_counter += 1
            if child.name is None:
                child.name = f"{self._label}-{child.kind}-{self._block_counter:03d}"
                child.generated_name = True
        if isinstance(child, HeadingLayout):
            self._block_counter += 1
            if child.name is None:
                child.name = f"{self._label}-heading-{self._block_counter:03d}"
                child.generated_name = True
        self.children.append(child)
        return child

    def extend(self, children: Iterable[object]) -> "Report":
        """Append report children from any iterable."""
        for child in children:
            self.add(child)
        return self

    def heading(self, value: str, *, name: str | None = None) -> HeadingLayout:
        """Append a report-level heading."""
        heading = HeadingLayout(_heading_text(value), _name(name, kind="heading"))
        self.add(heading)
        return heading

    def section(self, title: str | None = None, *, children: Iterable[object] | None = None) -> "Section":
        """Create and append a section."""
        self._section_counter += 1
        child = Section(title, children=children, _label=f"{self._label}-section-{self._section_counter:03d}")
        self.children.append(child._layout)
        return child

    def grid(self, blocks: Iterable[object] | None = None, *, columns: int = 1, name: str | None = None) -> "Grid":
        """Create and append a top-level grid."""
        self._grid_counter += 1
        child = Grid(
            blocks,
            columns=columns,
            name=name,
            _label=f"{self._label}-grid-{self._grid_counter:03d}",
        )
        self.children.append(child._layout)
        return child


class Section:
    """An ordered report section containing blocks, headings, and grids."""

    def __init__(
        self, title: str | None, children: Iterable[object] | None = None, *, _label: str | None = None
    ) -> None:
        if title is not None and (not isinstance(title, str) or not title.strip()):
            raise ValueError("Section title must be a non-empty string or None")
        self._layout = SectionLayout(title.strip() if isinstance(title, str) else None)
        self._label = _label or _slug(title or "section")
        self._block_counter = 0
        self._grid_counter = 0
        if children is not None:
            self.extend(children)

    @property
    def title(self) -> str | None:
        """Return the optional section title."""
        return self._layout.title

    @property
    def children(self) -> list[GridLayout | LayoutBlock | HeadingLayout]:
        """Return ordered section child dataclasses."""
        return self._layout.children

    def __enter__(self) -> "Section":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def _set_label(self, label: str) -> None:
        """Rebase generated names when a detached section gains an owner."""
        old_label = self._label
        self._label = label
        grid_index = 0
        for child in self.children:
            if isinstance(child, GridLayout):
                grid_index += 1
                old_grid_label = child.owner_label or old_label
                new_grid_label = f"{label}-grid-{grid_index:03d}"
                for block in child.blocks:
                    _rebase_generated(block, old_grid_label, new_grid_label)
                child.owner_label = new_grid_label
            elif isinstance(child, (LayoutBlock, HeadingLayout)):
                _rebase_generated(child, old_label, label)

    def add(self, child: object) -> object:
        """Append one owned section child and assign an auto name if needed."""
        if isinstance(child, Grid):
            self._grid_counter += 1
            child._set_label(f"{self._label}-grid-{self._grid_counter:03d}")
            child = child._layout
        if not isinstance(child, (GridLayout, LayoutBlock, HeadingLayout)):
            raise TypeError("Section.add(...) expects a Grid, block, or heading")
        if isinstance(child, LayoutBlock):
            self._block_counter += 1
            if child.name is None:
                child.name = f"{self._label}-{child.kind}-{self._block_counter:03d}"
                child.generated_name = True
        if isinstance(child, HeadingLayout):
            self._block_counter += 1
            if child.name is None:
                child.name = f"{self._label}-heading-{self._block_counter:03d}"
                child.generated_name = True
        self.children.append(child)
        return child

    def extend(self, children: Iterable[object]) -> "Section":
        """Append section children from any iterable."""
        for child in children:
            self.add(child)
        return self

    def heading(self, value: str, *, name: str | None = None) -> HeadingLayout:
        """Append a section heading."""
        heading = HeadingLayout(_heading_text(value), _name(name, kind="heading"))
        self.add(heading)
        return heading

    def grid(self, blocks: Iterable[object] | None = None, *, columns: int = 1, name: str | None = None) -> "Grid":
        """Create and append a grid in this section."""
        self._grid_counter += 1
        child = Grid(
            blocks,
            columns=columns,
            name=name,
            _label=f"{self._label}-grid-{self._grid_counter:03d}",
        )
        self.children.append(child._layout)
        return child


class Grid:
    """An ordered, non-nested collection of blocks."""

    def __init__(
        self,
        blocks: Iterable[object] | None = None,
        *,
        columns: int = 1,
        name: str | None = None,
        _label: str | None = None,
    ) -> None:
        self.columns = _span(columns, kind="Grid columns")
        self._label = _label or _slug(name or "grid")
        self._layout = GridLayout(columns=self.columns, name=_name(name, kind="grid"), owner_label=self._label)
        self._block_counter = 0
        if blocks is not None:
            self.extend(blocks)

    @property
    def blocks(self) -> list[LayoutBlock]:
        """Return ordered block dataclasses."""
        return self._layout.blocks

    def __enter__(self) -> "Grid":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def __repr__(self) -> str:
        return f"Grid(columns={self.columns}, blocks={len(self.blocks)})"

    def _set_label(self, label: str) -> None:
        """Rebase generated block names when a detached grid gains an owner."""
        old_label = self._label
        self._label = label
        self._layout.owner_label = label
        for block in self.blocks:
            _rebase_generated(block, old_label, label)

    def add(
        self,
        block: LayoutBlock,
        *,
        col_span: int | None = None,
        row_span: int | None = None,
    ) -> LayoutBlock:
        """Append one block and validate it against this grid's width."""
        if not isinstance(block, LayoutBlock):
            if isinstance(block, (Grid, GridLayout)):
                raise ValueError(f"Grid '{self._label}' does not support nested grids")
            raise TypeError("Grid.add(...) expects a table, plot, or text block")
        if col_span is not None or row_span is not None:
            block = replace(
                block,
                col_span=block.col_span if col_span is None else _span(col_span, kind="col_span"),
                row_span=block.row_span if row_span is None else _span(row_span, kind="row_span"),
            )
        if block.col_span > self.columns:
            raise ValueError(
                f"Grid '{self._label}' has columns={self.columns} but block "
                f"{block.name or '<unnamed>'!r} requested col_span={block.col_span}"
            )
        if block.col_span < 1 or block.row_span < 1:
            raise ValueError(f"Grid '{self._label}' block {block.name or '<unnamed>'!r} spans must be >= 1")
        self._block_counter += 1
        if block.name is None:
            block.name = f"{self._label}-{block.kind}-{self._block_counter:03d}"
            block.generated_name = True
        self.blocks.append(block)
        return block

    def extend(self, blocks: Iterable[object]) -> "Grid":
        """Append blocks from any iterable."""
        for block in blocks:
            self.add(block)  # type: ignore[arg-type]
        return self

    def table(self, ref: TableArtifactRef, **kwargs: Any) -> LayoutBlock:
        """Create and append a table block."""
        return self.add(table(ref, **kwargs))

    def plot(self, ref: str, **kwargs: Any) -> LayoutBlock:
        """Create and append a plot block."""
        return self.add(plot(ref, **kwargs))

    def text(self, value: str | None = None, **kwargs: Any) -> LayoutBlock:
        """Create and append a text block."""
        return self.add(text(value, **kwargs))


def _heading_text(value: str) -> str:
    """Validate and normalize heading text."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("heading must be a non-empty string")
    return value.strip()


def report(
    title: str,
    sections: Iterable[object] | None = None,
    *,
    children: Iterable[object] | None = None,
    extensions: dict[str, Any] | None = None,
) -> Report:
    """Build a report using the functional/list authoring style."""
    return Report(title, children=children, sections=sections, extensions=extensions)


def section(title: str | None, *items: object, children: Iterable[object] | None = None) -> Section:
    """Build a section using the functional/list authoring style."""
    if items and children is not None:
        raise TypeError("section(...) accepts positional children or children=, not both")
    return Section(title, children=children if children is not None else items)


def grid(blocks: Iterable[object] | None = None, *, columns: int = 1, name: str | None = None) -> Grid:
    """Build a grid using the functional/list authoring style."""
    return Grid(blocks, columns=columns, name=name)


__all__ = ["Grid", "Report", "Section", "grid", "plot", "report", "section", "table", "text"]
