import sys
from queue import Empty, Queue
from types import ModuleType
from unittest.mock import MagicMock, Mock, call

import numpy as np
import pandas as pd
import pytest
from runbook.core.bloomberg import bbg


def _native_session(monkeypatch):
    api = ModuleType("blpapi")
    api.Event = type("Event", (), {"SUBSCRIPTION_STATUS": 1, "SUBSCRIPTION_DATA": 2, "TIMEOUT": 3})
    api.CorrelationId = lambda value: Mock(value=Mock(return_value=value))
    subscription_list = Mock()
    api.SubscriptionList = Mock(return_value=subscription_list)
    monkeypatch.setitem(sys.modules, "blpapi", api)
    module = ModuleType("blp.blp")
    module.message_to_dict = lambda message: {"element": message.toPy(), "timeReceived": "timestamp"}
    monkeypatch.setitem(sys.modules, "blp.blp", module)
    session = Mock()
    session.openService.return_value = True

    def event(kind, name=None, data=None, ticker_index=0):
        result = MagicMock()
        result.eventType.return_value = kind
        messages = []
        if name:
            cid = subscription_list.add.call_args_list[ticker_index].kwargs["correlationId"]
            message = Mock()
            message.messageType.return_value = name
            message.correlationIds.return_value = [cid]
            message.toPy.return_value = data or {}
            messages.append(message)
        result.__iter__.side_effect = lambda: iter(messages)
        return result

    return api, session, subscription_list, event


def test_bsubscribe_borrowed_session_preserves_updates_and_ownership(monkeypatch):
    api, session, subscriptions, event = _native_session(monkeypatch)
    calls = iter(["idle", "data", "started"])

    def next_event(timeout):
        assert timeout > 0
        kind = next(calls)
        if kind == "idle":
            return event(api.Event.TIMEOUT)
        if kind == "data":
            return event(api.Event.SUBSCRIPTION_DATA, "MarketDataEvents", {"BID": 10})
        return event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted")

    session.nextEvent.side_effect = next_event
    with bbg.bsubscribe("A", "BID", session=session) as feed:
        session.tryNextEvent.side_effect = [
            event(api.Event.SUBSCRIPTION_DATA, "MarketDataEvents", {"BID": 11}),
            None,
            None,
        ]
        assert feed.poll(1) == [{"element": {"BID": 10}, "timeReceived": "timestamp", "correlationIds": ["A"]}]
        assert feed.poll() == [{"element": {"BID": 11}, "timeReceived": "timestamp", "correlationIds": ["A"]}]
        assert feed.poll() == []
    session.start.assert_not_called()
    session.stop.assert_not_called()
    session.subscribe.assert_called_once_with(subscriptions)
    session.unsubscribe.assert_called_once_with(subscriptions)
    session.openService.assert_called_once_with("//blp/mktdata")
    with pytest.raises(RuntimeError, match="closed"):
        feed.poll()


@pytest.mark.parametrize("failure", ["service", "async", "timeout", "field", "security", "consumer"])
def test_bsubscribe_borrowed_session_failures_keep_session_alive(monkeypatch, failure):
    api, session, subscriptions, event = _native_session(monkeypatch)
    session.openService.return_value = failure != "service"

    def next_event(timeout):
        if failure == "async":
            raise RuntimeError("asynchronous session")
        if session.nextEvent.call_count == 1 or failure == "timeout":
            return event(api.Event.TIMEOUT)
        return event(
            api.Event.SUBSCRIPTION_STATUS,
            "SubscriptionFailure" if failure == "security" else "SubscriptionStarted",
            {"exceptions": [{"fieldId": "BID"}]} if failure == "field" else {},
        )

    session.nextEvent.side_effect = next_event
    with pytest.raises((RuntimeError, ConnectionError, TimeoutError)):
        with bbg.bsubscribe("A", "BID", session=session):
            if failure == "consumer":
                raise RuntimeError("consumer failed")
            pytest.fail("Startup should fail")
    session.start.assert_not_called()
    session.stop.assert_not_called()
    if failure in {"service", "async"}:
        session.subscribe.assert_not_called()
        session.unsubscribe.assert_not_called()
    else:
        session.unsubscribe.assert_called_once_with(subscriptions)


