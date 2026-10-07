import pandas as pd
import numpy as np
import datetime as dt
from dateutil.relativedelta import relativedelta
import sys
import os
import requests
import ecm.cmds.table as table
import ecm.cmds.talib as talib
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.time_series as ts
from ecm.cmds.config import (
    root_path,
    output_path,
    html_path,
    gas_group,
    oil_group,
    macro_group,
    data_path,
)
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, CDR
from ecm.cmds.utils import convert_path_to_linux
from ecm.atom.services import context
from ecm.cmds.core.chart import _generate_holiday_dates
import ecm.cmds.to_html as to_html
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from gold_arb import gold_arb

send_to = macro_group
report_name = "Base metal inventory"
file_name = "base_metal_inventory"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"
cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"
cc_json_folder = f"{output_path}\\json\\cross_cmds"
cc_pdf_folder = f"{output_path}\\pdf\\cross_cmds"


def _unrecovered(location, *visible_values):
    raise NotImplementedError(f"Photographed source is clipped or absent: {location}")


def add_schedule():
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


folder_path = "\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\shfe\\"
start_stocks = {
    "CUA Comdty": 18384,
    "AAA Comdty": 200944,
    "ZNAA Comdty": 16931,
    "PBLA Comdty": 153371,
    "XIIA Comdty": 6873,
    "XOOA Comdty": 2464,
}
use_alt_dict = {"LME": False}
ins_dict = {
    "COPPER": {
        "LME": {
            "ticker": "LMCADS03 Comdty",
            "fut": "LPA Comdty",
            "stocks": "LSCA Index",
            "warrants": "LFCA Index",
            "cancelled_warrant": "NLFCA Index",
        },
        "SHFE": {
            "ticker": "CUA Comdty",
            "premium": "CECN00CU Index",
            "premium1": "CECN0002 SMMC Index",
            "stocks": "SHFCCOPD Index",
            "warrants": "SHFCCOPO Index",
            "warrants_20211117": 18384,
            "warrants_change": "SFCTCOPW Index",
        },
        "COMEX": {"ticker": "HGA Comdty", "stocks": "COMXCOPR Index", "conversion": 0.90718335},
    },
    "ALUMINIUM": {
        "LME": {
            "ticker": "LMAHDS03 Comdty", "fut": "LAA Comdty", "stocks": "LSAH Index",
            "warrants": "LFAH Index", "cancelled_warrant": "NLFAH Index",
        },
        "SHFE": {
            "ticker": "AAA Comdty", "premium": "AICNIWSH Index", "stocks": "SHFAALUD Index",
            "warrants": "SHFAALUO Index", "warrants_20211117": 200944, "warrants_change": "SFCTALUW Index",
        },
    },
    "ZINC": {
        "LME": {
            "ticker": "LMZSDS03 Comdty", "fut": "LXA Comdty", "stocks": "LSZS Index",
            "warrants": "LFZS Index", "cancelled_warrant": "NLFZS Index",
        },
        "SHFE": {
            "ticker": "ZNAA Comdty", "stocks": "SHFZZIND Index", "premium": "ZNCNMQKY Index",
            "warrants": "SHFZZINO Index", "warrants_20211117": 16931, "warrants_change": "SFCTZINW Index",
        },
    },
    "NICKEL": {
        "LME": {
            "ticker": "LMNIDS03 Comdty", "fut": "LNA Comdty", "stocks": "LSNI Index",
            "warrants": "LFNI Index", "cancelled_warrant": "NLFNI Index",
        },
        "SHFE": {
            "ticker": "XIIA Comdty", "premium": "NICNKBPV Index", "stocks": "SNIWNICD Index",
            "warrants": "SNIWNICO Index", "warrants_20211117": 6873,
        },
    },
    "LEAD": {
        "LME": {
            "ticker": "LMPBDS03 Comdty", "fut": "LLA Comdty", "stocks": "LSPB Index",
            "warrants": "LFPB Index", "cancelled_warrant": "NLFPB Index",
        },
        "SHFE": {
            "ticker": "PBLA Comdty", "stocks": "SFLCLEAD Index", "warrants": "SFLCLEAO Index",
            "warrants_20211117": 153371, "warrants_change": "SFCTPBOW Index",
        },
    },
    "TIN": {
        "LME": {
            "ticker": "LMSNDS03 Comdty", "fut": "LTA Comdty", "stocks": "LSSN Index",
            "warrants": "LFSN Index", "cancelled_warrant": "NLFSN Index",
        },
        "SHFE": {"ticker": "XOOA Comdty", "stocks": "SSNWNICD Index", "warrants": "SSNWNICO Index", "warrants_20211117": 2464},
    },
}


def get_data(exchange="LME", sdate=dt.datetime(2015, 1, 1), edate=today(), only_inv=True):
    ticker_list = []
    name_list = []
    for name, inv_dict in ins_dict.items():
        try:
            ticker_list.append(inv_dict[exchange]["stocks"])
            name_list.append(name + "_stocks")
            ticker_list.append(inv_dict[exchange]["warrants"])
            name_list.append(name + "_warrants")
            ticker_list.append(inv_dict[exchange]["cancelled_warrant"])
            name_list.append(name + "_cancelled_warrants")
        except:
            pass
    use_alt = use_alt_dict.get(exchange, False)
    inv = bbg.bdh(ticker_list, ["PX_LAST"], sdate=sdate, edate=edate, use_alt=use_alt)
    if len(ticker_list) != 1:
        inv = inv[ticker_list]
    inv.columns = name_list
    return inv


def get_shfe_daily_warrants(sdate=dt.datetime(2014, 1, 1), edate=today()):
    ticker_list = []
    name_list = []
    for name, inv_dict in ins_dict.items():
        try:
            ticker_list.append(inv_dict["SHFE"]["warrants_change"])
            name_list.append(name + "_warrants")
        except:
            pass
    inv = bbg.bdh(ticker_list, ["PX_LAST"], sdate=sdate, edate=edate)
    inv = inv[ticker_list]
    inv.columns = name_list
    return inv


def download_daily_stock_file():
    onlyfiles = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    if len(onlyfiles) > 0:
        file_dates = [dt.datetime.strptime(date, "%Y%m%d") for date in onlyfiles]
        sdate = max(file_dates)
    else:
        sdate = dt.datetime(2011, 1, 4)
    edate = today()
    weekdays = pd.bdate_range(sdate, edate, freq="B")
    for d in weekdays:
        date_str = dt.datetime.strftime(d, "%Y%m%d")
        url = "http://www.shfe.com.cn/data/dailydata/" + date_str + "dailystock.dat"
        res = requests.get(url)
        if "Request Page Not Found" not in res.text:
            file = open(folder_path + date_str + ".txt", "w", encoding="utf-8")
            file.write(res.text)
            file.close()


