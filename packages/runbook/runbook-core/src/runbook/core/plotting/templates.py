"""Named report chart presets; all functions return a Plotly Figure.

Dates and observations are supplied by the caller. Additional keyword options
override preset defaults and are passed to the documented plotting helper.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from ..timeseries.analysis import MovingAvgModes, calculate_moving_average
from ..timeseries.rollup import calendar_moving_average
from .bar import plot_bar_forecast
from .cot import plot_cot_market
from .line import plot_line
from .regression import plot_price_vs_position, plot_regression
from .seasonal import plot_cot, plot_seasonal, plot_seasonal_grid


def plot_line_with_moving_average(
    data: pd.Series, window: int = 20, title: str | None = None, **options: Any
) -> go.Figure:
    """Overlay a simple moving average, preserving gaps before a full window.

    Options are forwarded to ``plot_line``. The source series name is used as
    the title unless supplied explicitly.
    """
    if not isinstance(data, pd.Series):
        raise TypeError("data must be a pandas Series")
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    name = data.name if data.name is not None else "value"
    frame = data.to_frame(name=name).copy()
    label = f"{window}d MA"
    if label == str(name):
        label += " overlay"
    frame[label] = (
        calculate_moving_average(data, window=window, kind=MovingAvgModes.SIMPLE)
        if len(data) >= window
        else pd.Series(index=data.index, dtype="float64")
    )
    return plot_line(frame, title=str(name) if title is None else title, **options)


def plot_line_with_comparison(
    data: pd.Series, comparison: pd.DataFrame, title: str | None = None, **options: Any
) -> go.Figure:
    """Plot a series with supplied comparisons on the secondary axis.

    Comparisons are sorted and forward-aligned to source dates, without
    backfilling leading gaps. Name collisions get a ``Comparison:`` prefix.
    Additional options are forwarded to ``plot_line``.
    """
    if not isinstance(data, pd.Series) or not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data requires a pandas Series with a DatetimeIndex")
    if not isinstance(comparison, pd.DataFrame) or not isinstance(comparison.index, pd.DatetimeIndex):
        raise TypeError("comparison requires a DataFrame with a DatetimeIndex")
    if not comparison.index.is_unique or comparison.index.hasnans:
        raise ValueError("Comparison data requires unique dates without NaT")
    if not comparison.columns.is_unique or comparison.empty:
        raise ValueError("Comparison data requires non-empty data and unique columns")
    name = data.name if data.name is not None else "value"
    frame = data.to_frame(name=name).copy()
    styles = dict(options.pop("series_styles", None) or {})
    aligned = comparison.sort_index().reindex(data.index, method="ffill")
    for field in aligned:
        label = str(field)
        while label in frame:
            label = f"Comparison: {label}"
        frame[label] = aligned[field]
        styles[label] = {"secondary_y": True, **styles.get(label, {})}
    return plot_line(frame, title=str(name) if title is None else title, series_styles=styles, **options)


def plot_seasonal_comparison(data: pd.DataFrame, **options: Any) -> go.Figure:
    """Show seasonal years, Y-1/5Y deviations and cumulative comparisons.

    Options are forwarded to ``plot_seasonal``.
    """
    return plot_seasonal(data, **{"ytd_cum_sum": True, "tickformat": "%b", **options})


def plot_reversed_seasonal_forecast(data: pd.DataFrame, *, dash_from: str | pd.Timestamp, **options: Any) -> go.Figure:
    """Dash the forecast from a supplied date, reversing level/comparison axes.

    Options are forwarded to ``plot_seasonal``.
    """
    return plot_seasonal(
        data,
        dash_from=pd.Timestamp(dash_from),
        **{
            "y_axis_reversed": True,
            "y1_axis_reversed": True,
            "tickformat": "%b",
            **options,
        },
    )


def plot_seasonal_with_history(data: dict[str, pd.DataFrame], *, history: pd.DataFrame, **options: Any) -> go.Figure:
    """Place ordinary history first, beside seasonal and cumulative panels.

    Options are forwarded to ``plot_seasonal_grid``.
    """
    return plot_seasonal_grid(
        data,
        history=history,
        **{
            "history_first": True,
            "ytd_cum_sum": True,
            "tickformat": "%b",
            **options,
        },
    )


def plot_cot_positions(data: pd.DataFrame, title: str = "", **options: Any) -> go.Figure:
    """Plot prepared Net/Long/Short observations with price and OI panels.

    Use ``prepare_cot_data`` for raw observations. Options go to ``plot_cot``.
    """
    return plot_cot(
        data,
        title=title,
        **{
            "columns": None,
            "plot_titles": ["Net", "Long", "Short"],
            "tickformat": "%b",
            **options,
        },
    )


def plot_cot_long_short(data: pd.DataFrame, title: str = "", **options: Any) -> go.Figure:
    """Plot prepared Long/Short observations with price and OI panels.

    Options are forwarded to ``plot_cot``.
    """
    return plot_cot(
        data,
        title=title,
        **{
            "columns": [["Long", "PX_LAST", "Long OI", "Internal"], ["Short", "PX_LAST", "Short OI", "Internal"]],
            "plot_titles": ["Long", "Short"],
            "tickformat": "%b",
            **options,
        },
    )


def plot_cot_net(data: pd.DataFrame, title: str = "", **options: Any) -> go.Figure:
    """Plot one COT column with position/price above OI in a 70/30 layout.

    Requires ``Net``, ``PX_LAST`` and ``Net OI``; ``Internal`` is optional.
    Pass ``rows=1`` to omit OI. Options are forwarded to ``plot_cot``.
    """
    return plot_cot(
        data,
        title=title,
        **{
            "columns": [["Net", "PX_LAST", "Net OI", "Internal"]],
            "plot_titles": ["Net position"],
            "tickformat": "%b",
            **options,
        },
    )


def plot_market_ohlc(data: dict[str, pd.DataFrame], **options: Any) -> go.Figure:
    """Plot OHLC prices with optional volume and open interest.

    Pass ``cot_start=observation_date - pd.Timedelta(days=7)`` to shade the
    measured COT week. Price and volume/OI use 70/30 rows.
    Holdings are omitted by default; options go to ``plot_cot_market``.
    """
    return plot_cot_market(data, **{"holdings_column": None, **options})


def plot_market_holdings(data: dict[str, pd.DataFrame], **options: Any) -> go.Figure:
    """Plot OHLC/volume/OI, with supplied holdings on a third row when OI exists.

    No measurement-week highlight is drawn by default. Pass ``highlight=True``
    with ``cot_start`` to enable it. Options go to ``plot_cot_market``.
    """
    return plot_cot_market(data, **{"highlight": False, **options})


def plot_regression_origin(data: pd.DataFrame, **options: Any) -> go.Figure:
    """Fit OLS through the origin, with recent points and residual bands.

    Options are forwarded to ``plot_regression``.
    """
    return plot_regression(data, **{"constant": False, **options})


def plot_regression_intercept(data: pd.DataFrame, **options: Any) -> go.Figure:
    """Fit OLS with an intercept, recent points and residual bands.

    Options are forwarded to ``plot_regression``.
    """
    return plot_regression(data, **{"constant": True, **options})


def plot_weekly_price_position(data: pd.DataFrame, **options: Any) -> go.Figure:
    """Compare one-observation position changes and percentage price returns.

    Input observations are normally weekly; options go to ``plot_price_vs_position``.
    """
    return plot_price_vs_position(data, **{"periods": 1, "is_spread": False, **options})


def plot_four_week_price_position(data: pd.DataFrame, **options: Any) -> go.Figure:
    """Compare four-observation position changes and percentage price returns.

    Input observations are normally weekly; options go to ``plot_price_vs_position``.
    """
    return plot_price_vs_position(data, **{"periods": 4, "is_spread": False, **options})


def plot_spread_position_changes(data: pd.DataFrame, **options: Any) -> go.Figure:
    """Compare four-observation position changes with absolute spread changes.

    Options, including ``periods`` and column names, go to ``plot_price_vs_position``.
    """
    return plot_price_vs_position(data, **{"periods": 4, "is_spread": True, **options})


def plot_forecast_bars(
    data: dict[str, pd.DataFrame] | pd.DataFrame | pd.Series, *, forecast_from: object, **options: Any
) -> go.Figure:
    """Use patterned forecast bars from the supplied observation onward.

    Options are forwarded to ``plot_bar_forecast``.
    """
    return plot_bar_forecast(data, forecast_from=forecast_from, **{"forecast_pattern_shape": "/", **options})


def plot_highlighted_bar(
    data: dict[str, pd.DataFrame] | pd.DataFrame | pd.Series, *, selected_at: object, **options: Any
) -> go.Figure:
    """Highlight only the selected observation with a patterned bar.

    Options are forwarded to ``plot_bar_forecast``.
    """
    return plot_bar_forecast(
        data,
        forecast_from=selected_at,
        **{
            "highlight_only": True,
            "forecast_legend": "Selected month",
            "forecast_pattern_shape": "/",
            **options,
        },
    )


def plot_rollup_seasonal(
    data: pd.Series, *, windows: tuple[str, ...] = ("5d", "20d", "3m"), **options: Any
) -> go.Figure:
    """Link full base history with seasonal base and calendar-MA panels.

    Windows use calendar days/months and skip missing values without filling.
    Summary Y-1/5Y columns share the seasonal panel for their base MA window.
    Options are forwarded to ``plot_seasonal_grid``.
    """
    if not isinstance(data, pd.Series) or not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data requires a pandas Series with a DatetimeIndex")
    if not data.index.is_unique or data.index.hasnans or data.empty:
        raise ValueError("data requires non-empty, unique dates without NaT")
    name = data.name if data.name is not None else "Value"
    frame = data.sort_index().to_frame(name=name)
    if frame.dropna().empty:
        return go.Figure().update_layout(
            title=str(name), annotations=[{"text": "Insufficient observations", "showarrow": False}]
        )
    seasonal = {"Base": frame}
    for window in dict.fromkeys(windows):
        seasonal[f"{window} MA"] = calendar_moving_average(frame, window)
    current_year = frame.dropna().index[-1].year
    settings = {"current_year": current_year, "vs_average": False, "tickformat": "%b", "title": str(name), **options}
    # An exclusion applies to historical overlays, never the selected year.
    settings["exclude_years"] = [
        year for year in settings.get("exclude_years") or [] if year != settings["current_year"]
    ]
    return plot_seasonal_grid(seasonal, history=frame, history_first=True, **settings)


__all__ = [
    "plot_rollup_seasonal",
    "plot_line_with_moving_average",
    "plot_line_with_comparison",
    "plot_seasonal_comparison",
    "plot_reversed_seasonal_forecast",
    "plot_seasonal_with_history",
    "plot_cot_positions",
    "plot_cot_long_short",
    "plot_cot_net",
    "plot_market_ohlc",
    "plot_market_holdings",
    "plot_regression_origin",
    "plot_regression_intercept",
    "plot_weekly_price_position",
    "plot_four_week_price_position",
    "plot_spread_position_changes",
    "plot_forecast_bars",
    "plot_highlighted_bar",
]
