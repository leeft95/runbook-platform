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
from .seasonal import _comparison_difference, plot_cot, plot_seasonal, plot_seasonal_grid


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


def comparison_chart(
    df: pd.DataFrame,
    df_hst: pd.DataFrame | None = None,
    title: str | None = None,
    *,
    units: str | None = None,
    show_difference: bool = False,
    x_axis_title: str = "Date",
    row_heights: list[float] | None = None,
    **options: Any,
) -> go.Figure:
    """Compare series with the first column in levels, differences and cumulatives.

    ``df`` needs a unique DatetimeIndex and at least two numeric columns. Its
    first column is the black baseline; all other columns are compared with it.
    The dashed vertical marker uses the first supplied index value of ``df``.
    Calculations sort dates chronologically without filling missing values.
    ``df_hst`` optionally adds grey historical lines to the levels panel only;
    colliding column names receive a ``History:`` prefix.

    By default, show levels and cumulative differences (70/30). Set
    ``show_difference=True`` to add non-cumulative differences below the
    cumulative panel. Subplot proportions match seasonal charts: 70/30 for
    two panels and 50/30/20 for three. ``row_heights`` overrides these with
    positive, finite relative weights from top to bottom, one per panel.
    Each series is cumulatively summed
    separately before subtracting the baseline's cumulative series, matching
    seasonal comparisons, including their missing-value and roundoff behavior.
    No calendar-day weighting or unit conversion is applied. ``units`` labels
    the axes; e.g. ``units="mcm/d"``. Only the main chart title and the
    shared bottom x-axis title are shown. Additional options go to ``plot_line``.
    """
    frames = []
    for name, data in (("df", df), ("df_hst", df_hst)):
        if name == "df_hst" and data is None:
            continue
        if not isinstance(data, pd.DataFrame) or not isinstance(data.index, pd.DatetimeIndex):
            raise TypeError(f"{name} requires a DataFrame with a DatetimeIndex")
        if data.index.hasnans or not data.index.is_unique:
            raise ValueError(f"{name} requires unique dates without NaT")
        frame = data.rename(columns=str).sort_index().apply(pd.to_numeric, errors="raise")
        if not frame.columns.is_unique:
            raise ValueError(f"{name} requires unique column labels")
        if name == "df" and (frame.empty or frame.shape[1] < 2):
            raise ValueError("df requires observations and at least a baseline and one comparison column")
        if name == "df_hst" and frame.index.tz != df.index.tz:
            raise ValueError("df_hst and df must use the same timezone")
        frames.append(frame)
    frame = frames[0]
    baseline = frame.iloc[:, 0]
    cumulative = frame.cumsum()
    cumulative_differences = pd.DataFrame(
        {name: _comparison_difference(cumulative[name], cumulative.iloc[:, 0]) for name in frame.columns[1:]}
    )
    styles = dict(options.pop("series_styles", None) or {})
    levels = frame
    if len(frames) > 1 and not frames[1].empty:
        history = frames[1].copy()
        names = []
        for name in history.columns:
            while name in frame.columns or name in names:
                name = f"History: {name}"
            names.append(name)
            styles[name] = {"line": {"color": "grey"}, **styles.get(name, {})}
        history.columns = names
        levels = pd.concat([history, frame], axis=1).sort_index()
    base_style = styles.get(str(baseline.name), {})
    styles[str(baseline.name)] = {
        **base_style,
        "line": {"width": 2, **base_style.get("line", {}), "color": "black"},
    }
    panels = {"Levels": levels, "Cumulative differences": cumulative_differences}
    if show_difference:
        panels["Differences"] = pd.DataFrame(
            {name: _comparison_difference(frame[name], baseline) for name in frame.columns[1:]}
        )
    rows = len(panels)
    figure = plot_line(
        panels,
        title=title,
        rows=rows,
        cols=1,
        row_heights=row_heights,
        shared_xaxes=True,
        legend_groups=True,
        series_styles=styles,
        **{
            "width": 900,
            "height": 600,
            "vertical_spacing": 0.02,
            **options,
            "trace_style": {"connectgaps": False, **(options.get("trace_style") or {})},
        },
    )
    figure.layout.annotations = ()
    suffix = f"<br>({units})" if units else ""
    figure.update_yaxes(title_text=units, row=1, col=1)
    if show_difference:
        figure.update_yaxes(
            title_text=f"Delta to {baseline.name}{suffix}", zeroline=True, zerolinecolor="grey", row=3, col=1
        )
    figure.update_yaxes(
        title_text=f"Cum. delta to {baseline.name}{suffix}", zeroline=True, zerolinecolor="grey", row=2, col=1
    )
    figure.update_xaxes(title_text=x_axis_title, row=rows, col=1)
    figure.add_vline(x=df.index[0], line_dash="dash", line_color="grey", line_width=1)
    return figure


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
    "comparison_chart",
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
