import datetime
import datetime as dt

import ecm.cmds.core.cdr as cdr
import ecm.cmds.core.pyg as pyg
import ecm.cmds.core.ticker as tk
import ecm.cmds.quant.ced as ced
import numpy as np
import pandas as pd
from ecm.atom.services import context
from ecm.cmds.core.config import default_atom_config


def today():
    return datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def get_contract_price_ticker(
    ticker, fields=None, sdate=None, edate=None, spread=False, go=None,
):
    """
    get open/high/low/close/volume/oi for one contract
    """
    if not fields:
        fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    sdate = sdate or datetime.datetime(1980, 1, 1)
    edate = edate or today()
    if tk.is_spread(ticker[1]) or spread:
        which_db = "spreads"
    else:
        which_db = "contracts"
    ticker_dict = tk.contract2active_y_m(ticker)
    df = pd.DataFrame()
    for i in fields:
        if go:
            _cell = pyg.get_cell(
                f"{which_db}_{i}", active=ticker_dict["active"],
                y=ticker_dict["y"], m=ticker_dict["m"],
            ).go(go)
            p = _cell.data
            p.columns = [x.upper() for x in p.columns]
            df = pd.concat([df, p], axis=1)
        else:
            try:
                p = pyg.get_data(
                    f"{which_db}_{i}", active=ticker_dict["active"],
                    y=ticker_dict["y"], m=ticker_dict["m"],
                )
                p.columns = [x.upper() for x in p.columns]
                df = pd.concat([df, p], axis=1)
            except Exception:
                p = pd.Series()
                p = p.to_frame(i.upper())
                df = pd.concat([df, p], axis=1)
    return df.loc[sdate:edate, :]


def get_contract_price(
    active, y, m, far_y=None, far_m=None, fields=None, sdate=None, edate=None, go=None,
):
    """get open/high/low/close/volume/oi for one contract
    get data using active, year and month instead of ticker"""
    if not fields:
        fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    sdate = sdate or datetime.datetime(1980, 1, 1)
    edate = edate or today()
    if far_y is not None and far_m is not None:
        df = pd.DataFrame()
        for i in fields:
            if go is not None:
                _cell = pyg.get_cell(
                    f"spreads_{i}", active=active, y=y, m=m, far_y=far_y, far_m=far_m
                ).go(go)
                p = _cell.data
                p.columns = [x.upper() for x in p.columns]
                df = pd.concat([df, p], axis=1)
            else:
                p = pyg.get_data(
                    f"spreads_{i}", active=active, y=y, m=m, far_y=far_y, far_m=far_m
                )
                p.columns = [x.upper() for x in p.columns]
                df = pd.concat([df, p], axis=1)
    else:
        if active[:2] == "S:":
            db_str = "xspreads"
        else:
            db_str = "contracts"
        df = pd.DataFrame()
        for i in fields:
            if go is not None:
                _cell = pyg.get_cell(f"{db_str}_{i}", active=active, y=y, m=m).go(go)
                p = _cell.data
                p.columns = [x.upper() for x in p.columns]
                df = pd.concat([df, p], axis=1)
            else:
                try:
                    p = pyg.get_data(f"{db_str}_{i}", active=active, y=y, m=m)
                    p.columns = [x.upper() for x in p.columns]
                    df = pd.concat([df, p], axis=1)
                except Exception:
                    p = pd.Series()
                    p = p.to_frame(i.upper())
                    df = pd.concat([df, p], axis=1)
    return df.loc[sdate:edate, :]


def get_fx_spot(ticker, fields=None, sdate=None, edate=None, go=None):
    if not fields:
        fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    sdate = sdate or datetime.datetime(1980, 1, 1)
    edate = edate or today()
    df = pd.DataFrame()
    for i in fields:
        if go is not None:
            _cell = pyg.get_data("spot", ticker=ticker, field=i).go(go)
            p = _cell.data
            p.columns = [x.upper() for x in p.columns]
            df = pd.concat([df, p], axis=1)
        else:
            p = pyg.get_data("spot", ticker=ticker, field=i)
            p.columns = [x.upper() for x in p.columns]
            df = pd.concat([df, p], axis=1)
    return df.loc[sdate:edate, :]


