from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.table import render_table_html, resolve_table_style, table_with_linked_plots_monthly


def test_inventory_summary_reproduces_mixed_aggregates_quarters_and_year_comparisons() -> None:
    index = pd.date_range("2017-01-01", "2025-06-17")
    t = np.arange(len(index), dtype=float)
    frame = pd.DataFrame({"Stock": t**2, "Flow": t / 10, "Level": t}, index=index)
    output = table_with_linked_plots_monthly(
        frame,
        "Inventory",
        aggregation_type="diff",
        aggregation_columns={"Flow": "mean", "Level": None},
        windows=(5,),
        history_months=3,
        history_quarters=4,
        include_qtd=True,
        comparison_years=5,
        exclude_years=[2020],
        highlighting_rules={"seasonal": 5},
        moving_average_window=None,
    )["Inventory"]
    data = output["data"].set_index("Inventory")
    assert list(data.index) == ["Stock [Change]", "Flow [MA]", "Level [Level]"]
    assert data.loc["Stock [Change]", "5d Change"] == frame.Stock.iloc[-1] - frame.Stock.iloc[-6]
    assert data.loc["Flow [MA]", "5d Change"] == pytest.approx(frame.Flow.tail(5).mean())
    assert data.loc["Level [Level]", "5d Change"] == frame.Level.iloc[-1]
    assert data.loc["Stock [Change]", "2025-05"] == frame.Stock.loc["2025-05-31"] - frame.Stock.loc["2025-04-30"]
    assert data.loc["Stock [Change]", "QTD"] == frame.Stock.iloc[-1] - frame.Stock.loc["2025-03-31"]
    assert data.loc["Stock [Change]", "2025Q1"] == frame.Stock.loc["2025-03-31"] - frame.Stock.loc["2024-12-31"]
    assert data.loc["Flow [MA]", "QTD"] == pytest.approx(frame.Flow.loc["2025-04-01":].mean())
    history = [
        frame.Stock.loc[f"{year}-06-17"] - frame.Stock.loc[f"{year}-06-12"] for year in [2019, 2021, 2022, 2023, 2024]
    ]
    assert data.loc["Stock [Change]", "Y-1 5d Change"] == history[-1]
    assert data.loc["Stock [Change]", "5Y 5d Change"] == pytest.approx(np.mean(history))
    assert data.loc["Stock [Change]", "_mean"] == pytest.approx(np.mean(history))
    assert data.loc["Stock [Change]", "_std"] == pytest.approx(np.std(history, ddof=1))
    assert "_mean" not in render_table_html(output["data"], output["style"])


def test_all_configurable_windows_and_history_columns_receive_formats_and_rules() -> None:
    index = pd.date_range("2023-01-01", "2025-08-12")
    frame = pd.DataFrame({"Flow": np.arange(len(index), dtype=float)}, index=index)
    output = table_with_linked_plots_monthly(
        frame,
        "Flows",
        windows=(3, 17, 30),
        history_months=12,
        history_quarters=4,
        include_qtd=True,
        aggregation_type="ma",
        highlighting_rules={"window": 65},
        benchmark_month="2024-01-01",
        row_plot_links=True,
        all_plots_link=True,
    )["Flows"]
    row = output["data"].iloc[0]
    assert row["3d MA"] == pytest.approx(frame.Flow.tail(3).mean())
    assert row["17d MA"] == pytest.approx(frame.Flow.tail(17).mean())
    assert row["30d MA"] == pytest.approx(frame.Flow.tail(30).mean())
    assert row["3d MA vs Jan2024"] == pytest.approx(frame.Flow.tail(3).mean() - frame.Flow.loc["2024-01"].mean())
    assert row["_mean2"] == pytest.approx(frame.Flow.rolling(30).mean().iloc[-66:-1].mean())
    resolved = resolve_table_style(output["data"], output["style"])
    for field in resolved.visible_columns[1:]:
        assert resolved.formats[field].kind == "number"
        assert resolved.cell_css[(0, field)]["text-align"] == "center"
    assert len(resolved.visible_columns) > 20
    assert output["plot_names"] == ["flows-flow-seasonal-mva"]


