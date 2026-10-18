import datetime as dt
import json
import os
from itertools import cycle

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from ecm.cmds.core.bbg_blp import bbulkref
from ecm.cmds.core.bbg_blp import bref
from ecm.cmds.core.cdr import bday_adj
from ecm.cmds.core.cdr import last_month
from ecm.cmds.core.cdr import month_int2str
from ecm.cmds.core.cdr import month_str2int
from ecm.cmds.core.cdr import today
from ecm.cmds.core.pyg import bbg_db
from ecm.cmds.core.pyg import get_cell
from ecm.cmds.core.pyg import get_data
from ecm.cmds.core.ticker import contract2active_y_m
from ecm.cmds.core.ticker import expiry_to_first_of_month
from ecm.cmds.core.ticker import get_active
from ecm.cmds.core.ticker import yy2year
from ecm.cmds.core.time_series import dwmy
from ecm.cmds.vendor._bbg import bdh_update
from isoweek import Week
from pandas.tseries.offsets import BDay
from pyg_base import dictable
from pyg_cell import periodic_cell

_synthetic_gen_forwards = {
    "ELGB": "BCFV",
    "ELGP": "BCFV",
    "ELGO": "BCFY",
    "TTFU": "OECM",
    "FSNO": "",
    "FSNN": "",
    "PMRS": "LINK",
    "WC1D": "LINK",
    "PWTM": "LINK",
    "WMEH": "LINK",
    "PSHC": "LINK",
    "PSHL": "LINK",
    "BKCU": "LINK",
    "CDBS": "PVMO",
    "GOEW": "PVMO",
}


def cal(code):
    """
    Save calendar holidays
    Return dataframe
    """
    if os.path.exists(f"H:\\migration\\_cal\\{code}.csv"):
        data = pd.read_csv(f"H:\\migration\\_cal\\{code}.csv")
        data.set_index("Unnamed: 0", inplace=True)
        data.columns = ["holidays"]
    else:
        data = bbulkref(
            ["SPX Index"],
            "CALENDAR_NON_SETTLEMENT_DATES",
            option=[("CALENDAR_CODE", code)],
        )
        if not isinstance(data, pd.DataFrame):
            data = data.to_frame("holidays")
        else:
            data.columns = ["holidays"]
    return data


def ref(active):
    """
    Save futures information
    Return dict
    """
    if os.path.exists(f"H:\\migration\\_ref\\{active}.json"):
        with open(f"H:\\migration\\_ref\\{active}.json", "r") as f:
            data = json.load(f)
    else:
        market_ref_keys = [
            "CALENDAR_CODE", "CDR_SETTLE_CODE", "COUNTRY", "COUNTRY_ISO", "CURRENCY",
            "EXCH_CODE", "FUTURES_CATEGORY", "FUT_GEN_MONTH", "FUT_NOTL_BOND",
            "FUT_OPT_AVAIL", "FUT_OPT_TRADING", "FUT_TICK_SIZE", "FUT_TICK_VAL",
            "FUT_TRADING_HRS", "FUT_TRADING_UNITS", "FUT_VAL_PT", "ID_BB_GLOBAL",
            "ID_BB_UNIQUE", "ID_EXCH_SYMBOL", "MARKET_SECTOR_DES", "PX_DISP_FORMAT_TYP",
            "QUOTE_TYP", "QUOTE_UNITS", "SECURITY_TYP", "SECURITY_TYP2", "SETTLEMENT_TYPE",
            "TIME_ZONE_NUM", "UNDL_SPOT_TICKER",
        ]
        data = bref(active, market_ref_keys)
        data = data.iloc[0, :].to_dict()
    if active in ["SMA Comdty", "BOA Comdty"]:
        data["FUT_GEN_MONTH"] = "FHKNZ"
    elif active in ["S A Comdty"]:
        data["FUT_GEN_MONTH"] = "FHKNX"
    elif active in ["GCA Comdty"]:
        data["FUT_GEN_MONTH"] = "GJMQZ"
    elif active in ["SIA Comdty"]:
        data["FUT_GEN_MONTH"] = "HKNUZ"
    elif active in ["MOA Comdty"]:
        data["FUT_GEN_MONTH"] = "Z"
    elif active in ["LHA Comdty"]:
        data["FUT_GEN_MONTH"] = "GJMQVZ"
    elif active in ["CTA Comdty"]:
        data["FUT_GEN_MONTH"] = "HKNZ"
    elif active.split(" ")[0][:-1] in _synthetic_gen_forwards.keys():
        data["FUT_GEN_MONTH"] = "FGHJKMNQUVXZ"
    return data


def gen_fut_chain_syn_forward(active, source=None):
    parts = active.rpartition(" ")
    freq = parts[0][-1].upper()
    gen_years = [
        str(x.year)[-2:]
        for x in pd.date_range("2010-01-01", today() + dt.timedelta(days=365 * 8), freq="Y")
    ]
    if freq == "M":
        expiries = []
        fut_gen_months = "FGHJKMNQUVXZ"
        for y in gen_years:
            for exp in fut_gen_months:
                expiries.append("".join((exp, y)))
        if not source and (
            _synthetic_gen_forwards[parts[0][:-1]] is None
            or _synthetic_gen_forwards[parts[0][:-1]] == ""
        ):
            tickers = [f"{parts[0]} {exp} {parts[-1]}" for exp in expiries]
        else:
            tickers = [
                f"{parts[0]} {exp} {source or _synthetic_gen_forwards.get(parts[0][:-1], '')} {parts[-1]}"
                for exp in expiries
            ]
    elif freq == "Q":
        expiries = []
        fut_gen_quarters = [1, 2, 3, 4]
        for y in gen_years:
            for exp in fut_gen_quarters:
                expiries.append("".join((exp, y)))
        expiries = ["".join(x) for x in zip(fut_gen_quarters, cycle(gen_years))]
        tickers = [
            f"{parts[0]} {exp} {source or _synthetic_gen_forwards.get(parts[0][:-1], '')} {parts[-1]}"
            for exp in expiries
        ]
    elif freq == "Y":
        tickers = [
            f"{parts[0]} {exp} {source or _synthetic_gen_forwards.get(parts[0][:-1], '')} {parts[-1]}"
            for exp in gen_years
        ]
    else:
        raise ValueError(f"Ticker Frequency {freq} not known")
    tickers = pd.Series(tickers).to_frame("ticker")
    return tickers


