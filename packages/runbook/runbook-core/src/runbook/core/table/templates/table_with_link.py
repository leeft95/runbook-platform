from __future__ import annotations

import typing as tp

import pandas as pd

from ...plotting.line import plot_line
from ...plotting.seasonal import plot_seasonal
from ...plotting.templates import plot_line_with_comparison, plot_line_with_moving_average
from ...timeseries.analysis import MovingAvgModes
from ..models import (
    TableAction,
    TableColumnSizing,
    TableFormatNumber,
    TableFormatSpec,
    TableGlobalStyle,
    TableLink,
    TableRule,
    TableSizing,
    TableStyleFormat,
    TableStyleOptions,
    TableStylePlan,
    TableTarget,
    TargetScope,
)
from .common import (
    _aligned_moving_average,
    _build_plot_link_metadata,
    _select_highlight_columns,
    color_negative_red,
    highlight_zscore,
)


def _normalize_input_frame(
    raw_df: pd.DataFrame,
    *,
    columns_filter: list[str] | None,
    fill_na: str | None,
) -> pd.DataFrame:
    """Normalize input frame."""
    if not isinstance(raw_df, pd.DataFrame):
        raise TypeError(f"raw_df must be a pandas DataFrame, got {type(raw_df)!r}")
    if not isinstance(raw_df.index, pd.DatetimeIndex):
        raise TypeError("raw_df index must be a pandas DatetimeIndex")

    df = raw_df.sort_index().copy()
    if columns_filter is not None:
        unknown_cols = [col for col in columns_filter if col not in df.columns]
        if unknown_cols:
            raise ValueError(f"Column '{unknown_cols[0]}' not found in dataframe")
        df = df[columns_filter]
    if fill_na is None:
        return df
    if fill_na == "ffill":
        return df.ffill()
    if fill_na == "bfill":
        return df.bfill()
    raise ValueError(f"NA fill mode {fill_na} is unknown use 'ffill' or 'bfill'")


def _moving_average_type_label(mode: MovingAvgModes | str) -> str:
    """Handle moving average type label."""
    if isinstance(mode, MovingAvgModes):
        return mode.value
    return str(mode).lower()


def _resolve_chart_columns(
    columns: list[str],
    chart_columns: dict[str | tuple[str, ...], str | int | pd.DataFrame] | None,
    *,
    index: pd.DatetimeIndex,
) -> dict[str, tp.Any]:
    """Resolve chart columns."""
    allowed = {"line", "seasonal", "seasonal_mva"}
    default_chart = "seasonal" if (index.max() - index.min()).days > 730 else "line"
    resolved: dict[str, tp.Any] = {col: default_chart for col in columns}
    if chart_columns is None:
        return resolved

    for raw_key, mode in chart_columns.items():
        if isinstance(mode, pd.DataFrame):
            if not isinstance(mode.index, pd.DatetimeIndex) or not mode.index.is_unique:
                raise ValueError("Comparison data requires a unique DatetimeIndex")
            if not mode.columns.is_unique or mode.empty:
                raise ValueError("Comparison data requires non-empty data and unique columns")
        elif isinstance(mode, int) and not isinstance(mode, bool):
            if mode < 1:
                raise ValueError("Chart moving-average windows must be positive")
        elif not isinstance(mode, str) or mode not in allowed:
            raise ValueError(f"Unsupported chart type: {mode}")
        key_columns = list(raw_key) if isinstance(raw_key, tuple) else [raw_key]
        for column in key_columns:
            if column not in resolved:
                raise ValueError(f"Column '{column}' not found in dataframe")
            resolved[column] = mode
    return resolved


def _plots_for_columns(
    levels_df: pd.DataFrame,
    ma_df: pd.DataFrame,
    *,
    chart_modes: dict[str, tp.Any],
    moving_average_window: int,
    exclude_years: list[int] | None,
) -> list[tp.Any]:
    """Handle plots for columns."""
    plots: list[tp.Any] = []
    for col in levels_df.columns:
        mode = chart_modes[str(col)]
        title = str(col)
        if isinstance(mode, (int, pd.DataFrame)):
            if isinstance(mode, int):
                plots.append(plot_line_with_moving_average(levels_df[col], window=mode, title=title))
            else:
                plots.append(plot_line_with_comparison(levels_df[col], mode, title=title))
            continue
        if mode == "line":
            plots.append(
                plot_line(
                    levels_df[[col]],
                    title=title,
                    show_legend=False,
                    use_rangebreaks=True,
                )
            )
            continue
        if mode == "seasonal":
            plots.append(plot_seasonal(levels_df[[col]], title=title, ytd_cum_sum=True, exclude_years=exclude_years))
            continue
        plots.append(
            plot_seasonal(
                ma_df[[col]],
                title=f"{col} - {moving_average_window}d mva",
                ytd_cum_sum=True,
                exclude_years=exclude_years,
            )
        )
    return plots