def test_monthly_consensus_uses_month_intervals_and_preserves_update_metadata() -> None:
    dates = pd.date_range("2021-01-01", "2025-06-01", freq="MS")
    frame = pd.DataFrame(
        {"Consensus": np.arange(len(dates), dtype=float) ** 2, "_last_update": "2025-06-04"}, index=dates
    )
    output = table_with_linked_plots_monthly(
        frame,
        "Stocks",
        input_frequency="M",
        windows=(1,),
        history_months=3,
        history_quarters=3,
        include_qtd=True,
        comparison_years=5,
        aggregation_type="diff",
        columns_filter=["Consensus", "_last_update"],
        moving_average_window=None,
    )["Stocks"]
    row = output["data"].iloc[0]
    levels = frame.Consensus
    assert row["1m Change"] == levels.iloc[-1] - levels.iloc[-2]
    assert row["2025-05"] == levels.loc["2025-05-01"] - levels.loc["2025-04-01"]
    assert row["Y-1 1m Change"] == levels.loc["2024-06-01"] - levels.loc["2024-05-01"]
    assert row["QTD"] == levels.loc["2025-06-01"] - levels.loc["2025-03-01"]
    assert row["_last_update"] == "2025-06-04"
    assert "_last_update" in output["style"]["options"]["hidden_columns"]
    assert len(output["plots"]) == 1
    assert "_last_update" in frame


def test_mtd_rolling_means_use_prior_calendar_month_end_for_each_diff_series() -> None:
    dates = pd.date_range("2025-01-01 16:00", "2025-03-17 16:00", tz="Europe/London")
    frame = pd.DataFrame(
        {"A": np.arange(len(dates), dtype=float), "B": np.arange(len(dates), dtype=float) ** 2}, index=dates
    )
    output = table_with_linked_plots_monthly(
        frame,
        "Stocks",
        windows=(3, 10),
        aggregation_type="diff",
        aggregation_columns={"B": "diff"},
        mtd=True,
        moving_average_window=None,
    )["Stocks"]["data"]
    for position, field in enumerate(frame):
        for window in (3, 10):
            expected = frame[field].tail(window).mean() - frame[field].loc["2025-02"].iloc[-1]
            assert output.loc[position, f"{window}d Change (MTD basis)"] == pytest.approx(expected)


def test_asof_is_applied_before_filling_smoothing_and_companion_charts() -> None:
    dates = pd.date_range("2024-01-01", "2025-03-17")
    frame = pd.DataFrame({"A": np.arange(len(dates), dtype=float)}, index=dates)
    frame.loc["2025-02-04", "A"] = np.nan
    original = frame.copy()
    kwargs = dict(header="Stocks", windows=(5,), aggregation_type="diff", smooth=3, fill_na="bfill")
    full = table_with_linked_plots_monthly(frame.iloc[::-1], as_of="2025-02-04", **kwargs)["Stocks"]
    clipped = table_with_linked_plots_monthly(frame.loc[:"2025-02-04"], **kwargs)["Stocks"]
    pd.testing.assert_frame_equal(full["data"], clipped["data"])
    assert full["plots"][0].to_json() == clipped["plots"][0].to_json()
    assert pd.isna(full["data"].loc[0, "5d Change"])
    pd.testing.assert_frame_equal(frame, original)


def test_missing_history_and_excluded_prior_year_are_not_relabelled_or_zero_filled() -> None:
    dates = pd.date_range("2019-01-01", "2021-04-12")
    frame = pd.DataFrame({"A": np.arange(len(dates), dtype=float)}, index=dates)
    frame.loc["2021-03", "A"] = np.nan
    output = table_with_linked_plots_monthly(
        frame,
        "Flows",
        windows=(5,),
        aggregation_type="sum",
        comparison_years=5,
        exclude_years=[2020],
        moving_average_window=None,
    )["Flows"]["data"]
    assert pd.isna(output.loc[0, "Y-1 5d Sum"])
    assert pd.isna(output.loc[0, "2021-03"])
    short = table_with_linked_plots_monthly(frame.iloc[-3:], "Short", aggregation_type="mean")["Short"]
    assert pd.isna(short["data"].loc[0, "10d MA"])
    assert short["plots"][0].layout.annotations[0].text == "Insufficient observations"


@pytest.mark.parametrize(
    "options",
    [
        {"windows": ()},
        {"windows": (5, 5)},
        {"history_quarters": -1},
        {"smooth": 0},
        {"mtd": True, "smooth": 2},
        {"benchmark_month": "2024-01-01", "benchmark_quarter": "2024Q1"},
    ],
)
def test_summary_rejects_ambiguous_options(options) -> None:
    frame = pd.DataFrame({"A": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2))
    with pytest.raises(ValueError):
        table_with_linked_plots_monthly(frame, "Summary", **options)
