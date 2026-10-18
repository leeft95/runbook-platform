import pandas as pd
import numpy as np
import datetime as dt
import sys
from scipy import stats
from pandas.tseries.offsets import BDay
import plotly.graph_objects as go
from functools import partial
from dateutil.relativedelta import relativedelta

import ecm.cmds.data as dv
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.ticker as tk
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.talib as talib
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path, output_path, html_path, macro_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
from pathlib import Path
from ecm.atom.parse import FutureTicker
from pyg_mongo import *
from pyg_cell import *


test_email = None  # "ltrindade"
send_to_macro = macro_group
send_to_oil = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
send_to_gas = [
    "jmcphillips@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "caitcheson@elementcapital.com",
]
if test_email:
    send_to_gas = send_to_oil = send_to_macro = [test_email]
report_name = "Open Interest"
file_name = "open_interest"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"
cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"
cc_json_folder = f"{output_path}\\json\\cross_cmds"
cc_pdf_folder = f"{output_path}\\pdf\\cross_cmds"

fut_dict = {
    "Oil": ["CO1 Comdty", "CL1 Comdty", "EN1 Comdty", "HO1 Comdty", "QS1 Comdty", "XB1 Comdty"],
    "Gas": ["FN1 Comdty", "TZT1 Comdty", "NG1 Comdty", "MO1 Comdty"],
    "PM": ["GC1 Comdty", "AUA1 Comdty", "SI1 Comdty", "PL1 Comdty", "PA1 Comdty"],
    "Crypto": ["BTC1 Curncy", "DCR1 Curncy"],
    "BM": ["HG1 Comdty", "LP1 Comdty", "LA1 Comdty", "LX1 Comdty", "LN1 Comdty"],
    "CBM": ["CU1 Comdty", "AA1 Comdty", "ZNA1 Comdty", "XII1 Comdty"],
    "GR": ["C 1 Comdty", "W 1 Comdty", "S 1 Comdty", "BO1 Comdty", "SM1 Comdty"],
    "SFT": ["CC1 Comdty", "QC1 Comdty", "KC1 Comdty", "SB1 Comdty", "DF1 Comdty"],
}


