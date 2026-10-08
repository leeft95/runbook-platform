from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.plotting.bar import plot_bar_forecast
from runbook.core.plotting.cot import plot_cot_market
from runbook.core.plotting.regression import plot_price_vs_position, plot_regression
from runbook.core.plotting.seasonal import plot_cot, plot_seasonal, plot_seasonal_grid


def test_regression_fits_origin_and_constant_sorts_dates_and_drops_invalid_pairs() -> None:
    x = np.arange(1.0, 11.0)
    y = 2.0 + 3.0 * x + np.sin(x)
    dates = pd.date_range("2025-01-01", periods=10)
    frame = pd.DataFrame({"Price change": y, "Position change": x}, index=dates)
    frame.iloc[1, 0] = np.nan
    frame.iloc[3, 1] = np.inf
    clean = frame.replace(np.inf, np.nan).dropna()
    for constant in (False, True):
        figure = plot_regression(frame.iloc[::-1], constant=constant)
        stats = figure.layout.meta["regression"]
        design = (
            np.column_stack([np.ones(len(clean)), clean.iloc[:, 1]])
            if constant
            else clean.iloc[:, 1].to_numpy()[:, None]
        )
        params = np.linalg.lstsq(design, clean.iloc[:, 0], rcond=None)[0]
        residual_std = np.sqrt(np.square(clean.iloc[:, 0] - design @ params).sum() / (len(clean) - len(params)))
        assert stats["beta"] == pytest.approx(params[-1])
        assert stats["alpha"] == pytest.approx(params[0] if constant else 0)
        assert stats["residual_std"] == pytest.approx(residual_std)
        assert stats["observations"] == 8
        traces = {trace.name: trace for trace in figure.data}
        assert list(traces["Latest observation"].x) == [10]
        assert len(traces["Last 3 observations"].text) == 3
        assert list(traces["OLS fit"].x) == [1, 10]
        np.testing.assert_allclose(np.asarray(traces["+2 residual SD"].y) - traces["OLS fit"].y, 2 * residual_std)
    with pytest.raises(ValueError, match="distinct"):
        plot_regression(pd.DataFrame({"Y": [1, 2, 3], "X": [1, 1, 1]}))


def test_seasonal_options_and_grid_preserve_axes_and_observation_dates() -> None:
    index = pd.date_range("2021-01-01", "2025-07-01")
    data = pd.DataFrame({"A": np.arange(len(index), dtype=float)}, index=index)
    options = dict(
        start="2023-01-01",
        current_year=2025,
        vs_average=False,
        ytd=True,
        y_axis_reversed=True,
        y_axis_title="Stock",
        y2_axis_reversed=True,
        y2_axis_title="Cumulative stock",
        x_axis_title="Season",
    )
    single = plot_seasonal(data, **options)
    assert {trace.name for trace in single.data} == {"2023", "2024", "2025", "YTD cumulative change"}
    assert single.layout.yaxis.autorange == "reversed"
    assert single.layout.yaxis2.autorange == "reversed"
    assert single.layout.yaxis2.title.text == "Cumulative stock"
    assert single.layout.xaxis2.title.text == "Season"
    grid = plot_seasonal_grid({"A": data, "B": data * 2}, history=data, history_first=True, **options)
    historical = next(trace for trace in grid.data if trace.name == "A")
    assert list(historical.x) == list(data.index)
    assert historical.xaxis == "x"
    assert len(grid.data) == 1 + 2 * len(single.data)
    assert grid.layout.xaxis.matches is None
    assert grid.layout.yaxis2.autorange == "reversed"
    assert [note.text for note in grid.layout.annotations] == ["History", "A", "B"]
    assert not grid.layout.xaxis2.matches == "x"
    for name in {trace.name for trace in single.data}:
        matching = [trace for trace in grid.data if trace.name == name]
        assert len({trace.line.color for trace in matching}) == 1
        assert sum(trace.showlegend is True for trace in matching) == 1
    year_colors = {trace.name: trace.line.color for trace in grid.data if trace.name in {"2023", "2024", "2025"}}
    assert len(set(year_colors.values())) == 3
    with pytest.raises(TypeError):
        plot_seasonal(data, misspelled_option=True)
    with pytest.raises(ValueError, match="years remain"):
        plot_seasonal(data, exclude_years=list(range(2021, 2026)))


def test_cot_variable_columns_and_optional_oi_panel() -> None:
    index = pd.date_range("2021-01-03", periods=220, freq="W")
    data = pd.DataFrame(
        {"Long": np.arange(220.0), "Short": np.arange(220.0) / 2, "PX_LAST": 50.0, "Long OI": 0.2, "Short OI": 0.1},
        index=index,
    )
    one = plot_cot(data, [["Long", "PX_LAST"]], "Long", ["Long"], rows=1)
    assert {trace.xaxis for trace in one.data} == {"x"}
    assert not any(trace.name == "Net/OI" for trace in one.data)
    two = plot_cot(
        data, [["Long", "PX_LAST", "Long OI"], ["Short", "PX_LAST", "Short OI"]], "Positions", ["Long", "Short"]
    )
    assert {trace.xaxis for trace in two.data} == {"x", "x2", "x3", "x4"}
    assert sum(trace.name == "Net/OI" for trace in two.data) == 2
    with pytest.raises(ValueError, match="one title"):
        plot_cot(data, [["Long", "PX_LAST"]], "Long", [], rows=1)


