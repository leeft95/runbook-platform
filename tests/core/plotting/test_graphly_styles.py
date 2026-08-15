from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from runbook.core.plotting.bar import plot_bar, plot_bar_forecast
from runbook.core.plotting.graphly import (
    GraphlyFigureSpec,
    GraphlyPlotter,
    GraphlyTraceSpec,
    PlotlyPlotDef,
    PlotType,
)
from runbook.core.plotting.line import plot_line
from runbook.core.plotting.mixed import plot_mixed


def test_graphly_plotter_applies_trace_style_to_scatter() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    plot_def = PlotlyPlotDef(
        data=df,
        plot_type=PlotType.line,
        trace_style={"line": {"dash": "dot", "width": 3}},
    )

    fig = GraphlyPlotter().plot([plot_def])
    trace = fig.data[0]
    assert trace.line.dash == "dot"
    assert trace.line.width == 3


def test_graphly_plotter_applies_series_specific_overrides() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]})
    plot_def = PlotlyPlotDef(
        data=df,
        plot_type=PlotType.line,
        trace_style={"line": {"width": 1}},
        series_styles={"b": {"line": {"dash": "dash"}}},
    )

    fig = GraphlyPlotter().plot([plot_def])
    trace_a = fig.data[0]
    trace_b = fig.data[1]
    assert trace_a.name == "a"
    assert trace_a.line.width == 1
    assert trace_a.line.dash is None
    assert trace_b.name == "b"
    assert trace_b.line.width == 1
    assert trace_b.line.dash == "dash"


def test_plot_line_passes_style_into_plotly_defs() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    fig = plot_line(
        data=df,
        trace_style={"line": {"width": 4}},
    )

    trace = fig.data[0]
    assert trace.line.width == 4


def test_plot_bar_passes_style_into_plotly_defs() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    fig = plot_bar(
        data=df,
        trace_style={"marker": {"line": {"width": 4}}},
    )

    trace = fig.data[0]
    assert trace.type == "bar"
    assert trace.marker.line.width == 4


def test_plot_bar_applies_series_specific_overrides() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]})
    fig = plot_bar(
        data=df,
        series_styles={"b": {"marker": {"pattern": {"shape": "/"}}}},
    )

    trace_a = fig.data[0]
    trace_b = fig.data[1]
    assert trace_a.name == "a"
    assert trace_a.marker.pattern.shape in (None, "")
    assert trace_b.name == "b"
    assert trace_b.marker.pattern.shape == "/"


def test_plot_bar_supports_multi_subplot_dict_input() -> None:
    fig = plot_bar(
        data={
            "left": pd.DataFrame({"a": [1.0, 2.0]}),
            "right": pd.DataFrame({"b": [3.0, 4.0]}),
        },
        rows=1,
        cols=2,
    )

    assert len(fig.data) == 2
    assert {trace.xaxis for trace in fig.data} == {"x", "x2"}


def test_plot_bar_validates_subplot_capacity() -> None:
    with pytest.raises(ValueError, match="Not enough subplots"):
        plot_bar(
            data={
                "left": pd.DataFrame({"a": [1.0, 2.0]}),
                "right": pd.DataFrame({"b": [3.0, 4.0]}),
            },
            rows=1,
            cols=1,
        )


def test_plot_bar_forecast_splits_single_dataframe_into_two_traces() -> None:
    idx = pd.date_range("2025-01-01", periods=4, freq="D")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}, index=idx)

    fig = plot_bar_forecast(df, forecast_from=idx[2], hist_color="orange", forecast_color="purple")

    assert len(fig.data) == 2
    assert fig.data[0].type == "bar"
    assert fig.data[0].name == "value"
    assert fig.data[0].marker.color == "orange"
    assert fig.data[1].name == "value Forecast"
    assert fig.data[1].marker.color == "purple"


def test_plot_bar_forecast_supports_series_input_and_custom_legends() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    series = pd.Series([1.0, 2.0, 3.0], index=idx, name="balance")

    fig = plot_bar_forecast(
        series,
        forecast_from=idx[1],
        hist_legend="History",
        forecast_legend="Forecast",
    )

    assert [trace.name for trace in fig.data] == ["History", "Forecast"]


def test_plot_bar_forecast_applies_pattern_shapes() -> None:
    idx = pd.date_range("2025-01-01", periods=4, freq="D")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}, index=idx)

    fig = plot_bar_forecast(
        df,
        forecast_from=idx[2],
        hist_pattern_shape="",
        forecast_pattern_shape="/",
    )

    assert fig.data[0].marker.pattern.shape == ""
    assert fig.data[1].marker.pattern.shape == "/"


def test_plot_bar_forecast_omits_empty_history_trace() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)

    fig = plot_bar_forecast(df, forecast_from=idx[0])

    assert len(fig.data) == 1
    assert fig.data[0].name == "value Forecast"


def test_plot_bar_forecast_omits_empty_forecast_trace() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)

    fig = plot_bar_forecast(df, forecast_from=idx[-1] + pd.Timedelta(days=1))

    assert len(fig.data) == 1
    assert fig.data[0].name == "value"


