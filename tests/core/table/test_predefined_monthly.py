from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.table import render_table_html, table_with_linked_plots_monthly
from runbook.core.timeseries.analysis import (
    AggregationModes,
    MovingAvgModes,
    calculate_moving_average,
)


@pytest.mark.parametrize("highlighting", [None, {"window": 20}])
def test_quarter_benchmark_is_independent_of_highlighting(highlighting) -> None:
    data = pd.DataFrame({"x": np.arange(260.0)}, index=pd.date_range("2024-01-01", periods=260))
    out = table_with_linked_plots_monthly(
        data,
        "Asset",
        aggregation_type=AggregationModes.MA,
        benchmark_quarter="2024-01-01",
        highlighting_rules=highlighting,
    )["Asset"]["data"]
    expected = data["x"].rolling(20).mean().iloc[-1] - data["x"].resample("ME").mean().iloc[:3].mean()
    assert out.loc[0, "20d MA vs 2024-01-01"] == pytest.approx(expected)


def test_monthly_sorts_before_calculations_filling_and_companion_plots() -> None:
    data = pd.DataFrame({"x": np.arange(260.0)}, index=pd.date_range("2024-01-01", periods=260))
    data.iloc[-2] = np.nan
    original = data.copy()
    ascending = table_with_linked_plots_monthly(data, "Asset", aggregation_type=AggregationModes.DIFF, fill_na="ffill")[
        "Asset"
    ]
    descending = table_with_linked_plots_monthly(
        data.iloc[::-1], "Asset", aggregation_type=AggregationModes.DIFF, fill_na="ffill"
    )["Asset"]
    pd.testing.assert_frame_equal(ascending["data"], descending["data"])
    assert ascending["plots"][0].to_json() == descending["plots"][0].to_json()
    pd.testing.assert_frame_equal(data, original)


def test_table_with_linked_plots_monthly_applies_column_overrides_and_row_suffixes() -> None:
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    raw_df = pd.DataFrame(
        {
            "Brent": np.linspace(10.0, 269.0, num=len(idx)),
            "WTI": np.linspace(100.0, 359.0, num=len(idx)),
        },
        index=idx,
    )

    out = table_with_linked_plots_monthly(
        raw_df=raw_df,
        header="Commodity",
        aggregation_type=AggregationModes.DIFF,
        aggregation_columns={
            "Brent": AggregationModes.MA,
            "WTI": AggregationModes.SUM,
        },
    )
    table_df = out["Commodity"]["data"]

    assert isinstance(table_df.index, pd.RangeIndex)
    assert list(table_df["Commodity"]) == ["Brent [MA]", "WTI [Sum]"]
    assert all(item["label"] != "Commodity" for item in out["Commodity"]["style"]["sizing"]["columns"])
    assert "10d Change" in table_df.columns
    assert "20d Change" in table_df.columns
    assert "Brent [MA]" in set(table_df["Commodity"])
    assert "WTI [Sum]" in set(table_df["Commodity"])


def test_table_with_linked_plots_monthly_uses_moving_average_type_for_ma_mode() -> None:
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    raw_df = pd.DataFrame({"x": np.linspace(1.0, 260.0, num=len(idx))}, index=idx)

    out = table_with_linked_plots_monthly(
        raw_df=raw_df,
        header="Asset",
        aggregation_type=AggregationModes.MA,
        moving_average_type=MovingAvgModes.EXPONENTIAL,
    )
    table_df = out["Asset"]["data"]

    actual_10d = float(table_df.loc[table_df["Asset"] == "x", "10d MA"].iloc[0])
    expected_10d = float(
        pd.Series(calculate_moving_average(raw_df["x"], window=10, kind=MovingAvgModes.EXPONENTIAL)).iloc[-1]
    )
    simple_10d = float(raw_df["x"].rolling(10).mean().iloc[-1])

    assert np.isclose(actual_10d, expected_10d)
    assert not np.isclose(actual_10d, simple_10d)


def test_table_with_linked_plots_monthly_window_highlighting_routes_to_window_mode() -> None:
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    raw_df = pd.DataFrame({"x": np.linspace(1.0, 260.0, num=len(idx))}, index=idx)

    out = table_with_linked_plots_monthly(
        raw_df=raw_df,
        header="Asset",
        aggregation_type=None,
        highlighting_rules={"window": 5},
    )
    table_df = out["Asset"]["data"]

    row = table_df.loc[table_df["Asset"] == "x"].iloc[0]
    expected_mean = float(raw_df["x"].rolling(5).mean().iloc[-2])
    expected_std = float(raw_df["x"].rolling(5).std().iloc[-2])

    assert "_mean" in table_df.columns
    assert "_std" in table_df.columns
    assert "_mean1" in table_df.columns
    assert "_std1" in table_df.columns
    assert np.isclose(float(row["_mean"]), expected_mean)
    assert np.isclose(float(row["_std"]), expected_std)


def test_table_with_linked_plots_monthly_hides_helper_columns_in_rendered_html() -> None:
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    raw_df = pd.DataFrame({"x": np.linspace(1.0, 260.0, num=len(idx))}, index=idx)

    out = table_with_linked_plots_monthly(
        raw_df=raw_df,
        header="Asset",
        aggregation_type=None,
        highlighting_rules={"window": 5},
    )
    table_df = out["Asset"]["data"]
    html = render_table_html(table_df, out["Asset"]["style"])

    assert "_mean" not in html
    assert "_std" not in html
    assert "_mean1" not in html
    assert "_std1" not in html


def test_table_with_linked_plots_monthly_label_column_is_formatted_and_helper_hidden() -> None:
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    raw_df = pd.DataFrame({"x": np.linspace(1.0, 260.0, num=len(idx))}, index=idx)

    out = table_with_linked_plots_monthly(raw_df, header="Asset", row_plot_links=True)
    table_df = out["Asset"]["data"]
    html = render_table_html(table_df, out["Asset"]["style"])

    assert table_df.columns[0] == "Asset"
    assert out["Asset"]["style"]["options"]["show_index"] is False
    assert out["Asset"]["style"]["options"]["hidden_columns"] == ["_plot_link"]
    assert ">x</a>" in html
    assert "_plot_link" not in html
    assert ">260<" in html
