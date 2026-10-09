"""Calendar roll-ups with linked base-history and seasonal-average charts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pandas as pd

from ...plotting.templates import plot_rollup_seasonal
from ...timeseries.rollup import _calendar_offset, calendar_moving_average
from ..builder import _default_numeric_formats
from ..models import (
    TableAction,
    TableColumnSizing,
    TableFormatSpec,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    TableTarget,
    TargetScope,
    parse_python_format_string,
)
from .common import _build_plot_link_metadata, _select_highlight_columns, color_negative_red, highlight_zscore
from .table_with_link_monthly import _normalize_input_frame


def rollup_table_hst(
    data: pd.DataFrame,
    params: Sequence[str] | None = None,
    header: str = "Roll-up",
    *,
    as_of: str | pd.Timestamp | None = None,
    exclude_years: Sequence[int] = (),
    format_spec: TableFormatSpec | str | None = None,
    total_label: str | None = None,
    include_total: bool = True,
    row_plot_links: bool | list[str] | str = True,
    all_plots_link: bool | str = True,
    highlight_columns: Sequence[str] | None = None,
    use_highlighting: Sequence[str] | None = None,
    std_limits: tuple[float, float] = (1.0, 2.0),
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

    By default, append a Total row summing each displayed column (skipping
    missing values; all-missing columns stay missing). If an input column
    matches ``total_label`` (None means "Total"), use that precomputed series
    instead and move it to the last row. The total is bold with a top border.
    ``include_total=False`` omits either total and its companion plots.
    A custom label without a matching input column names the calculated total.

    Each row links to full base history plus seasonal base/MA panels. The index
    heading links to all figures. ``plot_options`` goes to ``plot_rollup_seasonal``;
    historical summary columns reuse their base window's seasonal panel.
    String link options target an absolute URL or relative report page;
    booleans retain the generated-plot links or disable them.
    Each selected column is scored against its own history. Latest uses the
    trailing 20-calendar-day observations; an MA uses the trailing 20 calendar
    days of that rolling-average series. Y-N uses that MA history at the prior
    date; NY uses the history of the equal-weight prior-year average. Thus
    Latest and 20d MA are independent short-term and smoothed trend signals.
    ``use_highlighting=None`` defaults to Latest and 20d MA, when present.
    A list can select any displayed column; [] disables bands. The earlier
    ``highlight_columns`` spelling remains supported; ``use_highlighting``
    takes precedence when supplied.
    ``std_limits`` sets the mild/strong thresholds symmetrically above and
    below the mean, defaulting to (1, 2) standard deviations for selected columns.
    Highlights use numeric values independently of display format; missing or
    zero dispersion leaves a cell without z-score highlighting.
    Use ``format_spec='{:.1%}'`` for shares and ``rules`` for domain overrides.
    By default, integer output columns use 0 decimals and float columns use 2.
    Formatting does not round the underlying values or highlighting statistics.
    Returns the ordinary named data/style/plots payload, with numeric values.
    """
    frame = _normalize_input_frame(data, columns_filter=None, fill_na=None, as_of=as_of)
    anchor = data.index[data.index.isin(frame.index)][-1]
    return _rollup_table(
        frame.loc[frame.index <= anchor],
        anchor,
        params,
        header,
        exclude_years=exclude_years,
        format_spec=format_spec,
        total_label=total_label,
        include_total=include_total,
        row_plot_links=row_plot_links,
        all_plots_link=all_plots_link,
        highlight_columns=highlight_columns,
        use_highlighting=use_highlighting,
        std_limits=std_limits,
        rules=rules,
        footer=footer,
        plot_options=plot_options,
    )