def test_plot_bar_forecast_supports_multi_subplot_dict_input() -> None:
    idx = pd.date_range("2025-01-01", periods=4, freq="D")
    fig = plot_bar_forecast(
        data={
            "left": pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]}, index=idx),
            "right": pd.DataFrame({"b": [4.0, 3.0, 2.0, 1.0]}, index=idx),
        },
        forecast_from=idx[2],
        rows=1,
        cols=2,
    )

    assert {trace.xaxis for trace in fig.data} == {"x", "x2"}


def test_plot_bar_forecast_rejects_multi_column_subplots() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}, index=idx)

    with pytest.raises(ValueError, match="exactly one data column"):
        plot_bar_forecast(df, forecast_from=idx[1])


def test_plot_bar_forecast_rejects_invalid_input_type() -> None:
    with pytest.raises(TypeError, match="Series, DataFrame, or dict"):
        plot_bar_forecast([1.0, 2.0, 3.0], forecast_from=1)


def test_plot_bar_forecast_requires_monotonic_index() -> None:
    idx = pd.to_datetime(["2025-01-02", "2025-01-01", "2025-01-03"])
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=idx)

    with pytest.raises(ValueError, match="monotonic increasing"):
        plot_bar_forecast(df, forecast_from=idx[1])


def test_graphly_groups_legend_by_series_name_in_single_row_multi_col() -> None:
    plot_defs = [
        PlotlyPlotDef(data=pd.DataFrame({"x": [1.0, 2.0, 3.0]}), plot_type=PlotType.line),
        PlotlyPlotDef(data=pd.DataFrame({"x": [3.0, 2.0, 1.0]}), plot_type=PlotType.line),
    ]
    fig = GraphlyPlotter(n_rows=1, n_cols=2, legend_groups=True).plot(plot_defs)

    assert len(fig.data) == 2
    assert fig.data[0].legendgroup == "x"
    assert fig.data[1].legendgroup == "x"
    assert fig.data[0].showlegend is True
    assert fig.data[1].showlegend is False


def test_graphly_allows_multiple_plot_defs_in_same_subplot() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    line_def = PlotlyPlotDef(
        data=pd.DataFrame({"line": [1.0, 2.0, 3.0]}, index=idx),
        plot_type=PlotType.line,
        row=1,
        col=1,
    )
    bar_def = PlotlyPlotDef(
        data=pd.DataFrame({"bar": [3.0, 2.0, 1.0]}, index=idx),
        plot_type=PlotType.bar,
        row=1,
        col=1,
    )

    fig = GraphlyPlotter(n_rows=1, n_cols=1).plot([line_def, bar_def])

    assert len(fig.data) == 2
    assert fig.data[0].xaxis == "x"
    assert fig.data[1].xaxis == "x"
    assert fig.data[0].type == "scatter"
    assert fig.data[1].type == "bar"


def test_graphly_enables_secondary_y_for_shared_subplot() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    primary_def = PlotlyPlotDef(
        data=pd.DataFrame({"left": [1.0, 2.0, 3.0]}, index=idx),
        plot_type=PlotType.line,
        row=1,
        col=1,
    )
    secondary_def = PlotlyPlotDef(
        data=pd.DataFrame({"right": [3.0, 2.0, 1.0]}, index=idx),
        plot_type=PlotType.line,
        row=1,
        col=1,
        series_styles={"right": {"secondary_y": True}},
    )

    fig = GraphlyPlotter(n_rows=1, n_cols=1).plot([primary_def, secondary_def])

    assert fig.data[0].yaxis == "y"
    assert fig.data[1].yaxis == "y2"


def test_graphly_rejects_mixed_explicit_and_implicit_positions() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    explicit_def = PlotlyPlotDef(
        data=pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=idx), plot_type=PlotType.line, row=1, col=1
    )
    implicit_def = PlotlyPlotDef(data=pd.DataFrame({"b": [3.0, 2.0, 1.0]}, index=idx), plot_type=PlotType.line)

    with pytest.raises(ValueError, match="must set row and col"):
        GraphlyPlotter(n_rows=1, n_cols=1).plot([explicit_def, implicit_def])


def test_graphly_rejects_invalid_explicit_position() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    bad_def = PlotlyPlotDef(data=pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=idx), plot_type=PlotType.line, row=0, col=1)

    with pytest.raises(ValueError, match="positive integers"):
        GraphlyPlotter(n_rows=1, n_cols=1).plot([bad_def])


def test_graphly_plot_spec_defaults_row_col_to_single_subplot() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"bars": [1.0, 2.0, 3.0], "line": [3.0, 2.0, 1.0]}, index=idx)

    fig = GraphlyPlotter().plot_spec(
        GraphlyFigureSpec(
            data=df,
            traces=[
                GraphlyTraceSpec(plot_type=PlotType.bar, columns=["bars"]),
                GraphlyTraceSpec(plot_type=PlotType.line, columns=["line"]),
            ],
        )
    )

    assert len(fig.data) == 2
    assert {trace.xaxis for trace in fig.data} == {"x"}
    assert {trace.type for trace in fig.data} == {"bar", "scatter"}


