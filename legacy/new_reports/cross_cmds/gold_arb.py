import pandas as pd
import datetime as dt

import sys
from pandas.tseries.offsets import BDay
import ecm.cmds.table as table
import ecm.cmds.talib as talib
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.ticker as tk
from ecm.cmds.config import (
    root_path,
    output_path,
    html_path,
    gas_group,
    oil_group,
    macro_group,
    data_path,
)
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
from ecm.atom.services import context

report_name = "Gold Arb"
file_name = "gold_arb"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"

cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"
cc_json_folder = f"{output_path}\\json\\cross_cmds"
cc_pdf_folder = f"{output_path}\\pdf\\cross_cmds"


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 9, 15),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


def gold_arb():
    edate_intraday = today() + BDay(1)
    sdate_intraday = today() - dt.timedelta(days=91)
    sh_gold_ = bbg.bdib("SHGFAUTD Index", sdate_intraday, edate_intraday, interval=15)
    cnh_ = bbg.bdib("USDCNH Curncy", sdate_intraday, edate_intraday, interval=15)
    xau_ = bbg.bdib("XAU Curncy", sdate_intraday, edate_intraday, interval=15)
    arb_live = sh_gold_["close"] / cnh_["close"].reindex(sh_gold_.index) * 31.103477 - xau_["close"].reindex(sh_gold_.index)

    sdate = dt.datetime(2017, 1, 1)
    edate = today()
    sh_gold = bbg.bdh("SHGFAUTD Index", ["PX_LAST"], sdate, edate)
    cnh = bbg.bdh("USDCNH Curncy", ["PX_LAST"], sdate, edate)
    cny = bbg.bdh("CNYMUSD Index", ["PX_LAST"], sdate, edate)
    with context({"container": {"registry": "rvx"}}):
        xau = context.rvx.query_frame("XAUUSD", "INTRADAY", sdate, edate)
    xau.index = xau.index.tz_localize("US/Eastern")
    xau.index = xau.index.tz_convert("UTC")
    xau.index = xau.index.tz_localize(None)
    dts = xau.index.normalize().unique()
    dts = dts[dts.dayofweek != 5]
    dts = dts[dts.dayofweek != 6]
    dts_730am = dts + dt.timedelta(hours=6, minutes=30)
    xau_730 = xau.iloc[:, 0].reindex(dts_730am, method="bfill")
    xau_730.index = dts
    xau_730 = xau_730.to_frame("PX_LAST")

    xau_live = bbg.bdib("XAU Curncy", sdate=dts[-1], edate=today() + dt.timedelta(hours=22))
    dts_new = xau_live.index.normalize().unique()
    dts_new = dts_new[dts_new.dayofweek != 5]
    dts_new = dts_new[dts_new.dayofweek != 6]
    dts_new_730am = dts_new + dt.timedelta(hours=7, minutes=29)
    xau_new_730 = xau_live["close"].reindex(dts_new_730am, method="bfill")
    xau_new_730.index = dts_new
    xau_new_730 = xau_new_730.to_frame("PX_LAST")
    xau_730 = pd.concat([xau_730, xau_new_730.loc[xau_new_730.index > xau_730.index[-1], :]], axis=0)

    arb = sh_gold / cnh * 31.103477 - xau_730
    arb_cny = sh_gold / cny * 31.103477 - xau_730
    arb.to_csv(convert_path_to_linux(f"{data_path}\\gold\\arb.csv"))
    arb_cny.to_csv(convert_path_to_linux(f"{data_path}\\gold\\arb_cny.csv"))
    figs = []
    fig_arb_live = chart.line_chart(
        df=arb_live.to_frame("15min"),
        title=f"Gold SH spot vs XAU Arb Live",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_arb_live.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    fig_arb_live.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
            {"pattern": "hour", "bounds": [19, 1]},
        ]
    )
    arb_lt = pd.concat([arb, talib.mva(arb.dropna(), 20)], axis=1)
    arb_lt.columns = ["Arb Daily", "Arb SMA_20D"]
    fig_arb_lt = chart.line_chart(
        df=arb_lt,
        title="Gold SH spot vs XAU Arb - long term (20D SMA)",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_arb_lt.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    arb_w = arb.reindex(pd.bdate_range(arb.index[0], arb.index[-1]))
    arb_w.fillna(method="ffill", inplace=True)
    arb_w = arb_w.resample("W-FRI").mean()
    fig_arb_w = chart.seasonal(
        df=arb_w,
        freq="W",
        title="Gold SH spot vs XAU Arb - weekly mean",
        width=750,
        height=500,
    )
    ticker = bbg.live_contract(active="GCA Comdty", roll="t1")["ticker"]
    fig_efp_1 = gold_efp_intraday(ticker)
    fig_efp_2, fig_efp_season = efp_roll()
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("Arb = SH Gold / CNH * 31.103477 - XAU based on 15 minutes interval")
    figs.append([fig_arb_live, fig_arb_lt, fig_arb_w])
    figs.append([fig_efp_1, fig_efp_2, fig_efp_season])
    table.to_html(figs, path=f"{html_path}\\cross_cmds\\metal\\gold_arb.html", task_name=report_name)


def silver_arb():
    edate_intraday = today() + BDay(1)
    sdate_intraday = today() - dt.timedelta(days=182)
    sh_gold_intraday = bbg.bdib("SHGFAGTD Index", sdate_intraday, edate_intraday, interval=15)
    sh_gold_ = bbg.bdh("SHGFSIPM Index", ["PX_LAST"], sdate_intraday, edate_intraday)
    cnh_ = bbg.bdib("USDCNH Curncy", sdate_intraday, edate_intraday, interval=15)
    xau_ = bbg.bdib("XAG Curncy", sdate_intraday, edate_intraday, interval=15)
    arb_intraday = sh_gold_intraday["close"] / 1000 / cnh_["close"].reindex(sh_gold_intraday.index) * 31.103477 - xau_["close"].reindex(sh_gold_intraday.index)

    dts = xau_.index.normalize().unique()
    dts = dts[dts.dayofweek != 5]
    dts = dts[dts.dayofweek != 6]
    dts_730am = dts + dt.timedelta(hours=6, minutes=30)
    xau_730 = xau_.iloc[:, 0].reindex(dts_730am, method="bfill")
    xau_730.index = dts
    cnh_730 = cnh_.iloc[:, 0].reindex(dts_730am, method="bfill")
    cnh_730.index = dts
    arb_live = sh_gold_["PX_LAST"] / 1000 / cnh_730.reindex(sh_gold_.index) * 31.103477 - xau_730.reindex(sh_gold_.index)
    figs = []
    fig_arb_live = chart.line_chart(
        df=arb_intraday.to_frame("intraday"),
        title=f"Silver SH spot vs XAG Arb Live",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_arb_live.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    fig_arb_live.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
            {"pattern": "hour", "bounds": [19, 1]},
        ]
    )
    fig_arb_daily = chart.line_chart(
        df=arb_live.to_frame("daily"),
        title=f"Silver SH PM spot vs XAG Arb at 6:30am UTC",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_arb_daily.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    fig_arb_daily.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    ticker = bbg.live_contract(active="SIA Comdty", roll="t1")["ticker"]
    fig_efp_1 = silver_efp_intraday(ticker)
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("Arb = SH Silver / CNH * 31.103477 - XAG based on 6:30am UTC")
    figs.append([fig_arb_live, fig_arb_daily])
    figs.append([fig_efp_1])
    table.to_html(figs, path=f"{html_path}\\cross_cmds\\metal\\silver_arb.html", task_name=report_name)


def gold_efp_intraday_old(ticker, hour=9):
    sdate = today() - dt.timedelta(days=91)
    edate = today() + BDay(1)
    phys_intraday = bbg.bdib("XAU Curncy", sdate, edate)
    phys_intraday.index = phys_intraday.index.tz_localize("UTC")
    phys_intraday.index = phys_intraday.index.tz_convert("Europe/London")
    phys_intraday.index = phys_intraday.index.tz_localize(None)
    cmx_intraday = bbg.bdib(ticker, sdate, edate)
    cmx_intraday.index = cmx_intraday.index.tz_localize("UTC")
    cmx_intraday.index = cmx_intraday.index.tz_convert("Europe/London")
    cmx_intraday.index = cmx_intraday.index.tz_localize(None)
    dts = cmx_intraday.index.normalize().unique()
    dts = dts[dts.dayofweek != 5]
    dts = dts[dts.dayofweek != 6]
    dts_9am = dts + dt.timedelta(hours=hour, minutes=0)
    cmx = cmx_intraday["close"].reindex(dts_9am, method="bfill")
    cmx.index = cmx.index.normalize()
    phys = phys_intraday["close"].reindex(dts_9am, method="bfill")
    phys.index = phys.index.normalize()
    ois = bbg.bdh("USOSFRA Curncy", ["PX_LAST"], sdate, edate)
    df = pd.concat([phys, cmx, ois], axis=1)
    df.dropna(inplace=True)
    expiry = bbg.bref(ticker, "FUT_DLV_DT_FIRST").iloc[0, 0]
    if isinstance(expiry, str):
        expiry = pd.to_datetime(expiry)
    df.columns = ["Spot", ticker, "ois"]
    df["days"] = (expiry - df.index).days
    df.loc[df["days"] < 0, "days"] = 0
    df["spot+carry"] = df["Spot"] * (1 + df["ois"] / 100 / 365 * df["days"])
    df["EFP"] = df[ticker] - df["spot+carry"]
    if hour > 12:
        str_hour = f"{hour-12}pm"
    else:
        str_hour = f"{hour}am"
    fig_efp = chart.line_chart(
        df=df[["EFP"]],
        title=f"Gold EFP - {ticker} vs Spot+carry {str_hour} London",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_efp.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    return fig_efp


def gold_efp_intraday(ticker):
    sdate = today() - dt.timedelta(days=91)
    edate = today() + BDay(1)
    phys_intraday = bbg.bdib("XAU Curncy", sdate, edate, interval=15)
    phys_intraday.index = phys_intraday.index.tz_localize("UTC")
    phys_intraday.index = phys_intraday.index.tz_convert("Europe/London")
    phys_intraday.index = phys_intraday.index.tz_localize(None)
    cmx_intraday = bbg.bdib(ticker, sdate, edate, interval=15)
    cmx_intraday.index = cmx_intraday.index.tz_localize("UTC")
    cmx_intraday.index = cmx_intraday.index.tz_convert("Europe/London")
    cmx_intraday.index = cmx_intraday.index.tz_localize(None)
    ois = bbg.bdib("USOSFRA Curncy", sdate, edate, interval=15)
    df = pd.concat([phys_intraday["close"], cmx_intraday["close"], ois["close"]], axis=1)
    df.columns = ["spot", ticker, "ois"]
    df.dropna(inplace=True)
    expiry = bbg.bref(ticker, "FUT_DLV_DT_FIRST").iloc[0, 0]
    if isinstance(expiry, str):
        expiry = pd.to_datetime(expiry)
    df["days"] = (expiry - df.index).days
    df.loc[df["days"] < 0, "days"] = 0
    df["spot+carry"] = df["spot"] * (1 + df["ois"] / 100 / 365 * df["days"])
    df["EFP"] = df[ticker] - df["spot+carry"]
    fig_efp = chart.line_chart(
        df=df[["EFP"]],
        title=f"Gold EFP - {ticker} vs Spot+carry {df.index[-1].strftime('%Y-%m-%d %H:%M')} UTC",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_efp.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    return fig_efp


def silver_efp_intraday(ticker):
    sdate = today() - dt.timedelta(days=91)
    edate = today() + BDay(1)
    phys_intraday = bbg.bdib("XAG Curncy", sdate, edate, interval=15)
    phys_intraday.index = phys_intraday.index.tz_localize("UTC")
    phys_intraday.index = phys_intraday.index.tz_convert("Europe/London")
    phys_intraday.index = phys_intraday.index.tz_localize(None)
    cmx_intraday = bbg.bdib(ticker, sdate, edate, interval=15)
    cmx_intraday.index = cmx_intraday.index.tz_localize("UTC")
    cmx_intraday.index = cmx_intraday.index.tz_convert("Europe/London")
    cmx_intraday.index = cmx_intraday.index.tz_localize(None)
    ois = bbg.bdib("USOSFRA Curncy", sdate, edate, interval=15)
    df = pd.concat([phys_intraday["close"], cmx_intraday["close"], ois["close"]], axis=1)
    df.columns = ["spot", ticker, "ois"]
    df.dropna(inplace=True)
    expiry = bbg.bref(ticker, "FUT_DLV_DT_FIRST").iloc[0, 0]
    if isinstance(expiry, str):
        expiry = pd.to_datetime(expiry)
    df["days"] = (expiry - df.index).days
    df.loc[df["days"] < 0, "days"] = 0
    df["spot+carry"] = df["spot"] * (1 + df["ois"] / 100 / 365 * df["days"])
    df["EFP"] = df[ticker] - df["spot+carry"]
    fig_efp = chart.line_chart(
        df=df[["EFP"]],
        title=f"Silver EFP - {ticker} vs Spot+carry {df.index[-1].strftime('%Y-%m-%d %H:%M')} UTC",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_efp.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    return fig_efp


def get_current_xau_rate():
    with context({"container": {"registry": "rvx"}}) as cdx:
        phys = context.rvx.query_frame("XAUUSD SP 20250731 F", "RATE", "2025-07-01", "2025-07-23")
        xau = context.rvx.query_frame("XAUUSD", "INTRADAY", "2025-07-01", "2025-07-23")
        xau2 = context.rvx.query_frame("XAUUSD CURNCY", "PX_LAST", "2025-07-01", "2025-07-23")
        xau1 = context.rvx.query_frame("XAUUSD", "RATE", "2025-07-01", "2025-07-23")
    phys1 = bbg.bdh("XAUUSD F133 CURNCY", ["PX_LAST"], dt.datetime(2025, 7, 1), dt.datetime(2025, 7, 23))
    phys2 = bbg.bdh("XAUUSD CURNCY", ["PX_LAST"], dt.datetime(2025, 7, 1), dt.datetime(2025, 7, 23))
    phys3 = bbg.bdh("XAUUSD CURNCY", ["FRD_RT_1M"], dt.datetime(2025, 7, 1), dt.datetime(2025, 7, 23))
    dts = xau.index.normalize().unique()
    dts = dts[dts.dayofweek != 5]
    dts = dts[dts.dayofweek != 6]
    dts_11am = dts + dt.timedelta(hours=11, minutes=0)
    xau_11am = xau.iloc[:, 0].reindex(dts_11am, method="bfill")
    raise NotImplementedError("Photo gap: gold_arb source 358-359 between IMG_5207 and IMG_5208")
    df = phys1.iloc[:, 0] - xau1.iloc[:, 0]
    dfr = (xau2.iloc[:, 0] - xau1.iloc[:, 0]) / xau2.iloc[:, 0]
    dfr1 = (xau2.iloc[:, 0] - phys.iloc[:, 0]) / xau2.iloc[:, 0]


def gold_efp(ticker, sdate, edate, notice):
    rvx_tk = tk.convert_ticker(ticker, base="bbg", to="rvx", ts=None)
    if rvx_tk.split(" ")[2][1] == "3":
        rvx_tk_list = rvx_tk.split(" ")
        rvx_tk_list[2] = rvx_tk_list[2][0] + "2" + rvx_tk_list[2][2]
        rvx_tk = " ".join(rvx_tk_list)
    expiry = notice
    if isinstance(expiry, str):
        expiry = pd.to_datetime(expiry)
    spot_tk = f"XAUUSD SP {expiry.strftime('%Y%m%d')} F"
    with context({"container": {"registry": "rvx"}}) as cdx:
        phys = context.rvx.query_frame(spot_tk, "RATE11AM", sdate, edate)
        cmx = context.rvx.query_frame(rvx_tk, "PRICE11AM", sdate, edate)
    if ticker == "GCZ5 Comdty":
        print("break")
    df = pd.concat([cmx, phys], axis=1)
    try:
        df.columns = ["GC", "XAU"]
    except:
        print(df)
    df.dropna(inplace=True)
    return df


def efp_roll():
    contracts = pyg.get_data("contracts", active="GCA Comdty", item="fut_chain")
    df = pd.DataFrame()
    exp_dts = {}
    for idx, row in contracts.iterrows():
        if row["last_t"] > dt.datetime(2018, 1, 1) and contracts.loc[idx - 1, "last_t"] < today():
            df1 = gold_efp(
                row["ticker"],
                sdate=contracts.loc[idx - 1, "last_t"],
                edate=row["last_t"],
                notice=row["fut_notice_first"],
            )
            exp_dts[row["ticker"]] = [df1.index[-1], df1.index[-20] if len(df1) > 20 else df1.index[0]]
            if len(df) > 0 and df1.index[0] <= df.index[-1]:
                df = pd.concat([df, df1.loc[df1.index > df.index[-1], :]], axis=0)
            else:
                df = pd.concat([df, df1], axis=0)
    df["EFP"] = df["GC"] - df["XAU"]
    fig_efp = chart.line_chart(
        df=df[["EFP"]],
        title=f"Gold EFP - GC1 vs XAU 11am NY (RVX)",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_efp.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    fig_efp_season = chart.seasonal(
        df=df[["EFP"]],
        freq="B",
        title="Gold EFP - GC1 vs XAU 11am NY (RVX)",
        width=750,
        height=500,
    )
    return fig_efp, fig_efp_season


def silver_efp_roll():
    contracts = pyg.get_data("contracts", active="SIA Comdty", item="fut_chain")
    df = pd.DataFrame()
    exp_dts = {}
    for idx, row in contracts.iterrows():
        if row["last_t"] > dt.datetime(2018, 1, 1) and contracts.loc[idx - 1, "last_t"] < today():
            df1 = gold_efp(
                row["ticker"],
                sdate=contracts.loc[idx - 1, "last_t"],
                edate=row["last_t"],
                notice=row["fut_notice_first"],
            )
            exp_dts[row["ticker"]] = [df1.index[-1], df1.index[-20] if len(df1) > 20 else df1.index[0]]
            if len(df) > 0 and df1.index[0] <= df.index[-1]:
                df = pd.concat([df, df1.loc[df1.index > df.index[-1], :]], axis=0)
            else:
                df = pd.concat([df, df1], axis=0)
    df["EFP"] = df["SI"] - df["XAG"]
    fig_efp = chart.line_chart(
        df=df[["EFP"]],
        title=f"Silver EFP - SI1 vs XAG 11am NY (RVX)",
        tickformat=None,
        width=750,
        height=500,
    )
    fig_efp.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    fig_efp_season = chart.seasonal(
        df=df[["EFP"]],
        freq="B",
        title="Silver EFP - SI1 vs XAG 11am NY (RVX)",
        width=750,
        height=500,
    )
    return fig_efp, fig_efp_season


if __name__ == "__main__":
    gold_arb()
    silver_arb()
