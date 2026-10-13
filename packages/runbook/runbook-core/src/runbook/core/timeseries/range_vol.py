"""Data-only calculations from market_scan_helpers and range_vol_am.

Inputs are copied. Dates that affect a result are explicit ``as_of`` arguments;
there are no provider, filesystem, plotting or delivery dependencies. The
report's FLAT/SPRD conventions, observation windows and signal thresholds are
preserved. See the range-vol calculation guide for source limitations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from .analysis import calculate_fisher_indicator, calculate_stochastic_indicator, calculate_true_range

ChangeType = Literal["FLAT", "SPRD"]


def _series(values: pd.Series, minimum: int = 0) -> pd.Series:
    """Copy and order a numeric series, rejecting ambiguous observations."""
    if not isinstance(values, pd.Series):
        raise TypeError("Expected a pandas Series")
    if values.index.hasnans or not values.index.is_unique:
        raise ValueError("Observation indices must be unique and non-missing")
    if len(values) < minimum:
        raise ValueError(f"Expected at least {minimum} observations")
    return values.astype(float).sort_index()


def _frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and copy a dated input frame without filling missing observations."""
    if not isinstance(frame, pd.DataFrame) or not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("Expected a DataFrame with a DatetimeIndex")
    if frame.index.hasnans or not frame.index.is_unique or not frame.columns.is_unique:
        raise ValueError("Dates and columns must be unique, and dates non-missing")
    return frame.sort_index().copy()


