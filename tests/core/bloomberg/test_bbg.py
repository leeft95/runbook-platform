from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from runbook.core.bloomberg import bbg


@pytest.mark.parametrize(
    ("tickers", "fields", "columns", "values"),
    [
        (["A"], ["PX_LAST"], pd.Index(["PX_LAST"]), [[1.0], [5.0]]),
        (["A"], ["PX_HIGH", "PX_LAST"], pd.Index(["PX_HIGH", "PX_LAST"]), [[3.0, 1.0], [7.0, 5.0]]),
        (["B", "A"], ["PX_LAST"], pd.Index(["A", "B"]), [[1.0, 2.0], [5.0, np.nan]]),
        (
            ["B", "A"],
            ["PX_HIGH", "PX_LAST"],
            pd.MultiIndex.from_product([["PX_HIGH", "PX_LAST"], ["A", "B"]], names=["field", "ticker"]),
            [[3.0, 4.0, 1.0, 2.0], [7.0, np.nan, 5.0, np.nan]],
        ),
    ],
    ids=["one-ticker-one-field", "one-ticker-many-fields", "many-tickers-one-field", "many-tickers-many-fields"],
)
def test_bdh_column_shapes(tickers, fields, columns, values):
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-02", "2026-07-01", "2026-07-01"]),
            "security": ["A", "B", "A"],
            "PX_LAST": [5.0, 2.0, 1.0],
            "PX_HIGH": [7.0, 4.0, 3.0],
        }
    )
    result = bbg._process(raw[raw["security"].isin(tickers)], bbg.BBGReturnTypes.BDH, tickers, fields)

    expected = pd.DataFrame(values, index=pd.DatetimeIndex(["2026-07-01", "2026-07-02"], name="date"), columns=columns)
    pd.testing.assert_frame_equal(result, expected)


@pytest.mark.parametrize("fields", [["PX_LAST"], ["PX_LAST", "PX_HIGH"]])
def test_bdh_missing_ticker_keeps_requested_column_shape(fields):
    raw = pd.DataFrame(
        {"date": pd.to_datetime(["2026-07-01"]), "security": ["A"], "PX_LAST": [1.0], "PX_HIGH": [np.nan]}
    )
    result = bbg._normalise_bdh(raw, ["A", "B"], fields)

    if len(fields) == 1:
        pd.testing.assert_index_equal(result.columns, pd.Index(["A"]))
        assert result.loc["2026-07-01", "A"] == 1.0
    else:
        pd.testing.assert_index_equal(
            result.columns, pd.MultiIndex.from_product([fields, ["A"]], names=["field", "ticker"])
        )
        assert result.loc["2026-07-01", ("PX_LAST", "A")] == 1.0
        assert result["PX_HIGH"].isna().all().all()


@pytest.mark.parametrize("tickers", [["A"], ["A", "B"]])
def test_bdh_missing_field_preserves_available_values(tickers):
    raw = pd.DataFrame(
        {"date": pd.to_datetime(["2026-07-01"] * len(tickers)), "security": tickers, "PX_LAST": [1.0] * len(tickers)}
    )
    result = bbg._normalise_bdh(raw, tickers, ["PX_LAST", "PX_HIGH"])

    assert (result["PX_LAST"].to_numpy() == 1.0).all()
    assert result["PX_HIGH"].isna().to_numpy().all()
    assert isinstance(result.columns, pd.MultiIndex) == (len(tickers) > 1)


@pytest.mark.parametrize("tickers", [["A"], ["A", "B"]])
@pytest.mark.parametrize("fields", [["PX_LAST"], ["PX_LAST", "PX_HIGH"]])
def test_bdh_empty_response(tickers, fields):
    result = bbg._normalise_bdh(pd.DataFrame(), tickers, fields)

    assert result.empty
    assert result.index.name == "date"
    assert isinstance(result.columns, pd.MultiIndex) == (len(tickers) > 1 and len(fields) > 1)


@pytest.mark.parametrize("ticker", ["A", ["A"], ["B", "A"]])
@pytest.mark.parametrize("field", ["PX_LAST", ["PX_LAST"], ["PX_LAST", "PX_HIGH"]])
def test_bdh_wrapper_normalizes_inputs_and_output(monkeypatch, ticker, field):
    tickers = [ticker] if isinstance(ticker, str) else ticker
    fields = [field] if isinstance(field, str) else field
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-01"] * len(tickers)),
            "security": tickers,
            "PX_LAST": [1.0] * len(tickers),
            "PX_HIGH": [2.0] * len(tickers),
        }
    )
    connection = Mock()
    connection.bdh.return_value = raw
    query = Mock()
    query.return_value.__enter__ = Mock(return_value=connection)
    query.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(bbg, "_blp_types", lambda: (None, query))
    monkeypatch.setattr(bbg, "_custom_api_parser", lambda: None)
    overrides = [("CURRENCY", "USD")]
    options = {"periodicitySelection": "DAILY"}

    result = bbg.bdh(ticker, field, "2026-07-01", "2026-07-02", overrides=overrides, options=options)

    connection.bdh.assert_called_once_with(tickers, fields, "20260701", "20260702", overrides, options)
    pd.testing.assert_frame_equal(result, bbg._normalise_bdh(raw, tickers, fields))
