"""Calendar-window averages shared by roll-up tables and their charts."""

from __future__ import annotations

import re

import pandas as pd
from pandas.api.indexers import VariableOffsetWindowIndexer


def _calendar_offset(window: str) -> pd.DateOffset:
    """Parse a positive calendar-day/month window, for example 20d or 3m."""
    match = re.fullmatch(r"([1-9]\d*)([dm])", window, re.IGNORECASE)
    if match is None:
        raise ValueError("window must be a positive calendar window such as '5d', '20d' or '3m'")
    return pd.DateOffset(**{"days" if match[2].lower() == "d" else "months": int(match[1])})


def calendar_moving_average(data: pd.DataFrame, window: str) -> pd.DataFrame:
    """Average available observations in (date - window, date], without filling.

    Days and months are calendar offsets, including across daylight-saving
    transitions. Missing values are skipped; all-missing windows remain NaN.
    Results are sorted by timestamp and the input is not modified.
    """
    if not isinstance(data, pd.DataFrame) or not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("data requires a DataFrame with a DatetimeIndex")
    if not data.index.is_unique or data.index.hasnans:
        raise ValueError("data requires unique dates without NaT")
    ordered = data.sort_index()
    indexer = VariableOffsetWindowIndexer(index=ordered.index, offset=_calendar_offset(window))
    return ordered.rolling(indexer, min_periods=1, closed="right").mean()
