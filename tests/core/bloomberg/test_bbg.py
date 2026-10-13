from unittest.mock import Mock, call

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


def test_bdh_reuses_supplied_session_without_owning_lifecycle(monkeypatch):
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-01"]),
            "security": ["A"],
            "PX_LAST": [1.0],
        }
    )
    session = Mock()
    connection = Mock()
    connection.bdh.return_value = raw
    query = Mock(return_value=connection)
    monkeypatch.setattr(bbg, "_blp_types", lambda: (None, query))
    monkeypatch.setattr(bbg, "_custom_api_parser", lambda: None)

    result = bbg.bdh("A", "PX_LAST", "2026-07-01", "2026-07-02", session=session)

    assert connection.session is session
    connection.start.assert_called_once_with()
    session.start.assert_not_called()
    session.stop.assert_not_called()
    connection.bdh.assert_called_once_with(["A"], ["PX_LAST"], "20260701", "20260702", None, None)
    pd.testing.assert_frame_equal(result, bbg._normalise_bdh(raw, ["A"], ["PX_LAST"]))


def test_supplied_session_is_not_stopped_when_query_fails(monkeypatch):
    session = Mock()
    connection = Mock()
    connection.bdh.side_effect = RuntimeError("request failed")
    query = Mock(return_value=connection)
    monkeypatch.setattr(bbg, "_blp_types", lambda: (None, query))
    monkeypatch.setattr(bbg, "_custom_api_parser", lambda: None)

    with pytest.raises(RuntimeError, match="request failed"):
        bbg.bdh("A", "PX_LAST", "2026-07-01", "2026-07-02", session=session)

    connection.start.assert_called_once_with()
    session.start.assert_not_called()
    session.stop.assert_not_called()


def test_bdib_serializes_requests_on_supplied_session(monkeypatch):
    session = Mock()
    connection = Mock()
    query = Mock(return_value=connection)
    active = 0
    max_active = 0

    def fetch(ticker, *_args):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            return pd.DataFrame({"time": [pd.Timestamp("2026-07-01 10:00")], "close": [1.0]})
        finally:
            active -= 1

    connection.bdib.side_effect = fetch
    monkeypatch.setattr(bbg, "_blp_types", lambda: (None, query))
    monkeypatch.setattr(bbg, "_custom_api_parser", lambda: None)

    result = bbg.bdib(
        ["A", "B"],
        "2026-07-01 10:00",
        "2026-07-01 10:01",
        session=session,
    )

    assert max_active == 1
    assert [call.args[0] for call in connection.bdib.call_args_list] == ["A", "B"]
    assert query.call_args_list == [call(timeout=30000), call(timeout=30000)]
    assert connection.start.call_count == 2
    session.start.assert_not_called()
    session.stop.assert_not_called()
    assert list(result["security"]) == ["A", "B"]


def _grid_response(columns, rows, event="RESPONSE"):
    """Match blp's serialized ExcelGetGrid sequence and choice containers."""
    return {
        "eventTypeName": f"blpapi.Event.{event}",
        "message": {
            "element": {
                "ExcelGetGridResponse": {
                    "ColumnTitles": columns,
                    "DataRecords": [
                        {"DataRecords": {"DataFields": [{"DataFields": {"value": value}} for value in row]}}
                        for row in rows
                    ],
                }
            }
        },
    }


