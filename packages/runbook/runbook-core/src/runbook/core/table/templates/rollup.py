"""Calendar roll-ups with linked base-history and seasonal-average charts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import pandas as pd

from ...plotting.templates import plot_rollup_seasonal
from ...timeseries.rollup import _calendar_offset
from ..models import (
    TableColumnSizing,
    TableFormatSpec,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    parse_python_format_string,
)
from .common import _build_plot_link_metadata, color_negative_red, highlight_zscore
from .table_with_link_monthly import _normalize_input_frame


def rollup_table_hst(
    data: pd.DataFrame,
    params: Sequence[str] | None = None,
    header: str = "Roll-up",
    *,
    as_of: str | pd.Timestamp | None = None,
    exclude_years: Sequence[int] = (),
    format_spec: TableFormatSpec | str = "{:,.0f}",
    row_plot_links: bool | list[str] = True,
    all_plots_link: bool = True,
    highlight_columns: Sequence[str] | None = None,
    rules: Sequence[TableRule] = (),
    footer: str | None = None,
    plot_options: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Roll one numeric time-series DataFrame into one row per input series.

    Default columns: Latest, 5d MA, 20d MA, 3m MA, Y-1 20d MA, 5Y 20d MA.
    ``params`` selects and orders columns; positive day/month lengths and
    historical year counts can be changed, e.g. ``10d MA`` or ``Y-2 3m MA``.

    All windows are calendar intervals (anchor - window, anchor], including
    across DST. The anchor is the final supplied row remaining after ``as_of``
    filtering, even for unsorted inputs; later-dated rows are then excluded.
    Latest uses that exact row, even when missing. Averages skip missing values
    without filling. Y-1 samples the corresponding date last year; 5Y equally
    averages available window means from the previous five calendar years,
    excluding ``exclude_years``. Missing years are not replaced with older ones.

    Each row links to full base history plus seasonal base/MA panels. The index
    heading links to all figures. ``plot_options`` goes to ``plot_rollup_seasonal``;
    historical summary columns reuse their base window's seasonal panel.
    The 20d MA column uses the general table's summary-band highlights: compare
    Latest with that calendar window's mean and sample standard deviation.
    ``highlight_columns`` selects other current MA columns; [] disables bands.
    Use ``format_spec='{:.1%}'`` for shares and ``rules`` for domain overrides.
    Returns the ordinary named data/style/plots payload, with numeric values.
    """
    if not header.strip():
        raise ValueError("header must not be blank")
    if params is None:
        params = ("Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA")
    if isinstance(params, str) or not params or any(not isinstance(label, str) for label in params):
        raise ValueError("params must be a non-empty sequence of roll-up column names")
    if len({label.strip().casefold() for label in params}) != len(params):
        raise ValueError("params must contain distinct column names")
    frame = _normalize_input_frame(data, columns_filter=None, fill_na=None, as_of=as_of)
    anchor = data.index[data.index.isin(frame.index)][-1]
    frame = frame.loc[frame.index <= anchor]
    frame = frame.apply(pd.to_numeric, errors="raise")
    values: dict[str, pd.Series] = {}
    windows: list[str] = []
    current_windows: dict[str, str] = {}

    def mean_at(window: str, date: pd.Timestamp) -> pd.Series:
        return frame.loc[(frame.index > date - _calendar_offset(window)) & (frame.index <= date)].mean()

    for label in params:
        if label.strip().casefold() == "latest":
            values[label] = frame.iloc[-1]
            continue
        match = re.fullmatch(r"(?:(Y-[1-9]\d*|[1-9]\d*Y)\s+)?([1-9]\d*[dm])\s+MA", label.strip(), re.IGNORECASE)
        if match is None:
            raise ValueError(f"Unsupported roll-up column: {label!r}")
        history, window = match[1], match[2].lower()
        if window not in windows:
            windows.append(window)
        if history is None:
            values[label] = mean_at(window, anchor)
            current_windows[label] = window
        else:
            history = history.upper()
            years = [int(history[2:])] if history.startswith("Y-") else range(1, int(history[:-1]) + 1)
            samples = [
                mean_at(window, anchor - pd.DateOffset(years=year))
                for year in years
                if anchor.year - year not in exclude_years
            ]
            values[label] = pd.DataFrame(samples, columns=frame.columns).mean()
    result = pd.DataFrame(values)
    result.index.name = header
    highlighted = (
        [label for label, window in current_windows.items() if window == "20d"]
        if highlight_columns is None
        else list(highlight_columns)
    )
    if set(highlighted) - current_windows.keys():
        raise ValueError("highlight_columns must select current moving-average columns")
    hidden: list[str] = []
    targets: list[tuple[str, str, str, str]] = []
    for i, label in enumerate(highlighted):
        signal, mean, std = f"_rollup_{i}_latest", f"_rollup_{i}_mean", f"_rollup_{i}_std"
        sample = frame.loc[frame.index > anchor - _calendar_offset(current_windows[label])]
        result[signal], result[mean], result[std] = frame.iloc[-1], result[label], sample.std()
        hidden.extend([signal, mean, std])
        targets.append((label, signal, mean, std))
    columns = list(result.columns)
    style_rules = color_negative_red(columns, [(label, label) for label in params])
    style_rules.extend(highlight_zscore(columns, targets))
    style_rules.extend(rules)
    plot_names, links, all_plots_name = _build_plot_link_metadata(
        header,
        [(column, "rollup-seasonal") for column in frame],
        list(frame.columns),
        column_plot_links=row_plot_links,
        all_plots_link=all_plots_link,
        link_area="index",
    )
    spec = parse_python_format_string(format_spec) if isinstance(format_spec, str) else format_spec
    plan = TableStylePlan(
        format=TableStyleFormat(na_rep="-", columns={label: spec for label in params}),
        sizing=TableSizing(
            index_width_px=180, columns=[TableColumnSizing(label=label, width_px=95) for label in params]
        ),
        rules=style_rules,
        options=TableStyleOptions(
            max_rows=max(1, len(result)),
            hidden_columns=hidden,
            footer=footer if footer is not None else f"Latest data: {anchor:%Y-%m-%d}",
        ),
        links=links,
    )
    figures = [
        plot_rollup_seasonal(
            frame[column], **{"windows": tuple(windows), "exclude_years": list(exclude_years), **(plot_options or {})}
        )
        for column in frame
    ]
    payload = {
        "data": result,
        "style": plan.model_dump(mode="python", exclude_none=True),
        "plots": figures,
        "plot_names": plot_names,
    }
    if all_plots_name is not None:
        payload["all_plots_name"] = all_plots_name
    return {header: payload}
