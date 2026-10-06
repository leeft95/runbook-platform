from __future__ import annotations

import typing as tp

import pandas as pd
import plotly.graph_objects as go

from ...plotting.seasonal import plot_seasonal
from ...timeseries.analysis import (
    AggregationModes,
    MovingAvgModes,
    _get_historical_data_on_date,
    calculate_historical_mean_std_for_date,
)
from ..models import (
    TableAction,
    TableColumnSizing,
    TableFormatNumber,
    TableFormatSpec,
    TableFormatString,
    TableGlobalStyle,
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
)
from .common import _aligned_moving_average, _build_plot_link_metadata, color_negative_red, highlight_zscore


def _month_end(ts: pd.Timestamp) -> pd.Timestamp:
    """Handle month end."""
    return ts + pd.offsets.MonthEnd(0)


def _parse_aggregation_mode(
    mode: AggregationModes | str | None,
) -> AggregationModes | None:
    """Parse aggregation mode."""
    if mode is None:
        return None
    if isinstance(mode, AggregationModes):
        return mode
    if isinstance(mode, str):
        if mode.strip().lower() in {"last", "level"}:
            return None
        try:
            return AggregationModes(mode)
        except ValueError as exc:
            raise ValueError(f"Unsupported aggregation type: {mode}") from exc
    raise ValueError(f"{mode} is unknown")


def _aggregation_suffix(mode: AggregationModes | None) -> str:
    """Handle aggregation suffix."""
    if mode is None:
        return "Level"
    if mode == AggregationModes.DIFF:
        return "Change"
    if mode == AggregationModes.SUM:
        return "Sum"
    if mode == AggregationModes.MA:
        return "MA"
    raise ValueError(f"{mode} is unknown")


def _period_aggregate(series: pd.Series, mode: AggregationModes | None, frequency: str) -> pd.Series:
    """Aggregate calendar periods without turning wholly missing periods into zero."""
    periods = series.resample(frequency)
    if mode == AggregationModes.DIFF:
        return periods.last().diff()
    if mode == AggregationModes.SUM:
        return periods.sum(min_count=1)
    if mode == AggregationModes.MA:
        return periods.mean()
    return periods.last()


def _aggregate_series(
    series: pd.Series,
    mode: AggregationModes | None,
    *,
    moving_average_type: MovingAvgModes | str,
    windows: tuple[int, ...],
    smooth: int | None,
    mtd: bool,
) -> tuple[dict[int, pd.Series], pd.Series, pd.Series]:
    """Compute rolling measures and calendar summaries for one input series."""
    measures = {}
    for window in windows:
        if mode == AggregationModes.DIFF:
            if mtd:
                # Shift by calendar period before aligning: a stale series must
                # not use its current-month observation as the prior month-end.
                monthly_last = series.resample("ME").last()
                prior = monthly_last.shift().reindex(series.index.normalize() + pd.offsets.MonthEnd(0))
                prior.index = series.index
                measures[window] = _aligned_moving_average(series, window, moving_average_type) - prior
            else:
                source = series.rolling(smooth).mean() if smooth is not None else series
                measures[window] = source.diff(window)
        elif mode == AggregationModes.SUM:
            measures[window] = series.rolling(window).sum()
        elif mode == AggregationModes.MA:
            measures[window] = _aligned_moving_average(series, window, moving_average_type)
        else:
            measures[window] = series
    return measures, _period_aggregate(series, mode, "ME"), _period_aggregate(series, mode, "QE")


def _seasonal_plots_for_columns(
    raw_df: pd.DataFrame,
    *,
    moving_average_window: int | None,
    moving_average_type: MovingAvgModes,
    input_frequency: str,
    exclude_years: list[int] | None,
) -> list[tp.Any]:
    """Handle seasonal plots for columns."""
    seasonal_plots: list[tp.Any] = []
    for col in raw_df.columns:
        raw_plot_series = tp.cast(pd.Series, raw_df[col])
        plot_series = (
            _aligned_moving_average(raw_plot_series, moving_average_window, moving_average_type)
            if moving_average_window is not None
            else raw_plot_series
        )
        unit = "m" if input_frequency == "M" else "d"
        title = str(col) if moving_average_window is None else f"{col} - {moving_average_window}{unit} mva"
        if plot_series.dropna().empty:
            seasonal_plots.append(
                go.Figure().update_layout(
                    title=title, annotations=[{"text": "Insufficient observations", "showarrow": False}]
                )
            )
            continue
        current_year = int(plot_series.dropna().index[-1].year)
        seasonal_plots.append(
            plot_seasonal(
                plot_series.to_frame(col),
                title=title,
                ytd_cum_sum=True,
                frequency=input_frequency,
                current_year=current_year,
                exclude_years=[year for year in exclude_years or [] if year != current_year],
            )
        )
    return seasonal_plots


