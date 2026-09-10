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


@pytest.mark.parametrize(
    ("current_offset", "exclude_offsets", "current_value", "history_values"),
    [
        (None, [], 10, [1, 2]),
        (-1, [], 2, [1]),
        (None, [0], 2, [1]),
        (None, [-2, -1], 10, []),
        (None, [-2, -1, 0], 1000, []),
    ],
)
def test_plot_seasonal_selects_current_year_and_only_earlier_history(
    current_offset, exclude_offsets, current_value, history_values
) -> None:
    year = pd.Timestamp.today().year
    dates = [pd.Timestamp(year=year + offset, month=1, day=day) for offset in (-2, -1, 0, 1) for day in (1, 2)]
    df = pd.DataFrame({"value": np.repeat([1, 2, 10, 1000], 2)}, index=dates)
    fig = plot_seasonal(
        df,
        ytd=True,
        ytd_cum_sum=True,
        exclude_years=[year + offset for offset in exclude_offsets],
        **({"current_year": year + current_offset} if current_offset is not None else {}),
    )
    traces = {trace.name: trace for trace in fig.data}
    np.testing.assert_allclose(traces["YTD cumulative change"].y, [current_value, 2 * current_value])
    assert str(year + 1) in traces
    for label, reference in (
        ("5y Avg", np.mean(history_values) if history_values else None),
        ("Y-1", history_values[-1] if history_values else None),
    ):
        if reference is None:
            assert f"Cur Yr vs {label}" not in traces
            assert f"Cum Cur Yr vs {label}" not in traces
        else:
            difference = current_value - reference
            np.testing.assert_allclose(traces[f"Cur Yr vs {label}"].y, [difference, difference])
            np.testing.assert_allclose(traces[f"Cum Cur Yr vs {label}"].y, [difference, 2 * difference])


@pytest.mark.parametrize("ytd", [False, True])
@pytest.mark.parametrize("ytd_cum_sum", [False, True])
@pytest.mark.parametrize("five_year", [False, True])
@pytest.mark.parametrize("ytd_diff", [False, True])
@pytest.mark.parametrize("vs_average", [False, True])
def test_plot_seasonal_cumulative_flags_and_values(ytd, ytd_cum_sum, five_year, ytd_diff, vs_average) -> None:
    dates = [pd.Timestamp(year=year, month=1, day=day) for year in (2023, 2024, 2025) for day in (1, 2, 3)]
    df = pd.DataFrame({"value": [1, np.nan, 3, 2, 4, 8, 10, 20, 35]}, index=dates)
    fig = plot_seasonal(
        df,
        ytd=ytd,
        ytd_cum_sum=ytd_cum_sum,
        five_year=five_year,
        ytd_diff=ytd_diff,
        vs_average=vs_average,
    )
    expected = {}
    if ytd:
        expected["YTD cumulative change"] = [np.nan, 10, 25] if ytd_diff else [10, 30, 65]
    if ytd_cum_sum:
        if five_year:
            expected["Cum Cur Yr vs 5y Avg"] = [np.nan, 8, 19] if ytd_diff else [8.5, 24, 56]
        expected["Cum Cur Yr vs Y-1"] = [np.nan, 8, 19] if ytd_diff else [8, 24, 51]
    trace_names = {trace.name for trace in fig.data}
    assert ("Cur Yr vs 5y Avg" in trace_names) == (vs_average and five_year)
    assert ("Cur Yr vs Y-1" in trace_names) == vs_average
    cumulative_traces = {trace.name: trace for trace in fig.data if trace.name.startswith(("YTD", "Cum "))}
    assert cumulative_traces.keys() == expected.keys()
    for name, values in expected.items():
        trace = cumulative_traces[name]
        np.testing.assert_allclose(trace.y, values, equal_nan=True)
        assert trace.xaxis == ("x3" if vs_average else "x2")
        assert trace.yaxis == ("y3" if vs_average else "y2")
    assert len({trace.xaxis for trace in fig.data}) == 1 + int(vs_average) + int(ytd or ytd_cum_sum)


def test_plot_seasonal_cumulative_average_uses_last_five_years() -> None:
    dates = [pd.Timestamp(year=year, month=1, day=day) for year in range(2019, 2026) for day in (1, 2, 3)]
    df = pd.DataFrame({"value": np.repeat([100, 1, 2, 3, 4, 5, 10], 3)}, index=dates)
    fig = plot_seasonal(df, ytd_cum_sum=True, vs_average=False)
    trace = next(trace for trace in fig.data if trace.name == "Cum Cur Yr vs 5y Avg")
    np.testing.assert_allclose(trace.y, [7, 14, 21])


@pytest.mark.parametrize("ytd", [False, True])
def test_plot_seasonal_without_history_omits_cumulative_comparisons(ytd) -> None:
    df = pd.DataFrame({"value": [10, 20, 35]}, index=pd.date_range("2025-01-01", periods=3))
    fig = plot_seasonal(df, ytd=ytd, ytd_cum_sum=True, ytd_diff=True)
    assert {trace.name for trace in fig.data} == ({"2025", "YTD cumulative change"} if ytd else {"2025"})


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


@pytest.mark.parametrize("year", [2022, 2024, 2025])
def test_plot_seasonal_forecast_matches_historical_color(year: int) -> None:
    fig = plot_seasonal(
        df=_seasonal_fixture_df(),
        dash_from=pd.Timestamp(year=year, month=1, day=15),
        dash_name="Projection",
    )
    historical_index, historical = next((i, trace) for i, trace in enumerate(fig.data) if trace.name == str(year))
    forecast = next(trace for trace in fig.data if trace.name == f"{year}_Projection")
    colors = fig.layout.template.layout.colorway
    expected_color = historical.line.color or colors[historical_index % len(colors)]
    assert forecast.line.color == expected_color
    assert forecast.line.dash == "dash"
    if year < 2025:
        future = next(trace for trace in fig.data if trace.name == f"{year + 1}_Projection")
        assert future.line.color == "red"
        assert future.line.dash == "dash"


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
