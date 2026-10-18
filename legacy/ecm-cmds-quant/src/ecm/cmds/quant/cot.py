import datetime as dt
from functools import partial

import ecm.cmds.core.bbg as bbg
import ecm.cmds.core.cdr as cdr
import ecm.cmds.core.pyg as pyg
import ecm.cmds.core.talib as talib
import ecm.cmds.core.ticker as ticker
import numpy as np
import pandas as pd
from ecm.cmds.core.config import url
from pyg_cell import periodic_cell
from pyg_mongo import mongo_table


def cot_cell(ticker, active, item, period, start=None, fields=None):
    """
    delete existing cell, create new cot cell
    Example:
        cot_cell(ticker="IU34MHZA Index",
                 active="MOA Comdty",
                 item="MMLFO",
                 period="2n")
        c = pyg.get_cell(pyg.data_db().cot,
                         ticker="IU34MHZA Index",
                         active="MOA Comdty",
                         item="MMLFO")
        print(c)
    """
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    if start is None:
        start = dt.datetime(2000, 1, 1)
    if fields is None:
        fields = ["PX_LAST"]
    try:
        c = pyg.get_cell(db, ticker=ticker)
        db().inc(ticker=c.ticker).drop()
    except Exception:
        pass
    periodic_cell(
        function=bbg.bdh,
        ticker=ticker,
        fields=fields,
        sdate=start,
        edate=None,
        db=db,
        active=active,
        item=item,
        period=period,
    ).go()


def vwap(active):
    """
    Return 5d mean of vwap
    Example:
        active = "COA Comdty"
        df = vwap(active)
        print(df)
    """
    contracts = pyg.get_data("contracts", active=active, item="fut_chain")
    live = contracts.loc[contracts["last_t"] > cdr.CDR(active).bday_adj(cdr.today(), -3, adj="p")].iloc[0, :]
    closep = pyg.get_cell("contracts_PX_LAST", active=active, m=live["m"], y=live["y"]).go(0)
    highp = pyg.get_cell("contracts_PX_HIGH", active=active, m=live["m"], y=live["y"]).go(0)
    lowp = pyg.get_cell("contracts_PX_LOW", active=active, m=live["m"], y=live["y"]).go(0)
    volume = pyg.get_cell("contracts_PX_VOLUME", active=active, m=live["m"], y=live["y"]).go(0)
    close_ = closep.data.iloc[:, 0]
    high_ = highp.data.iloc[:, 0]
    low_ = lowp.data.iloc[:, 0]
    volume_ = volume.data.iloc[:, 0]
    volume_ = volume_.reindex(close_.index)
    vp = (((close_ + high_ + low_) / 3 * volume_).rolling(5).mean()) / (volume_.rolling(5).mean())
    df = pd.concat([close_, vp], axis=1)
    df.columns = ["PX_LAST", "VWAP"]
    return df


def vwap_lme(active):
    """
    Return 5d mean of vwap
    Example:
        df = vwap_lme(active="LMCADS03 LME Comdty")
        print(df)
    """
    closep = pyg.get_cell("spot", ticker=active, field="PX_LAST")
    if closep.edate is not None:
        closep.edate = None
    closep.go()
    highp = pyg.get_cell("spot", ticker=active, field="PX_HIGH")
    if highp.edate is not None:
        highp.edate = None
    highp.go()
    lowp = pyg.get_cell("spot", ticker=active, field="PX_LOW")
    if lowp.edate is not None:
        lowp.edate = None
    lowp.go()
    volume = pyg.get_cell("spot", ticker=active, field="PX_VOLUME")
    if volume.edate is not None:
        volume.edate = None
    volume.go()
    close_ = closep.data.iloc[:, 0]
    high_ = highp.data.iloc[:, 0]
    low_ = lowp.data.iloc[:, 0]
    volume_ = volume.data.iloc[:, 0]
    vp = (((close_ + high_ + low_) / 3 * volume_).rolling(5).mean()) / (volume_.rolling(5).mean())
    df = pd.concat([close_, vp], axis=1)
    df.columns = ["PX_LAST", "VWAP"]
    return df


