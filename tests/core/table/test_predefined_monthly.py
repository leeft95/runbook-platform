from __future__ import annotations

import numpy as np
import pandas as pd
from runbook.core.table import render_table_html, table_with_linked_plots_monthly
from runbook.core.timeseries.analysis import (
    AggregationModes,
    MovingAvgModes,
    calculate_moving_average,
)


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

    assert table_df.index.name == "Commodity"
    assert not isinstance(table_df.index, pd.RangeIndex)
    assert all(item["label"] != "Commodity" for item in out["Commodity"]["style"]["sizing"]["columns"])
    assert "10d Change" in table_df.columns
    assert "20d Change" in table_df.columns
    assert "Brent [MA]" in set(table_df.index.astype(str))
    assert "WTI [Sum]" in set(table_df.index.astype(str))


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

    actual_10d = float(table_df.loc[table_df.index == "x", "10d MA"].iloc[0])
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

    row = table_df.loc[table_df.index == "x"].iloc[0]
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