def test_bsubscribe_borrowed_session_keeps_remainder_of_native_event(monkeypatch):
    api, session, _, event = _native_session(monkeypatch)
    session.nextEvent.side_effect = lambda _: (
        event(api.Event.TIMEOUT)
        if session.nextEvent.call_count == 1
        else event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted")
    )
    with bbg.bsubscribe("A", "BID", session=session) as feed:
        combined = event(api.Event.SUBSCRIPTION_DATA)
        messages = [
            *event(api.Event.SUBSCRIPTION_DATA, "MarketDataEvents", {"BID": 10}),
            *event(api.Event.SUBSCRIPTION_DATA, "MarketDataEvents", {"BID": 11}),
        ]
        combined.__iter__.side_effect = lambda: iter(messages)
        session.tryNextEvent.side_effect = [combined, None]
        assert feed.poll(1)[0]["element"] == {"BID": 10}
        assert feed.poll(1)[0]["element"] == {"BID": 11}
        assert feed.poll() == []


@pytest.mark.parametrize("name", ["SubscriptionTerminated", "SessionConnectionDown"])
def test_bsubscribe_borrowed_session_runtime_failure(monkeypatch, name):
    api, session, subscriptions, event = _native_session(monkeypatch)
    session.nextEvent.side_effect = lambda _: (
        event(api.Event.TIMEOUT)
        if session.nextEvent.call_count == 1
        else event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted")
    )
    error = ConnectionError if name == "SessionConnectionDown" else RuntimeError
    with pytest.raises(error):
        with bbg.bsubscribe("A", "BID", session=session) as feed:
            session.tryNextEvent.return_value = event(api.Event.SUBSCRIPTION_STATUS, name)
            feed.poll()
    session.unsubscribe.assert_called_once_with(subscriptions)
    session.stop.assert_not_called()


def _polling_stream(monkeypatch, status):
    stream = Mock()
    stream.subscribe.return_value = status
    queue = Queue()

    def events(*, timeout):
        while True:
            yield queue.get(timeout=timeout)

    stream.events.side_effect = events
    context = MagicMock()
    context.__enter__.return_value = stream
    context.__exit__.return_value = False
    factory = Mock(return_value=context)
    monkeypatch.setattr(bbg, "bstream", factory)
    return stream, queue, context, factory


def test_market_bars_owned_session_request_and_markers(monkeypatch):
    topic = "//blp/mktbar/ticker/IBM US Equity"
    stream, queue, context, factory = _polling_stream(monkeypatch, {topic: True})
    options = {"start_time": "13:30", "end_time": "20:00"}
    kinds = ["MarketBarStart", "MarketBarUpdate", "MarketBarIntervalEnd", "MarketBarEnd"]
    with bbg.bsubscribe("IBM US Equity", "LAST_PRICE", bar_size=5, options=options) as feed:
        for kind in kinds:
            queue.put({"messageType": kind, "correlationIds": [topic], "element": {kind: {"DATE_TIME": "time"}}})
        updates = feed.poll()
        assert [item["messageType"] for item in updates] == kinds
        assert all(item["correlationIds"] == ["IBM US Equity"] for item in updates)
        assert feed.poll() == []
    factory.assert_called_once_with(host="localhost", port=8194, service="//blp/mktbar")
    stream.subscribe.assert_called_once_with(
        {topic: {"fields": ["LAST_PRICE"], "options": {**options, "bar_size": 5}}}, timeout=5
    )
    assert "bar_size" not in options
    context.__exit__.assert_called_once()


