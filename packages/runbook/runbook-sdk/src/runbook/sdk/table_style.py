from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Mapping, TypeAlias, TypedDict

import pandas as pd
from runbook.core.table.builder import (
    render_table_html as _render_table_html,
)
from runbook.core.table.builder import (
    table_style_hash as _table_style_hash,
)
from runbook.core.table.builder import (
    table_style_payload as _table_style_payload,
)
from runbook.core.table.models import (
    TABLE_STYLE_SCHEMA_VERSION,
    StyleInput,
    TableAction,
    TableColumnSizing,
    TableCondition,
    TableFormatSpec,
    TableLink,
    TableRowRef,
    TableRowSizing,
    TableRule,
    TableTarget,
)


class NumberFormatSpecInput(TypedDict):
    kind: Literal["number"]
    digits: int
    thousands: bool


class PercentFormatSpecInput(TypedDict):
    kind: Literal["percent"]
    digits: int


class DateFormatSpecInput(TypedDict):
    kind: Literal["date"]
    pattern: str


class StringFormatSpecInput(TypedDict):
    kind: Literal["string"]


FormatSpecInput: TypeAlias = (
    TableFormatSpec | NumberFormatSpecInput | PercentFormatSpecInput | DateFormatSpecInput | StringFormatSpecInput
)


class TableFormatEntry(TypedDict):
    column: str
    spec: FormatSpecInput


class TableRowRefInput(TypedDict):
    mode: Literal["label", "position"]
    value: Any


class ColumnSizingEntry(TypedDict):
    kind: Literal["column"]
    label: str
    width_px: int


class RowSizingEntry(TypedDict):
    kind: Literal["row"]
    row_ref: TableRowRef | TableRowRefInput
    width_px: int


TableSizingEntry: TypeAlias = TableColumnSizing | TableRowSizing | ColumnSizingEntry | RowSizingEntry
TableTargetInput: TypeAlias = TableTarget | Mapping[str, Any]
TableConditionInput: TypeAlias = TableCondition | Mapping[str, Any]
TableActionInput: TypeAlias = TableAction | Mapping[str, Any]
TableRuleInput: TypeAlias = TableRule | Mapping[str, Any]
TableLinkInput: TypeAlias = TableLink | Mapping[str, Any]


def format_number(column: str, digits: int = 2, thousands: bool = False) -> TableFormatEntry:
    """Format number."""
    return {
        "column": column,
        "spec": {
            "kind": "number",
            "digits": digits,
            "thousands": thousands,
        },
    }


def format_percent(column: str, digits: int = 2) -> TableFormatEntry:
    """Format percent."""
    return {
        "column": column,
        "spec": {
            "kind": "percent",
            "digits": digits,
        },
    }


def format_date(column: str, pattern: str) -> TableFormatEntry:
    """Format date."""
    return {
        "column": column,
        "spec": {
            "kind": "date",
            "pattern": pattern,
        },
    }


def column_width(label: str, width_px: int) -> ColumnSizingEntry:
    """Handle column width."""
    return {
        "kind": "column",
        "label": label,
        "width_px": width_px,
    }


def row_width_label(label: str, width_px: int) -> RowSizingEntry:
    """Handle row width label."""
    return {
        "kind": "row",
        "row_ref": {"mode": "label", "value": label},
        "width_px": width_px,
    }


def row_width_position(position: int, width_px: int) -> RowSizingEntry:
    """Handle row width position."""
    return {
        "kind": "row",
        "row_ref": {"mode": "position", "value": position},
        "width_px": width_px,
    }


def target_all() -> dict[str, Any]:
    """Handle target all."""
    return {"scope": "all"}


def target_columns(labels: Sequence[str]) -> dict[str, Any]:
    """Handle target columns."""
    return {"scope": "columns", "labels": list(labels)}


def target_column_positions(positions: Sequence[int]) -> dict[str, Any]:
    """Handle target column positions."""
    return {"scope": "columns", "positions": list(positions)}


def target_rows(labels: Sequence[str]) -> dict[str, Any]:
    """Handle target rows."""
    return {"scope": "rows", "labels": list(labels)}


def rhs_literal(value: Any) -> dict[str, Any]:
    """Handle rhs literal."""
    return {"kind": "literal", "value": value}


def rhs_column(label: str) -> dict[str, Any]:
    """Handle rhs column."""
    return {"kind": "column", "label": label}


def rhs_row_label(label: str) -> dict[str, Any]:
    """Handle rhs row label."""
    return {"kind": "row", "row_ref": {"mode": "label", "value": label}}


def rhs_row_position(position: int) -> dict[str, Any]:
    """Handle rhs row position."""
    return {"kind": "row", "row_ref": {"mode": "position", "value": position}}