def rollup_table_fcst(
    df: pd.DataFrame,
    df_hst: pd.DataFrame | None = None,
    params: Sequence[str] | None = None,
    header: str = "Roll-up",
    *,
    today: str | pd.Timestamp | None = None,
    std_limits: tuple[float, float] = (1.0, 2.0),
    include_total: bool = True,
    highlight_columns: Sequence[str] | None = None,
    use_highlighting: Sequence[str] | None = None,
    **options: Any,
) -> dict[str, dict[str, Any]]:
    """Roll forecast averages alongside the latest historical observations.

    Default columns are Current Month, Latest, 5d MA, 20d MA, 3m MA,
    Y-1 20d MA and 5Y 20d MA. Averages always use ``df``. When populated,
    ``df_hst`` supplies Latest values from its final supplied row, matched to
    ``df`` columns by name, and that row's date anchors every MA window.
    Without history, today's date anchors the windows and Latest reads that
    exact row in ``df``. Missing dates, columns and values remain missing.

    Current Month averages all supplied observations in today's calendar month,
    including future dates, independently of the Latest date. ``today`` pins
    the calendar date for reproducible reports; None uses ``datetime.today()``.
    Dates are interpreted in ``df``'s timezone. Linked charts retain the full
    supplied time series.

    ``std_limits`` and other presentation options work as in ``rollup_table_hst``.
    Highlighting defaults to Latest and 20d MA, when present. ``use_highlighting``
    can select any displayed column, including Current Month, or [] to disable
    coloured bands. Current Month uses the last 20 calendar months of monthly
    averages, including the current month; Latest and MAs use their own series'
    trailing 20-calendar-day reference windows, anchored to the Latest date.
    Latest uses ``df_hst`` for its reference when supplied, otherwise ``df``.
    ``highlight_columns`` remains supported; red negatives are independent.
    String link options target custom pages.
    Totals work as in ``rollup_table_hst``: sum the displayed columns, or use
    the input series matching ``total_label`` and place it last.
    ``include_total=False`` omits the total from the table and linked plots.
    """
    frame = _normalize_input_frame(df, columns_filter=None, fill_na=None)
    current_date = _rollup_date(datetime.today() if today is None else today, frame.index).normalize()
    if df_hst is not None and not isinstance(df_hst, pd.DataFrame):
        raise TypeError("df_hst must be a DataFrame or None")
    anchor = current_date
    latest_history = None
    if df_hst is not None and not df_hst.empty:
        if not isinstance(df_hst.index, pd.DatetimeIndex) or df_hst.index.hasnans:
            raise ValueError("df_hst must have a DatetimeIndex without NaT")
        anchor = _rollup_date(df_hst.index[-1], frame.index)
        latest_history = _normalize_input_frame(df_hst, columns_filter=None, fill_na=None)
        if frame.index.tz is not None:
            latest_history.index = (
                latest_history.index.tz_localize(frame.index.tz)
                if latest_history.index.tz is None
                else latest_history.index.tz_convert(frame.index.tz)
            )
    return _rollup_table(
        frame,
        anchor,
        params,
        header,
        current_month=current_date,
        latest_history=latest_history,
        std_limits=std_limits,
        include_total=include_total,
        highlight_columns=highlight_columns,
        use_highlighting=use_highlighting,
        **options,
    )


def _rollup_date(value: str | pd.Timestamp, index: pd.DatetimeIndex) -> pd.Timestamp:
    """Resolve a calendar/anchor date in the input time series' timezone."""
    date = pd.Timestamp(value)
    if pd.isna(date):
        raise ValueError("roll-up dates must not be NaT")
    if index.tz is not None:
        return date.tz_localize(index.tz) if date.tzinfo is None else date.tz_convert(index.tz)
    if date.tzinfo is not None:
        raise ValueError("roll-up dates must be timezone-naive when df has a timezone-naive index")
    return date


