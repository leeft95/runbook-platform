"""COT tables reuse the shared formats, rules, and semantic plot links."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from ..models import (
    TableAction,
    TableColumnSizing,
    TableFormatNumber,
    TableFormatPercent,
    TableFormatSpec,
    TableFormatString,
    TableLink,
    TableLinkDestination,
    TableLinkKind,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    TableTarget,
    TargetScope,
    validate_link_url,
)
from .common import _select_highlight_columns, color_negative_red, highlight


def cot_summary_table(
    summary: pd.DataFrame,
    header: str = "COT",
    *,
    label_column: str = "Asset",
    position_column: str = "Net Position",
    position_label: str | None = None,
    internal_change_label: str = "Internal Change",
    group_column: str | None = None,
    plot_links: Mapping[str, str] | str | None = None,
    highlight_columns: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Style full or filtered ``cot_summary`` rows, retaining numeric semantics.

    ``label_column`` and ``position_column`` accept existing ECM summary names
    without recalculating the data. Use ``position_label`` to optionally rename
    the displayed net-position column for managed money, dealers or funds.
    Legacy ``CTA Change`` summaries display as ``Internal Change``; override
    ``internal_change_label`` when the model's final name is known.
    Optional noncommercial positions are displayed next to the asset name.
    ``group_column`` adds a separator after each contiguous instrument group;
    it is hidden along with calculation helpers. ``plot_links`` maps asset
    labels to existing named plot artifacts or custom URLs/relative report
    pages. A single string links every asset to that page. Bare mapping values
    remain plot names; values containing /, ., ?, # or : are page URLs.
    Legacy ``plots/name.json`` artifact references retain plot routing.
    ``highlight_columns`` selects coloured columns; [] disables highlights,
    retaining red negative values. No files
    are written, and the source summary is not modified.
    """
    if not summary.columns.is_unique or not all(isinstance(col, str) for col in summary.columns):
        raise ValueError("summary requires unique string column names")
    if label_column not in summary or position_column not in summary or label_column == position_column:
        raise ValueError("summary requires distinct label and net-position columns")
    position_label = position_column if position_label is None else position_label
    if not header.strip() or not position_label.strip() or not internal_change_label.strip():
        raise ValueError("header, position_label and internal_change_label must not be blank")
    if position_label != position_column and position_label in summary.columns:
        raise ValueError("position_label must not collide with another summary column")
    frame = summary.copy().reset_index(drop=True)
    if group_column is not None and (group_column not in frame or group_column in {label_column, position_column}):
        raise ValueError("group_column must name a separate existing column")
    columns = [
        label_column,
        *(["Net Position (NC)"] if "Net Position (NC)" in frame and position_column != "Net Position (NC)" else []),
    ]
    frame = frame[columns + [col for col in frame if col not in columns]]
    frame = frame.rename(columns={position_column: position_label})
    internal_column = "Internal Change" if "Internal Change" in frame else "CTA Change"
    if internal_column in frame:
        if internal_change_label != internal_column and internal_change_label in frame:
            raise ValueError("internal_change_label must not collide with another summary column")
        frame = frame.rename(columns={internal_column: internal_change_label})
    hidden = [
        col
        for col in frame
        if col.startswith("_") or col in {"net pos rank", "net/oi pct rank", "YTD price change", group_column}
    ]
    links = None
    if plot_links is not None:
        targets = dict.fromkeys(frame[label_column], plot_links) if isinstance(plot_links, str) else plot_links
        if isinstance(plot_links, str):
            validate_link_url(plot_links)
        unknown = set(targets) - set(frame[label_column])
        if unknown:
            raise ValueError(f"Unknown linked assets: {sorted(unknown)}")
        destinations: dict[TableLinkKind, dict[str, str]] = {}
        for asset, name in targets.items():
            kind = (
                TableLinkKind.url
                if isinstance(plot_links, str)
                or (
                    any(char in name for char in "/.?#:") and not (name.startswith("plots/") and name.endswith(".json"))
                )
                else TableLinkKind.plot
            )
            if kind == TableLinkKind.url:
                validate_link_url(name)
            TableLinkDestination(kind=kind, value=name)
            destinations.setdefault(kind, {})[asset] = name
        links = []
        for kind, target_values in destinations.items():
            field = f"_{kind.value}_link"
            frame[field] = frame[label_column].map(target_values)
            hidden.append(field)
            links.append(
                TableLink(
                    area="cells",
                    field=label_column,
                    destination=TableLinkDestination(kind=kind, value_field=field),
                )
            )
    visible = [col for col in frame if col not in hidden]
    highlighted = _select_highlight_columns(visible, highlight_columns)
    percents = {
        "% OI",
        "Weekly Price Change",
        "4w change of price",
        "Net percentile",
        "Net/OI percentile",
        "Long percentile",
        "Short percentile",
    }
    decimals = {
        "Ref Week VWAP",
        internal_change_label,
        "Long Short Ratio",
        "net change z score",
        "4w price change z score",
        "4w delta change z score",
    }
    formats: dict[str, TableFormatSpec] = {
        col: TableFormatString()
        if col == label_column
        else TableFormatPercent(digits=1)
        if col in percents
        else TableFormatNumber(digits=2 if col in decimals else 0, thousands=True)
        for col in visible
    }
    bold = [
        col
        for col in ("Weekly Price Change", "Weekly Delta Change", "4w change of price", "4w change of net position")
        if col in frame
    ]
    rules = [
        TableRule(
            id="cot_align",
            target=TableTarget(scope=TargetScope.columns, labels=visible),
            action=TableAction(text_align="center"),
        ),
    ]
    if bold:
        rules.append(
            TableRule(
                id="cot_bold",
                target=TableTarget(scope=TargetScope.columns, labels=bold),
                action=TableAction(font_weight="bold"),
            )
        )
    rules.extend(color_negative_red(list(frame.columns), [(col, col) for col in visible if col != label_column]))
    rules.extend(
        highlight(
            list(frame.columns),
            [
                target
                for target in [
                    (label_column, "net pos rank", "_thr_high", "_thr_low"),
                    ("% OI", "net/oi pct rank", "_thr_high", "_thr_low"),
                    ("Weekly Price Change", "_price_chg", "_thr_high", "_thr_low"),
                    ("Weekly Delta Change", "net change z score", "_z_high", "_z_low"),
                    ("4w change of price", "4w price change z score", "_z_high", "_z_low"),
                    ("4w change of net position", "4w delta change z score", "_z_high", "_z_low"),
                    ("Net percentile", "_thr_net"),
                    ("Net/OI percentile", "_thr_net"),
                    ("Long percentile", "_thr_high8", "_thr_low8"),
                    ("Short percentile", "_thr_high8", "_thr_low8"),
                ]
                if target[0] in highlighted
            ],
        )
    )
    separators = [
        col
        for col in (
            label_column,
            "Ref Week VWAP",
            "Weekly Delta Change in millions",
            "Weekly Delta Change in $m",
            "Weekly Delta Change in $/EUR m",
            "Weekly OI change",
            "Short percentile",
        )
        if col in frame
    ]
    rules.append(
        TableRule(
            id="cot_column_groups",
            target=TableTarget(scope=TargetScope.columns, labels=separators),
            action=TableAction(border_right="1px solid black"),
        )
    )
    if group_column is not None and len(frame):
        groups = frame[group_column]
        positions = groups.ne(groups.shift(-1)).fillna(True).iloc[:-1].to_numpy().nonzero()[0].tolist()
        if positions:
            rules.append(
                TableRule(
                    id="cot_row_groups",
                    target=TableTarget(scope=TargetScope.rows, positions=positions),
                    action=TableAction(bottom_border=True),
                )
            )
    style = TableStylePlan(
        format=TableStyleFormat(na_rep="-", columns=formats),
        sizing=TableSizing(
            columns=[
                TableColumnSizing(
                    label=col,
                    width_px=120
                    if col == label_column
                    else 80
                    if col in {"Long Position", "Net percentile", "Net/OI percentile", "Short percentile"}
                    else 60,
                )
                for col in visible
            ]
        ),
        rules=rules,
        options=TableStyleOptions(show_index=False, hidden_columns=hidden, max_rows=max(1, len(frame))),
        links=links,
    )
    return {header: {"data": frame, "style": style.model_dump(mode="python", exclude_none=True), "plots": []}}


# Compatibility with the v0.3.2.2 public name.
cot_table = cot_summary_table
