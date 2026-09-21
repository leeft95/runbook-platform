import pandas as pd
import pytest
from runbook.core.plotting.bar import plot_bar, plot_bar_forecast
from runbook.core.plotting.graphly import GraphlyFigureSpec, GraphlyPlotter, GraphlyTraceSpec, PlotlyPlotDef, PlotType
from runbook.core.plotting.line import plot_line
from runbook.core.plotting.mixed import plot_mixed
from runbook.core.plotting.seasonal import plot_seasonal


@pytest.mark.parametrize("freq", ["D", "B"])
@pytest.mark.parametrize("helper", [plot_line, plot_seasonal])
@pytest.mark.parametrize("width", [350, 600, 1200])
def test_short_daily_helpers_use_plotly_auto_ticks(helper, freq, width):
    index = pd.date_range("2026-09-07", periods=14, freq=freq)
    data = pd.DataFrame({"value": range(14)}, index=index)
    kwargs = {}
    if helper is plot_seasonal:
        kwargs = {"frequency": freq, "vs_average": False}

    fig = helper(data, width=width, use_rangebreaks=False, **kwargs)

    assert fig.layout.width == width
    assert fig.layout.xaxis.dtick is None
    assert fig.layout.xaxis.tickformat is None
    assert fig.layout.xaxis.nticks is None
    assert len(fig.data[0].x) == 14


@pytest.mark.parametrize("helper", [plot_bar, plot_bar_forecast])
@pytest.mark.parametrize("width", [350, 1200])
@pytest.mark.parametrize(
    "freq,format",
    [
        ("D", "%b %d\n%Y"),
        ("B", "%b %d\n%Y"),
        ("W", "%b %d\n%Y"),
        ("ME", "%b\n%Y"),
        ("2ME", "%b\n%Y"),
        ("QE", "%b\n%Y"),
        ("YE", "%Y"),
        ("h", None),
    ],
)
def test_bar_helpers_label_actual_dates_at_each_frequency(helper, width, freq, format):
    index = pd.date_range("2026-09-07", periods=14, freq=freq)
    data = pd.DataFrame({"value": range(14)}, index=index)
    kwargs = {"forecast_from": index[7]} if helper is plot_bar_forecast else {}
    fig = helper(data, width=width, use_rangebreaks=False, **kwargs)
    assert fig.layout.xaxis.tickmode == "array"
    assert list(fig.layout.xaxis.tickvals) == list(index)
    assert fig.layout.xaxis.tickformat == format
    assert len(fig.data[0].x) == 14


@pytest.mark.parametrize(
    "kwargs", [{"tickformat": "%d/%m"}, {"dtick": "M1"}, {"dtick": 86_400_000, "tickformat": "%d/%m"}]
)
def test_bar_labels_respect_explicit_overrides(kwargs):
    data = pd.DataFrame({"value": range(14)}, index=pd.date_range("2026-09-07", periods=14))
    figures = [
        plot_bar(data, use_rangebreaks=False, **kwargs),
        plot_bar_forecast(data, forecast_from=data.index[7], use_rangebreaks=False, **kwargs),
        GraphlyPlotter(use_rangebreaks=False).plot([PlotlyPlotDef(data=data, plot_type="bar", **kwargs)]),
    ]
    for fig in figures:
        for key, value in kwargs.items():
            assert fig.layout.xaxis[key] == value
        if "dtick" in kwargs:
            assert fig.layout.xaxis.tickvals is None
        else:
            assert list(fig.layout.xaxis.tickvals) == list(data.index)


def test_bar_dates_deduplicate_and_skip_missing_bars_without_filling_gaps():
    index = pd.DatetimeIndex(["2026-03-30", "2026-03-22", "2026-03-30", "2026-03-25"], tz="Europe/London")
    data = pd.DataFrame({"value": [1, 2, 3, float("nan")]}, index=index)
    fig = plot_bar(data, use_rangebreaks=False)
    assert list(fig.layout.xaxis.tickvals) == [index[0], index[1]]
    assert len(fig.data[0].x) == len(index)


