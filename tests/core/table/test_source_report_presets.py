import numpy as np
import pandas as pd
import pytest

from runbook.core.table.templates import (
    futures_price_range_table,
    kpler_inventory_consensus_table,
    kpler_inventory_table,
    oil_dashboard_table,
    oil_on_water_table,
    product_inventory_consensus_table,
    russia_exports_table,
)
from runbook.core.table import render_table_html, resolve_table_style


@pytest.fixture
def daily():
    dates = pd.date_range("2023-01-01", "2025-07-15")
    t = np.arange(len(dates), dtype=float)
    return pd.DataFrame({"Stock": 1000 + t**2 / 100, "Flow": 30 + np.sin(t / 15)}, index=dates)


def test_inventory_report_preserves_row_order_mixed_aggregations_and_four_quarters(daily):
    original = daily.copy()
    result = kpler_inventory_table(daily, "Stocks", aggregation_columns={"Flow": "mean"})["Stocks"]["data"]
    assert result.Stocks.tolist() == ["Stock [Change]", "Flow [MA]"]
    result = result.set_index("Stocks")
    assert result.loc["Stock [Change]", "20d Change"] == pytest.approx(daily.Stock.diff(20).iloc[-1])
    assert result.loc["Flow [MA]", "20d Change"] == pytest.approx(daily.Flow.tail(20).mean())
    assert [col for col in result if "Q" in col] == ["QTD", "2025Q2", "2025Q1", "2024Q4", "2024Q3"]
    assert result.loc["Stock [Change]", "2025-06"] == pytest.approx(
        daily.Stock.loc["2025-06-30"] - daily.Stock.loc["2025-05-31"]
    )
    pd.testing.assert_frame_equal(daily, original)


def test_exports_report_uses_means_quarter_benchmark_and_92_observation_highlights(daily):
    result = russia_exports_table(daily[["Flow"]], benchmark_quarter="2025Q1")["Total export (kbd)"]["data"]
    row = result.iloc[0]
    means = daily.Flow.rolling(20).mean()
    quarter = daily.Flow.loc["2025-01-01":"2025-03-31"].resample("ME").mean().mean()
    assert row["10d MA"] == pytest.approx(daily.Flow.tail(10).mean())
    assert row["20d MA"] == pytest.approx(means.iloc[-1])
    assert row["20d MA vs 2025Q1"] == pytest.approx(means.iloc[-1] - quarter)
    assert row["_mean1"] == pytest.approx(means.iloc[:-1].tail(92).mean())
    assert row["_std1"] == pytest.approx(means.iloc[:-1].tail(92).std())
    assert "QTD" not in result and "2025Q2" not in result
    assert all(month in result for month in ["2025-06", "2025-05", "2025-04", "2025-03", "2025-02"])


def test_consensus_variants_preserve_monthly_balances_levels_or_changes(daily):
    monthly = daily[["Flow"]].resample("MS").mean()
    monthly["_last_update"] = "2025-07-15"
    result = kpler_inventory_consensus_table(monthly)["Crude Stocks"]["data"].iloc[0]
    assert result["1m MA"] == pytest.approx(monthly.Flow.iloc[-1])
    assert result["2025Q2"] == pytest.approx(monthly.Flow.loc["2025-04-01":"2025-06-01"].mean())
    assert "2024Q4" in result and "2024Q3" not in result
    product = product_inventory_consensus_table(monthly)["Product Stocks"]["data"].iloc[0]
    assert product["1m Level"] == pytest.approx(monthly.Flow.iloc[-1])
    assert product["2025Q2"] == pytest.approx(monthly.Flow.loc["2025-06-01"])
    for mode, column, value in [
        ("diff", "1m Change", monthly.Flow.diff().iloc[-1]),
        (None, "1m Level", monthly.Flow.iloc[-1]),
    ]:
        row = kpler_inventory_consensus_table(monthly, aggregation_type=mode)["Crude Stocks"]["data"].iloc[0]
        assert row[column] == pytest.approx(value)


def test_oil_on_water_preserves_report_difference_despite_mtd_row_name(daily):
    water = daily[["Stock"]].assign(**{"Total MTD Chg": daily.Stock})
    result = oil_on_water_table(water)["Oil on Water (mb)"]["data"].set_index("Oil on Water (mb)")
    assert result.loc["Stock [MA]", "20d MA"] == pytest.approx(daily.Stock.tail(20).mean())
    assert result.loc["Total MTD Chg [Change]", "20d MA"] == pytest.approx(daily.Stock.diff(20).iloc[-1])
    assert "2024Q4" in result and "2024Q3" not in result
    assert not any("MTD basis" in col for col in result)


def test_dashboard_keeps_ten_daily_rows_and_latest_twenty_observation_mean(daily):
    payload = oil_dashboard_table(daily[["Stock"]])["Liquids Price"]
    result = payload["data"]
    assert len(result) == 11
    assert result.Stock.iloc[:-1].tolist() == daily.Stock.tail(10).tolist()
    assert result.Stock.iloc[-1] == pytest.approx(daily.Stock.tail(20).mean())
    assert len(payload["plots"]) == 1


def test_price_range_report_formats_percentiles_without_changing_calculated_values():
    summary = pd.DataFrame(
        {
            "Current price vs history": ["Brent", "WTI"],
            "Current Price": [72.25, 68.40],
            "Percentile of 10yr Range": [0.35, -0.25],
            "Z-score of 10yr Range": [0.65, -0.40],
            "10yr Avg Price": [68.10, 71.30],
            "10yr Max": [105.0, 102.0],
            "10yr Min": [35.0, 32.0],
        }
    )
    original = summary.copy()
    payload = futures_price_range_table(summary, separator_rows=[0])["Futures price range"]
    style = resolve_table_style(payload["data"], payload["style"])
    percentile = "Percentile of 10yr Range"
    assert style.formats[percentile].kind == "percent"
    assert style.formats[percentile].digits == 1
    assert style.formats["Current Price"].digits == 2
    assert style.formats["Z-score of 10yr Range"].digits == 2
    assert style.cell_css[(0, "Current Price")]["border-bottom"] == "1px solid #000000"
    bar = next(rule for rule in payload["style"]["rules"] if rule["id"] == "bars")["action"]["data_bar"]
    assert bar["vmin"] == -1 and bar["vmax"] == 1
    rendered = render_table_html(payload["data"], payload["style"])
    assert ">35.0%<" in rendered and ">-25.0%<" in rendered and ">68.40<" in rendered
    assert "linear-gradient" in rendered and "text-align: center" in rendered
    pd.testing.assert_frame_equal(summary, original)
    pd.testing.assert_frame_equal(payload["data"], original.set_index("Current price vs history"))
    assert payload["data"].index.tolist() == ["Brent", "WTI"]
    with pytest.raises(ValueError, match="Missing price-range"):
        futures_price_range_table(summary.drop(columns=percentile))
