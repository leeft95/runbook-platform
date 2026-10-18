import datetime as dt
import getpass
import os
import re
import sys
import typing as tp

import numpy as np
import pandas as pd
from aiohttp.client_exceptions import ClientConnectorError
from blp.blp import BlpParser
from blp.blp import BlpQuery
from blpapi import Event
from blpapi import Session
from blpapi import SessionOptions
from ecm.atom.clients import ECMClientError
from ecm.atom.clients import ECMHttpError
from ecm.atom.services import context
from ecm.cmds.core.cdr import today
from ecm.cmds.core.config import default_atom_config
from ecm.cmds.core.config import DREMIO_TOKENS
from ecm.cmds.core.pyg import get_data
from ecm.cmds.core.ticker import flat_to_spread
from loguru import logger as log
from pandas.tseries.offsets import BDay

try:
    current_user = os.getlogin()
except OSError:
    current_user = getpass.getuser()

bbg_service_switch = dict(
    ltrindade="prod_lt", rzhao="prod_rz", jmcphillips="prod_rz", pmlo25_svc="prod_lt", lballand="prod_lt",
)
bbg_svc_env = bbg_service_switch.get(current_user, "prod_lt")
backup_bbg_service_switch = dict(
    ltrindade="prod_lt", rzhao="prod_lt", jmcphillips="prod_rz", pmlo25_svc="prod_lt", lballand="prod_rz",
)
backup_bbg_svc_env = backup_bbg_service_switch.get(current_user, "prod_lt")

atom_services_context = dict(default_atom_config, **{"lo25_internal": {"environment": bbg_svc_env}})
backup_services_context = dict(default_atom_config, **{"lo25_internal": {"environment": backup_bbg_svc_env}})

retry_on_errors = [
    "INVALID_SECURITY", "Failed to start with", "No Data Returned trying backup service",
    "Alternative Override used will use backup", "'subcategory': 'EID_NEEDED'",
]
os.environ["DREMIO_ACCESS_TOKEN"] = DREMIO_TOKENS.get(current_user, os.environ.get("ECM_DREMIO_TOKEN_DEFAULT", ""))

use_remote = sys.platform == "linux" or current_user not in [
    "rzhao", "jmcphillips",
    "mkiano", "lballand", "caitcheson",
]
only_remote = current_user in ["pmlo25_svc"] or sys.platform == "linux"

option_pattern = None


def _log_security_error_processor(response, request_data):
    """Custom processor that validates responses and logs errors instead of raising exceptions.

    Performs all standard validation steps but catches errors and logs them, injecting empty
    data for failed securities so they return as NaN columns instead of being omitted.
    """
    if response["eventType"] not in (Event.PARTIAL_RESPONSE, Event.RESPONSE):
        log.error(f"Invalid eventType: {response['eventType']}")
        return response
    rtype = list(response["message"]["element"].keys())[0]
    response_data = response["message"]["element"][rtype]

    known_responses = (
        "ReferenceDataResponse", "HistoricalDataResponse", "IntradayBarResponse", "BeqsResponse",
        "IntradayTickResponse", "fieldResponse", "InstrumentListResponse", "GetFillsResponse",
    )
    if rtype not in known_responses:
        log.error(f"Unknown response type {rtype!r}, expected one of {known_responses}")
        return response

    if "responseError" in response_data:
        log.error(f"Response contains responseError: {response_data['responseError']}")
        return response
    if rtype in ("IntradayBarResponse", "IntradayTickResponse", "BeqsResponse", "fieldResponse", "InstrumentListResponse", "GetFillsResponse"):
        return response
    if rtype == "HistoricalDataResponse":
        response_data = [response_data]

    for sec_data in response_data:
        data = sec_data.get("securityData", {})
        if "securityError" in data:
            security = data.get("security", "unknown")
            error_info = data["securityError"]
            log.warning(f"Security error for {security}: {error_info}")
            data["fieldData"] = []
        field_exceptions = data.get("fieldExceptions", [])
        for fe in field_exceptions:
            fe_data = fe.get("fieldExceptions", {})
            error_info = fe_data.get("errorInfo", {}).get("errorInfo", {})
            category = error_info.get("category")
            subcategory = error_info.get("subcategory")
            if category == "BAD_FLD" and subcategory == "NOT_APPLICABLE_TO_REF_DATA":
                field = fe_data.get("fieldId")
                log.debug(f"Field {field} not applicable to {data.get('security', 'unknown')}")
                if "fieldData" in data and data["fieldData"]:
                    data["fieldData"][0]["fieldData"][field] = None
            else:
                security = data.get("security", "unknown")
                log.warning(f"Field exception for {security}: {fe_data}")
    return response