def get_lme(ticker, fields=None, sdate=None, edate=None, go=None):
    if not fields:
        fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    sdate = sdate or datetime.datetime(1980, 1, 1)
    edate = edate or today()
    df = pd.DataFrame()
    for i in fields:
        if go is not None:
            _cell = pyg.get_data("spot", ticker=ticker, field=i).go(go)
            p = _cell.data
            p.columns = [x.upper() for x in p.columns]
            df = pd.concat([df, p], axis=1)
        else:
            p = pyg.get_data("spot", ticker=ticker, field=i)
            p.columns = [x.upper() for x in p.columns]
            df = pd.concat([df, p], axis=1)
    return df.loc[sdate:edate, :]


def get_futures_price(active, fields=None, sdate=None, edate=None, seq=0, go=None):
    """get rolled futures price
    seq: sequence - which generic contract, default front
    return both unadjusted and roll adjusted price"""
    if not fields:
        fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
    df = pd.DataFrame()
    df_adj = pd.DataFrame()
    for i in fields:
        if go is not None:
            _cell1 = pyg.get_cell("contracts", active=active, item=f"{i}_gen").go(go)
            p1 = _cell1.data.loc[:, seq]
            _cell2 = pyg.get_cell("contracts", active=active, item=f"{i}_roll").go(go)
            p2 = _cell2.data.loc[:, seq]
        else:
            p1 = pyg.get_data("contracts", active=active, item=f"{i}_gen")[seq]
            p2 = pyg.get_data("contracts", active=active, item=f"{i}_roll")[seq]
        p1 = p1.to_frame(i.upper())
        p2 = p2.to_frame(i.upper())
        df = pd.concat([df, p1], axis=1)
        df_adj = pd.concat([df_adj, p2], axis=1)
    return df.loc[sdate:edate, :], df_adj.loc[sdate:edate, :]


def get_futures_ticker(active, sdate=None, edate=None, seq=0):
    c = pyg.get_cell("contracts", active=active, item="fut_chain")
    df = c.data[[
        "y", "m", "ticker", "fut_notice_first", "fut_dlv_dt_first",
        "last_tradeable_dt", "last_t", "t",
    ]]
    df = df.sort_values("t")
    df = df[["t", "ticker"]]
    df.set_index("t", inplace=True)
    df = df["ticker"]
    if seq > 0:
        df = df.shift(seq)
    return df[(df.index >= sdate)]


def get_basis(active="CLA Comdty", seq=0, go=None):
    """Calculate roll basis (front (old) - back (new) contract)
    Return reversed cumsum of all basis, this can be
    added to open/high/low/close to adjust roll difference"""
    c1 = pyg.get_cell("markets", active=active, item="t")
    if go is not None:
        c2 = pyg.get_cell("markets", active=active, item="LAST_PRICE").go(go)
        c2 = pyg.get_cell("markets", active=active, item="diff").go(go)
    else:
        c2 = pyg.get_cell("markets", active=active, item="diff")
    c3 = pyg.get_cell("markets", active=active, item="PX_LAST")
    data = c3.data.diff() - c2.data.reindex(c3.data.index)
    data = data.loc[:today() - dt.timedelta(days=1), :]
    data = data.shift(-1)
    roll_t = [x for x in c1.data.t if x < data.index[-1] and x > data.index[0]]
    try:
        data_roll = data.loc[roll_t, :]
    except Exception:
        weekdays = pd.bdate_range(start=data.index[0], end=data.index[-1])
        data = data.reindex(weekdays, fill_value=0)
        data_roll = data.loc[roll_t, :]
    data_roll = data_roll.reindex(data.index, fill_value=0)
    return data_roll.loc[::-1, :].cumsum()[::-1]


def get_active(ticker):
    if tk.is_spread(ticker):
        ticker_parts = ticker.split(" ")
        if (
            ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2):]
            == ticker_parts[0][2:-int(len(ticker_parts[0][2:]) / 2)]
        ):
            if ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2):][-1] == "_":
                return ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2):][0] + " A Comdty"
            else:
                return ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2):] + "A Comdty"
        else:
            if ticker_parts[0] in ["S:ENCO", "S:XBCL", "S:HOCL", "S:XBHO", "S:CODAT"]:
                return ticker_parts[0] + " Comdty"
            else:
                return ticker_parts[0][2:-int(len(ticker_parts[0][2:]) / 2)] + "A Comdty"
    else:
        try:
            return tk.as_active(ticker)
        except ValueError:
            ticker_parts = ticker.split(" ")
            if len(ticker_parts) > 3 or (
                len(ticker_parts) > 2 and len(ticker_parts[0]) > 2
                and ticker_parts[0][-1] in ["C", "P"]
            ):
                return get_active(f"{ticker_parts[0][:-1]} {ticker_parts[-1]}")
            else:
                return ticker