def get_data_zscore():
    df = pd.DataFrame()
    sdate = dt.datetime(2018, 1, 1)
    edate = today() - BDay(1)
    columns = [
        "Days to expiry", "Total OI", "1y percentile",
        "1d chg", "1d chg zscore", "1d_mean", "1d_std", "1d price chg %", "1dp_mean", "1dp_std",
        "3d chg", "3d chg zscore", "3d_mean", "3d_std", "3d price chg %", "3dp_mean", "3dp_std",
        "5d chg", "5d chg zscore", "5d_mean", "5d_std", "5d price chg %", "5dp_mean", "5dp_std",
        "20d chg zscore", "20d chg", "20d_mean", "20d_std", "20d price chg %", "20dp_mean", "20dp_std",
        "thr1", "thr2",
    ]
    chart_base_path = convert_path_to_linux(f"{html_path}\\cross_cmds\\oi\\")
    for key, val in fut_dict.items():
        df1 = pd.DataFrame(np.nan, index=[f"{key} Total Lots"] + val, columns=columns)
        leg_ois = {}
        oil_agg_oi = pd.DataFrame()
        look_back = 252 * 2
        percentile_look_back = 252
        periods = [1, 3, 5, 20]
        for i in val:
            oi = bbg.bdh(i, ["FUT_AGGTE_OPEN_INT"], sdate=sdate, edate=today())
            active = i.replace("1", "A")
            exp_date = bbg.bref(active, ["LAST_TRADEABLE_DT", "FUT_DLV_DT_FIRST"])
            exp_date = pd.to_datetime(exp_date.iloc[0, :]).min()
            price = bbg.bdh(active, ["PX_LAST"], sdate=sdate, edate=today() - BDay(1))
            price = price["PX_LAST"]
            if i == "CO1 Comdty":
                edate = oi.index[-1]
            if i in ["TZT1 Comdty", "FN1 Comdty"]:
                oi = oi["FUT_AGGTE_OPEN_INT"] * 0.25
            elif i in ["QS1 Comdty"]:
                oi = oi["FUT_AGGTE_OPEN_INT"] * 0.745
            elif i in ["DCR1 Curncy"]:
                btc_price = bbg.bdh("BTC1 Curncy", ["PX_LAST"], sdate=sdate, edate=today() - BDay(1))
                btc_price = btc_price["PX_LAST"]
                oi = (oi["FUT_AGGTE_OPEN_INT"] * 50 * price[-1]) / btc_price[-1]
            else:
                oi = oi["FUT_AGGTE_OPEN_INT"]
            if i != "MO1 Comdty":
                leg_ois[i] = oi
            if key == "Oil":
                oil_agg_oi = pd.concat([oil_agg_oi, oi], axis=1).sort_index()
            oi_vd_px_fig = oi_total(i[:-7], i, dt.datetime(today().year - 1, today().month, today().day))
            chart_link = Path(chart_base_path) / f"{i.replace(' ', '_')}_oi_vs_price.html"
            chart_link.parent.mkdir(parents=True, exist_ok=True)
            table.figures_to_html([oi_vd_px_fig], str(chart_link), task_name=report_name)
            df1.loc[i, "Total OI"] = oi.iloc[-1]
            df1.loc[i, "Days to expiry"] = (exp_date - today()).days
            df1.loc[i, "1y percentile"] = talib.percentilerank(
                oi.iloc[-percentile_look_back:-2].values, oi.iloc[-1])
            oi_chgs = {p: oi.diff(p) for p in periods}
            price_chgs = {p: price.diff(p) / price.shift(p) for p in periods}
            for p in periods:
                chg = oi_chgs[p]
                prchg = price_chgs[p]
                mu = chg.rolling(window=look_back).mean().iloc[-1]
                sig = chg.rolling(window=look_back).std().iloc[-1]
                df1.loc[i, f"{p}d chg zscore"] = (chg.iloc[-1] - mu) / sig
                df1.loc[i, f"{p}d chg"] = chg.iloc[-1]
                df1.loc[i, f"{p}d_mean"] = mu
                df1.loc[i, f"{p}d_std"] = sig
                df1.loc[i, f"{p}d price chg %"] = prchg.iloc[-1]
                df1.loc[i, f"{p}dp_mean"] = prchg[-look_back:].mean()
                df1.loc[i, f"{p}dp_std"] = prchg[-look_back:].std()
            df1.loc[i, "thr1"] = 0.9
            df1.loc[i, "thr2"] = 0.1
            df1.loc[i, "_last_update"] = oi.index[-1].strftime("%Y-%m-%d")
            plot_url = f'<a href="{chart_link}" target="_blank">{i}</a>'
            df1.loc[i, "Name_"] = plot_url
            if "Lots" in i:
                df1.loc[i, "Name_"] = i
        total_oi = pd.concat(leg_ois.values(), axis=1).sum(axis=1)
        oi_chgs_tot = {p: total_oi.diff(p) for p in periods}
        lots_idx = f"{key} Total Lots"
        df1.loc[lots_idx, "thr1"] = 0.9
        df1.loc[lots_idx, "thr2"] = 0.1
        df1.loc[lots_idx, "_last_update"] = total_oi.index[-1].strftime("%Y-%m-%d")
        for p in (1, 3, 5, 20):
            chg_tot = oi_chgs_tot[p]
            assert (chg_tot != total_oi).any(), "chg_tot and total_oi should differ!"
            mu_tot = chg_tot.rolling(window=look_back).mean()
            sig_tot = chg_tot.rolling(window=look_back).std()
            z_score = ((chg_tot - mu_tot) / sig_tot).iloc[-1]
            chg_ = chg_tot.iloc[-1]
            df1.loc[lots_idx, f"{p}d chg zscore"] = z_score
            df1.loc[lots_idx, f"{p}d chg"] = chg_
            if key == "Oil":
                df1.loc[f"{key} Agg", f"{p}d chg zscore"] = z_score
                df1.loc[f"{key} Agg", f"{p}d chg"] = chg_
        if key == "Oil":
            df1.loc[f"{key} Agg", "Total OI"] = total_oi.iloc[-1]
            df1.loc[f"{key} Agg", "thr1"] = 0.9
            df1.loc[f"{key} Agg", "thr2"] = 0.1
            df1.loc[f"{key} Agg", "1y percentile"] = talib.percentilerank(
                total_oi.iloc[-percentile_look_back:-2].values, total_oi.iloc[-1])
        df = pd.concat([df, df1], axis=0)
    df.index.name = "Name"
    df.reset_index(inplace=True)
    return df, edate