@pytest.mark.parametrize("shared_xaxes", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_bar_axes_combine_dates_from_overlaid_or_shared_traces(shared_xaxes, reverse):
    index = pd.date_range("2026-09-07", periods=14)
    traces = [
        GraphlyTraceSpec(data=pd.DataFrame({"a": range(7)}, index=index[:7]), plot_type="bar"),
        GraphlyTraceSpec(
            data=pd.DataFrame({"b": range(7)}, index=index[7:]), plot_type="bar", row=2 if shared_xaxes else 1
        ),
    ]
    fig = plot_mixed(
        traces[::-1] if reverse else traces,
        n_rows=2 if shared_xaxes else 1,
        shared_xaxes=shared_xaxes,
        use_rangebreaks=False,
    )
    for axis in fig.select_xaxes():
        assert pd.DatetimeIndex(axis.tickvals).sort_values().equals(index)


@pytest.mark.parametrize("periods,freq", [(120, "D"), (30, "W"), (36, "ME"), (1000, "D"), (14, "h")])
def test_long_or_intraday_ranges_use_automatic_ticks(periods, freq):
    data = pd.DataFrame({"value": range(periods)}, index=pd.date_range("2024-01-01", periods=periods, freq=freq))
    fig = plot_line(data, use_rangebreaks=False)
    assert fig.layout.xaxis.dtick is None
    assert fig.layout.xaxis.tickformat is None


@pytest.mark.parametrize(
    "plot_type", [PlotType.line, PlotType.bar, PlotType.scatter, PlotType.line_scatter, PlotType.OHLC]
)
def test_graphly_specs_resolve_ticks_by_trace_type(plot_type):
    index = pd.date_range("2026-09-07", periods=14)
    data = pd.DataFrame({column: range(14) for column in ["open", "high", "low", "close"]}, index=index)
    fig = GraphlyPlotter().plot_spec(
        GraphlyFigureSpec(traces=[GraphlyTraceSpec(data=data, plot_type=plot_type)], use_rangebreaks=False)
    )
    assert fig.layout.xaxis.dtick is None
    assert fig.layout.xaxis.tickformat == ("%b %d\n%Y" if plot_type == PlotType.bar else None)
    assert fig.layout.xaxis.tickmode == ("array" if plot_type == PlotType.bar else None)


@pytest.mark.parametrize("freq", ["D", "ME", "h"])
def test_mixed_bars_lines_and_points_share_the_same_datetime_positions(freq):
    index = pd.date_range("2026-09-07", periods=14, freq=freq)
    data = pd.DataFrame({"value": range(14)}, index=index)
    fig = plot_mixed(
        [
            GraphlyTraceSpec(data=data, plot_type=kind, secondary_y=(kind == "scatter"))
            for kind in ["bar", "line", "scatter"]
        ],
        use_rangebreaks=False,
    )
    assert {trace.xaxis for trace in fig.data} == {"x"}
    for trace in fig.data:
        assert pd.DatetimeIndex(trace.x).equals(index)
    assert fig.layout.xaxis.tickvals is None
    assert fig.layout.xaxis.tickmode is None
    assert fig.layout.xaxis.dtick is None


@pytest.mark.parametrize("shared_xaxes", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_overlaid_or_shared_axes_use_full_history_and_forecast_range(shared_xaxes, reverse):
    history = pd.DataFrame({"history": range(365)}, index=pd.date_range("2025-09-07", periods=365))
    forecast = pd.DataFrame({"forecast": range(14)}, index=pd.date_range("2026-09-07", periods=14))
    traces = [
        GraphlyTraceSpec(data=history, plot_type="line"),
        GraphlyTraceSpec(data=forecast, plot_type="bar", row=2 if shared_xaxes else 1),
    ]
    fig = plot_mixed(
        traces[::-1] if reverse else traces,
        n_rows=2 if shared_xaxes else 1,
        shared_xaxes=shared_xaxes,
        use_rangebreaks=False,
    )
    assert all(axis.dtick is None for axis in fig.select_xaxes())
    assert all(axis.tickvals is None for axis in fig.select_xaxes())


def test_independent_subplots_resolve_their_own_date_ranges():
    data = pd.DataFrame({"value": range(365)}, index=pd.date_range("2025-09-07", periods=365))
    fig = plot_line({"short": data.iloc[-14:], "long": data}, rows=2, use_rangebreaks=False)
    assert fig.layout.xaxis.dtick is None
    assert fig.layout.xaxis2.dtick is None
    assert fig.layout.xaxis.matches is None
    assert fig.layout.xaxis2.matches is None


@pytest.mark.parametrize(
    "kwargs", [{"dtick": "M1"}, {"dtick": 86_400_000}, {"tickformat": "%d/%m"}, {"dtick": "M1", "tickformat": "%Y"}]
)
def test_explicit_tick_settings_take_precedence(kwargs):
    data = pd.DataFrame({"value": range(14)}, index=pd.date_range("2026-09-07", periods=14))
    figures = [
        plot_line(data, use_rangebreaks=False, **kwargs),
        GraphlyPlotter(use_rangebreaks=False).plot([PlotlyPlotDef(data=data, **kwargs)]),
    ]
    for fig in figures:
        for key, value in kwargs.items():
            assert fig.layout.xaxis[key] == value


def test_unsorted_duplicate_timezone_dates_use_plotly_auto_ticks():
    index = pd.date_range("2026-03-22", periods=14, tz="Europe/London")
    index = index[::-1].append(index[:1])
    data = pd.DataFrame({"value": range(len(index))}, index=index)
    fig = plot_line(data, use_rangebreaks=False)
    assert fig.layout.xaxis.dtick is None
    assert len(fig.data[0].x) == len(index)


@pytest.mark.parametrize(
    "index",
    [
        pd.DatetimeIndex([]),
        pd.DatetimeIndex([pd.NaT]),
        pd.DatetimeIndex(["2026-09-07"]),
        pd.Index([1, 2]),
        pd.Index(["a", "b"]),
    ],
)
def test_empty_single_or_non_datetime_indexes_keep_automatic_ticks(index):
    fig = plot_line(pd.DataFrame({"value": range(len(index))}, index=index), use_rangebreaks=False)
    assert fig.layout.xaxis.dtick is None


def test_histogram_datetime_index_does_not_format_numeric_bins_as_dates():
    data = pd.DataFrame({"value": range(14)}, index=pd.date_range("2026-09-07", periods=14))
    fig = plot_mixed([GraphlyTraceSpec(data=data, plot_type="histogram")], use_rangebreaks=False)
    assert fig.layout.xaxis.dtick is None
    assert fig.layout.xaxis.tickformat is None


@pytest.mark.parametrize(
    "tick_settings", [{}, {"dtick": "M1"}, {"tickformat": "%b"}, {"dtick": "M1", "tickformat": "%b"}]
)
def test_seasonal_plots_use_auto_ticks_unless_overridden(tick_settings):
    data = pd.DataFrame({"value": range(24)}, index=pd.date_range("2025-07-31", periods=24, freq="ME"))
    fig = plot_seasonal(
        data, start_month=7, end_month=6, over_year=True, frequency="M", vs_average=False, **tick_settings
    )
    assert fig.layout.xaxis.dtick == tick_settings.get("dtick")
    assert fig.layout.xaxis.tickformat == tick_settings.get("tickformat")