def query_atom_bdh(
    ticker: tp.Union[str, tp.List[str]], fields: tp.Union[str, tp.List[str]],
    sdate: dt.datetime, edate: dt.datetime,
    options: tp.Union[tp.Dict[str, str], tp.List[tp.Tuple[str, str]]] | None = None,
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    use_alt: bool = False,
):
    if isinstance(ticker, str):
        ticker = [ticker]
    if isinstance(fields, str):
        fields = [fields]
    if options and not isinstance(options, dict) and all(isinstance(o, tuple) for o in options):
        options = {x: y for x, y in options}
    if overrides and not isinstance(overrides, dict) and isinstance(overrides, list) and all(isinstance(o, tuple) for o in overrides):
        overrides = [dict(key=x, value=y) for x, y in overrides]
    try:
        if not use_alt:
            with context(atom_services_context) as ctx:
                client = ctx.lo25_internal
                data: pd.DataFrame = client.get_bdh(
                    ticker=ticker, fields=fields, start_date=sdate, end_date=edate,
                    options=options, overrides=overrides,
                )
                if "date" in data.columns:
                    data = data.set_index("date")
                    data.index = data.index.astype("datetime64[ns]")
                if data.empty:
                    raise ValueError("No Data Returned trying backup service")
        else:
            raise ValueError("Alternative Override used will use backup")
    except (ClientConnectorError, ECMHttpError, ValueError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        elif isinstance(e, ValueError) and any(x == str(e) for x in retry_on_errors):
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bdh(
                    ticker=ticker, fields=fields, start_date=sdate, end_date=edate,
                    options=options, overrides=overrides,
                )
            if "date" in data.columns:
                data = data.set_index("date")
                data.index = data.index.astype("datetime64[ns]")
        else:
            raise e
    if not data.empty:
        if len(ticker) == 1:
            data.columns = pd.Index([x.split("|")[0] for x in data.columns])
            data.columns.names = ["field"]
        elif len(ticker) > 1 and len(fields) == 1:
            data.columns = pd.Index([x.split("|")[1] for x in data.columns])
            data.columns.names = ["ticker"]
            raise NotImplementedError("Photographed query_atom_bdh lines236–237 unavailable")
        else:
            data.columns = pd.Index([tuple(x.split("|")) for x in data.columns])
            data.columns.names = ["field", "ticker"]
    return data


def bdh(ticker, fields, sdate, edate=None, ovrds=None, elms=None, use_alt=False, use_bpipe=False, retries=0):
    """
    update historical data from bloomberg
    """
    try:
        try:
            if use_remote:
                if edate is None:
                    edate = dt.date.today() + BDay(1)
                df = query_atom_bdh(ticker, fields, sdate, edate, elms, ovrds, use_alt)
                df = df.fillna(value=np.nan)
                return df
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        if not isinstance(ticker, list):
            ticker = [ticker]
        if isinstance(fields, str):
            fields = [fields]
        use_bpipe = False if any(x.startswith("LNK") for x in ticker) else use_bpipe
        if option_pattern is None:
            raise NotImplementedError("Photographed bbg_blp.py option_pattern suffix75 unavailable")
        if any(option_pattern.match(tic) for tic in ticker):
            use_bpipe = True
        custom_parser = BlpParser(processor_steps=[_log_security_error_processor], raise_security_errors=False)
        BPipe = BlpQuery(timeout=20000, app="element_cap:EDH", host="69.184.252.2", parser=custom_parser)
        with BlpQuery(timeout=30000, parser=custom_parser) if not use_bpipe else BPipe as con:
            if edate is None:
                edate = dt.date.today() + BDay(1)
            if not isinstance(sdate, str):
                sdate = dt.datetime.strftime(sdate, "%Y%m%d")
            if not isinstance(edate, str):
                edate = dt.datetime.strftime(edate, "%Y%m%d")
            if elms is None and ovrds is None:
                df = con.bdh(ticker, fields, sdate, edate)
            elif elms is None:
                df = con.bdh(ticker, fields, sdate, edate, overrides=ovrds)
            elif ovrds is None:
                df = con.bdh(ticker, fields, sdate, edate, options=elms)
            else:
                df = con.bdh(ticker, fields, sdate, edate, overrides=ovrds, options=elms)
        df = df.pivot(columns=["security"], values=fields if isinstance(fields, list) else [fields], index=["date"])
        if isinstance(ticker, str):
            ticker = [ticker]
        if len(ticker) == 1 and len(fields) > 1:
            df.columns = [x[0] for x in df.columns]
        elif len(ticker) == 1 and len(fields) == 1:
            df.columns = [x[0] for x in df.columns]
        elif len(ticker) > 1 and len(fields) == 1:
            df.columns = [x[1] for x in df.columns]
            df = df[[x for x in ticker if x in df.columns]]
        else:
            df.columns.names = ["field", "ticker"]
        df = df.fillna(value=np.nan)
        return df
    except Exception as e:
        if isinstance(e, ConnectionError):
            log.error(f"Could not process Bdh request for {ticker} | {fields} |" f" {sdate} | {edate} | [photographed message clipped]")
            return pd.DataFrame()
        else:
            if isinstance(e, TypeError):
                if "EID_NEEDED" in str(e):
                    log.debug(f"Request for {ticker} | {fields} |" f" {sdate} | {edate} | {elms} | {ovrds} [photographed message clipped]")
                    if use_bpipe:
                        data = bdh(ticker, fields, sdate, edate, ovrds, elms, use_alt, use_bpipe=False)
                        return data
                log.error(f"Coul not process Bdh request for {ticker} | {fields} |" f" {sdate} | {edate} [photographed message clipped]")
            if "TIMEOUT" in str(e) and retries != 2:
                log.error(f"TIMEOUT in request retrying: Attempt: {retries}/2")
                data = bdh(ticker, fields, sdate, edate, ovrds, elms, use_alt, use_bpipe=False, retries=retries + 1)
                return data
            elif "INVALID_SECURITY" in str(e):
                log.error(e)
            else:
                raise e


def query_atom_bql(query: str, use_alt: bool = False):
    try:
        if not use_alt:
            with context(atom_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bql(query=query)
                if "index" in data.columns:
                    data = data.drop(columns=["index"])
        else:
            raise ValueError("Alternative Override used will use backup")
    except (ClientConnectorError, ECMHttpError, ValueError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        elif isinstance(e, ValueError) and "Alternative Override used will use backup" == str(e):
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bql(query=query)
                if "index" in data.columns:
                    data = data.drop(columns=["index"])
        else:
            raise e
    return data


def bql(query: str, pivot: bool = True, use_alt: bool = False, use_bpipe=False) -> pd.DataFrame:
    try:
        try:
            if use_remote:
                df = query_atom_bql(query, use_alt)
                return df
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        BPipe = BlpQuery(timeout=20000, app="element_cap:EDH", host="69.184.252.2")
        with BlpQuery(timeout=30000) if not use_bpipe else BPipe as con:
            try:
                df = con.bql(query)
            except Exception as e:
                log.error(f"Could not complete request for query {query} because of \n {e}")
                df = pd.DataFrame()
                return df
        if pivot:
            if isinstance(df, list):
                df = pd.concat(df, ignore_index=True)
            if not isinstance(df, pd.DataFrame) or df.empty:
                raise ValueError("No Data Returned from BQL request")
            valid_cols = [x for x in df.columns if x not in ["field", "id"]]
            df = df[valid_cols]
            df = df.rename(columns={"value": "VALUE"})
        return df
    except Exception as e:
        if isinstance(e, TypeError):
            if "EID_NEEDED" in str(e):
                log.debug(f"Request for {query} | {use_bpipe}" "has thrown a security error likely needs e[photographed message clipped]")
                if use_bpipe:
                    data = bql(query, pivot, use_alt, use_bpipe=False)
                    return data
        log.error(f"Could not process BQL request for {query}")
        log.error(e)
        if "INVALID_SECURITY" not in str(e):
            raise e


def query_atom_bbulkref(
    ticker: tp.List[str], fields: tp.List[str],
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    use_alt: bool = False,
):
    if isinstance(fields, str):
        fields = [fields]
    if overrides and not isinstance(overrides, dict) and isinstance(overrides, list) and all(isinstance(o, tuple) for o in overrides):
        overrides = [dict(key=x, value=y) for x, y in overrides]
    try:
        if not use_alt:
            with context(atom_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bulkref(ticker=ticker, fields=fields, overrides=overrides)
                data.columns = [x.split("|")[0] for x in data.columns]
                if "security" in data.columns:
                    data = data.set_index("security")
        else:
            raise ValueError("Alternative Override used will use backup")
    except (ClientConnectorError, ECMHttpError, ValueError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        elif isinstance(e, ValueError) and "Alternative Override used will use backup" == str(e):
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bulkref(ticker=ticker, fields=fields, overrides=overrides)
                data.columns = [x.split("|")[0] for x in data.columns]
                if "security" in data.columns:
                    data = data.set_index("security")
        else:
            raise e
    return data


def bbulkref(
    ticker: tp.List[str], fields: tp.List[str] | str,
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    raw: bool = True, use_alt: bool = False, use_bpipe=False, **kwargs,
):
    if "option" in kwargs.keys():
        overrides = kwargs.pop("option", overrides)
    if isinstance(fields, str):
        fields = [fields]
    try:
        try:
            if use_remote:
                response_df = query_atom_bbulkref(ticker, fields, overrides, use_alt)
                response_df = response_df.fillna(value=np.nan)
                return response_df
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        BPipe = BlpQuery(timeout=20000, app="element_cap:EDH", host="69.184.252.2")
        with BlpQuery(timeout=30000) if not use_bpipe else BPipe as con:
            responses = {x: con.bds(ticker, x, overrides=overrides) for x in fields}
        if not raw:
            formatted_frames = []
            for k, v in responses.items():
                raise NotImplementedError("Photographed bbulkref column condition537 unavailable")
                if ...:
                    cols = [(ticker, x) for x in v.columns]
                else:
                    cols = [(ticker, k)]
                v.columns = pd.MultiIndex.from_tuples(cols)
                formatted_frames.append(v)
            response_df = pd.concat(formatted_frames, axis=1)
            if "security" in response_df.columns:
                response_df = response_df.set_index("security")
            response_df = response_df.fillna(value=np.nan)
            return response_df
        else:
            return responses[fields[0]] if len(fields) == 1 else responses
    except Exception as e:
        if isinstance(e, TypeError):
            if "EID_NEEDED" in str(e):
                log.debug(f"Request for {ticker} | {fields} | {overrides} | {use_bpipe}" "has thrown a secu[photographed message clipped]")
                if use_bpipe:
                    data = bbulkref(ticker, fields, overrides, raw, use_alt, use_bpipe=False)
                    return data
        elif "INVALID_SECURITY" in str(e):
            log.error("Could not process bbulkref request for" f" {ticker} | {fields} | {overrides}\n{str(e)}")
        else:
            raise e


def query_atom_bref(
    ticker: tp.List[str] | str, fields: tp.List[str],
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    use_alt: bool = False,
):
    if isinstance(fields, str):
        fields = [fields]
    if overrides and not isinstance(overrides, dict) and all(isinstance(o, tuple) for o in overrides):
        overrides = [dict(key=x, value=y) for x, y in overrides]
    try:
        if not use_alt:
            with context(atom_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bref(ticker=ticker, fields=fields, overrides=overrides)
                data.columns = [x.split("|")[0] for x in data.columns]
                if "security" in data.columns:
                    data = data.set_index("security")
        else:
            raise ValueError("Alternative Override used will use backup")
    except (ClientConnectorError, ECMHttpError, ValueError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        elif isinstance(e, ValueError) and "Alternative Override used will use backup" == str(e):
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as ctx:
                client = ctx.lo25_internal
                data = client.get_bref(ticker=ticker, fields=fields, overrides=overrides)
                data.columns = [x.split("|")[0] for x in data.columns]
                if "security" in data.columns:
                    data = data.set_index("security")
        else:
            raise e
    return data


def bref(
    ticker: tp.List[str] | str, fields: tp.List[str] | str,
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    use_alt: bool = False, use_bpipe: bool = False, retries: int = 0, **kwargs,
):
    if "option" in kwargs.keys():
        overrides = kwargs.pop("option")
    if "options" in kwargs.keys():
        overrides = kwargs.pop("options")
    if isinstance(fields, str):
        fields = [fields]
    try:
        try:
            if use_remote:
                response_df = query_atom_bref(ticker, fields, overrides, use_alt)
                response_df = response_df.fillna(value=np.nan)
                return response_df
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        BPipe = BlpQuery(timeout=20000, app="element_cap:EDH", host="69.184.252.2")
        if option_pattern is None:
            raise NotImplementedError("Photographed bbg_blp.py option_pattern suffix75 unavailable")
        if any(option_pattern.match(tic) for tic in (ticker if isinstance(ticker, list) else [ticker])):
            use_bpipe = True
        with BlpQuery(timeout=30000) if not use_bpipe else BPipe as con:
            responses = con.bdp(ticker, fields=fields, overrides=overrides)
            if "security" in responses.columns:
                responses = responses.set_index("security")
            responses = responses.fillna(value=np.nan)
        return responses
    except Exception as e:
        if isinstance(e, TypeError):
            if "EID_NEEDED" in str(e):
                raise NotImplementedError("Photographed bref retry branch658–659 unavailable")
                if ...:
                    data = bref(ticker, fields, overrides, use_alt, use_bpipe=use_bpipe)
                    return data
        log.error(f"Could not process bref request for {ticker} | {fields} | {overrides}")
        log.error(e)
        if "TIMEOUT" in str(e) and retries != 2:
            log.error(f"TIMEOUT in request retrying: Attempt: {retries}/2")
            data = bref(ticker, fields, overrides, use_alt, use_bpipe=False, retries=retries + 1)
            return data
        elif "INVALID_SECURITY" in str(e):
            log.error(str(e))
        else:
            raise e


def release_schedule(ticker: str, fields: str | tp.List[str], data=None, sdate=None, edate=None):
    """
    get bulk reference data from bloomberg
    fields must be list
    start from the end of data
    """
    if data is None:
        if sdate is None:
            sdate = dt.datetime(2000, 1, 1)
    else:
        sdate = data.iloc[-1, 0]
        if isinstance(sdate, str):
            sdate = pd.to_datetime(sdate)
    if edate is None:
        edate = dt.date.today() + dt.timedelta(days=364)
    df = bbulkref(
        [ticker], fields,
        [("START_DT", sdate.strftime(format="%Y%m%d")), ("END_DT", edate.strftime(format="%Y%m%d"))],
        raw=True,
    )
    if isinstance(df, pd.DataFrame):
        df.columns = ["value"]
    if data is None:
        return df.value
    else:
        return pd.concat([data.iloc[:-1, :], df["value"].to_frame(data.columns[0])], axis=0, ignore_index=True)


def query_atom_bdib(
    ticker: str | tp.List[str], sdate: dt.datetime, edate: dt.datetime,
    event_type: str = "TRADE", interval: int = 1,
    options: tp.Union[tp.Dict[str, str], tp.List[tp.Tuple[str, str]]] | None = None,
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    use_alt: bool = False,
):
    if isinstance(ticker, str):
        ticker = [ticker]
    if options and not isinstance(options, dict) and all(isinstance(o, tuple) for o in options):
        options = {x: y for x, y in options}
    if overrides and not isinstance(overrides, dict) and isinstance(overrides, list) and all(isinstance(o, tuple) for o in overrides):
        overrides = [dict(key=x, value=y) for x, y in overrides]
    try:
        if not use_alt:
            with context(atom_services_context) as ctx:
                dfs = []
                for t in ticker:
                    client = ctx.lo25_internal
                    data = client.get_bdib(ticker=t, start_date=sdate, end_date=edate, event_type=event_type,
                                           interval=interval, options=options, overrides=overrides)
                    if "index" in data.columns:
                        data = data.drop(columns=["index"])
                    dfs.append(data)
            return_df = pd.concat(dfs)
            if "time" in return_df.columns:
                return_df = return_df.set_index("time")
            return_df.index = return_df.index.astype("datetime64[ns]")
        else:
            raise ValueError("Alternative Override used will use backup")
    except (ClientConnectorError, ECMHttpError, ValueError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        elif isinstance(e, ValueError) and "Alternative Override used will use backup" == str(e):
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as ctx:
                client = ctx.lo25_internal
                dfs = []
                for t in ticker:
                    client = ctx.lo25_internal
                    data = client.get_bdib(ticker=t, start_date=sdate, end_date=edate, event_type=event_type,
                                           interval=interval, options=options, overrides=overrides)
                    if "index" in data.columns:
                        data = data.drop(columns=["index"])
                    dfs.append(data)
            return_df = pd.concat(dfs)
            if "time" in return_df.columns:
                return_df = return_df.set_index("time")
            return_df.index = return_df.index.astype("datetime64[ns]")
        else:
            raise e
    return return_df


def bdib(
    ticker: str | tp.List[str], sdate: dt.datetime, edate: dt.datetime,
    event_type: str = "TRADE", interval: int = 1,
    options: tp.Union[tp.Dict[str, str], tp.List[tp.Tuple[str, str]]] | None = None,
    overrides: tp.Union[tp.List[tp.Dict[str, str]], tp.List[tp.Tuple[str, str]]] | None = None,
    use_alt: bool = False, use_bpipe: bool = False, retries: int = 0,
):
    if isinstance(sdate, str):
        sdate = pd.to_datetime(sdate)
    if isinstance(edate, str):
        edate = pd.to_datetime(edate)
    if isinstance(ticker, str):
        ticker = [ticker]
    try:
        try:
            if use_remote:
                data = query_atom_bdib(ticker, sdate, edate, event_type, interval, options, overrides, use_alt)
                return data
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        if not isinstance(sdate, str):
            sdate_str = dt.datetime.strftime(sdate, "%Y-%m-%dT%H:%M:%S")
        else:
            sdate_str = sdate
        if not isinstance(edate, str):
            edate_str = dt.datetime.strftime(edate, "%Y-%m-%dT%H:%M:%S")
        else:
            edate_str = edate
        BPipe = BlpQuery(timeout=20000, app="element_cap:EDH", host="69.184.252.2")
        with BlpQuery(timeout=30000) if not use_bpipe else BPipe as con:
            dfs = []
            for t in ticker:
                df = con.bdib(t, event_type, interval, sdate_str, edate_str, overrides=overrides, options=options)
                df["ticker"] = t
                dfs.append(df)
            return_df = pd.concat(dfs)
        if "time" in return_df.columns:
            return_df = return_df.set_index("time")
        return return_df
    except Exception as e:
        if isinstance(e, TypeError):
            if "EID_NEEDED" in str(e):
                log.debug(f"Request for {ticker} | {sdate} -> {edate}| {use_bpipe}" " has thrown a securit[photographed message clipped]")
                if use_bpipe:
                    data = bdib(ticker, sdate, edate, event_type, interval, options, overrides, use_alt, use_bpipe=False)
                    return data
        if "TIMEOUT" in str(e) and retries != 2:
            data = bdib(ticker, sdate, edate, event_type, interval, options, overrides, use_alt,
                        use_bpipe=False, retries=retries + 1)
        elif "INVALID_SECURITY" in str(e):
            log.error(f"Could not process bdib request for {ticker} | {sdate} -> {edate}\n{str(e)}")
        else:
            raise e


class BSRCHHandler:
    def __init__(self, host="69.184.252.2", port=8194, appID="element_cap:EDH"):
        self.__host = host
        self.__port = port
        self.__app = appID
        options = SessionOptions()
        options.setServerHost(self.__host)
        options.setServerPort(self.__port)
        raise NotImplementedError("Photographed BSRCH authentication options901 are incomplete")
        self.__session = None
        self.__service = None
        self.__connected = False
        self.__started = False

        try:
            self.__session = Session(options)
            self.__started = self.__session.start()
            if not self.__started:
                raise ConnectionError("Failed to start Bloomberg session")
            if not self.__session.openService("//blp/exrsvc"):
                raise ConnectionError("Failed to open Bloomberg exrsvc service")
            self.__service = self.__session.getService("//blp/exrsvc")
            self.__connected = True
        except Exception:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        """Explicitly close the Bloomberg session and release resources."""
        if self.__started and self.__session is not None:
            try:
                self.__session.stop()
            except Exception:
                pass  # Ignore errors during cleanup
            finally:
                self.__session = None
                self.__service = None
                self.__connected = False
                self.__started = False

    def __del__(self):
        """Cleanup fallback for garbage collection."""
        self.close()

    def create_request(self, **args):
        if not self.__connected:
            raise ConnectionError("Bloomberg session is not connected")
        request = self.__service.createRequest("ExcelGetGridRequest")
        service_list = ["IPD:DEX", "comdty:ngasmeta", "comdty:ngasflow", "comdty:weather"]
        if args["dataset"] in service_list:
            request.set("Domain", args["dataset"])
        else:
            print(
                """The selected dataset, {} is not support.
                Only {} are currently supported.
                Please use to listed format the refer to dataset""".format(
                    args["dataset"], service_list
                )
            )
        overrides = request.getElement("Overrides")
        for k, v in args["args"].items():
            element = overrides.appendElement()
            element.setElement("name", k)
            element.setElement("value", v)
        return request

    def send_request(self, request):
        """Sends the ExcelRequest object to send to the Bloomberg API

        Parameters
        ----------
        request: A dict() containing the request properties we add to the ExcelGetGridRequest

        Return: blpapi.Event object
        """
        if not self.__connected or self.__session is None:
            raise ConnectionError("Bloomberg session is not connected")
        self.__session.sendRequest(request)
        return self.wait_for_response()

    def wait_for_response(self):
        while True:
            event = self.__session.nextEvent(4000)
            if event.eventType() == Event.TIMEOUT:
                pass
            if event.eventType() == Event.RESPONSE:
                return event

    def process_response(self, event):
        results = []
        for message in event:
            try:
                element = message.asElement()
                titles = element.getElement("ColumnTitles")
                titles = [titles.getValueAsString(i) for i in range(titles.numValues())]
            except Exception as e:
                raise e
            if titles:
                records = element.getElement("DataRecords")
                rows = []
                for i in range(records.numValues()):
                    record = records.getValueAsElement(i)
                    field_list = record.getElement("DataFields")
                    row = []
                    for j in range(field_list.numValues()):
                        field = field_list.getValueAsElement(j)
                        row.append(field.getElement(0).getValue())
                    rows.append(row)
                df = pd.DataFrame(rows, columns=titles)
                results.append(df)
            else:
                raise ValueError("Invalid parameter passed: {}".format(message))
        return results

    def get_BSRCH_data(self, **args):
        request = self.create_request(**args)
        response = self.send_request(request)
        if response:
            results = self.process_response(response)
            return results[0]
        else:
            raise ValueError(f"Could not complete BSRCH request for {args}")


def args_hist(x, startDate, endDate, fields, frequency):
    return {
        "dataset": "comdty:weather",
        "args": {
            "location": x,
            "model": "actuals",
            "target_start_date": startDate,
            "target_end_date": endDate,  # history finished yesterday
            "frequency": frequency,
            "fields": fields,
        },
    }


def args_fcst(station, publication_date, run, model, model_type, fields):
    if run < 10:
        run = "0{0}".format(str(run))
    pubdate = publication_date.strftime("%Y-%m-%d") + "T{0}:00:00".format(str(run))
    return {
        "dataset": "comdty:weather",
        "args": {
            "location": station,
            "model": model,
            "type": model_type,
            "publication_date": pubdate,
            "fields": fields,
        },
    }


def query_atom_historical_weather(location="FR", sdate=None, edate=None, field="TEMPERATURE", frequency="DAILY"):
    if sdate is None:
        start = "2020-01-01"
    else:
        start = pd.to_datetime(sdate)
    if edate is None:
        end = today().strftime(edate, "%Y-%m-%d")
    else:
        end = pd.to_datetime(edate)
    try:
        with context(atom_services_context) as cntx:
            client = cntx.lo25_internal
            resp = client.get_bsrch_weather_historical(location=location, start_date=start, end_date=end, field=field, frequency=frequency)
            return resp
    except (ClientConnectorError, ECMHttpError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as cntx:
                client = cntx.lo25_internal
                resp = client.get_bsrch_weather_historical(
                    location=location, start_date=start, end_date=end, field=field, frequency=frequency,
                )
                return resp
        else:
            raise e


def get_historical_weather(location="FR", sdate=None, edate=None, field="TEMPERATURE", frequency="DAILY"):
    try:
        try:
            if use_remote:
                if not isinstance(field, list):
                    field = [field]
                df = query_atom_historical_weather(location, sdate, edate, field, frequency)
                df = df.fillna(value=np.nan)
                return df
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        if sdate is None:
            start = "2021-01-01"
        else:
            start = pd.to_datetime(sdate).strftime("%Y-%m-%d")
        if edate is None:
            end = today().strftime(edate, "%Y-%m-%d")
        else:
            end = pd.to_datetime(edate).strftime("%Y-%m-%d")
        with BSRCHHandler() as bsrch:
            if isinstance(field, list):
                frames = []
                idx_col = "Reported Time"
                for fld in field:
                    f = bsrch.get_BSRCH_data(**args_hist(location.upper(), start, end, fld.upper(), frequency)).set_index(idx_col)
                    frames.append(f)
                df = frames[0]
                for f in frames[1:]:
                    df = df.join(f, how="outer")
                df = df.reset_index()
            else:
                df = bsrch.get_BSRCH_data(**args_hist(location.upper(), start, end, field.upper(), frequency))
        return df
    except Exception as e:
        log.error(f"Could not process bsrch request for {location}" f" | {field} | {frequency} | {sdate}[photographed message clipped]")
        raise e


def query_atom_forcast_weather(
    location="FR", publication_date=None, run=0, model="ECMWF", model_type="ENSEMBLE_MEAN",
    field="TEMPERATURE", use_alt: bool = False,
):
    try:
        if not use_alt:
            with context(atom_services_context) as cntx:
                client = cntx.lo25_internal
                resp = client.get_bsrch_weather_forecast(
                    location=location, publication_date=publication_date, run=run,
                    model=model, model_type=model_type, field=field,
                )
                return resp
        else:
            raise ValueError("Alternative Override used will use backup")
    except (ClientConnectorError, ECMHttpError, ValueError) as e:
        if isinstance(e, ECMHttpError):
            msg = e.data.get("exception_message")
            if any(x in msg for x in retry_on_errors):
                log.warning(f"INVALID_SECURITY or bbg down on {bbg_svc_env} trying {backup_bbg_svc_env}")
                retry = True
            else:
                retry = False
        elif isinstance(e, ClientConnectorError):
            log.warning(f"Service down on {bbg_svc_env} trying {backup_bbg_svc_env}")
            retry = True
        elif isinstance(e, ValueError) and "Alternative Override used will use backup" == str(e):
            retry = True
        else:
            retry = False
        if retry:
            with context(backup_services_context) as cntx:
                client = cntx.lo25_internal
                resp = client.get_bsrch_weather_forecast(
                    location=location, publication_date=publication_date, run=run,
                    model=model, model_type=model_type, field=field,
                )
                return resp
        else:
            raise e


def get_weather_forecast(
    location="FR", publication_date=None, run=0, model="ECMWF", model_type="ENSEMBLE_MEAN",
    field="TEMPERATURE", use_alt: bool = False,
):
    if publication_date is None:
        publication_date = today()
    try:
        try:
            if use_remote:
                if not isinstance(field, list):
                    field = [field]
                df = query_atom_forcast_weather(location, publication_date, run, model, model_type, field, use_alt)
                df = df.fillna(value=np.nan)
                return df
            else:
                pass
        except ECMHttpError as he:
            log.error(
                f"{he.data.get('message')}\n{he.data.get('stack_trace')}\n\n"
                "Could not complete query via remote bbg service"
                f" on {bbg_service_switch.get(current_user, 'prod_lt')}"
                " attempting direct local to bbg"
            )
            if only_remote:
                raise he
        except ECMClientError as ce:
            log.error(f"Could not complete query via remote bbg service due to {ce} in client code " "attempting direct local to bbg")
            if only_remote:
                raise ce
        with BSRCHHandler() as bsrch:
            if isinstance(field, list):
                frames = []
                idx_col = "Reported Time"
                for fld in field:
                    f = bsrch.get_BSRCH_data(
                        **args_fcst(location.upper(), publication_date, run, model.upper(), model_type.upper(), fld.upper())
                    ).set_index(idx_col)
                    frames.append(f)
                df = frames[0]
                for f in frames[1:]:
                    df = df.join(f, how="outer")
                df = df.reset_index()
            else:
                df = bsrch.get_BSRCH_data(
                    **args_fcst(location.upper(), publication_date, run, model.upper(), model_type.upper(), field.upper())
                )
        return df
    except Exception as e:
        log.error(f"Could not process bsrch request for {location} | {field} " f"| {model} | {publication_date}[photographed message clipped]")
        if "No weather data points found" in str(e):
            log.error("No weather data points found... run usually to early")
            return pd.DataFrame()
        raise e


def args_bikey(dataset, bikey):
    return {"dataset": dataset, "args": {"BIKEY": bikey}}


def bsrch(dataset="IPD:DEX", bikey="RWJWX71X52CI"):
    with BSRCHHandler() as handler:
        df = handler.get_BSRCH_data(**args_bikey(dataset, bikey))
    return df


def live_contract(active, db="contracts", seq=0, roll="t3"):
    """
    Get live contract from mongodb
    seq: 0 is the front contract
    db: contracts - flat; spreads - spread
    """
    if db == "contracts":
        contracts = get_data(db, active=active, item="t")
    elif db == "spreads":
        contracts = get_data(db, active=active, item="sprd_chain")
    return contracts.loc[contracts[roll] > today(), :].iloc[seq, :]


def live_spread_ticker(active, roll="t3", spread="26", short_ticker=True):
    """
    Get live synthetic 2-6 spread
    """
    contracts = get_data("contracts", active=active, item="fut_chain")
    ticker1 = (contracts.loc[contracts[roll] > today(), :].iloc[int(spread[0]) - 1, :]).ticker
    ticker2 = (contracts.loc[contracts[roll] > today(), :].iloc[int(spread[-1]) - 1, :]).ticker
    return flat_to_spread(ticker1, ticker2, short_ticker=short_ticker)


if __name__ == "__main__":

    x = get_weather_forecast(location="DE", publication_date=dt.datetime(2026, 1, 5), run=0)
    print(x)