def oi_chart(cmdty, cmdty2):
    active = tk.generic2active(cmdty + " Comdty")
    contracts = pyg.get_data("contracts", active=active, item="fut_chain")
    if cmdty[:3] in ["AGD", "ABE"]:
        contracts["last_t"] = contracts["last_t"].shift(1)
        contracts["last_tradeable_dt"] = contracts["last_tradeable_dt"].shift(1)
        contracts["t1"] = contracts["t1"].shift(1)
        contracts["t3"] = contracts["t3"].shift(1)
    contracts = contracts.loc[contracts["last_t"] >= dt.datetime(2018, 1, 1), :]
    contracts.reset_index(inplace=True, drop=True)
    oi_total = pd.DataFrame()
    oi_inv_total = pd.DataFrame()
    inv_sdate = dt.datetime(2017, 1, 1)
    if cmdty[:2] == "HG":
        inv = bbg.bdh("COMXCOPR Index", ["PX_LAST"], inv_sdate, today())
        inv = inv * 2000 / 25000
    elif cmdty[:2] == "GC":
        inv = bbg.bdh("COMXGOLD Index", ["PX_LAST"], inv_sdate, today())
        inv = inv / 100
    elif cmdty[:2] == "SI":
        inv = bbg.bdh("COMXSILV Index", ["PX_LAST"], inv_sdate, today())
        inv = inv / 5
    elif cmdty[:2] == "PL":
        inv = bbg.bdh("COMXPTCT Index", ["PX_LAST"], inv_sdate, today())
        inv = inv / 50
    elif cmdty[:2] == "PA":
        inv = bbg.bdh("COMXTCPD Index", ["PX_LAST"], inv_sdate, today())
        inv = inv / 100
    else:
        inv = pd.DataFrame()
    live_added = 0
    for idx, row in contracts.iterrows():
        ticker = row["ticker"]
        if ticker.startswith("LX"):
            ticker = FutureTicker(ticker, row["last_tradeable_dt"]).outright(format=2)
        try:
            try:
                c = pyg.get_cell("contracts_OPEN_INT", active=active, m=row["m"], y=row["y"]).go()
            except:
                db = partial(
                    mongo_table,
                    db="bbg",
                    table=f"contracts_OPEN_INT",
                    url="mongodb://nypmdevlo25v:27017/",
                    pk=["active", "m", "y"],
                )
                c = periodic_cell(
                    function=bbg.bdh_update,
                    ticker=ticker,
                    fields=["OPEN_INT"],
                    sdate=row["fut_first_trade_dt"],
                    edate=row["last_t"],
                    data=None,
                    db=db,
                    active=active,
                    m=row["m"],
                    y=row["y"],
                    period="5n",
                    end_date=row["last_t"],
                )
                c.go()
            oi = c.load().data
        except TypeError:
            tk_dict = tk.decompose_ticker(ticker)
            oi = bbg.bdh(
                f"{tk_dict['base_ticker']}{tk_dict['m']}{str(tk_dict['y'])[-2:]} Comdty",
                ["OPEN_INT"],
                sdate=today() - dt.timedelta(364),
                edate=today(),
            )
        if len(oi) < 101:
            continue
        oi.fillna(method="ffill", inplace=True)
        oi = oi.iloc[-101:, :]
        oi_ = oi.copy()
        oi["days"] = np.busday_count(
            oi.index.values.astype("datetime64[D]"),
            pd.DatetimeIndex([row["last_t"]]).values.astype("datetime64[D]"),
        )
        oi.set_index("days", inplace=True)
        try:
            oi.columns = [ticker.split(" Comdty")[0]]
        except:
            print("error")
        if len(oi_total.columns) > 0:
            oi = oi.reindex(oi_total.index)
            oi.fillna(method="bfill", inplace=True)
        oi_total = pd.concat([oi_total, oi], axis=1)
        if len(inv) > 0:
            inv_ = inv.reindex(oi_.index).fillna(method="ffill")
            oi_inv = oi_.iloc[:, 0] / inv_.iloc[:, 0]
            try:
                oi_inv = oi_inv.to_frame(ticker.split(" Comdty")[0])
            except:
                print("error")
            oi_inv["days"] = np.busday_count(
                oi_inv.index.values.astype("datetime64[D]"),
                pd.DatetimeIndex([row["last_t"]]).values.astype("datetime64[D]"),
            )
            oi_inv.set_index("days", inplace=True)
            if len(oi_inv_total.columns) > 0:
                oi_inv = oi_inv.reindex(oi_inv_total.index)
                oi_inv.fillna(method="bfill", inplace=True)
            oi_inv_total = pd.concat([oi_inv_total, oi_inv], axis=1)
        if idx > 1 and contracts.loc[idx - 1, "last_t"] >= today():
            live_added += 1
        if live_added == 1:
            last_date = c.load().data.index[-1]
        elif cmdty in ["DAT1", "AFY1", "MUC1"] and live_added == 4:
            break
        elif live_added == 2 and cmdty not in ["DAT1", "AFY1", "MUC1"]:
            break
    if cmdty not in ["DAT1", "AFY1", "MUC1"]:
        if len(oi_total.columns) < 14:
            print(f"Not enough contracts found for {cmdty}, only {len(oi_total.columns)}")
            min_cols = len(oi_total.columns)
        else:
            min_cols = 14
        oi_min = oi_total.iloc[:, -14:-2].min(axis=1)
        oi_max = oi_total.iloc[:, -14:-2].max(axis=1)
        oi_avg = oi_total.iloc[:, -14:-2].mean(axis=1)
        newcharting = oi_total.copy().iloc[:, -4:]
        newcharting["min"] = oi_min
        newcharting["max"] = oi_max
        newcharting["avg"] = oi_avg
    else:
        oi_min = oi_total.iloc[:, -16:-4].min(axis=1)
        oi_max = oi_total.iloc[:, -16:-4].max(axis=1)
        oi_avg = oi_total.iloc[:, -16:-4].mean(axis=1)
        newcharting = oi_total.copy().iloc[:, -5:]
        newcharting["min"] = oi_min
        newcharting["max"] = oi_max
        newcharting["avg"] = oi_avg

    if cmdty in ["DAT1", "AFY1", "MUC1"]:
        trace = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 0],
            connectgaps=True,
            name=newcharting.columns[0],
        )
        trace1 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 1],
            connectgaps=True,
            name=newcharting.columns[1],
        )
        trace2 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 2],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting.columns[2],
        )
        trace3 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 3],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting.columns[3],
        )
        trace4 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 4],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting.columns[4],
        )
        tracemin = go.Scatter(
            x=newcharting.index,
            y=newcharting["min"],
            fill=None,
            opacity=0.1,
            showlegend=False,
            line=dict(color="rgb(255, 255, 204)"),
        )
        traceaverage = go.Scatter(
            x=newcharting.index,
            y=newcharting["avg"],
            name="average of last 12 contracts",
            line=dict(color=("rgb(22, 96, 167)"), width=4, dash="dash"),
        )
        tracerange = go.Scatter(
            x=newcharting.index,
            y=newcharting["max"],
            fill="tonexty",
            mode="lines",
            line=dict(color="rgb(255, 255, 204)"),
            name="Range",
        )
        data = [trace, trace1, trace2, trace3, trace4, traceaverage, tracemin, tracerange]
    else:
        trace = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 0],
            connectgaps=True,
            name=newcharting.columns[0],
        )
        trace1 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 1],
            connectgaps=True,
            name=newcharting.columns[1],
        )
        trace2 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 2],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting.columns[2],
        )
        trace3 = go.Scatter(
            x=newcharting.index,
            y=newcharting.iloc[:, 3],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting.columns[3],
        )
        tracemin = go.Scatter(
            x=newcharting.index,
            y=newcharting["min"],
            fill=None,
            opacity=0.1,
            showlegend=False,
            line=dict(color="rgb(255, 255, 204)"),
        )
        traceaverage = go.Scatter(
            x=newcharting.index,
            y=newcharting["avg"],
            name="average of last 12 contracts",
            line=dict(color=("rgb(22, 96, 167)"), width=4, dash="dash"),
        )
        tracerange = go.Scatter(
            x=newcharting.index,
            y=newcharting["max"],
            fill="tonexty",
            mode="lines",
            line=dict(color="rgb(255, 255, 204)"),
            name="Range",
        )
        data = [trace, trace1, trace2, trace3, traceaverage, tracemin, tracerange]
    layout = go.Layout(
        xaxis=dict(autorange="reversed"),
        title=f'{cmdty[:-1]} Front {"2" if cmdty not in ["DAT1", "AFY1", "MUC2"] else "3"} contracts - latest OI on {last_date.strftime("%Y-%m-%d")}',
        width=900,
        height=600,
    )
    fig = go.Figure(data=data, layout=layout)
    if len(inv) > 0:
        oi_inv_min = oi_inv_total.iloc[:, -14:-2].min(axis=1)
        oi_inv_max = oi_inv_total.iloc[:, -14:-2].max(axis=1)
        oi_inv_avg = oi_inv_total.iloc[:, -14:-2].mean(axis=1)
        newcharting_oi_inv = oi_inv_total.copy().iloc[:, -4:]
        newcharting_oi_inv["min"] = oi_inv_min
        newcharting_oi_inv["max"] = oi_inv_max
        newcharting_oi_inv["avg"] = oi_inv_avg
        trace = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv.iloc[:, 0],
            connectgaps=True,
            name=newcharting_oi_inv.columns[0],
        )
        trace1 = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv.iloc[:, 1],
            connectgaps=True,
            name=newcharting_oi_inv.columns[1],
        )
        trace2 = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv.iloc[:, 2],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting_oi_inv.columns[2],
        )
        trace3 = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv.iloc[:, 3],
            mode="markers+lines",
            connectgaps=True,
            name=newcharting_oi_inv.columns[3],
        )
        tracemin = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv["min"],
            fill=None,
            opacity=0.1,
            showlegend=False,
            line=dict(color="rgb(255, 255, 204)"),
        )
        traceaverage = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv["avg"],
            name="average of last 12 contracts",
            line=dict(color=("rgb(22, 96, 167)"), width=4, dash="dash"),
        )
        tracerange = go.Scatter(
            x=newcharting_oi_inv.index,
            y=newcharting_oi_inv["max"],
            fill="tonexty",
            mode="lines",
            line=dict(color="rgb(255, 255, 204)"),
            name="Range",
        )
        data_oi_inv = [trace, trace1, trace2, trace3, traceaverage, tracemin, tracerange]
        layout = go.Layout(
            xaxis=dict(autorange="reversed"),
            title=f'{cmdty[:-1]} Front 2 contracts - latest OI/INV on {last_date.strftime("%Y-%m-%d")}',
            width=900,
            height=600,
        )
        fig_oi_inv = go.Figure(data=data_oi_inv, layout=layout)
    else:
        fig_oi_inv = None
    data_for_chart = []
    current_contract = bbg.live_contract(active)
    ticker_dict = tk.decompose_ticker(current_contract["ticker"])
    for idx, col in enumerate(oi_total.columns):
        if col[len(ticker_dict["base_ticker"])] == ticker_dict["m"]:
            if col == oi_total.columns[-2]:
                tz = go.Scatter(
                    x=oi_total.index,
                    y=oi_total.loc[:, col],
                    connectgaps=True,
                    name=col,
                    mode="markers+lines",
                )
            else:
                tz = go.Scatter(
                    x=oi_total.index,
                    y=oi_total.loc[:, col],
                    connectgaps=True,
                    name=col,
                    mode="lines",
                )
            data_for_chart.append(tz)
    layout3 = go.Layout(
        xaxis=dict(autorange="reversed"),
        title="{}".format(cmdty),
        width=900,
        height=600,
    )
    fig3 = go.Figure(data=data_for_chart, layout=layout3)
    return fig, fig3, fig_oi_inv