def get_total_stocks(sdate=dt.datetime(2014, 1, 1)):
    """
    SHFE daily stock is eatimated from daily warrant change and 52w rolling regression between
    weekly stock and warrant change
    """
    weekdays = pd.bdate_range(sdate, today())
    lme_data = get_data(exchange="LME", sdate=sdate, edate=today())
    lme_data = lme_data.reindex(weekdays)
    lme_data.fillna(method="ffill", inplace=True)
    comex_data = get_data(exchange="COMEX", sdate=sdate, edate=today())
    comex_data = comex_data.reindex(lme_data.index)
    comex_data.fillna(method="ffill", inplace=True)
    comex_data = comex_data.shift(1)
    shfe_data = get_data(exchange="SHFE", sdate=sdate, edate=today())
    shfe_weekly = shfe_data.copy()
    shfe_data = shfe_data.reindex(lme_data.index)
    shfe_data.fillna(method="ffill", inplace=True)
    shfe_warrants = get_shfe_daily_warrants(sdate=sdate, edate=today())
    shfe_warrants = shfe_warrants.reindex(lme_data.index)
    shfe_warrants.fillna(method="ffill", inplace=True)

    shfe_weekly.fillna(method="ffill", inplace=True)
    shfe_weekly_chg = shfe_weekly.diff()
    shfe_weekly_chg.fillna(0, inplace=True)
    lst = ["ALUMINIUM", "COPPER", "ZINC", "LEAD"]
    shfe_daily = pd.DataFrame()
    for i in lst:
        y = shfe_weekly_chg[i + "_stocks"].values
        x = shfe_weekly_chg[i + "_warrants"].values
        alphas, betas = talib.rolling_ols(y, x, window=52, const=True)[:2]
        se_a = pd.Series(alphas, index=shfe_weekly_chg.index)
        se_b = pd.Series(betas, index=shfe_weekly_chg.index)
        se_a = se_a.reindex(lme_data.index)
        se_a.fillna(method="ffill", inplace=True)
        se_b = se_b.reindex(lme_data.index)
        se_b.fillna(method="ffill", inplace=True)
        stock_chg = se_a + se_b * shfe_warrants[i + "_warrants"]
        stock_chg[shfe_weekly.index] = 0
        stock_chg = stock_chg.to_frame("stock_change")
        stock_chg["_no"] = np.nan
        stock_chg.loc[shfe_weekly.index, "_no"] = range(0, len(shfe_weekly))
        stock_chg["_no"].fillna(method="ffill", inplace=True)
        stock_chg["cum"] = stock_chg.groupby("_no").cumsum()
        shfe_data[i + "_stocks"] = shfe_data[i + "_stocks"] + stock_chg["cum"]

    stock_cols = [c for c in shfe_data.columns if c.split("_")[1] == "stocks"]
    shfe_data = shfe_data[stock_cols]
    total_stocks = lme_data[stock_cols] + shfe_data
    total_stocks.index.name = "Date"
    lme_data.index.name = "Date"
    shfe_data.index.name = "Date"
    total_stocks = total_stocks.loc[dt.datetime(2015, 1, 1):, :]
    total_stocks.columns = [c + "_TOTAL" for c in list(ins_dict.keys())]
    lme_data_stocks = lme_data[stock_cols].loc[dt.datetime(2015, 1, 1):, :]
    lme_data_stocks.columns = [c + "_LME" for c in list(ins_dict.keys())]
    shfe_data = shfe_data.loc[dt.datetime(2015, 1, 1):, :]
    shfe_data.columns = [c + "_SHFE" for c in list(ins_dict.keys())]
    stocks = pd.concat([total_stocks, lme_data_stocks, shfe_data], axis=1)
    stocks["COPPER_COMEX"] = comex_data["COPPER_stocks"] * ins_dict["COPPER"]["COMEX"]["conversion"]
    stocks["COPPER_TOTAL"] = stocks["COPPER_TOTAL"] + stocks["COPPER_COMEX"]
    stocks["COPPER_WEST"] = stocks["COPPER_LME"] + stocks["COPPER_COMEX"]
    ex_copper = list(ins_dict.keys())
    ex_copper.pop(0)
    cols = [c + f for c in ex_copper for f in ("_TOTAL", "_LME", "_SHFE")]
    cols = ["COPPER_TOTAL", "COPPER_LME", "COPPER_COMEX", "COPPER_WEST", "COPPER_SHFE"] + cols
    stocks = stocks[cols]
    stocks.to_csv(convert_path_to_linux(f"{cc_csv_folder}\\base_metal_stocks.csv"))
    lme_cancelled_warrents = lme_data[
        [x for x in lme_data.columns if x.endswith("cancelled_warrants")]
    ]
    lme_cancelled_warrents.to_csv(convert_path_to_linux(f"{cc_csv_folder}\\lme_can_warrents.csv"))
    return stocks, lme_cancelled_warrents


def get_table(bal, index_name="Total Inventory", pct=None):
    df_table = pd.DataFrame(
        0, index=bal.columns,
        columns=["Latest", "Change on day", "5day change", "20day change", "3month change", "YTD"],
    )
    df_table.loc[:, "Latest"] = bal.iloc[-1]
    df_table.loc[:, "Change on day"] = bal.iloc[-1] - bal.iloc[-2]
    df_table.loc[:, "5day change"] = bal.iloc[-1] - bal.iloc[-6]
    df_table.loc[:, "20day change"] = bal.iloc[-1] - bal.iloc[-21]
    df_table.loc[:, "3month change"] = bal.iloc[-1] - bal.iloc[-66]
    start_year = bal.loc[bal.index >= dt.datetime(today().year, 1, 1), :].index[0]
    df_table.loc[:, "YTD"] = bal.iloc[-1] - bal.loc[start_year, :]
    price_3m = bal["LME 3m"]
    df_table.loc["LME 3m", "Change on day"] = (price_3m.iloc[-1] - price_3m.iloc[-2]) / price_3m.iloc[-2]
    df_table.loc["LME 3m", "5day change"] = (price_3m.iloc[-1] - price_3m.iloc[-6]) / price_3m.iloc[-6]
    df_table.loc["LME 3m", "20day change"] = (price_3m.iloc[-1] - price_3m.iloc[-21]) / price_3m.iloc[-21]
    df_table.loc["LME 3m", "3month change"] = (price_3m.iloc[-1] - price_3m.iloc[-66]) / price_3m.iloc[-66]
    df_table.loc["LME 3m", "YTD"] = (price_3m.iloc[-1] - bal.loc[start_year, "LME 3m"]) / bal.loc[start_year, "LME 3m"]
    if pct is not None:
        for i in pct:
            price_3m = bal[i]
            df_table.loc[i, "Change on day"] = (price_3m.iloc[-1] - price_3m.iloc[-2]) / price_3m.iloc[-2]
            df_table.loc[i, "5day change"] = (price_3m.iloc[-1] - price_3m.iloc[-6]) / price_3m.iloc[-6]
            df_table.loc[i, "20day change"] = (price_3m.iloc[-1] - price_3m.iloc[-21]) / price_3m.iloc[-21]
            df_table.loc[i, "3month change"] = (price_3m.iloc[-1] - price_3m.iloc[-66]) / price_3m.iloc[-66]
            df_table.loc[i, "YTD"] = (price_3m.iloc[-1] - bal.loc[start_year, i]) / bal.loc[start_year, i]

    df_mean_std = ts.historical_mean_std(bal, window=20, seasonal=None)
    df_mean_std_lme = ts.historical_mean_std(
        (bal[["LME 3m"]] - bal[["LME 3m"]].shift(1)) / bal[["LME 3m"]].shift(1),
        window=20,
        seasonal=None,
    )
    df_mean_std.loc["LME 3m"] = df_mean_std_lme.loc["LME 3m"]
    if pct is not None:
        for i in pct:
            df_mean_std_lme = ts.historical_mean_std(
                (bal[[i]] - bal[[i]].shift(1)) / bal[[i]].shift(1), window=20, seasonal=None
            )
            df_mean_std.loc[i] = df_mean_std_lme.loc[i]
    df_table.loc[:, "mean"] = df_mean_std.loc[:, "mean"]
    df_table.loc[:, "std"] = df_mean_std.loc[:, "std"]

    df_mean_std = ts.historical_mean_std((bal - bal.shift(5)), window=65, seasonal=None)
    df_mean_std_lme = ts.historical_mean_std(
        (bal[["LME 3m"]] - bal[["LME 3m"]].shift(5)) / bal[["LME 3m"]].shift(5),
        window=20,
        seasonal=None,
    )
    df_mean_std.loc["LME 3m"] = df_mean_std_lme.loc["LME 3m"]
    if pct is not None:
        for i in pct:
            df_mean_std_lme = ts.historical_mean_std(
                (bal[[i]] - bal[[i]].shift(5)) / bal[[i]].shift(5), window=20, seasonal=None
            )
            df_mean_std.loc[i] = df_mean_std_lme.loc[i]
    df_table.loc[:, "mean_5d"] = df_mean_std.loc[:, "mean"]
    df_table.loc[:, "std_5d"] = df_mean_std.loc[:, "std"]

    df_mean_std = ts.historical_mean_std((bal - bal.shift(20)), window=65, seasonal=None)
    df_mean_std_lme = ts.historical_mean_std(
        (bal[["LME 3m"]] - bal[["LME 3m"]].shift(20)) / bal[["LME 3m"]].shift(20),
        window=20,
        seasonal=None,
    )
    df_mean_std.loc["LME 3m"] = df_mean_std_lme.loc["LME 3m"]
    if pct is not None:
        for i in pct:
            df_mean_std_lme = ts.historical_mean_std(
                (bal[[i]] - bal[[i]].shift(20)) / bal[[i]].shift(20), window=20, seasonal=None
            )
            df_mean_std.loc[i] = df_mean_std_lme.loc[i]
    df_table.loc[:, "mean_20d"] = df_mean_std.loc[:, "mean"]
    df_table.loc[:, "std_20d"] = df_mean_std.loc[:, "std"]

    df_table.index.name = index_name
    df_table.reset_index(inplace=True)
    return df_table