def _rollup_table(
    frame: pd.DataFrame,
    anchor: pd.Timestamp,
    params: Sequence[str] | None,
    header: str,
    *,
    current_month: pd.Timestamp | None = None,
    latest_history: pd.DataFrame | None = None,
    exclude_years: Sequence[int] = (),
    format_spec: TableFormatSpec | str | None = None,
    total_label: str | None = None,
    include_total: bool = True,
    row_plot_links: bool | list[str] | str = True,
    all_plots_link: bool | str = True,
    highlight_columns: Sequence[str] | None = None,
    use_highlighting: Sequence[str] | None = None,
    std_limits: tuple[float, float] = (1.0, 2.0),
    rules: Sequence[TableRule] = (),
    footer: str | None = None,
    plot_options: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build shared calendar statistics, highlights and linked roll-up plots."""
    if not header.strip():
        raise ValueError("header must not be blank")
    if params is None:
        params = ("Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA")
        if current_month is not None:
            params = ("Current Month", *params)
    if isinstance(params, str) or not params or any(not isinstance(label, str) for label in params):
        raise ValueError("params must be a non-empty sequence of roll-up column names")
    if len({label.strip().casefold() for label in params}) != len(params):
        raise ValueError("params must contain distinct column names")
    selected = use_highlighting if use_highlighting is not None else highlight_columns
    if selected is None:
        selected = [label for label in params if label.strip().casefold() in {"latest", "20d ma"}]
    highlighted = _select_highlight_columns(list(params), selected)
    frame = frame.apply(pd.to_numeric, errors="raise")
    total_label = "Total" if total_label is None else total_label
    if not total_label.strip():
        raise ValueError("total_label must not be blank")
    calculate_total = include_total and total_label not in frame
    if include_total:
        total = frame.pop(total_label) if total_label in frame else frame.sum(axis=1, min_count=1)
        frame[total_label] = total
    else:
        frame = frame.drop(columns=total_label, errors="ignore")
        if isinstance(row_plot_links, list):
            row_plot_links = [column for column in row_plot_links if column != total_label]
        total_label = None
    values: dict[str, pd.Series] = {}
    windows: list[str] = []
    benchmarks: dict[str, tuple[pd.Series, pd.Series]] = {}
    rolling_history: dict[str, pd.DataFrame] = {}
    latest_frame = frame
    if latest_history is not None:
        latest_frame = latest_history.reindex(columns=frame.columns).apply(pd.to_numeric, errors="raise")
        if include_total and total_label not in latest_history:
            latest_frame[total_label] = latest_frame.drop(columns=total_label).sum(axis=1, min_count=1)
    latest = latest_frame.reindex([anchor]).iloc[0]

    def sample_at(window: str, date: pd.Timestamp) -> pd.DataFrame:
        """Select observations in a calendar window, including its end date."""
        return frame.loc[(frame.index > date - _calendar_offset(window)) & (frame.index <= date)]

    def reference(
        history: pd.DataFrame, date: pd.Timestamp, *, monthly: bool = False, sum_components: bool = True
    ) -> tuple[pd.Series, pd.Series]:
        """Score each column against its own recent observations, including totals."""
        offset = pd.DateOffset(months=20) if monthly else pd.DateOffset(days=20)
        sample = history.loc[(history.index > date - offset) & (history.index <= date)].copy()
        if calculate_total and sum_components:
            sample[total_label] = sample.drop(columns=total_label).sum(axis=1, min_count=1)
        return sample.mean(), sample.std()

    for label in params:
        if label.strip().casefold() == "latest":
            values[label] = latest
            if label in highlighted:
                benchmarks[label] = reference(latest_frame, anchor, sum_components=False)
            continue
        if current_month is not None and label.strip().casefold() == "current month":
            month_start = current_month.replace(day=1)
            sample = frame.loc[(frame.index >= month_start) & (frame.index < month_start + pd.DateOffset(months=1))]
            values[label] = sample.mean()
            if label in highlighted:
                benchmarks[label] = reference(frame.resample("MS").mean(), month_start, monthly=True)
            continue
        match = re.fullmatch(r"(?:(Y-[1-9]\d*|[1-9]\d*Y)\s+)?([1-9]\d*[dm])\s+MA", label.strip(), re.IGNORECASE)
        if match is None:
            raise ValueError(f"Unsupported roll-up column: {label!r}")
        history, window = match[1], match[2].lower()
        if window not in windows:
            windows.append(window)
        if history is None:
            sample = sample_at(window, anchor)
            values[label] = sample.mean()
        else:
            history = history.upper()
            years = [int(history[2:])] if history.startswith("Y-") else range(1, int(history[:-1]) + 1)
            samples = [
                sample_at(window, anchor - pd.DateOffset(years=year))
                for year in years
                if anchor.year - year not in exclude_years
            ]
            annual_means = pd.DataFrame([sample.mean() for sample in samples], columns=frame.columns)
            values[label] = annual_means.mean()
        if label in highlighted:
            if history is None or history.startswith("Y-"):
                if window not in rolling_history:
                    rolling_history[window] = calendar_moving_average(frame, window)
                reference_date = anchor if history is None else anchor - pd.DateOffset(years=int(history[2:]))
                benchmarks[label] = reference(rolling_history[window], reference_date)
            else:
                # Reconstruct this same prior-year average at recent observation
                # dates, rather than scoring it against today's raw level.
                dates = sample_at("20d", anchor).index
                historical = pd.DataFrame(
                    [
                        pd.DataFrame(
                            [
                                sample_at(window, date - pd.DateOffset(years=year)).mean()
                                for year in range(1, int(history[:-1]) + 1)
                                if date.year - year not in exclude_years
                            ],
                            columns=frame.columns,
                        ).mean()
                        for date in dates
                    ],
                    index=dates,
                    columns=frame.columns,
                )
                benchmarks[label] = reference(historical, anchor)
    if calculate_total:
        # Sum the displayed aggregates: averaging summed observations would
        # give different answers when components have different missing dates.
        for label, series in values.items():
            # Latest already has its own supplied or calculated history total.
            if label.strip().casefold() != "latest":
                series.loc[total_label] = series.drop(total_label).sum(min_count=1)
    result = pd.DataFrame(values)
    result.index.name = header
    hidden: list[str] = []
    targets: list[tuple[str, str, str, str]] = []
    for i, label in enumerate(highlighted):
        mean, std = f"_rollup_{i}_mean", f"_rollup_{i}_std"
        reference_mean, reference_std = benchmarks[label]
        result[mean], result[std] = reference_mean, reference_std.where(reference_std > 0)
        hidden.extend([mean, std])
        targets.append((label, label, mean, std))
    columns = list(result.columns)
    style_rules = color_negative_red(columns, [(label, label) for label in params])
    style_rules.extend(highlight_zscore(columns, targets, std_limits=std_limits))
    if total_label is not None:
        style_rules.append(
            TableRule(
                id="rollup_total",
                target=TableTarget(scope=TargetScope.rows, positions=[len(result) - 1]),
                action=TableAction(font_weight="bold", border_top="1px solid #000000"),
            )
        )
    style_rules.extend(rules)
    plot_names, links, all_plots_name = _build_plot_link_metadata(
        header,
        [(column, "rollup-seasonal") for column in frame],
        list(frame.columns),
        column_plot_links=row_plot_links,
        all_plots_link=all_plots_link if len(frame.columns) > 0 else False,
        link_area="index",
    )
    spec = parse_python_format_string(format_spec) if isinstance(format_spec, str) else format_spec
    formats = (
        {label: spec for label in params}
        if spec is not None
        else _default_numeric_formats(result[list(params)], thousands=True)
    )
    plan = TableStylePlan(
        format=TableStyleFormat(na_rep="-", columns=formats),
        sizing=TableSizing(
            index_width_px=180, columns=[TableColumnSizing(label=label, width_px=95) for label in params]
        ),
        rules=style_rules,
        options=TableStyleOptions(
            max_rows=max(1, len(result)),
            hidden_columns=hidden,
            footer=footer,
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