def _normalize_input_frame(
    raw_df: pd.DataFrame,
    *,
    columns_filter: list[str] | None,
    fill_na: str | None,
    as_of: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Normalize input frame."""
    if not isinstance(raw_df, pd.DataFrame):
        raise TypeError("raw_df must be a pandas DataFrame")
    if not isinstance(raw_df.index, pd.DatetimeIndex):
        raise TypeError("raw_df index must be a pandas DatetimeIndex")
    if not raw_df.index.is_unique or raw_df.index.hasnans:
        raise ValueError("raw_df index must contain unique timestamps without NaT")
    if not raw_df.columns.is_unique or not all(isinstance(col, str) for col in raw_df.columns):
        raise ValueError("raw_df requires unique string column names")
    df = raw_df.sort_index().copy()
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if df.index.tz is not None and cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(df.index.tz)
        df = df.loc[df.index <= cutoff]
    if columns_filter is not None:
        df = df[columns_filter]
    if df.empty:
        raise ValueError("No data available after filtering")
    if fill_na is None:
        return df
    if fill_na == "ffill":
        return df.ffill()
    if fill_na == "bfill":
        return df.bfill()
    raise ValueError(f"NA fill mode {fill_na} is unknown use 'ffill' or 'bfill'")


def _build_monthly_table(
    df: pd.DataFrame,
    *,
    moving_average_type: MovingAvgModes,
    aggregation_type: AggregationModes | str | None,
    aggregation_columns: dict[str, AggregationModes | str | None] | None,
    highlighting_rules: dict[str, tp.Any] | None,
    benchmark_month: tp.Any,
    benchmark_quarter: tp.Any,
    windows: tuple[int, ...],
    history_months: int,
    history_quarters: int,
    include_qtd: bool,
    comparison_years: int | None,
    exclude_years: list[int] | None,
    input_frequency: str,
    smooth: int | None,
    mtd: bool,
) -> tuple[pd.DataFrame, AggregationModes | None, dict[str, AggregationModes | None], list[str]]:
    """Build both inventory and flow summaries from the same period calculations."""
    default_mode = _parse_aggregation_mode(aggregation_type)
    unknown = set(aggregation_columns or {}) - set(df.columns)
    if unknown:
        raise ValueError(f"Column '{sorted(unknown)[0]}' not found in dataframe")
    modes = {col: _parse_aggregation_mode((aggregation_columns or {}).get(col, default_mode)) for col in df}
    rolling_parts: dict[int, list[pd.Series]] = {window: [] for window in windows}
    monthly_parts, quarterly_parts = [], []
    for col in df:
        measures, monthly, quarterly = _aggregate_series(
            df[col],
            modes[col],
            moving_average_type=moving_average_type,
            windows=windows,
            smooth=smooth,
            mtd=mtd,
        )
        for window, values in measures.items():
            rolling_parts[window].append(values.rename(col))
        monthly_parts.append(monthly.rename(col))
        quarterly_parts.append(quarterly.rename(col))
    rolling = {window: pd.concat(parts, axis=1) for window, parts in rolling_parts.items()}
    monthly = pd.concat(monthly_parts, axis=1)
    quarterly = pd.concat(quarterly_parts, axis=1)
    unit = "m" if input_frequency == "M" else "d"
    suffix = _aggregation_suffix(default_mode)
    window_labels = [f"{window}{unit} {suffix}" for window in windows]
    if mtd:
        window_labels = [label + " (MTD basis)" for label in window_labels]
    parts = [rolling[window].iloc[-1].to_frame(label) for window, label in zip(windows, window_labels, strict=True)]
    if history_months:
        months = monthly.iloc[-history_months - 1 : -1].iloc[::-1].T
        months.columns = months.columns.strftime("%Y-%m")
        parts.append(months)
    if include_qtd:
        parts.append(quarterly.iloc[-1].to_frame("QTD"))
    if history_quarters:
        quarters = quarterly.iloc[-history_quarters - 1 : -1].iloc[::-1].T
        quarters.columns = [f"{value.year}Q{value.quarter}" for value in quarters.columns]
        parts.append(quarters)
    if comparison_years is not None:
        for window, label in zip(windows, window_labels, strict=True):
            history = _get_historical_data_on_date(rolling[window], df.index[-1])
            history = history.loc[
                (history.index.year < df.index[-1].year) & ~history.index.year.isin(exclude_years or [])
            ]
            prior_year = history.loc[history.index.year == df.index[-1].year - 1].reindex(columns=df.columns)
            previous = prior_year.iloc[-1] if len(prior_year) else pd.Series(float("nan"), index=df.columns)
            parts.extend(
                [
                    previous.to_frame(f"Y-1 {label}"),
                    history.tail(comparison_years).mean().to_frame(f"{comparison_years}Y {label}"),
                ]
            )
    if benchmark_month is not None or benchmark_quarter is not None:
        date = (
            pd.Timestamp(benchmark_month)
            if benchmark_month is not None
            else pd.Period(benchmark_quarter, freq="Q").start_time
        )
        if df.index.tz is not None and date.tzinfo is None:
            date = date.tz_localize(df.index.tz)
        if benchmark_month is not None:
            reference = monthly.reindex([_month_end(date.normalize())]).iloc[0]
            parts.append((rolling[windows[0]].iloc[-1] - reference).to_frame(f"{window_labels[0]} vs {date:%b%Y}"))
        else:
            dates = [_month_end(date + pd.DateOffset(months=i)) for i in range(3)]
            reference = monthly.reindex(dates).mean(skipna=False)
            parts.append(
                (rolling[windows[-1]].iloc[-1] - reference).to_frame(f"{window_labels[-1]} vs {benchmark_quarter}")
            )
    if highlighting_rules is not None:
        if "seasonal" in highlighting_rules:
            seasonal, window_history = highlighting_rules["seasonal"], None
        elif "window" in highlighting_rules:
            seasonal, window_history = None, highlighting_rules["window"]
        else:
            raise ValueError("highlighting_rules must include either 'seasonal' or 'window'")
        for i, window in enumerate(windows):
            stats = calculate_historical_mean_std_for_date(
                rolling[window],
                seasonal=seasonal,
                window=window_history,
                excluded_years=exclude_years,
            )
            number = str(i) if i else ""
            stats.columns = [f"_mean{number}", f"_std{number}"]
            parts.append(stats)
    return pd.concat(parts, axis=1), default_mode, modes, window_labels


def _build_monthly_style(
    ret_df: pd.DataFrame,
    *,
    na_rep: str | None,
    label_column: str,
    window_columns: list[str],
    plot_target_column: str | None = None,
    links: list[TableLink] | None = None,
) -> dict[str, tp.Any]:
    """Build monthly style."""
    all_columns = [str(col) for col in ret_df.columns]
    value_cols = [col for col in all_columns if col != label_column and not col.startswith("_")]
    data_cols = [col for col in value_cols if col in ret_df.columns]
    first_row_label = str(ret_df.index[0]) if not ret_df.empty else "0"

    format_columns: dict[str, TableFormatSpec] = {
        col: TableFormatNumber(digits=0, thousands=False) for col in data_cols
    }
    format_columns[label_column] = TableFormatString()
    sizing_cols = [TableColumnSizing(label=col, width_px=80) for col in data_cols]

    rules: list[TableRule] = [
        TableRule(
            id="first_row_bold_border",
            target=TableTarget(scope=TargetScope.rows, labels=[first_row_label]),
            action=TableAction(font_weight="bold", bottom_border=True),
        ),
    ]
    if data_cols:
        rules.append(
            TableRule(
                id="align_data_center",
                target=TableTarget(scope=TargetScope.columns, labels=data_cols),
                action=TableAction(text_align="center"),
            )
        )
        data_col_positions = [idx for idx, col in enumerate(all_columns) if col in data_cols]
        rules.extend(color_negative_red(list(ret_df.columns), [(pos, pos) for pos in data_col_positions]))

    rules.extend(
        highlight_zscore(
            all_columns,
            [(col, f"_mean{i if i else ''}", f"_std{i if i else ''}") for i, col in enumerate(window_columns)],
        )
    )

    options = TableStyleOptions(
        max_rows=max(1, len(ret_df)),
        show_index=False,
        global_style=TableGlobalStyle(
            background_color="lightblue",
            one_bg_color=False,
            header_border_bottom="1px solid black",
            table_border="2px solid black",
            font_size="11pt",
            font_family="Calibri",
            header_text_align="center",
        ),
    )
    options.hidden_columns = [col for col in all_columns if col != label_column and col.startswith("_")]
    if plot_target_column is not None and plot_target_column not in options.hidden_columns:
        options.hidden_columns.append(plot_target_column)

    return TableStylePlan(
        format=TableStyleFormat(na_rep=na_rep, precision=1, thousands=",", columns=format_columns),
        sizing=TableSizing(columns=sizing_cols),
        rules=rules,
        options=options,
        links=links,
    ).model_dump(mode="python", exclude_none=True)


def _unique_column_name(preferred: str, columns: tp.Iterable[object]) -> str:
    """Return a stable column name that does not collide with existing columns."""
    existing = {str(column) for column in columns}
    candidate = preferred or "index"
    suffix = 2
    while candidate in existing:
        candidate = f"{preferred or 'index'}_{suffix}"
        suffix += 1
    return candidate


def table_with_linked_plots_monthly(
    raw_df: pd.DataFrame,
    header: str,
    moving_average_window: int | None = 20,
    moving_average_type: MovingAvgModes = MovingAvgModes.SIMPLE,
    aggregation_type: AggregationModes | str | None = None,
    columns_filter: list[str] | None = None,
    aggregation_columns: dict[str, AggregationModes | str | None] | None = None,
    highlighting_rules: dict[str, tp.Any] | None = None,
    benchmark_month: tp.Any = None,
    benchmark_quarter: tp.Any = None,
    fill_na: str | None = None,
    na_rep: str | None = "-",
    row_plot_links: bool | list[str] = False,
    all_plots_link: bool = False,
    *,
    windows: tuple[int, ...] = (10, 20),
    history_months: int = 5,
    history_quarters: int = 0,
    include_qtd: bool = False,
    comparison_years: int | None = None,
    exclude_years: list[int] | None = None,
    input_frequency: tp.Literal["D", "M"] = "D",
    as_of: str | pd.Timestamp | None = None,
    smooth: int | None = None,
    mtd: bool = False,
) -> dict[str, dict[str, tp.Any]]:
    """Build the predefined monthly summary table with linked seasonal plots.

    The helper computes monthly summary columns plus optional historical
    highlight statistics, returns the styled table payload, and emits one
    seasonal plot per selected input series. ``row_plot_links`` selects the
    input series whose displayed row labels receive those plot links.
    Auxiliary ``_mean``/``_std`` columns are retained for rule evaluation and
    hidden at render time.

    ``windows`` counts observations for daily inputs and calendar months for
    monthly inputs. Use ``windows=(20,), history_months=3, comparison_years=5``
    for the inventory/table_format1 shape. ``history_quarters`` and ``include_qtd``
    append calendar aggregates. ``mtd`` measures each DIFF rolling average from
    the previous month-end; other aggregation modes are unchanged. ``smooth``
    smooths DIFF inputs before computing rolling changes, not calendar totals.
    ``as_of`` cuts inputs before filling, calculations and plots. Metadata in
    an input ``_last_update`` column is retained as a hidden output helper.
    """
    if (
        not windows
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in windows)
        or len(set(windows)) != len(windows)
    ):
        raise ValueError("windows must contain distinct positive integers")
    for name, value, minimum in (
        ("history_months", history_months, 0),
        ("history_quarters", history_quarters, 0),
        ("comparison_years", comparison_years, 1),
        ("smooth", smooth, 1),
        ("moving_average_window", moving_average_window, 1),
    ):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < minimum):
            raise ValueError(f"{name} must be an integer >= {minimum}")
    if input_frequency not in {"D", "M"}:
        raise ValueError("input_frequency must be 'D' or 'M'")
    if benchmark_month is not None and benchmark_quarter is not None:
        raise ValueError("Choose either benchmark_month or benchmark_quarter")
    if mtd and smooth is not None:
        raise ValueError("mtd and smooth cannot be combined")
    moving_average_type = MovingAvgModes(moving_average_type)
    link_requested = bool(row_plot_links or all_plots_link)
    if link_requested and (header is None or not str(header).strip()):
        raise ValueError("table/header name must not be blank when plot links are requested")

    raw_df = _normalize_input_frame(raw_df, columns_filter=None, fill_na=None, as_of=as_of)
    last_update = raw_df.pop("_last_update").iloc[-1] if "_last_update" in raw_df else None
    if columns_filter is not None:
        columns_filter = [col for col in columns_filter if col != "_last_update"]
    if input_frequency == "M":
        month_dates = raw_df.index.normalize() + pd.offsets.MonthEnd(0)
        if not month_dates.is_unique:
            raise ValueError("Monthly input requires one observation per calendar month")
        raw_df.index = month_dates
        raw_df = raw_df.asfreq("ME")
    raw_df = _normalize_input_frame(raw_df, columns_filter=None, fill_na=fill_na).apply(pd.to_numeric, errors="raise")
    df = _normalize_input_frame(raw_df, columns_filter=columns_filter, fill_na=None)
    seasonal_plots = _seasonal_plots_for_columns(
        raw_df,
        moving_average_window=moving_average_window,
        moving_average_type=moving_average_type,
        input_frequency=input_frequency,
        exclude_years=exclude_years,
    )
    table_df, default_agg_type, resolved_mode_by_column, window_columns = _build_monthly_table(
        df,
        moving_average_type=moving_average_type,
        aggregation_type=aggregation_type,
        aggregation_columns=aggregation_columns,
        highlighting_rules=highlighting_rules,
        benchmark_month=benchmark_month,
        benchmark_quarter=benchmark_quarter,
        windows=windows,
        history_months=history_months,
        history_quarters=history_quarters,
        include_qtd=include_qtd,
        comparison_years=comparison_years,
        exclude_years=exclude_years,
        input_frequency=input_frequency,
        smooth=smooth,
        mtd=mtd,
    )
    if last_update is not None:
        table_df["_last_update"] = last_update

    if aggregation_columns is not None:
        formatted_index: list[str] = []
        for col in table_df.index:
            col_name = str(col)
            mode = resolved_mode_by_column.get(col_name, default_agg_type)
            formatted_index.append(f"{col_name} [{_aggregation_suffix(mode)}]")
        table_df.index = pd.Index(formatted_index)
    table_df.columns = [str(col) for col in table_df.columns]
    rendered_index_by_column = dict(
        zip((str(col) for col in df.columns), (str(label) for label in table_df.index), strict=True)
    )
    links: list[TableLink] | None = None
    plot_names: list[str] | None = None
    all_plots_name: str | None = None
    selected_plot_targets: dict[str, str] = {}
    if link_requested:
        plot_type = "seasonal-mva" if moving_average_window is not None else "seasonal"
        plot_names, plot_metadata_links, all_plots_name = _build_plot_link_metadata(
            header,
            [(str(col), plot_type) for col in raw_df.columns],
            [str(label) for label in table_df.index],
            column_plot_links=row_plot_links,
            all_plots_link=all_plots_link,
            rendered_link_fields=rendered_index_by_column,
        )
        selected_plot_targets = {
            link.field: link.destination.value
            for link in plot_metadata_links
            if link.area == "header" and link.field is not None and link.destination.value is not None
        }

    label_column = _unique_column_name(str(header) if header is not None else "index", table_df.columns)
    table_df.index.name = label_column
    table_df = table_df.reset_index()
    table_df.columns = [str(col) for col in table_df.columns]

    plot_target_column: str | None = None
    if selected_plot_targets:
        plot_target_column = _unique_column_name("_plot_link", table_df.columns)
        table_df[plot_target_column] = table_df[label_column].map(selected_plot_targets)
        links = [
            TableLink(
                area="cells",
                field=label_column,
                destination=TableLinkDestination(kind=TableLinkKind.plot, value_field=plot_target_column),
            )
        ]
    if all_plots_name is not None:
        links = [*(links or ())]
        links.append(
            TableLink(
                area="header",
                field=label_column,
                destination=TableLinkDestination(kind=TableLinkKind.plot, value=all_plots_name),
            )
        )
    payload: dict[str, tp.Any] = {
        "data": table_df,
        "style": _build_monthly_style(
            table_df,
            na_rep=na_rep,
            label_column=label_column,
            window_columns=window_columns,
            plot_target_column=plot_target_column,
            links=links,
        ),
        "plots": seasonal_plots,
    }
    if plot_names is not None:
        payload["plot_names"] = plot_names
        if all_plots_name is not None:
            payload["all_plots_name"] = all_plots_name

    return {header: payload}


__all__ = ["table_with_linked_plots_monthly"]