def table_format_html(df_table, index_name="Total Inventory"):
    return table.html_format(
        df=df_table,
        precision=0,
        hide_cols=["mean", "std", "mean_5d", "std_5d", "mean_20d", "std_20d"],
        format_column={
            index_name: {"width": "120px", "text-align": "left"},
            "Latest": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["Latest", "mean", "std"],
            },
            "Change on day": {"width": "100px", "text-align": "center"},
            "5day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["5day change", "mean_5d", "std_5d"],
            },
            "20day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["20day change", "mean_20d", "std_20d"],
            },
            "3month change": {"width": "100px", "text-align": "center"},
            "YTD": {"width": "100px", "text-align": "center"},
        },
        format_row={
            "3": {"bottom_border": True},
            "4": {"format": "{0:.2%}", "columns": df_table.columns[2:-1]},
            "5": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "6": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "7": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "8": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "9": {
                "bottom_border": True,
                "format": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            },
            "10": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "11": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "12": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "13": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
        },
    )


def table_format_html_aluminium(df_table, index_name="Total Inventory"):
    return table.html_format(
        df=df_table,
        precision=0,
        hide_cols=["mean", "std", "mean_5d", "std_5d", "mean_20d", "std_20d"],
        format_column={
            index_name: {"width": "120px", "text-align": "left"},
            "Latest": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["Latest", "mean", "std"],
            },
            "Change on day": {"width": "100px", "text-align": "center"},
            "5day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["5day change", "mean_5d", "std_5d"],
            },
            "20day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["20day change", "mean_20d", "std_20d"],
            },
            "3month change": {"width": "100px", "text-align": "center"},
            "YTD": {"width": "100px", "text-align": "center"},
        },
        format_row={
            "3": {"bottom_border": True},
            "4": {"format": "{0:.2%}", "columns": df_table.columns[2:-1]},
            "5": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "6": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "7": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "8": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "9": {
                "bottom_border": True,
                "format": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            },
            "10": {"format": "{0:.2%}", "columns": df_table.columns[2:-1]},
            "11": {"format": "{0:.2%}", "columns": df_table.columns[2:-1]},
            "12": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "13": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "14": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "15": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
        },
    )


def table_format_html_copper(df_table, index_name="Total Inventory"):
    return table.html_format(
        df=df_table,
        precision=0,
        hide_cols=["mean", "std", "mean_5d", "std_5d", "mean_20d", "std_20d"],
        format_column={
            index_name: {"width": "120px", "text-align": "left"},
            "Latest": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["Latest", "mean", "std"],
            },
            "Change on day": {"width": "100px", "text-align": "center"},
            "5day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["5day change", "mean_5d", "std_5d"],
            },
            "20day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["20day change", "mean_20d", "std_20d"],
            },
            "3month change": {"width": "100px", "text-align": "center"},
            "YTD": {"width": "100px", "text-align": "center"},
        },
        format_row={
            "4": {"bottom_border": True},
            "5": {"format": "{0:.2f}", "columns": df_table.columns[1:-1]},
            "6": {"format": "{0:.2f}", "columns": df_table.columns[1:-1]},
            "7": {"format": "{0:.2f}", "columns": df_table.columns[1:-1]},
            "9": {"format": "{0:.2f}", "columns": df_table.columns[1:-1]},
            "9": {"bottom_border": True},
            "10": {"format": "{0:.2%}", "columns": df_table.columns[2:-1]},
            "11": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "12": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "13": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "14": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "15": {
                "bottom_border": True,
                "format": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            },
            "16": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "17": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "18": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
            "19": {"format": "{0:.1f}", "columns": df_table.columns[1:-1]},
        },
    )


def update_old():
    tbs = []
    tbs.append("<div style='font-family:Calibri;' >")
    tbs.append(_unrecovered("base_metal_inventory.py line 580 text after Data starts from 201", "Highlight colors: green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. Data starts from 201"))
    tbs.append("Latest inventory is highlighted vs 20d average. 5d average is highlighted vs 3m average. <br>")
    tbs.append(
        "SHFE daily inventory is estimated from daily warrants data when available. "
        "It is replaced with weekly data on Friday.<br>"
    )
    stocks_last = ts.read_csv(f"{cc_csv_folder}\\base_metal_stocks.csv", index_name="Date")
    figs = []
    total_stocks = get_total_stocks()
    if len(stocks_last) == 0 or total_stocks.index[-1] > stocks_last.index[-1]:
        send_file = True
        total_stocks["COPPER_COMEX"] = total_stocks["COPPER_COMEX"].shift(1)
    elif _unrecovered("base_metal_inventory.py lines 598-599 COPPER_COMEX comparison", total_stocks["COPPER_COMEX"], stocks_last):
        send_file = True
    else:
        send_file = True
        total_stocks["COPPER_COMEX"] = total_stocks["COPPER_COMEX"].shift(1)
    lme = total_stocks[
        ["COPPER_LME", "COPPER_COMEX", "COPPER_WEST", "ALUMINIUM_LME", "ZINC_LME", "NICKEL_LME", "LEAD_LME", "TIN_LME"]
    ]
    lme.columns = ["LME COPPER", "COMEX COPPER", "WEST COPPER", "ALUMINIUM", "ZINC", "NICKEL", "LEAD", "TIN"]
    shfe = total_stocks[["COPPER_SHFE", "ALUMINIUM_SHFE", "ZINC_SHFE", "NICKEL_SHFE", "LEAD_SHFE", "TIN_SHFE"]]
    shfe.columns = ["COPPER", "ALUMINIUM", "ZINC", "NICKEL", "LEAD", "TIN"]
    total = total_stocks[["COPPER_TOTAL", "ALUMINIUM_TOTAL", "ZINC_TOTAL", "NICKEL_TOTAL", "LEAD_TOTAL", "TIN_TOTAL"]]
    total.columns = ["COPPER", "ALUMINIUM", "ZINC", "NICKEL", "LEAD", "TIN"]
    if send_file:
        df_table_total = get_table(total, index_name="Total Inventory")
        tbs.append(table_format_html(df_table_total, index_name="Total Inventory"))
        df_table_lme = get_table(lme, index_name="LME Inventory")
        tbs.append(table_format_html(df_table_lme, index_name="LME Inventory"))
        df_table_shfe = get_table(shfe, index_name="SHFE Inventory")
        tbs.append(table_format_html(df_table_shfe, index_name="SHFE Inventory"))
        for i in total_stocks.columns:
            figs.append(
                chart.seasonal_chart(
                    df=total_stocks[i], ex2020=False, freq="B", title=i,
                    y_axis_title="metric tons", x_axis_title="Date",
                )
            )
        table.figures_to_html(
            figs,
            filename=f"{html_path}\\cross_cmds\\links\\base_metal_inventory_charts.html",
            task_name=report_name,
        )
        pdf_path = f"{cc_pdf_folder}\\base_metal_inventory_charts.pdf"
        table.figures_to_pdf(figs, pdf_path=pdf_path)
        tbs.append(
            '<a href="{}\\cross_cmds\\links\\base_metal_inventory_charts.html">Inventory charts</a>'.format(html_path)
        )
        send_email(
            send_to=send_to,
            subject=report_name,
            body=tbs,
            attachments=pdf_path,
            html_path=f"{html_path}\\cross_cmds\\links\\base_metal_inventory_charts.html",
        )


