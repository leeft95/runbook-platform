"""Public facing wrappers for bar plots."""

from __future__ import annotations

import typing as tp
from collections.abc import Mapping

import pandas as pd
import plotly

from .graphly import GraphlyTraceSpec, PlotType
from .mixed import plot_mixed


def _normalize_plot_data(
    data: dict[str, pd.DataFrame] | pd.DataFrame | pd.Series,
) -> dict[str, pd.DataFrame]:
    """Normalize plot data."""
    if isinstance(data, pd.Series):
        series_name = str(data.name) if data.name is not None else "value"
        return {"": data.to_frame(name=series_name)}
    if isinstance(data, pd.DataFrame):
        return {"": data}
    if isinstance(data, dict):
        normalized: dict[str, pd.DataFrame] = {}
        for name, df in data.items():
            if not isinstance(df, pd.DataFrame):
                raise TypeError("When data is a dict, values must be pandas DataFrame instances.")
            normalized[str(name)] = df
        return normalized
    raise TypeError("data must be a pandas Series, DataFrame, or dict[str, DataFrame].")


def _merge_style(base: dict[str, tp.Any], overlay: Mapping[str, tp.Any] | None) -> dict[str, tp.Any]:
    """Handle merge style."""
    if overlay is None:
        return dict(base)
    out = dict(base)
    for key, value in overlay.items():
        current = out.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            out[key] = _merge_style(dict(current), value)
        else:
            out[key] = value
    return out


def _set_marker_defaults(style: dict[str, tp.Any], color: str, pattern_shape: str | None) -> dict[str, tp.Any]:
    """Handle set marker defaults."""
    marker = style.get("marker")
    marker_dict = dict(marker) if isinstance(marker, Mapping) else {}
    marker_dict["color"] = color
    if pattern_shape is not None:
        pattern = marker_dict.get("pattern")
        pattern_dict = dict(pattern) if isinstance(pattern, Mapping) else {}
        pattern_dict["shape"] = pattern_shape
        marker_dict["pattern"] = pattern_dict
    style["marker"] = marker_dict
    return style