def get_contract_info(active="CLA Comdty", ticker=None):
    """return dict that contains basic information"""
    if active is None and ticker is not None:
        active = tk.as_active(ticker)
    return pyg.get_data("contracts", active=active, item="ref")


def adjust_holiday(d, method="p", active="CLA Comdty", go=0):
    """
    adjust a non-business day to prev/following bussiness date
    :Parameters:
    --------
    date : datetime.
    adj : None or p/f/m
        adjustment convention: 'prev/following/modified following'
    :Returns:
    -------
    dateime
        nearby business day
    """
    return cdr.CDR(active).bday_adj(d, 0, adj=method)


def add_days(d, days, method="p", active="CLA Comdty", go=0):
    return cdr.CDR(active).bday_adj(d, days, adj=method)


def holidays(active="CLA Comdty", go=0):
    return cdr.CDR(active).holidays


def is_bday(d, active="CLA Comdty", go=0):
    return cdr.CDR(active).is_bday(d)


def drange(active, sdate, edate):
    return cdr.CDR(active).drange(t0=sdate, t1=edate)


def get_contract_table(active="CLA Comdty", ticker=None, item="fut_chain", go=None):
    """
    get contract roll table
    item='fut_chain': get flat contracts
    item='sprd_chain.1': get spread contracts
    """
    if active is None and ticker is not None:
        active = tk.as_active(ticker)
    if item in ["fut_chain", "t"]:
        if active[:2] == "S:":
            which_db = "spreads"
            item = "xsprd_chain"
        else:
            which_db = "contracts"
    elif item in ["sprd_chain"]:
        which_db = "spreads"
    if go is not None:
        _cell = pyg.get_cell(which_db, active=active, item=item).go(go)
        fut_chain_data = _cell.data
    else:
        _cell = pyg.get_cell(which_db, active=active, item=item)
        fut_chain_data = _cell.data
    if item in ["fut_chain", "xsprd_chain", "t"]:
        fut_chain_data["far_m"] = None
        fut_chain_data["far_y"] = None
    fut_chain_data.rename(columns={"t3": "t"}, inplace=True)
    fut_chain_data.sort_values("t", inplace=True)
    fut_chain_data.reset_index(drop=True, inplace=True)
    if "near" in fut_chain_data.columns:
        if "t15" in fut_chain_data.columns:
            return fut_chain_data[[
                "ticker", "m", "y", "t", "t1", "t5", "t10", "t15", "t20",
                "fut_first_trade_dt", "last_t", "far_m", "far_y", "near", "far",
            ]]
        else:
            return fut_chain_data[[
                "ticker", "m", "y", "t", "t1", "t5", "t10", "fut_first_trade_dt",
                "last_t", "far_m", "far_y", "near", "far",
            ]]
    else:
        if "t15" in fut_chain_data.columns:
            return fut_chain_data[[
                "ticker", "m", "y", "t", "t1", "t5", "t10", "t15", "t20",
                "fut_first_trade_dt", "last_t", "far_m", "far_y",
            ]]
        else:
            return fut_chain_data[[
                "ticker", "m", "y", "t", "t1", "t5", "t10", "fut_first_trade_dt",
                "last_t", "far_m", "far_y",
            ]]


def get_spread_table(active="CLA Comdty", ticker=None, go=0):
    """get spread roll table"""
    if active is None and ticker is not None:
        active = tk.as_active(ticker)
    if go is not None:
        _cell = pyg.get_cell("spreads", active=active, item="sprd_chain").go(go)
        fut_chain_data = _cell.data
    else:
        fut_chain_data = pyg.get_data("spreads", active=active, item="sprd_chain")
    fut_chain_data.rename(columns={"t3": "t"}, inplace=True)
    fut_chain_data.sort_values("t", inplace=True)
    fut_chain_data.reset_index(drop=True, inplace=True)
    return fut_chain_data[[
        "ticker", "m", "y", "t", "t5", "fut_first_trade_dt", "last_t", "far_m", "far_y"
    ]]


