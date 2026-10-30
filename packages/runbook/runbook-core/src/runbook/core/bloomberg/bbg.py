import datetime as dt
import typing as tp
from collections import deque
from concurrent.futures import ThreadPoolExecutor as tp_exec
from contextlib import contextmanager
from enum import Enum, StrEnum
from queue import Empty
from time import monotonic
from uuid import uuid4

import numpy as np
import pandas as pd
from loguru import logger as log
from pandas.tseries.offsets import BDay


class BBGReturnTypes(Enum):
    BDH = 0
    BDIB = 1
    BREF = 2
    BBLKREF = 3
    BSRCH = 4
    BQL = 5


def _blp_types():
    """Import Bloomberg's optional runtime only when a live query runs."""
    from blp.blp import BlpParser, BlpQuery

    return BlpParser, BlpQuery


def _queue_market_bar_events(handler, event):
    """Preserve interval/end markers omitted by blp's default event filter."""
    from blp.blp import message_to_dict

    for message in event:
        handler.data_queue.put(message_to_dict(message))


def _forward_stream_failures(handler):
    """Wake queue consumers when blp would otherwise only log a failure."""

    def wrap(original):
        def handle(event):
            for message in event:
                kind = str(message.messageType())
                error = None
                if kind in {"SessionTerminated", "SessionConnectionDown", "SessionStartupFailure"}:
                    error = ConnectionError(f"Bloomberg session unavailable: {message}")
                elif kind in {"SubscriptionFailure", "SubscriptionTerminated"} or (
                    kind == "SubscriptionStarted" and message.toPy().get("exceptions")
                ):
                    error = RuntimeError(f"Bloomberg subscriptions rejected: {message}")
                if error is not None:
                    handler.data_queue.put(error)
            original(event)

        return handle

    handler.session_status_event = wrap(handler.session_status_event)
    handler.subscription_status_event = wrap(handler.subscription_status_event)


@contextmanager
def bstream(host: str = "localhost", port: int = 8194, *, service: str = "//blp/mktdata"):
    """Open a dedicated live market-data session, closed on context exit.

    Yields ``blp.BlpStream`` with ``subscribe``, ``resubscribe``,
    ``unsubscribe`` and ``events`` methods. Subscription dictionaries map
    tickers to ``fields`` and optional ``options``; ticker strings are the
    default correlation IDs. Check subscription results: True means success,
    False means failure, and a list identifies rejected fields.

    ``events(timeout=...)`` yields raw message dictionaries containing
    ``correlationIds``, ``element`` and ``timeReceived``. Updates contain only
    changed fields, not complete snapshots. Timeouts are in seconds and raise
    ``queue.Empty``. Session/status diagnostics are logged by blp.

    Use inside a ``with`` block, including when breaking out of the event loop.
    This owns a separate session from the historical/reference query helpers.
    Bloomberg's optional runtime is loaded only on context entry.
    ``service="//blp/mktbar"`` opens streaming bars and retains all bar events.
    """
    from blp.blp import BlpStream

    if service not in {"//blp/mktdata", "//blp/mktbar"}:
        raise ValueError("service must be //blp/mktdata or //blp/mktbar")
    connection = BlpStream(host=host, port=port)
    if service == "//blp/mktbar":
        connection.event_handler.marketdata_event = lambda event: _queue_market_bar_events(
            connection.event_handler, event
        )
    with connection as stream:
        if not stream.session.openService(service):
            raise ConnectionError(f"Failed to open Bloomberg {service}")
        yield stream


class BloombergSubscriptionField(StrEnum):
    """Convenience names for common live quote fields.

    Other Bloomberg field names are accepted as strings by bsubscribe.
    """

    BID = "BID"
    ASK = "ASK"
    LAST_PRICE = "LAST_PRICE"


