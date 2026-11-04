from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from runbook.core.plotting.templates import (
    plot_doe_actual_vs_whisper,
    plot_doe_inventory_change,
    plot_doe_inventory_signal,
    plot_doe_seasonal_range,
)
from runbook.core.timeseries.transforms import ts_by_year


@pytest.fixture
def weekly() -> pd.Series:
    index = pd.date_range("2018-01-03", "2026-10-28", freq="W-WED")
    step = np.arange(len(index), dtype=float)
    return pd.Series(420_000 + step * 100 + 4000 * np.sin(step / 13), index=index, name="Crude stocks")


def test_doe_inventory_change_uses_current_level_and_historical_delta_bars(weekly: pd.Series) -> None:
    original = weekly.copy()
    figure = plot_doe_inventory_change(weekly, current_year=2026, history_years=5)
    traces = {trace.name: trace for trace in figure.data}

    assert traces["Delta vs Average"].type == "bar"
    assert traces["Delta vs Last Year"].type == "bar"
    assert traces["2026"].type == "scatter"
    assert traces["2026"].yaxis == "y2"
    by_year = ts_by_year(weekly.to_frame(), frequency="W", column="Crude stocks", dummy_date_index=True)
    expected = by_year[2026] - by_year[[2021, 2022, 2023, 2024, 2025]].mean(axis=1)
    np.testing.assert_allclose(traces["Delta vs Average"].y, expected, equal_nan=True)
    assert figure.layout.yaxis.title.text == "Storage vs history"
    assert figure.layout.yaxis2.title.text == "Total storage"
    pd.testing.assert_series_equal(weekly, original)


def test_doe_seasonal_range_adds_band_average_comparisons_and_forecast(weekly: pd.Series) -> None:
    forecast = pd.DataFrame(
        {"EA latest": [468_000.0, 469_000.0, 470_000.0]},
        index=pd.date_range("2026-11-04", periods=3, freq="W-WED"),
    )
    figure = plot_doe_seasonal_range(
        weekly,
        current_year=2026,
        history_years=[2021, 2022, 2023, 2024, 2025],
        forecasts=forecast,
    )
    traces = {trace.name: trace for trace in figure.data}

    assert {"Min", "Max", "5Y Avg", "EA latest"}.issubset(traces)
    assert {"Cur Yr vs 5y Avg", "Cur Yr vs Y-1"}.issubset(traces)
    assert traces["Max"].fill == "tonexty"
    assert traces["EA latest"].line.dash == "dash"
    assert traces["2026"].line.color == "black"


def test_doe_seasonal_range_can_accumulate_stock_changes(weekly: pd.Series) -> None:
    changes = weekly.diff().rename("Weekly stock change")
    figure = plot_doe_seasonal_range(changes, current_year=2026, cumulative=True)
    traces = {trace.name: trace for trace in figure.data}
    by_year = ts_by_year(changes.to_frame(), frequency="W", column="Weekly stock change", dummy_date_index=True)
    cumulative = by_year.cumsum()
    np.testing.assert_allclose(traces["2026"].y, cumulative[2026], equal_nan=True)
    expected = cumulative[2026] - cumulative[[2018, 2019, 2021, 2023, 2024, 2025]].mean(axis=1)
    np.testing.assert_allclose(traces["Cur Yr vs 5y Avg"].y, expected, equal_nan=True)
    assert "2018-2025 Avg" in traces


def test_doe_inventory_signal_uses_seasonal_and_signal_panels(weekly: pd.Series) -> None:
    changes = weekly.pct_change().rolling(4).mean().mul(100).rename("4w stock change")
    zscore = pd.Series(
        np.linspace(-1, 1, 44), index=pd.date_range("2026-01-02", periods=44, freq="W-FRI"), name="4y z-score"
    )
    figure = plot_doe_inventory_signal(changes, zscore, current_year=2026)
    traces = {trace.name: trace for trace in figure.data}

    assert traces["2026"].yaxis == "y"
    assert traces["4y z-score"].yaxis == "y2"
    assert list(traces["4y z-score"].y) == pytest.approx(zscore.tolist())
    assert figure.layout.yaxis.title.text == "%"
    assert figure.layout.yaxis2.title.text == "z-score"


def test_doe_actual_vs_whisper_uses_shared_inventory_and_price_panels() -> None:
    index = pd.date_range("2026-01-02", periods=12, freq="W-FRI")
    observations = pd.DataFrame({"Actual": np.arange(12), "Whisper": np.arange(12) + 1}, index=index)
    price = pd.Series(np.linspace(70, 75, 12), index=index, name="WTI")
    figure = plot_doe_actual_vs_whisper(observations, price)
    traces = {trace.name: trace for trace in figure.data}

    assert traces["Actual"].yaxis == "y"
    assert traces["Whisper"].yaxis == "y"
    assert traces["WTI"].yaxis == "y2"
    assert figure.layout.xaxis.matches == "x2"
    assert figure.layout.yaxis.title.text == "kbbl"
    assert figure.layout.yaxis2.title.text == "Price"


def test_doe_plot_templates_validate_required_inputs(weekly: pd.Series) -> None:
    with pytest.raises(ValueError, match="history_years"):
        plot_doe_inventory_change(weekly, history_years=0)
    with pytest.raises(ValueError, match="Actual and Whisper"):
        plot_doe_actual_vs_whisper(weekly.to_frame("Actual"), weekly)
    with pytest.raises(TypeError, match="DatetimeIndex"):
        plot_doe_inventory_signal(weekly.reset_index(drop=True), weekly)