def get_live_contract():
    fut_list = [
        "CLA Comdty", "COA Comdty", "XBA Comdty", "HOA Comdty", "QSA Comdty",
        "NGA Comdty", "MOA Comdty", "TZTA Comdty",
        "GCA Comdty", "SIA Comdty", "PLA Comdty", "PAA Comdty", "C A Comdty",
        "S A Comdty", "SMA Comdty", "BOA Comdty", "W A Comdty", "SBA Comdty",
        "CCA Comdty", "KCA Comdty", "CTA Comdty", "LCA Comdty", "FCA Comdty",
        "LHA Comdty", "KWA Comdty", "HGA Comdty",
    ]
    live_ticker = {}
    for i in fut_list:
        contracts = get_contract_table(active=i, item="fut_chain", go=None)
        live_contract = contracts.loc[contracts["t"] > dt.datetime.now(), :].iloc[0, :]
        live_ticker[i] = live_contract["ticker"]
    return live_ticker


def spread_base_ticker(ticker, live=True):
    """get tickers of two legs from spread ticker"""
    if ticker[1] == ":":
        ticker_parts = ticker.split(" ")
        base_ticker = ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2):]
        m1 = ticker_parts[1].split("-")[0]
        m2 = ticker_parts[1].split("-")[1]
        if live and base_ticker not in ["NG", "MO"]:
            m1 = m1[:-2] + m1[-1]
            m2 = m2[:-2] + m2[-1]
        base_ticker = base_ticker.replace("_", " ")
        return (
            base_ticker + m1 + " " + ticker_parts[-1],
            base_ticker + m2 + " " + ticker_parts[-1],
        )
    else:
        ticker_parts = ticker.split(" ")
        return (
            ticker_parts[0][:int(len(ticker_parts[0]) / 2)] + " " + ticker_parts[-1],
            ticker_parts[0][int(len(ticker_parts[0]) / 2):] + " " + ticker_parts[-1],
        )


def convert_spread_ticker(ticker, live=True, long_to_short=True):
    """convert ticker format from S:COCO to COXXCOXX"""
    ticker_parts = ticker.split(" ")
    if long_to_short:
        base_ticker = ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2):]
        m1 = ticker_parts[1].split("-")[0]
        m2 = ticker_parts[1].split("-")[1]
        if live:
            m1 = m1[:-2] + m1[-1]
            m2 = m2[:-2] + m2[-1]
        return base_ticker + m1 + base_ticker + m2 + " " + ticker_parts[-1]
    else:
        ticker1 = f"{ticker_parts[0][:int(len(ticker_parts[0])/2)]} {ticker_parts[1]}"
        ticker2 = f"{ticker_parts[0][-int(len(ticker_parts[0])/2):]} {ticker_parts[1]}"
        ticker_dict1 = decompose_ticker(ticker1)
        ticker_dict2 = decompose_ticker(ticker2)
        base_ticker = ticker_dict1["base_ticker"]
        asset_class = ticker_dict1["asset_class"]
        month1 = ticker_dict1["m"]
        month2 = ticker_dict2["m"]
        year1 = ticker_dict1["y"]
        year2 = ticker_dict2["y"]
        return "S:{:s}{:s} {:s}{:s}-{:s}{:s} {:s}".format(
            base_ticker, base_ticker, month1, str(year1)[-2:], month2,
            str(year2)[-2:], asset_class
        )


def get_spread_ticker(ticker, fut_gen_month="FGHJKMNQUVXZ"):
    ticker_dict = decompose_ticker(ticker)
    month = ticker_dict["m"]
    year = ticker_dict["y"]
    base_ticker = ticker_dict["base_ticker"]
    asset_class = ticker_dict["asset_class"]
    next_ticker_month = fut_gen_month[np.mod(fut_gen_month.index(month) + 1, len(fut_gen_month))]
    next_ticker_year = year if fut_gen_month.index(month) + 1 < len(fut_gen_month) else year + 1
    return "S:{:s}{:s} {:s}{:s}-{:s}{:s} {:s}".format(
        base_ticker, base_ticker, month, str(year)[-2:], next_ticker_month,
        str(next_ticker_year)[-2:], asset_class,
    )