def test_market_bars_borrowed_session_payload_and_cleanup(monkeypatch):
    api, session, subscriptions, event = _native_session(monkeypatch)
    session.nextEvent.side_effect = lambda _: (
        event(api.Event.TIMEOUT)
        if session.nextEvent.call_count == 1
        else event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted")
    )
    payloads = [
        ("MarketBarStart", {"OPEN": 10, "HIGH": 10, "LOW": 10, "CLOSE": 10, "DATE_TIME": "time"}),
        ("MarketBarUpdate", {"HIGH": 11, "CLOSE": 11, "DATE_TIME": "time"}),
        ("MarketBarIntervalEnd", {"DATE_TIME": "time"}),
        ("MarketBarEnd", {"DATE_TIME": "time"}),
    ]
    with bbg.bsubscribe("IBM US Equity", "LAST_PRICE", bar_size=5, session=session) as feed:
        session.tryNextEvent.side_effect = [
            *(event(api.Event.SUBSCRIPTION_DATA, kind, {kind: data}) for kind, data in payloads),
            None,
        ]
        updates = feed.poll()
        assert [item["element"] for item in updates] == [{kind: data} for kind, data in payloads]
        assert all(item["correlationIds"] == ["IBM US Equity"] for item in updates)
    session.openService.assert_called_once_with("//blp/mktbar")
    assert subscriptions.add.call_args.args == ("//blp/mktbar/ticker/IBM US Equity",)
    assert subscriptions.add.call_args.kwargs["options"] == {"bar_size": 5}
    session.unsubscribe.assert_called_once_with(subscriptions)
    session.start.assert_not_called()
    session.stop.assert_not_called()


@pytest.mark.parametrize(
    "size,field,options",
    [
        (0, "LAST_PRICE", None),
        (1441, "LAST_PRICE", None),
        (True, "LAST_PRICE", None),
        (1.5, "LAST_PRICE", None),
        (5, "BID", None),
        (5, ["LAST_PRICE", "ASK"], None),
        (5, "LAST_PRICE", {"interval": 1}),
        (None, "LAST_PRICE", {"bar_size": 5}),
    ],
)
def test_market_bars_validate_before_connection(monkeypatch, size, field, options):
    factory = Mock()
    monkeypatch.setattr(bbg, "bstream", factory)
    with pytest.raises(ValueError):
        with bbg.bsubscribe("IBM US Equity", field, bar_size=size, options=options):
            pytest.fail("Invalid bar configuration must not connect")
    factory.assert_not_called()


def test_bstream_bar_handler_retains_end_markers(monkeypatch):
    stream = MagicMock()
    stream.__enter__.return_value = stream
    stream.__exit__.return_value = False
    stream.event_handler.data_queue = Queue()
    module = ModuleType("blp.blp")
    module.BlpStream = Mock(return_value=stream)
    module.message_to_dict = lambda msg: {"messageType": msg}
    monkeypatch.setitem(sys.modules, "blp.blp", module)
    with bbg.bstream(service="//blp/mktbar") as live:
        live.event_handler.marketdata_event(
            ["MarketBarStart", "MarketBarUpdate", "MarketBarIntervalEnd", "MarketBarEnd"]
        )
        assert [live.event_handler.data_queue.get_nowait()["messageType"] for _ in range(4)] == [
            "MarketBarStart",
            "MarketBarUpdate",
            "MarketBarIntervalEnd",
            "MarketBarEnd",
        ]
    stream.session.openService.assert_called_once_with("//blp/mktbar")
    stream.__exit__.assert_called_once()


def test_bsubscribe_polls_repeatedly_without_reopening_or_waiting(monkeypatch):
    stream, queue, context, factory = _polling_stream(monkeypatch, {"A": True, "B": True})
    first = {"correlationIds": ["A"], "element": {"MarketDataEvents": {"BID": 10}}}
    second = {"correlationIds": ["B"], "element": {"MarketDataEvents": {"ASK": None}}}
    with bbg.bsubscribe(["A", "B"], ["BID", "ASK"], options={"interval": 1}, host="host", port=8196) as feed:
        assert feed.poll() == []
        queue.put(first)
        queue.put(second)
        assert feed.poll(max_events=1) == [first]
        assert feed.poll() == [second]
        assert feed.poll() == []
        queue.put(first)
        assert feed.poll() == [first]
        factory.assert_called_once_with(host="host", port=8196)
        stream.subscribe.assert_called_once_with(
            {
                "A": {"fields": ["BID", "ASK"], "options": {"interval": 1}},
                "B": {"fields": ["BID", "ASK"], "options": {"interval": 1}},
            },
            timeout=5,
        )
        assert all(args == call(timeout=0) for args in stream.events.call_args_list)
    context.__exit__.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        feed.poll()


