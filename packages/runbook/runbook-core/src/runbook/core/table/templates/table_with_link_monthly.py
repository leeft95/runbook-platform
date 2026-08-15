from __future__ import annotations

import typing as tp

import pandas as pd

from ...plotting.seasonal import plot_seasonal
from ...timeseries.analysis import (
    AggregationModes,
    MovingAvgModes,
    calculate_historical_mean_std_for_date,
    calculate_moving_average,
)
from ..models import (
    TableAction,
    TableColumnSizing,
    TableFormatNumber,
    TableFormatSpec,
    TableGlobalStyle,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    TableTarget,
    TargetScope,
)
from .common import color_negative_red, highlight_zscore


def _month_end(ts: pd.Timestamp) -> pd.Timestamp:
    """Handle month end."""
    return ts + pd.offsets.MonthEnd(0)


def _as_single_column_df(series: pd.Series, column_name: str) -> pd.DataFrame:
    """Handle as single column df."""
    return pd.DataFrame({column_name: series})


def _parse_aggregation_mode(
    mode: AggregationModes | str | None,
) -> AggregationModes | None:
    """Parse aggregation mode."""
    if mode is None:
        return None
    if isinstance(mode, AggregationModes):
        return mode
    if isinstance(mode, str):
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


def _aligned_moving_average(series: pd.Series, window: int, kind: MovingAvgModes | str) -> pd.Series:
    """Handle aligned moving average."""
    aligned = pd.Series(index=series.index, dtype="float64")
    ma_values = tp.cast(pd.Series, calculate_moving_average(series, window=window, kind=kind))
    aligned.loc[ma_values.index] = ma_values.to_numpy()
    return aligned