def fut_ref(active, data=None):
    """
    Create futures contracts reference that includes ticker, month, year and expiry dates
    If expand is False, do not update
    Return dataframe
    """

    parts = active.rpartition(" ")
    generic = f"{parts[0][:-1]}1 {parts[-1]}"
    if parts[0][:-1] in _synthetic_gen_forwards.keys():
        contracts = gen_fut_chain_syn_forward(active)
    else:
        contracts = bbulkref(generic, ["FUT_CHAIN"], option=[("INCLUDE_EXPIRED_CONTRACTS", "Y")])
    if not isinstance(contracts, pd.DataFrame):
        contracts = contracts.to_frame("ticker")
    else:
        contracts.columns = ["ticker"]

    tickers = dictable(contracts)
    tickers = tickers(d=lambda ticker: contract2active_y_m(ticker))
    tickers = tickers(active=lambda d: d["active"])
    tickers = tickers(m=lambda d: d["m"])
    tickers = tickers(y=lambda d: d["y"])
    tickers = tickers - "d"
    tickers = tickers(con_dt=lambda m, y: dt.datetime(y, month_str2int[m], 1))
    tickers = tickers.sort("con_dt")
    tickers = tickers - ["con_dt", "active"]
    contracts = pd.DataFrame(tickers)
    if data is not None:
        contracts_d_data = contracts[~contracts["ticker"].isin(data["ticker"])]
    else:
        contracts_d_data = contracts
    new_contract = pd.DataFrame()
    if len(contracts_d_data) > 0:
        for idx, row in contracts_d_data.iterrows():
            if (
                data is not None
                and len(data.loc[(data["m"] == row["m"]) & (data["y"] == row["y"]), :]) > 0
            ):
                data.loc[(data["m"] == row["m"]) & (data["y"] == row["y"]), "ticker"] = row[
                    "ticker"
                ]
            else:
                new_contract = pd.concat(
                    [new_contract, contracts_d_data.loc[[idx], :]], axis=0, ignore_index=True
                )
    if len(new_contract) > 0:
        attributes = [
            "fut_dlv_dt_first", "fut_first_trade_dt", "fut_notice_first", "last_tradeable_dt",
        ]
        new_contract[attributes] = np.nan
        for idx, row in new_contract.iterrows():
            if row["ticker"].split(" ")[0][:-1] in _synthetic_gen_forwards.keys():
                new_contract.loc[idx, "fut_first_trade_dt"] = (
                    expiry_to_first_of_month(row["m"], row["y"]) - dt.timedelta(days=365)
                ) + pd.offsets.BMonthBegin(0)
                new_contract.loc[idx, "last_tradeable_dt"] = expiry_to_first_of_month(
                    row["m"], row["y"]
                ) + pd.offsets.BMonthEnd(0)
                new_contract.loc[idx, "fut_dlv_dt_first"] = expiry_to_first_of_month(
                    row["m"], row["y"]
                ) + pd.offsets.BMonthEnd(0)
                new_contract.loc[idx, "fut_notice_first"] = expiry_to_first_of_month(
                    row["m"], row["y"]
                ) + pd.offsets.BMonthEnd(0)
            else:
                try:
                    df = bref(row["ticker"], attributes)
                    new_contract.loc[idx, attributes] = pd.to_datetime(df.iloc[0, :])
                except Exception:
                    pass
        if len(new_contract) > 0:
            new_contract.dropna(inplace=True)
            new_contract = new_contract.sort_values("last_tradeable_dt")
            data = pd.concat([data, new_contract], ignore_index=True, axis=0)
    return data.sort_values("last_tradeable_dt").reset_index(drop=True)


def roll_day(ref, fut_ref, cal, fut_gen_month=None):
    """
    Calculate contracts last dates - min of last trading day, first notice day or
    first delivery day,
    and roll dates - how many days before the min of above
    Return dataframe
    """
    hol = cal.holidays
    if fut_gen_month is None:
        fut_gen_month = [x for x in ref["FUT_GEN_MONTH"]]
    else:
        fut_gen_month = [x for x in fut_gen_month]
    contracts = fut_ref.loc[fut_ref["m"].isin(fut_gen_month), :]
    res = dictable(contracts)
    res = res(
        last_t=lambda fut_notice_first, fut_dlv_dt_first, last_tradeable_dt: np.min(
            [fut_notice_first, fut_dlv_dt_first, last_tradeable_dt]
        )
    )
    res = res(t1=lambda last_t: bday_adj(last_t, -1, "p", hol))
    res = res(t2=lambda last_t: bday_adj(last_t, -2, "p", hol))
    res = res(t3=lambda last_t: bday_adj(last_t, -3, "p", hol))
    res = res(t4=lambda last_t: bday_adj(last_t, -4, "p", hol))
    res = res(t5=lambda last_t: bday_adj(last_t, -5, "p", hol))
    res = res(t10=lambda last_t: bday_adj(last_t, -10, "p", hol))
    res = res(t15=lambda last_t: bday_adj(last_t, -15, "p", hol))
    res = res(t20=lambda last_t: bday_adj(last_t, -20, "p", hol))
    return pd.DataFrame(res)


def _get_or_create_cell(active, row, field, update_price=True):
    try:
        c = get_cell(f"contracts_{field}", active=active, m=row["m"], y=row["y"])
    except ValueError:
        c = periodic_cell(
            function=bdh_update,
            ticker=row["ticker"],
            fields=[field],
            sdate=row["fut_first_trade_dt"],
            edate=row["last_t"],
            data=None,
            db=bbg_db(f"contracts_{field}"),
            active=active,
            m=row["m"],
            y=row["y"],
            period="1b",
            end_date=row["last_t"],
        )
        c.go()
    if c.ticker != row["ticker"]:
        c.ticker = row["ticker"]
        c.save()
    if update_price:
        c.go()
    return c