@pytest.mark.parametrize("status", [{"A": False}, {"A": ["BAD_FIELD"]}, {}])
def test_bsubscribe_rejects_failed_or_missing_status_and_closes(monkeypatch, status):
    stream, _, context, _ = _polling_stream(monkeypatch, status)
    with pytest.raises(RuntimeError, match="subscriptions rejected"):
        with bbg.bsubscribe("A", "BID"):
            pytest.fail("Rejected subscriptions must not reach polling")
    stream.subscribe.assert_called_once_with({"A": {"fields": ["BID"], "options": None}}, timeout=5)
    context.__exit__.assert_called_once()


def test_bsubscribe_ack_timeout_closes_session(monkeypatch):
    stream, _, context, _ = _polling_stream(monkeypatch, {})
    stream.subscribe.side_effect = Empty
    with pytest.raises(TimeoutError, match="acknowledgements"):
        with bbg.bsubscribe("A", "BID", timeout=2):
            pytest.fail("Unacknowledged subscriptions must not reach polling")
    context.__exit__.assert_called_once()


def test_bsubscribe_poll_error_propagates_and_closes(monkeypatch):
    stream, _, context, _ = _polling_stream(monkeypatch, {"A": True})
    stream.events.side_effect = RuntimeError("stream failed")
    with pytest.raises(RuntimeError, match="stream failed"):
        with bbg.bsubscribe("A", "BID") as feed:
            feed.poll()
    context.__exit__.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        feed.poll()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_bsubscribe_rejects_invalid_poll_limit(monkeypatch, limit):
    stream, _, _, _ = _polling_stream(monkeypatch, {"A": True})
    with bbg.bsubscribe("A", "BID") as feed:
        with pytest.raises(ValueError, match="positive integer"):
            feed.poll(limit)
    stream.events.assert_not_called()


@pytest.mark.parametrize(
    "ticker,field,timeout",
    [("", "BID", 5), ([], "BID", 5), (["A", " "], "BID", 5), ("A", [], 5), ("A", "BID", 0), ("A", "BID", float("inf"))],
)
def test_bsubscribe_validates_before_opening_session(monkeypatch, ticker, field, timeout):
    factory = Mock()
    monkeypatch.setattr(bbg, "bstream", factory)
    with pytest.raises(ValueError):
        with bbg.bsubscribe(ticker, field, timeout=timeout):
            pytest.fail("Invalid input must not start a subscription")
    factory.assert_not_called()


@pytest.mark.parametrize("field", [" BID ", "BID,ASK", "BID&interval=1", "BID?ASK", ["BID", "ASK\n"]])
def test_bsubscribe_rejects_malformed_fields_before_connection(monkeypatch, field):
    factory = Mock()
    monkeypatch.setattr(bbg, "bstream", factory)
    with pytest.raises(ValueError, match="one field name per string"):
        with bbg.bsubscribe("A", field):
            pytest.fail("Malformed fields must not start a subscription")
    factory.assert_not_called()


@pytest.mark.parametrize("borrowed", [False, True])
def test_bsubscribe_allows_fields_outside_enum(monkeypatch, borrowed):
    fields = ["OPEN", "HIGH", "LOW", "VOLUME", "BEST_BID", "BEST_ASK", "NEW_VENDOR_FIELD"]
    if borrowed:
        api, session, subscriptions, event = _native_session(monkeypatch)
        session.nextEvent.side_effect = lambda _: (
            event(api.Event.TIMEOUT)
            if session.nextEvent.call_count == 1
            else event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted")
        )
    else:
        stream, _, _, _ = _polling_stream(monkeypatch, {"A": True})
        session = None
    with bbg.bsubscribe("A", fields, session=session):
        pass
    if borrowed:
        assert subscriptions.add.call_args.kwargs["fields"] == fields
    else:
        stream.subscribe.assert_called_once_with({"A": {"fields": fields, "options": None}}, timeout=5)


def test_bsubscribe_vendor_rejects_unknown_field(monkeypatch):
    _, _, context, _ = _polling_stream(monkeypatch, {"A": ["UNKNOWN_FIELD"]})
    with pytest.raises(RuntimeError, match="UNKNOWN_FIELD"):
        with bbg.bsubscribe("A", "UNKNOWN_FIELD"):
            pytest.fail("Vendor-rejected fields must fail startup")
    context.__exit__.assert_called_once()


