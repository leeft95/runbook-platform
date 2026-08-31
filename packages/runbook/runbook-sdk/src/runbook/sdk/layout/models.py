"""Plain data objects used by the composable report layout API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from runbook.core.pdl.models import PDLColumn, PDLLinkDestination, PDLTableWidth
from runbook.core.table.models import TableArtifactRef

BlockKind = Literal["table", "plot", "text", "link"]


@dataclass
class LayoutBlock:
    """A renderer-neutral block draft awaiting placement."""

    kind: BlockKind
    value: TableArtifactRef | PDLLinkDestination | str
    name: str | None = None
    title: str | None = None
    col_span: int = 1
    row_span: int = 1
    columns: list[PDLColumn] | None = None
    table_width: PDLTableWidth = "fill"
    extensions: dict[str, dict[str, Any]] | None = None
    label: str | None = None
    generated_name: bool = field(default=False, repr=False)


@dataclass
class HeadingLayout:
    """A heading lowered to the existing PDL text block."""

    text: str
    name: str | None = None
    generated_name: bool = field(default=False, repr=False)


@dataclass
class GridLayout:
    """The ordered block storage for one logical grid."""

    columns: int
    blocks: list[LayoutBlock] = field(default_factory=list)
    name: str | None = None
    owner_label: str | None = field(default=None, repr=False)


@dataclass
class StackLayout:
    """The ordered block storage for one explicit vertical composition."""

    children: list[LayoutBlock] = field(default_factory=list)
    name: str | None = None
    owner_label: str | None = field(default=None, repr=False)


@dataclass
class RowLayout:
    """The ordered slot storage for one explicit horizontal composition."""

    columns: int
    children: list[LayoutBlock | StackLayout] = field(default_factory=list)
    name: str | None = None
    owner_label: str | None = field(default=None, repr=False)


@dataclass
class SectionLayout:
    """The ordered children storage for one titled report section."""

    title: str | None
    children: list[GridLayout | RowLayout | StackLayout | LayoutBlock | HeadingLayout] = field(default_factory=list)


@dataclass
class ReportLayout:
    """The ordered top-level storage for a report."""

    title: str
    children: list[SectionLayout | GridLayout | RowLayout | StackLayout | LayoutBlock | HeadingLayout] = field(
        default_factory=list
    )


LayoutNode: TypeAlias = SectionLayout | GridLayout | RowLayout | StackLayout | LayoutBlock | HeadingLayout