def _aggregate_series(
    series: pd.Series,
    mode: AggregationModes | None,
    *,
    moving_average_type: MovingAvgModes | str,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Handle aggregate series."""
    monthly_freq = "ME"
    quarterly_freq = "QE"
    if mode is None:
        return (
            series,
            series,
            series.resample(monthly_freq).last(),
            series.resample(quarterly_freq).last(),
        )
    if mode == AggregationModes.DIFF:
        return (
            series.diff(periods=10),
            series.diff(periods=20),
            series.resample(monthly_freq).last().diff(),
            series.resample(quarterly_freq).last().diff(),
        )
    if mode == AggregationModes.SUM:
        return (
            series.rolling(10).sum(),
            series.rolling(20).sum(),
            series.resample(monthly_freq).sum(),
            series.resample(quarterly_freq).sum(),
        )
    if mode == AggregationModes.MA:
        return (
            _aligned_moving_average(series, 10, moving_average_type),
            _aligned_moving_average(series, 20, moving_average_type),
            series.resample(monthly_freq).mean(),
            series.resample(quarterly_freq).mean(),
        )
    raise ValueError(f"{mode} is unknown")


def _seasonal_plots_for_columns(
    raw_df: pd.DataFrame,
    *,
    moving_average_window: int | None,
    moving_average_type: MovingAvgModes,
) -> list[tp.Any]:
    """Handle seasonal plots for columns."""
    seasonal_plots: list[tp.Any] = []
    for col in raw_df.columns:
        raw_plot_series = tp.cast(pd.Series, raw_df[col])
        plot_series = (
            tp.cast(
                pd.Series,
                calculate_moving_average(raw_plot_series, moving_average_window, moving_average_type),
            )
            if moving_average_window is not None
            else raw_plot_series
        )
        seasonal_plots.append(
            plot_seasonal(
                plot_series.to_frame(col),
                title=f"{col} - {moving_average_window}d mva",
                ytd_cum_sum=True,
            )
        )
    return seasonal_plots


def _normalize_input_frame(
    raw_df: pd.DataFrame,
    *,
    columns_filter: list[str] | None,
    fill_na: str | None,
) -> pd.DataFrame:
    """Normalize input frame."""
    df = raw_df.copy()
    if columns_filter is not None:
        df = df[columns_filter]
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
    aggregation_columns: dict[str, AggregationModes] | None,
    highlighting_rules: dict[str, tp.Any] | None,
    benchmark_month: tp.Any,
    benchmark_quater: tp.Any,
) -> tuple[pd.DataFrame, AggregationModes | None, dict[str, AggregationModes | None]]:
    """Build monthly table."""
    default_agg_type = _parse_aggregation_mode(aggregation_type)
    if aggregation_columns is not None:
        unknown_cols = [col for col in aggregation_columns if col not in df.columns]
        if unknown_cols:
            raise ValueError(f"Column '{unknown_cols[0]}' not found in dataframe")

    resolved_mode_by_column: dict[str, AggregationModes | None] = {}
    window_change_parts: list[pd.Series] = []
    window_change1_parts: list[pd.Series] = []
    monthly_parts: list[pd.Series] = []
    for col in df.columns:
        mode = default_agg_type
        if aggregation_columns is not None and col in aggregation_columns:
            mode = _parse_aggregation_mode(aggregation_columns[col])
        resolved_mode_by_column[str(col)] = mode
        col_series = tp.cast(pd.Series, df[col])
        col_window_change, col_window_change1, col_monthly, _ = _aggregate_series(
            col_series,
            mode,
            moving_average_type=moving_average_type,
        )
        window_change_parts.append(col_window_change.rename(col))
        window_change1_parts.append(col_window_change1.rename(col))
        monthly_parts.append(col_monthly.rename(col))

    window_change = pd.concat(window_change_parts, axis=1).loc[:, list(df.columns)]
    window_change1 = pd.concat(window_change1_parts, axis=1).loc[:, list(df.columns)]
    monthly = pd.concat(monthly_parts, axis=1).loc[:, list(df.columns)]

    column_suffix = _aggregation_suffix(default_agg_type)
    window_change_last = _as_single_column_df(tp.cast(pd.Series, window_change.iloc[-1, :]), f"10d {column_suffix}")
    window_change_last1 = _as_single_column_df(tp.cast(pd.Series, window_change1.iloc[-1, :]), f"20d {column_suffix}")
    last_5_months = monthly.iloc[-6:-1, :].sort_index(ascending=False).T
    last_5_months.columns = [pd.to_datetime(x).strftime("%Y-%m") for x in last_5_months.columns]

    if highlighting_rules is not None:
        if "seasonal" in highlighting_rules:
            mean_std = tp.cast(
                pd.DataFrame,
                calculate_historical_mean_std_for_date(window_change, seasonal=highlighting_rules["seasonal"]),
            )
            mean_std1 = tp.cast(
                pd.DataFrame,
                calculate_historical_mean_std_for_date(window_change1, seasonal=highlighting_rules["seasonal"]),
            )
        elif "window" in highlighting_rules:
            mean_std = tp.cast(
                pd.DataFrame,
                calculate_historical_mean_std_for_date(
                    window_change, seasonal=None, window=highlighting_rules["window"]
                ),
            )
            mean_std1 = tp.cast(
                pd.DataFrame,
                calculate_historical_mean_std_for_date(
                    window_change1, seasonal=None, window=highlighting_rules["window"]
                ),
            )
        else:
            raise ValueError("highlighting_rules must include either 'seasonal' or 'window'")
        mean_std.columns = ["_mean", "_std"]
        mean_std1.columns = ["_mean1", "_std1"]
        if benchmark_month is not None:
            benchmark_month_ts = tp.cast(pd.Timestamp, pd.Timestamp(benchmark_month))
            benchmark_month_delta = tp.cast(
                pd.Series,
                window_change_last.iloc[:, 0] - monthly.loc[_month_end(benchmark_month_ts), :],
            )
            benchmark_month_df = _as_single_column_df(
                benchmark_month_delta,
                f"10d MA vs {benchmark_month_ts.strftime('%b%Y')}",
            )
            table_df = pd.concat(
                [
                    window_change_last,
                    window_change_last1,
                    last_5_months,
                    benchmark_month_df,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
        elif benchmark_quater is not None:
            benchmark_month_ts = tp.cast(pd.Timestamp, pd.Timestamp(benchmark_quater))
            benchmark_months = [
                _month_end(benchmark_month_ts),
                _month_end(benchmark_month_ts + pd.DateOffset(months=1)),
                _month_end(benchmark_month_ts + pd.DateOffset(months=2)),
            ]
            benchmark_month_delta = tp.cast(
                pd.Series,
                window_change_last1.iloc[:, 0] - monthly.loc[benchmark_months, :].mean(),
            )
            benchmark_month_df = _as_single_column_df(benchmark_month_delta, f"20dMA vs {benchmark_quater}")
            table_df = pd.concat(
                [
                    window_change_last,
                    window_change_last1,
                    last_5_months,
                    benchmark_month_df,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
        else:
            table_df = pd.concat(
                [
                    window_change_last,
                    window_change_last1,
                    last_5_months,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
    elif benchmark_month is not None:
        benchmark_month_ts = tp.cast(pd.Timestamp, pd.Timestamp(benchmark_month))
        benchmark_month_delta = tp.cast(
            pd.Series,
            window_change_last.iloc[:, 0] - monthly.loc[_month_end(benchmark_month_ts), :],
        )
        benchmark_month_df = _as_single_column_df(
            benchmark_month_delta, f"10dMA vs {benchmark_month_ts.strftime('%b%Y')}"
        )
        table_df = pd.concat(
            [
                window_change_last,
                window_change_last1,
                last_5_months,
                benchmark_month_df,
            ],
            axis=1,
        )
    else:
        table_df = pd.concat([window_change_last, window_change_last1, last_5_months], axis=1)

    return table_df, default_agg_type, resolved_mode_by_column


def _build_monthly_style(
    ret_df: pd.DataFrame,
    *,
    na_rep: str | None,
) -> dict[str, tp.Any]:
    """Build monthly style."""
    first_col = str(ret_df.columns[0])
    value_cols = [str(col) for col in ret_df.columns[1:10]]
    data_cols = [col for col in value_cols if col in ret_df.columns]
    first_row_label = str(ret_df.index[0]) if not ret_df.empty else "0"

    format_columns: dict[str, TableFormatSpec] = {
        col: TableFormatNumber(digits=0, thousands=False) for col in data_cols
    }
    sizing_cols = [TableColumnSizing(label=first_col, width_px=120)] + [
        TableColumnSizing(label=col, width_px=80) for col in data_cols
    ]

    rules: list[TableRule] = [
        TableRule(
            id="align_first_col_left",
            target=TableTarget(scope=TargetScope.columns, labels=[first_col]),
            action=TableAction(text_align="left"),
        ),
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
        data_col_positions = [idx for idx, col in enumerate(ret_df.columns) if col in data_cols]
        rules.extend(color_negative_red(list(ret_df.columns), [(pos, pos) for pos in data_col_positions]))

    rules.extend(highlight_zscore(list(ret_df.columns), [(1, "_mean", "_std"), (2, "_mean1", "_std1")]))

    options = TableStyleOptions(
        max_rows=100,
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
    options.hidden_columns = [str(col) for col in ret_df.columns if str(col).startswith("_")]

    return TableStylePlan(
        format=TableStyleFormat(na_rep=na_rep, precision=1, thousands=",", columns=format_columns),
        sizing=TableSizing(columns=sizing_cols),
        rules=rules,
        options=options,
    ).model_dump(mode="python", exclude_none=True)


def table_with_linked_plots_monthly(
    raw_df: pd.DataFrame,
    header: str,
    moving_averge_window: int | None = 20,
    moving_average_type: MovingAvgModes = MovingAvgModes.SIMPLE,
    aggregation_type: AggregationModes | str | None = None,
    columns_filter: list[str] | None = None,
    aggregation_columns: dict[str, AggregationModes] | None = None,
    highlighting_rules: dict[str, tp.Any] | None = None,
    benchmark_month: tp.Any = None,
    benchmark_quater: tp.Any = None,
    fill_na: str | None = None,
    na_rep: str | None = "-",
) -> dict[str, dict[str, tp.Any]]:
    """Build the predefined monthly summary table with linked seasonal plots.

    The helper computes monthly summary columns plus optional historical
    highlight statistics, returns the styled table payload, and emits one
    seasonal plot per selected input series. Auxiliary ``_mean``/``_std``
    columns are retained for rule evaluation and hidden at render time.
    """
    seasonal_plots = _seasonal_plots_for_columns(
        raw_df,
        moving_average_window=moving_averge_window,
        moving_average_type=moving_average_type,
    )
    df = _normalize_input_frame(raw_df, columns_filter=columns_filter, fill_na=fill_na)
    table_df, default_agg_type, resolved_mode_by_column = _build_monthly_table(
        df,
        moving_average_type=moving_average_type,
        aggregation_type=aggregation_type,
        aggregation_columns=aggregation_columns,
        highlighting_rules=highlighting_rules,
        benchmark_month=benchmark_month,
        benchmark_quater=benchmark_quater,
    )

    if aggregation_columns is not None:
        formatted_index: list[str] = []
        for col in table_df.index:
            col_name = str(col)
            mode = resolved_mode_by_column.get(col_name, default_agg_type)
            formatted_index.append(f"{col_name} [{_aggregation_suffix(mode)}]")
        table_df.index = pd.Index(formatted_index)
    if header is not None:
        table_df.index.name = header

    ret_df = table_df.reset_index()
    ret_df.columns = [str(col) for col in ret_df.columns]
    table_style = _build_monthly_style(ret_df, na_rep=na_rep)

    return {
        header: {
            "data": ret_df,
            "style": table_style,
            "plots": seasonal_plots,
        }
    }


__all__ = ["table_with_linked_plots_monthly"]