@pytest.mark.parametrize("supplied_session", [False, True], ids=["owned-session", "caller-session"])
@pytest.mark.parametrize("failure", [None, "query", "response"], ids=["success", "query-failure", "response-failure"])
def test_bsrch_request_and_session_ownership(monkeypatch, supplied_session, failure):
    session = Mock() if supplied_session else None
    connection = Mock()
    original_services = {"HistoricalDataRequest": "//blp/refdata"}
    connection._SERVICES = original_services
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    query = Mock(return_value=connection)
    monkeypatch.setattr(bbg, "_blp_types", lambda: (None, query))
    responses = [
        _grid_response(["Ticker", "Value"], [["A", 12.5]], "PARTIAL_RESPONSE"),
        _grid_response(["Ticker", "Value"], [["B", None]]),
    ]
    if failure == "response":
        responses[-1]["message"]["element"] = {"ExcelGetGridResponse": {"responseError": "Not entitled"}}

    def fetch(request, *, parse, collector):
        assert parse is False
        if failure == "query":
            raise ConnectionError("Unexpected blpapi.Event.TIMEOUT")
        return collector(iter(responses))

    connection.query.side_effect = fetch
    if failure:
        with pytest.raises((ConnectionError, RuntimeError), match="TIMEOUT|Not entitled"):
            bbg.bsrch("IPD:DEX", "saved-search-key", session=session)
    else:
        result = bbg.bsrch("IPD:DEX", "saved-search-key", session=session)
        pd.testing.assert_frame_equal(result, pd.DataFrame({"Ticker": ["A", "B"], "Value": [12.5, np.nan]}))
    query.assert_called_once_with(timeout=30000)
    assert connection._SERVICES == {"ExcelGetGridRequest": "//blp/exrsvc"}
    assert original_services == {"HistoricalDataRequest": "//blp/refdata"}
    connection.query.assert_called_once_with(
        {
            "ExcelGetGridRequest": {
                "Domain": "IPD:DEX",
                "Overrides": [
                    {"Overrides": {"name": "BIKEY", "value": "saved-search-key"}},
                ],
            }
        },
        parse=False,
        collector=bbg._normalise_bsrch,
    )
    if supplied_session:
        assert connection.session is session
        assert connection._started is True
        connection.start.assert_called_once_with()
        session.start.assert_not_called()
        session.stop.assert_not_called()
        connection.stop.assert_not_called()
        connection.__enter__.assert_not_called()
        connection.__exit__.assert_not_called()
    else:
        connection.__enter__.assert_called_once()
        connection.__exit__.assert_called_once()


def test_bsrch_grid_types_empty_results_and_partial_headers():
    date = pd.Timestamp("2026-10-13")
    columns = ["Name", "Number", "Date", "Flag", "Missing"]
    first = _grid_response(columns, [["Asset", 1.25, date, True, None]], "PARTIAL_RESPONSE")
    second = _grid_response(None, [["Next", -2.0, date, False, None]])
    # CHOICE elements may be serialized directly under their element name.
    second["message"]["element"]["ExcelGetGridResponse"]["DataRecords"][0]["DataRecords"]["DataFields"][0] = {
        "DataFields": "Next",
    }
    actual = bbg._normalise_bsrch([first, second])
    expected = pd.DataFrame([["Asset", 1.25, date, True, None], ["Next", -2.0, date, False, None]], columns=columns)
    pd.testing.assert_frame_equal(actual, expected)
    empty = bbg._normalise_bsrch([_grid_response(columns, [])])
    assert empty.empty and empty.columns.tolist() == columns


@pytest.mark.parametrize(
    "responses, error",
    [
        ([], "No data"),
        ([_grid_response([], [])], "no ColumnTitles"),
        ([_grid_response(["A", "B"], [[1]])], "row length"),
        ([_grid_response(["A"], [[1]], "PARTIAL_RESPONSE"), _grid_response(["B"], [[2]])], "titles changed"),
        ([_grid_response(["A"], [[1]], "REQUEST_STATUS")], "request failed"),
    ],
)
def test_bsrch_rejects_failed_or_inconsistent_responses(responses, error):
    with pytest.raises((RuntimeError, ValueError), match=error):
        bbg._normalise_bsrch(responses)


@pytest.mark.parametrize("dataset,bikey", [("", "key"), ("IPD:DEX", None), ("IPD:DEX", " ")])
def test_bsrch_validates_search_before_loading_bloomberg(monkeypatch, dataset, bikey):
    loader = Mock(side_effect=AssertionError("Runtime should not be imported"))
    monkeypatch.setattr(bbg, "_blp_types", loader)
    with pytest.raises(ValueError, match="nonempty"):
        bbg.bsrch(dataset, bikey)
    loader.assert_not_called()
