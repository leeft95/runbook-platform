"""Deterministic positioning calculations over caller-supplied observations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .analysis import calculate_percential_rank


def prepare_cot_data(
    data: pd.DataFrame,
    *,
    as_of: str | pd.Timestamp | None = None,
    position_scale: float = 1.0,
) -> pd.DataFrame:
    """Align COT observations and derive net positions and OI ratios.

    ``Long`` and ``Short`` are required. Optional columns are ``OI``, ``PX_LAST``,
    ``VWAP``, ``Internal`` (CTA), and paired ``NC Long``/``NC Short``. Price, OI,
    VWAP and CTA are forward-filled before selecting actual position dates;
    positions are never filled. Supply normalized participant/venue data here.
    ``position_scale`` multiplies contract counts, including OI. No provider
    access, ticker-specific conversion, or wall-clock date is used.
    """
    if not isinstance(data, pd.DataFrame) or not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data must be a DataFrame with a DatetimeIndex")
    if not data.index.is_unique or data.index.hasnans or not data.columns.is_unique:
        raise ValueError("COT observations need unique dates and columns, without NaT")
    if not np.isfinite(position_scale) or position_scale <= 0:
        raise ValueError("position_scale must be finite and positive")
    required = {"Long", "Short"}
    if not required.issubset(data.columns):
        raise ValueError("COT data requires Long and Short columns")
    if ("NC Long" in data) != ("NC Short" in data):
        raise ValueError("NC Long and NC Short must be supplied together")
    frame = data.sort_index().copy()
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if frame.index.tz is not None and cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(frame.index.tz)
        frame = frame.loc[frame.index <= cutoff]
    fields = [
        col for col in ("Long", "Short", "OI", "PX_LAST", "VWAP", "Internal", "NC Long", "NC Short") if col in frame
    ]
    frame = frame[fields].apply(pd.to_numeric, errors="raise").astype(float)
    if np.isinf(frame.to_numpy()).any():
        raise ValueError("COT observations must be finite or missing")
    for col in ("OI", "PX_LAST", "VWAP", "Internal"):
        frame[col] = frame[col].ffill() if col in frame else np.nan
    frame = frame.dropna(subset=["Long", "Short"])
    if frame.empty:
        raise ValueError("No paired Long/Short observations at or before as_of")
    for col in ("Long", "Short", "OI", "NC Long", "NC Short"):
        if col in frame:
            frame[col] *= position_scale
    frame["Net"] = frame["Long"] - frame["Short"]
    for col in ("Net", "Long", "Short"):
        frame[f"{col} OI"] = frame[col] / frame["OI"].replace(0, np.nan)
    if "NC Long" in frame:
        frame["NC Net"] = frame["NC Long"] - frame["NC Short"]
    return frame


def _ratio(value: float, denominator: float) -> float:
    """Return missing for undefined ratios instead of misleading infinity."""
    return float(value / denominator) if np.isfinite(denominator) and denominator != 0 else float("nan")


def _rank(series: pd.Series, window: int) -> float:
    """Rank the latest observation against earlier observations only."""
    history = series.iloc[-window - 1 : -1].dropna()
    if history.empty or pd.isna(series.iloc[-1]):
        return float("nan")
    return calculate_percential_rank(history, float(series.iloc[-1]))


def cot_summary(
    data: pd.DataFrame,
    name: str,
    *,
    as_of: str | pd.Timestamp | None = None,
    position_scale: float = 1.0,
    contract_value: float | None = None,
    change_window: int = 52,
    price_window: int = 52,
    percentile_window: int = 260,
    rank_window: int = 52,
    threshold: float = 1.5,
) -> pd.DataFrame:
    """Build one COT summary row with numeric values and hidden signal columns.

    Horizons count position observations (normally weekly). Four-week changes
    consistently use four intervals; weekly price return uses the previous
    price as its denominator. Position scores divide changes by sample standard
    deviation without centering, matching ECM's convention. Price scores are
    centered. Dispersion windows include the latest change, while percentile
    windows exclude the latest level. Set ``change_window=208`` for the MiFID
    convention; the default is the standard COT 52-observation convention.
    YTD starts at the last observation before the latest observation's year.
    Missing history, zero denominators and unavailable optional inputs yield NaN.
    Monetary changes are in millions of the supplied contract's currency.
    """
    if not name.strip():
        raise ValueError("name must not be blank")
    for window in (change_window, price_window, percentile_window, rank_window):
        if not isinstance(window, int) or isinstance(window, bool) or window < 2:
            raise ValueError("COT lookback windows must be integers >= 2")
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    if contract_value is not None and (not np.isfinite(contract_value) or contract_value <= 0):
        raise ValueError("contract_value must be finite and positive")
    frame = prepare_cot_data(data, as_of=as_of, position_scale=position_scale)
    net, price = frame["Net"], frame["PX_LAST"]
    latest = frame.iloc[-1]
    changes, changes4 = net.diff(), net.diff(4)
    returns4 = price.pct_change(4, fill_method=None).replace([np.inf, -np.inf], np.nan)
    price_history = returns4.tail(price_window)
    prior_year = frame.loc[frame.index.year < frame.index[-1].year]
    base = prior_year.iloc[-1] if not prior_year.empty else pd.Series(dtype=float)
    row = {
        "Asset": name,
        "Net Position": latest["Net"],
        "% OI": latest["Net OI"],
        "Weekly Price Change": _ratio(price.diff().iloc[-1], price.shift().iloc[-1]),
        "Ref Week VWAP": latest["VWAP"],
        "CTA Change": frame["Internal"].diff().iloc[-1],
        "Weekly Delta Change": changes.iloc[-1],
        "Weekly change in longs": frame["Long"].diff().iloc[-1],
        "Weekly change in shorts": frame["Short"].diff().iloc[-1],
        "Weekly Delta Change in millions": changes.iloc[-1] * latest["PX_LAST"] * (contract_value or np.nan) / 1e6,
        "4w change of price": returns4.iloc[-1],
        "4w change of net position": changes4.iloc[-1],
        "YTD position change": latest["Net"] - base.get("Net", np.nan),
        "Long Short Ratio": _ratio(latest["Long"], latest["Short"]),
        "Long Position": latest["Long"],
        "Short Position": latest["Short"],
        "Weekly OI change": frame["OI"].diff().iloc[-1],
        "Net percentile": _rank(net, percentile_window),
        "Net/OI percentile": _rank(frame["Net OI"], percentile_window),
        "Long percentile": _rank(frame["Long"], percentile_window),
        "Short percentile": _rank(frame["Short"], percentile_window),
        "net change z score": _ratio(changes.iloc[-1], changes.tail(change_window).std()),
        "4w price change z score": _ratio(returns4.iloc[-1] - price_history.mean(), price_history.std()),
        "4w delta change z score": _ratio(changes4.iloc[-1], changes4.tail(change_window).std()),
        "net pos rank": _rank(net, rank_window),
        "net/oi pct rank": _rank(frame["Net OI"], rank_window),
        "YTD price change": latest["PX_LAST"] - base.get("PX_LAST", np.nan),
    }
    if "NC Net" in frame:
        row["Net Position (NC)"] = latest["NC Net"]
    net_rank, oi_rank = row["net pos rank"], row["net/oi pct rank"]
    net_signal = 1 if net_rank > 0.8 and oi_rank > 0.8 else -1 if net_rank < 0.2 and oi_rank < 0.2 else 0
    price_change, net_change = price.diff().iloc[-1], changes.iloc[-1]
    divergence = 1 if price_change > 0 > net_change else 0 if price_change < 0 < net_change else 0.5
    row.update(
        _thr_high=0.9,
        _thr_low=0.1,
        _thr_high8=0.8,
        _thr_low8=0.2,
        _thr_net=net_signal,
        _z_high=threshold,
        _z_low=-threshold,
        _price_chg=divergence,
        _last_update=frame.index[-1].isoformat(),
        _change_window=change_window,
    )
    return pd.DataFrame([row])


def cot_position_changes(summary: pd.DataFrame, threshold: float = 1.5) -> pd.DataFrame:
    """Select large weekly or four-observation position moves, without row exclusions."""
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    scores = summary[["net change z score", "4w delta change z score"]]
    return summary.loc[scores.abs().gt(threshold).any(axis=1)].copy()


def cot_position_divergence(summary: pd.DataFrame) -> pd.DataFrame:
    """Select rows whose weekly position and price changes have opposite signs."""
    return summary.loc[(summary["Weekly Delta Change"] * summary["Weekly Price Change"]) < 0].copy()