def oi_total(cmdty, headline, sdate=None):
    if not sdate:
        sdate = dt.datetime(2018, 1, 1)
    NL = bbg.bdh(
        f"{cmdty} Comdty",
        ["FUT_AGGTE_OPEN_INT"],
        sdate,
        today(),
        elms=[("periodicityAdjustment", "ACTUAL")],
    )
    NL2 = bbg.bdh(
        f"{cmdty} Comdty", ["PX_LAST"], sdate, today(), elms=[("periodicityAdjustment", "ACTUAL")]
    )
    NL.columns = ["NL"]
    NL2.columns = ["price"]
    NL["ordinal"] = np.arange(len(NL))
    slope, intercept, r_value, p_value, std_err = stats.linregress(NL["ordinal"], NL["NL"])
    line = slope * NL["ordinal"] + intercept
    stdeviation = NL["NL"].std()
    upstd = line + stdeviation
    lowstd = line - stdeviation
    trace = go.Scatter(x=NL.index, y=NL["NL"], mode="lines", yaxis="y1", name="Total OI")
    trace2 = go.Scatter(x=NL.index, y=line, mode="lines", yaxis="y1", name="trendline")
    trace3 = go.Scatter(
        x=NL.index, y=upstd, mode="lines", line=dict(dash="dash"), yaxis="y1", name="std_dev_Upper"
    )
    trace4 = go.Scatter(
        x=NL.index, y=lowstd, mode="lines", line=dict(dash="dash"), yaxis="y1", name="std_dev_Lower"
    )
    trace5 = go.Scatter(x=NL2.index, y=NL2["price"], mode="lines", yaxis="y2", name="price")
    data = [trace, trace2, trace3, trace4, trace5]
    layout = go.Layout(
        title=headline,
        showlegend=True,
        yaxis=dict(showgrid=True, side="left"),
        yaxis2=dict(overlaying="y", side="right"),
        width=900,
        height=600,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
    )
    fig = go.Figure(data=data, layout=layout)
    return fig