def normalize_by_first_value(x):
    baseline = x.iloc[0]
    diff = x - baseline
    return diff


def update_comex_arb(active_contract, contracts_table):
    pass


def update_base_metal():
    tbs = []
    tbs.append("<div style='font-family:Calibri;' >")
    tbs.append("SHFE prices are in $/t")
    figs_arb = []
    figs_arb.append("<div style='font-family:Calibri;' >")
    figs_arb.append("Arb = SHFE - (LME * vat * CNH + 200)) / CNH")
    figs_arb.append(_unrecovered("base_metal_inventory.py line 702 explanatory text after benchmark", "Premium: refers to the price premium paid for imported metal in China on top of the benchmark"))
    df_arb_prem = pd.DataFrame()
    stocks_last = ts.read_csv(f"{cc_csv_folder}\\base_metal_stocks.csv", index_name="Date")
    total_stocks, lme_cancelled_warrents = get_total_stocks()
    for k, v in ins_dict.items():
        tbs_one = []
        tbs_one.append("<div style='font-family:Calibri;' >")
        tbs_one.append("SHFE prices are in $/t")
        if k not in ["LEAD", "TIN"]:
            df = pd.DataFrame()
            if k == "COPPER":
                col1 = ["COPPER_TOTAL", "COPPER_WEST", "COPPER_LME", "COPPER_COMEX", "COPPER_SHFE"]
                df = pd.concat([df, total_stocks[col1]], axis=1)
                df = pd.concat([df, lme_cancelled_warrents[k + "_cancelled_warrants"]], axis=1)
                col_new = ["COPPER_TOTAL", "COPPER_WEST", "COPPER_LME", k + "_cancelled_warrants", "COPPER_COMEX", "COPPER_SHFE"]
                contracts = pyg.get_data("spreads", active="HGA Comdty", item="sprd_chain")
                hg_ticker = (
                    contracts.loc[contracts["t3"] > today(), :].iloc[0:4, :].ticker.values.tolist()
                )
                hg_sprd = bbg.bdh(hg_ticker, ["PX_LAST"], today() - dt.timedelta(days=364 + 28), today())
                hg_sprd.columns = [f"HG {x.split(' ')[1]}" for x in hg_ticker]
                df = pd.concat([df, hg_sprd], axis=1)
                col_new = col_new[:-1] + hg_sprd.columns.to_list() + [col_new[-1]]
                col1 = col1[:-1] + hg_sprd.columns.to_list() + [col1[-1]]
                df = df[col_new]
            else:
                col = [f"{k}_TOTAL", f"{k}_LME", f"{k}_SHFE"]
                warrents_col = f"{k}_cancelled_warrants"
                df = pd.concat([df, total_stocks[col]], axis=1)
                df = pd.concat([df, lme_cancelled_warrents[warrents_col]], axis=1)
                col_new = [f"{k}_TOTAL", f"{k}_LME", warrents_col, f"{k}_SHFE"]
                df = df[col_new]
            ticker_list = []
            drop_cols = []
            forward_ticker = v["LME"]["ticker"]
            base_ticker = forward_ticker[:6]
            base_ticker_shfe = v["SHFE"]["ticker"].split(" ")[0][:-1]
            ticker_list.append(forward_ticker)
            ticker_list.append(f"{base_ticker} Comdty")
            contracts = pyg.get_data("contracts", active=v["LME"]["fut"], item="fut_chain")
            contracts = contracts.loc[contracts["t3"] > today(), :]
            ticker_list.append(_unrecovered("base_metal_inventory.py line 756 first spread ticker tail", base_ticker, contracts['m'].iloc[0], str(contracts['y'].iloc[0])[-2:]))
            lme_sprd1 = _unrecovered("base_metal_inventory.py line 758 first spread label tail", v['LME']['fut'][:2], contracts['m'].iloc[0], str(contracts['y'].iloc[0])[-2:])
            ticker_list.append(_unrecovered("base_metal_inventory.py line 761 second spread ticker tail", base_ticker, contracts['m'].iloc[1], str(contracts['y'].iloc[1])[-2:]))
            lme_sprd2 = _unrecovered("base_metal_inventory.py line 763 second spread label tail", v['LME']['fut'][:2], contracts['m'].iloc[1], str(contracts['y'].iloc[1])[-2:])
            lme_sprd_3z = "03Z25"
            ticker_list.append(f"{base_ticker} {lme_sprd_3z} Comdty")
            lme_sprd_zz = "Z25Z26"
            ticker_list.append(f"{base_ticker} {lme_sprd_zz} Comdty")
            if k == "ALUMINIUM":
                alumina_ticker = f"ANO{contracts['m'].iloc[0]}{str(contracts['y'].iloc[0])[-1]}"
                ticker_list.append(alumina_ticker + " Comdty")
            first_ticker = f"{base_ticker_shfe}{contracts['m'].iloc[0]}{str(contracts['y'].iloc[0])[-1]}"
            ticker_list.append(first_ticker + " Comdty")
            drop_cols.append(first_ticker + " Comdty")
            shfe_sprd1 = _unrecovered("base_metal_inventory.py line 780 SHFE first spread label tail", base_ticker_shfe, contracts['m'].iloc[0], str(contracts['y'].iloc[0])[-1])
            ticker_list.append(f"{base_ticker_shfe}{contracts['m'].iloc[1]}{str(contracts['y'].iloc[1])[-1]} Comdty")
            drop_cols.append(f"{base_ticker_shfe}{contracts['m'].iloc[1]}{str(contracts['y'].iloc[1])[-1]} Comdty")
            shfe_sprd2 = _unrecovered("base_metal_inventory.py line 788 SHFE second spread label tail", base_ticker_shfe, contracts['m'].iloc[1], str(contracts['y'].iloc[1])[-1])
            ticker_list.append(f"{base_ticker_shfe}{contracts['m'].iloc[2]}{str(contracts['y'].iloc[2])[-1]} Comdty")
            drop_cols.append(f"{base_ticker_shfe}{contracts['m'].iloc[2]}{str(contracts['y'].iloc[2])[-1]} Comdty")
            shfe_sprd3 = _unrecovered("base_metal_inventory.py line 796 SHFE third spread label tail", base_ticker_shfe, contracts['m'].iloc[2], str(contracts['y'].iloc[2])[-1])
            ticker_list.append(f"{base_ticker_shfe}{contracts['m'].iloc[3]}{str(contracts['y'].iloc[3])[-1]} Comdty")
            drop_cols.append(f"{base_ticker_shfe}{contracts['m'].iloc[3]}{str(contracts['y'].iloc[3])[-1]} Comdty")
            ticker_list.append(v["SHFE"]["premium"])
            if k == "COPPER":
                ticker_list.append(v["SHFE"]["premium1"])
            ticker_list.append("USDCNH Curncy")
            price = bbg.bdh(ticker_list, ["PX_LAST"], today() - dt.timedelta(days=364 + 28), today())
            if isinstance(price.columns, pd.MultiIndex):
                price.columns = [x[0] for x in price.columns]
            try:
                shfe_arb = ts.read_csv(
                    _unrecovered("base_metal_inventory.py line 819 model path filename tail", f"\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\model\\{v['LME']['fut']}"),
                    index_name="date",
                )
            except:
                shfe_arb = ts.read_csv(
                    _unrecovered("base_metal_inventory.py line 824 model path filename tail", f"\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\model\\{v['LME']['fut']}"),
                    index_name="Unnamed: 0",
                )
            shfe_arb.columns = ["Arb SHFE vs LME"]
            shfe_arb = shfe_arb.reindex(price.index)
            if k in ["COPPER"]:
                cur_year = today().year
                dec_hg_1 = f"HGZ{str(cur_year)[-1]} Comdty"
                dec_hg_2 = f"HGZ{str(cur_year + 1)[-1]} Comdty"
                dec_lp_1 = f"LPZ{str(cur_year)[-2:]} Comdty"
                dec_lp_2 = f"LPZ{str(cur_year + 1)[-2:]} Comdty"
                comex_arb_raw_data = bbg.bdh(
                    ["HGA Comdty", "LMCADS03 Comdty", dec_hg_1, dec_lp_1, dec_hg_2, dec_lp_2],
                    sdate=today() - relativedelta(months=6),
                    edate=today() - relativedelta(days=1),
                )
                active_arb = (
                    (22.04623 * comex_arb_raw_data["HGA Comdty"]) - comex_arb_raw_data["LMCADS03 Comdty"]
                ).to_frame("Comex vs LME Arb")
                dec_dec_arb_1 = (
                    (22.04623 * comex_arb_raw_data[dec_hg_1]) - comex_arb_raw_data[dec_lp_1]
                ).to_frame(f"{dec_hg_1}-{dec_lp_1}")
                dec_dec_arb_2 = (
                    (22.04623 * comex_arb_raw_data[dec_hg_2]) - comex_arb_raw_data[dec_lp_2]
                ).to_frame(f"{dec_hg_2}-{dec_lp_2}")
                tarrif_pctile_dec_dec_2 = (dec_dec_arb_2 / comex_arb_raw_data[dec_lp_2].iloc[-1]) * 100
                tarrif_pctile_dec_dec_2.columns = [f"Arb Percentile DecDec{str(cur_year + 1)[-1]}"]
                tarrif_pctile_dec_dec_1 = (dec_dec_arb_1 / comex_arb_raw_data[dec_lp_1].iloc[-1]) * 100
                tarrif_pctile_dec_dec_1.columns = [f"Arb Percentile DecDec{str(cur_year)[-1]}"]
                tarrif_pctile_active = (active_arb / comex_arb_raw_data["LMCADS03 Comdty"].iloc[-1]) * 100
                tarrif_pctile_active.columns = ["Arb Percentile Front"]
                comex_arb = pd.concat([active_arb, dec_dec_arb_1, dec_dec_arb_2], axis=1)
                comex_arb_pct = pd.concat([tarrif_pctile_active, tarrif_pctile_dec_dec_1, tarrif_pctile_dec_dec_2], axis=1)
                comex_arb_chart = chart.line_chart(
                    df=comex_arb, data_p1y2=comex_arb_pct, title=f"Comex vs LME Arb",
                    y_axis_title="Price", tickformat=None, secondary_y=True, p1y2_axis_title="Implied Tariff (%)",
                )
                comex_arb_chart.update_layout(
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5)
                )
            else:
                comex_arb = pd.DataFrame()
            df = pd.concat([df, price, shfe_arb, comex_arb], axis=1)
            df.fillna(method="ffill", inplace=True)
            df[shfe_sprd1] = (df[drop_cols[0]] - df[drop_cols[1]]) / df["USDCNH Curncy"]
            df[shfe_sprd2] = (df[drop_cols[1]] - df[drop_cols[2]]) / df["USDCNH Curncy"]
            df[shfe_sprd3] = (df[drop_cols[2]] - df[drop_cols[3]]) / df["USDCNH Curncy"]
            ticker_list.insert(-2, shfe_sprd1)
            ticker_list.insert(-2, shfe_sprd2)
            ticker_list.insert(-2, shfe_sprd3)
            df = df[col_new + ticker_list + ["Arb SHFE vs LME"]]
            df[df.columns[-5]] = df[df.columns[-5]] / df["USDCNH Curncy"]
            if k == "ALUMINIUM":
                drop_cols.pop(0)
            df.drop(drop_cols, axis=1, inplace=True)
            df.drop("USDCNH Curncy", axis=1, inplace=True)
            if k == "COPPER":
                df["TOTAL Inv Normalised"] = df["COPPER_TOTAL"].groupby(df.index.year).transform(normalize_by_first_value)
                df["WEST Inv Normalised"] = df.groupby(df.index.year)["COPPER_WEST"].transform(normalize_by_first_value)
                df["COMEX Inv Normalised"] = df.groupby(df.index.year)["COPPER_COMEX"].transform(normalize_by_first_value)
                df["LME Inv Normalised"] = df.groupby(df.index.year)["COPPER_LME"].transform(normalize_by_first_value)
                df["SHFE Inv Normalised"] = df.groupby(df.index.year)["COPPER_SHFE"].transform(normalize_by_first_value)
            else:
                df["TOTAL Inv Normalised"] = df.groupby(df.index.year)[f"{k}_TOTAL"].transform(normalize_by_first_value)
                df["LME Inv Normalised"] = df.groupby(df.index.year)[f"{k}_LME"].transform(normalize_by_first_value)
                df["SHFE Inv Normalised"] = df.groupby(df.index.year)[f"{k}_SHFE"].transform(normalize_by_first_value)
            if k in ["COPPER"]:
                df.columns = (
                    ["Total Inv", "WEST Inv", "LME Inv", "LME Cancelled Warrants", "COMEX Inv"]
                    + hg_sprd.columns.to_list()
                    + [
                        "SHFE Inv", "LME 3m", "Cash-3m", lme_sprd1, lme_sprd2, lme_sprd_3z, lme_sprd_zz,
                        shfe_sprd1, shfe_sprd2, shfe_sprd3, "SHFE Premium", "SHFE Premium vs LME", "SHFE vs LME Arb",
                        "TOTAL Inv Normalised", "WEST Inv Normalised", "COMEX Inv Normalised", "LME Inv Normalised", "SHFE Inv Normalised",
                    ]
                )
            elif k == "ALUMINIUM":
                df.columns = [
                    "Total Inv", "LME Inv", "LME Cancelled Warrants", "SHFE Inv", "LME 3m", "Cash-3m",
                    lme_sprd1, lme_sprd2, lme_sprd_3z, lme_sprd_zz, alumina_ticker, first_ticker,
                    shfe_sprd1, shfe_sprd2, shfe_sprd3, "SHFE Premium", "SHFE vs LME Arb",
                    "TOTAL Inv Normalised", "LME Inv Normalised", "SHFE Inv Normalised",
                ]
            else:
                df.columns = [
                    "Total Inv", "LME Inv", "LME Cancelled Warrants", "SHFE Inv", "LME 3m", "Cash-3m",
                    lme_sprd1, lme_sprd2, lme_sprd_3z, lme_sprd_zz,
                    shfe_sprd1, shfe_sprd2, shfe_sprd3, "SHFE Premium", "SHFE vs LME Arb",
                    "TOTAL Inv Normalised", "LME Inv Normalised", "SHFE Inv Normalised",
                ]
            fig_arb = chart.line_chart(
                df=shfe_arb.loc[shfe_arb.index >= shfe_arb.index[-1] - dt.timedelta(182), :],
                title=f"{k} SHFE vs LME Arb", y_axis_title="price", tickformat=None, width=750, height=500,
            )
            fig_arb.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
            fig_prem = chart.line_chart(
                df=df.loc[df.index >= df.index[-1] - dt.timedelta(182), ["SHFE Premium"]],
                title=f"{k} SHFE Premium", tickformat=None, width=750, height=500,
            )
            fig_prem.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
            figs_arb.append([fig_arb, fig_prem])
            arb_premium = {}
            total_inv_price = {}
            lme_inv_spread = {}
            shef_inv_spread = {}
            comex_inv_spread = {}
            if k == "ALUMINIUM":
                df_table_total = get_table(df, index_name=k, pct=[first_ticker, alumina_ticker])
            else:
                df_table_total = get_table(df, index_name=k)
            df_temp = df_table_total.loc[
                df_table_total.iloc[:, 0].isin(["LME 3m", "SHFE Premium", "SHFE vs LME Arb"]), :
            ]
            df_temp.rename(columns={k: "Arb & Premium"}, inplace=True)
            df_temp["Arb & Premium"] = [forward_ticker[:8], f"{k} SHFE Premium", f"{k} Arb"]
            df_arb_prem = pd.concat([df_arb_prem, df_temp], ignore_index=True, axis=0)
            if k in ["COPPER"]:
                output_table = table_format_html_copper(df_table_total.iloc[:-5], index_name=k)
                tbs_one.append(output_table)
                df = df.loc[df.index >= dt.datetime(2018, 1, 1), :]
                for idx, i in enumerate(df.columns):
                    if i.split(" ")[0] in ["LME", "SHFE", "COMEX", "Total"] and i.split(" ")[-1] == "Inv":
                        inv_chart = chart.seasonal_chart(df=df[i], ex2020=False, freq="B", title=i, x_axis_title="Date")
                        if "LME" == i.split(" ")[0]:
                            lme_inv_spread["inv"] = inv_chart
                        elif "SHFE" == i.split(" ")[0]:
                            shef_inv_spread["inv"] = inv_chart
                        elif "COMEX" == i.split(" ")[0]:
                            comex_inv_spread["inv"] = inv_chart
                        elif "Total" == i.split(" ")[0]:
                            total_inv_price["inv"] = inv_chart
                    elif i.split(" ")[0] in ["LME", "SHFE", "COMEX", "TOTAL"] and i.split(" ")[-1] == "Normalised":
                        inv_chart = chart.seasonal_chart(df=df[i], ex2020=False, freq="B", title=i, x_axis_title="Date")
                        if "LME" == i.split(" ")[0]:
                            lme_inv_spread["norm"] = inv_chart
                        elif "SHFE" == i.split(" ")[0]:
                            shef_inv_spread["norm"] = inv_chart
                        elif "COMEX" == i.split(" ")[0]:
                            comex_inv_spread["norm"] = inv_chart
                        elif "TOTAL" == i.split(" ")[0]:
                            total_inv_price["norm"] = inv_chart
                    elif i in ["SHFE Premium", "SHFE Premium vs LME", "SHFE vs LME Arb"]:
                        df_ = pd.concat([df[i].dropna(), df[i].dropna().rolling(5).mean()], axis=1).loc[today() - relativedelta(months=6):]
                        df_.columns = [i, "5d ma"]
                        prem_arb_chart = chart.line_chart(df=df_, title=i, tickformat=False, x_axis_title="Date")
                        if "SHFE Premium" == i:
                            arb_premium["premium"] = prem_arb_chart
                        elif "SHFE vs LME Arb" == i:
                            arb_premium["SHFE vs LME Arb"] = prem_arb_chart
                        elif "SHFE Premium vs LME" == i:
                            arb_premium["SHFE Premium vs LME"] = prem_arb_chart
                    elif idx == 5:
                        y1_data = df.iloc[:, [5, 6, 7, 8]].dropna().loc[today() - relativedelta(months=6):]
                        comex_inv_spread["sprd"] = chart.line_chart(
                            df=y1_data, title="COMEX spreads", tickformat=False, x_axis_title="Date", y_axis_title="Price",
                        )
                    elif idx == 11:
                        y1_data = df.iloc[:, [12, 13]].dropna().loc[today() - relativedelta(months=6):]
                        y2_data = df.iloc[:, [11, 14, 15]].dropna().loc[today() - relativedelta(months=6):]
                        y2_data.columns = [x + " R" for x in y2_data.columns]
                        cancelled_warrents_data = lme_cancelled_warrents[[f"{k}_cancelled_warrants"]].dropna().loc[today() - relativedelta(months=6):]
                        sprd_chart_lme = chart.line_chart(
                            df=y1_data, data_p1y2=y2_data, data_p2y1=cancelled_warrents_data,
                            secondary_y=True, subplots=2, title="LME spreads", tickformat=False,
                            x_axis_title="Date", y_axis_title="Price", p1y2_axis_title="Price", p2y1_axis_title="Inv (Ton)",
                        )
                        sprd_chart_lme.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
                        lme_inv_spread["sprd"] = sprd_chart_lme
                    elif idx in [12, 13, 14]:
                        pass
                    elif idx == 16:
                        shfe_sprd_plt = df.iloc[:, [16, 17, 18]].dropna().loc[today() - relativedelta(months=6):]
                        sprd_chart_shfe = chart.line_chart(df=shfe_sprd_plt, title="SHFE spreads", tickformat=False, x_axis_title="Date")
                        shef_inv_spread["sprd"] = sprd_chart_shfe
                    elif idx in [18, 19]:
                        pass
                    else:
                        if i == "LME 3m":
                            data = bbg.bdh(
                                forward_ticker,
                                ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_VOLUME"],
                                today() - relativedelta(months=6),
                                today() - relativedelta(days=1),
                            )
                            fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True, vertical_spacing=0.02)
                            fig.add_trace(
                                go.Candlestick(
                                    x=data.index, open=data["PX_OPEN"], high=data["PX_HIGH"],
                                    low=data["PX_LOW"], close=data["PX_LAST"], name="OHLC",
                                ), row=1, col=1,
                            )
                            fig.update_layout(xaxis_rangeslider_visible=False)
                            fig.add_trace(
                                go.Bar(name="Volume", x=data.index, y=data["PX_VOLUME"].values, showlegend=True), col=1, row=2,
                            )
                            fig.update_layout(
                                title={"text": f"{k.lower().capitalize()} {i} Price", "x": 0.5, "xanchor": "center"},
                                width=900, height=600,
                            )
                            data.index = pd.to_datetime(data.index)
                            dates = _generate_holiday_dates(min(data.index.year), max(data.index.year))
                            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=dates)], row=1, col=1)
                            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=dates)], row=2, col=1)
                            fig.update_yaxes(title_text="Price", row=1, col=1)
                            fig.update_xaxes(title_text="Date", row=2, col=1)
                            fig.update_yaxes(title_text="Volume", row=2, col=1)
                            price_chart = fig
                            total_inv_price["price"] = price_chart
                        else:
                            pass
            elif k == "ALUMINIUM":
                output_table = table_format_html_aluminium(df_table_total.iloc[:-3], index_name=k)
                tbs_one.append(output_table)
                figs = []
                df = df.loc[df.index >= dt.datetime(2018, 1, 1), :]
                for idx, i in enumerate(df.columns):
                    if i.split(" ")[0] in ["LME", "SHFE", "Total"] and i.split(" ")[-1] == "Inv":
                        inv_chart = chart.seasonal_chart(df=df[i], ex2020=False, freq="B", title=i, x_axis_title="Date")
                        if "LME" == i.split(" ")[0]:
                            lme_inv_spread["inv"] = inv_chart
                        elif "SHFE" == i.split(" ")[0]:
                            shef_inv_spread["inv"] = inv_chart
                        elif "Total" == i.split(" ")[0]:
                            total_inv_price["inv"] = inv_chart
                    elif i.split(" ")[0] in ["LME", "SHFE", "COMEX", "TOTAL"] and i.split(" ")[-1] == "Normalised":
                        inv_chart = chart.seasonal_chart(df=df[i], ex2020=False, freq="B", title=i, x_axis_title="Date")
                        if "LME" == i.split(" ")[0]:
                            lme_inv_spread["norm"] = inv_chart
                        elif "SHFE" == i.split(" ")[0]:
                            shef_inv_spread["norm"] = inv_chart
                        elif "TOTAL" == i.split(" ")[0]:
                            total_inv_price["norm"] = inv_chart
                    elif i in ["SHFE Premium", "SHFE vs LME Arb"]:
                        df_ = pd.concat([df[i].dropna(), df[i].dropna().rolling(5).mean()], axis=1).loc[today() - relativedelta(months=6):]
                        df_.columns = [i, "5d ma"]
                        prem_arb_chart = chart.line_chart(df=df_, title=i, tickformat=False, x_axis_title="Date")
                        if "SHFE Premium" == i:
                            arb_premium["premium"] = prem_arb_chart
                        elif "SHFE vs LME Arb" == i:
                            arb_premium["SHFE vs LME Arb"] = prem_arb_chart
                    elif idx == 5:
                        y1_data = df.iloc[:, [6, 7]].dropna().loc[today() - relativedelta(months=6):]
                        y2_data = df.iloc[:, [5, 8, 9]].dropna().loc[today() - relativedelta(months=6):]
                        y2_data.columns = [x + "_R" for x in y2_data.columns]
                        cancelled_warrents_data = lme_cancelled_warrents[[f"{k}_cancelled_warrants"]].dropna().loc[today() - relativedelta(months=6):]
                        sprd_chart_lme = chart.line_chart(
                            df=y1_data, data_p1y2=y2_data, data_p2y1=cancelled_warrents_data,
                            secondary_y=True, subplots=2, title="LME spreads", tickformat=False,
                            x_axis_title="Date", y_axis_title="Price", p1y2_axis_title="Price", p2y1_axis_title="Inv (Ton)",
                        )
                        sprd_chart_lme.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
                        lme_inv_spread["sprd"] = sprd_chart_lme
                    elif idx in [6, 7, 8, 9]:
                        pass
                    elif idx == 12:
                        shfe_sprd_plt = df.iloc[:, [12, 13, 14]].dropna().loc[today() - relativedelta(months=6):]
                        sprd_chart_shfe = chart.line_chart(df=shfe_sprd_plt, title="SHFE spreads", tickformat=False, x_axis_title="Date")
                        shef_inv_spread["sprd"] = sprd_chart_shfe
                    elif idx in [13, 14]:
                        pass
                    else:
                        price_chart = chart.line_chart(
                            df=df[[first_ticker]].dropna().loc[today() - relativedelta(months=6):],
                            data_p1y2=df[[alumina_ticker]].reindex(df[[first_ticker]].dropna().index).loc[today() - relativedelta(months=6):],
                            title=f"{k.lower().capitalize()} {i} Price", tickformat=False, secondary_y=True,
                            x_axis_title="Date", y_axis_title=first_ticker, p1y2_axis_title=alumina_ticker,
                        )
                        total_inv_price["price"] = price_chart
            else:
                output_table = table_format_html(df_table_total.iloc[:-3], index_name=k)
                tbs_one.append(output_table)
                figs = []
                df = df.loc[df.index >= dt.datetime(2018, 1, 1), :]
                for idx, i in enumerate(df.columns):
                    if i.split(" ")[0] in ["LME", "SHFE", "Total"] and i.split(" ")[-1] == "Inv":
                        inv_chart = chart.seasonal_chart(df=df[i], ex2020=False, freq="B", title=i, x_axis_title="Date")
                        if "LME" == i.split(" ")[0]:
                            lme_inv_spread["inv"] = inv_chart
                        elif "SHFE" == i.split(" ")[0]:
                            shef_inv_spread["inv"] = inv_chart
                        elif "Total" == i.split(" ")[0]:
                            total_inv_price["inv"] = inv_chart
                    elif i.split(" ")[0] in ["LME", "SHFE", "COMEX", "TOTAL"] and i.split(" ")[-1] == "Normalised":
                        inv_chart = chart.seasonal_chart(df=df[i], ex2020=False, freq="B", title=i, x_axis_title="Date")
                        if "LME" == i.split(" ")[0]:
                            lme_inv_spread["norm"] = inv_chart
                        elif "SHFE" == i.split(" ")[0]:
                            shef_inv_spread["norm"] = inv_chart
                        elif "TOTAL" == i.split(" ")[0]:
                            total_inv_price["norm"] = inv_chart
                    elif i in ["SHFE Premium", "SHFE vs LME Arb"]:
                        df_ = pd.concat([df[i].dropna(), df[i].dropna().rolling(5).mean()], axis=1).loc[today() - relativedelta(months=6):]
                        df_.columns = [i, "5d ma"]
                        prem_arb_chart = chart.line_chart(df=df_, title=i, tickformat=False, x_axis_title="Date")
                        if "SHFE Premium" == i:
                            arb_premium["premium"] = prem_arb_chart
                        elif "SHFE vs LME Arb" == i:
                            arb_premium["SHFE vs LME Arb"] = prem_arb_chart
                    elif idx == 5:
                        y1_data = df.iloc[:, [6, 7]].dropna().loc[today() - relativedelta(months=6):]
                        y2_data = df.iloc[:, [5, 8, 9]].dropna().loc[today() - relativedelta(months=6):]
                        y2_data.columns = [x + "_R" for x in y2_data.columns]
                        cancelled_warrents_data = lme_cancelled_warrents[[f"{k}_cancelled_warrants"]].dropna().loc[today() - relativedelta(months=6):]
                        sprd_chart_lme = chart.line_chart(
                            df=y1_data, data_p1y2=y2_data, data_p2y1=cancelled_warrents_data,
                            secondary_y=True, subplots=2, title="LME spreads", tickformat=False,
                            x_axis_title="Date", y_axis_title="Price", p1y2_axis_title="Price", p2y1_axis_title="Inv (Ton)",
                        )
                        sprd_chart_lme.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
                        lme_inv_spread["sprd"] = sprd_chart_lme
                    elif idx in [6, 7, 8, 9]:
                        pass
                    elif idx == 10:
                        y1_data = df.iloc[:, [10, 11, 12]].dropna().loc[today() - relativedelta(months=6):]
                        sprd_chart_shfe = chart.line_chart(df=y1_data, title="SHFE spreads", tickformat=False, x_axis_title="Date")
                        shef_inv_spread["sprd"] = sprd_chart_shfe
                    elif idx in [11, 12]:
                        pass
                    else:
                        if i == "LME 3m":
                            data = bbg.bdh(
                                forward_ticker,
                                ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_VOLUME"],
                                today() - relativedelta(months=6),
                                today() - relativedelta(days=1),
                            )
                            fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True, vertical_spacing=0.02)
                            fig.add_trace(
                                go.Candlestick(
                                    x=data.index, open=data["PX_OPEN"], high=data["PX_HIGH"],
                                    low=data["PX_LOW"], close=data["PX_LAST"], name="OHLC",
                                ), row=1, col=1,
                            )
                            fig.update_layout(xaxis_rangeslider_visible=False)
                            fig.add_trace(
                                go.Bar(name="Volume", x=data.index, y=data["PX_VOLUME"].values, showlegend=True), col=1, row=2,
                            )
                            fig.update_layout(
                                title={"text": f"{k.lower().capitalize()} {i} Price", "x": 0.5, "xanchor": "center"},
                                width=900, height=600,
                            )
                            data.index = pd.to_datetime(data.index)
                            dates = _generate_holiday_dates(min(data.index.year), max(data.index.year))
                            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=dates)], row=1, col=1)
                            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(values=dates)], row=2, col=1)
                            fig.update_yaxes(title_text="Price", row=1, col=1)
                            fig.update_xaxes(title_text="Date", row=2, col=1)
                            fig.update_yaxes(title_text="Volume", row=2, col=1)
                            price_chart = fig
                        total_inv_price["price"] = price_chart
            if k in ["COPPER"]:
                orderd_figs = (
                    [total_inv_price.get("inv"), total_inv_price.get("norm"), total_inv_price.get("price")]
                    + [lme_inv_spread.get("inv"), lme_inv_spread.get("norm"), lme_inv_spread.get("sprd")]
                    + [comex_inv_spread.get("inv"), comex_inv_spread.get("norm"), comex_inv_spread.get("sprd")]
                    + [shef_inv_spread.get("inv"), shef_inv_spread.get("norm"), shef_inv_spread.get("sprd")]
                    + [comex_arb_chart, arb_premium.get("SHFE vs LME Arb"), arb_premium.get("premium"), arb_premium.get("SHFE Premium vs LME")]
                )
            else:
                orderd_figs = (
                    [total_inv_price.get("inv"), total_inv_price.get("norm"), total_inv_price.get("price")]
                    + [lme_inv_spread.get("inv"), lme_inv_spread.get("norm"), lme_inv_spread.get("sprd")]
                    + [shef_inv_spread.get("inv"), shef_inv_spread.get("norm"), shef_inv_spread.get("sprd")]
                    + [arb_premium.get("SHFE vs LME Arb"), arb_premium.get("premium")]
                )
            figs = to_html._figure_to_html_table(orderd_figs, num_columns=3, email_mode=False)
            table.figures_to_html(
                [figs], filename=f"{html_path}\\cross_cmds\\links\\base_metal_charts_{k}.html", task_name=report_name,
            )
            output_table = output_table.replace(
                k,
                '<a href="{}\\cross_cmds\\links\\base_metal_charts_{}.html">{}</a><br>'.format(html_path, k, k),
            )
            tbs.append(output_table)
            tbs.append("<br>")
            tbs.append("<br>")
            tbs_one.append("<br>")
            tbs_one.append(_unrecovered("base_metal_inventory.py line 1557 highlight description tail", "Highlight colors: green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. Data starts"))
            tbs_one.append("Latest inventory is highlighted vs 20d average. 5d average is highlighted vs 3m average. <br>")
            tbs_one.append(
                "SHFE daily inventory is estimated from daily warrants data when available. "
                "It is replaced with weekly data on Friday.<br>"
            )
            tbs_one.append("<br>")
            tbs_one = tbs_one + [figs]
            table.figures_to_html(
                tbs_one, filename=f"{html_path}\\cross_cmds\\base_metal_inventory_{k}.html", task_name=report_name,
            )
    tbs.append(_unrecovered("base_metal_inventory.py line 1574 highlight description tail", "Highlight colors: green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. Data starts from 201"))
    tbs.append("Latest inventory is highlighted vs 20d average. 5d average is highlighted vs 3m average. <br>")
    tbs.append(
        "SHFE daily inventory is estimated from daily warrants data when available. "
        "It is replaced with weekly data on Friday.<br>"
    )
    table.figures_to_html(tbs, filename=f"{html_path}\\cross_cmds\\base_metal_inventory.html", task_name=report_name)
    arb_prem_html = table.html_format(
        df=df_arb_prem,
        precision=0,
        hide_cols=["mean", "std", "mean_5d", "std_5d", "mean_20d", "std_20d"],
        format_column={
            "Arb & Premium": {"width": "140px", "text-align": "left"},
            "Latest": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["Latest", "mean", "std"],
            },
            "Change on day": {"width": "100px", "text-align": "center"},
            "5day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["5day change", "mean_5d", "std_5d"],
            },
            "20day change": {
                "width": "100px",
                "text-align": "center",
                "highlight_z": ["20day change", "mean_20d", "std_20d"],
            },
            "3month change": {"width": "100px", "text-align": "center"},
            "YTD": {"width": "100px", "text-align": "center"},
        },
        format_row={
            "0": {"format": "{0:.2%}", "columns": df_arb_prem.columns[2:-1]},
            "1": {"format": "{0:.0f}", "columns": df_arb_prem.columns[1:-1]},
            "2": {
                "bottom_border": True,
                "format": {"format": "{0:.1f}", "columns": df_arb_prem.columns[1:-1]},
            },
            "3": {"format": "{0:.2%}", "columns": df_arb_prem.columns[2:-1]},
            "4": {"format": "{0:.0f}", "columns": df_arb_prem.columns[1:-1]},
            "5": {
                "bottom_border": True,
                "format": {"format": "{0:.1f}", "columns": df_arb_prem.columns[1:-1]},
            },
            "6": {"format": "{0:.2%}", "columns": df_arb_prem.columns[2:-1]},
            "7": {"format": "{0:.0f}", "columns": df_arb_prem.columns[1:-1]},
            "8": {
                "bottom_border": True,
                "format": {"format": "{0:.1f}", "columns": df_arb_prem.columns[1:-1]},
            },
            "9": {"format": "{0:.2%}", "columns": df_arb_prem.columns[2:-1]},
            "10": {"format": "{0:.0f}", "columns": df_arb_prem.columns[1:-1]},
            "11": {"format": "{0:.0f}", "columns": df_arb_prem.columns[1:-1]},
        },
    )
    figs_arb.insert(3, arb_prem_html)
    table.to_html(
        figs_arb, path=f"{html_path}\\cross_cmds\\metal\\base_metal_arb_premium.html", task_name=report_name,
    )
    send_email(
        send_to=send_to, subject=report_name, body=tbs,
        html_path=f"{html_path}\\cross_cmds\\base_metal_inventory.html", task_name=report_name,
    )


def update():
    update_base_metal()


if __name__ == "__main__":
    update()