@pytest.mark.parametrize("field", [None, 42, {"BID": True}, [None], [[]]])
def test_bsubscribe_rejects_invalid_field_types(monkeypatch, field):
    factory = Mock()
    monkeypatch.setattr(bbg, "bstream", factory)
    with pytest.raises(ValueError, match="field must contain nonempty strings"):
        with bbg.bsubscribe("A", field):
            pytest.fail("Invalid fields must not start a subscription")
    factory.assert_not_called()


def test_bsubscribe_accepts_supported_enum_fields_and_deduplicates(monkeypatch):
    stream, _, _, _ = _polling_stream(monkeypatch, {"A": True})
    fields = [*bbg.BloombergSubscriptionField, "BID"]
    with bbg.bsubscribe("A", fields):
        pass
    stream.subscribe.assert_called_once_with(
        {"A": {"fields": ["BID", "ASK", "LAST_PRICE"], "options": None}}, timeout=5
    )


@pytest.mark.parametrize("failure", [None, "service", "subscribe", "consumer"])
def test_bstream_live_session_and_cleanup(monkeypatch, failure):
    stream = MagicMock()
    stream.__enter__.return_value = stream
    stream.__exit__.return_value = False
    stream.session.openService.return_value = failure != "service"
    if failure == "subscribe":
        stream.subscribe.side_effect = RuntimeError("subscription failed")
    update = {
        "correlationIds": ["EURUSD Curncy"],
        "element": {"MarketDataEvents": {"BID": 1.1}},
    }
    stream.events.return_value = iter([update])
    factory = Mock(return_value=stream)
    module = ModuleType("blp.blp")
    module.BlpStream = factory
    monkeypatch.setitem(sys.modules, "blp.blp", module)

    def consume():
        context = bbg.bstream(host="bloomberg-host", port=8196)
        factory.assert_not_called()
        with context as live:
            assert live is stream
            live.subscribe({"EURUSD Curncy": {"fields": ["BID", "ASK"]}})
            for event in live.events(timeout=5):
                assert event is update
                if failure == "consumer":
                    raise RuntimeError("consumer failed")
                break

    if failure:
        with pytest.raises((ConnectionError, RuntimeError), match="Failed to open|subscription failed|consumer failed"):
            consume()
    else:
        consume()
        stream.events.assert_called_once_with(timeout=5)
    factory.assert_called_once_with(host="bloomberg-host", port=8196)
    stream.session.openService.assert_called_once_with("//blp/mktdata")
    stream.__exit__.assert_called_once()
    if failure == "service":
        stream.subscribe.assert_not_called()


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


def test_receive_owned_waits_once_and_preserves_remainder(monkeypatch):
    stream, queue, _, _ = _polling_stream(monkeypatch, {"A": True})
    with bbg.bsubscribe("A", "BID") as feed:
        queue.put({"correlationIds": ["A"], "element": {"BID": 10}})
        queue.put({"correlationIds": ["A"], "element": {"BID": 11}})
        assert feed.receive(max_events=1)[0]["element"] == {"BID": 10}
        assert feed.receive()[0]["element"] == {"BID": 11}
        assert stream.events.call_args_list == [call(timeout=1.0), call(timeout=0), call(timeout=1.0), call(timeout=0)]
        assert feed.receive(timeout=0.001) == []
    with pytest.raises(RuntimeError, match="closed"):
        feed.receive()


def test_receive_owned_wakes_on_delayed_data(monkeypatch):
    from threading import Event, Thread

    stream, queue, _, _ = _polling_stream(monkeypatch, {"A": True})
    waiting = Event()
    original = stream.events.side_effect

    def events(*, timeout):
        waiting.set()
        yield from original(timeout=timeout)

    stream.events.side_effect = events
    update = {"correlationIds": ["A"], "element": {"BID": 12}}
    producer = Thread(target=lambda: (waiting.wait(2), queue.put(update)))
    with bbg.bsubscribe("A", "BID") as feed:
        producer.start()
        try:
            assert feed.receive(timeout=2) == [update]
        finally:
            producer.join(3)