def analysis(active, type, long, short, oi, long1=None, short1=None, vwap=None, ref=None, cta=None):
    """
    Analyze positioning, output is one row dataframe
    Example:
        active = "COA Comdty"
        type = "Fut"
        vw = vwap(active)
        ref = pyg.get_data("contracts", active=active, item="ref")
        db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
        long = pyg.get_data(db, active=active, item="MMLFO")
        short = pyg.get_data(db, active=active, item="MMSFO")
        oi = pyg.get_data(db, active=active, item="OIF")
        df = analysis(
            active=active,
            type="Fut",
            vwap=vw,
            ref=ref,
            long=long,
            short=short,
            oi=oi,
            long1=None,
            short1=None,
        )
        print(df)
    """
    cols = [
        "Net Position (MM)",
    ]

    long_ = long.copy()
    short_ = short.copy()
    oi_ = oi.copy()
    if active in ["NG NYMEX Swap", "NG NYMEX Penultimate", "NG ICE Henry Hub", "NG ICE Swap Dealers"]:
        long_ = long_ / 4
        short_ = short_ / 4
        oi_ = oi_ / 4
    net = long_ - short_

    if long1 is not None and short1 is not None:
        long1_ = long1.copy()
        short1_ = short1.copy()
        if active in ["NG NYMEX Swap", "NG NYMEX Penultimate", "NG ICE Henry Hub", "NG ICE Swap Dealers"]:
            long1_ = long1_ / 4
            short1_ = short1_ / 4
        net1 = long1_ - short1_
        cols = ["Net Position (NC)"] + cols

    if vwap is not None:
        weekdays = pd.bdate_range(vwap.index[0], vwap.index[-1], freq="B")
        vwap_ = vwap.reindex(weekdays, method="ffill")
        closep = vwap_["PX_LAST"]
        closep_w = closep.reindex(net.index)
        vwap_w = vwap_["VWAP"].reindex(net.index)
    else:
        vwap_w = pd.Series(0, index=net.index)
        closep_w = pd.Series(0, index=net.index)

    if ref is not None:
        vpp = float(ref["FUT_VAL_PT"])
    else:
        vpp = np.nan

    last_year_loc = np.where(net.index < dt.datetime(cdr.today().year, 1, 1))[0][-1]

    if ticker.is_active_contract(active):
        df = pd.DataFrame(0, index=[active.partition(" Comdty")[0] + " " + type], columns=cols)
    else:
        df = pd.DataFrame(0, index=[active + " " + type], columns=cols)

    if long1 is not None and short1 is not None:
        df["Net Position (NC)"] = net1.iloc[-1, 0]
    df["Net Position (MM)"] = net.iloc[-1, 0]
    df["% OI"] = (net / oi_).iloc[-1, 0]
    df["Weekly Price Change"] = (closep_w.diff())[-1] / closep_w[-1]
    df["Ref Week VWAP"] = vwap_w[-1]
    if cta is not None:
        df["CTA Change"] = cta[-1] - cta[-2]
    else:
        df["CTA Change"] = np.nan
    df["Weekly Delta Change"] = net.diff().iloc[-1, 0]
    df["Weekly change in longs"] = long_.diff().iloc[-1, 0]
    df["Weekly change in shorts"] = short_.diff().iloc[-1, 0]
    df["Weekly Delta Change in $m"] = net.diff().iloc[-1, 0] * closep_w[-1] * vpp / 1000000
    df["4w change of price"] = closep_w.pct_change(4).iloc[-1]
    df["4w change of net position"] = net.iloc[-1, 0] - net.iloc[-4, 0]
    df["YTD position change"] = net.iloc[-1, 0] - net.iloc[last_year_loc, 0]
    df["Long Short Ratio"] = (long_ / short_).iloc[-1, 0]
    df["Long Position"] = long_.iloc[-1, 0]
    df["Short Position"] = short_.iloc[-1, 0]
    df["Weekly OI change"] = oi_.diff().iloc[-1, 0]
    df["Net percentile"] = talib.percentilerank(net.iloc[-261:-1, 0], net.iloc[-1, 0])
    df["Net/OI percentile"] = talib.percentilerank((net / oi_).iloc[-261:-1, 0], (net / oi_).iloc[-1, 0])
    df["Long percentile"] = talib.percentilerank(long_.iloc[-261:-1, 0], long_.iloc[-1, 0])
    df["Short percentile"] = talib.percentilerank(short_.iloc[-261:-1, 0], short_.iloc[-1, 0])
    df["net change z score"] = net.diff().iloc[-1, 0] / net.diff().iloc[-52:, 0].std()
    _pct_chng = closep_w.pct_change(4).iloc[-1]
    mean_pct = closep_w.pct_change(4).rolling(52).mean().iloc[-1]
    std_pct = closep_w.pct_change(4).rolling(52).std().iloc[-1]
    df["4w price change z score"] = (_pct_chng - mean_pct) / std_pct
    df["4w delta change z score"] = net.diff(4).iloc[-1, 0] / net.diff(4).iloc[-52:, 0].std()
    df["net pos rank"] = talib.percentilerank(net.iloc[-53:-1, 0], net.iloc[-1, 0])
    df["net/oi pct rank"] = talib.percentilerank((net / oi_).iloc[-53:-1, 0], (net / oi_).iloc[-1, 0])
    df["YTD price change"] = closep_w[-1] - closep_w[last_year_loc]
    df["_thr_high"] = 0.9
    df["_thr_low"] = 0.1
    df["_thr_high8"] = 0.8
    df["_thr_low8"] = 0.2
    if (df["net pos rank"].values[0] > 0.8) and (df["net/oi pct rank"].values[0] > 0.8):
        df["_thr_net"] = 1
    elif (df["net pos rank"].values[0] < 0.2) and (df["net/oi pct rank"].values[0] < 0.2):
        df["_thr_net"] = -1
    else:
        df["_thr_net"] = 0
    df["_z_high"] = 1.5
    df["_z_low"] = -1.5
    if (closep_w.diff())[-1] > 0 and net.diff().iloc[-1, 0] < 0:
        df["_price_chg"] = 1
    elif (closep_w.diff())[-1] < 0 and net.diff().iloc[-1, 0] > 0:
        df["_price_chg"] = 0
    else:
        df["_price_chg"] = 0.5
    df["_last_update"] = net.index[-1].strftime("%Y-%m-%d")
    df.index.name = f"{(net.index[-1] - dt.timedelta(days=7)).strftime('%d-%b')} to {(net.index[-1]).strftime('%d-%b')}"
    return df.reset_index()