def _ohlc(high: pd.Series, low: pd.Series, close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Validate OHLC alignment before positional indicator calculations."""
    high, low, close = (_series(series) for series in (high, low, close))
    if not high.index.equals(close.index) or not low.index.equals(close.index):
        raise ValueError("High, low and close must have the same observation index")
    return high, low, close


def _timestamp(value: Any, index: pd.DatetimeIndex) -> pd.Timestamp:
    """Express a boundary in the input's timezone, preserving naive local dates."""
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("Date-based calculations require a DatetimeIndex")
    value = pd.Timestamp(value)
    if pd.isna(value):
        raise ValueError("Date boundaries must not be missing")
    if index.tz is None:
        return value.tz_localize(None)
    return value.tz_localize(index.tz) if value.tz is None else value.tz_convert(index.tz)


def _ratio(numerator: float, denominator: float) -> float:
    """Preserve the source's NaN/inf division semantics without runtime warnings."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(np.divide(numerator, denominator))


def _tail(values: Any, offset: int = 1) -> float:
    """Return a trailing numeric observation, or NaN during warmup."""
    return float(np.asarray(values)[-offset]) if len(values) >= offset else float("nan")


def _change_type(chg_type: str) -> None:
    """Reject unsupported return conventions."""
    if chg_type not in {"FLAT", "SPRD"}:
        raise ValueError("chg_type must be FLAT or SPRD")


def calculate_exponential_moving_average(values: pd.Series, window: int) -> pd.Series:
    """Reproduce ECM mva(type='e'), including its finite-history tail.

    Alpha is 2/(window+1), seeded with the first window's arithmetic mean.
    Recursion runs through the next 5*window observations; subsequent values
    use the source's normalized 5*window exponential kernel. Output retains
    the input index and has window-1 leading NaNs. Short samples stay NaN.
    This is deliberately distinct from analysis.calculate_moving_average.
    """
    values = _series(values)
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("window must be a positive integer")
    if len(values) < window:
        return pd.Series(np.nan, index=values.index, name=values.name)
    prices = values.to_numpy()
    alpha = 2.0 / (window + 1)
    weights = (1 - alpha) ** np.arange(window * 5)
    weights /= weights.sum()
    padded = np.concatenate((np.repeat(prices[0], window * 5), prices))
    result = np.convolve(padded, weights, mode="full")[window * 5 : window * 5 + len(prices)]
    result[: window - 1] = np.nan
    result[window - 1] = prices[:window].mean()
    for i in range(window, min(len(prices), window * 6)):
        result[i] = alpha * prices[i] + (1 - alpha) * result[i - 1]
    return pd.Series(result, index=values.index, name=values.name)


def prepare_price_data(
    daily_price: pd.DataFrame, weekly_price: pd.DataFrame | None = None, monthly_price: pd.DataFrame | None = None
) -> dict[str, pd.Series] | None:
    """Copy Bloomberg-style OHLC frames into the report's price-series dictionary.

    Daily input needs more than 30 rows and PX_LAST. When all OHLC fields exist,
    missing O/H/L use close, missing close uses the H/L midpoint, then prices
    forward-fill. Absent H/L fields use close. Weekly/monthly frames are optional;
    their missing H/L fields fall back together to close, without filling.
    No timeframe is synthesized from daily data.
    """
    daily = _frame(daily_price)
    if len(daily) <= 30 or "PX_LAST" not in daily:
        return None
    if {"PX_OPEN", "PX_HIGH", "PX_LOW"}.issubset(daily):
        for column in ("PX_OPEN", "PX_HIGH", "PX_LOW"):
            daily[column] = daily[column].fillna(daily.PX_LAST)
        daily["PX_LAST"] = daily.PX_LAST.fillna((daily.PX_HIGH + daily.PX_LOW) / 2)
        fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
        daily[fields] = daily[fields].ffill()
    close = _series(daily.PX_LAST)
    result = {
        "closep": close,
        "highp": _series(daily.get("PX_HIGH", close)),
        "lowp": _series(daily.get("PX_LOW", close)),
        "imp_vol": _series(daily.get("3MTH_IMPVOL_100.0%MNY_DF", pd.Series(dtype=float))),
    }
    for suffix, frame in (("_w", weekly_price), ("_m", monthly_price)):
        frame = _frame(frame) if frame is not None else pd.DataFrame()
        close = _series(frame.PX_LAST) if "PX_LAST" in frame else pd.Series(dtype=float)
        has_range = {"PX_HIGH", "PX_LOW"}.issubset(frame) and not close.empty
        result.update(
            {
                f"closep{suffix}": close,
                f"highp{suffix}": _series(frame.PX_HIGH) if has_range else close.copy(),
                f"lowp{suffix}": _series(frame.PX_LOW) if has_range else close.copy(),
            }
        )
    return result


def calculate_price_changes(
    closep: pd.Series, chg_type: ChangeType, intraday_price: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Return FLAT fractional changes or SPRD absolute differences.

    Retains the source's chg_5d convention: last observation versus the fifth
    from last (four intervals). Intraday input uses a column named close.
    Missing observations are never filled by a return calculation.
    """
    _change_type(chg_type)
    closep = _series(closep, 5)
    changes = closep.diff()
    daily = changes / closep.shift() if chg_type == "FLAT" else changes
    intraday = pd.Series(dtype=float)
    if intraday_price is not None and not intraday_price.empty:
        prices = _series(_frame(intraday_price)["close"])
        intraday = prices.diff() / prices.shift() if chg_type == "FLAT" else prices.diff()
    return {
        "last_price": closep.iloc[-1],
        "price_change": changes.iloc[-1],
        "price_change1": changes.iloc[-2],
        "price_change_pct": daily.iloc[-1],
        "price_change_pct1": daily.iloc[-2],
        "daily_price_chg": daily,
        "chg_5d": _ratio(closep.iloc[-1] - closep.iloc[-5], closep.iloc[-5])
        if chg_type == "FLAT"
        else closep.iloc[-1] - closep.iloc[-5],
        "intraday_price_chg": intraday,
    }


def calculate_post_close(daily_price: pd.DataFrame) -> float:
    """Return FUT_PX minus settlement, falling back one row if latest settlement is missing."""
    daily = _frame(daily_price)
    if daily.empty or not {"FUT_PX", "PX_SETTLE"}.issubset(daily):
        return 0.0
    offset = 2 if pd.isna(daily.PX_SETTLE.iloc[-1]) else 1
    return float(daily.FUT_PX.iloc[-offset] - daily.PX_SETTLE.iloc[-offset]) if len(daily) >= offset else 0.0


def calculate_sharpe_3d_cob(
    intraday_price_chg: pd.Series, sdate_3d_cob: Any, edate_3d_cob: Any, instr: str, chg_type: ChangeType
) -> float:
    """Return mean/std(ddof=1)*sqrt(n), dropping the window's first intraday return.

    At least 11 observations are required before that drop. FI/SPRD changes
    are sign-inverted for COB, as in the source. Zero variance keeps inf/NaN.
    """
    _change_type(chg_type)
    changes = _series(intraday_price_chg)
    if changes.empty:
        return float("nan")
    start, end = (_timestamp(value, changes.index) for value in (sdate_3d_cob, edate_3d_cob))
    changes = changes.loc[start:end]
    if len(changes) <= 10:
        return float("nan")
    changes = changes.iloc[1:] * (-1 if instr == "FI" and chg_type == "SPRD" else 1)
    return _ratio(changes.mean(), changes.std()) * np.sqrt(len(changes))


def calculate_sharpe_ratios(
    daily_price_chg: pd.Series,
    intraday_price_chg: pd.Series | None = None,
    instr: str = "",
    chg_type: ChangeType = "FLAT",
) -> dict[str, float | bool]:
    """Return 22-observation, live 3-day and four successive COB Sharpe values.

    The 22-observation sample excludes the latest daily row. Live windows use
    the final three supplied daily dates; COB windows precede that window.
    Unlike COB, the source's live FI/SPRD metric is not inverted. ``upload``
    only reports availability of a finite live metric; nothing is published.
    """
    _change_type(chg_type)
    daily = _series(daily_price_chg, 1)
    sample = daily.iloc[-23:-1]
    result = {
        key: float("nan")
        for key in ("sharpe_3d", "sharpe_3d_cob", "sharpe_3d_cob_1", "sharpe_3d_cob_2", "sharpe_3d_cob_3")
    }
    result["sharpe_22d"] = _ratio(sample.mean(), sample.std()) * np.sqrt(22)
    intraday = _series(intraday_price_chg) if intraday_price_chg is not None else pd.Series(dtype=float)
    if not intraday.empty and len(daily) >= 3:
        end = daily.index[-1] + pd.Timedelta(hours=23, minutes=59)
        result["sharpe_3d"] = calculate_sharpe_3d_cob(intraday, daily.index[-3], end, "", chg_type)
        for lag in range(4):
            if len(daily) < 4 + lag:
                continue
            start = daily.index[-4 - lag]
            end = daily.index[-2 - lag] + pd.Timedelta(hours=23, minutes=59)
            latest_cob = daily.index[-2] + pd.Timedelta(hours=23, minutes=59)
            if intraday.index[-1] > _timestamp(latest_cob - BDay(10), intraday.index) or instr == "RISK":
                key = "sharpe_3d_cob" + (f"_{lag}" if lag else "")
                result[key] = calculate_sharpe_3d_cob(intraday, start, end, instr, chg_type)
    return {**result, "upload": bool(np.isfinite(result["sharpe_3d"]))}


def calculate_range_metrics(highp: pd.Series, lowp: pd.Series, closep: pd.Series, *, as_of: Any) -> dict[str, Any]:
    """Divide true range by the preceding five-observation ECM EMA of true range.

    range_spike uses the latest observation. range_spike1 uses the previous
    row for an as_of-day last row, the latest for stale data, or the third
    from last for a future-dated last row, retaining the source's date rule.
    """
    high, low, close = _ohlc(highp, lowp, closep)
    if close.empty:
        return {"range_spike": np.nan, "range_spike1": np.nan, "avg_true_range": np.array([])}
    true_range = np.atleast_1d(calculate_true_range(high, low, close))
    true_range[0] = high.iloc[0] - low.iloc[0]
    average = calculate_exponential_moving_average(pd.Series(true_range, index=close.index), 5).to_numpy()
    day = _timestamp(as_of, close.index).normalize()
    offset = 2 if close.index[-1] == day else 1 if close.index[-1] < day else 3
    return {
        "range_spike": _ratio(_tail(true_range), _tail(average, 2)),
        "range_spike1": _ratio(_tail(true_range, offset), _tail(average, offset + 1)),
        "avg_true_range": average,
    }


def calculate_stochastic(highp: pd.Series, lowp: pd.Series, closep: pd.Series) -> str | None:
    """Return OB/OS and crossing flags from the report's 13/3/3 stochastic."""
    high, low, close = _ohlc(highp, lowp, closep)
    if len(close) < 18:
        return None
    _, d, slow = calculate_stochastic_indicator(high, low, close, 13, 3, 3)
    if d[-1] > 80 and slow[-1] > 80:
        return "OB CROSS" if d[-2] > slow[-2] and d[-1] < slow[-1] else "OB"
    if d[-1] < 20 and slow[-1] < 20:
        return "OS CROSS" if d[-2] < slow[-2] and d[-1] > slow[-1] else "OS"
    return None


def calculate_fisher_indicators(
    highp: pd.Series,
    lowp: pd.Series,
    closep: pd.Series,
    highp_w: pd.Series,
    lowp_w: pd.Series,
    closep_w: pd.Series,
    highp_m: pd.Series,
    lowp_m: pd.Series,
    closep_m: pd.Series,
) -> dict[str, float]:
    """Return daily/weekly/monthly Fisher price bands for the last three daily rows.

    Weekly/monthly values are reindexed to daily dates, shifted one daily row,
    then forward-filled, matching the source's period-label convention.
    Supply weekly/monthly observations labelled on dates present in daily data;
    absent dates are not silently shifted to a different session.
    """
    daily = _ohlc(highp, lowp, closep)
    result = {}
    for prefix, triple in (
        ("d", daily),
        ("w", _ohlc(highp_w, lowp_w, closep_w)),
        ("m", _ohlc(highp_m, lowp_m, closep_m)),
    ):
        for side, values in zip(("h", "l"), calculate_fisher_indicator(*triple), strict=True):
            series = pd.Series(values, index=triple[2].index)
            if prefix != "d":
                series = series.reindex(daily[2].index).shift().ffill()
            for lag in range(3):
                result[f"f{prefix}{side}" + (str(lag) if lag else "")] = _tail(series, lag + 1)
    return result


def calculate_three_day_trend(closep: pd.Series) -> str | None:
    """Determine 3-day price trend"""
    closep = _series(closep)
    if len(closep) < 5:
        return None
    if closep.iloc[-1] > closep.iloc[-2] > closep.iloc[-3] > closep.iloc[-4] and closep.iloc[-4] < closep.iloc[-5]:
        return "UP"
    elif closep.iloc[-1] < closep.iloc[-2] < closep.iloc[-3] < closep.iloc[-4] and closep.iloc[-4] > closep.iloc[-5]:
        return "DOWN"
    return None


def calculate_current_price_range(closep: pd.Series, highp: pd.Series, lowp: pd.Series) -> str | None:
    """Determine if current price is at high or low of range"""
    highp, lowp, closep = _ohlc(highp, lowp, closep)
    if closep.empty:
        return None
    if closep.iloc[-1] > highp.iloc[-1] - (highp.iloc[-1] - lowp.iloc[-1]) * 0.1:
        return "HIGH"
    elif closep.iloc[-1] < lowp.iloc[-1] + (highp.iloc[-1] - lowp.iloc[-1]) * 0.1:
        return "LOW"
    return None


def determine_fisher_signals(fisher: Mapping[str, float], closep: pd.Series) -> tuple[str | None, ...]:
    """Determine buy/sell signals from Fisher indicators"""
    closep = _series(closep, 3)
    if (
        fisher["fdl"] > fisher["fwh"]
        and fisher["fwh"] > fisher["fmh"]
        and (fisher["fwl"] > fisher["fml"])
        and (closep.iloc[-1] > fisher["fwl"])
        and (fisher["fdl1"] < fisher["fwh1"] or fisher["fwh1"] < fisher["fmh1"] or fisher["fwl1"] < fisher["fml1"])
    ):
        fish = "BUY"
    elif (
        fisher["fdh"] < fisher["fwl"]
        and fisher["fwl"] < fisher["fml"]
        and (fisher["fwh"] < fisher["fmh"])
        and (closep.iloc[-1] < fisher["fwh"])
        and (fisher["fdh1"] > fisher["fwl1"] or fisher["fwl1"] > fisher["fml1"] or fisher["fwh1"] > fisher["fmh1"])
    ):
        fish = "SELL"
    else:
        fish = None
    if (
        fisher["fdl1"] > fisher["fwh1"]
        and fisher["fwh1"] > fisher["fmh1"]
        and (fisher["fwl1"] > fisher["fml1"])
        and (closep.iloc[-2] > fisher["fwl1"])
        and (fisher["fdl2"] < fisher["fwh2"] or fisher["fwh2"] < fisher["fmh2"] or fisher["fwl2"] < fisher["fml2"])
    ):
        fish1 = "BUY"
    elif (
        fisher["fdh1"] < fisher["fwl1"]
        and fisher["fwl1"] < fisher["fml1"]
        and (fisher["fwh1"] < fisher["fmh1"])
        and (closep.iloc[-2] < fisher["fwh1"])
        and (fisher["fdh2"] > fisher["fwl2"] or fisher["fwl2"] > fisher["fml2"] or fisher["fwh2"] > fisher["fmh2"])
    ):
        fish1 = "SELL"
    else:
        fish1 = None
    if fisher["fwl"] > fisher["fmh"] and closep.iloc[-1] > fisher["fmh"] and (fisher["fwl1"] < fisher["fmh1"]):
        fishlt = "BUY"
    elif fisher["fwh"] < fisher["fml"] and closep.iloc[-1] < fisher["fml"] and (fisher["fwh1"] > fisher["fml1"]):
        fishlt = "SELL"
    else:
        fishlt = None
    if fisher["fwl1"] > fisher["fmh1"] and closep.iloc[-2] > fisher["fmh1"] and (fisher["fwl2"] < fisher["fmh2"]):
        fishlt1 = "BUY"
    elif fisher["fwh1"] < fisher["fml1"] and closep.iloc[-2] < fisher["fml1"] and (fisher["fwh2"] > fisher["fml2"]):
        fishlt1 = "SELL"
    else:
        fishlt1 = None
    if (
        closep.iloc[-1] > closep.iloc[-2]
        and closep.iloc[-1] > fisher["fwl"]
        and (fisher["fdl"] > fisher["fwh"])
        and (fisher["fwh"] < fisher["fml"])
        and (fisher["fdl1"] < fisher["fwh1"])
    ):
        counter = "BUY"
    elif (
        closep.iloc[-1] < closep.iloc[-2]
        and closep.iloc[-1] < fisher["fwh"]
        and (fisher["fdh"] < fisher["fwl"])
        and (fisher["fwl"] > fisher["fmh"])
        and (fisher["fdh1"] > fisher["fwl1"])
    ):
        counter = "SELL"
    else:
        counter = None
    if (
        closep.iloc[-2] > closep.iloc[-3]
        and closep.iloc[-2] > fisher["fwl1"]
        and (fisher["fdl1"] > fisher["fwh1"])
        and (fisher["fwh1"] < fisher["fml1"])
        and (fisher["fdl2"] < fisher["fwh2"])
    ):
        counter1 = "BUY"
    elif (
        closep.iloc[-2] < closep.iloc[-3]
        and closep.iloc[-2] < fisher["fwh1"]
        and (fisher["fdh1"] < fisher["fwl1"])
        and (fisher["fwl1"] > fisher["fmh1"])
        and (fisher["fdh2"] > fisher["fwl2"])
    ):
        counter1 = "SELL"
    else:
        counter1 = None
    return (fish, fish1, fishlt, fishlt1, counter, counter1)


def get_simple_fisher_signals(fisher: Mapping[str, float]) -> tuple[str | None, ...]:
    """Get simple (non-crossed) Fisher signals for previous period"""
    if fisher["fdl1"] > fisher["fwh1"] > fisher["fmh1"] and fisher["fwl1"] > fisher["fml1"]:
        fish2 = "B"
    elif fisher["fdh1"] < fisher["fwl1"] < fisher["fml1"] and fisher["fwh1"] < fisher["fmh1"]:
        fish2 = "S"
    else:
        fish2 = None
    if fisher["fwl1"] > fisher["fmh1"]:
        fishlt2 = "B"
    elif fisher["fwh1"] < fisher["fml1"]:
        fishlt2 = "S"
    else:
        fishlt2 = None
    if fisher["fdl1"] > fisher["fwh1"] and fisher["fwh1"] < fisher["fml"]:
        counter2 = "B"
    elif fisher["fdh1"] < fisher["fwl1"] and fisher["fwl1"] > fisher["fmh1"]:
        counter2 = "S"
    else:
        counter2 = None
    return (fish2, fishlt2, counter2)


def calculate_moving_average_signals(closep: pd.Series) -> dict[str, Any]:
    """Calculate exponential moving average based signals"""
    closep = _series(closep, 3)
    emva3 = calculate_exponential_moving_average(closep, 3).to_numpy()
    emva8 = calculate_exponential_moving_average(closep, 8).to_numpy()
    emva14 = calculate_exponential_moving_average(closep, 14).to_numpy()
    emva30 = calculate_exponential_moving_average(closep, 30).to_numpy()
    if (
        closep.iloc[-1] > closep.iloc[-2]
        and emva3[-1] > emva8[-1] > emva14[-1]
        and (closep.iloc[-1] > emva8[-1])
        and (emva3[-2] < emva8[-2] or emva8[-2] < emva14[-2])
    ):
        mom = "BUY"
    elif (
        closep.iloc[-1] < closep.iloc[-2]
        and emva3[-1] < emva8[-1] < emva14[-1]
        and (closep.iloc[-1] < emva8[-1])
        and (emva3[-2] > emva8[-2] or emva8[-2] > emva14[-2])
    ):
        mom = "SELL"
    else:
        mom = None
    if (
        closep.iloc[-2] > closep.iloc[-3]
        and emva3[-2] > emva8[-2] > emva14[-2]
        and (closep.iloc[-2] > emva8[-2])
        and (emva3[-3] < emva8[-3] or emva8[-3] < emva14[-3])
    ):
        mom1 = "BUY"
    elif (
        closep.iloc[-2] < closep.iloc[-3]
        and emva3[-2] < emva8[-2] < emva14[-2]
        and (closep.iloc[-2] < emva8[-2])
        and (emva3[-3] > emva8[-3] or emva8[-3] > emva14[-3])
    ):
        mom1 = "SELL"
    else:
        mom1 = None
    if (
        emva8[-1] > emva14[-1] > emva30[-1]
        and closep.iloc[-1] > emva14[-1]
        and (emva8[-2] < emva14[-2] or emva14[-2] < emva30[-2])
    ):
        hybrid = "BUY"
    elif (
        emva8[-1] < emva14[-1] < emva30[-1]
        and closep.iloc[-1] < emva14[-1]
        and (emva8[-2] > emva14[-2] or emva14[-2] > emva30[-2])
    ):
        hybrid = "SELL"
    else:
        hybrid = None
    if (
        emva8[-2] > emva14[-2] > emva30[-2]
        and closep.iloc[-2] > emva14[-2]
        and (emva8[-3] < emva14[-3] or emva14[-3] < emva30[-3])
    ):
        hybrid1 = "BUY"
    elif (
        emva8[-2] < emva14[-2] < emva30[-2]
        and closep.iloc[-2] < emva14[-2]
        and (emva8[-3] > emva14[-3] or emva14[-3] > emva30[-3])
    ):
        hybrid1 = "SELL"
    else:
        hybrid1 = None
    if emva3[-2] > emva8[-2] > emva14[-2]:
        mom2 = "B"
    elif emva3[-2] < emva8[-2] < emva14[-2]:
        mom2 = "S"
    else:
        mom2 = None
    if emva8[-2] > emva14[-2] > emva30[-2]:
        hybrid2 = "B"
    elif emva8[-2] < emva14[-2] < emva30[-2]:
        hybrid2 = "S"
    else:
        hybrid2 = None
    return {
        "mom": mom,
        "mom1": mom1,
        "mom2": mom2,
        "hybrid": hybrid,
        "hybrid1": hybrid1,
        "hybrid2": hybrid2,
        "emva3": emva3,
        "emva8": emva8,
        "emva14": emva14,
        "emva30": emva30,
    }


def calculate_trend_index(
    price_change: float,
    range_spike: float,
    volume_spike_5d: float,
    three_day: str | None,
    sharpe_3d: float,
    sharpe_22d: float,
    current_price_range: str | None,
    post_close: float,
    avg_true_range: Sequence[float],
) -> float:
    """Calculate trend index based on multiple factors"""
    trend_index = 0.0
    if price_change > 0:
        if range_spike > 1.2:
            trend_index += 1
        if not pd.isna(volume_spike_5d) and volume_spike_5d > 1.2:
            trend_index += 1
        if three_day == "UP":
            trend_index += 0.5
        if sharpe_3d > 1:
            trend_index += sharpe_3d
        elif sharpe_3d > 0.5 and sharpe_22d > 1:
            trend_index += 0.5
        if current_price_range == "HIGH":
            trend_index += 0.5
        if _ratio(post_close, _tail(avg_true_range, 2)) > 0.2:
            trend_index += 0.5
    elif price_change <= 0:
        if range_spike > 1.2:
            trend_index -= 1
        if not pd.isna(volume_spike_5d) and volume_spike_5d > 1.2:
            trend_index -= 1
        if three_day == "DOWN":
            trend_index -= 0.5
        if sharpe_3d < -1:
            trend_index += sharpe_3d
        elif sharpe_3d < -0.5 and sharpe_22d < -1:
            trend_index -= 0.5
        if current_price_range == "LOW":
            trend_index -= 0.5
        if _ratio(post_close, _tail(avg_true_range, 2)) < -0.2:
            trend_index -= 0.5
    return trend_index


def determine_combined_signals(
    trend_index: float,
    price_change: float,
    mom: str | None,
    mom1: str | None,
    hybrid: str | None,
    hybrid1: str | None,
    fish: str | None,
    fish1: str | None,
    fishlt: str | None,
    fishlt1: str | None,
    counter: str | None,
    counter1: str | None,
) -> dict[str, str | None]:
    """Gate the five current/prior signal families on trend >2 or <-2 and price direction."""
    direction = (
        "BUY" if trend_index > 2 and price_change > 0 else "SELL" if trend_index < -2 and price_change < 0 else None
    )
    signals = {}
    for name, current, previous in (
        ("mom", mom, mom1),
        ("hybrid", hybrid, hybrid1),
        ("fish", fish, fish1),
        ("fishlt", fishlt, fishlt1),
        ("counter", counter, counter1),
    ):
        signals[f"{name}_signal"] = direction if direction in (current, previous) else None
        signals[f"{name}_signal_ystd"] = direction if previous == direction else None
    return signals


def calculate_signal_flag(combined_signals: Mapping[str, str | None], trend_index: float) -> int:
    """Flag any combined BUY/SELL signal or an absolute trend index above three."""
    return int(
        abs(trend_index) > 3
        or any(
            combined_signals.get(f"{name}_signal") in {"BUY", "SELL"}
            for name in ("mom", "hybrid", "fish", "fishlt", "counter")
        )
    )


def classify_sharpe_signal(sharpe_3d_cob: float, sharpe_22d: float) -> str:
    """Return the Sharpe report's TREND, COUNTER or '-' classification."""
    if (sharpe_3d_cob > 0 and sharpe_22d > 0) or (sharpe_3d_cob < 0 and sharpe_22d < 0):
        return "TREND"
    if (sharpe_3d_cob > 1 and sharpe_22d < -0.5) or (sharpe_3d_cob < -1 and sharpe_22d > 0.5):
        return "COUNTER"
    return "-"


def parse_fom_date(value: Any, *, as_of: Any) -> pd.Timestamp | tuple[pd.Timestamp, pd.Timestamp] | None:
    """Parse an ISO/US FOM date or a string containing start/end dates.

    Retains the report's interval rule: a future start becomes the first day
    of the as_of month. A single future date is not clamped.
    """
    if value is None or (not isinstance(value, (tuple, list)) and pd.isna(value)):
        return None
    day = pd.Timestamp(as_of)
    if pd.isna(day):
        raise ValueError("as_of must be a valid date")
    index = pd.DatetimeIndex([day])
    if isinstance(value, str) and len(value) > 10:
        value = (value[:10], value[-10:])
    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError("FOM interval must contain two dates")
        start, end = (_timestamp(bound, index) for bound in value)
        if start > day.normalize():
            start = day.normalize().replace(day=1)
        if start > end:
            raise ValueError("FOM start must precede its end")
        return start, end
    return _timestamp(value, index)


def calculate_fom_metrics(
    fom_date: Any,
    daily_price_chg: pd.Series,
    highp: pd.Series,
    lowp: pd.Series,
    closep: pd.Series,
    *,
    as_of: Any,
) -> tuple[str | None, float | None, Any]:
    """Return FOM breakout flag, change/std score and the report's date label.

    A single date uses the first observation on/after it. An interval uses
    summed changes and high/low extrema over its inclusive bounds. The score
    denominator is the sample standard deviation of the preceding 20 returns.
    Missing FOM observations return (None, None, None).
    """
    high, low, close = _ohlc(highp, lowp, closep)
    changes = _series(daily_price_chg)
    if not changes.index.equals(close.index):
        raise ValueError("FOM returns and OHLC must share the same dates")
    parsed = parse_fom_date(fom_date, as_of=_timestamp(as_of, close.index))
    if parsed is None or close.empty:
        return None, None, None
    interval = isinstance(parsed, tuple)
    start, end = parsed if interval else (parsed, close.index[-1])
    start, end = (_timestamp(bound, close.index) for bound in (start, end))
    sample = changes.loc[start:end]
    if sample.empty:
        return None, None, None
    change = sample.sum(min_count=1) if interval else sample.iloc[0]
    ceiling = high.loc[start:end].max() if interval else high.loc[start:end].iloc[0]
    floor = low.loc[start:end].min() if interval else low.loc[start:end].iloc[0]
    std = changes.loc[changes.index < start].tail(20).std()
    flag = "A+" if close.iloc[-1] > ceiling else "A-" if close.iloc[-1] < floor else None
    label = f"{start:%Y-%m-%d} - {end:%Y-%m-%d}" if interval else start
    return flag, _ratio(change, std), label


def calculate_fom_vwap(vwap: float, intraday_price: pd.DataFrame | None = None) -> tuple[float, float]:
    """Return a supplied provider VWAP and latest-close delta rounded to two decimals.

    The original obtains EQY_WEIGHTED_AVG_PX from Bloomberg. Pass that value
    here; bar-close averages are not substituted for the provider's VWAP.
    """
    delta = np.nan
    if intraday_price is not None and not intraday_price.empty:
        delta = round(float(_frame(intraday_price)["close"].iloc[-1]) - vwap, 2)
    return float(vwap), float(delta)


def calculate_kpi(
    closep: pd.Series,
    imp_vol: pd.Series | pd.DataFrame | None,
    daily_price_chg: pd.Series,
    chg_type: ChangeType,
    generic_name: str = "",
    intraday_price: pd.DataFrame | None = None,
    *,
    as_of: Any = None,
) -> dict[str, float]:
    """Normalize price moves by lagged annual volatility and return the report KPI.

    Implied volatility is in percentage points. Missing/all-null implied vol
    falls back to 30-observation return std(ddof=1)*100*sqrt(252). FLAT uses
    current close in its denominator; SPRD uses absolute moves. GXA retains
    the report's prior-close convention and midnight intraday cutoff, which
    requires as_of when intraday prices are supplied. KPI Index is the last
    14 KPIs with normalized 0.94 decay, newest weighted highest.
    """
    _change_type(chg_type)
    close = _series(closep, 3)
    if isinstance(imp_vol, pd.DataFrame):
        if len(imp_vol.columns) > 1:
            raise ValueError("imp_vol must have at most one column")
        imp_vol = imp_vol.iloc[:, 0] if len(imp_vol.columns) else None
    if imp_vol is None or imp_vol.dropna().empty:
        vol = _series(daily_price_chg).rolling(30).std() * 100 * np.sqrt(252)
    else:
        vol = _series(imp_vol)
    vol = vol.reindex(close.index).ffill()
    sigma = vol.shift() / 100 / np.sqrt(252)
    denominator = sigma if chg_type == "SPRD" else close * sigma
    if chg_type == "FLAT" and generic_name == "GXA Index":
        denominator = close.shift() * sigma
    kpi = close.diff() / denominator
    latest = _tail(kpi)
    if chg_type == "FLAT" and generic_name == "GXA Index":
        if intraday_price is not None and not intraday_price.empty:
            if as_of is None:
                raise ValueError("as_of is required for GXA intraday KPI")
            intraday = _frame(intraday_price)
            history = intraday.loc[: _timestamp(as_of, intraday.index).normalize(), "close"]
            prior = _tail(history)
            latest = _ratio(close.iloc[-1] - prior, prior * sigma.iloc[-1])
        else:
            latest = _ratio(close.iloc[-1] - close.iloc[-2], close.iloc[-1] * sigma.iloc[-1])
    values = kpi.tail(14).to_numpy()[::-1]
    weights = 0.94 ** np.arange(len(values))
    average = float(np.sum(values * weights / weights.sum()))
    return {"kpi_on": latest, "kpi_1d": _tail(kpi, 2), "kpi_avg": average}


def calculate_cumulative_volume(intraday_price: pd.DataFrame) -> pd.Series:
    """Sample each weekday's cumulative volume at the latest ten-minute grid time.

    The grid starts at the first supplied timestamp; missing bars contribute
    zero. Weekends and zero-volume sessions are excluded, matching the report.
    Session times/timezones must be prepared upstream.
    """
    intraday = _frame(intraday_price)
    if intraday.empty:
        return pd.Series(dtype=float, index=intraday.index, name="agg_volume")
    grid = pd.date_range(intraday.index[0], intraday.index[-1], freq="10min")
    grid = grid[grid.dayofweek < 5]
    volume = _series(intraday["volume"]).reindex(grid).fillna(0)
    if volume.empty:
        return volume.rename("agg_volume")
    accumulated = volume.groupby(volume.index.normalize()).cumsum()
    sample = accumulated.loc[accumulated.index.time == accumulated.index[-1].time()]
    return sample.loc[sample != 0].rename("agg_volume")


def adjust_volume_for_roll(
    volume_at_minute: pd.Series,
    previous_volume: pd.Series,
    roll_date: Any,
    *,
    as_of: Any,
) -> pd.Series:
    """Splice supplied previous-contract volumes before a recent roll boundary.

    Both series must already use the same session cutoff. The source applies
    rolls within ten business days and moves a current-day boundary back one
    business day. Missing previous-contract observations remain missing.
    """
    current, previous = _series(volume_at_minute), _series(previous_volume)
    if current.empty:
        return current
    end = _timestamp(as_of, current.index)
    boundary = _timestamp(roll_date, current.index)
    if end > boundary > end - BDay(10):
        if boundary >= end.normalize():
            boundary -= BDay(1)
        mask = current.index < boundary
        current.loc[mask] = previous.reindex(current.index).loc[mask]
    return current


def calculate_volume_spikes(
    intraday_price: pd.DataFrame,
    daily_price: pd.DataFrame,
    *,
    as_of: Any,
    previous_volume: pd.Series | None = None,
    roll_date: Any = None,
) -> dict[str, Any]:
    """Compare same-time cumulative volume with preceding 5/20-session means.

    Live ratios require more than 20 nonzero sessions and a final timestamp
    after as_of midnight. The prior daily ratio uses VOLUME and the report's
    stale/current/future daily-row rule. Call only for volume-enabled markets;
    ticker eligibility and contract identification belong upstream.
    """
    intraday, daily = _frame(intraday_price), _frame(daily_price)
    if (previous_volume is None) != (roll_date is None):
        raise ValueError("previous_volume and roll_date must be supplied together")
    result = {
        "volume_spike_5d": np.nan,
        "volume_spike_5d_1": np.nan,
        "volume_spike_20d": np.nan,
        "volume_at_minute": pd.Series(dtype=float),
    }
    if len(intraday) <= 10:
        return result
    sample = calculate_cumulative_volume(intraday)
    if previous_volume is not None:
        sample = adjust_volume_for_roll(sample, previous_volume, roll_date, as_of=as_of)
    result["volume_at_minute"] = sample
    day = _timestamp(as_of, intraday.index).normalize()
    if len(sample) > 20 and sample.index[-1] > day:
        for window in (5, 20):
            result[f"volume_spike_{window}d"] = _ratio(_tail(sample), _tail(sample.rolling(window).mean(), 2))
    if not daily.empty and "VOLUME" in daily:
        daily_day = _timestamp(as_of, daily.index).normalize()
        offset = 2 if daily.index[-1] == daily_day else 1 if daily.index[-1] < daily_day else 3
        volumes = _series(daily.VOLUME)
        result["volume_spike_5d_1"] = _ratio(_tail(volumes, offset), _tail(volumes.rolling(5).mean(), offset + 1))
    return result


def calculate_divergence(
    spread: pd.Series,
    flat: pd.Series,
    *,
    as_of: Any,
    scale: float = 1.0,
    invert_spread: bool = False,
    min_move_zscore: float | None = None,
) -> dict[str, float]:
    """Return the AM report's 3/8-observation change ratios and last settled moves.

    Inputs must share dates. A current/future last row is excluded. Use scale=.42
    for the report's XB/HO versus CO unit conversion; the JKM/TTF preset uses
    invert_spread=True and min_move_zscore=1.5 after upstream date alignment.
    The caller screens for negative divergence ratios as the report does.
    """
    spread, flat = _series(spread, 2), _series(flat, 2)
    if not spread.index.equals(flat.index):
        raise ValueError("Divergence inputs must share the same dates")
    spread_change = spread.diff() * (-1 if invert_spread else 1)
    flat_change = flat.diff()
    live = spread.index[-1] >= _timestamp(as_of, spread.index).normalize()
    offset = 2 if live else 1
    result = {
        "Sprd change": _tail(spread_change, offset),
        "Flat change": _tail(flat_change, offset),
        "3d divergence": np.nan,
        "8d divergence": np.nan,
    }
    reference = flat_change.iloc[-23:-2] if live else flat_change.iloc[-22:]
    valid = min_move_zscore is None or _ratio(abs(result["Flat change"]), reference.std()) > min_move_zscore
    if valid:
        for window in (3, 8):
            result[f"{window}d divergence"] = _ratio(
                _tail(spread_change.rolling(window).sum(), offset) * scale,
                _tail(flat_change.rolling(window).sum(), offset),
            )
    return result


def calculate_fly_switches(spreads: pd.DataFrame) -> pd.DataFrame:
    """Return adjacent-spread flies whose last two observations changed sign.

    Supply the ordered spread columns used by get_fly_switch (first, second,
    third spread). Moving to/from zero counts as a switch, as in the report.
    """
    frame = _frame(spreads).astype(float)
    rows = {}
    if len(frame) >= 2:
        for first, second in zip(frame.columns[:-1], frame.columns[1:], strict=True):
            fly = frame[first] - frame[second]
            previous, current = fly.iloc[-2:]
            if pd.notna(previous) and pd.notna(current) and np.sign(current) != np.sign(previous):
                rows[f"{first}-{second}"] = [current, previous, current - previous]
    return pd.DataFrame.from_dict(rows, orient="index", columns=["Current Price", "Yesterday Price", "Daily Change"])


def calculate_weighted_risk_index(
    metrics: pd.DataFrame,
    weights: Mapping[str, float],
    *,
    normalize: bool = False,
) -> pd.Series:
    """Weight report metric rows, optionally normalizing component-group weights.

    Input index contains instrument names and columns contain numeric metrics.
    The report uses raw weights for the overall index and normalized weights
    for EQT/USD/commodities/rates groups. Units and column labels are retained;
    all-missing metrics stay missing rather than turning into zero.
    """
    if not metrics.index.is_unique or not weights:
        raise ValueError("Risk index requires unique instruments and nonempty weights")
    weight = pd.Series(weights, dtype=float)
    if not np.isfinite(weight).all():
        raise ValueError("Risk weights must be finite")
    if normalize:
        if weight.sum() == 0:
            raise ValueError("Cannot normalize zero-sum weights")
        weight = weight / weight.sum()
    return metrics.loc[weight.index].astype(float).mul(weight, axis=0).sum(min_count=1)