@pytest.mark.parametrize("timeout", [-1, True, None, "1", float("nan"), float("inf")])
def test_receive_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="timeout"):
        bbg.BloombergSubscription(Mock()).receive(timeout=timeout)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_receive_invalid_limit(limit):
    with pytest.raises(ValueError, match="max_events"):
        bbg.BloombergSubscription(Mock()).receive(max_events=limit)


def test_receive_borrowed_deadline_status_and_batch(monkeypatch):
    api, session, _, event = _native_session(monkeypatch)
    stream = bbg._SessionStream(session, {"A": {"fields": ["BID"]}})
    feed = bbg.BloombergSubscription(stream)
    monkeypatch.setattr(bbg, "monotonic", Mock(side_effect=[10, 10.1, 10.4, 11]))
    combined = event(api.Event.SUBSCRIPTION_DATA)
    combined.__iter__.side_effect = lambda: iter(
        [
            *event(api.Event.SUBSCRIPTION_DATA, "MarketDataEvents", {"BID": 10}),
            *event(api.Event.SUBSCRIPTION_DATA, "MarketDataEvents", {"BID": 11}),
        ]
    )
    session.nextEvent.side_effect = [event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted"), combined]
    session.tryNextEvent.return_value = None
    assert feed.receive(timeout=1, max_events=1)[0]["element"] == {"BID": 10}
    waits = [c.args[0] for c in session.nextEvent.call_args_list]
    assert 0 < waits[1] < waits[0] <= 1000
    assert feed.receive(timeout=0)[0]["element"] == {"BID": 11}
    assert session.nextEvent.call_count == 2


@pytest.mark.parametrize(
    "failure", ["SubscriptionFailure", "SubscriptionTerminated", "SessionConnectionDown", "SessionTerminated"]
)
def test_receive_borrowed_failure(monkeypatch, failure):
    api, session, _, event = _native_session(monkeypatch)
    stream = bbg._SessionStream(session, {"A": {"fields": ["BID"]}})
    session.nextEvent.return_value = event(api.Event.SUBSCRIPTION_STATUS, failure)
    with pytest.raises((RuntimeError, ConnectionError)):
        bbg.BloombergSubscription(stream).receive()


def test_receive_borrowed_timeout(monkeypatch):
    api, session, _, event = _native_session(monkeypatch)
    stream = bbg._SessionStream(session, {"A": {"fields": ["BID"]}})
    session.nextEvent.return_value = event(api.Event.TIMEOUT)
    assert bbg.BloombergSubscription(stream).receive(timeout=0.01) == []
    session.nextEvent.assert_called_once()


@pytest.mark.parametrize(
    "failure", ["SubscriptionFailure", "SubscriptionTerminated", "SessionConnectionDown", "SessionTerminated"]
)
def test_receive_owned_status_failure_wakes_consumer(failure):
    handler = Mock()
    handler.data_queue = Queue()
    bbg._forward_stream_failures(handler)
    message = Mock()
    message.messageType.return_value = failure
    callback = handler.session_status_event if failure.startswith("Session") else handler.subscription_status_event
    callback([message])

    def events(timeout):
        yield handler.data_queue.get(timeout=timeout)

    feed = bbg.BloombergSubscription(Mock(events=events))
    for _ in range(2):
        with pytest.raises((RuntimeError, ConnectionError)):
            feed.receive()


def test_receive_borrowed_status_only_respects_overall_deadline(monkeypatch):
    api, session, _, event = _native_session(monkeypatch)
    stream = bbg._SessionStream(session, {"A": {"fields": ["BID"]}})
    monkeypatch.setattr(bbg, "monotonic", Mock(side_effect=[10, 10.2, 10.7, 11.1]))
    session.nextEvent.side_effect = lambda _: event(api.Event.SUBSCRIPTION_STATUS, "SubscriptionStarted")
    assert bbg.BloombergSubscription(stream).receive(timeout=1) == []
    waits = [c.args[0] for c in session.nextEvent.call_args_list]
    assert len(waits) == 2
    assert 0 < waits[1] < waits[0] <= 1000