def analysis_mifid(active, type, long, short, oi, long1=None, short1=None, vwap=None, ref=None, cta=None):
    """
    For ENDEX and LME
    Analyze positioning, output is one row dataframe
    Example:
        active = "TZTA Comdty"
        type = "Fut"
        vw = vwap(active)
        ref = pyg.get_data("contracts", active=active, item="ref")
        db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
        long = pyg.get_data(db, active=active, item="IFLFO")
        short = pyg.get_data(db, active=active, item="IFSFO")
        oi = pyg.get_data(db, active=active, item="OIF")
        df = analysis_mifid(
            active=active,
            type="Fut",
            vwap=vw,
            ref=ref,
            long=long,
            short=short,
            oi=oi,
            long1=None,
            short1=None,
        )
        print(df)
    """
    cols = [
        "Net Position",
    ]

    net = long - short
    if long1 is not None and short1 is not None:
        net = (long + long1) - (short + short1)

    if vwap is not None:
        weekdays = pd.bdate_range(vwap.index[0], vwap.index[-1], freq="B")
        vwap_ = vwap.reindex(weekdays, method="ffill")
        closep = vwap_["PX_LAST"]
        closep_w = closep.reindex(net.index)
        vwap_w = vwap_["VWAP"].reindex(net.index)
    else:
        vwap_w = pd.Series(0, index=net.index)

    if ref is not None:
        vpp = float(ref["FUT_VAL_PT"])
    else:
        vpp = np.nan

    last_year_loc = np.where(net.index < dt.datetime(cdr.today().year, 1, 1))[0][-1]

    oi_ = oi.copy()
    oi_ = oi_.reindex(weekdays, method="ffill")
    oi_ = oi_.reindex(long.index)
    oi_.columns = ["PX_LAST"]

    df = pd.DataFrame(0, index=[active.partition(" Comdty")[0] + " " + type], columns=cols)
    df["Net Position"] = net.iloc[-1, 0]
    df["% OI"] = (net / oi_).iloc[-1, 0]
    df["Weekly Price Change"] = (closep_w.diff())[-1] / closep_w[-1]
    df["Ref Week VWAP"] = vwap_w[-1]
    if cta is not None:
        df["CTA Change"] = cta[-1] - cta[-2]
    df["Weekly Delta Change"] = net.diff().iloc[-1, 0]
    df["Weekly change in longs"] = long.diff().iloc[-1, 0]
    df["Weekly change in shorts"] = short.diff().iloc[-1, 0]
    df["Weekly Delta Change in $/EUR m"] = net.diff().iloc[-1, 0] * closep_w[-1] * vpp / 1000000
    df["4w change of price"] = closep_w.pct_change(4).iloc[-1]
    df["4w change of net position"] = net.iloc[-1, 0] - net.iloc[-4, 0]
    df["YTD position change"] = net.iloc[-1, 0] - net.iloc[last_year_loc, 0]
    df["Long Short Ratio"] = (long / short).iloc[-1, 0]
    df["Long Position"] = long.iloc[-1, 0]
    df["Short Position"] = short.iloc[-1, 0]
    df["Weekly OI change"] = oi_.diff().iloc[-1, 0]
    df["Net percentile"] = talib.percentilerank(net.iloc[-261:-1, 0], net.iloc[-1, 0])
    df["Net/OI percentile"] = talib.percentilerank((net / oi_).iloc[-261:-1, 0], (net / oi_).iloc[-1, 0])
    df["Long percentile"] = talib.percentilerank(long.iloc[-261:-1, 0], long.iloc[-1, 0])
    df["Short percentile"] = talib.percentilerank(short.iloc[-261:-1, 0], short.iloc[-1, 0])
    df["net change z score"] = net.diff().iloc[-1, 0] / net.diff().iloc[-208:, 0].std()
    _pct_chng = closep_w.pct_change(4).iloc[-1]
    mean_pct = closep_w.pct_change(4).rolling(52).mean().iloc[-1]
    std_pct = closep_w.pct_change(4).rolling(52).std().iloc[-1]
    df["4w price change z score"] = (_pct_chng - mean_pct) / std_pct
    df["4w delta change z score"] = net.diff(4).iloc[-1, 0] / net.diff(4).iloc[-208:, 0].std()
    df["net pos rank"] = talib.percentilerank(net.iloc[-53:-1, 0], net.iloc[-1, 0])
    df["net/oi pct rank"] = talib.percentilerank((net / oi_).iloc[-53:-1, 0], (net / oi_).iloc[-1, 0])
    df["YTD price change"] = closep_w[-1] - closep_w[last_year_loc]
    df["_thr_high"] = 0.9
    df["_thr_low"] = 0.1
    df["_thr_high8"] = 0.8
    df["_thr_low8"] = 0.2
    if (df["net pos rank"].values[0] > 0.8) and (df["net/oi pct rank"].values[0] > 0.8):
        df["_thr_net"] = 1
    elif (df["net pos rank"].values[0] < 0.2) and (df["net/oi pct rank"].values[0] < 0.2):
        df["_thr_net"] = -1
    else:
        df["_thr_net"] = 0
    df["_z_high"] = 1.5
    df["_z_low"] = -1.5
    if (closep_w.diff())[-1] > 0 and net.diff().iloc[-1, 0] < 0:
        df["_price_chg"] = 1
    elif (closep_w.diff())[-1] < 0 and net.diff().iloc[-1, 0] > 0:
        df["_price_chg"] = 0
    else:
        df["_price_chg"] = 0.5
    df["_last_update"] = net.index[-1].strftime("%Y-%m-%d")
    df.index.name = f"{(net.index[-1] - dt.timedelta(days=7)).strftime('%d-%b')} to {(net.index[-1]).strftime('%d-%b')}"
    return df.reset_index()


