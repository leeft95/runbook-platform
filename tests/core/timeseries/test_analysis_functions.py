from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import pytest
from runbook.core.timeseries.analysis import (
    calculate_bollinger_bands,
    calculate_change,
    calculate_donchain_channel,
    calculate_fisher_indicator,
    calculate_historical_mean_std_for_date,
    calculate_moving_average,
    calculate_percential_rank,
    calculate_regressions,
    calculate_stochastic_indicator,
    calculate_true_range,
)


def test_calculate_moving_average_simple_and_alias() -> None:
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    expected = np.array([2.0, 3.0, 4.0], dtype=np.float64)

    out_simple = np.asarray(calculate_moving_average(values, window=3, kind="simple"), dtype=np.float64)
    out_alias = np.asarray(calculate_moving_average(values, window=3, kind="s"), dtype=np.float64)

    np.testing.assert_allclose(out_simple, expected)
    np.testing.assert_allclose(out_alias, expected)


def test_calculate_bollinger_bands_known_values() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    upper, lower, bandwidth, pct_b, middle = calculate_bollinger_bands(series, window=3, num_std_dev=2.0)

    std = np.sqrt(2.0 / 3.0)
    expected_middle = np.array([2.0, 3.0, 4.0], dtype=np.float64)
    expected_upper = expected_middle + 2.0 * std
    expected_lower = expected_middle - 2.0 * std

    np.testing.assert_allclose(middle.to_numpy(), expected_middle, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(upper.to_numpy(), expected_upper, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(lower.to_numpy(), expected_lower, rtol=1e-12, atol=1e-12)

    expected_pct_b = (np.array([3.0, 4.0, 5.0]) - expected_lower) / (expected_upper - expected_lower)
    expected_bandwidth = (expected_upper - expected_lower) / expected_middle
    np.testing.assert_allclose(pct_b.to_numpy(), expected_pct_b, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(bandwidth.to_numpy(), expected_bandwidth, rtol=1e-12, atol=1e-12)


def test_calculate_change_known_outputs() -> None:
    values = np.array([1.0, 2.0, 4.0], dtype=np.float64)
    np.testing.assert_allclose(calculate_change(values, flag="d", n=1), np.array([0.0, 1.0, 2.0]))
    np.testing.assert_allclose(calculate_change(values, flag="p", n=1), np.array([0.0, 1.0, 1.0]))
    np.testing.assert_allclose(calculate_change(values, flag="l", n=1), np.array([0.0, np.log(2.0), np.log(2.0)]))


def test_calculate_percential_rank_ties_and_interpolation() -> None:
    values = np.array([1.0, 2.0, 2.0, 4.0], dtype=np.float64)
    assert calculate_percential_rank(values, 2.0) == 0.5
    assert calculate_percential_rank(values, 0.0) == 0.0
    assert calculate_percential_rank(values, 5.0) == 1.0
    assert calculate_percential_rank(values, 3.0) == 0.875


def test_calculate_regressions_full_sample_and_rolling_known_linear_case() -> None:
    x = pd.Series([0.0, 1.0, 2.0, 3.0, 4.0])
    y = pd.Series([1.0, 3.0, 5.0, 7.0, 9.0])

    alpha, beta, rsqr, rmse = calculate_regressions(x, y, constant=True, rolling=False)
    assert np.isclose(alpha, 1.0)
    assert np.isclose(beta, 2.0)
    assert np.isclose(rsqr, 1.0)
    assert np.isclose(rmse, 0.0)

    rolling_out = cast(
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
        calculate_regressions(x, y, window=3, constant=True, rolling=True),
    )
    r_alpha, r_beta, r_rsqr, r_rmse = rolling_out
    np.testing.assert_allclose(r_alpha[:2], np.array([0.0, 0.0]))
    np.testing.assert_allclose(r_beta[:2], np.array([0.0, 0.0]))
    np.testing.assert_allclose(r_alpha[2:], np.array([1.0, 1.0, 1.0]), atol=1e-10)
    np.testing.assert_allclose(r_beta[2:], np.array([2.0, 2.0, 2.0]), atol=1e-10)
    np.testing.assert_allclose(r_rsqr[2:], np.array([1.0, 1.0, 1.0]), atol=1e-10)
    np.testing.assert_allclose(r_rmse[2:], np.array([0.0, 0.0, 0.0]), atol=1e-10)


def test_calculate_true_range_known_outputs_and_rolling() -> None:
    high = np.array([10.0, 12.0, 11.0], dtype=np.float64)
    low = np.array([9.0, 10.0, 8.0], dtype=np.float64)
    close = np.array([9.5, 11.0, 9.0], dtype=np.float64)

    tr = np.asarray(calculate_true_range(high, low, close), dtype=np.float64)
    np.testing.assert_allclose(tr, np.array([1.0, 2.5, 3.0], dtype=np.float64))

    atr = np.asarray(
        calculate_true_range(high, low, close, window=2, rolling=True, rolling_kind="simple"), dtype=np.float64
    )
    np.testing.assert_allclose(atr, np.array([np.nan, 1.75, 2.75], dtype=np.float64), equal_nan=True)

    atr_mean = calculate_true_range(high, low, close, window=None, rolling=True)
    assert atr_mean == np.mean(tr)

    close_only = np.asarray(calculate_true_range(np.array([1.0, 3.0, 2.0])), dtype=np.float64)
    np.testing.assert_allclose(close_only, np.array([0.0, 4.0, 2.0], dtype=np.float64))


def test_calculate_donchain_channel_known_signal() -> None:
    idx = pd.RangeIndex(4)
    high = pd.Series([1.0, 2.0, 2.0, 3.0], index=idx)
    low = pd.Series([0.0, 1.0, 1.0, 2.0], index=idx)
    close = pd.Series([0.5, 1.5, 2.5, 2.2], index=idx)

    upper, lower, signal = calculate_donchain_channel(high, low, close, window=2)
    np.testing.assert_allclose(upper.to_numpy(), np.array([np.nan, 2.0, 2.0, 3.0]), equal_nan=True)
    np.testing.assert_allclose(lower.to_numpy(), np.array([np.nan, 0.0, 1.0, 1.0]), equal_nan=True)
    np.testing.assert_allclose(signal.to_numpy(), np.array([0.0, 0.0, 1.0, 1.0]))


def test_calculate_stochastic_indicator_known_outputs() -> None:
    high = np.array([10.0, 12.0, 14.0], dtype=np.float64)
    low = np.array([0.0, 2.0, 4.0], dtype=np.float64)
    close = np.array([5.0, 7.0, 10.0], dtype=np.float64)

    k_percent, d_percent, sd_percent = calculate_stochastic_indicator(
        high, low, close, k_window=1, slow_d_window=2, sd=2
    )
    np.testing.assert_allclose(k_percent, np.array([50.0, 50.0, 60.0]))
    np.testing.assert_allclose(d_percent, np.array([50.0, 55.0]))
    np.testing.assert_allclose(sd_percent, np.array([52.5]))


def test_calculate_fisher_indicator_known_outputs() -> None:
    high = np.array([10.0, 12.0], dtype=np.float64)
    low = np.array([8.0, 10.0], dtype=np.float64)
    close = np.array([12.0, 9.0], dtype=np.float64)

    fisher_high, fisher_low = calculate_fisher_indicator(high, low, close)
    np.testing.assert_allclose(fisher_high, np.array([11.0, 11.0]), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(fisher_low, np.array([9.0, 29.0 / 3.0]), rtol=1e-12, atol=1e-12)


def test_calculate_historical_mean_std_for_last_day_non_seasonal() -> None:
    index = pd.to_datetime(["2019-01-01", "2020-01-01", "2021-01-01", "2022-01-01"])
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0]}, index=index)

    out = calculate_historical_mean_std_for_date(
        df,
        seasonal=None,
        excluded_years=[2020],
        ranking_date=pd.Timestamp("2022-01-01"),
    )

    assert list(out.index) == ["a", "b"]
    assert out.loc["a", "mean"] == 2.0
    assert out.loc["a", "std"] == pytest.approx(2**0.5)
    assert out.loc["b", "mean"] == 4.0
    assert out.loc["b", "std"] == pytest.approx(2 * (2**0.5))


def test_calculate_historical_mean_std_for_last_day_seasonal() -> None:
    index = pd.to_datetime(["2019-01-10", "2020-01-10", "2021-01-10", "2022-01-10"])
    df = pd.DataFrame({"x": [10.0, 12.0, 14.0, 16.0]}, index=index)

    out = calculate_historical_mean_std_for_date(
        df,
        seasonal=2,
        excluded_years=None,
        ranking_date=pd.Timestamp("2022-01-10"),
    )

    assert out.loc["x", "mean"] == 13.0
    assert out.loc["x", "std"] == pytest.approx(2**0.5)
