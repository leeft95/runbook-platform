"""COT report calculations over dictionaries of caller-supplied time series.

The public names follow ``ecm.cmds.quant.cot``. Calculation functions return
numeric summary DataFrames; table presentation belongs to table.templates.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .timeseries.analysis import calculate_percential_rank


def prepare_cot_data(
    data: pd.DataFrame,
    *,
    as_of: str | pd.Timestamp | None = None,
    position_scale: float = 1.0,
) -> pd.DataFrame:
    """Align COT observations and derive net positions and OI ratios.

    ``Long`` and ``Short`` are required. Optional columns are ``OI``, ``PX_LAST``,
    ``VWAP``, ``Internal`` (the model estimate), and paired
    ``NC Long``/``NC Short``. Price, OI,
    VWAP and the model estimate are forward-filled before selecting position dates;
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
    ``Internal Change`` is the weekly change in the internal model estimate.
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
        "Internal Change": frame["Internal"].diff().iloc[-1],
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


def position_change(summary: pd.DataFrame, threshold: float = 1.5) -> pd.DataFrame:
    """Select large weekly or four-observation position moves, without row exclusions."""
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    scores = summary[["net change z score", "4w delta change z score"]]
    return summary.loc[scores.abs().gt(threshold).any(axis=1)].copy()


def position_divergence(summary: pd.DataFrame) -> pd.DataFrame:
    """Select rows whose weekly position and price changes have opposite signs."""
    return summary.loc[(summary["Weekly Delta Change"] * summary["Weekly Price Change"]) < 0].copy()


def summary_from_timeseries(
    observations: Mapping[str, pd.DataFrame],
    *,
    summary_options: Mapping[str, Any] | None = None,
    asset_options: Mapping[str, Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Calculate one generic ``cot_summary`` row per dictionary entry, in order.

    Keys are output row labels, including contract type where appropriate.
    Values have a DatetimeIndex and Long/Short, with optional OI, PX_LAST,
    VWAP, Internal and paired NC Long/NC Short columns. ``summary_options``
    supplies shared calculation options; ``asset_options`` overrides per row.
    Inputs are never modified. Provider access and participant aggregation
    belong to the caller.
    """
    if not observations:
        raise ValueError("observations must contain at least one named asset")
    if unknown := set(asset_options or {}) - set(observations):
        raise ValueError(f"Unknown assets in asset_options: {sorted(unknown)}")
    return pd.concat(
        [
            cot_summary(frame, name, **{**(summary_options or {}), **(asset_options or {}).get(name, {})})
            for name, frame in observations.items()
        ],
        ignore_index=True,
    )


def analysis(
    observations: Mapping[str, pd.DataFrame],
    *,
    summary_options: Mapping[str, Any] | None = None,
    asset_options: Mapping[str, Mapping[str, Any]] | None = None,
    asset_groups: Mapping[str, str] | None = None,
    label_column: str | None = None,
    position_column: str = "Net Position (MM)",
    group_column: str = "Group",
) -> pd.DataFrame:
    """Build the CME/ICE/macro ``cot.analysis`` report summary from named frames.

    Position-score windows default to 52 observations. NC positions stay
    separate. Output uses the ECM column names, including dollar-million
    changes and the first row's observation-week heading. Dictionary order
    determines report row order. ``asset_groups`` adds group metadata for the
    table formatter. Contract scaling/value are explicit calculation options.
    Uses Runbook's documented return and four-week conventions.
    """
    return _analysis_rows(
        observations,
        summary_options={"change_window": 52, **(summary_options or {})},
        asset_options=asset_options,
        asset_groups=asset_groups,
        label_column=label_column,
        position_column=position_column,
        group_column=group_column,
        currency_column="Weekly Delta Change in $m",
    )


def analysis_mifid(
    observations: Mapping[str, pd.DataFrame],
    *,
    summary_options: Mapping[str, Any] | None = None,
    asset_options: Mapping[str, Mapping[str, Any]] | None = None,
    asset_groups: Mapping[str, str] | None = None,
    label_column: str | None = None,
    position_column: str = "Net Position",
    group_column: str = "Group",
) -> pd.DataFrame:
    """Build the ICE MiFID/EUA-TTF/LME ``cot.analysis_mifid`` summary.

    Supply normalized Long/Short frames, combining additional venues upstream.
    Position-score windows default to 208; price/rank windows remain 52 and
    percentile history 260. Output uses Net Position and dollar/euro-million
    column names. Other input/output conventions match ``analysis``.
    """
    return _analysis_rows(
        observations,
        summary_options={"change_window": 208, **(summary_options or {})},
        asset_options=asset_options,
        asset_groups=asset_groups,
        label_column=label_column,
        position_column=position_column,
        group_column=group_column,
        currency_column="Weekly Delta Change in $/EUR m",
    )


def _analysis_rows(
    observations: Mapping[str, pd.DataFrame],
    *,
    summary_options: Mapping[str, Any],
    asset_options: Mapping[str, Mapping[str, Any]] | None,
    asset_groups: Mapping[str, str] | None,
    label_column: str | None,
    position_column: str,
    group_column: str,
    currency_column: str,
) -> pd.DataFrame:
    """Assemble report-ordered rows with shared headings and optional group metadata."""
    summary = summary_from_timeseries(observations, summary_options=summary_options, asset_options=asset_options)
    reference_date = pd.Timestamp(summary["_last_update"].iloc[0])
    if label_column is None:
        label_column = f"{reference_date - pd.DateOffset(days=7):%d-%b} to {reference_date:%d-%b}"
    if asset_groups is not None:
        if set(asset_groups) != set(observations):
            raise ValueError("asset_groups must have exactly one group for each named asset")
        if not isinstance(group_column, str) or not group_column.strip() or group_column in summary:
            raise ValueError("group_column must name a new, non-blank metadata column")
        summary[group_column] = summary["Asset"].map(asset_groups)
    summary = summary.rename(
        columns={
            "Asset": label_column,
            "Net Position": position_column,
            "Weekly Delta Change in millions": currency_column,
        }
    )
    if not summary.columns.is_unique or any(not isinstance(col, str) or not col.strip() for col in summary):
        raise ValueError("analysis output requires distinct, non-blank string column names")
    leading = [label_column, *(["Net Position (NC)"] if "Net Position (NC)" in summary else [])]
    return summary[leading + [col for col in summary if col not in leading]]


__all__ = [
    "analysis",
    "analysis_mifid",
    "summary_from_timeseries",
    "prepare_cot_data",
    "cot_summary",
    "position_change",
    "position_divergence",
]