def fut_chain(
    active, t, curve_size, data=None, history_items=None, update_price=True, start_date=None,
):
    """
    Do three things in this function:
        - cut off back end contracts based on curve_size
        - change contracts tickers based on the latest bloomberg ticker (increase year digits)
        - update contracts open/high/low/close
    """
    if not isinstance(t, pd.DataFrame):
        t = t.data
    if history_items is None:
        history_items = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    if start_date is None:
        start_date = dt.datetime(1990, 1, 1)
    if t["last_t"].iloc[-1] > today():
        cur_idx = np.where(t["last_t"] > today())[0][0]
    else:
        cur_idx = t.index[-1]
    start_idx = np.where(t["last_t"] >= start_date)[0][0]
    end_idx = cur_idx + curve_size
    valid_t = t.loc[(t.index <= end_idx) & (t.index >= start_idx), :]
    valid_t.loc[:, history_items] = None

    if update_price:
        if data is None or len(data) == 0:
            for idx, row in valid_t.iterrows():
                for field in history_items:
                    c = _get_or_create_cell(active, row, field)
                    valid_t.loc[idx, field] = c.updated
        else:
            for idx, row in valid_t.iterrows():
                if row["ticker"] not in list(data["ticker"]):
                    for field in history_items:
                        c = _get_or_create_cell(active, row, field)
                        valid_t.loc[idx, field] = c.updated
                else:
                    valid_t.loc[idx, history_items] = data.loc[
                        data["ticker"] == row["ticker"], history_items
                    ].iloc[0]
                    for field in history_items:
                        if (
                            valid_t.loc[idx, field] is None
                            or (
                                isinstance(valid_t.loc[idx, field], float)
                                and np.isnan(valid_t.loc[idx, field])
                            )
                            or valid_t.loc[idx, field] < valid_t.loc[idx, "last_tradeable_dt"]
                        ):
                            c = _get_or_create_cell(active, row, field)
                            valid_t.loc[idx, field] = c.updated
    return valid_t


def crack_chain(
    active, t, curve_size, data=None, history_items=None, update_price=True,
    start_date=None, alt_active=None,
):
    """
    Do three things in this function:
        - cut off back end contracts based on curve_size
        - change contracts tickers based on the latest bloomberg ticker (increase year digits)
        - update contracts open/high/low/close
    """
    if not isinstance(t, pd.DataFrame):
        t = t.data
    if history_items is None:
        history_items = ["PX_LAST"]
    if start_date is None:
        start_date = dt.datetime(1990, 1, 1)
    if t["last_t"].iloc[-1] > today():
        if active == "COA Comdty":
            cur_idx = np.where(t["last_t"] > today())[0][0]
        else:
            cur_idx = np.where(t["last_t"] > today())[0][1]
    else:
        cur_idx = t.index[-1]
    start_idx = np.where(t["last_t"] >= start_date)[0][0]
    end_idx = cur_idx + curve_size
    valid_t = t.loc[(t.index <= end_idx) & (t.index >= start_idx), :]
    valid_t.loc[:, history_items] = None

    if alt_active is not None:
        tk1 = alt_active.partition(" ")[0]
        sec1 = alt_active.partition(" ")[-1]
        for idx in valid_t.index:
            valid_t.loc[
                idx, "ticker"
            ] = f"{tk1} {valid_t.loc[idx, 'm']}{str(int(valid_t.loc[idx, 'y']))[-2:]} {sec1}"
        active_ = alt_active.split(" ")[0] + " " + alt_active.split(" ")[-1]
    else:
        active_ = active

    if update_price:
        if data is None or len(data) == 0:
            for idx, row in valid_t.iterrows():
                for field in history_items:
                    c = _get_or_create_cell(active_, row, field)
                    valid_t.loc[idx, field] = c.updated
        else:
            for idx, row in valid_t.iterrows():
                if row["ticker"] not in list(data["ticker"]):
                    for field in history_items:
                        c = _get_or_create_cell(active_, row, field)
                        valid_t.loc[idx, field] = c.updated
                else:
                    valid_t.loc[idx, history_items] = data.loc[
                        data["ticker"] == row["ticker"], history_items
                    ].iloc[0]
                    for field in history_items:
                        if (
                            valid_t.loc[idx, field] is None
                            or (
                                isinstance(valid_t.loc[idx, field], float)
                                and np.isnan(valid_t.loc[idx, field])
                            )
                            or valid_t.loc[idx, field] <= valid_t.loc[idx, "last_tradeable_dt"] + BDay(2)
                        ):
                            c = _get_or_create_cell(active_, row, field)
                            valid_t.loc[idx, field] = c.updated
    return valid_t


def _get_or_create_sprd_cell(active, row, field, update_price=True):
    try:
        c = get_cell(
            f"spreads_{field}", active=active, m=row["m"], y=row["y"],
            far_m=row["far_m"], far_y=row["far_y"],
        )
    except ValueError:
        c = periodic_cell(
            function=bdh_update, ticker=row["ticker"], fields=[field],
            sdate=row["fut_first_trade_dt"], edate=row["last_t"], data=None,
            db=bbg_db(f"spreads_{field}"), active=active, m=row["m"], y=row["y"],
            far_m=row["far_m"], far_y=row["far_y"], period="1b", end_date=row["last_t"],
        )
        c.go()
    if c.ticker != row["ticker"]:
        c.ticker = row["ticker"]
        c.save()
    if update_price:
        c.go()
    return c


