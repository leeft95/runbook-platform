from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.plotting.seasonal import plot_cot, plot_seasonal


def _seasonal_fixture_df() -> pd.DataFrame:
    idx = pd.date_range("2018-01-01", "2025-01-31", freq="D")
    values = np.sin(np.linspace(0, 20, len(idx))) * 10 + np.linspace(-2, 2, len(idx))
    return pd.DataFrame({"value": values}, index=idx)


def _cot_fixture_df() -> pd.DataFrame:
    idx = pd.date_range("2021-01-03", periods=220, freq="W")
    t = np.arange(len(idx), dtype=float)
    return pd.DataFrame(
        {
            "Net": 50_000 + 1_500 * np.sin(t / 5.0),
            "Long": 80_000 + 2_000 * np.cos(t / 7.0),
            "Short": 30_000 + 1_200 * np.sin(t / 6.0),
            "PX_LAST": 70 + np.sin(t / 12.0),
            "Net OI": 0.01 * np.sin(t / 4.0),
            "Long OI": 0.02 * np.cos(t / 5.0),
            "Short OI": 0.015 * np.sin(t / 6.0),
            "Internal": np.cos(t / 10.0),
        },
        index=idx,
    )


def test_plot_seasonal_builds_three_stacked_subplots_when_enabled() -> None:
    seasonal_df = _seasonal_fixture_df()
    fig = plot_seasonal(
        df=seasonal_df,
        column="value",
        current_year=2025,
        vs_average=True,
        ytd_cum_sum=True,
    )
    assert {"x", "x2", "x3"}.issubset({trace.xaxis for trace in fig.data})


def test_plot_seasonal_excludes_year_columns() -> None:
    seasonal_df = _seasonal_fixture_df()
    fig = plot_seasonal(df=seasonal_df, column="value", current_year=2025, exclude_years=[2023])
    trace_names = {str(t.name) for t in fig.data}
    assert "2023" not in trace_names


def test_plot_seasonal_raises_when_current_year_excluded() -> None:
    seasonal_df = _seasonal_fixture_df()
    with pytest.raises(KeyError, match="current_year"):
        plot_seasonal(df=seasonal_df, column="value", current_year=2025, exclude_years=[2025])


def test_plot_seasonal_requires_datetime_index() -> None:
    bad_df = pd.DataFrame({"value": [1.0, 2.0, 3.0]})
    with pytest.raises(TypeError, match="DatetimeIndex"):
        plot_seasonal(df=bad_df)


def test_plot_seasonal_accepts_ts_by_year_args() -> None:
    seasonal_idx = pd.date_range("2024-01-01", periods=70, freq="D")
    seasonal_df = pd.DataFrame({"value": np.arange(70, dtype=float)}, index=seasonal_idx)

    fig = plot_seasonal(df=seasonal_df, start_month=2, start_day=1)

    first_x = pd.Timestamp(fig.data[0].x[0])
    assert first_x.month == 2
    assert first_x.day == 1


def test_plot_seasonal_forces_dummy_date_index() -> None:
    seasonal_idx = pd.date_range("2024-01-01", periods=3, freq="D")
    seasonal_df = pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=seasonal_idx)

    fig = plot_seasonal(df=seasonal_df)

    assert not isinstance(fig.data[0].x[0], (int, np.integer))


def test_plot_cot_builds_two_by_three_layout_with_secondary_axes() -> None:
    fig = plot_cot(
        data=_cot_fixture_df(),
        columns=None,
        title="COT",
        plot_titles=["Net", "Long", "Short"],
        freq="W",
    )

    xaxes = {trace.xaxis for trace in fig.data}
    yaxes = {trace.yaxis for trace in fig.data}
    assert {"x", "x2", "x3", "x4", "x5", "x6"}.issubset(xaxes)
    assert "y2" in yaxes
    assert "y8" in yaxes