def position_change(df, thr):
    """
    Find 1w or 4w position change zscore above +1.5 or below -1.5
    Example:
        db = partial(mongo_table, table="data",
                     pk=["name", "sector", "market", "category", "region", "country", "source"],
                     db="reports", url=url)
        c = pyg.get_cell(db, name="cftc_cot")
        df = position_change(df=c.data, thr=1.5)
        print(df)
    """
    res = pd.DataFrame()
    for idx, row in df.iterrows():
        if row["4w delta change z score"] > thr or row["4w delta change z score"] < -thr or row["net change z score"] > thr or row["net change z score"] < -thr:
            if idx in [12, 13, 14]:
                pass
            else:
                res = pd.concat([res, df.loc[[idx], :]], axis=0, ignore_index=True)
    return res


def position_divergence(df):
    """
    Find weekly position change diverges from price change
    Example:
        db = partial(mongo_table, table="data",
                     pk=["name", "sector", "market", "category", "region", "country", "source"],
                     db="reports", url=url)
        c = pyg.get_cell(db, name="cftc_cot")
        df = position_divergence(df=c.data)
        print(df)
    """
    res = pd.DataFrame()
    for idx, row in df.iterrows():
        if row["_price_chg"] == 1 or row["_price_chg"] == 0:
            if idx in [12, 13, 14]:
                pass
            else:
                res = pd.concat([res, df.loc[[idx], :]], axis=0, ignore_index=True)
    return res


if __name__ == "__main__":
    db = partial(
        mongo_table,
        table="data",
        pk=["name", "sector", "market", "category", "region", "country", "source"],
        db="reports",
        url=url,
    )
    c = pyg.get_cell(db, name="cftc_cot")
    df = position_divergence(df=c.data)
    print(df)