def _build_internal_general_frame(
    levels_df: pd.DataFrame,
    ma_df: pd.DataFrame,
    *,
    rows: int,
    moving_average_window: int,
    moving_average_type: MovingAvgModes,
    change_zscore_window: int,
    header_label: str,
) -> tuple[pd.DataFrame, list[str]]:
    """Build internal general frame."""
    chg_df = levels_df.diff()
    chg_mean_df = chg_df.rolling(change_zscore_window).mean()
    chg_std_df = chg_df.rolling(change_zscore_window).std()
    level_std_df = levels_df.rolling(moving_average_window).std()

    internal_df = levels_df.copy()
    helper_columns: list[str] = []
    for col in levels_df.columns:
        chg_col = f"{col}_chg"
        chg_mean_col = f"{col}_chg_mean"
        chg_std_col = f"{col}_chg_std"
        internal_df[chg_col] = chg_df[col]
        internal_df[chg_mean_col] = chg_mean_df[col]
        internal_df[chg_std_col] = chg_std_df[col]
        helper_columns.extend([chg_col, chg_mean_col, chg_std_col])

    visible_body = internal_df.tail(rows).copy()
    visible_index = tp.cast(pd.DatetimeIndex, visible_body.index)
    visible_body.index = visible_index.strftime("%d-%b-%y")

    summary_label = f"{moving_average_window}d mv ({_moving_average_type_label(moving_average_type)})"
    summary_row: dict[str, tp.Any] = {}
    latest_level = levels_df.iloc[-1]
    latest_ma = ma_df.iloc[-1]
    latest_level_std = level_std_df.iloc[-1]
    for col in levels_df.columns:
        summary_row[str(col)] = latest_ma[col]
        summary_row[f"{col}_chg"] = latest_level[col]
        summary_row[f"{col}_chg_mean"] = latest_ma[col]
        summary_row[f"{col}_chg_std"] = latest_level_std[col]

    summary_df = pd.DataFrame([summary_row], index=[summary_label])
    full_df = pd.concat([visible_body, summary_df], axis=0)
    full_df.index.name = header_label
    full_df.columns = [str(col) for col in full_df.columns]
    return full_df, helper_columns