def sprd_chain(
    active, t, curve_size, data=None, fut_gen_month=None, history_items=None,
    update_price=True, start_date=None,
):
    """
    Create spread chain from fut_ref based on fut_gen_month
    Do two things in this function:
        - cut off back end contracts based on curve_size
        - update contracts open/high/low/close
    """
    if not isinstance(t, pd.DataFrame):
        t = t.data
    if history_items is None:
        history_items = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    if start_date is None:
        start_date = dt.datetime(2010, 1, 1)
    t_with_month = t.copy()
    if fut_gen_month is not None:
        if isinstance(fut_gen_month, str):
            fut_gen_month = [x for x in fut_gen_month]
        t_with_month = t_with_month.loc[t_with_month["m"].isin(fut_gen_month), :]
    t_with_month.reset_index(inplace=True, drop=True)
    if "Unnamed: 0" in t_with_month.columns:
        t_with_month = t_with_month.drop(["Unnamed: 0"], axis=1)
    for idx, row in t_with_month.iterrows():
        if idx < len(t_with_month) - 1:
            row1 = t_with_month.loc[idx + 1, :]
            lst = active.rpartition("A ")
            ys = str(row["y"])[-2:]
            ys1 = str(row1["y"])[-2:]
            if len(lst[0]) == 2 and lst[0][-1] == " ":
                t_with_month.loc[
                    idx, "ticker"
                ] = f"S:{lst[0][0]}_{lst[0][0]}_ {row['m']}{ys}-{row1['m']}{ys1} {lst[-1]}"
            else:
                t_with_month.loc[
                    idx, "ticker"
                ] = f"S:{lst[0]}{lst[0]} {row['m']}{ys}-{row1['m']}{ys1} {lst[-1]}"
            t_with_month.loc[idx, "far_m"] = row1["m"]
            t_with_month.loc[idx, "far_y"] = row1["y"]
    t_with_month.drop(t_with_month.index[-1], axis=0, inplace=True)
    if t["last_t"].iloc[-1] > today():
        cur_idx = np.where(t_with_month["last_t"] > today())[0][0]
    else:
        cur_idx = t.index[-1]
    start_idx = np.where(t_with_month["last_t"] >= start_date)[0][0]
    end_idx = cur_idx + curve_size + 1
    valid_t = t_with_month.loc[
        (t_with_month.index <= end_idx) & (t_with_month.index >= start_idx), :
    ]
    valid_t.loc[:, history_items] = None

    if update_price:
        if data is None or len(data) == 0:
            for idx, row in valid_t.iterrows():
                for field in history_items:
                    c = _get_or_create_sprd_cell(active, row, field)
                    valid_t.loc[idx, field] = c.updated
        else:
            for idx, row in valid_t.iterrows():
                if row["ticker"] not in list(data["ticker"]):
                    for field in history_items:
                        c = _get_or_create_sprd_cell(active, row, field)
                        valid_t.loc[idx, field] = c.updated
                else:
                    valid_t.loc[idx, history_items] = data.loc[
                        data["ticker"] == row["ticker"], history_items
                    ].iloc[0]
                    for field in history_items:
                        if (
                            valid_t.loc[idx, field] is None
                            or (
                                isinstance(valid_t.loc[idx, field], float)
                                and np.isnan(valid_t.loc[idx, field])
                            )
                            or valid_t.loc[idx, field] < valid_t.loc[idx, "last_tradeable_dt"]
                        ):
                            c = _get_or_create_sprd_cell(active, row, field)
                            valid_t.loc[idx, field] = c.updated
    return valid_t


def _get_or_create_xsprd_cell(active, row, field, update_price=True):
    try:
        c = get_cell(f"xspreads_{field}", active=active, m=row["m"], y=row["y"])
    except ValueError:
        c = periodic_cell(
            function=bdh_update, ticker=row["ticker"], fields=[field],
            sdate=row["fut_first_trade_dt"], edate=row["last_t"], data=None,
            db=bbg_db(f"xspreads_{field}"), active=active, m=row["m"], y=row["y"],
            near=row["near"], far=row["far"], period="1b", end_date=row["last_t"],
        )
        c.go()
    if c.ticker != row["ticker"]:
        c.ticker = row["ticker"]
        c.save()
    if update_price:
        c.go()
    return c


