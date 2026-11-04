from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from runbook.core.table import (
    doe_crude_table,
    doe_detail_table,
    doe_distillates_table,
    doe_mogas_table,
    doe_overview_table,
    doe_signal_table,
    render_table_html,
    resolve_table_style,
)


@pytest.fixture
def weekly() -> pd.DataFrame:
    index = pd.date_range("2018-01-03", "2026-05-20", freq="W-WED")
    step = np.arange(len(index), dtype=float)
    return pd.DataFrame(
        {
            "Stocks": 100_000 + step * 100,
            "Demand": 20_000 + step * 10,
            "Runs": 15_000 + step * 5,
            "Production": 12_000 + step * 3,
        },
        index=index,
    )


def test_doe_signal_table_formats_the_prepared_signal_snapshot() -> None:
    source = pd.DataFrame(
        {
            "Stocks Change": ["Crude", "PADD2-Cushing", "Whisper"],
            "Weekly Chg (kb)": [1200.0, -300.0, 400.0],
            "4w average change (%)": [0.012, -0.004, 0.002],
            "4y z-score": [1.2, -0.4, 0.1],
            "s-curve signal": [0.83, -0.38, np.nan],
            "Contract": ["COZ6", "CLZ6F7", None],
            "Position": [120.0, -45.0, np.nan],
            "Position chg": [10.0, -5.0, np.nan],
        }
    )
    original = source.copy()
    payload = doe_signal_table(source)["DOE inventory signals"]
    style = resolve_table_style(payload["data"], payload["style"])

    assert payload["data"].index.tolist() == ["Crude", "PADD2-Cushing", "Whisper"]
    assert style.formats["4w average change (%)"].kind == "percent"
    assert style.formats["Weekly Chg (kb)"].digits == 0
    html = render_table_html(payload["data"], payload["style"])
    assert "1.2%" in html and "1,200" in html
    pd.testing.assert_frame_equal(source, original)


def test_doe_overview_table_reproduces_change_and_demand_level_rows(weekly: pd.DataFrame) -> None:
    source = weekly[["Stocks", "Demand", "Runs"]].rename(columns={"Stocks": "Liquids"})
    original = source.copy()
    result = doe_overview_table(source)["Runs, Demand and Stocks (mb), average 4w level for Demand"]["data"]

    assert result.index.tolist() == ["Liquids", "Demand (Outright)", "Runs"]
    assert result.loc["Liquids", "Latest"] == source.Liquids.iloc[-1]
    assert result.loc["Liquids", "1 week change"] == source.Liquids.diff().iloc[-1]
    assert result.loc["Liquids", "4 week change"] == source.Liquids.diff(4).iloc[-1]
    assert result.loc["Demand (Outright)", "4 week change"] == source.Demand.rolling(4).mean().iloc[-1]
    assert result.loc["Liquids", "4w chg 18-25"] == pytest.approx(400)
    assert result.loc["Liquids", "Next 4w chg 18-25"] == pytest.approx(400)
    assert result.loc["Liquids", "last_update"] == source.index[-1].strftime("%Y-%m-%d")
    pd.testing.assert_frame_equal(source, original)


def test_doe_detail_table_reproduces_balance_calculations_and_consensus(weekly: pd.DataFrame) -> None:
    source = weekly[["Stocks", "Demand", "Runs", "Production"]]
    original = source.copy()
    payload = doe_detail_table(
        source,
        consensus={"1 week change": -50.0, "4 week change": -75.0},
    )["DOE report detailed"]
    result = payload["data"]

    assert result.index.tolist() == [
        "Stocks (kb)",
        "Demand",
        "Runs",
        "Production",
        "Change in stock (kbd)",
        "Consensus Stocks chg (kbd)",
    ]
    assert result.loc["Stocks (kb)", "Latest"] == source.Stocks.iloc[-1]
    assert result.loc["Stocks (kb)", "4 week average"] == source.Stocks.rolling(4).mean().iloc[-1]
    assert pd.isna(result.loc["Change in stock (kbd)", "Latest"])
    assert result.loc["Change in stock (kbd)", "1 week change"] == pytest.approx(source.Stocks.diff().iloc[-1] / 7)
    assert result.loc["Change in stock (kbd)", "4 week change"] == pytest.approx(source.Stocks.diff(4).iloc[-1] / 28)
    assert result.loc["Stocks (kb)", "4w chg 18-25"] == pytest.approx(400)
    assert result.loc["Consensus Stocks chg (kbd)", "1 week change"] == -50
    assert pd.isna(result.loc["Change in stock (kbd)", "last_update"])
    render_table_html(result, payload["style"])
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize(
    ("template", "header"),
    [
        (doe_crude_table, "DOE Crude report detailed"),
        (doe_mogas_table, "DOE Mogas report detailed"),
        (doe_distillates_table, "DOE Disty report detailed"),
    ],
)
def test_named_doe_detail_templates_use_report_headers(weekly, template, header) -> None:
    assert header in template(weekly)


def test_doe_templates_validate_their_required_inputs(weekly: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="Stocks"):
        doe_detail_table(weekly.drop(columns="Stocks"))
    with pytest.raises(ValueError, match="Unknown demand"):
        doe_overview_table(weekly, demand_columns=["Missing"])
    with pytest.raises(TypeError, match="DatetimeIndex"):
        doe_detail_table(weekly.reset_index(drop=True))