class BloombergSubscription:
    """A single-consumer live feed created by :func:`bsubscribe`."""

    def __init__(self, stream, tickers_by_topic=None):
        self._stream = stream
        self._closed = False
        self._failure = None
        self._tickers_by_topic = tickers_by_topic or {}

    def poll(self, max_events: int = 1000) -> list[dict]:
        """Drain at most ``max_events`` queued updates without waiting.

        Returns raw Bloomberg message dictionaries in arrival order, or []
        when idle. Messages are incremental updates, not quote snapshots.
        Call again on the next service cycle; do not poll concurrently.
        An empty batch is not a connection-health indication.
        """
        return self._collect(max_events, timeout=0)

    def receive(self, *, timeout: float = 1.0, max_events: int = 1000) -> list[dict]:
        """Wait for the first update, then drain queued updates without waiting.

        Timeout is one overall idle-wait limit in seconds, not a delivery delay.
        Zero is nonblocking. Returns [] on timeout, not a health indication.
        Failures propagate. Like poll(), this is a single-consumer API.
        """
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not np.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("timeout must be a nonnegative finite number of seconds")
        return self._collect(max_events, timeout=timeout)

    def _collect(self, max_events, *, timeout):
        if self._closed:
            raise RuntimeError("Bloomberg subscription is closed")
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
            raise ValueError("max_events must be a positive integer")
        if self._failure is not None:
            raise self._failure
        updates = []
        # queue.Empty closes blp's generator; each poll needs a fresh one.
        events = self._stream.events(timeout=timeout)
        try:
            for _ in range(max_events):
                update = next(events)
                if isinstance(update, Exception):
                    self._failure = update
                    raise update
                if not updates and timeout > 0:
                    events.close()
                    events = self._stream.events(timeout=0)
                if self._tickers_by_topic:
                    update = dict(update)
                    update["correlationIds"] = [
                        self._tickers_by_topic.get(cid, cid) for cid in update["correlationIds"]
                    ]
                updates.append(update)
        except (Empty, StopIteration):
            pass
        finally:
            events.close()
        return updates


class _SessionStream:
    """Adapt an exclusively borrowed synchronous session to the polling feed."""

    def __init__(self, session, subscriptions):
        import blpapi
        from blp.blp import message_to_dict

        self.session = session
        self._blpapi = blpapi
        self._serialize = message_to_dict
        self._pending = deque()
        self._started = set()
        self._topics = {}
        self.subscriptions = blpapi.SubscriptionList()
        for ticker, config in subscriptions.items():
            correlation = uuid4().hex
            self._topics[correlation] = ticker
            self.subscriptions.add(ticker, correlationId=blpapi.CorrelationId(correlation), **config)

    def _receive(self, event):
        for message in event:
            kind = str(message.messageType())
            if kind in {"SessionTerminated", "SessionConnectionDown"}:
                raise ConnectionError(f"Bloomberg session unavailable: {message}")
            correlations = [cid.value() for cid in message.correlationIds() if cid.value() in self._topics]
            if not correlations:
                continue
            if event.eventType() == self._blpapi.Event.SUBSCRIPTION_STATUS:
                data = message.toPy()
                if kind in {"SubscriptionFailure", "SubscriptionTerminated"} or data.get("exceptions"):
                    raise RuntimeError(f"Bloomberg subscriptions rejected: {message}")
                if kind == "SubscriptionStarted":
                    self._started.update(correlations)
            elif event.eventType() == self._blpapi.Event.SUBSCRIPTION_DATA:
                update = self._serialize(message)
                update["correlationIds"] = [self._topics[cid] for cid in correlations]
                self._pending.append(update)

    def wait_started(self, timeout):
        deadline = monotonic() + timeout
        while len(self._started) < len(self._topics):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for Bloomberg subscription acknowledgements")
            # Zero means an infinite wait in blpapi, rather than a nonblocking poll.
            event = self.session.nextEvent(max(1, int(remaining * 1000)))
            if event.eventType() == self._blpapi.Event.TIMEOUT:
                raise TimeoutError("Timed out waiting for Bloomberg subscription acknowledgements")
            self._receive(event)

    def events(self, timeout=0):
        deadline = monotonic() + timeout if timeout > 0 else 0
        while timeout > 0 and not self._pending:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            event = self.session.nextEvent(max(1, int(remaining * 1000)))
            if event.eventType() == self._blpapi.Event.TIMEOUT:
                return
            self._receive(event)
        # Bound status-event processing too, so a busy session cannot monopolize a poll.
        for _ in range(1000):
            while self._pending:
                yield self._pending.popleft()
            event = self.session.tryNextEvent()
            if event is None:
                return
            self._receive(event)
        while self._pending:
            yield self._pending.popleft()


