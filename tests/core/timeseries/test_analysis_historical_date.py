from __future__ import annotations

import numpy as np
import pandas as pd
from runbook.core.timeseries.analysis import (
    _get_historical_data_on_date,
    calculate_historical_mean_std_for_date,
)


def test_get_historical_data_on_date_uses_calendar_day_with_leap_fallback() -> None:
    idx = pd.date_range("2019-01-01", "2022-03-15", freq="D")
    year_values = idx.year.astype(float)
    df = pd.DataFrame({"x": year_values, "y": year_values + 10.0}, index=idx)

    out = _get_historical_data_on_date(df, pd.Timestamp("2020-02-29"))

    assert out.index.is_monotonic_increasing
    assert {(int(ts.month), int(ts.day)) for ts in out.index} == {(2, 28)}
    assert out["x"].tolist() == [2019.0, 2020.0, 2021.0, 2022.0]
    assert out["y"].tolist() == [2029.0, 2030.0, 2031.0, 2032.0]


def test_calculate_historical_mean_std_for_date_seasonal_respects_excluded_years() -> None:
    idx = pd.date_range("2018-01-01", "2023-12-31", freq="D")
    df = pd.DataFrame({"x": idx.year.astype(float)}, index=idx)

    out = calculate_historical_mean_std_for_date(
        df,
        seasonal=3,
        excluded_years=[2021],
        ranking_date=pd.Timestamp("2023-01-10"),
    )

    expected_history = pd.Series([2019.0, 2020.0, 2022.0], dtype=np.float64)
    assert np.isclose(float(out.loc["x", "mean"]), float(expected_history.mean()))
    assert np.isclose(float(out.loc["x", "std"]), float(expected_history.std()))


def test_calculate_historical_mean_std_for_date_window_mode_uses_window_arg() -> None:
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame({"x": np.linspace(1.0, 30.0, num=30)}, index=idx)

    out = calculate_historical_mean_std_for_date(df, seasonal=None, window=5)

    expected_mean = float(df["x"].rolling(5).mean().iloc[-2])
    expected_std = float(df["x"].rolling(5).std().iloc[-2])
    assert np.isclose(float(out.loc["x", "mean"]), expected_mean)
    assert np.isclose(float(out.loc["x", "std"]), expected_std)
