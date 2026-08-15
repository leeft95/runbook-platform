"""Functions aimed at transforming timeseries data."""

from __future__ import annotations

import calendar
from collections.abc import Hashable
from datetime import tzinfo
from typing import List, Literal, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

_FRAME_LEN_BY_FREQUENCY: dict[str, int] = {
    "D": 366,
    "M": 12,
    "W": 53,
    "B": 262,
}


def _timestamp_for_boundary(year: int, month: int, day: int, tz: str | tzinfo | None) -> pd.Timestamp:
    """Handle timestamp for boundary."""
    max_day = calendar.monthrange(year, month)[1]
    clamped_day = min(day, max_day)
    return pd.Timestamp(year=year, month=month, day=clamped_day, tz=tz)


def _normalize_weekly(series: pd.Series) -> pd.Series:
    """Keep one observed point per calendar week (last observation wins)."""
    if series.empty:
        return series

    if not isinstance(series.index, pd.DatetimeIndex):
        msg = "series.index must be a pandas.DatetimeIndex for weekly normalization."
        raise TypeError(msg)

    idx: pd.DatetimeIndex = series.index
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    week_keys = idx.to_period("W")
    return series.loc[~week_keys.duplicated(keep="last")]


def _position_index(index: pd.DatetimeIndex, start_ts: pd.Timestamp, frequency: str) -> NDArray[np.int64]:
    """Handle position index."""
    if frequency == "D":
        return np.asarray((index - start_ts) // pd.Timedelta(days=1), dtype=np.int64)

    if frequency == "W":
        day_delta: NDArray[np.int64] = np.asarray((index - start_ts) // pd.Timedelta(days=1), dtype=np.int64)
        return day_delta // 7

    if frequency == "M":
        return np.asarray((index.year - start_ts.year) * 12 + (index.month - start_ts.month), dtype=np.int64)

    if frequency == "B":
        idx_days = index
        if idx_days.tz is not None:
            idx_days = idx_days.tz_localize(None)
        idx_days = idx_days.normalize().to_numpy(dtype="datetime64[D]")
        start_day_np = (
            np.datetime64(start_ts.tz_localize(None).date(), "D")
            if start_ts.tz is not None
            else np.datetime64(start_ts.date(), "D")
        )
        return np.asarray(np.busday_count(start_day_np, idx_days), dtype=np.int64)

    raise ValueError(f"Unsupported frequency: {frequency}")


def _dummy_plot_index(length: int, frequency: str, start_month: int, start_day: int, year: int) -> pd.DatetimeIndex:
    """Handle dummy plot index."""
    start = _timestamp_for_boundary(year, start_month, start_day, tz=None)

    if frequency == "D":
        return pd.date_range(start=start, periods=length, freq="D")

    if frequency == "W":
        return pd.date_range(start=start, periods=length, freq="7D")

    if frequency == "M":
        dates = [
            _timestamp_for_boundary(
                year + ((start_month - 1 + i) // 12), ((start_month - 1 + i) % 12) + 1, start_day, tz=None
            )
            for i in range(length)
        ]
        return pd.DatetimeIndex(dates)

    if frequency == "B":
        return pd.bdate_range(start=start, periods=length)

    raise ValueError(f"Unsupported frequency: {frequency}")


def ts_by_year(
    df: pd.DataFrame | pd.Series,
    frequency: str = "D",
    start_day: int | None = None,
    start_month: int | None = None,
    end_day: int | None = None,
    end_month: int | None = None,
    column: Hashable | None = None,
    over_year: bool = False,
    dummy_date_index: bool = False,
) -> pd.DataFrame:
    """
    Transform a timeseries dataframe into a frame where each year is a column.
    The returned index is a shape-normalized period index (0..N-1) for the chosen frequency.

    frequency: the frequency of the data, e.g. "D" for daily, "M" for monthly, etc.
    start_day: the day of the month to start the year, e.g. 1 for January 1st, 15 for January 15th, etc. if None, it will be set to the day of the first date in the dataframe.
    start_month: the month to start the year, e.g. 1 for January, 2 for February, etc., if None, it will be set to the month of the first date in the dataframe.
    end_day: the day of the month to end the year, e.g. 31 for January 31st, 15 for January 15th, etc., if None, it will be set to the same as start_day ie (YoY)
    end_month: the month to end the year, e.g. 1 for January, 2 for February, etc. if None, it will be set to the same as start_month ie (YoY)
    column: the column to use for the values, if None, the first column will be used.
    over_year: if the timseries is seasonal and the year should be considered to start at the start_month and end at the end_month,
    e.g. for a seasonal timeseries that starts in October and ends in September, set start_month to 10 and end_month to 9, and set over_year to True.
    dummy_date_index: if True, replace the integer slot index with a dummy DatetimeIndex for plotting multi-year overlays.
    In this mode, rows where all columns are NaN are trimmed before building the x-axis.
    """
    if frequency not in _FRAME_LEN_BY_FREQUENCY:
        supported = ", ".join(_FRAME_LEN_BY_FREQUENCY)
        raise ValueError(f"Frequency {frequency} not supported. Supported frequencies are: {supported}.")

    if isinstance(df, pd.Series):
        if column is not None and column != df.name:
            raise KeyError(f"column {column!r} not found in df.")
        # Normalize Series input into a single-column DataFrame.
        series_name = "value" if df.name is None else df.name
        df = df.to_frame(name=series_name)
        if column is None:
            column = series_name
    elif not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame or Series.")

    if df.empty:
        raise ValueError("df must not be empty.")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("df.index must be a pandas.DatetimeIndex.")

    if column is None:
        if len(df.columns) == 0:
            raise ValueError("df must contain at least one column when column is None.")
        column = df.columns[0]
    if column not in df.columns:
        raise KeyError(f"column {column!r} not found in df.")

    selected = df[column]
    if isinstance(selected, pd.DataFrame):
        msg = f"column {column!r} is ambiguous because it resolves to multiple columns."
        raise ValueError(msg)

    series = cast(pd.Series, selected.copy())
    series = series.sort_index()
    series_index = cast(pd.DatetimeIndex, series.index)

    first_date = series_index[0]
    last_date = series_index[-1]
    tz = series_index.tz

    if start_day is None:
        start_day = int(first_date.day)
    if start_month is None:
        start_month = int(first_date.month)
    if end_day is None:
        end_day = int(start_day)
    if end_month is None:
        end_month = int(start_month)

    if not 1 <= start_month <= 12 or not 1 <= end_month <= 12:
        raise ValueError("start_month and end_month must be in [1, 12].")
    if not 1 <= start_day <= 31 or not 1 <= end_day <= 31:
        raise ValueError("start_day and end_day must be in [1, 31].")

    if frequency == "W":
        series = _normalize_weekly(series)

    # End boundary is exclusive to keep the one-year default window stable.
    end_year_offset = 1 if over_year or (end_month, end_day) <= (start_month, start_day) else 0

    start_of_first_calendar_year = _timestamp_for_boundary(first_date.year, start_month, start_day, tz)
    start_of_last_calendar_year = _timestamp_for_boundary(last_date.year, start_month, start_day, tz)
    start_anchor_year = first_date.year if first_date >= start_of_first_calendar_year else first_date.year - 1
    end_anchor_year = last_date.year if last_date >= start_of_last_calendar_year else last_date.year - 1

    if end_anchor_year < start_anchor_year:
        return pd.DataFrame(np.nan, index=range(_FRAME_LEN_BY_FREQUENCY[frequency]), columns=[])

    out = pd.DataFrame(
        np.nan,
        index=range(_FRAME_LEN_BY_FREQUENCY[frequency]),
        columns=range(start_anchor_year, end_anchor_year + 1),
    )

    for anchor_year_raw in out.columns:
        anchor_year = int(anchor_year_raw)
        start_ts = _timestamp_for_boundary(anchor_year, start_month, start_day, tz)
        end_ts = _timestamp_for_boundary(anchor_year + end_year_offset, end_month, end_day, tz)
        in_window = series[(series.index >= start_ts) & (series.index < end_ts)]
        if in_window.empty:
            continue

        in_window_index = cast(pd.DatetimeIndex, in_window.index)
        positions = _position_index(in_window_index, start_ts, frequency)
        valid_mask = (positions >= 0) & (positions < len(out.index))
        if not valid_mask.any():
            continue

        values = in_window.to_numpy()[valid_mask]
        positions = positions[valid_mask]

        # If multiple observations map to one slot, keep the last observation.
        mapped = pd.Series(values, index=positions)
        mapped = mapped[~mapped.index.duplicated(keep="last")]
        out.loc[mapped.index.to_numpy(dtype=np.int64, copy=False), anchor_year] = mapped.to_numpy()

    out = out.dropna(axis=1, how="all")
    if dummy_date_index:
        out = out.dropna(axis=0, how="all")
        plot_year = pd.Timestamp.today().year
        out.index = _dummy_plot_index(len(out.index), frequency, start_month, start_day, year=plot_year)

    return out


# General dataframe operations
# - merge
# - diff a dataframe tagging it by new and updated rows


def merge_dfs(
    dfs: List[pd.DataFrame],
    on: str | None = None,
    how: Literal["left", "right", "outer", "inner", "cross"] = "inner",
) -> pd.DataFrame:
    """Merge a list of dataframes on a common column."""
    if not dfs:
        return pd.DataFrame()

    if on is None:
        common_cols = set(dfs[0].columns)
        for df in dfs[1:]:
            common_cols.intersection_update(df.columns)
        if not common_cols:
            raise ValueError("No common columns found to merge on.")
        on = sorted(common_cols)[0]

    merged = dfs[0]
    for df in dfs[1:]:
        merged = pd.merge(merged, df, on=on, how=how)
    return merged


def diff_dfs(existing: pd.DataFrame, updated: pd.DataFrame, on: List[str]) -> pd.DataFrame:
    # Align keys into index space for deterministic row set comparison.
    """Handle diff dfs."""
    existing_df = existing.reset_index(drop=False) if not isinstance(existing.index, pd.RangeIndex) else existing.copy()
    updated_df = updated.reset_index(drop=False) if not isinstance(updated.index, pd.RangeIndex) else updated.copy()
    existing_idx = existing_df.set_index(on)
    updated_idx = updated_df.set_index(on)

    if not existing_idx.index.is_unique or not updated_idx.index.is_unique:
        raise ValueError("`on` must uniquely identify rows in both dataframes.")

    # Compare only shared payload columns.
    common_cols = existing_idx.columns.intersection(updated_idx.columns)
    existing_idx = existing_idx[common_cols]
    updated_idx = updated_idx[common_cols]

    # Rows present only in updated are new.
    new_idx = updated_idx.index.difference(existing_idx.index)
    df_new = updated_idx.loc[new_idx].reset_index()
    df_new["update_type"] = "new"

    # Rows present in both are updated only when any non-key field changed.
    common_idx = existing_idx.index.intersection(updated_idx.index)
    existing_common = existing_idx.loc[common_idx]
    updated_common = updated_idx.loc[common_idx]
    diff_mask = updated_common.ne(existing_common) & ~(updated_common.isna() & existing_common.isna())
    changed_idx = diff_mask.any(axis=1)
    df_updated = updated_common.loc[changed_idx].reset_index()
    df_updated["update_type"] = "updated"

    return pd.concat([df_new, df_updated], axis=0, ignore_index=True)
