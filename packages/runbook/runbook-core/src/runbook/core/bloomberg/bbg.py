import datetime as dt
import typing as tp
from concurrent.futures import ThreadPoolExecutor as tp_exec
from enum import Enum

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


def _to_yyyymmdd(value: dt.datetime | str) -> str:
    """Convert a date-like value to Bloomberg's compact YYYYMMDD form."""
    ts = pd.to_datetime(value)
    return ts.strftime("%Y%m%d")


def _normalise_bdh(data, ticker, fields):
    """
    Always return columns as a ``(field, ticker)`` MultiIndex.
    """
    available_fields = [field for field in fields if field in data.columns]
    if available_fields:
        df = data.pivot(index="date", columns="security", values=available_fields)
    else:
        df = pd.DataFrame(index=pd.Index(data.get("date", pd.Series(dtype=object)), name="date").drop_duplicates())
    columns = pd.MultiIndex.from_product([fields, ticker], names=["field", "ticker"])
    return df.reindex(columns=columns).fillna(value=np.nan)


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
):
    """
    Simple wrapper around the BlpQuery api to query and normalise the data
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
    with BlpQuery(timeout=30000, parser=_custom_api_parser()) as conn:
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
):
    """
    Query wrapper around the bdp (Bloomberg data point)
    single refrence data point for a ticker, i.e contract expirty date
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
    with BlpQuery(timeout=30000, parser=parser) as conn:
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
    with BlpQuery(timeout=30000, parser=_custom_api_parser()) as conn:
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
):
    """
    wrapper around bdib, and make it parallised on ticker
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
    # run the query in a threadpool to allow for multiple tickers
    with tp_exec(5) as pool:
        futures = [pool.submit(_bdib_query, *x) for x in args]
        # collect the responses
        for fut in futures:
            resp = fut.result()
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
):
    """
    Wrapper around the BDS endpoint
    allows for multiple fields and tickers to be queried at once
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
    with BlpQuery(timeout=30000, parser=_custom_api_parser()) as conn:
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


def bql(query: str, pivot: bool = True):
    """Run a BQL query and optionally return its normalized DataFrame."""
    _, BlpQuery = _blp_types()
    log.info(
        "query start source=bloomberg operation=bql query_length={} pivot={}",
        len(query),
        pivot,
    )
    log.debug("query detail source=bloomberg operation=bql query={!r}", query)
    with BlpQuery(timeout=30000) as conn:
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


# TODO(LT):>> Add BSRCH