def rhs_zscore(mean_column: str, std_column: str, num_std: float = 1.0) -> dict[str, Any]:
    """Handle rhs zscore."""
    return {
        "kind": "zscore",
        "mean_column": mean_column,
        "std_column": std_column,
        "num_std": num_std,
    }


def condition(
    op: str = "always",
    rhs: Mapping[str, Any] | None = None,
    *,
    lhs_column: str | None = None,
    all_of: Sequence[Mapping[str, Any]] | None = None,
    any_of: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Handle condition."""
    payload: dict[str, Any] = {"op": op}
    if rhs is not None:
        payload["rhs"] = dict(rhs)
    if lhs_column is not None:
        payload["lhs_column"] = lhs_column
    if all_of is not None:
        payload["all_of"] = [dict(item) for item in all_of]
    if any_of is not None:
        payload["any_of"] = [dict(item) for item in any_of]
    return payload


def action(
    *,
    background_color: str | None = None,
    text_color: str | None = None,
    font_weight: str | None = None,
    font_style: str | None = None,
    text_align: str | None = None,
    bottom_border: bool | None = None,
    border_top: str | None = None,
    border_right: str | None = None,
    border_bottom: str | None = None,
    border_left: str | None = None,
) -> dict[str, Any]:
    """Handle action."""
    payload: dict[str, Any] = {}
    if background_color is not None:
        payload["background_color"] = background_color
    if text_color is not None:
        payload["text_color"] = text_color
    if font_weight is not None:
        payload["font_weight"] = font_weight
    if font_style is not None:
        payload["font_style"] = font_style
    if text_align is not None:
        payload["text_align"] = text_align
    if bottom_border is not None:
        payload["bottom_border"] = bottom_border
    if border_top is not None:
        payload["border_top"] = border_top
    if border_right is not None:
        payload["border_right"] = border_right
    if border_bottom is not None:
        payload["border_bottom"] = border_bottom
    if border_left is not None:
        payload["border_left"] = border_left
    return payload


def rule(
    rule_id: str,
    target: TableTargetInput,
    condition: TableConditionInput | None = None,
    action: TableActionInput | None = None,
) -> dict[str, Any]:
    """Handle rule."""
    if action is None:
        raise ValueError("rule action must be provided")
    condition_payload = {"op": "always"} if condition is None else dict(condition)
    return {
        "id": rule_id,
        "target": dict(target),
        "condition": condition_payload,
        "action": dict(action),
    }


def highlight_z_rules(
    *,
    target_column: str,
    mean_column: str,
    std_column: str,
    num_std: float = 1.0,
    above_action: TableActionInput,
    below_action: TableActionInput,
    rule_id_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Handle highlight z rules."""
    prefix = target_column if rule_id_prefix is None else rule_id_prefix
    rhs = rhs_zscore(mean_column=mean_column, std_column=std_column, num_std=num_std)
    return [
        rule(
            rule_id=f"{prefix}_z_gt",
            target=target_columns([target_column]),
            condition=condition("z_gt", rhs=rhs),
            action=above_action,
        ),
        rule(
            rule_id=f"{prefix}_z_lt",
            target=target_columns([target_column]),
            condition=condition("z_lt", rhs=rhs),
            action=below_action,
        ),
    ]


def legacy_zscore_band_rules(
    *,
    target_column: str,
    mean_column: str,
    std_column: str,
    rule_id_prefix: str | None = None,
    two_sigma_up_color: str = "green",
    one_sigma_up_color: str = "lightgreen",
    one_sigma_down_color: str = "#FFA94D",
    two_sigma_down_color: str = "#FF8787",
) -> list[dict[str, Any]]:
    """Build legacy-equivalent z-score band highlight rules.

    Rule order is weak->strong so strong bands override weak ones.
    """
    prefix = target_column if rule_id_prefix is None else rule_id_prefix
    return [
        rule(
            rule_id=f"{prefix}_z_gt_1",
            target=target_columns([target_column]),
            condition=condition(
                "z_gt",
                rhs=rhs_zscore(mean_column=mean_column, std_column=std_column, num_std=1.0),
            ),
            action=action(background_color=one_sigma_up_color),
        ),
        rule(
            rule_id=f"{prefix}_z_gt_2",
            target=target_columns([target_column]),
            condition=condition(
                "z_gt",
                rhs=rhs_zscore(mean_column=mean_column, std_column=std_column, num_std=2.0),
            ),
            action=action(background_color=two_sigma_up_color),
        ),
        rule(
            rule_id=f"{prefix}_z_lt_1",
            target=target_columns([target_column]),
            condition=condition(
                "z_lt",
                rhs=rhs_zscore(mean_column=mean_column, std_column=std_column, num_std=1.0),
            ),
            action=action(background_color=one_sigma_down_color),
        ),
        rule(
            rule_id=f"{prefix}_z_lt_2",
            target=target_columns([target_column]),
            condition=condition(
                "z_lt",
                rhs=rhs_zscore(mean_column=mean_column, std_column=std_column, num_std=2.0),
            ),
            action=action(background_color=two_sigma_down_color),
        ),
    ]


def table_style(
    *,
    key: str | None = None,
    formats: Sequence[TableFormatEntry] | None = None,
    sizing: Sequence[TableSizingEntry] | None = None,
    rules: Sequence[TableRuleInput] | None = None,
    max_rows: int = 100,
    na_rep: str | None = None,
    show_index: bool = True,
    links: Sequence[TableLinkInput] | None = None,
) -> dict[str, Any]:
    """Handle table style."""
    payload: dict[str, Any] = {
        "schema_version": TABLE_STYLE_SCHEMA_VERSION,
        "options": {"max_rows": max_rows, "show_index": show_index},
    }
    if key is not None:
        payload["style_key"] = key

    format_columns: dict[str, Any] = {}
    for fmt in formats or []:
        column = fmt.get("column")
        spec = fmt.get("spec")
        if not isinstance(column, str) or not column:
            raise ValueError("format entry must include non-empty 'column'")
        if not isinstance(spec, Mapping):
            raise ValueError(f"format entry for column={column!r} must include 'spec' mapping")
        format_columns[column] = dict(spec)
    if format_columns or na_rep is not None:
        format_payload: dict[str, Any] = {}
        if na_rep is not None:
            format_payload["na_rep"] = na_rep
        if format_columns:
            format_payload["columns"] = format_columns
        payload["format"] = format_payload

    column_sizes: list[dict[str, Any]] = []
    row_sizes: list[dict[str, Any]] = []
    for size in sizing or []:
        kind = size.get("kind")
        if kind == "column":
            label = size.get("label")
            width_px = size.get("width_px")
            if not isinstance(label, str) or not label:
                raise ValueError("column sizing entry must include non-empty 'label'")
            if not isinstance(width_px, int):
                raise ValueError("column sizing entry must include integer 'width_px'")
            column_sizes.append({"label": label, "width_px": width_px})
            continue
        if kind == "row":
            row_ref = size.get("row_ref")
            width_px = size.get("width_px")
            if not isinstance(row_ref, Mapping):
                raise ValueError("row sizing entry must include 'row_ref' mapping")
            if not isinstance(width_px, int):
                raise ValueError("row sizing entry must include integer 'width_px'")
            row_sizes.append({"row_ref": dict(row_ref), "width_px": width_px})
            continue
        raise ValueError(f"unsupported sizing kind: {kind!r}")
    if column_sizes or row_sizes:
        payload["sizing"] = {"columns": column_sizes, "rows": row_sizes}

    if rules:
        payload["rules"] = [dict(r) for r in rules]

    if links:
        payload["links"] = [
            item.model_dump(mode="python") if isinstance(item, TableLink) else dict(item) for item in links
        ]

    return payload


def table_style_payload(
    style: StyleInput | None,
    *,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Handle table style payload."""
    return _table_style_payload(style, style_key=style_key, max_rows=max_rows)


def table_style_hash(
    style: StyleInput | None,
    *,
    style_key: str | None = None,
    max_rows: int | None = None,
) -> str:
    """Handle table style hash."""
    return _table_style_hash(style, style_key=style_key, max_rows=max_rows)


def render_table_html(
    df: pd.DataFrame,
    style: StyleInput | None = None,
    *,
    style_df: pd.DataFrame | None = None,
    style_key: str | None = None,
    max_rows: int | None = None,
    table_class: str = "rb-table",
) -> str:
    """Render table html."""
    return _render_table_html(
        df,
        style,
        style_df=style_df,
        style_key=style_key,
        max_rows=max_rows,
        table_class=table_class,
    )


__all__ = [
    "action",
    "column_width",
    "condition",
    "format_date",
    "format_number",
    "format_percent",
    "legacy_zscore_band_rules",
    "render_table_html",
    "highlight_z_rules",
    "rhs_column",
    "rhs_literal",
    "rhs_row_label",
    "rhs_row_position",
    "rhs_zscore",
    "row_width_label",
    "row_width_position",
    "rule",
    "table_style",
    "table_style_hash",
    "table_style_payload",
    "target_all",
    "target_column_positions",
    "target_columns",
    "target_rows",
]