def test_plot_mixed_supports_shared_dataframe_and_secondary_y() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"bars": [1.0, 2.0, 3.0], "line": [3.0, 2.0, 1.0]}, index=idx)

    fig = plot_mixed(
        data=df,
        traces=[
            GraphlyTraceSpec(plot_type=PlotType.bar, columns=["bars"]),
            GraphlyTraceSpec(plot_type=PlotType.line, columns=["line"], secondary_y=True),
        ],
    )

    trace_by_name = {trace.name: trace for trace in fig.data}
    assert trace_by_name["bars"].yaxis == "y"
    assert trace_by_name["line"].yaxis == "y2"


def test_plot_mixed_supports_explicit_multi_subplot_positions() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"left": [1.0, 2.0, 3.0], "right": [3.0, 2.0, 1.0]}, index=idx)

    fig = plot_mixed(
        data=df,
        traces=[
            GraphlyTraceSpec(plot_type=PlotType.line, columns=["left"], row=1, col=1),
            GraphlyTraceSpec(plot_type=PlotType.bar, columns=["right"], row=1, col=2),
        ],
        n_rows=1,
        n_cols=2,
    )

    assert {trace.xaxis for trace in fig.data} == {"x", "x2"}


def test_plot_mixed_supports_ohlc_histogram_and_pie() -> None:
    idx = pd.date_range("2025-01-01", periods=4, freq="D")
    ohlc_df = pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0, 11.5],
            "high": [11.0, 12.0, 12.5, 12.0],
            "low": [9.5, 10.5, 11.5, 11.0],
            "close": [10.5, 11.5, 12.0, 11.8],
        },
        index=idx,
    )
    hist_df = pd.DataFrame({"returns": [1.0, 0.5, -0.2, 0.1]})
    pie_df = pd.DataFrame({"label": ["a", "b"], "value": [2, 3]})

    fig = plot_mixed(
        traces=[
            GraphlyTraceSpec(plot_type=PlotType.OHLC, data=ohlc_df, row=1, col=1),
            GraphlyTraceSpec(plot_type=PlotType.histogram, data=hist_df, row=1, col=2),
            GraphlyTraceSpec(plot_type=PlotType.pie, data=pie_df, columns=["label", "value"], row=1, col=3),
        ],
        n_rows=1,
        n_cols=3,
    )

    assert fig.data[0].type in {"ohlc", "candlestick"}
    assert fig.data[1].type == "histogram"
    assert fig.data[2].type == "pie"


def test_plot_mixed_supports_trace_level_data_override() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    shared_df = pd.DataFrame({"line": [1.0, 2.0, 3.0]}, index=idx)
    override_df = pd.DataFrame({"signal": [3.0, 2.0, 1.0]}, index=idx)

    fig = plot_mixed(
        data=shared_df,
        traces=[
            GraphlyTraceSpec(plot_type=PlotType.line, columns=["line"]),
            GraphlyTraceSpec(plot_type=PlotType.scatter, data=override_df, columns=["signal"]),
        ],
    )

    assert {trace.name for trace in fig.data} == {"line", "signal"}


def test_plot_mixed_applies_name_map_to_legend_labels() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"PX_LAST": [1.0, 2.0, 3.0]}, index=idx)

    fig = plot_mixed(
        data=df,
        traces=[
            GraphlyTraceSpec(
                plot_type=PlotType.line,
                columns=["PX_LAST"],
                name_map={"PX_LAST": "Price"},
            )
        ],
    )

    assert fig.data[0].name == "Price"


def test_plot_mixed_requires_data_source() -> None:
    with pytest.raises(ValueError, match="provide data directly"):
        plot_mixed(traces=[GraphlyTraceSpec(plot_type=PlotType.line, columns=["x"])])


def test_plot_mixed_rejects_invalid_ohlc_column_count() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"open": [1.0, 2.0, 3.0], "high": [2.0, 3.0, 4.0], "low": [0.0, 1.0, 2.0]}, index=idx)

    with pytest.raises(ValueError, match="exactly four columns"):
        plot_mixed(
            data=df,
            traces=[GraphlyTraceSpec(plot_type=PlotType.OHLC, columns=["open", "high", "low"])],
        )


def test_plot_mixed_rejects_out_of_grid_position() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]}, index=idx)

    with pytest.raises(ValueError, match="exceeds subplot grid"):
        plot_mixed(
            data=df,
            traces=[GraphlyTraceSpec(plot_type=PlotType.line, columns=["x"], row=2, col=1)],
            n_rows=1,
            n_cols=1,
        )


def test_graphly_ohlc_with_intraday_bdib_data() -> None:
    csv_path = Path("data/fixtures/intraday_bars.csv")
    df = pd.read_csv(csv_path, parse_dates=["timestamp"], nrows=1000)
    intraday = df.set_index("timestamp")[["open", "high", "low", "close"]]

    plot_def = PlotlyPlotDef(data=intraday, plot_type=PlotType.OHLC)
    fig = GraphlyPlotter().plot([plot_def])

    assert len(fig.data) == 1
    assert fig.data[0].type in {"ohlc", "candlestick"}
