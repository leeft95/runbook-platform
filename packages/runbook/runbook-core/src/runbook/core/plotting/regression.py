"""Scatter plots for price/position changes using the shared OLS calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..timeseries.analysis import calculate_regressions


def plot_regression(
    data: pd.DataFrame,
    title: str | None = None,
    *,
    x: str | None = None,
    y: str | None = None,
    constant: bool = False,
    highlight_length: int = 8,
    recent_length: int = 3,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    width: int = 750,
    height: int = 500,
) -> go.Figure:
    """Plot OLS and ±2 residual standard deviations, with recent observations.

    By default the first column is y and the second is x, matching the COT
    report convention. The default fit goes through the origin. Missing and
    non-finite pairs are dropped together; dated observations are sorted before
    selecting the most recent points. Regression statistics are plain numbers
    in ``figure.layout.meta['regression']`` for report annotations.
    """
    if not isinstance(data, pd.DataFrame) or not data.columns.is_unique or data.shape[1] < 2:
        raise ValueError("data requires at least two uniquely named columns")
    for value in (highlight_length, recent_length):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("Highlight lengths must be non-negative integers")
    y = data.columns[0] if y is None else y
    x = data.columns[1] if x is None else x
    if x == y:
        raise ValueError("x and y must select different columns")
    pairs = data[[y, x]].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if isinstance(pairs.index, pd.DatetimeIndex):
        pairs = pairs.sort_index()
    if len(pairs) <= (2 if constant else 1) or pairs[x].nunique() < 2:
        raise ValueError("OLS requires distinct x values and positive residual degrees of freedom")
    alpha, beta, r_squared, residual_std = calculate_regressions(pairs[x], pairs[y], constant=constant, rolling=False)
    fig = go.Figure()
    for count, name, color, size in (
        (len(pairs), "Full sample", "#636efa", 7),
        (highlight_length, f"Last {highlight_length} observations", "black", 11),
        (recent_length, f"Last {recent_length} observations", "green", 11),
        (1, "Latest observation", "red", 12),
    ):
        if not count:
            continue
        sample = pairs.tail(count)
        dates = (
            sample.index.strftime("%d/%b/%Y")
            if isinstance(sample.index, pd.DatetimeIndex)
            else sample.index.astype(str)
        )
        fig.add_scatter(
            x=sample[x],
            y=sample[y],
            text=dates,
            name=name,
            mode="markers",
            marker={"color": color, "size": size},
            hovertemplate="%{text}<br>x: %{x}<br>y: %{y}<extra>%{fullData.name}</extra>",
        )
    fit_x = np.array([pairs[x].min(), pairs[x].max()])
    fit_y = alpha + beta * fit_x
    for multiplier, name, dash in (
        (0, "OLS fit", "solid"),
        (2, "+2 residual SD", "dash"),
        (-2, "-2 residual SD", "dash"),
    ):
        fig.add_scatter(
            x=fit_x, y=fit_y + multiplier * residual_std, mode="lines", name=name, line={"color": "grey", "dash": dash}
        )
    fig.update_layout(
        title=title,
        width=width,
        height=height,
        xaxis_title=x_axis_title or str(x),
        yaxis_title=y_axis_title or str(y),
        meta={
            "regression": {
                "alpha": alpha,
                "beta": beta,
                "r_squared": r_squared,
                "residual_std": residual_std,
                "observations": len(pairs),
                "constant": constant,
            }
        },
    )
    return fig


def plot_price_vs_position(
    data: pd.DataFrame,
    title: str | None = None,
    *,
    position_column: str = "Net",
    price_column: str = "PX_LAST",
    periods: int = 1,
    is_spread: bool = False,
    highlight_length: int = 4,
    as_of: str | pd.Timestamp | None = None,
) -> go.Figure:
    """Compare position changes with price returns (percent) or spread changes.

    ``periods`` counts paired observations, normally weekly COT reports. The
    fit goes through the origin. Older points are grouped by year, the previous
    ``highlight_length`` observations are marked separately, and the latest
    observation is always highlighted. No observation is forward-filled.
    """
    if not isinstance(data, pd.DataFrame) or not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data requires a DataFrame with a DatetimeIndex")
    if not data.index.is_unique or data.index.hasnans:
        raise ValueError("data requires unique dates without NaT")
    for value, minimum in ((periods, 1), (highlight_length, 0)):
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError("periods must be positive and highlight_length non-negative integers")
    frame = data.sort_index()
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if frame.index.tz is not None and cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(frame.index.tz)
        frame = frame.loc[frame.index <= cutoff]
    frame = frame[[position_column, price_column]].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    changes = (
        pd.DataFrame(
            {
                "Position change": frame[position_column].diff(periods),
                "Price change" if is_spread else "Price change (%)": (
                    frame[price_column].diff(periods)
                    if is_spread
                    else frame[price_column].pct_change(periods, fill_method=None) * 100
                ),
            }
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    x, y = changes.columns
    fig = plot_regression(changes, title, x=x, y=y, highlight_length=0, recent_length=0)
    fig.data = fig.data[1:]  # Replace the full sample with disjoint year/recent groups.
    older = changes.iloc[: -(highlight_length + 1)]
    for year, group in older.groupby(older.index.year):
        fig.add_scatter(
            x=group[x],
            y=group[y],
            text=group.index.strftime("%Y-%m-%d"),
            mode="markers",
            name=str(year),
            legendgroup=str(year),
            hovertemplate="%{text}<br>x: %{x}<br>y: %{y}<extra>%{fullData.name}</extra>",
        )
    if highlight_length:
        recent = changes.iloc[-(highlight_length + 1) : -1]
        fig.add_scatter(
            x=recent[x],
            y=recent[y],
            text=recent.index.strftime("%Y-%m-%d"),
            mode="markers",
            name=f"Previous {highlight_length} observations",
            marker={"color": "red", "symbol": "x", "size": 9},
            hovertemplate="%{text}<br>x: %{x}<br>y: %{y}<extra>%{fullData.name}</extra>",
        )
    fig.update_layout(legend_title_text="Observation group")
    return fig
