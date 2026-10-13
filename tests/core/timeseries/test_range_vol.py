"""Range-Vol arithmetic and report conventions, without provider dependencies.

EMA/KPI values and signal dates below were checked against the recovered ECM
talib and market_scan_helpers functions, executed without their I/O imports.
The committed tests use fixed expectations and need no legacy checkout.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from runbook.core.timeseries import range_vol as rv


@pytest.fixture
def prices() -> pd.Series:
    x = np.arange(250, dtype=float)
    return pd.Series(100 + x * 0.03 + 4 * np.sin(x / 5) + np.cos(x / 2), index=pd.date_range("2026-02-06", periods=250))


def test_prepare_prices_fills_only_source_fields_and_does_not_mutate(prices: pd.Series) -> None:
    daily = pd.DataFrame({"PX_LAST": prices, "PX_OPEN": prices, "PX_HIGH": prices + 2, "PX_LOW": prices - 2})
    daily.iloc[-2, 0] = np.nan
    daily.iloc[-1, 1:3] = np.nan
    original = daily.copy()
    weekly = pd.DataFrame({"PX_LAST": prices.iloc[::5], "PX_HIGH": prices.iloc[::5] + 10})
    prepared = rv.prepare_price_data(daily.iloc[::-1], weekly)
    assert prepared is not None
    assert_series_equal(prepared["closep"], prices.rename("PX_LAST"))
    assert prepared["highp"].iloc[-1] == prices.iloc[-1]
    assert_series_equal(prepared["highp_w"], weekly.PX_LAST)
    assert prepared["closep_m"].empty
    assert prepared["imp_vol"].empty
    assert_frame_equal(daily, original)
    assert rv.prepare_price_data(daily.iloc[:30]) is None


def test_rejects_ambiguous_dates_and_misaligned_ohlc(prices: pd.Series) -> None:
    with pytest.raises(ValueError, match="unique"):
        rv.calculate_price_changes(pd.concat([prices, prices.iloc[:1]]), "FLAT")
    with pytest.raises(ValueError, match="same observation index"):
        rv.calculate_stochastic(prices.iloc[1:], prices, prices)
    with pytest.raises(ValueError, match="FLAT or SPRD"):
        rv.calculate_price_changes(prices, "invalid")


@pytest.mark.parametrize("kind, expected_daily, expected_5d", [("FLAT", 0.5, 7.0), ("SPRD", 8.0, 21.0)])
def test_price_changes_and_post_close(kind: str, expected_daily: float, expected_5d: float) -> None:
    close = pd.Series([3.0, 4.0, 8.0, 16.0, 24.0], index=pd.date_range("2026-01-01", periods=5))
    intraday = close.to_frame("close")
    out = rv.calculate_price_changes(close, kind, intraday)
    assert out["chg_5d"] == expected_5d
    assert out["price_change_pct"] == expected_daily
    assert out["price_change"] == 8
    assert out["price_change1"] == 8
    assert_series_equal(out["daily_price_chg"], out["intraday_price_chg"], check_names=False)
    daily = pd.DataFrame({"FUT_PX": [5.0, 10.0], "PX_SETTLE": [4.0, np.nan]}, index=close.index[-2:])
    assert rv.calculate_post_close(daily) == 1
    assert rv.calculate_post_close(close.to_frame("PX_LAST")) == 0


def test_ema_matches_source_seed_and_finite_history_tail(prices: pd.Series) -> None:
    result = rv.calculate_exponential_moving_average(prices, 30)
    assert result.iloc[:29].isna().all()
    np.testing.assert_allclose(
        result.iloc[[29, 30, 179, 180, 249]],
        [100.55186596379707, 100.45320687544536, 104.9438226767148, 104.68859414156722, 105.67465303317405],
        rtol=1e-12,
    )
    assert rv.calculate_exponential_moving_average(prices.iloc[:5], 30).isna().all()
    with pytest.raises(ValueError, match="positive integer"):
        rv.calculate_exponential_moving_average(prices, 0)


@pytest.mark.parametrize(
    "day, prior_spike", [("2026-01-12", 22 / 16), ("2026-01-13", 24 / 18), ("2026-01-11", 20 / 14)]
)
def test_range_spike_uses_preceding_atr_and_daily_date_rule(day: str, prior_spike: float) -> None:
    high = pd.Series(np.arange(1.0, 13.0), index=pd.date_range("2026-01-01", periods=12, tz="Europe/London"))
    result = rv.calculate_range_metrics(high, -high, high * 0, as_of=day)
    np.testing.assert_allclose(result["avg_true_range"][4:], np.arange(6.0, 21.0, 2))
    assert result["range_spike"] == pytest.approx(24 / 18)
    assert result["range_spike1"] == pytest.approx(prior_spike)
    close_only = rv.calculate_range_metrics(high, high, high, as_of=day)
    assert close_only["avg_true_range"][4] == pytest.approx(1.6)


def test_sharpe_windows_exclude_latest_daily_and_invert_only_cob() -> None:
    daily = pd.Series(np.arange(1.0, 26.0), index=pd.date_range("2026-09-19", periods=25))
    daily.iloc[-1] = 10000
    intraday = pd.Series(np.tile([1.0, 2.0, -1.0, 3.0], 42), index=pd.date_range("2026-10-07", periods=168, freq="h"))
    out = rv.calculate_sharpe_ratios(daily, intraday, instr="FI", chg_type="SPRD")
    expected_daily = np.arange(3.0, 25.0)
    assert out["sharpe_22d"] == pytest.approx(expected_daily.mean() / expected_daily.std(ddof=1) * np.sqrt(22))
    live = intraday.loc["2026-10-11":"2026-10-13"].iloc[1:]
    assert out["sharpe_3d"] == pytest.approx(live.mean() / live.std() * np.sqrt(len(live)))
    for lag in range(4):
        start = pd.Timestamp("2026-10-10") - pd.Timedelta(days=lag)
        end = pd.Timestamp("2026-10-12 23:59") - pd.Timedelta(days=lag)
        sample = intraday.loc[start:end].iloc[1:]
        key = "sharpe_3d_cob" + (f"_{lag}" if lag else "")
        assert out[key] == pytest.approx(-sample.mean() / sample.std() * np.sqrt(len(sample)))
    assert out["upload"] is True
    assert rv.calculate_sharpe_ratios(daily)["upload"] is False
    assert np.isnan(rv.calculate_sharpe_3d_cob(intraday.iloc[:10], intraday.index[0], intraday.index[-1], "FI", "SPRD"))


@pytest.mark.parametrize(
    "end, key, signal",
    [
        (33, "mom", "BUY"),
        (34, "mom1", "BUY"),
        (38, "hybrid", "BUY"),
        (39, "hybrid1", "BUY"),
        (48, "mom", "SELL"),
        (49, "mom1", "SELL"),
        (51, "hybrid", "SELL"),
        (52, "hybrid1", "SELL"),
    ],
)
def test_momentum_crossing_dates_match_recovered_source(prices: pd.Series, end: int, key: str, signal: str) -> None:
    assert rv.calculate_moving_average_signals(prices.iloc[:end])[key] == signal
    previous = rv.calculate_moving_average_signals(prices.iloc[: end - 1])
    assert previous[key] is None


def test_stochastic_and_price_flags() -> None:
    close = pd.Series(np.arange(1.0, 31.0), index=pd.date_range("2026-01-01", periods=30))
    assert rv.calculate_stochastic(close + 0.1, close - 0.1, close) == "OB"
    assert rv.calculate_stochastic(-close + 0.1, -close - 0.1, -close) == "OS"
    assert rv.calculate_stochastic(close[:10], close[:10], close[:10]) is None
    assert rv.calculate_three_day_trend(pd.Series([10.0, 5.0, 6.0, 7.0, 8.0])) == "UP"
    assert rv.calculate_three_day_trend(pd.Series([1.0, 5.0, 4.0, 3.0, 2.0])) == "DOWN"
    assert rv.calculate_three_day_trend(close) is None
    assert rv.calculate_current_price_range(close, close, close - 5) == "HIGH"
    assert rv.calculate_current_price_range(close, close + 5, close) == "LOW"


def test_fisher_bands_shift_weekly_monthly_before_forward_fill() -> None:
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0], index=pd.date_range("2026-01-01", periods=5))
    weekly = pd.Series([30.0, 60.0], index=close.index[[0, 3]])
    monthly = pd.Series([90.0], index=close.index[:1])
    result = rv.calculate_fisher_indicators(
        close + 3, close - 1, close, weekly + 3, weekly - 1, weekly, monthly + 3, monthly - 1, monthly
    )
    assert result["fdh"] == pytest.approx(15)
    assert result["fdl"] == pytest.approx(14 + 1 / 3)
    assert result["fwh"] == pytest.approx(61)
    assert result["fwh1"] == pytest.approx(31)
    assert result["fml2"] == pytest.approx(90 + 1 / 3)


def test_fisher_signal_cross_and_previous_flags() -> None:
    # A daily/weekly/monthly BUY cross; prior daily band was below weekly high.
    fisher = dict(
        zip(
            (f"f{period}{side}{lag}" for lag in ("", "1", "2") for period in ("d", "w", "m") for side in ("h", "l")),
            [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 5.0, 4.0, 5.0, 4.0, 3.0, 2.0, 5.0, 4.0, 5.0, 4.0, 3.0, 2.0],
            strict=True,
        )
    )
    flags = rv.determine_fisher_signals(fisher, pd.Series([3.0, 5.0, 7.0]))
    assert flags == ("BUY", None, None, None, None, None)
    assert rv.get_simple_fisher_signals(fisher) == (None, "B", None)


@pytest.mark.parametrize(
    "kind, name, expected",
    [
        ("FLAT", "CO", [0.7142096290210271, 0.6489681772363495, 0.03194131140449388]),
        ("FLAT", "GXA Index", [0.7142096290210271, 0.6556693064661273, 0.034940125650327544]),
        ("SPRD", "CO", [75.75658893206986, 68.06213984880992, 3.4297879029913987]),
    ],
)
def test_kpi_matches_source_conventions(prices: pd.Series, kind: str, name: str, expected: list[float]) -> None:
    vol = pd.Series(25.0, index=prices.index)
    vol.iloc[-2] = np.nan
    original = vol.copy()
    result = rv.calculate_kpi(prices, vol.to_frame(), prices.diff(), kind, name)
    np.testing.assert_allclose(list(result.values()), expected, rtol=1e-12)
    assert_series_equal(vol, original)


def test_kpi_realized_vol_fallback_and_gxa_midnight_cutoff(prices: pd.Series) -> None:
    returns = prices.pct_change(fill_method=None)
    result = rv.calculate_kpi(prices, None, returns, "FLAT")
    expected = prices.diff().iloc[-1] / (prices.iloc[-1] * returns.iloc[-31:-1].std())
    assert result["kpi_on"] == pytest.approx(expected)
    vol = pd.Series(25.0, index=prices.index)
    intraday = pd.DataFrame(
        {"close": [99.0, 100.0, 1000.0]},
        index=pd.to_datetime(["2026-10-12 23:50", "2026-10-13 00:00", "2026-10-13 00:10"]),
    )
    gxa = rv.calculate_kpi(prices, vol, returns, "FLAT", "GXA Index", intraday, as_of="2026-10-13")
    assert gxa["kpi_on"] == pytest.approx((prices.iloc[-1] - 100) / (100 * 0.25 / np.sqrt(252)))
    with pytest.raises(ValueError, match="as_of is required"):
        rv.calculate_kpi(prices, vol, returns, "FLAT", "GXA Index", intraday)


def test_trend_combined_and_sharpe_classification() -> None:
    trend = rv.calculate_trend_index(1, 1.3, 1.3, "UP", 1.5, 0, "HIGH", 0.3, [1.0, 1.0])
    assert trend == 5
    assert rv.calculate_trend_index(-1, 1.3, 1.3, "DOWN", -1.5, 0, "LOW", -0.3, [1.0, 1.0]) == -5
    combined = rv.determine_combined_signals(trend, 1, None, "BUY", "BUY", None, None, None, None, None, "SELL", None)
    assert combined["mom_signal"] == combined["mom_signal_ystd"] == "BUY"
    assert combined["hybrid_signal"] == "BUY"
    assert combined["hybrid_signal_ystd"] is None
    assert combined["counter_signal"] is None
    assert rv.calculate_signal_flag(combined, 0) == 1
    assert rv.calculate_signal_flag({}, 3) == 0
    assert rv.calculate_signal_flag({}, -3.1) == 1
    assert rv.classify_sharpe_signal(1, 1) == "TREND"
    assert rv.classify_sharpe_signal(-2, 1) == "COUNTER"
    assert rv.classify_sharpe_signal(1, -0.5) == "-"


def test_fom_dates_interval_scoring_and_provider_vwap() -> None:
    dates = pd.date_range("2026-01-01", periods=31)
    changes = pd.Series(np.arange(1.0, 32.0), index=dates)
    close = changes + 100
    flag, score, label = rv.calculate_fom_metrics("01/21/2026", changes, close + 1, close - 1, close, as_of=dates[-1])
    assert flag == "A+"
    assert score == pytest.approx(21 / np.arange(1.0, 21.0).std(ddof=1))
    assert label == dates[20]
    interval = rv.calculate_fom_metrics(
        "2026-01-21 - 2026-01-23", changes, close + 1, close - 1, close, as_of=dates[-1]
    )
    assert interval[0] == "A+"
    assert interval[1] == pytest.approx((21 + 22 + 23) / np.arange(1.0, 21.0).std(ddof=1))
    assert interval[2] == "2026-01-21 - 2026-01-23"
    assert rv.parse_fom_date("2026-02-01 - 2026-02-05", as_of=dates[-1]) == (dates[0], pd.Timestamp("2026-02-05"))
    assert rv.parse_fom_date("2026-02-01", as_of=dates[-1]) == pd.Timestamp("2026-02-01")
    assert rv.calculate_fom_metrics(None, changes, close + 1, close - 1, close, as_of=dates[-1]) == (None, None, None)
    assert rv.calculate_fom_vwap(120.126, close.to_frame("close")) == (120.126, 10.87)


@pytest.fixture
def volume_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    days = pd.bdate_range("2026-09-01", periods=25)
    stamps = [day + pd.Timedelta(hours=9, minutes=minute) for day in days for minute in (0, 10, 20)]
    intraday = pd.DataFrame({"volume": np.repeat(np.arange(1.0, 26.0), 3)}, index=stamps)
    # A later observation in a historical session must not leak into its comparison.
    intraday.loc[days[-2] + pd.Timedelta(hours=10), "volume"] = 100000
    return intraday.sort_index(), pd.DataFrame({"VOLUME": np.arange(1.0, 26.0) * 3}, index=days)


def test_volume_ratios_compare_same_clock_time_and_prior_days(volume_frames: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    intraday, daily = volume_frames
    result = rv.calculate_volume_spikes(intraday, daily, as_of=daily.index[-1])
    np.testing.assert_allclose(result["volume_at_minute"], np.arange(1.0, 26.0) * 3)
    assert result["volume_spike_5d"] == pytest.approx(25 / 22)
    assert result["volume_spike_20d"] == pytest.approx(25 / 14.5)
    assert result["volume_spike_5d_1"] == pytest.approx(24 / 21)
    stale = rv.calculate_volume_spikes(intraday, daily, as_of=daily.index[-1] + pd.Timedelta(days=1))
    assert np.isnan(stale["volume_spike_5d"])
    assert stale["volume_spike_5d_1"] == pytest.approx(25 / 22)


def test_volume_grid_missing_bars_weekends_and_roll(volume_frames: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    intraday, daily = volume_frames
    intraday = intraday.drop(intraday.index[1])
    intraday.loc[pd.Timestamp("2026-09-05 09:20"), "volume"] = 999999
    sample = rv.calculate_cumulative_volume(intraday)
    assert sample.iloc[0] == 2
    assert len(sample) == 25
    previous = sample * 10
    boundary = sample.index[-3].normalize()
    adjusted = rv.adjust_volume_for_roll(sample, previous, boundary, as_of=sample.index[-1])
    assert_series_equal(adjusted.iloc[:-3], previous.iloc[:-3])
    assert_series_equal(adjusted.iloc[-3:], sample.iloc[-3:])
    unchanged = rv.adjust_volume_for_roll(sample, previous, sample.index[0], as_of=sample.index[-1])
    assert_series_equal(unchanged, sample)
    result = rv.calculate_volume_spikes(
        intraday, daily, as_of=sample.index[-1], previous_volume=previous, roll_date=boundary
    )
    assert_series_equal(result["volume_at_minute"], adjusted)
    with pytest.raises(ValueError, match="supplied together"):
        rv.calculate_volume_spikes(intraday, daily, as_of=sample.index[-1], roll_date=boundary)


def test_divergence_uses_settled_row_scaling_and_move_filter() -> None:
    dates = pd.date_range("2026-09-01", periods=30)
    flat = pd.Series(np.arange(30, dtype=float) ** 2, index=dates)
    spread = -2 * flat
    spread.iloc[-1] = 99999
    result = rv.calculate_divergence(spread, flat, as_of=dates[-1], scale=0.42)
    assert result["Sprd change"] == -110
    assert result["Flat change"] == 55
    assert result["3d divergence"] == pytest.approx(-0.84)
    assert result["8d divergence"] == pytest.approx(-0.84)
    inverse = rv.calculate_divergence(spread, flat, as_of=dates[-1], invert_spread=True, min_move_zscore=1.5)
    assert inverse["3d divergence"] == pytest.approx(2)
    invalid = rv.calculate_divergence(spread, flat, as_of=dates[-1], min_move_zscore=100)
    assert np.isnan(invalid["3d divergence"])
    settled = rv.calculate_divergence(spread.iloc[:-1], flat.iloc[:-1], as_of=dates[-1], scale=0.42)
    assert settled == result


def test_fly_switches_and_weighted_risk_index() -> None:
    frame = pd.DataFrame(
        {"M1-M2": [3.0, 1.0], "M2-M3": [2.0, 2.0], "M3-M4": [1.0, 2.0]}, index=pd.date_range("2026-10-12", periods=2)
    )
    flies = rv.calculate_fly_switches(frame)
    np.testing.assert_allclose(flies, [[-1.0, 1.0, -2.0], [0.0, 1.0, -1.0]])
    metrics = pd.DataFrame({"KPI": [2.0, 4.0], "Sharpe": [np.nan, np.nan]}, index=["Oil", "Gas"])
    assert rv.calculate_weighted_risk_index(metrics, {"Oil": 1, "Gas": 3})["KPI"] == 14
    assert rv.calculate_weighted_risk_index(metrics, {"Oil": 1, "Gas": 3}, normalize=True)["KPI"] == 3.5
    assert np.isnan(rv.calculate_weighted_risk_index(metrics, {"Oil": 1})["Sharpe"])
    with pytest.raises(ValueError, match="zero-sum"):
        rv.calculate_weighted_risk_index(metrics, {"Oil": 1, "Gas": -1}, normalize=True)
