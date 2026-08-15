from __future__ import annotations

import numpy as np
import pandas as pd
from runbook.core.timeseries.transforms import ts_by_year


def test_ts_by_year_daily_window_includes_start_boundary() -> None:
    idx = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    df = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)

    out = ts_by_year(df, frequency="D", start_day=1, start_month=1)

    assert list(out.columns) == [2024]
    assert int(out[2024].notna().sum()) == 366
    assert out.loc[0, 2024] == 0.0
    assert out.loc[365, 2024] == 365.0
    assert isinstance(out.index, pd.RangeIndex)


def test_ts_by_year_weekly_normalization_keeps_last_point_per_week() -> None:
    idx = pd.to_datetime(
        [
            "2024-01-05",
            "2024-01-08",
            "2024-01-12",
            "2024-01-19",
            "2024-01-26",
        ]
    )
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 4.0]}, index=idx)

    out = ts_by_year(df, frequency="W", start_day=5, start_month=1)
    expected_output = [0.0, 2.0, 3.0, 4.0]

    assert list(out.columns) == [2024]
    assert out[2024].dropna().tolist() == expected_output


def test_ts_by_year_over_year_drops_incomplete_trailing_season() -> None:
    idx = pd.date_range("2023-10-01", "2024-07-01", freq="D")
    df = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)

    out = ts_by_year(
        df,
        frequency="D",
        start_day=1,
        start_month=10,
        end_day=30,
        end_month=9,
        over_year=True,
    )

    assert list(out.columns) == [2023]
    assert out.loc[0, 2023] == 0.0
    assert out[2023].dropna().iloc[-1] == float(len(df) - 1)


def test_ts_by_year_winter_season_assigns_next_year_april_to_previous_column() -> None:
    idx = pd.date_range("2023-10-01", "2025-04-30", freq="D")
    df = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)

    out = ts_by_year(
        df,
        frequency="D",
        start_day=1,
        start_month=10,
        end_day=1,
        end_month=5,
        over_year=True,
    )

    assert list(out.columns) == [2023, 2024]
    assert int(out[2023].notna().sum()) == 213  # Oct-2023 -> Apr-2024 (leap year)
    assert int(out[2024].notna().sum()) == 212  # Oct-2024 -> Apr-2025

    oct_2023_pos = (pd.Timestamp("2023-10-01") - pd.Timestamp("2023-10-01")).days
    apr_2024_pos = (pd.Timestamp("2024-04-30") - pd.Timestamp("2023-10-01")).days
    oct_2024_pos = (pd.Timestamp("2024-10-01") - pd.Timestamp("2024-10-01")).days
    apr_2025_pos = (pd.Timestamp("2025-04-30") - pd.Timestamp("2024-10-01")).days

    assert out.loc[oct_2023_pos, 2023] == df.loc[pd.Timestamp("2023-10-01"), "x"]
    assert out.loc[apr_2024_pos, 2023] == df.loc[pd.Timestamp("2024-04-30"), "x"]
    assert np.isnan(out.loc[apr_2024_pos, 2024])

    assert out.loc[oct_2024_pos, 2024] == df.loc[pd.Timestamp("2024-10-01"), "x"]
    assert out.loc[apr_2025_pos, 2024] == df.loc[pd.Timestamp("2025-04-30"), "x"]


def test_ts_by_year_does_not_fallback_to_calendar_year_when_season_slice_is_empty() -> None:
    idx = pd.date_range("2023-10-15", "2024-10-10", freq="D")
    df = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)

    out = ts_by_year(
        df,
        frequency="D",
        start_day=15,
        start_month=10,
        end_day=14,
        end_month=10,
        over_year=True,
    )

    assert list(out.columns) == [2023]


def test_ts_by_year_handles_leap_day_defaults_without_error() -> None:
    idx = pd.to_datetime(["2024-02-29", "2024-03-01", "2025-03-01"])
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]}, index=idx)

    out = ts_by_year(df, frequency="D")

    assert list(out.columns) == [2024, 2025]
    assert out.loc[0, 2024] == 1.0
    assert out.loc[1, 2024] == 2.0
    assert out.loc[1, 2025] == 3.0


def test_ts_by_year_supports_tz_aware_index() -> None:
    idx = pd.date_range("2024-01-01", "2024-01-10", freq="D", tz="UTC")
    df = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)

    out = ts_by_year(df, frequency="D", start_day=1, start_month=1)

    assert list(out.columns) == [2024]
    assert out.loc[0, 2024] == 0.0
    assert out.loc[9, 2024] == 9.0


def test_ts_by_year_can_return_dummy_date_index_for_plotting() -> None:
    idx = pd.to_datetime(
        [
            "2024-01-05",
            "2024-01-08",
            "2024-01-12",
            "2024-01-19",
            "2024-01-26",
        ]
    )
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 4.0]}, index=idx)

    out = ts_by_year(
        df,
        frequency="W",
        start_day=5,
        start_month=1,
        dummy_date_index=True,
    )

    current_year = pd.Timestamp.today().year
    assert isinstance(out.index, pd.DatetimeIndex)
    assert out.index[0] == pd.Timestamp(current_year, 1, 5)
    assert out.index[1] == pd.Timestamp(current_year, 1, 12)
    assert out[2024].dropna().tolist() == [0.0, 2.0, 3.0, 4.0]


def test_ts_by_year_dummy_date_index_trims_seasonal_axis_to_oct_apr() -> None:
    idx = pd.date_range("2024-10-01", "2026-04-30", freq="D")
    df = pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)

    out = ts_by_year(
        df,
        frequency="D",
        start_day=1,
        start_month=10,
        end_day=1,
        end_month=5,
        over_year=True,
        dummy_date_index=True,
    )

    current_year = pd.Timestamp.today().year
    assert isinstance(out.index, pd.DatetimeIndex)
    assert out.index[0] == pd.Timestamp(current_year, 10, 1)
    assert out.index[-1] == pd.Timestamp(current_year + 1, 4, 30)


def test_ts_by_year_accepts_datetime_indexed_series() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    series = pd.Series(np.arange(5, dtype=float), index=idx, name="x")

    out = ts_by_year(series, frequency="D", start_day=1, start_month=1)

    assert list(out.columns) == [2024]
    assert out.loc[0, 2024] == 0.0
    assert out.loc[4, 2024] == 4.0


def test_ts_by_year_accepts_datetime_indexed_series_without_name() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    series = pd.Series([1.0, 2.0, 3.0], index=idx)

    out = ts_by_year(series, frequency="D", start_day=1, start_month=1)

    assert list(out.columns) == [2024]
    assert out.loc[0, 2024] == 1.0
    assert out.loc[2, 2024] == 3.0
