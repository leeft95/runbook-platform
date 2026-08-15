"""Public facing wrapper for mixed plots."""

from __future__ import annotations

import pandas as pd
import plotly

from .graphly import GraphlyFigureSpec, GraphlyPlotter, GraphlyTraceSpec


def plot_mixed(
    traces: list[GraphlyTraceSpec],
    data: pd.DataFrame | None = None,
    title: str | None = None,
    width: int | None = None,
    height: int | None = None,
    n_rows: int = 1,
    n_cols: int = 1,
    row_heights: list[float] | None = None,
    column_widths: list[float] | None = None,
    shared_xaxes: bool = False,
    shared_yaxes: bool = False,
    horizontal_spacing: float | None = None,
    vertical_spacing: float | None = None,
    show_rangeslider: bool = False,
    tickformat: str | None = "%b",
    dtick: str | int | float | None = "M1",
    use_rangebreaks: bool = True,
    holiday_countries: list[str] | None = None,
    legend_groups: bool = False,
) -> plotly.graph_objs._figure.Figure:
    """Plot a mixed figure from explicit Graphly trace specifications.

    ``data`` acts as the shared dataframe for any trace that does not provide
    its own ``GraphlyTraceSpec.data``. Each trace defaults to ``row=1`` and
    ``col=1``, so a single-subplot mixed figure can be built without explicit
    subplot placement.
    """
    fig_spec = GraphlyFigureSpec(
        traces=traces,
        data=data,
        title=title,
        n_rows=n_rows,
        n_cols=n_cols,
        width=width,
        height=height,
        row_heights=row_heights,
        column_widths=column_widths,
        shared_xaxes=shared_xaxes,
        shared_yaxes=shared_yaxes,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
        show_rangeslider=show_rangeslider,
        tickformat=tickformat,
        dtick=dtick,
        use_rangebreaks=use_rangebreaks,
        holiday_countries=holiday_countries,
        legend_groups=legend_groups,
    )
    return GraphlyPlotter(
        title=title,
        n_rows=n_rows,
        n_cols=n_cols,
        width=width,
        height=height,
        auto_layout=False,
        row_heights=row_heights,
        column_widths=column_widths,
        shared_xaxes=shared_xaxes,
        shared_yaxes=shared_yaxes,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
        dtick=dtick,
        tickformat=tickformat,
        show_rangeslider=show_rangeslider,
        use_rangebreaks=use_rangebreaks,
        holiday_countries=holiday_countries,
        legend_groups=legend_groups,
    ).plot_spec(fig_spec)