def update_oi_charts():
    OI_Contracts_Energy = [
        ['HG1', 'LP1', 'CU1'],
        ['LA1', 'AA1'],
        ['LX1', 'ZNA1'],
        ['LN1', 'XII1'],
        ['CO1', 'AGD1'],
        ['QS1', 'ABE1'],
        'HO1',
        'XB1',
        'CL1',
        'NG1',
        'TZT1',
        'GC1',
        'SI1',
        'PL1',
        'PA1',
        ['DAT1', 'AFY1', 'MUC1'],
    ]
    OI_Contracts_Energy2 = [
        ['HG2', 'LP2', 'CU2'],
        ['LA2', 'AA2'],
        ['LX2', 'ZNA2'],
        ['LN2', 'XII2'],
        ['CO2', 'AGD2'],
        ['QS2', 'ABE2'],
        'HO2',
        'XB2',
        'CL2',
        'NG2',
        'TZT2',
        'GC2',
        'SI2',
        'PL2',
        'PA2',
        ['DAT2', 'AFY2', 'MUC2'],
    ]
    for i in range(0, len(OI_Contracts_Energy)):
        if isinstance(OI_Contracts_Energy[i], list):
            fig_dict = {}
            for j in range(0, len(OI_Contracts_Energy[i])):
                print(OI_Contracts_Energy[i][j])
                f1, f3, fig_oi_inv = oi_chart(OI_Contracts_Energy[i][j], OI_Contracts_Energy2[i][j])
                if OI_Contracts_Energy[i][j] == "HG1":
                    fig_oi_inv_hg = fig_oi_inv
                f4 = oi_total(OI_Contracts_Energy[i][j], OI_Contracts_Energy[i][j])
                fig_dict[j] = [f1, f3, f4]
            total_fig = [list(x) for x in zip(*list(fig_dict.values()))]
            if OI_Contracts_Energy[i][0] == "HG1":
                total_fig.insert(1, fig_oi_inv_hg)
            if "LP1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\copper.html",
                    task_name=report_name,
                )
            elif "LA1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\aluminium.html",
                    task_name=report_name,
                )
            elif "LX1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\zinc.html",
                    task_name=report_name,
                )
            elif "LN1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\nickel.html",
                    task_name=report_name,
                )
            elif "AGD1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\brent.html",
                    task_name=report_name,
                )
            elif "ABE1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\gasoil.html",
                    task_name=report_name,
                )
            elif "AFY1" in OI_Contracts_Energy[i]:
                table.to_html(
                    total_fig,
                    path=f"{html_path}\\cross_cmds\\oi\\dubai.html",
                    task_name=report_name,
                )
        else:
            print(OI_Contracts_Energy[i])
            f1, f3, fig_oi_inv = oi_chart(OI_Contracts_Energy[i], OI_Contracts_Energy2[i])
            f4 = oi_total(OI_Contracts_Energy[i], OI_Contracts_Energy[i])
            if fig_oi_inv is not None:
                table.figures_to_html(
                    [f1, fig_oi_inv, f3, f4],
                    filename=f"{html_path}\\cross_cmds\\oi\\{OI_Contracts_Energy[i]}.html",
                    task_name=report_name,
                )
            else:
                table.figures_to_html(
                    [f1, f3, f4],
                    filename=f"{html_path}\\cross_cmds\\oi\\{OI_Contracts_Energy[i]}.html",
                    task_name=report_name,
                )