@contextmanager
def _session_subscription(session, subscriptions, timeout, service="//blp/mktdata", tickers_by_topic=None):
    stream = _SessionStream(session, subscriptions)
    if not session.openService(service):
        raise ConnectionError(f"Failed to open Bloomberg {service}")
    # Check synchronous mode before subscribing; nextEvent raises for an
    # asynchronous session. Process any queued session-status event too.
    stream._receive(session.nextEvent(1))
    feed = BloombergSubscription(stream, tickers_by_topic)
    try:
        session.subscribe(stream.subscriptions)
        stream.wait_started(timeout)
        yield feed
    finally:
        feed._closed = True
        session.unsubscribe(stream.subscriptions)


@contextmanager
def bsubscribe(
    ticker: list[str] | str,
    field: list[str] | str,
    *,
    options: dict | None = None,
    host: str = "localhost",
    port: int = 8194,
    timeout: float = 5,
    session: tp.Any = None,
    bar_size: int | None = None,
) -> tp.Iterator[BloombergSubscription]:
    """Subscribe once to tickers and yield a feed for polling or blocking receives.

    Keep the context open for the service lifetime and call ``feed.poll()``
    each cycle, or use ``feed.receive(timeout=1.0)`` to wake on incoming data.
    Entry waits up to ``timeout`` seconds per subscription status;
    rejected securities or fields raise RuntimeError, missing acknowledgements
    raise TimeoutError. Exit closes the owned bstream session and subscriptions.
    Polling itself never waits for new data. See ``bstream`` for the raw message
    format and the underlying library's status logging behaviour.

    ``field`` accepts Bloomberg field names or BloombergSubscriptionField
    members. The full mktdata field catalogue is allowed; Bloomberg validates
    availability for each ticker and entitlement at subscription startup.
    Pass one field per string, without whitespace or subscription delimiters.

    ``session`` may be a started synchronous blpapi.Session, exclusively lent
    to this feed while the context is open. No other consumer or outstanding
    request/subscription may share its event stream. Its authentication and
    lifecycle remain caller-owned; only this feed's subscriptions are cancelled
    on exit. Host/port are ignored, and timeout bounds total startup waiting.

    ``bar_size`` selects trade-based OHLC bars on //blp/mktbar (1–1440 minutes).
    Only LAST_PRICE may be requested in this mode. All four MarketBar event
    types are returned, including interval/end markers. Merge incremental
    updates by ticker and DATE_TIME; interval-end messages are not OHLC snapshots.
    """
    tickers = [ticker] if isinstance(ticker, str) else ticker
    fields = [field] if isinstance(field, str) else field
    for name, values in (("ticker", tickers), ("field", fields)):
        if (
            not isinstance(values, (list, tuple))
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise ValueError(f"{name} must contain nonempty strings")
    if any(any(char.isspace() or char in ",&=?" for char in value) for value in fields):
        raise ValueError("Pass one field name per string, without whitespace or subscription delimiters")
    fields = list(dict.fromkeys(str(value) for value in fields))
    service = "//blp/mktdata"
    tickers_by_topic = {}
    if bar_size is not None:
        if isinstance(bar_size, bool) or not isinstance(bar_size, int) or not 1 <= bar_size <= 1440:
            raise ValueError("bar_size must be an integer from 1 to 1440 minutes")
        if fields != ["LAST_PRICE"]:
            raise ValueError("Market bars require only LAST_PRICE")
        if options is not None and any(key not in {"start_time", "end_time"} for key in options):
            raise ValueError("Market bar options support only start_time and end_time; use bar_size for the interval")
        options = {**(options or {}), "bar_size": bar_size}
        service = "//blp/mktbar"
        if any("/" in name or "?" in name for name in tickers):
            raise ValueError("Market bars require plain Bloomberg tickers, not subscription topic strings")
        tickers_by_topic = {f"{service}/ticker/{name}": name for name in tickers}
        tickers = list(tickers_by_topic)
    elif options is not None and "bar_size" in options:
        raise ValueError("Use the bar_size argument to select market bars")
    if not isinstance(timeout, (int, float)) or not np.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number of seconds")
    subscriptions = {name: {"fields": list(fields), "options": options} for name in tickers}
    if session is not None:
        with _session_subscription(session, subscriptions, timeout, service, tickers_by_topic) as feed:
            yield feed
        return
    connection = (
        bstream(host=host, port=port, service=service) if bar_size is not None else bstream(host=host, port=port)
    )
    with connection as stream:
        _forward_stream_failures(stream.event_handler)
        try:
            status = stream.subscribe(subscriptions, timeout=timeout)
        except Empty as exc:
            raise TimeoutError("Timed out waiting for Bloomberg subscription acknowledgements") from exc
        rejected = {name: status.get(name) for name in subscriptions if status.get(name) is not True}
        if rejected:
            raise RuntimeError(f"Bloomberg subscriptions rejected: {rejected}")
        feed = BloombergSubscription(stream, tickers_by_topic)
        try:
            yield feed
        finally:
            feed._closed = True


def _log_api_errors_processor(response, request_data):
    """Validate Bloomberg responses but log security/field errors instead of raising."""
    BlpParser, _ = _blp_types()
    response = BlpParser._validate_event(response, request_data)
    response = BlpParser._validate_response_type(response, request_data)
    response = BlpParser._validate_response_error(response, request_data)

    rtype = next(iter(response["message"]["element"].keys()))
    response_data = response["message"]["element"][rtype]
    if rtype in (
        "IntradayBarResponse",
        "IntradayTickResponse",
        "BeqsResponse",
        "fieldResponse",
        "InstrumentListResponse",
        "GetFillsResponse",
    ):
        return response
    if rtype == "HistoricalDataResponse":
        response_data = [response_data]

    for sec_data in response_data:
        data = sec_data.get("securityData", {})
        security = data.get("security", "unknown")

        if "securityError" in data:
            log.error(f"Security error for {security}: {data['securityError']}")
            if rtype == "HistoricalDataResponse":
                data["fieldData"] = []
            else:
                field_data = data.setdefault("fieldData", {})
                if "fieldData" not in field_data:
                    field_data["fieldData"] = {}
            data["fieldExceptions"] = []
            continue

        if rtype == "HistoricalDataResponse":
            continue

        field_data = data.setdefault("fieldData", {})
        if "fieldData" not in field_data:
            field_data["fieldData"] = {}
        field_exceptions = data.get("fieldExceptions", [])
        for fe in field_exceptions:
            fe_data = fe.get("fieldExceptions", {})
            error_info = fe_data.get("errorInfo", {}).get("errorInfo", {})
            category = error_info.get("category")
            subcategory = error_info.get("subcategory")
            field = fe_data.get("fieldId")
            if field is not None:
                field_data["fieldData"].setdefault(field, None)
            if category == "BAD_FLD" and subcategory == "NOT_APPLICABLE_TO_REF_DATA":
                log.debug(f"Field {field!r} not applicable for {security}")
            else:
                log.warning(f"Field exception for {security}: {fe_data}")
        data["fieldExceptions"] = []
    return response


def _custom_api_parser() -> tp.Any:
    """Create a Bloomberg parser that preserves partial security results."""
    BlpParser, _ = _blp_types()
    return BlpParser(processor_steps=[_log_api_errors_processor])


@contextmanager
def _blp_connection(BlpQuery, *, timeout: int, parser, session, services=None):
    """Yield a query connection, reusing a caller-owned started session when supplied."""
    if parser is None:
        conn = BlpQuery(timeout=timeout)
    else:
        conn = BlpQuery(timeout=timeout, parser=parser)
    if services is not None:
        # Override only this connection; do not change BlpQuery's global map.
        conn._SERVICES = services
    if session is None:
        with conn as started_conn:
            yield started_conn
        return

    # blp.BlpQuery 0.0.4 always creates its own session and its context manager
    # always stops it. Replacing that session lets the caller own its lifecycle.
    conn.session = session
    conn._started = True
    conn.start()
    yield conn


def _to_yyyymmdd(value: dt.datetime | str) -> str:
    """Convert a date-like value to Bloomberg's compact YYYYMMDD form."""
    ts = pd.to_datetime(value)
    return ts.strftime("%Y%m%d")


def _normalise_bdh(data, ticker, fields):
    """
    1 ticker 1 field => column = Field
    1 ticker many fields => columns = Fields
    many tickers 1 field => columns = Tickers
    many tickers many fields => multi index field, ticker
    """
    df = data.reindex(columns=["date", "security", *fields]).pivot(index="date", columns="security", values=fields)
    if len(ticker) == 1 and len(fields) > 1:
        df.columns = [x[0] for x in df.columns]
        # df.column.name = "fields"
    elif len(ticker) == 1 and len(fields) == 1:
        df.columns = [x[0] for x in df.columns]
        # df.column.name = "field"
    elif len(ticker) > 1 and len(fields) == 1:
        df.columns = [x[1] for x in df.columns]
        # df.column.names = "tickers"
    else:
        df.columns.names = ["field", "ticker"]
    df = df.fillna(value=np.nan)
    return df


def _normalise_bref(data):
    """Normalize Bloomberg reference data to a security-indexed frame."""
    if "security" in data.columns:
        df = data.set_index("security")
    else:
        df = data.copy()
    df = df.fillna(value=np.nan)
    return df


def _normalise_bblkref(data):
    """Normalize grouped bulk-reference responses into columns."""
    out = pd.concat({k: v.iloc[:, 0].reset_index(drop=True) for k, v in data.items()}, axis=1)
    # if is a single ticker many fields drop the duplicate level 0
    if out.columns.get_level_values(0).nunique() == 1:
        out.columns = out.columns.droplevel(0)
    return out


def _normalise_bdib(data):
    """Normalize intraday bars with a time index and stable nulls."""
    if "time" in data.columns:
        df = data.set_index("time")
    else:
        df = data.copy()
    df = df.fillna(value=np.nan)
    return df


def _normalise_bql(data):
    """Normalize BQL rows, rejecting empty results and exposing VALUE."""
    if isinstance(data, list):
        data = pd.concat(data, ignore_index=True, copy=False)
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("No Data Returned from BQL request")
    cols_to_drop = ["field", "id"]
    df = data.drop(columns=cols_to_drop, errors="ignore")
    if "value" in df.columns:
        df = df.rename(columns={"value": "VALUE"})
    return df


def _process(
    raw_data: pd.DataFrame | dict,
    input_typ: BBGReturnTypes,
    tickers: list[str] | None = None,
    fields: list[str] | None = None,
):
    """
    normalise the dataframe to a single output style
    """

    match input_typ:
        case BBGReturnTypes.BDH:
            return _normalise_bdh(raw_data, tickers, fields)
        case BBGReturnTypes.BDIB:
            return _normalise_bdib(raw_data)
        case BBGReturnTypes.BREF:
            return _normalise_bref(raw_data)
        case BBGReturnTypes.BBLKREF:
            return _normalise_bblkref(raw_data)
        case BBGReturnTypes.BQL:
            return _normalise_bql(raw_data)
        case _:
            raise LookupError(f"{input_typ} is unknown")


def bdh(
    ticker: list[str] | str,
    field: list[str] | str,
    start_date: dt.datetime | str,
    end_date: dt.datetime | str | None = None,
    overrides: tp.Sequence[tuple[str, str]] | None = None,
    options: dict | None = None,
    session: tp.Any = None,
):
    """
    Query Bloomberg history with analyst-friendly columns.

    A single ticker returns field columns. Multiple tickers with one field
    return ticker columns. Multiple tickers and fields return a
    ``(field, ticker)`` MultiIndex.

    ``session`` may be a started synchronous ``blpapi.Session``. The caller
    owns its lifecycle when it is supplied.
    """
    _, BlpQuery = _blp_types()
    # normalise all inputs
    if isinstance(ticker, str):
        ticker = [ticker]
    if isinstance(field, str):
        field = [field]
    start_date_str = _to_yyyymmdd(start_date)
    if end_date is None:
        end_date_str = (dt.datetime.now(tz=dt.timezone.utc).astimezone() + BDay(1)).strftime("%Y%m%d")
    else:
        end_date_str = _to_yyyymmdd(end_date)

    log.info(
        "query start source=bloomberg operation=bdh tickers={} fields={} start={} end={}",
        ticker,
        field,
        start_date_str,
        end_date_str,
    )
    log.debug(
        "query detail source=bloomberg operation=bdh overrides={} options={}",
        overrides,
        options,
    )
    with _blp_connection(
        BlpQuery,
        timeout=30000,
        parser=_custom_api_parser(),
        session=session,
    ) as conn:
        try:
            raw_data = conn.bdh(ticker, field, start_date_str, end_date_str, overrides, options)  # type: ignore
        except Exception:
            log.error(
                "query failed source=bloomberg operation=bdh tickers={} fields={} start={} end={}",
                ticker,
                field,
                start_date_str,
                end_date_str,
            )
            log.debug(
                "query failure detail source=bloomberg operation=bdh overrides={} options={}",
                overrides,
                options,
            )
            raise
        # normalise the data
    try:
        df = _process(raw_data, BBGReturnTypes.BDH, ticker, field)
    except Exception:
        log.error(
            "query normalize failed source=bloomberg operation=bdh tickers={} fields={}",
            ticker,
            field,
        )
        log.debug(
            "query failure detail source=bloomberg operation=bdh overrides={} options={}",
            overrides,
            options,
        )
        raise
    log.info(
        "query complete source=bloomberg operation=bdh rows={} columns={}",
        len(df),
        len(df.columns),
    )
    return df


def bref(
    ticker: list[str] | str,
    field: list[str] | str,
    overrides: tp.Sequence[tuple[str, str]] | None = None,
    options: dict[str, str] | None = None,
    allow_partial_errors: bool = True,
    session: tp.Any = None,
):
    """
    Query wrapper around the bdp (Bloomberg data point)
    single refrence data point for a ticker, i.e contract expirty date

    ``session`` may be a started synchronous ``blpapi.Session``. The caller
    owns its lifecycle when it is supplied.
    """
    _, BlpQuery = _blp_types()
    if isinstance(ticker, str):
        ticker = [ticker]
    if isinstance(field, str):
        field = [field]
    parser = _custom_api_parser() if allow_partial_errors else None
    log.info(
        "query start source=bloomberg operation=bref tickers={} fields={}",
        ticker,
        field,
    )
    log.debug(
        "query detail source=bloomberg operation=bref overrides={} options={}",
        overrides,
        options,
    )
    with _blp_connection(BlpQuery, timeout=30000, parser=parser, session=session) as conn:
        try:
            raw_data = conn.bdp(ticker, field, overrides, options)
        except Exception:
            log.error(
                "query failed source=bloomberg operation=bref tickers={} fields={}",
                ticker,
                field,
            )
            log.debug(
                "query failure detail source=bloomberg operation=bref overrides={} options={}",
                overrides,
                options,
            )
            raise
    # normalise data
    try:
        df = _process(raw_data, BBGReturnTypes.BREF)
    except Exception:
        log.error(
            "query normalize failed source=bloomberg operation=bref tickers={} fields={}",
            ticker,
            field,
        )
        raise

    log.info(
        "query complete source=bloomberg operation=bref rows={} columns={}",
        len(df),
        len(df.columns),
    )
    return df


class IntradayEventType(Enum):
    TRADE = "TRADE"
    BID = "BID"
    ASK = "ASK"
    BEST_BID = "BEST_BID"
    BEST_ASK = "BEST_ASK"


def _bdib_query(
    ticker,
    event_type,
    start_datetime_str,
    end_datetime_str,
    interval,
    overrides,
    options,
    session=None,
):
    """Fetch one ticker's intraday bars and attach its security when absent."""
    _, BlpQuery = _blp_types()
    log.info(
        "query start source=bloomberg operation=bdib ticker={} event_type={} start={} end={} interval={}",
        ticker,
        event_type,
        start_datetime_str,
        end_datetime_str,
        interval,
    )
    log.debug(
        "query detail source=bloomberg operation=bdib overrides={} options={}",
        overrides,
        options,
    )
    with _blp_connection(
        BlpQuery,
        timeout=30000,
        parser=_custom_api_parser(),
        session=session,
    ) as conn:
        try:
            resp = conn.bdib(
                ticker,
                event_type,
                interval,
                start_datetime_str,
                end_datetime_str,
                overrides,
                options,
            )
            if "security" not in resp.columns:
                resp = resp.copy()
                resp["security"] = ticker
        except Exception:  # pylint: disable=broad-exception-caught
            log.error(
                "query failed source=bloomberg operation=bdib ticker={} event_type={} start={} end={} interval={}",
                ticker,
                event_type,
                start_datetime_str,
                end_datetime_str,
                interval,
            )
            log.debug(
                "query failure detail source=bloomberg operation=bdib overrides={} options={}",
                overrides,
                options,
            )
            raise
    log.info(
        "query complete source=bloomberg operation=bdib ticker={} rows={} columns={}",
        ticker,
        len(resp),
        len(resp.columns),
    )
    return resp


def bdib(
    ticker: list[str] | str,
    start_datetime: dt.datetime | str,
    end_datetime: dt.datetime | str,
    event_type: str = IntradayEventType.BID.value,
    interval: int = 1,
    overrides: tp.Sequence[tuple[str, str]] | None = None,
    options: dict[str, str] | None = None,
    session: tp.Any = None,
):
    """
    wrapper around bdib, and make it parallised on ticker

    ``session`` may be a started synchronous ``blpapi.Session``. The caller
    owns its lifecycle when it is supplied; requests then run serially because
    synchronous Bloomberg sessions consume events from a shared stream.
    """
    #  convert to start and end pd.timestamp and then into the right string format
    start_datetime_pd = pd.to_datetime(start_datetime)
    start_datetime_str = start_datetime_pd.strftime("%Y-%m-%dT%H:%M:%S")
    end_datetime_pd = pd.to_datetime(end_datetime)
    end_datetime_str = end_datetime_pd.strftime("%Y-%m-%dT%H:%M:%S")

    # listify the tickers
    if isinstance(ticker, str):
        ticker = [ticker]
    if isinstance(event_type, IntradayEventType):
        event_type = event_type.value
    log.info(
        "query batch source=bloomberg operation=bdib tickers={} event_type={} start={} end={} interval={}",
        ticker,
        event_type,
        start_datetime_str,
        end_datetime_str,
        interval,
    )
    args = [
        (
            x,
            event_type,
            start_datetime_str,
            end_datetime_str,
            interval,
            overrides,
            options,
        )
        for x in ticker
    ]
    ret_frame = pd.DataFrame()
    if session is None:
        # run the query in a threadpool to allow for multiple tickers
        with tp_exec(5) as pool:
            futures = [pool.submit(_bdib_query, *x) for x in args]
            # collect the responses
            for fut in futures:
                resp = fut.result()
                if resp is not None and not resp.empty:
                    ret_frame = pd.concat([ret_frame, resp])
    else:
        # A synchronous blpapi.Session consumes events from a shared stream.
        for query_args in args:
            resp = _bdib_query(*query_args, session=session)
            if resp is not None and not resp.empty:
                ret_frame = pd.concat([ret_frame, resp])
    # process the response
    try:
        df = _process(ret_frame, BBGReturnTypes.BDIB)
    except Exception:
        log.error(
            "query normalize failed source=bloomberg operation=bdib tickers={} event_type={}",
            ticker,
            event_type,
        )
        raise
    log.info(
        "query complete source=bloomberg operation=bdib rows={} columns={}",
        len(df),
        len(df.columns),
    )
    return df


def bbulkref(
    ticker: list[str] | str,
    field: list[str],
    overrides: tp.Sequence[tuple[str, str]] | None = None,
    options: dict[str, str] | None = None,
    session: tp.Any = None,
):
    """
    Wrapper around the BDS endpoint
    allows for multiple fields and tickers to be queried at once

    ``session`` may be a started synchronous ``blpapi.Session``. The caller
    owns its lifecycle when it is supplied.
    """
    _, BlpQuery = _blp_types()
    if isinstance(ticker, str):
        ticker = [ticker]
    if isinstance(field, str):
        field = [field]
    log.info(
        "query start source=bloomberg operation=bbulkref tickers={} fields={}",
        ticker,
        field,
    )
    log.debug(
        "query detail source=bloomberg operation=bbulkref overrides={} options={}",
        overrides,
        options,
    )
    with _blp_connection(
        BlpQuery,
        timeout=30000,
        parser=_custom_api_parser(),
        session=session,
    ) as conn:
        try:
            # grouped by (ticker, field)
            responses = {(x, y): conn.bds(x, y, overrides, options) for x in ticker for y in field}
        except Exception:
            log.error(
                "query failed source=bloomberg operation=bbulkref tickers={} fields={}",
                ticker,
                field,
            )
            log.debug(
                "query failure detail source=bloomberg operation=bbulkref overrides={} options={}",
                overrides,
                options,
            )
            raise
    # process response to dataframe
    try:
        df = _process(responses, BBGReturnTypes.BBLKREF)
    except Exception:
        log.error("query normalize failed source=bloomberg operation=bbulkref")
        raise
    log.info(
        "query complete source=bloomberg operation=bbulkref rows={} columns={}",
        len(df),
        len(df.columns),
    )
    return df


def bql(query: str, pivot: bool = True, session: tp.Any = None):
    """Run a BQL query and optionally return its normalized DataFrame.

    ``session`` may be a started synchronous ``blpapi.Session``. The caller
    owns its lifecycle when it is supplied.
    """
    _, BlpQuery = _blp_types()
    log.info(
        "query start source=bloomberg operation=bql query_length={} pivot={}",
        len(query),
        pivot,
    )
    log.debug("query detail source=bloomberg operation=bql query={!r}", query)
    with _blp_connection(BlpQuery, timeout=30000, parser=None, session=session) as conn:
        try:
            raw_data = conn.bql(query)
        except Exception:
            log.error(
                "query failed source=bloomberg operation=bql query_length={}",
                len(query),
            )
            raise
    if pivot:
        try:
            df = _process(raw_data, BBGReturnTypes.BQL)
        except Exception:
            log.error(
                "query normalize failed source=bloomberg operation=bql query_length={}",
                len(query),
            )
            raise
        log.info(
            "query complete source=bloomberg operation=bql rows={} columns={}",
            len(df),
            len(df.columns),
        )
        return df
    log.info("query complete source=bloomberg operation=bql result=raw")
    return raw_data


def _bsrch_value(field):
    """Unwrap blp's named sequence/choice containers, retaining typed cell values."""
    while isinstance(field, dict):
        if not field:
            return None
        if len(field) != 1:
            raise ValueError(f"Invalid Bloomberg BSRCH cell: {field!r}")
        field = next(iter(field.values()))
    return field


def _normalise_bsrch(responses) -> pd.DataFrame:
    """Collect ExcelGetGrid ColumnTitles/DataRecords, including partial responses."""
    columns = None
    rows = []
    for response in responses:
        message = response["message"]
        if response["eventTypeName"] not in {"blpapi.Event.PARTIAL_RESPONSE", "blpapi.Event.RESPONSE"}:
            raise RuntimeError(f"Bloomberg BSRCH request failed: {message['element']!r}")
        data = next(iter(message["element"].values()))
        if data.get("responseError") or data.get("ErrorReport"):
            raise RuntimeError(f"Bloomberg BSRCH response error: {data!r}")
        titles = data.get("ColumnTitles")
        if titles:
            if columns is not None and columns != titles:
                raise ValueError("Bloomberg BSRCH column titles changed between response parts")
            columns = titles
        if columns is None:
            raise ValueError("Bloomberg BSRCH response has no ColumnTitles")
        for record in data.get("DataRecords", []):
            fields = record["DataRecords"]["DataFields"]
            row = [_bsrch_value(field) for field in fields]
            if len(row) != len(columns):
                raise ValueError("Bloomberg BSRCH row length does not match ColumnTitles")
            rows.append(row)
    if columns is None:
        raise ValueError("No data returned from Bloomberg BSRCH request")
    return pd.DataFrame(rows, columns=columns)


def bsrch(dataset: str = "IPD:DEX", bikey: str | None = None, session: tp.Any = None) -> pd.DataFrame:
    """Fetch a saved Bloomberg search using the core package's ExcelGetGrid request.

    Pass the saved search's ``bikey`` explicitly. ColumnTitles become DataFrame
    columns and DataRecords become rows, preserving Bloomberg's cell values.
    Partial responses are combined in arrival order; an empty search retains
    its column names.

    ``session`` may be a started synchronous ``blpapi.Session``. The caller
    owns its lifecycle when supplied, as with ``bdh``. Otherwise a local
    session is opened and closed for this call. Only ``//blp/exrsvc`` is opened;
    response waits use the other helpers' 30-second timeout and a request-local
    event queue. The optional Bloomberg runtime is imported only on invocation.
    """
    if not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("dataset must be a nonempty Bloomberg search domain")
    if not isinstance(bikey, str) or not bikey.strip():
        raise ValueError("bikey must be the nonempty saved Bloomberg search key")
    _, BlpQuery = _blp_types()
    request = {
        "ExcelGetGridRequest": {
            "Domain": dataset,
            "Overrides": [{"Overrides": {"name": "BIKEY", "value": bikey}}],
        }
    }
    log.info("query start source=bloomberg operation=bsrch dataset={}", dataset)
    try:
        with _blp_connection(
            BlpQuery, timeout=30000, parser=None, session=session, services={"ExcelGetGridRequest": "//blp/exrsvc"}
        ) as conn:
            # blp's standard parser handles refdata, not ExcelGetGrid responses.
            df = conn.query(request, parse=False, collector=_normalise_bsrch)
    except Exception:
        log.error("query failed source=bloomberg operation=bsrch dataset={}", dataset)
        raise
    log.info("query complete source=bloomberg operation=bsrch rows={} columns={}", len(df), len(df.columns))
    return df
