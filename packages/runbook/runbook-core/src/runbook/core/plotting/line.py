"""Public facing wrapper for line plots."""

import typing as tp

import pandas as pd
import plotly

from .graphly import GraphlyTraceSpec, PlotType
from .mixed import plot_mixed


def plot_line(
    data: tp.Union[tp.Dict[str, pd.DataFrame], pd.DataFrame],
    title: str | None = None,
    width: int = 600,
    height: int = 400,
    show_legend: bool = False,
    hovertemplate: str | None = None,
    rows: int = 1,
    cols: int = 1,
    trace_style: dict[str, tp.Any] | None = None,
    series_styles: dict[str, dict[str, tp.Any]] | None = None,
    shared_xaxes: bool = False,
    horizontal_spacing: float | None = None,
    vertical_spacing: float | None = None,
    tickformat: str | None = "%b",
    dtick: str | int | float | None = "M1",
    use_rangebreaks: bool = True,
    holiday_countries: list[str] | None = None,
    legend_groups: bool = False,
) -> plotly.graph_objs._figure.Figure:
    """Plot line charts from a dataframe or a dict of named dataframes.

    Accepted inputs:

    - Single subplot: ``pd.DataFrame`` (each column is a series).
    - Multi subplot: ``{plot_name: pd.DataFrame}``.

    Styling contract:

    - ``trace_style``: kwargs applied to every trace in every subplot.
      Example: ``{"line": {"width": 2}, "mode": "lines+markers"}``
    - ``series_styles``: per-series overrides keyed by column name.
      Example: ``{"x": {"line": {"dash": "dot"}}, "y": {"marker": {"size": 10}}}``

    Subplot behavior for ``series_styles``:

    - Matching is by column name only, across all subplots.
    - If subplot A has column ``x`` and subplot B has column ``y``, both can be
      styled in one dict: ``{"x": {...}, "y": {...}}``.
    - If multiple subplots contain a column with the same name, that style is
      applied to all of those traces.
    """
    if isinstance(data, pd.DataFrame):
        data = {"": data}
    if rows * cols < len(data):
        raise ValueError(f"Not enough subplots for {len(data)} lines with {rows} rows and {cols} cols.")
    if rows < 1 or cols < 1:
        raise ValueError("Rows and cols must be positive integers.")
    match rows:
        case 1:
            row_height = [1.0]
        case 2:
            row_height = [0.7, 0.3]
        case 3:
            row_height = [0.5, 0.3, 0.2]
        case _:
            row_height = None  # type: ignore
    traces: list[GraphlyTraceSpec] = []
    for subplot_index, (name, df) in enumerate(data.items()):
        if not isinstance(df, pd.DataFrame):
            raise TypeError("When data is a dict, values must be pandas DataFrame instances.")
        traces.append(
            GraphlyTraceSpec(
                data=df,
                title=name,
                plot_type=PlotType.line,
                row=(subplot_index // cols) + 1,
                col=(subplot_index % cols) + 1,
                hovertemplate=hovertemplate,
                show_legend=show_legend,
                trace_style=trace_style,
                series_styles=series_styles,
                use_rangebreaks=use_rangebreaks,
                holiday_countries=holiday_countries,
            )
        )

    return plot_mixed(
        traces=traces,
        title=title,
        width=width,
        height=height,
        n_rows=rows,
        n_cols=cols,
        row_heights=row_height,
        shared_xaxes=shared_xaxes,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
        tickformat=tickformat,
        dtick=dtick,
        use_rangebreaks=use_rangebreaks,
        holiday_countries=holiday_countries,
        legend_groups=legend_groups,
    )