def get_next_ticker(ticker, fut_gen_month="FGHJKMNQUVXZ"):
    ticker_dict = decompose_ticker(ticker)
    month = ticker_dict["m"]
    year = ticker_dict["y"]
    base_ticker = ticker_dict["base_ticker"]
    asset_class = ticker_dict["asset_class"]
    next_ticker_month = fut_gen_month[np.mod(fut_gen_month.index(month) + 1, len(fut_gen_month))]
    next_ticker_year = year if fut_gen_month.index(month) + 1 < len(fut_gen_month) else year + 1
    return base_ticker + next_ticker_month + str(next_ticker_year)[-1] + " " + asset_class


def decompose_ticker(ticker):
    return tk.decompose_ticker(ticker)


def decompose_active(active):
    parts = active.split("A ")
    return {"base_ticker": parts[0], "asset_class": parts[1]}


def active2generic(ticker, contract=None):
    """
    >>> assert as_generic(active = 'TYA Comdty') == 'TY Comdty'
    >>> assert as_generic('TYA Comdty', 3.0) == 'TY Comdty 3'
    >>> assert as_generic('L A Comdty', 2) == 'L Comdty 2'
    >>> assert as_generic(active='L A Comdty', contract=[1,2,3])
    == ['L Comdty 1', 'L Comdty 2', 'L Comdty 3']
    """
    return tk.as_generic(ticker, contract=contract)


def convert_fx(size, from_ccy="USD", to_ccy="USD"):
    """size is time series denominated in from_ccy, convert size to to_ccy"""
    if from_ccy[:3] in ["AUD", "EUR", "GBP", "NZD"] and to_ccy.upper() in ["USD", "DOLLAR"]:
        deno_ccy = get_fx_spot(ticker=from_ccy[:3] + "USD BGN Curncy", fields=["PX_LAST"])
        entry_price_deno = deno_ccy["PX_LAST"].reindex(size.index, method="ffill")
        return size * entry_price_deno
    elif to_ccy[:3] in ["AUD", "EUR", "GBP", "NZD"] and from_ccy.upper() in ["USD", "DOLLAR"]:
        deno_ccy = get_fx_spot(ticker=to_ccy[:3] + "USD BGN Curncy", fields=["PX_LAST"])
        entry_price_deno = deno_ccy["PX_LAST"].reindex(size.index, method="ffill")
        return size / entry_price_deno
    elif from_ccy[:3] not in ["USD", "DOLLAR"] and to_ccy.upper() in ["USD", "DOLLAR"]:
        try:
            deno_cur = get_fx_spot(ticker="USD" + from_ccy[:3] + " BGN Curncy", fields=["PX_LAST"])
        except Exception:
            deno_cur = get_fx_spot(ticker="USD" + from_ccy[:3] + " Curncy", fields=["PX_LAST"])
        entry_price_deno = deno_cur["PX_LAST"].reindex(size.index, method="ffill")
        return size / entry_price_deno
    elif to_ccy[:3] not in ["USD", "DOLLAR"] and from_ccy.upper() in ["USD", "DOLLAR"]:
        deno_cur = get_fx_spot(ticker="USD" + to_ccy[:3] + " BGN Curncy", fields=["PX_LAST"])
        entry_price_deno = deno_cur["PX_LAST"].reindex(size.index, method="ffill")
        return size * entry_price_deno
    else:
        return size


def get_positions(substrategy=None, strategy="SYS"):
    positions = ced.sys_position(substrategy=substrategy)
    return positions


def rvx_data(generic="CL COMDTY 1", attribute="eac_exec", sdate=None, edate=None):
    if sdate is None:
        sdate = datetime.datetime.now()
    if edate is None:
        edate = datetime.datetime.now()
    with context(default_atom_config) as services:
        rvx = services.rvx
        sr_eac = rvx.query_series(
            ticker=generic, attribute=attribute, start_date=sdate, end_date=edate
        )
        return sr_eac


if __name__ == "__main__":
    unadjusted_series, adj_series = get_futures_price(
        active="HPYA Comdty", fields=["PX_LAST"], sdate="2024-01-01", edate="2025-02-01"
    )
    print(unadjusted_series)