def _validate_single_series_subplot(df: pd.DataFrame, subplot_name: str) -> None:
    """Validate single series subplot."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Subplot {subplot_name!r} must be a pandas DataFrame.")
    if not df.index.is_monotonic_increasing:
        raise ValueError(f"Subplot {subplot_name!r} index must be monotonic increasing.")
    if df.shape[1] != 1:
        raise ValueError(f"Subplot {subplot_name!r} must contain exactly one data column.")


def _split_bar_series(series: pd.Series, forecast_from: object) -> tuple[pd.Series, pd.Series]:
    """Handle split bar series."""
    history = series.where(series.index < forecast_from)
    forecast = series.where(series.index >= forecast_from)
    return history, forecast


def plot_bar(
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
    """Plot bar charts from a dataframe or a dict of named dataframes."""
    normalized_data = _normalize_plot_data(data)
    if rows * cols < len(normalized_data):
        raise ValueError(f"Not enough subplots for {len(normalized_data)} bars with {rows} rows and {cols} cols.")
    if rows < 1 or cols < 1:
        raise ValueError("Rows and cols must be positive integers.")

    traces: list[GraphlyTraceSpec] = []
    for subplot_index, (name, df) in enumerate(normalized_data.items()):
        traces.append(
            GraphlyTraceSpec(
                data=df,
                title=name,
                plot_type=PlotType.bar,
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
        shared_xaxes=shared_xaxes,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
        tickformat=tickformat,
        dtick=dtick,
        use_rangebreaks=use_rangebreaks,
        holiday_countries=holiday_countries,
        legend_groups=legend_groups,
    )


def plot_bar_forecast(
    data: dict[str, pd.DataFrame] | pd.DataFrame | pd.Series,
    forecast_from: object,
    title: str | None = None,
    width: int = 600,
    height: int = 400,
    show_legend: bool = True,
    hovertemplate: str | None = None,
    rows: int = 1,
    cols: int = 1,
    shared_xaxes: bool = False,
    horizontal_spacing: float | None = None,
    vertical_spacing: float | None = None,
    tickformat: str | None = "%b",
    dtick: str | int | float | None = "M1",
    use_rangebreaks: bool = True,
    holiday_countries: list[str] | None = None,
    legend_groups: bool = False,
    hist_color: str = "green",
    forecast_color: str = "blue",
    hist_pattern_shape: str | None = None,
    forecast_pattern_shape: str | None = None,
    hist_legend: str | None = None,
    forecast_legend: str | None = None,
    trace_style: dict[str, tp.Any] | None = None,
    hist_trace_style: dict[str, tp.Any] | None = None,
    forecast_trace_style: dict[str, tp.Any] | None = None,
) -> plotly.graph_objs._figure.Figure:
    """Plot history and forecast bars as separate traces split at ``forecast_from``."""
    normalized_data = _normalize_plot_data(data)
    if rows * cols < len(normalized_data):
        raise ValueError(f"Not enough subplots for {len(normalized_data)} bars with {rows} rows and {cols} cols.")
    if rows < 1 or cols < 1:
        raise ValueError("Rows and cols must be positive integers.")

    forecast_data: dict[str, pd.DataFrame] = {}
    forecast_styles_by_subplot: dict[str, dict[str, dict[str, tp.Any]]] = {}
    for subplot_name, df in normalized_data.items():
        _validate_single_series_subplot(df, subplot_name)
        base_name = str(df.columns[0])
        series = df.iloc[:, 0]
        history, forecast = _split_bar_series(series, forecast_from)

        subplot_df = pd.DataFrame(index=df.index)
        subplot_styles: dict[str, dict[str, tp.Any]] = {}

        history_name = hist_legend or base_name
        forecast_name = forecast_legend or f"{base_name} Forecast"

        if history.notna().any():
            subplot_df[history_name] = history
            history_style = _merge_style(dict(trace_style or {}), hist_trace_style)
            subplot_styles[history_name] = _set_marker_defaults(history_style, hist_color, hist_pattern_shape)

        if forecast.notna().any():
            subplot_df[forecast_name] = forecast
            forecast_style = _merge_style(dict(trace_style or {}), forecast_trace_style)
            subplot_styles[forecast_name] = _set_marker_defaults(forecast_style, forecast_color, forecast_pattern_shape)

        forecast_data[subplot_name] = subplot_df
        forecast_styles_by_subplot[subplot_name] = subplot_styles

    if len(forecast_data) == 1 and "" in forecast_data:
        return plot_bar(
            data=forecast_data[""],
            title=title,
            width=width,
            height=height,
            show_legend=show_legend,
            hovertemplate=hovertemplate,
            rows=rows,
            cols=cols,
            trace_style=None,
            series_styles=forecast_styles_by_subplot[""],
            shared_xaxes=shared_xaxes,
            horizontal_spacing=horizontal_spacing,
            vertical_spacing=vertical_spacing,
            tickformat=tickformat,
            dtick=dtick,
            use_rangebreaks=use_rangebreaks,
            holiday_countries=holiday_countries,
            legend_groups=legend_groups,
        )

    merged_series_styles: dict[str, dict[str, tp.Any]] = {}
    for subplot_styles in forecast_styles_by_subplot.values():
        merged_series_styles.update(subplot_styles)

    return plot_bar(
        data=forecast_data,
        title=title,
        width=width,
        height=height,
        show_legend=show_legend,
        hovertemplate=hovertemplate,
        rows=rows,
        cols=cols,
        trace_style=None,
        series_styles=merged_series_styles,
        shared_xaxes=shared_xaxes,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
        tickformat=tickformat,
        dtick=dtick,
        use_rangebreaks=use_rangebreaks,
        holiday_countries=holiday_countries,
        legend_groups=legend_groups,
    )