def format_table_signal(df_signal, z=False, key="", full=False, gas_only=False):
    def get_chg_col_frmt(col_num=1, z=False):
        if z:
            return {
                "width": "80px",
                "text-align": "center",
                "format": "{:,.2f}",
                "highlight_z": [
                    f"{col_num}d chg zscore",
                    f"{col_num}d chg",
                    f"{col_num}d_mean",
                    f"{col_num}d_std",
                ],
            }
        else:
            return {
                "width": "80px",
                "text-align": "center",
                "format": "{:,.0f}",
                "highlight_z": [f"{col_num}d chg", f"{col_num}d_mean", f"{col_num}d_std"],
            }
    if full:
        fmt_row = {
            (0, 8, 13, 19, 22, 28, 33, 39): {"bold": True},
            (7, 12, 18, 21, 27, 32, 38): {"bottom_border": True},
        }
    elif gas_only:
        fmt_row = {0: {"bold": True}}
    else:
        fmt_row = {}
    if z:
        extra_hide = ["1d chg", "3d chg", "5d chg", "20d chg"]
    else:
        extra_hide = ["1d chg zscore", "3d chg zscore", "5d chg zscore", "20d chg zscore"]
    return table.html_format(
        df=df_signal,
        precision=1,
        show_date=False,
        header=(f"OI {key} Table 2Y lookback" if not z else f"OI {key} Table 2Y lookback (Z-Score)"),
        hide_cols=[
            "1d_mean",
            "1d_std",
            "1dp_mean",
            "1dp_std",
            "3d_mean",
            "3d_std",
            "3dp_mean",
            "3dp_std",
            "5d_mean",
            "5d_std",
            "5dp_mean",
            "5dp_std",
            "20d_mean",
            "20d_std",
            "20dp_mean",
            "20dp_std",
            "thr1",
            "thr2",
            "_last_update",
        ] + extra_hide,
        format_column={
            "Name": {"width": "120px", "text-align": "center"},
            "Days to expiry": {"width": "80px", "text-align": "center", "format": "{:,.0f}"},
            "Total OI": {"width": "80px", "text-align": "center", "format": "{:,.0f}"},
            "1y percentile": {
                "width": "100px",
                "text-align": "center",
                "format": "{:.1%}",
                "highlight": ["1y percentile", "thr1", "thr2"],
            },
            "1d chg" if not z else "1d chg zscore": get_chg_col_frmt(1, z),
            "1d price chg %": {
                "width": "80px",
                "text-align": "center",
                "format": "{:.1%}",
                "highlight_z": ["1d price chg %", "1dp_mean", "1dp_std"],
            },
            "3d chg" if not z else "3d chg zscore": get_chg_col_frmt(3, z),
            "3d price chg %": {
                "width": "80px",
                "text-align": "center",
                "format": "{:.1%}",
                "highlight_z": ["3d price chg %", "3dp_mean", "3dp_std"],
            },
            "5d chg" if not z else "5d chg zscore": get_chg_col_frmt(5, z),
            "5d price chg %": {
                "width": "80px",
                "text-align": "center",
                "format": "{:.1%}",
                "highlight_z": ["5d price chg %", "5dp_mean", "5dp_std"],
            },
            "20d chg" if not z else "20d chg zscore": get_chg_col_frmt(20, z),
            "20d price chg %": {
                "width": "80px",
                "text-align": "center",
                "format": "{:.1%}",
                "highlight_z": ["20d price chg %", "20dp_mean", "20dp_std"],
            },
        },
        format_row=fmt_row,
    )