def xsprd_chain(
    active, near, far, curve_size, data=None, fut_gen_month=None, history_items=None,
    update_price=True, start_date=None, alt_active=None,
):
    """
    Create spread chain from two fut_refs based on fut_gen_month
    Do two things in this function:
        - cut off back end contracts based on curve_size
        - update contracts open/high/low/close
    Example:
        active = "S:QSCO Comdty"
        near = get_data("contracts", active="QSA Comdty", item="t")
        far = get_data("contracts", active="COA Comdty", item="t")
        xsprd_chain(
            active,
            near,
            far,
            curve_size=13,
            data=None,
            fut_gen_month=None,
            history_items=None,
            update_price=True,
            start_date=None,
            alt_active="FVQCM Index",
        )
    """
    if history_items is None:
        history_items = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    if start_date is None:
        start_date = dt.datetime(2010, 1, 1)
    t1 = near.copy()
    t2 = far.copy()
    if fut_gen_month is not None:
        if isinstance(fut_gen_month, str):
            fut_gen_month = [x for x in fut_gen_month]
        t1 = t1.loc[t1["m"].isin(fut_gen_month), :]
        t2 = t2.loc[t2["m"].isin(fut_gen_month), :]
    t_combine = t1.merge(t2, how="left", on=["m", "y"])
    t_with_month = pd.DataFrame(np.nan, index=near.index, columns=near.columns)
    t_with_month.reset_index(inplace=True, drop=True)
    if "Unnamed: 0" in t_with_month.columns:
        t_with_month = t_with_month.drop(["Unnamed: 0"], axis=1)
    ticker = active.rpartition(" ")[0]
    sector = active.rpartition(" ")[-1]
    for idx, _row in t_with_month.iterrows():
        if idx < len(t_with_month):
            if t_combine.loc[idx, "last_t_x"] <= t_combine.loc[idx, "last_t_y"]:
                t_with_month.loc[idx, :] = t_combine.loc[
                    idx,
                    [
                        "ticker_x", "m", "y", "fut_dlv_dt_first_x", "fut_first_trade_dt_x",
                        "fut_notice_first_x", "last_tradeable_dt_x", "last_t_x", "t1_x",
                        "t2_x", "t3_x", "t4_x", "t5_x", "t10_x", "t15_x", "t20_x",
                    ],
                ].values
            else:
                t_with_month.loc[idx, :] = t_combine.loc[
                    idx,
                    [
                        "ticker_y", "m", "y", "fut_dlv_dt_first_y", "fut_first_trade_dt_y",
                        "fut_notice_first_y",
                        "last_tradeable_dt_y", "last_t_y", "t1_y", "t2_y", "t3_y",
                        "t4_y", "t5_y", "t10_x", "t15_x", "t20_x",
                    ],
                ].values
            ys = str(t_combine.loc[idx, "y"])[-2:]
            if alt_active is not None:
                tk1 = alt_active.rpartition(" ")[0]
                sec1 = alt_active.rpartition(" ")[-1]
                t_with_month.loc[idx, "ticker"] = f"{tk1} {t_combine.loc[idx, 'm']}{ys} {sec1}"
            else:
                t_with_month.loc[
                    idx, "ticker"
                ] = f"{ticker} {t_combine.loc[idx, 'm']}{ys}-{t_combine.loc[idx, 'm']}{ys} {sector}"
    t_with_month = t_with_month.loc[t_with_month["last_t"].notnull(), :]
    t_with_month.reset_index(drop=True, inplace=True)
    t_with_month["y"] = t_with_month["y"].astype("int")
    if t_with_month["last_t"].iloc[-1] > today():
        cur_idx = np.where(t_with_month["last_t"] > today())[0][0]
    else:
        cur_idx = t_with_month.index[-1]
    start_idx = np.where(t_with_month["last_t"] > start_date)[0][0]
    end_idx = cur_idx + curve_size + 1
    valid_t = t_with_month.loc[
        (t_with_month.index <= end_idx) & (t_with_month.index >= start_idx), :
    ]
    valid_t["near"] = get_active(near["ticker"].iloc[1])
    valid_t["far"] = get_active(far["ticker"].iloc[1])
    valid_t.loc[:, history_items] = None

    if update_price:
        if data is None or len(data) == 0:
            for idx, row in valid_t.iterrows():
                for field in history_items:
                    c = _get_or_create_xsprd_cell(active, row, field)
                    valid_t.loc[idx, field] = c.updated
        else:
            for idx, row in valid_t.iterrows():
                if row["ticker"] not in list(data["ticker"]):
                    for field in history_items:
                        c = _get_or_create_xsprd_cell(active, row, field)
                        valid_t.loc[idx, field] = c.updated
                else:
                    valid_t.loc[idx, history_items] = data.loc[
                        data["ticker"] == row["ticker"], history_items
                    ].iloc[0]
                    for field in history_items:
                        if (
                            valid_t.loc[idx, field] is None
                            or (
                                isinstance(valid_t.loc[idx, field], float)
                                and np.isnan(valid_t.loc[idx, field])
                            )
                            or valid_t.loc[idx, field] < valid_t.loc[idx, "last_tradeable_dt"]
                        ):
                            c = _get_or_create_xsprd_cell(active, row, field)
                            valid_t.loc[idx, field] = c.updated
    return valid_t