def _build_general_style(
    ret_df: pd.DataFrame,
    *,
    helper_columns: list[str],
    data_column_width: int,
    title_column_width: int,
    footer: str | None,
    na_rep: str | None,
    links: list[TableLink] | None = None,
    highlight_columns: tp.Sequence[str] | None = None,
) -> dict[str, tp.Any]:
    """Build general style."""
    visible_data_cols = [str(col) for col in ret_df.columns if str(col) not in helper_columns]
    summary_label = str(ret_df.index[-1]) if not ret_df.empty else ""

    format_columns: dict[str, TableFormatSpec] = {
        col: TableFormatNumber(digits=2, thousands=False) for col in visible_data_cols
    }
    sizing_cols = [TableColumnSizing(label=col, width_px=data_column_width) for col in visible_data_cols]

    rules: list[TableRule] = [
        TableRule(
            id="align_data_center",
            target=TableTarget(scope=TargetScope.columns, labels=visible_data_cols),
            action=TableAction(text_align="center"),
        ),
    ]
    if summary_label and not ret_df.empty:
        rules.append(
            TableRule(
                id="summary_row_bold",
                target=TableTarget(scope=TargetScope.rows, positions=[len(ret_df.index) - 1]),
                action=TableAction(font_weight="bold"),
            )
        )

    data_col_positions = [idx for idx, col in enumerate(ret_df.columns) if str(col) in visible_data_cols]
    rules.extend(color_negative_red(list(ret_df.columns), [(pos, pos) for pos in data_col_positions]))

    zscore_targets: list[tuple[int, int, str, str]] = []
    for visible_col in _select_highlight_columns(visible_data_cols, highlight_columns):
        target_pos = tp.cast(int, ret_df.columns.get_loc(visible_col))
        signal_pos = tp.cast(int, ret_df.columns.get_loc(f"{visible_col}_chg"))
        zscore_targets.append(
            (
                target_pos,
                signal_pos,
                f"{visible_col}_chg_mean",
                f"{visible_col}_chg_std",
            )
        )
    rules.extend(highlight_zscore(list(ret_df.columns), zscore_targets))

    options = TableStyleOptions(
        max_rows=max(1, len(ret_df)),
        footer=footer,
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
    options.hidden_columns = helper_columns

    return TableStylePlan(
        format=TableStyleFormat(na_rep=na_rep, precision=2, thousands=None, columns=format_columns),
        sizing=TableSizing(columns=sizing_cols, index_width_px=title_column_width),
        rules=rules,
        options=options,
        links=links,
    ).model_dump(mode="python", exclude_none=True)


def general_table_with_link(
    raw_df: pd.DataFrame,
    header: str | None = None,
    footer: str | None = None,
    rows: int = 10,
    moving_average_window: int = 20,
    moving_average_type: MovingAvgModes = MovingAvgModes.SIMPLE,
    change_zscore_window: int = 65,
    columns_filter: list[str] | None = None,
    chart_columns: dict[str | tuple[str, ...], str | int | pd.DataFrame] | None = None,
    title_column_width: int = 80,
    data_column_width: int = 60,
    fill_na: str | None = None,
    na_rep: str | None = "-",
    column_plot_links: bool | list[str] | str = False,
    all_plots_link: bool | str = False,
    *,
    exclude_years: list[int] | None = None,
    highlight_columns: tp.Sequence[str] | None = None,
) -> dict[str, dict[str, tp.Any]]:
    """Build a daily table with linked plots using legacy mixed-row highlight semantics.

    The visible table shows raw price levels for the dated rows and a final
    summary row showing the latest moving-average value. Styling is computed
    against hidden helper columns so the same z-score helper can color:

    - dated rows by testing 1-day change versus rolling change mean/std
    - the final summary row by testing raw level versus a Bollinger-style band

    ``highlight_columns`` selects coloured columns; [] disables highlights,
    retaining red negative values. String link options point to custom page
    URLs; True uses generated plots, False disables the corresponding links.

    The returned payload matches the predefined helper contract:
    ``{table_key: {"data": df, "style": style_payload, "plots": plots}}``.
    """
    if rows < 1:
        raise ValueError("rows must be >= 1")
    if moving_average_window < 1:
        raise ValueError("moving_average_window must be >= 1")
    if change_zscore_window < 2:
        raise ValueError("change_zscore_window must be >= 2")

    link_requested = (
        bool(column_plot_links or all_plots_link)
        or isinstance(column_plot_links, str)
        or isinstance(all_plots_link, str)
    )
    if link_requested and header is not None and not str(header).strip():
        raise ValueError("table/header name must not be blank when plot links are requested")
    header_label = header or "table"
    moving_average_type = MovingAvgModes(moving_average_type)

    levels_df = _normalize_input_frame(raw_df, columns_filter=columns_filter, fill_na=fill_na)
    if levels_df.empty:
        raise ValueError("No data available after filtering")

    ma_df = pd.concat(
        [
            _aligned_moving_average(
                tp.cast(pd.Series, levels_df[col]),
                moving_average_window,
                moving_average_type,
            ).rename(col)
            for col in levels_df.columns
        ],
        axis=1,
    ).loc[:, list(levels_df.columns)]
    chart_modes = _resolve_chart_columns(
        list(levels_df.columns),
        chart_columns,
        index=tp.cast(pd.DatetimeIndex, levels_df.index),
    )
    plots = _plots_for_columns(
        levels_df,
        ma_df,
        chart_modes=chart_modes,
        moving_average_window=moving_average_window,
        exclude_years=exclude_years,
    )

    ret_df, helper_columns = _build_internal_general_frame(
        levels_df,
        ma_df,
        rows=rows,
        moving_average_window=moving_average_window,
        moving_average_type=moving_average_type,
        change_zscore_window=change_zscore_window,
        header_label=header_label,
    )
    links: list[TableLink] | None = None
    plot_names: list[str] | None = None
    all_plots_name: str | None = None
    if link_requested:
        plot_names, links, all_plots_name = _build_plot_link_metadata(
            header_label,
            [
                (
                    str(col),
                    "line-comparison"
                    if isinstance(chart_modes[str(col)], pd.DataFrame)
                    else "line-ma"
                    if isinstance(chart_modes[str(col)], int)
                    else chart_modes[str(col)],
                )
                for col in levels_df.columns
            ],
            [str(col) for col in ret_df.columns],
            column_plot_links=column_plot_links,
            all_plots_link=all_plots_link,
        )
    payload: dict[str, tp.Any] = {
        "data": ret_df,
        "style": _build_general_style(
            ret_df,
            helper_columns=helper_columns,
            data_column_width=data_column_width,
            title_column_width=title_column_width,
            footer=footer,
            na_rep=na_rep,
            links=links,
            highlight_columns=highlight_columns,
        ),
        "plots": plots,
    }
    if plot_names is not None:
        payload["plot_names"] = plot_names
        if all_plots_name is not None:
            payload["all_plots_name"] = all_plots_name
    return {header_label: payload}


__all__ = ["general_table_with_link"]