def update():
    update_oi_charts()
    tbs = []
    tbs.append("<div style='font-family:Calibri;' >")
    tbs_oil = []
    tbs_oil.append("<div style='font-family:Calibri;' >")
    tbs_gas = []
    tbs_gas.append("<div style='font-family:Calibri;' >")
    df, _ = get_data_zscore()
    df_gas = df.loc[8:12, :]
    df_gas.reset_index(drop=True, inplace=True)
    df_gas.loc[0, "_last_update"] = df_gas.loc[1, "_last_update"]
    df_gas["Name"] = df_gas["Name_"].replace("", pd.NA).combine_first(df_gas["Name"])
    df_gas = df_gas.drop(columns=["Name_"])
    df_ = df.copy()
    df_["Name"] = df_["Name_"].replace("", pd.NA).combine_first(df_["Name"])
    df_ = df_.drop(columns=["Name_"])
    tb = format_table_signal(df_, full=True)
    tb_z = format_table_signal(df_, z=True, full=True)
    table.figures_to_html(
        [tb, tb_z],
        filename=f"{html_path}\\cross_cmds\\links\\full_oi_table.html",
        task_name=report_name,
    )
    tb_gas = format_table_signal(df_gas, full=False, key="Gas", gas_only=True)
    tb_gas_z = format_table_signal(df_gas, z=True, full=False, key="Gas", gas_only=True)
    table.figures_to_html(
        [tb_gas, tb_gas_z],
        filename=f"{html_path}\\cross_cmds\\links\\full_oi_table_gas.html",
        task_name=report_name,
    )
    df_signal = pd.DataFrame()
    df_signal_oil = pd.DataFrame()
    df_signal_gas = pd.DataFrame()
    switch_dict = {y1: x for x, y in fut_dict.items() for y1 in y}
    switch_dict["Oil Agg"] = "Oil"
    for idx, row in df.iterrows():
        if (
            row["1d chg"] > row["1d_mean"] + 1.5 * row["1d_std"]
            or row["1d chg"] < row["1d_mean"] - 1.5 * row["1d_std"]
            or row["3d chg"] > row["3d_mean"] + 1.5 * row["3d_std"]
            or row["3d chg"] < row["3d_mean"] - 1.5 * row["3d_std"]
            or row["5d chg"] > row["5d_mean"] + 1.5 * row["5d_std"]
            or row["5d chg"] < row["5d_mean"] - 1.5 * row["5d_std"]
        ):
            df_signal = pd.concat([df_signal, df.loc[[idx], :]], axis=0)
            if switch_dict[row["Name"]] == "Oil":
                df_signal_oil = pd.concat([df_signal_oil, df.loc[[idx], :]], axis=0)
            elif switch_dict[row["Name"]] == "Gas":
                df_signal_gas = pd.concat([df_signal_gas, df.loc[[idx], :]], axis=0)
    if len(df_signal) > 0:
        df_signal["Name"] = (
            df["Name_"]
            .replace("", pd.NA)
            .combine_first(df_signal["Name"])
        )
        df_signal = df_signal.drop(columns=["Name_"])
        df_signal.reset_index(drop=True, inplace=True)
        df_signal_html = format_table_signal(df_signal)
        df_signal_z_html = format_table_signal(df_signal, z=True)
        tbs.append(df_signal_html)
        tbs.append(df_signal_z_html)
        tbs.append(
            '<a href="{}\\cross_cmds\\links\\full_oi_table.html">Full OI Table</a>'.format(html_path)
        )
        send_email(send_to=send_to_macro, subject='Open Interest', body=tbs)
    else:
        tbs.append("No OI change above 1.5sd in past 1, 3, 5d. <br>")
        tbs.append(
            '<a href="{}\\cross_cmds\\links\\full_oi_table.html">Full OI Table</a>'.format(html_path)
        )
        send_email(send_to=send_to_macro, subject='Open Interest', body=tbs)
    table.figures_to_html(
        tbs,
        filename=f"{html_path}\\cross_cmds\\links\\oi_signal.html",
        task_name=report_name,
    )
    if len(df_signal_oil) > 0:
        df_signal_oil["Name"] = (
            df_signal_oil["Name_"]
            .replace("", pd.NA)
            .combine_first(df_signal_oil["Name"])
        )
        df_signal_oil = df_signal_oil.drop(columns=["Name_"])
        df_signal_oil.reset_index(drop=True, inplace=True)
        df_signal_oil_html = format_table_signal(df_signal_oil, key='Oil')
        df_signal_oil_z_html = format_table_signal(df_signal_oil, z=True, key='Oil')
        tbs_oil.append(df_signal_oil_html)
        tbs_oil.append(df_signal_oil_z_html)
        tbs_oil.append(
            '<a href="{}\\cross_cmds\\links\\full_oi_table.html">Full OI Table</a>'.format(html_path)
        )
        send_email(send_to=send_to_oil, subject='Open Interest - Oil', body=tbs_oil)
    else:
        tbs_oil.append("No OI change above 1.5sd in past 1, 3, 5d. <br>")
        tbs_oil.append(
            '<a href="{}\\cross_cmds\\links\\full_oi_table.html">Full OI Table</a>'.format(html_path)
        )
        send_email(send_to=send_to_oil, subject='Open Interest - Oil', body=tbs_oil)
    table.figures_to_html(
        tbs_oil,
        filename=f"{html_path}\\cross_cmds\\links\\oi_signal_oil.html",
        task_name=report_name,
    )
    if len(df_signal_gas) > 0:
        df_signal_gas["Name"] = (
            df_signal_gas["Name_"]
            .replace("", pd.NA)
            .combine_first(df_signal_gas["Name"])
        )
        df_signal_gas = df_signal_gas.drop(columns=["Name_"])
        df_signal_gas.reset_index(drop=True, inplace=True)
        df_signal_gas_html = format_table_signal(df_signal_gas, key='Gas')
        df_signal_gas_z_html = format_table_signal(df_signal_gas, z=True, key='Gas')
        tbs_gas.append(df_signal_gas_html)
        tbs_gas.append(df_signal_gas_z_html)
        tbs_gas.append(
            '<a href="{}\\cross_cmds\\links\\full_oi_table_gas.html">Full OI Table</a>'.format(html_path)
        )
        send_email(send_to=send_to_gas, subject='Open Interest - Gas', body=tbs_gas)
    else:
        tbs_gas.append("No OI change above 1.5sd in past 1, 3, 5d. <br>")
        tbs_gas.append(
            '<a href="{}\\cross_cmds\\links\\full_oi_table_gas.html">Full OI Table</a>'.format(html_path)
        )
        send_email(send_to=send_to_gas, subject='Open Interest - Gas', body=tbs_gas)
    table.figures_to_html(
        tbs_gas,
        filename=f"{html_path}\\cross_cmds\\links\\oi_signal_gas.html",
        task_name=report_name,
    )


if __name__ == "__main__":
    update()