def _roll(fut_chain, active, field, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures price,
    return generic price, price with roll adjustment, basis
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    basis = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        sdate = data.last_valid_index()
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            price_all_last = pd.DataFrame()
            for i in range(curve_size + 1):
                if idx + i < len(contracts):
                    price = get_data(
                        f"contracts_{field}",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                    if field == "PX_LAST":
                        price_last = price.copy()
                    else:
                        price_last = get_data(
                            "contracts_PX_LAST",
                            active=active,
                            y=contracts.loc[idx + i, "y"],
                            m=contracts.loc[idx + i, "m"],
                        )
                        price = price.reindex(price_last.index)
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                    price_last = pd.DataFrame(np.nan, index=price.index, columns=[field])
                price_all = pd.concat([price_all, price[field].to_frame(i)], axis=1)
                price_all_last = pd.concat(
                    [price_all_last, price_last["PX_LAST"].to_frame(i)], axis=1
                )
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
                price_all_last = price_all_last.loc[
                    (price_all_last.index >= sdate)
                    & (price_all_last.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
                price_all_last = price_all_last.loc[
                    (price_all_last.index > contracts.loc[idx - 1, roll_col])
                    & (price_all_last.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
                sprd = price_all_last.diff(axis=1)
                cols = sprd.columns[:-1]
                sprd.drop(0, axis=1, inplace=True)
                sprd.columns = cols
                sprd.loc[sprd.index[:-1], :] = np.nan
                basis = pd.concat([basis, sprd], axis=0)
                roll_price = roll_price[cols]
    basis.loc[basis.index[-1], :] = np.nan
    basis_cum = basis.loc[::-1, :].cumsum()[::-1]
    basis_cum.fillna(method="bfill", inplace=True)
    basis_cum.fillna(0, inplace=True)
    if len(roll_price) > 0:
        if data is None:
            return roll_price, roll_price + basis_cum, basis
        elif roll_price.index[0] > data.index[-1]:
            return (
                pd.concat([data, roll_price], axis=0),
                pd.concat([data, roll_price + basis_cum], axis=0),
                pd.concat([data, basis], axis=0),
            )
        else:
            return (
                pd.concat([data.iloc[:-1, :], roll_price], axis=0),
                pd.concat([data.iloc[:-1, :], roll_price + basis_cum], axis=0),
                pd.concat([data.iloc[:-1, :], basis], axis=0),
            )
    else:
        return data


def gen_price(fut_chain, active, field, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures price,
    without roll adjustment
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if idx + i < len(contracts):
                    price = get_data(
                        f"contracts_{field}",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                if price.empty:
                    print(
                        f"No contracts_{field} for {contracts.loc[idx + i, 'y']}"
                        f"{contracts.loc[idx + i, 'm']}"
                    )
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                price_all = pd.concat([price_all, price[field].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def gen_price_co(
    active, field, curve_size, roll_day=-1, data=None, start_date=None, shift_last_t=True
):
    """
    connect all futures contracts to create generic futures price,
    without roll adjustment
    use COA Comdty as fut_chain
    roll at the last trading day of month
    """
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2010, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    fut_chain_ori = get_data("contracts", active="COA Comdty", item="fut_chain")
    fut_chain = fut_chain_ori.copy()
    hol = get_data("cal", code="IP")["holidays"]
    if shift_last_t:
        fut_chain["last_t"] = [
            bday_adj(
                date=dt.datetime(x["y"], month_str2int[x["m"]], 1), t=roll_day - 1, holidays=hol
            )
            for _idx, x in fut_chain.iterrows()
        ]
    contracts = fut_chain.loc[fut_chain["last_t"] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, "last_t"] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if idx + i < len(contracts):
                    price = get_data(
                        f"contracts_{field}",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                price_all = pd.concat([price_all, price[field].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, "last_t"]),
                    :,
                ]
            else:
                if shift_last_t:
                    price_all = price_all.loc[
                        (price_all.index > contracts.loc[idx - 1, "last_t"])
                        & (price_all.index <= contracts.loc[idx, "last_t"]),
                        :,
                    ]
                else:
                    price_all = price_all.loc[
                        (price_all.index > roll_price.index[-1])
                        & (price_all.index <= contracts.loc[idx, "last_t"]),
                        :,
                    ]
                    if roll_day < 0 and contracts.loc[idx, "last_t"] <= today():
                        price_all = price_all.iloc[:roll_day, :]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def gen_price_spread(fut_chain, active, field, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures price,
    without roll adjustment
    Example:
        c = get_cell('spreads', active='COA Comdty', item='sprd_chain')
        b = gen_price_spread(fut_chain = c.data, active='COA Comdty', field='PX_LAST',
                    curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2010, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if idx + i < len(contracts):
                    price = get_data(
                        f"spreads_{field}",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                        far_y=contracts.loc[idx + i, "far_y"],
                        far_m=contracts.loc[idx + i, "far_m"],
                    )
                    if "LAST_PRICE" in price.columns:
                        price.rename(columns={"LAST_PRICE": "PX_LAST"}, inplace=True)
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                price_all = pd.concat([price_all, price[field].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def gen_price_xspread(fut_chain, active, field, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures price,
    without roll adjustment
    Example:
        c = get_cell('spreads', active='S:ENCO Comdty', item='xsprd_chain')
        b = gen_price_xspread(fut_chain=c.data, active='S:ENCO Comdty', field='PX_LAST',
                        curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2010, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if idx + i < len(contracts):
                    price = get_data(
                        f"xspreads_{field}",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                if price.empty:
                    price = pd.DataFrame(np.nan, index=price.index, columns=[field])
                price_all = pd.concat([price_all, price[field].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def roll_adj(gen_price, roll_spread, active, field):
    """
    connect all futures contracts to create generic futures price,
    with roll adjustment
    """
    basis_cum = roll_spread.loc[::-1, :].cumsum()[::-1]
    basis_cum.fillna(method="bfill", inplace=True)
    basis_cum.fillna(0, inplace=True)
    return gen_price + basis_cum


def roll_spread(fut_chain, active, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to calculate roll basis
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    basis = pd.DataFrame()
    if data is None or data.dropna().empty:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size + 1):
                if idx + i < len(contracts):
                    price = get_data(
                        "contracts_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=["PX_LAST"])
                price = price.drop_duplicates()
                if price.empty:
                    print(
                        f"No contracts_PX_LAST data for {contracts.loc[idx + i, 'm']}"
                        f"{contracts.loc[idx + i, 'y']}"
                    )
                    price = pd.DataFrame(np.nan, index=price.index, columns=["PX_LAST"])
                price_all = pd.concat([price_all, price["PX_LAST"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
                sprd = price_all.diff(axis=1)
                cols = sprd.columns[:-1]
                sprd.drop(0, axis=1, inplace=True)
                sprd.columns = cols
                sprd.loc[sprd.index[:-1], :] = np.nan
                basis = pd.concat([basis, sprd], axis=0)
                roll_price = roll_price[cols]
    basis.loc[basis.index[-1], :] = np.nan
    basis = basis[~basis.index.duplicated(keep="last")]
    if len(basis) > 0:
        if data is None or data.dropna().empty:
            return basis
        elif basis.index[0] > data.index[n]:
            return pd.concat([data, basis], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], basis], axis=0)
    else:
        return data


def roll_spread_co(active, curve_size, roll_day=3, data=None, start_date=None, shift_last_t=True):
    """
    connect all futures contracts to calculate roll basis
    """
    roll_price = pd.DataFrame()
    basis = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2010, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    fut_chain_ori = get_data("contracts", active="COA Comdty", item="fut_chain")
    fut_chain = fut_chain_ori.copy()
    if shift_last_t:
        hol = get_data("cal", code="IP")["holidays"]
        fut_chain["last_t"] = [
            bday_adj(
                date=dt.datetime(x["y"], month_str2int[x["m"]], 1), t=roll_day - 1, holidays=hol
            )
            for _idx, x in fut_chain.iterrows()
        ]
    contracts = fut_chain.loc[fut_chain["last_t"] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, "last_t"] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size + 1):
                if idx + i < len(contracts):
                    price = get_data(
                        "contracts_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                    if len(price) == 0:
                        c = get_cell(
                            "contracts_PX_LAST",
                            active=active,
                            y=contracts.loc[idx + i, "y"],
                            m=contracts.loc[idx + i, "m"],
                        ).go()
                        price = c.data
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=["PX_LAST"])
                price_all = pd.concat([price_all, price["PX_LAST"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, "last_t"]),
                    :,
                ]
            else:
                if shift_last_t:
                    price_all = price_all.loc[
                        (price_all.index > contracts.loc[idx - 1, "last_t"])
                        & (price_all.index <= contracts.loc[idx, "last_t"]),
                        :,
                    ]
                else:
                    price_all = price_all.loc[
                        (price_all.index > roll_price.index[-1])
                        & (price_all.index <= contracts.loc[idx, "last_t"]),
                        :,
                    ]
                    if roll_day < 0 and contracts.loc[idx, "last_t"] <= today():
                        price_all = price_all.iloc[:roll_day, :]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
                sprd = price_all.diff(axis=1)
                cols = sprd.columns[:-1]
                sprd.drop(0, axis=1, inplace=True)
                sprd.columns = cols
                sprd.loc[sprd.index[:-1], :] = np.nan
                basis = pd.concat([basis, sprd], axis=0)
                roll_price = roll_price[cols]
    basis.loc[basis.index[-1], :] = np.nan
    basis = basis[~basis.index.duplicated(keep="last")]
    if len(basis) > 0:
        if data is None:
            return basis
        elif basis.index[0] > data.index[n]:
            return pd.concat([data, basis], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], basis], axis=0)
    else:
        return data


def roll_spread_spread(fut_chain, active, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to calculate roll basis
    Example:
        c = get_cell('spreads', active='COA Comdty', item='sprd_chain')
        a = roll_spread_spread(fut_chain = c.data, active='COA Comdty',
                        curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    basis = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size + 1):
                if idx + i < len(contracts):
                    price = get_data(
                        "spreads_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                        far_y=contracts.loc[idx + i, "far_y"],
                        far_m=contracts.loc[idx + i, "far_m"],
                    )
                    if "LAST_PRICE" in price.columns:
                        price.rename(columns={"LAST_PRICE": "PX_LAST"}, inplace=True)
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=["PX_LAST"])
                price_all = pd.concat([price_all, price["PX_LAST"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
                sprd = price_all.diff(axis=1)
                cols = sprd.columns[:-1]
                sprd.drop(0, axis=1, inplace=True)
                sprd.columns = cols
                sprd.loc[sprd.index[:-1], :] = np.nan
                basis = pd.concat([basis, sprd], axis=0)
                roll_price = roll_price[cols]
    basis.loc[basis.index[-1], :] = np.nan
    basis = basis[~basis.index.duplicated(keep="last")]
    if len(basis) > 0:
        if data is None:
            return basis
        elif basis.index[0] > data.index[n]:
            return pd.concat([data, basis], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], basis], axis=0)
    else:
        return data


def roll_spread_xspread(fut_chain, active, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to calculate roll basis
    Example:
        c = get_cell('spreads', active='S:ENCO Comdty', item='xsprd_chain')
        a = roll_spread_spread(fut_chain = c.data, active='S:ENCO Comdty',
                        curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    basis = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size + 1):
                if idx + i < len(contracts):
                    price = get_data(
                        "xspreads_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                else:
                    price = pd.DataFrame(np.nan, index=price.index, columns=["PX_LAST"])
                price_all = pd.concat([price_all, price["PX_LAST"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
                sprd = price_all.diff(axis=1)
                cols = sprd.columns[:-1]
                sprd.drop(0, axis=1, inplace=True)
                sprd.columns = cols
                sprd.loc[sprd.index[:-1], :] = np.nan
                basis = pd.concat([basis, sprd], axis=0)
                roll_price = roll_price[cols]
    basis.loc[basis.index[-1], :] = np.nan
    basis = basis[~basis.index.duplicated(keep="last")]
    if len(basis) > 0:
        if data is None:
            return basis
        elif basis.index[0] > data.index[n]:
            return pd.concat([data, basis], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], basis], axis=0)
    else:
        return data


def gen_contract(fut_chain, active, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures tickers,
    Example:
        c = get_cell('contracts', active='COA Comdty', item='fut_chain')
        gen_contract(fut_chain=c.data, active='COA Comdty',
                curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if i == 0:
                    price = get_data(
                        "contracts_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                    if price.empty:
                        continue
                    price_ = price.copy()
                    price_.columns = ["ticker"]
                    price_["ticker"] = np.nan
                if idx + i < len(contracts):
                    price_["ticker"] = contracts.loc[idx + i, "ticker"]
                price_all = pd.concat([price_all, price_["ticker"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def gen_spread(fut_chain, active, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures tickers,
    Example:
        c = get_cell('spreads', active='COA Comdty', item='sprd_chain')
        gen_spread(fut_chain=c.data, active='COA Comdty',
                curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2010, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if i == 0:
                    price = get_data(
                        "spreads_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                        far_y=contracts.loc[idx + i, "far_y"],
                        far_m=contracts.loc[idx + i, "far_m"],
                    )
                    price_ = price.copy()
                    price_.columns = ["ticker"]
                    price_["ticker"] = np.nan
                if idx + i < len(contracts):
                    price_["ticker"] = contracts.loc[idx + i, "ticker"]
                price_all = pd.concat([price_all, price_["ticker"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def gen_xspread(fut_chain, active, curve_size, roll_day=3, data=None, start_date=None):
    """
    connect all futures contracts to create generic futures tickers,
    Example:
        c = get_cell('spreads', active='S:ENCO Comdty', item='xsprd_chain')
        gen_xspread(fut_chain=c.data, active='S:ENCO Comdty',
                curve_size=6, roll_day=3, data=None, start_date=None)
    """
    roll_col = f"t{str(roll_day)}"
    roll_price = pd.DataFrame()
    if data is None:
        if start_date is None:
            sdate = dt.datetime(2000, 1, 1)
        else:
            sdate = start_date
    else:
        data = data[~data.index.duplicated(keep="last")].sort_index()
        sdate = data.last_valid_index()
        n = data.index.get_loc(sdate) - len(data)
    contracts = fut_chain.loc[fut_chain[roll_col] >= sdate, :]
    contracts.reset_index(drop=True, inplace=True)
    for idx in contracts.index:
        if idx == 0 or (idx > 0 and contracts.loc[idx - 1, roll_col] < today()):
            price_all = pd.DataFrame()
            for i in range(curve_size):
                if i == 0:
                    price = get_data(
                        "xspreads_PX_LAST",
                        active=active,
                        y=contracts.loc[idx + i, "y"],
                        m=contracts.loc[idx + i, "m"],
                    )
                    price_ = price.copy()
                    price_.columns = ["ticker"]
                    price_["ticker"] = np.nan
                if idx + i < len(contracts):
                    price_["ticker"] = contracts.loc[idx + i, "ticker"]
                price_all = pd.concat([price_all, price_["ticker"].to_frame(i)], axis=1)
            if idx == 0:
                price_all = price_all.loc[
                    (price_all.index >= sdate) & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            else:
                price_all = price_all.loc[
                    (price_all.index > contracts.loc[idx - 1, roll_col])
                    & (price_all.index <= contracts.loc[idx, roll_col]),
                    :,
                ]
            if len(price_all) > 0:
                roll_price = pd.concat([roll_price, price_all], axis=0)
    if len(roll_price) > 0:
        if data is None:
            return roll_price
        elif roll_price.index[0] > data.index[n]:
            return pd.concat([data, roll_price], axis=0)
        else:
            return pd.concat([data.iloc[:n, :], roll_price], axis=0)
    else:
        return data


def synthetic_spread(active, y, m, far_y, far_m):
    p1 = get_data("contracts_PX_LAST", active=active, y=y, m=m)
    p2 = get_data("contracts_PX_LAST", active=active, y=far_y, m=far_m)
    d = p1 - p2
    return d.reindex(p1.index)


def cfd_table(ticker="cfd", data=None):
    """
    Construct CFD table with specific week and month
    """
    if data is None or len(data) == 0:
        start_date = dt.datetime(2010, 1, 1) - dt.timedelta(days=7)
    else:
        start_date = data["friday"].iloc[-1]
    end_date = today() + dt.timedelta(days=364)
    if start_date < end_date - dt.timedelta(days=28):
        dts_df = dwmy(start_date=start_date, end_date=end_date, m1=1, m2=2)
        dts_df["m1"] = dts_df["m1"].shift(5)
        dts_df["m2"] = dts_df["m2"].shift(5)
        dts_df["y1"] = dts_df["y1"].shift(5)
        dts_df["y2"] = dts_df["y2"].shift(5)
        dts_df.dropna(inplace=True)
        dts_df[["m1", "m2", "y1", "y2"]] = dts_df[["m1", "m2", "y1", "y2"]].astype("int64")
        res = dts_df.groupby(["week", "m1", "y1"], as_index=False).first()
        res = res.sort_values("monday")
        res.reset_index(inplace=True, drop=True)
        for idx, row in res.iterrows():
            res.loc[
                idx, "ticker"
            ] = f"EC{month_int2str[row['m1']]}{str(row['y1'])[-2:]}W{row['week']} PVMO Index"
    return res


def update_cfd(ticker, data=None):
    """
    Construct CFD price for specific week and month instead of generic week and month
    """
    month = month_str2int[ticker.split(" ")[0][2]]
    year = yy2year(int(ticker.split(" ")[0][3:5]))
    ticker_date = dt.datetime(year, month, 1) - pd.DateOffset(months=2)
    ticker_month = ticker_date.month
    ticker_year = ticker_date.year
    sloc = ticker.split(" ")[0].find("W") + 1
    ticker_week = int(ticker.split(" ")[0][sloc:])
    if data is None or len(data) == 0:
        if year > ticker_year and ticker_week > 30:
            start_date = pd.to_datetime(Week(ticker_year, ticker_week).monday() - dt.timedelta(42))
        else:
            start_date = pd.to_datetime(Week(year, ticker_week).monday() - dt.timedelta(42))
    else:
        start_date = data.index[-1]
    if year > ticker_year and ticker_week > 30:
        end_date = min(
            [
                pd.to_datetime(Week(ticker_year, ticker_week).monday() - BDay(1)),
                dt.datetime(ticker_year, ticker_month, 1) + relativedelta(day=31),
            ]
        )
    else:
        end_date = min(
            [
                pd.to_datetime(Week(year, ticker_week).monday() - BDay(1)),
                dt.datetime(ticker_year, ticker_month, 1) + relativedelta(day=31),
            ]
        )
    if data is None or len(data) == 0 or start_date <= today() <= end_date:
        res = dwmy(start_date=start_date, end_date=end_date + dt.timedelta(days=7))
        res["PX_LAST"] = np.nan
        res["ticker"] = np.nan
        res["monday"] = res["monday"].iloc[-1]
        res["friday"] = res["friday"].iloc[-1]
        res = res.iloc[:-5, :]
        res.loc[res["m1"] == res["m1"].iloc[-1], "ticker"] = [
            f"ECM1W{x + res['week'].max()} PVMO Index" if x < 0 else f"ECM1W{x} PVMO Index"
            for x in ticker_week - res.loc[res["m1"] == res["m1"].iloc[-1], "week"]
        ]
        res.loc[res["m1"] == last_month(res["m1"].iloc[-1]), "ticker"] = [
            f"ECM2W{x + res['week'].max()} PVMO Index" if x < 0 else f"ECM2W{x} PVMO Index"
            for x in ticker_week - res.loc[res["m1"] == last_month(res["m1"].iloc[-1]), "week"]
        ]
        if len(res.loc[res["ticker"].isnull(), :]) > 0:
            res.drop(res.loc[res["ticker"].isnull(), :].index, axis=0, inplace=True)
        price_dict = {}
        for i in res["ticker"].unique():
            price_dict[i] = get_cell(bbg_db("spot"), ticker=i, field="PX_LAST").go()
            temp_price = price_dict[i].data.reindex(res[res["ticker"] == i].index)
            res.loc[res["ticker"] == i, "PX_LAST"] = temp_price
    return res[["PX_LAST", "ticker", "monday", "friday"]].dropna()


if __name__ == "__main__":
    gen_price_co(
        active="GEBBM", field="PX_LAST", curve_size=3, roll_day=-1, data=None, start_date=None
    )