def test_cot_market_reuses_mixed_ohlc_volume_and_secondary_axes() -> None:
    index = pd.date_range("2025-01-01", periods=100)
    data = pd.DataFrame(
        {
            "PX_OPEN": 100.0,
            "PX_HIGH": 102.0,
            "PX_LOW": 98.0,
            "PX_LAST": 101.0,
            "VOLUME": np.arange(100.0),
            "FUT_AGGTE_OPEN_INT": 5000.0,
        },
        index=index,
    )
    original = data.copy()
    figure = plot_cot_market(
        {"Brent": data.iloc[::-1], "WTI": data.drop(columns="VOLUME")}, cot_start="2025-03-01", lookback_days=30
    )
    prices = [trace for trace in figure.data if trace.type == "candlestick"]
    assert len(prices) == 2
    assert list(prices[0].x) == list(index[index >= pd.Timestamp("2025-01-30")])
    volume = next(trace for trace in figure.data if trace.name == "Volume")
    oi = next(trace for trace in figure.data if trace.name == "OI")
    assert volume.type == "bar" and oi.yaxis != volume.yaxis
    assert len(figure.layout.shapes) == 4
    assert all(shape.x0 == pd.Timestamp("2025-03-01") for shape in figure.layout.shapes)
    assert all(shape.x1 == pd.Timestamp("2025-03-08") for shape in figure.layout.shapes)
    assert {shape.xref for shape in figure.layout.shapes} == {"x", "x2", "x3", "x4"}
    assert all(shape.y0 == 0 and shape.y1 == 1 and shape.yref.endswith(" domain") for shape in figure.layout.shapes)
    for col in (1, 2):
        top = figure.get_subplot(1, col).yaxis.domain
        bottom = figure.get_subplot(2, col).yaxis.domain
        assert (top[1] - top[0]) / (bottom[1] - bottom[0]) == pytest.approx(0.7 / 0.3)
        assert top[0] - bottom[1] == pytest.approx(0.02)
    assert not plot_cot_market({"Brent": data}, cot_start="2025-03-01", highlight=False).layout.shapes
    assert not any(axis.rangeslider.visible for axis in figure.select_xaxes())
    pd.testing.assert_frame_equal(data, original)
    only = plot_cot_market({"Price": data.drop(columns=["VOLUME", "FUT_AGGTE_OPEN_INT"])}, highlight=False)
    assert len(only.data) == 1 and not only.layout.shapes
    both = plot_cot_market({"Fund": data.assign(HOLDINGS=20.0)})
    holdings = next(trace for trace in both.data if trace.name == "Holdings")
    open_interest = next(trace for trace in both.data if trace.name == "OI")
    assert holdings.xaxis != open_interest.xaxis and holdings.yaxis != open_interest.yaxis


def test_forecast_bar_can_highlight_one_observation_without_coloring_later_bars() -> None:
    data = pd.Series([10.0, 20.0, 30.0, 40.0], index=pd.date_range("2025-01-01", periods=4), name="Value")
    figure = plot_bar_forecast(
        data, forecast_from=data.index[1], highlight_only=True, forecast_legend="Selected", forecast_pattern_shape="/"
    )
    history, selected = figure.data
    np.testing.assert_allclose(history.y, [10, np.nan, 30, 40], equal_nan=True)
    np.testing.assert_allclose(selected.y, [np.nan, 20, np.nan, np.nan], equal_nan=True)
    assert selected.marker.pattern.shape == "/" and selected.name == "Selected"
    with pytest.raises(ValueError, match="index value"):
        plot_bar_forecast(data, forecast_from=pd.Timestamp("2026-01-01"), highlight_only=True)


def test_price_position_changes_are_paired_horizon_specific_and_recent_groups_do_not_overlap() -> None:
    dates = pd.date_range("2024-12-01", periods=15, freq="W")
    frame = pd.DataFrame({"Net": np.arange(15.0) ** 2, "PX_LAST": 100.0 + np.arange(15.0)}, index=dates)
    for spread in (False, True):
        figure = plot_price_vs_position(
            frame.iloc[::-1], periods=4, is_spread=spread, as_of=dates[-2], highlight_length=3
        )
        traces = {trace.name: trace for trace in figure.data}
        assert list(traces["Latest observation"].x) == [13**2 - 9**2]
        expected = 4 if spread else (113 / 109 - 1) * 100
        assert traces["Latest observation"].y[0] == pytest.approx(expected)
        assert len(traces["Previous 3 observations"].x) == 3
        assert sum(len(trace.x) for trace in figure.data if trace.mode == "markers") == 10
        assert figure.layout.meta["regression"]["observations"] == 10
    short = plot_price_vs_position(frame.head(4), highlight_length=8)
    assert sum(len(trace.x) for trace in short.data if trace.mode == "markers") == 3
