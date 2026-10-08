from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from runbook.core.timeseries.cot import (
    cot_position_changes,
    cot_position_divergence,
    cot_summary,
    prepare_cot_data,
)


def _observations() -> pd.DataFrame:
    index = pd.date_range("2023-01-03", periods=140, freq="W-TUE")
    t = np.arange(len(index), dtype=float)
    return pd.DataFrame(
        {
            "Long": 100 + t**2,
            "Short": 50 + t,
            "OI": 30000 + t,
            "PX_LAST": 50 + t / 10,
            "VWAP": 49 + t / 10,
            "Internal": t / 100,
            "NC Long": 50 + t,
            "NC Short": 10 + t / 2,
        },
        index=index,
    )


def test_cot_summary_horizons_scores_and_asof_are_explicit() -> None:
    data = _observations()
    cutoff = data.index[-4]
    row = cot_summary(data.iloc[::-1], "Asset Fut", as_of=cutoff, contract_value=1000).iloc[0]
    history = data.loc[:cutoff]
    net = history.Long - history.Short
    expected4 = net.iloc[-1] - net.iloc[-5]
    assert row["4w change of net position"] == expected4
    assert row["Weekly Price Change"] == pytest.approx(history.PX_LAST.pct_change().iloc[-1])
    assert row["net change z score"] == pytest.approx(net.diff().iloc[-1] / net.diff().tail(52).std())
    assert row["4w delta change z score"] == pytest.approx(net.diff(4).iloc[-1] / net.diff(4).tail(52).std())
    assert row["Net percentile"] == 1.0
    assert row["Weekly Delta Change in millions"] == pytest.approx(
        net.diff().iloc[-1] * history.PX_LAST.iloc[-1] / 1000
    )
    prior = net.loc[net.index.year < cutoff.year].iloc[-1]
    assert row["YTD position change"] == net.iloc[-1] - prior
    assert row["Net Position (NC)"] == history["NC Long"].iloc[-1] - history["NC Short"].iloc[-1]
    mifid = cot_summary(history, "Funds", change_window=208).iloc[0]
    assert mifid["net change z score"] == pytest.approx(net.diff().iloc[-1] / net.diff().tail(208).std())


def test_cot_alignment_does_not_fill_positions_or_look_ahead() -> None:
    data = _observations().iloc[:8].reindex(pd.date_range("2023-01-02", "2023-03-01"))
    data.loc["2023-01-02", "PX_LAST"] = 12.0
    data.loc["2023-01-03", "PX_LAST"] = np.nan
    data.loc["2023-01-04", "PX_LAST"] = 99.0
    prepared = prepare_cot_data(data, as_of="2023-01-03", position_scale=0.25)
    assert list(prepared.index) == [pd.Timestamp("2023-01-03")]
    assert prepared.PX_LAST.iloc[0] == 12.0
    assert prepared.Long.iloc[0] == 25.0
    assert prepared["Net OI"].iloc[0] == pytest.approx(50 / 30000)


def test_internal_model_estimate_and_weekly_change_keep_placeholder_names() -> None:
    data = _observations()
    prepared = prepare_cot_data(data, position_scale=0.25)
    pd.testing.assert_series_equal(prepared.Internal, data.Internal)
    summary = cot_summary(data, "Asset")
    assert summary["Internal Change"].iloc[0] == pytest.approx(data.Internal.diff().iloc[-1])
    assert "CTA Change" not in summary


def test_cot_missing_history_and_zero_denominators_remain_missing() -> None:
    data = pd.DataFrame({"Long": [10.0], "Short": [0.0], "OI": [0.0]}, index=pd.to_datetime(["2025-03-04"]))
    result = cot_summary(data, "New asset")
    row = result.iloc[0]
    for field in (
        "% OI",
        "Long Short Ratio",
        "Weekly Price Change",
        "4w change of net position",
        "YTD position change",
        "net change z score",
        "Net percentile",
    ):
        assert pd.isna(row[field])
    assert cot_position_changes(result).empty
    assert cot_position_divergence(result).empty


def test_cot_screeners_use_signals_without_legacy_row_number_exclusions() -> None:
    frame = pd.DataFrame(
        {
            "net change z score": [2.0, 0.0, np.nan],
            "4w delta change z score": [0.0, -3.0, np.nan],
            "Weekly Delta Change": [10, -5, 0],
            "Weekly Price Change": [-0.1, 0.1, -0.1],
        },
        index=[12, 13, 14],
    )
    assert list(cot_position_changes(frame).index) == [12, 13]
    assert list(cot_position_divergence(frame).index) == [12, 13]


def test_cot_validates_duplicate_dates_and_optional_position_pairs() -> None:
    data = _observations()
    with pytest.raises(ValueError, match="unique"):
        prepare_cot_data(pd.concat([data, data.iloc[-1:]]))
    with pytest.raises(ValueError, match="together"):
        prepare_cot_data(data.drop(columns="NC Short"))
    with pytest.raises(ValueError, match="paired"):
        cot_summary(data, "Empty", as_of="2000-01-01")
