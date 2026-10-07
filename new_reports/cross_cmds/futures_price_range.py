import pandas as pd
import numpy as np
import datetime as dt
import time
import sys
from pathlib import Path
from ecm.cmds.config import root_path, html_path, oil_group, macro_group, gas_group, data_path
import re
sys.path.append(f"{root_path}\\autoreports\\reports\\cross_cmds")
import sma200dw
from pandas.tseries.offsets import BDay
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.talib as talib
import ecm.cmds.time_series as ts
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux
from ecm.cmds.cdr import today, getworkingdays, CDR
from dateutils import relativedelta

send_to_dev = None  # ["ltrindade"]
send_to_gas = send_to_dev or gas_group
send_to = send_to_dev or ["rzhao@elementcapital.com"]
report_name = "Energy futures price range"
file_name = "futures_price_range"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"


def _unrecovered(location, *visible_values):
    raise NotImplementedError(f"Photographed source is clipped or absent: {location}")


def add_schedule():
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2023, 7, 1, 6, 10),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


ins_list = ["CLA Comdty", "COA Comdty", "DATA Comdty", "XBA Comdty", "HOA Comdty", "QSA Comdty", "NGA Comdty", "TZTA Comdty"]
oil_list = ["CLA Comdty", "COA Comdty", "DATA Comdty"]
oil_products_list = ["XBA Comdty", "HOA Comdty", "QSA Comdty"]
flat_m_list = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]
flat_m_list_qz = ["F", "J", "N", "V"]
flat_m_list_qq = ["J", "V"]
sprd_m_list = ["F-G", "G-H", "H-J", "J-K", "K-M", "M-N", "N-Q", "Q-U", "U-V", "V-X", "X-Z", "Z-F"]
sprd_m_list_qz = ["F-J", "J-N", "N-V", "V-F"]
sprd_m_list_qq = ["J-V", "V-J"]


def synthetic_spread(active, y, m, far_y=None, far_m=None, sdate=None, edate=None, pct=False):
    """
    synthetic spread is calculated as front outright contact - far outright contract
    """
    if active in ["LPA Comdty", "LAA Comdty", "LXA Comdty", "LNA Comdty"]:
        fields = ["LAST_PRICE"]
    else:
        fields = ["PX_LAST"]
    front = pyg.get_data("contracts_PX_LAST", active=active, y=y, m=m)
    far = pyg.get_data("contracts_PX_LAST", active=active, y=far_y, m=far_m)
    if pct:
        spread = (front - far) / far
    else:
        spread = front - far
    spread.columns = ["PX_LAST"]
    return spread.loc[sdate:edate, :]


def get_outright_physical_data(active="Crd-P-US", drop_year=True):
    """Simple split a full timeseries by year, there are no contracts for physicals"""
    outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
    if active == "CLA Comdty":
        data = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_us.csv", index_name="date")
        phys_ticker = "Crd-P-US"
        data = data[phys_ticker]
    elif active == "COA Comdty":
        data = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_eu.csv", index_name="date")
        phys_ticker = "Crd-P-EU"
        data = data[phys_ticker]
    elif active == "DATA Comdty":
        data = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_asia.csv", index_name="date")
        phys_ticker = "Crd-P-Asia"
        data = data["Crd-P-A"]
        data.name = phys_ticker
    else:
        raise ValueError("active must be one of CLA Comdty, COA Comdty, DATA Comdty")
    data_start_month = data.index[0].month
    if data_start_month != 1:
        pad_start_date = dt.datetime(data.index[0].year, 1, 1)
        pad_dates = pd.date_range(start=pad_start_date, end=today(), freq="B")
        data = data.reindex(pad_dates)
    data_by_year = ts.data_by_year(data, freq="B")
    if drop_year:
        for yr in [2020, 2022]:
            if yr in data_by_year:
                data_by_year.pop(yr)
    data_by_year.columns = [f"{phys_ticker} {col}" for col in data_by_year.columns]
    dts = pd.date_range(start=dt.datetime(today().year, 1, 1), end=dt.datetime(today().year, 12, 31), freq="B")
    if len(dts) < data_by_year.shape[0]:
        data_by_year = data_by_year.iloc[:len(dts), :]
    data_by_year.index = dts
    data_by_year.index.name = "dates"
    return data_by_year, data_by_year.columns[-1]


def get_outright_data(active="CLA Comdty", mon=None, window=10, by_month=True, drop_year=False, custom_drop_year=None):
    contracts_ori = pyg.get_data("contracts", active=active, item="fut_chain")
    contracts = contracts_ori.copy()
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts["t1"] = contracts["t"].shift(1)
    if active == "DATA Comdty":
        contracts["last_t"] = contracts["last_t"].shift(1)
        contracts["t"] = contracts["t"].shift(1)
        contracts["t1"] = contracts["t"].shift(1)
    live_contract = contracts.iloc[np.where(contracts["t"] > today())[0][0], :]
    if by_month:
        if mon is None:
            same_month_contract = contracts.loc[
                (contracts["m"] == live_contract["m"]) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
            ]
        else:
            same_month_contract = contracts.loc[
                (contracts["m"] == mon) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
            ]
    else:
        same_month_contract = contracts.loc[
            contracts.loc[contracts["ticker"] == live_contract["ticker"], :].index[0] - window:contracts.loc[contracts["ticker"] == live_contract["ticker"], :].index[0], :
        ]
    if drop_year:
        with pd.option_context("mode.chained_assignment", None):
            same_month_contract.drop(
                same_month_contract.loc[same_month_contract["y"].isin([2020, 2022] if not custom_drop_year else custom_drop_year)].index,
                axis=0, inplace=True,
            )
    data = pd.DataFrame()
    for idx, row in same_month_contract.iterrows():
        price = pyg.get_data("contracts_PX_LAST", active=active, m=row["m"], y=row["y"])
        if row["ticker"] == live_contract["ticker"]:
            live_price = bbg.bdh(row["ticker"], ["PX_LAST"], sdate=price.index[-1], edate=today() + BDay(1))
            price = pd.concat([price.iloc[:-1, :], live_price], axis=0)
        price = price.loc[row["t1"] - dt.timedelta(days=14):row["last_t"], "PX_LAST"]
        if row["ticker"] == live_contract["ticker"]:
            data = data.iloc[::-1].reset_index(drop=True)
            data[row["ticker"]] = price.reset_index(drop=True)
        else:
            data[row["ticker"]] = price.iloc[::-1].reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract["t1"] - dt.timedelta(days=14), t1=_unrecovered("futures_price_range.py line182 live_contract date key", live_contract))
    trade_dates = pd.DatetimeIndex(trade_dates)
    trade_dates = price.index.union(trade_dates[np.where(trade_dates > price.index[-1])])
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    try:
        data["dates"] = trade_dates
    except:
        print("stop")
    data.set_index("dates", inplace=True)
    return data.iloc[:-1, :], live_contract["ticker"]


def get_spread_data(active="CLA Comdty", spread=1, mon=None, window=10, by_month=True, drop_year=False, custom_drop_year=None):
    contracts_ = pyg.get_data("spreads", active=active, item="sprd_chain")
    contracts = contracts_.copy()
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts["t1"] = contracts["t"].shift(1)
    contracts.reset_index(inplace=True, drop=True)
    if active == "DATA Comdty":
        contracts["last_t"] = contracts["last_t"].shift(1)
        contracts["t"] = contracts["t"].shift(1)
        contracts["t1"] = contracts["t"].shift(1)
    if isinstance(spread, int) and spread > 1:
        contracts["t"] = contracts["t"].shift(spread - 1)
        contracts["t1"] = contracts["t1"].shift(spread - 1)
    elif spread == "2-6":
        contracts["far_y"] = contracts["far_y"].fillna(0).astype(str)
        contracts["t"] = contracts["t"].shift(1)
        contracts["t1"] = contracts["t1"].shift(1)
        contracts["far_m"] = contracts["far_m"].shift(-3)
        contracts["far_y"] = contracts["far_y"].shift(-3)
        contracts = contracts.loc[~contracts["far_m"].isna()]
        contracts["ticker"] = [f"{x['ticker'].split(' ')[0]} {x['m']}{str(x['y'])[-2:]}-{x['far_m']}{str(int(float(x['far_y'])))[-2:]} Comdty" for _, x in contracts.iterrows()]
    live_contract = contracts.iloc[np.where(contracts["t"] >= today())[0][0], :]
    if by_month:
        if mon is None:
            same_month_contract = contracts.loc[
                (contracts["m"] == live_contract["m"]) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
            ]
        else:
            same_month_contract = contracts.loc[
                (contracts["m"] == mon) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
            ]
    else:
        same_month_contract = contracts.iloc[live_contract.index - window:live_contract.index, :]
    if drop_year:
        with pd.option_context("mode.chained_assignment", None):
            same_month_contract.drop(
                same_month_contract.loc[same_month_contract["y"].isin([2020, 2022] if not custom_drop_year else custom_drop_year)].index,
                axis=0, inplace=True,
            )
    data = pd.DataFrame()
    for idx, row in same_month_contract.iterrows():
        if active == "TZTA Comdty" or spread == "2-6":
            price = synthetic_spread(active=active, m=row["m"], y=int(row["y"]), far_m=row["far_m"], far_y=int(float(row["far_y"])))
            if active == "TZTA Comdty" and row["y"] == today().year:
                ticker = f"{active[:3]}{row['m']}{str(row['y'])[-1]}{row['far_m']}{str(int(float(row['far_y'])))[-1]} Comdty"
                print(ticker)
                price = bbg.bdh(ticker, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
        else:
            price = pyg.get_data("spreads_PX_LAST", active=active, m=row["m"], y=row["y"], far_m=row["far_m"], far_y=row["far_y"])
            price.columns = ["PX_LAST"]
            if row["ticker"] == live_contract["ticker"]:
                live_price = bbg.bdh(row["ticker"], ["PX_LAST"], sdate=price.index[-1], edate=today() + BDay(1))
                price = pd.concat([price.iloc[:-1, :], live_price], axis=0)
        if isinstance(price.columns, pd.MultiIndex):
            price = price[ticker]
        price = price.loc[row["t1"] - dt.timedelta(days=14):today(), "PX_LAST"]
        if row["ticker"] == live_contract["ticker"]:
            data = data.iloc[::-1].reset_index(drop=True)
            data[row["ticker"]] = price.reset_index(drop=True)
        else:
            data[row["ticker"]] = price.iloc[::-1].reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract["t1"] - dt.timedelta(days=14), t1=today())  # live
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data["dates"] = trade_dates
    data.set_index("dates", inplace=True)
    return data.iloc[:-1, :], live_contract["ticker"]


MONTH_CODE_TO_NUM = {"F":1,"G":2,"H":3,"J":4,"K":5,"M":6,"N":7,"Q":8,"U":9,"V":10,"X":11,"Z":12}


def is_over_year_pair(near_code: str, far_code: str) -> bool:
    a = MONTH_CODE_TO_NUM[near_code]
    b = MONTH_CODE_TO_NUM[far_code]
    return (a > b) or (a == b)  # VF true, ZZ true; FH/HJ/JV false


def get_spread_special_zz(
    active: str = "CLA Comdty",
    spread: str | None = None,
    mon: str | None = None,
    window: int = 10,
    drop_year: bool = False,
) -> tuple[pd.DataFrame, str]:
    """
    Calendar-aligned special spread history.

    For the live spread contract:
        ref axis = (live t1 - 14 days) through min(today, live last_t).
    For each historical year in the window (same front month):
        Take the price observed on the SAME calendar Month-Day (mapped into that year).
        If that date is outside the contract's life ((t1-14d) .. last_t) -> NaN.

    Result:
        DataFrame indexed by the live contract date axis (current year's dates),
        columns = individual historical spreads (oldest -> newest, live last),
        values = like-for-like calendar-day comparisons.
    """
    code_map = {"ZZ": ["Z", "Z"]}
    months = code_map.get(spread)
    if months is None:
        raise ValueError(f"Unsupported spread {spread}")
    contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
    df = contracts_.copy()
    df.rename(columns={"t3": "t"}, inplace=True)
    df = df[df["m"].isin(months)].copy()
    df = df.sort_values(["y", "m", "t"]).reset_index(drop=True)
    over_year = is_over_year_pair(months[0], months[1])
    near_code, far_code = months
    df_near = df[df["m"] == near_code].copy()
    df_near["far_y"] = df_near["y"] + (1 if over_year else 0)  # key line
    df_near["far_m"] = far_code
    df_far = df[df["m"] == far_code][["y", "ticker"]].copy().rename(columns={"y": "far_y", "ticker": "far_ticker"})
    df = df_near.merge(df_far, on="far_y", how="left")
    df = df.sort_values(["y", "t"]).reset_index(drop=True)
    df["t1"] = df["t"].shift(1)
    live_contract = df.iloc[np.where(df["t"] >= today())[0][0], :]
    if mon is None:
        same = df.loc[
            (df["m"] == live_contract["m"])
            & (df["y"] <= live_contract["y"])
            & (df["y"] >= live_contract["y"] - window), :
        ]
    else:
        same = df.loc[
            (df["m"] == mon)
            & (df["y"] <= live_contract["y"])
            & (df["y"] >= live_contract["y"] - window), :
        ]
    if drop_year:
        same = same[~same["y"].isin([2020, 2022])]
    live_idx = np.where(same["t"] >= today())[0][0]
    live_contract = same.iloc[live_idx, :]
    prefix = (active[:2] * 2) if active not in ["TZTA Comdty", "DATA Comdty"] else (active[:3] * 2)
    ret_ticker = (
        f"S:{prefix} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-"
        f"{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty"
    )
    anchor_end = min(today(), live_contract["last_t"])
    ref_start = live_contract["t1"] - dt.timedelta(days=14)
    ref_dates = pd.DatetimeIndex(CDR(active=active).drange(t0=ref_start, t1=anchor_end))
    cols: dict[str, pd.Series] = {}
    for _, row in same.iterrows():
        yr = int(row["y"])
        ticker = f"S:{prefix} {row['m']}{str(yr)[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        ser_df = synthetic_spread(active=active, m=row["m"], y=yr, far_m=row["far_m"], far_y=int(row["far_y"]))
        series = ser_df["PX_LAST"]
        if yr >= today().year:
            real = bbg.bdh(ticker, ["PX_LAST"], sdate=series.index[0], edate=anchor_end)["PX_LAST"]
            if not real.empty:
                series = real
        t1_val = row["t1"] if pd.notna(row["t1"]) else (row["t"] - dt.timedelta(days=30))
        slice_start = t1_val - dt.timedelta(days=14)
        slice_end = row["last_t"]
        if slice_end < dt.datetime(slice_end.year, today().month, today().day) and not live_contract.equals(row):
            next_yr = yr + 1
            next_ticker = f"S:{prefix} {row['m']}{str(next_yr)[-2:]}-{row['far_m']}{str(int(row['far_y']) + 1)[-2:]} Comdty"
            print(f"Extending series for {ticker} with {next_ticker}")
            next_ser_df = synthetic_spread(active=active, m=row["m"], y=next_yr, far_m=row["far_m"], far_y=int(row["far_y"]) + 1)
            next_series = next_ser_df["PX_LAST"]
            series = series.combine_first(next_series)
        values = []
        for d in ref_dates:
            if yr > today().year:
                yr = today().year
            try:
                mapped = d.replace(year=yr)
                if mapped > today() and d <= today():
                    mapped = d
            except ValueError:
                values.append(np.nan)
                continue
            if mapped < slice_start:
                values.append(np.nan)
            elif mapped.day_of_week in [5, 6] or mapped > today():
                values.append(np.nan)
            elif mapped.year == today().year and not live_contract.equals(row):
                values.append(np.nan)
            else:
                values.append(series.get(mapped, np.nan))
        cols[ticker] = pd.Series(values, index=ref_dates)
    data = pd.DataFrame(cols)
    data.index = ref_dates
    return data, ret_ticker


def get_spread_special_calendar2(
    active: str = "CLA Comdty",
    spread: str | None = None,
    mon: str | None = None,
    window: int = 10,
    drop_year: bool = False,
) -> tuple[pd.DataFrame, str]:
    """
    Calendar-aligned special spread history.

    For the live spread contract:
        ref axis = (live t1 - 14 days) through min(today, live last_t).
    For each historical year in the window (same front month):
        Take the price observed on the SAME calendar Month-Day (mapped into that year).
        If that date is outside the contract's life ((t1-14d) .. last_t) -> NaN.

    Result:
        DataFrame indexed by the live contract date axis (current year's dates),
        columns = individual historical spreads (oldest -> newest, live last),
        values = like-for-like calendar-day comparisons.
    """
    code_map = {"FH": ["F", "H"], "HJ": ["H", "J"], "JV": ["J", "V"], "ZZ": ["Z", "Z"], "VF": ["V", "F"]}
    months = code_map.get(spread)
    if months is None:
        raise ValueError(f"Unsupported spread {spread}")
    contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
    df = contracts_.copy()
    df.rename(columns={"t3": "t"}, inplace=True)
    df = df[df["m"].isin(months)].copy()
    df = df.sort_values(["y", "m", "t"]).reset_index(drop=True)
    over_year = is_over_year_pair(months[0], months[1])
    near_code, far_code = months
    near_month = MONTH_CODE_TO_NUM[near_code]
    df_near = df[df["m"] == near_code].copy()
    df_near["far_y"] = df_near["y"] + (1 if over_year else 0)  # key line
    df_near["far_m"] = far_code
    df_far = df[df["m"] == far_code][["y", "ticker"]].copy().rename(columns={"y": "far_y", "ticker": "far_ticker"})
    df = df_near.merge(df_far, on="far_y", how="left")
    df = df.sort_values(["y", "t"]).reset_index(drop=True)
    df["t1"] = df["t"].shift(1)
    live_contract = df.iloc[np.where(df["t"] >= today())[0][0], :]
    if mon is None:
        same = df.loc[
            (df["m"] == live_contract["m"])
            & (df["y"] <= live_contract["y"])
            & (df["y"] >= live_contract["y"] - window), :
        ]
    else:
        same = df.loc[
            (df["m"] == mon)
            & (df["y"] <= live_contract["y"])
            & (df["y"] >= live_contract["y"] - window), :
        ]
    if drop_year:
        same = same[~same["y"].isin([2020, 2022])]
    live_idx = np.where(same["t"] >= today())[0][0]
    live_contract = same.iloc[live_idx, :]
    prefix = (active[:2] * 2) if active not in ["TZTA Comdty", "DATA Comdty"] else (active[:3] * 2)
    ret_ticker = (
        f"S:{prefix} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-"
        f"{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty"
    )
    anchor_end = min(today(), live_contract["last_t"])
    ref_start = live_contract["t1"] - dt.timedelta(days=14)
    ref_dates = pd.DatetimeIndex(CDR(active=active).drange(t0=ref_start, t1=anchor_end))
    cols: dict[str, pd.Series] = {}
    for _, row in same.iterrows():
        yr = int(row["y"])
        ticker = f"S:{prefix} {row['m']}{str(yr)[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        ser_df = synthetic_spread(active=active, m=row["m"], y=yr, far_m=row["far_m"], far_y=int(row["far_y"]))
        series = ser_df["PX_LAST"]
        if yr >= today().year:
            real = bbg.bdh(ticker, ["PX_LAST"], sdate=series.index[0], edate=anchor_end)["PX_LAST"]
            if not real.empty:
                series = real
        t1_val = row["t1"] if pd.notna(row["t1"]) else (row["t"] - dt.timedelta(days=30))
        slice_start = t1_val - dt.timedelta(days=14)
        slice_end = row["last_t"]
        hist_year = yr
        season_start_month = near_month  # anchor on NEAR leg month (e.g., V=Oct, Z=Dec)
        values = []
        for d in ref_dates:
            target_year = (hist_year - 1) if (d.month >= season_start_month) else hist_year
            if target_year > today().year:
                target_year = today().year
            try:
                mapped = d.replace(year=target_year)
                if mapped > today() and d <= today():
                    mapped = d
            except ValueError:
                values.append(np.nan)
                continue
            if (mapped < slice_start) or (mapped > slice_end):
                values.append(np.nan)
            else:
                values.append(series.get(mapped, np.nan))
        cols[ticker] = pd.Series(values, index=ref_dates)
    data = pd.DataFrame(cols)
    data.index = ref_dates
    return data, ret_ticker


def get_quarter_spread_data(active="CLA Comdty", spread=1, mon=None, window=10, drop_year=False, custom_drop_year=None):
    contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
    contracts = contracts_.copy()
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts = contracts.loc[contracts["m"].isin(["H", "M", "U", "Z"]), :]
    contracts["far_m"] = contracts["m"].shift(-1)
    contracts["far_y"] = contracts["y"].shift(-1)
    contracts["far_ticker"] = contracts["ticker"].shift(-1)
    contracts["t1"] = contracts["t"].shift(1)
    if isinstance(spread, int) and spread > 1:
        contracts["t"] = contracts["t"].shift(spread - 1)
        contracts["t1"] = contracts["t1"].shift(spread - 1)
    live_contract = contracts.iloc[np.where(contracts["t"] >= today())[0][0], :]
    if mon is None:
        same_month_contract = contracts.loc[
            (contracts["m"] == live_contract["m"]) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
        ]
    else:
        same_month_contract = contracts.loc[
            (contracts["m"] == mon) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
        ]
    if drop_year:
        with pd.option_context("mode.chained_assignment", None):
            same_month_contract.drop(
                same_month_contract.loc[same_month_contract["y"].isin([2020, 2022] if not custom_drop_year else custom_drop_year)].index,
                axis=0, inplace=True,
            )
    data = pd.DataFrame()
    same_month_contract.dropna(inplace=True)
    for idx, row in same_month_contract.iterrows():
        if active in ["TZTA Comdty", "DATA Comdty"]:
            ticker = f"S:{active[:3]}{active[:3]} {row['m']}{str(row['y'])[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        else:
            ticker = f"S:{active[:2]}{active[:2]} {row['m']}{str(row['y'])[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        price = synthetic_spread(active=active, m=row["m"], y=int(row["y"]), far_m=row["far_m"], far_y=int(row["far_y"]))
        if row["y"] >= today().year:
            print(ticker)
            price = bbg.bdh(ticker, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
        if isinstance(price.columns, pd.MultiIndex):
            price = price[ticker]
        price = price.loc[row["t1"] - dt.timedelta(days=14):today(), "PX_LAST"]
        if idx == same_month_contract.index[-1]:
            data = data.iloc[::-1].reset_index(drop=True)
            data[ticker] = price.reset_index(drop=True)
        else:
            data[ticker] = price.iloc[::-1].reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract["t1"] - dt.timedelta(days=14), t1=today())
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data["dates"] = trade_dates
    data.set_index("dates", inplace=True)
    if active in ["TZTA Comdty", "DATA Comdty", "QQTA Comdty", "QZTA Comdty"]:
        ret_ticker = f"S:{active[:3]}{active[:3]} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty"
    else:
        ret_ticker = (
            f"S:{active[:2]}{active[:2]} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-"
            f"{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty"
        )
    return data.iloc[:-1, :], ret_ticker  # (f"S:{active[:2]}{active[:2]} {live_contract['m']}{str(int(live


def get_synthetic_spread(active="CLA Comdty", spread=1, go=None):
    if active in [
        "LPA Comdty", "LAA Comdty", "LXA Comdty", "LNA Comdty", "CCA Comdty", "KCA Comdty",
        "CTA Comdty", "LCA Comdty", "FCA Comdty", "LHA Comdty", "GCA Comdty", "SIA Comdty",
    ]:
        contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
        contracts = contracts_.copy()
        contracts.rename(columns={"t3": "t"}, inplace=True)
    else:
        contracts_ = pyg.get_data("spreads", active=active, item="sprd_chain")
        contracts = contracts_.copy()
        contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts["t1"] = contracts["t"].shift(1)
    if isinstance(spread, int) and spread > 1:
        contracts["t"] = contracts["t"].shift(spread - 1)
        contracts["t1"] = contracts["t1"].shift(spread - 1)
    elif spread == "1-13":
        contracts["far_m"] = contracts["m"]
        contracts["far_y"] = contracts["y"] + 1
    live_contract = contracts.iloc[np.where(contracts["t"] >= today())[0][0], :]
    same_month_contract = contracts.loc[
        (contracts["m"] == live_contract["m"]) & (contracts["y"] <= live_contract["y"]) & _unrecovered("futures_price_range.py line734 year-window condition", contracts, live_contract), :
    ]
    data = pd.DataFrame()
    for idx, row in same_month_contract.iterrows():
        price = synthetic_spread(active=active, m=row["m"], y=row["y"], far_m=row["far_m"], far_y=row["far_y"], go=go, pct=True)
        if row["y"] == today().year:
            if active in ["C A Comdty", "S A Comdty", "W A Comdty"]:
                ticker = f"{active[0]} {row['m']}{str(row['y'])[-1]}{active[0]} {row['far_m']}{str(row['far_y'])[-1]} Comdty"
            else:
                ticker = f"{active[:2]}{row['m']}{str(row['y'])[-1]}{active[:2]}{row['far_m']}{str(row['far_y'])[-1]} Comdty"
            if active in ["NGA Comdty", "LPA Comdty", "LAA Comdty"]:
                ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-2:]} Comdty"
                ticker1 = f"{active[:2]}{row['far_m']}{str(row['far_y'])[-2:]} Comdty"
            else:
                ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-1]} Comdty"
                ticker1 = f"{active[:2]}{row['far_m']}{str(row['far_y'])[-1]} Comdty"
            print(ticker)
            if active in ["LPA Comdty", "LAA Comdty", "LXA Comdty", "LNA Comdty"]:
                if active in ["LPA Comdty", "LAA Comdty"]:
                    ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-2:]} Comdty"
                else:
                    ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-1]} Comdty"
                if len(price) == 0 or price.index[-1] < today() - BDay(1):
                    sdate = today() - dt.timedelta(days=364)
                    edate = today()
                    price = bbg.bdh(ticker0, ["PX_LAST"], sdate=sdate, edate=edate)
                    price1 = bbg.bdh(ticker1, ["PX_LAST"], sdate=sdate, edate=edate)
                    price = (price - price1) / price
                else:
                    price = bbg.bdh(ticker0, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
                    price1 = bbg.bdh(ticker1, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
                    price = (price - price1) / price
            else:
                if len(price) == 0 or price.index[-1] < today() - BDay(1):
                    sdate = today() - dt.timedelta(days=364)
                    edate = today()
                    price = bbg.bdh(ticker, ["PX_LAST"], sdate=sdate, edate=edate)
                    price0 = bbg.bdh(ticker0, ["PX_LAST"], sdate=sdate, edate=edate)
                    price = price / price0
                else:
                    price = bbg.bdh(ticker, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
                    price0 = bbg.bdh(ticker0, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
                    price = price / price0
        price = price.loc[row["t1"] - dt.timedelta(days=14):row["last_t"], "PX_LAST"]
        data[row["ticker"]] = price.reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract["t1"] - dt.timedelta(days=14), t1=_unrecovered("futures_price_range.py line793 live_contract date key", live_contract))
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data["dates"] = trade_dates
    data.set_index("dates", inplace=True)
    return data.iloc[:-1, :], live_contract["ticker"]


def create_table(data_, ticker, ex2020=False):
    data = data_.copy()
    if ex2020:
        for col in data.columns:
            if col.split(" ")[0][-2:] == "20" or col.split(" ")[0][-2:] == "22":
                data.drop(col, axis=1, inplace=True)
    cur_price = data.loc[data[ticker].last_valid_index(), ticker]
    cols = data.columns.drop(ticker)
    x = data.loc[data[ticker].last_valid_index(), cols].values
    if len(x[~np.isnan(x)]) == 0:
        pct = np.nan
        avg = np.nan
        max5 = np.nan
        min5 = np.nan
        zscore = np.nan
    else:
        pct = (talib.percentilerank(x[~np.isnan(x)], cur_price) - 0.5) * 2
        avg = data.loc[data[ticker].last_valid_index(), cols].mean()
        max5 = data.loc[data[ticker].last_valid_index(), cols].max()
        min5 = data.loc[data[ticker].last_valid_index(), cols].min()
        se = data.loc[data[ticker].last_valid_index(), cols].std()
        zscore = (cur_price - avg) / se
    return [cur_price, pct, zscore, avg, max5, min5]


def create_chart(data, ticker, title):
    cols = data.columns.drop(ticker)
    avg = data[cols].mean(axis=1)
    data2 = data[ticker] - avg
    fig = chart.line_chart(
        df=data, title=title, data_p2y1=data2.to_frame("Current vs Avg"), subplots=[0.7, 0.3],
        highlight_dict={
            ticker: {"color": "black", "mode": "lines"},
            "Current vs Avg": {"color": "black", "mode": "lines"},
        },
    )
    return fig


def create_html_table(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            "Current price vs history": {"width": "120px", "text-align": "left"},
            "Current Price": {"width": "100px", "text-align": "center"},
            "Percentile of 10yr Range": {
                "width": "80px", "text-align": "center", "format": "{:.1%}",
                "bar": {"vmin": -1, "vmax": 1},
            },
            "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "10yr Avg Price": {"width": "100px", "text-align": "center"},
            "10yr Max": {"width": "100px", "text-align": "center"},
            "10yr Min": {"width": "100px", "text-align": "center"},
        },
        format_row={
            (7, 15, 21, 27, 33, 39, 46): {"bottom_border": True},
        },
    )


def create_html_table_1y(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            "Name": {"width": "120px", "text-align": "left"},
            "Carry yield": {"width": "100px", "text-align": "center", "format": "{:.1%}"},
            "Percentile of 20yr Range": {
                "width": "80px", "text-align": "center", "format": "{:.1%}",
                "bar": {"vmin": -1, "vmax": 1},
            },
            "Z-score of 20yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "20yr Avg yield": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "20yr Max": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "20yr Min": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
        },
        format_row={
            (5, 9, 14, 18, 20, 22): {"bottom_border": True},
        },
    )


def create_html_table_gas(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            "Current price vs history": {"width": "120px", "text-align": "left"},
            "Current Price": {"width": "100px", "text-align": "center"},
            "Percentile of 10yr Range": {
                "width": "80px", "text-align": "center", "format": "{:.1%}",
                "bar": {"vmin": -1, "vmax": 1},
            },
            "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "10yr Avg Price": {"width": "100px", "text-align": "center"},
            "10yr Max": {"width": "100px", "text-align": "center"},
            "10yr Min": {"width": "100px", "text-align": "center"},
        },
        format_row={
            6: {"bottom_border": True},
        },
    )


def create_html_table_oil(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            "Current price vs history": {"width": "120px", "text-align": "left"},
            "Current Price": {"width": "100px", "text-align": "center"},
            "Percentile of 10yr Range": {
                "width": "80px", "text-align": "center", "format": "{:.1%}",
                "bar": {"vmin": -1, "vmax": 1},
            },
            "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "10yr Avg Price": {"width": "100px", "text-align": "center"},
            "10yr Max": {"width": "100px", "text-align": "center"},
            "10yr Min": {"width": "100px", "text-align": "center"},
        },
        format_row={
            (4, 9): {"bottom_border": True},
        },
    )


def create_html_table_oil_products(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            "Current price vs history": {"width": "120px", "text-align": "left"},
            "Current Price": {"width": "100px", "text-align": "center"},
            "Percentile of 10yr Range": {
                "width": "80px", "text-align": "center", "format": "{:.1%}",
                "bar": {"vmin": -1, "vmax": 1},
            },
            "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "10yr Avg Price": {"width": "100px", "text-align": "center"},
            "10yr Max": {"width": "100px", "text-align": "center"},
            "10yr Min": {"width": "100px", "text-align": "center"},
        },
        format_row={
            (2, 5): {"bottom_border": True},
        },
    )


def update_price_range(send_to=send_to):
    folder_path = f"{html_path}\\cross_cmds\\energy_spread\\"
    figs = []
    figs_gas = []
    figs_oil = []
    figs_oil_products = []
    df_table = pd.DataFrame()
    df_table_oil = pd.DataFrame()
    df_table_oil_products = pd.DataFrame()
    latest_date = 0
    dict_outright = {}
    dict_spread26 = {}
    for ins in ins_list:
        print(ins)
        outright, outright_ticker = get_outright_data(active=ins, mon=None, window=10, drop_year=True)
        spread1, spread1_ticker = get_spread_data(active=ins, spread=1, mon=None, window=10, drop_year=True)
        spread2, spread2_ticker = get_spread_data(active=ins, spread=2, mon=None, window=10, drop_year=True)
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            spread3, spread3_ticker = get_spread_data(active=ins, spread=3, mon=None, window=10, drop_year=True)
        else:
            spread_q1, spread_q1_ticker = get_quarter_spread_data(active=ins, spread=1, mon=None, window=10, drop_year=True)
            spread_q2, spread_q2_ticker = get_quarter_spread_data(active=ins, spread=2, mon=None, window=10, drop_year=True)
            spread_q3, spread_q3_ticker = get_quarter_spread_data(active=ins, spread=3, mon=None, window=10, drop_year=True)
            spread26, spread26_ticker = get_spread_data(active=ins, spread="2-6", mon=None, window=10, drop_year=True)
        if ins in ["NGA Comdty", "TZTA Comdty"]:
            spread_FH, spread_FH_ticker = get_spread_special_calendar2(active=ins, spread="FH", mon=None, window=10, drop_year=True)
            spread_HJ, spread_HJ_ticker = get_spread_special_calendar2(active=ins, spread="HJ", mon=None, window=10, drop_year=True)
            spread_JV, spread_JV_ticker = get_spread_special_calendar2(active=ins, spread="JV", mon=None, window=10, drop_year=True)
            spread_VF, spread_VF_ticker = get_spread_special_calendar2(active=ins, spread="VF", mon=None, window=10, drop_year=True)
        if ins in ["COA Comdty", "CLA Comdty", "DATA Comdty"]:
            spread_ZZ, spread_ZZ_ticker = get_spread_special_zz(active=ins, spread="ZZ", mon=None, window=10, drop_year=True)
        if isinstance(latest_date, int):
            latest_date = outright[outright_ticker].last_valid_index()
        if ins in ["CLA Comdty", "COA Comdty", "DATA Comdty"]:
            outright_phys, outright_ticker_phys = get_outright_physical_data(active=ins, drop_year=True)
        else:
            outright_phys, outright_ticker_phys = None, None
        if outright_ticker_phys is not None:
            outright_index = [outright_ticker.rpartition(" ")[0], outright_ticker_phys.rpartition(" ")[0]]
        else:
            outright_index = [outright_ticker.rpartition(" ")[0]]
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            if ins in ["NGA Comdty", "TZTA Comdty"]:
                additional_index = [spread_FH_ticker.split(" ")[1], spread_HJ_ticker.split(" ")[1], spread_JV_ticker.split(" ")[1], spread_VF_ticker.split(" ")[1]]
            if ins == "DATA Comdty":
                additional_index = [spread_ZZ_ticker.split(" ")[1]]
            else:
                additional_index = []
            df = pd.DataFrame(
                0,
                index=outright_index + [spread1_ticker.split(" ")[1], spread2_ticker.split(" ")[1], spread3_ticker.split(" ")[1]] + additional_index,
                columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"],
            )
        else:
            if ins in ["COA Comdty", "CLA Comdty"]:
                additional_index = [spread_ZZ_ticker.split(" ")[1]]
            else:
                additional_index = []
            df = pd.DataFrame(
                0,
                index=outright_index + [spread1_ticker.split(" ")[1], spread2_ticker.split(" ")[1], spread_q1_ticker.split(" ")[1], spread_q2_ticker.split(" ")[1], spread_q3_ticker.split(" ")[1]] + additional_index,
                columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"],
            )
        df.loc[outright_ticker.rpartition(" ")[0], :] = create_table(outright, outright_ticker, ex2020=True)
        df.loc[spread1_ticker.split(" ")[1], :] = create_table(spread1, spread1_ticker, ex2020=True)
        df.loc[spread2_ticker.split(" ")[1], :] = create_table(spread2, spread2_ticker, ex2020=True)
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            df.loc[spread3_ticker.split(" ")[1], :] = create_table(spread3, spread3_ticker, ex2020=True)
            if ins in ["NGA Comdty", "TZTA Comdty"]:
                df.loc[spread_FH_ticker.split(" ")[1], :] = create_table(spread_FH, spread_FH_ticker, ex2020=True)
                df.loc[spread_HJ_ticker.split(" ")[1], :] = create_table(spread_HJ, spread_HJ_ticker, ex2020=True)
                df.loc[spread_JV_ticker.split(" ")[1], :] = create_table(spread_JV, spread_JV_ticker, ex2020=True)
                df.loc[spread_VF_ticker.split(" ")[1], :] = create_table(spread_VF, spread_VF_ticker, ex2020=True)
            if ins == "DATA Comdty":
                df.loc[spread_ZZ_ticker.split(" ")[1], :] = create_table(spread_ZZ, spread_ZZ_ticker, ex2020=True)
        else:
            if spread_q3_ticker == "S:CLCL H25-M25 Comdty":
                print("break")
            df.loc[spread_q1_ticker.split(" ")[1], :] = create_table(spread_q1, spread_q1_ticker, ex2020=True)
            df.loc[spread_q2_ticker.split(" ")[1], :] = create_table(spread_q2, spread_q2_ticker, ex2020=True)
            df.loc[spread_q3_ticker.split(" ")[1], :] = create_table(spread_q3, spread_q3_ticker, ex2020=True)
            if ins in ["COA Comdty", "CLA Comdty", "DATA Comdty"]:
                df.loc[spread_ZZ_ticker.split(" ")[1], :] = create_table(spread_ZZ, spread_ZZ_ticker, ex2020=True)
        if outright_ticker_phys is not None:
            df.loc[outright_ticker_phys.rpartition(" ")[0], :] = create_table(outright_phys, outright_ticker_phys, ex2020=True)
        df_table = pd.concat([df_table, df], axis=0)
        if ins in oil_list:
            if ins in ["CLA Comdty", "COA Comdty", "DATA Comdty"]:
                df_table_oil = pd.concat([df_table_oil, df.iloc[:4, :], df.iloc[-1, :].to_frame().T], axis=0)
            else:
                df_table_oil = pd.concat([df_table_oil, df.iloc[:3, :]], axis=0)
        if ins in oil_products_list:
            df_table_oil_products = pd.concat([df_table_oil_products, df.iloc[:3, :]], axis=0)
        if outright_ticker_phys is not None:
            figs.append(create_chart(outright_phys.dropna(how="all", axis=1), outright_ticker_phys, title=_unrecovered("futures_price_range.py line1113 physical chart title", ins)))
        figs.append(create_chart(outright, outright_ticker, title=ins + "_Outright contract"))
        figs.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
        figs.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            figs.append(create_chart(spread3, spread3_ticker, title=ins + "_3rd spread"))
        else:
            figs.append(create_chart(spread_q1, spread_q1_ticker, title=ins + "_1st quarter spread"))
            figs.append(create_chart(spread_q2, spread_q2_ticker, title=ins + "_2nd quarter spread"))
            figs.append(create_chart(spread_q3, spread_q3_ticker, title=ins + "_3rd quarter spread"))
            dict_outright[ins] = outright
            dict_spread26[ins] = spread26
        if ins in ["NGA Comdty", "TZTA Comdty"]:
            figs_gas.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
            figs_gas.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
            figs_gas.append(create_chart(spread3, spread3_ticker, title=ins + "_3rd spread"))
            figs_gas.append(create_chart(spread_FH, spread_FH_ticker, title=_unrecovered("futures_price_range.py line1130 FH calendar-spread title", ins, today().year)))
            figs_gas.append(create_chart(spread_HJ, spread_HJ_ticker, title=_unrecovered("futures_price_range.py line1131 HJ calendar-spread title", ins, today().year)))
            figs_gas.append(create_chart(spread_JV, spread_JV_ticker, title=_unrecovered("futures_price_range.py line1132 JV calendar-spread title", ins, today().year)))
            figs_gas.append(create_chart(spread_VF, spread_VF_ticker, title=_unrecovered("futures_price_range.py line1133 VF calendar-spread title", ins, today().year)))
        if ins in oil_list:
            if outright_ticker_phys is not None:
                figs_oil.append(create_chart(outright_phys.dropna(how="all", axis=1), outright_ticker_phys, title=_unrecovered("futures_price_range.py line1136 physical chart title", ins)))
            figs_oil.append(create_chart(outright, outright_ticker, title=ins + "_Outright contract"))
            figs_oil.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
            figs_oil.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
            if ins in ["COA Comdty", "CLA Comdty", "DATA Comdty"]:
                figs_oil.append(create_chart(spread_ZZ, spread_ZZ_ticker, title=ins + "_DEC/DEC"))
                figs_oil.append("")
        if ins in oil_products_list:
            figs_oil_products.append(create_chart(outright, outright_ticker, title=ins + "_Outright contract"))
            figs_oil_products.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
            figs_oil_products.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
    df_table.index.name = "Current price vs history"
    df_table.reset_index(inplace=True)
    df_html_table = create_html_table(df_table)
    figs = [df_html_table, ""] + figs
    figs = table.figs_to_grid(figs, columns=2)
    table.figures_to_html([figs], filename=folder_path + "charts.html", task_name=report_name)
    df_table_gas = df_table.iloc[-14:].copy()
    df_table_gas.reset_index(inplace=True, drop=True)
    df_table_gas.loc[1:6, "Current price vs history"] = "NG " + df_table_gas.loc[1:6, "Current price vs history"]
    df_table_gas.loc[8:, "Current price vs history"] = "TZT " + df_table_gas.loc[8:, "Current price vs history"]
    df_html_table_gas = create_html_table_gas(df_table_gas)
    figs_gas = [df_html_table_gas, ""] + figs_gas
    figs_gas = table.figs_to_grid(figs_gas, columns=2)
    table.figures_to_html([figs_gas], filename=folder_path + "charts_gas.html", task_name=report_name)
    df_table_oil.index.name = "Current price vs history"
    df_table_oil.reset_index(inplace=True)
    df_html_table_oil = create_html_table_oil(df_table_oil)
    figs_oil = [df_html_table_oil, ""] + figs_oil
    figs_oil = table.figs_to_grid(figs_oil, columns=2)
    table.figures_to_html([figs_oil], filename=folder_path + "charts_crude.html", task_name=report_name)
    df_table_oil_products.index.name = "Current price vs history"
    df_table_oil_products.reset_index(inplace=True)
    df_html_table_oil_products = create_html_table_oil_products(df_table_oil_products)
    figs_oil_products = [df_html_table_oil_products, ""] + figs_oil_products
    figs_oil_products = table.figs_to_grid(figs_oil_products, columns=2)
    table.figures_to_html([figs_oil_products], filename=folder_path + "charts_oil_products.html", task_name=report_name)


def update_oil(send_to=send_to):
    folder_path = f"{html_path}\\cross_cmds\\energy_spread\\"
    figs = []
    figs_gas = []
    df_table = pd.DataFrame()
    latest_date = 0
    dict_outright = {}
    dict_spread26 = {}
    for ins in oil_list:
        print(ins)
        outright, outright_ticker = get_outright_data(active=ins, mon=None, window=10, drop_year=True)
        spread1, spread1_ticker = get_spread_data(active=ins, spread=1, mon=None, window=10, drop_year=True)
        spread2, spread2_ticker = get_spread_data(active=ins, spread=2, mon=None, window=10, drop_year=True)
        spread26, spread26_ticker = get_spread_data(active=ins, spread="2-6", mon=None, window=10, drop_year=True)
        if isinstance(latest_date, int):
            latest_date = outright[outright_ticker].last_valid_index()
        df = pd.DataFrame(
            0,
            index=[outright_ticker.rpartition(" ")[0], spread1_ticker.split(" ")[1], spread2_ticker.split(" ")[1], spread26_ticker.split(" ")[1]],
            columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"],
        )
        df.loc[outright_ticker.rpartition(" ")[0], :] = create_table(outright, outright_ticker, ex2020=True)
        df.loc[spread1_ticker.split(" ")[1], :] = create_table(spread1, spread1_ticker, ex2020=True)
        df.loc[spread2_ticker.split(" ")[1], :] = create_table(spread2, spread2_ticker, ex2020=True)
        df_table = pd.concat([df_table, df], axis=0)
        figs.append(create_chart(outright, outright_ticker, title=ins + "_Outright contract"))
        figs.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
        figs.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
        dict_outright[ins] = outright
        dict_spread26[ins] = spread26
    df_table.index.name = "Current price vs history"
    df_table.reset_index(inplace=True)
    df_html_table = table.html_format(
        df=df_table,
        precision=2,
        format_column={
            "Current price vs history": {"width": "120px", "text-align": "left"},
            "Current Price": {"width": "100px", "text-align": "center"},
            "Percentile of 10yr Range": {
                "width": "80px", "text-align": "center", "format": "{:.1%}",
                "bar": {"vmin": -1, "vmax": 1},
            },
            "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
            "10yr Avg Price": {"width": "100px", "text-align": "center"},
            "10yr Max": {"width": "100px", "text-align": "center"},
            "10yr Min": {"width": "100px", "text-align": "center"},
        },
        format_row={
            (0, 4): {"bottom_border": True},
        },
    )
    figs.insert(0, df_html_table)
    table.figures_to_html(figs, filename=folder_path + "charts_oil.html", task_name=report_name)


def get_com_curve(send_to=send_to):
    ins_list = ['CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty', 'NGA Comdty', 'LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'C A Comdty', 'S A Comdty', 'SMA Comdty', 'BOA Comdty', 'W A Comdty', 'SBA Comdty', 'CCA Comdty', 'KCA Comdty', 'CTA Comdty', 'LCA Comdty', 'LHA Comdty', 'GCA Comdty', 'SIA Comdty']
    bcom_w = {'CLA Comdty': 8.78, 'COA Comdty': 7.12, 'XBA Comdty': 2.71, 'HOA Comdty': 2.37, 'QSA Comdty': 3.08, 'NGA Comdty': 13.85, 'LPA Comdty': 4.14, 'LAA Comdty': 3.34, 'LXA Comdty': 2.54, 'LNA Comdty': 2.9, 'C A Comdty': 5.64, 'S A Comdty': 5.56, 'SMA Comdty': 2.88, 'BOA Comdty': 3.41, 'W A Comdty': 5.61, 'SBA Comdty': 2.4, 'CCA Comdty': 0, 'KCA Comdty': 1.99, 'CTA Comdty': 1.46, 'LCA Comdty': 2.68, 'LHA Comdty': 1.8, 'GCA Comdty': 12.11, 'SIA Comdty': 3.62}
    gsci_w = {'CLA Comdty': 22.33, 'COA Comdty': 15.78, 'XBA Comdty': 3.8, 'HOA Comdty': 4, 'QSA Comdty': 5.23, 'NGA Comdty': 3.96, 'LPA Comdty': 5.53, 'LAA Comdty': 4.34, 'LXA Comdty': 1.12, 'LNA Comdty': 1.02, 'C A Comdty': 6.23, 'S A Comdty': 3.69, 'SMA Comdty': 0, 'BOA Comdty': 0, 'W A Comdty': 5.58, 'SBA Comdty': 1.83, 'CCA Comdty': 0.29, 'KCA Comdty': 1.19, 'CTA Comdty': 1.45, 'LCA Comdty': 3.89, 'LHA Comdty': 1.91, 'GCA Comdty': 4.57, 'SIA Comdty': 0.49}
    bcom_w_df = pd.DataFrame(bcom_w.items(), columns=["name", "Carry yield"])
    bcom_w_df.set_index("name", inplace=True)
    gsci_w_df = pd.DataFrame(gsci_w.items(), columns=["name", "Carry yield"])
    gsci_w_df.set_index("name", inplace=True)
    folder_path = f"{html_path}\\cross_cmds\\energy_spread\\"
    figs = []
    figs_gas = []
    df_table = pd.DataFrame()
    latest_date = 0
    dict_spread = {}
    for ins in ins_list:
        print(ins)
        spread1, spread1_ticker = get_synthetic_spread(active=ins, spread="1-13", go=None)
        if isinstance(latest_date, int):
            latest_date = spread1[spread1.columns[-1]].last_valid_index()
        df = pd.DataFrame(0, index=[ins], columns=["Carry yield", "Percentile of 20yr Range", "Z-score of 20yr Range", "20yr Avg yield", "20yr Max", "20yr Min"])
        df.loc[ins, :] = create_table(spread1, spread1_ticker)
        df_table = pd.concat([df_table, df], axis=0)
        figs.append(create_chart(spread1, spread1_ticker, title=ins + " 1y spread"))
        dict_spread[ins] = spread1
    df_bcom = pd.DataFrame(np.nan, index=["BCOM"], columns=df_table.columns)
    df_gsci = pd.DataFrame(np.nan, index=["GSCI"], columns=df_table.columns)
    df_bcom["Carry yield"] = (df_table["Carry yield"] * bcom_w_df["Carry yield"]).sum() / 100
    df_gsci["Carry yield"] = (df_table["Carry yield"] * gsci_w_df["Carry yield"]).sum() / 100
    df_table = pd.concat([df_table, df_bcom, df_gsci], axis=0)
    df_table.index.name = "Name"
    df_table.reset_index(inplace=True)
    df_table = df_table.sort_index()
    df_html_table = create_html_table_1y(df_table)
    figs.insert(0, df_html_table)
    table.figures_to_html(figs, filename=folder_path + "_charts_1y_spread.html", task_name=report_name)
    send_email(
        send_to=send_to,
        subject="Commodity backwardation",
        body=[
            "Lastest update from source is {:s}".format(dt.datetime.strftime(latest_date, "%Y-%m-%d")),
            df_html_table,
            "<br><br>Please follow the link for charts: ",
            _unrecovered("futures_price_range.py line1386 clipped charts_1y_spread hyperlink"),
            "<br><br>This is automated email sent at {:s}. <br><br>".format(time.strftime("%Y-%m-%d %H:%M")),
        ],
    )


def update_seasonal():
    folder_path = f"{html_path}\\cross_cmds\\energy_spread\\"
    for ins in ins_list:
        print(ins)
        if ins in ["Crd-P-US", "Crd-P-EU", "Crd-P-Asia"]:
            continue
        if ins in ["TZTA Comdty"]:
            custom_drop_year = []
        else:
            custom_drop_year = None
        df_table = pd.DataFrame()
        latest_date = 0
        dict_outright = {}
        dict_spread26 = {}
        figs = []
        outright, outright_ticker = get_outright_data(active=ins, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        spread1, spread1_ticker = get_spread_data(active=ins, spread=1, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        spread2, spread2_ticker = get_spread_data(active=ins, spread=2, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            spread3, spread3_ticker = get_spread_data(active=ins, spread=3, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        else:
            spread_q1, spread_q1_ticker = get_quarter_spread_data(active=ins, spread=1, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
            spread_q2, spread_q2_ticker = get_quarter_spread_data(active=ins, spread=2, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
            spread_q3, spread_q3_ticker = get_quarter_spread_data(active=ins, spread=3, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
            spread26, spread26_ticker = get_spread_data(active=ins, spread="2-6", mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        if isinstance(latest_date, int):
            latest_date = outright[outright_ticker].last_valid_index()
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            df = pd.DataFrame(0, index=[outright_ticker.rpartition(" ")[0], spread1_ticker.split(" ")[1], spread2_ticker.split(" ")[1], spread3_ticker.split(" ")[1]], columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"])
        else:
            df = pd.DataFrame(0, index=[outright_ticker.rpartition(" ")[0], spread1_ticker.split(" ")[1], spread2_ticker.split(" ")[1], spread_q1_ticker.split(" ")[1], spread_q2_ticker.split(" ")[1], spread_q3_ticker.split(" ")[1]], columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"])
        df.loc[outright_ticker.rpartition(" ")[0], :] = create_table(outright, outright_ticker, ex2020=True)
        df.loc[spread1_ticker.split(" ")[1], :] = create_table(spread1, spread1_ticker, ex2020=True)
        df.loc[spread2_ticker.split(" ")[1], :] = create_table(spread2, spread2_ticker, ex2020=True)
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            df.loc[spread3_ticker.split(" ")[1], :] = create_table(spread3, spread3_ticker, ex2020=True)
        else:
            if spread_q3_ticker == "S:CLCL H25-M25 Comdty":
                print("break")
            df.loc[spread_q1_ticker.split(" ")[1], :] = create_table(spread_q1, spread_q1_ticker, ex2020=True)
            df.loc[spread_q2_ticker.split(" ")[1], :] = create_table(spread_q2, spread_q2_ticker, ex2020=True)
            df.loc[spread_q3_ticker.split(" ")[1], :] = create_table(spread_q3, spread_q3_ticker, ex2020=True)
        df_table = pd.concat([df_table, df], axis=0)
        figs.append(create_chart(outright, outright_ticker, title=ins + "_Outright contract"))
        figs.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
        figs.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            pass
        else:
            figs.append(create_chart(spread_q1, spread_q1_ticker, title=ins + "_1st quarter spread"))
            figs.append(create_chart(spread_q2, spread_q2_ticker, title=ins + "_2nd quarter spread"))
            figs.append(create_chart(spread_q3, spread_q3_ticker, title=ins + "_3rd quarter spread"))
            dict_outright[ins] = outright
            dict_spread26[ins] = spread26
        if ins in ["NGA Comdty", "TZTA Comdty", "DATA Comdty"]:
            figs.append(create_chart(spread1, spread1_ticker, title=ins + "_1st spread"))
            figs.append(create_chart(spread2, spread2_ticker, title=ins + "_2nd spread"))
            figs.append(create_chart(spread3, spread3_ticker, title=ins + "_3rd spread"))
        df_table.index.name = "Current price vs history"
        df_table.reset_index(inplace=True)
        df_html_table = table.html_format(
            df=df_table, header=f"{ins} current price vs historical range", precision=2,
            format_column={
                "Current price vs history": {"width": "120px", "text-align": "left"},
                "Current Price": {"width": "100px", "text-align": "center"},
                "Percentile of 10yr Range": {"width": "80px", "text-align": "center", "format": "{:.1%}", "bar": {"vmin": -1, "vmax": 1}},
                "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
                "10yr Avg Price": {"width": "100px", "text-align": "center"},
                "10yr Max": {"width": "100px", "text-align": "center"},
                "10yr Min": {"width": "100px", "text-align": "center"},
            }, format_row={0: {"bottom_border": True}},
        )
        figs.insert(0, df_html_table)
        flat_season = season(active=ins, spread=False, drop_years=custom_drop_year)
        flat_season.index.name = "Contract"
        data_dump_perf_path = convert_path_to_linux(Path(f"{data_path}\\energy_spread\\seasonal_flat_perf_{ins}.csv"))
        if not data_dump_perf_path.parent.exists():
            data_dump_perf_path.parent.mkdir(parents=True)
        flat_season.to_csv(data_dump_perf_path)
        flat_season.reset_index(inplace=True)
        flat_season_html = table.html_format(
            df=flat_season, header=f"{ins} outright penultimate perf", precision=2,
            format_column={
                flat_season.columns[0]: {"width": "60px", "text-align": "center", "bold": True},
                tuple(flat_season.columns[1:]): {"width": "60px", "text-align": "center", "format": "{:.1%}"},
                flat_season.columns[-2]: {"width": "60px", "text-align": "center", "format": "{:.2f}", "bold": True},
                flat_season.columns[-1]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                flat_season.columns[-3]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                flat_season.columns[-4]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "right_border": True},
            },
        )
        figs.insert(0, flat_season_html)
        sprd_season = season(active=ins, spread=True, drop_years=custom_drop_year)
        sprd_season.index.name = "Contract"
        data_dump_perf_sprd_path = convert_path_to_linux(Path(f"{data_path}\\energy_spread\\seasonal_sprd_perf_{ins}.csv"))
        if not data_dump_perf_sprd_path.parent.exists():
            data_dump_perf_sprd_path.parent.mkdir(parents=True)
        sprd_season.to_csv(data_dump_perf_sprd_path)
        sprd_season.reset_index(inplace=True)
        sprd_season_html = table.html_format(
            df=sprd_season, header=f"{ins} spread penultimate perf", precision=2,
            format_column={
                sprd_season.columns[0]: {"width": "60px", "text-align": "center", "bold": True},
                tuple(sprd_season.columns[1:]): {"width": "60px", "text-align": "center"},
                sprd_season.columns[-2]: {"width": "60px", "text-align": "center", "bold": True},
                sprd_season.columns[-1]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                sprd_season.columns[-3]: {"width": "60px", "text-align": "center", "bold": True},
                sprd_season.columns[-4]: {"width": "60px", "text-align": "center", "right_border": True},
            },
        )
        figs.insert(0, sprd_season_html)
        sp_season = season(active=ins, spread=True, change=False, drop_years=custom_drop_year)
        fp_season = season(active=ins, spread=False, change=False, drop_years=custom_drop_year)
        fp_season_weights = fp_season.copy().iloc[:, :-3]
        sp_season_weighted = sp_season.copy().iloc[:, :-3]
        fp_season_weights.index = sp_season_weighted.index
        sp_season_weighted = sp_season_weighted.divide(fp_season_weights).replace([np.inf, -np.inf], np.nan)
        sp_season_weighted["Mean"] = sp_season_weighted.mean(axis=1)
        sp_season_weighted["Z-score"] = sp_season_weighted.mean(axis=1) / sp_season_weighted.std(axis=1)
        sp_season_weighted["Hit ratio"] = sp_season_weighted[sp_season_weighted > 0].count(axis=1) / sp_season_weighted.count(axis=1)
        sp_season_weighted.index.name = "Contract"
        weighted_data_dump_path = convert_path_to_linux(Path(f"{data_path}\\energy_spread\\seasonal_sprd_weighted_{ins}.csv"))
        if not weighted_data_dump_path.parent.exists():
            weighted_data_dump_path.parent.mkdir(parents=True)
        sp_season_weighted.to_csv(weighted_data_dump_path)
        sp_season.index.name = "Contract"
        data_dump_path = convert_path_to_linux(Path(f"{data_path}\\energy_spread\\seasonal_{ins}.csv"))
        if not data_dump_path.parent.exists():
            data_dump_path.parent.mkdir(parents=True)
        sp_season.to_csv(data_dump_path)
        sp_season.reset_index(inplace=True)
        sp_season_html = table.html_format(
            df=sp_season, header=f"{ins} spread penultimate price", precision=2,
            format_column={
                sp_season.columns[0]: {"width": "60px", "text-align": "center", "bold": True},
                tuple(sp_season.columns[1:]): {"width": "60px", "text-align": "center"},
                sp_season.columns[-2]: {"width": "60px", "text-align": "center", "bold": True},
                sp_season.columns[-1]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                sp_season.columns[-3]: {"width": "60px", "text-align": "center", "bold": True},
                sp_season.columns[-4]: {"width": "60px", "text-align": "center", "right_border": True},
            },
        )
        figs.insert(1, sp_season_html)
        table.figures_to_html(figs, filename=folder_path + f"seasonal_{ins}.html", task_name=report_name)


def season(active, spread, change=True, sdate=None, drop_years=None, special_case=None):
    if drop_years is None:
        drop_years = [2020, 2022]
    if not sdate:
        sdate = dt.datetime(2010, 1, 1)
    if spread:
        contracts_ = pyg.get_data("spreads", active=active, item="sprd_chain")
        if special_case == "QZT":
            m_list = sprd_m_list_qz
        elif special_case == "QQT":
            m_list = sprd_m_list_qq
        else:
            m_list = sprd_m_list
    else:
        contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
        if special_case == "QZT":
            m_list = flat_m_list_qz
        elif special_case == "QQT":
            m_list = flat_m_list_qq
        else:
            m_list = flat_m_list
    contracts = contracts_.copy()
    contracts["start_t"] = contracts["t1"].shift(1)
    contracts = contracts.loc[(contracts["t1"] >= sdate - dt.timedelta(days=32)) & (contracts["t1"] <= _unrecovered("futures_price_range.py line1666 contract-filter upper date bound", today())), :]
    yrs = list(range(sdate.year, today().year + 1))
    for y in drop_years:
        if y in yrs:
            yrs.remove(y)
    season_df = pd.DataFrame(np.nan, index=yrs, columns=m_list)
    for i in m_list:
        if "-" in i:
            same_month = contracts.loc[contracts["m"] == i[0], :]
        else:
            same_month = contracts.loc[contracts["m"] == i, :]
        if len(drop_years) > 0:
            with pd.option_context("mode.chained_assignment", None):
                same_month.drop(same_month.loc[same_month["y"].isin([2020, 2022] if not drop_years else drop_years)].index, inplace=True)
        all_price = pd.DataFrame()
        for idx, row in same_month.iterrows():
            if row["start_t"] <= today():
                if row["t1"] >= today():
                    price = bbg.bdh(row["ticker"], ["PX_LAST"], row["start_t"], today())
                else:
                    if spread:
                        try:
                            price = pyg.get_data("spreads_PX_LAST", active=active, m=row["m"], y=row["y"], far_m=row["far_m"], far_y=row["far_y"])
                        except:
                            price1 = pyg.get_data("contracts_PX_LAST", active=active, m=row["m"], y=row["y"])
                            price2 = pyg.get_data("contracts_PX_LAST", active=active, m=row["far_m"], y=row["far_y"])
                            price = (price1 - price2).dropna()
                    else:
                        price = pyg.get_data("contracts_PX_LAST", active=active, m=row["m"], y=row["y"])
                    price = price.loc[(price.index >= row["start_t"]) & (price.index <= row["t1"])]
                if spread and change:
                    season_df.loc[row["y"], i] = price.iloc[-1, 0] - price.iloc[0, 0]
                elif spread is False and change:
                    try:
                        season_df.loc[row["y"], i] = (price.iloc[-1, 0] - price.iloc[0, 0]) / price.iloc[0, 0]
                    except:
                        print("error")
                elif spread and change is False:
                    if not price.empty:
                        season_df.loc[row["y"], i] = price.iloc[-1, 0]
                elif spread is False and change is False:
                    if not price.empty:
                        season_df.loc[row["y"], i] = price.iloc[-1, 0]
                    else:
                        season_df.loc[row["y"], i] = np.nan
                else:
                    season_df.loc[row["y"], i] = np.nan
                all_price = pd.concat([all_price, price.reset_index(drop=True)], axis=1)
    season_df.index = season_df.index.map(str)
    season_df.loc["Mean"] = season_df.mean(axis=0)
    season_df.loc["Z-score"] = season_df.mean(axis=0) / season_df.std(axis=0)
    season_df.loc["Hit ratio"] = season_df[season_df > 0].count(axis=0) / season_df.count(axis=0)
    return season_df.T


def get_quarter_spread_data_qz(active="QZTA Comdty", spread=1, mon=None, window=10, drop_year=False, custom_drop_year=None):
    contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
    contracts = contracts_.copy()
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts = contracts.loc[contracts["m"].isin(["F", "J", "N", "V"]), :]
    contracts["far_m"] = contracts["m"].shift(-1)
    contracts["far_y"] = contracts["y"].shift(-1)
    contracts["far_ticker"] = contracts["ticker"].shift(-1)
    contracts["t1"] = contracts["t"].shift(1)
    if isinstance(spread, int) and spread > 1:
        contracts["t"] = contracts["t"].shift(spread - 1)
        contracts["t1"] = contracts["t1"].shift(spread - 1)
    live_contract = contracts.iloc[np.where(contracts["t"] >= today())[0][0], :]
    if mon is None:
        same_month_contract = contracts.loc[
            (contracts["m"] == live_contract["m"]) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
        ]
    else:
        same_month_contract = contracts.loc[
            (contracts["m"] == mon) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
        ]
    if drop_year:
        with pd.option_context("mode.chained_assignment", None):
            same_month_contract.drop(
                same_month_contract.loc[same_month_contract["y"].isin([2020, 2022] if not custom_drop_year else custom_drop_year)].index,
                axis=0, inplace=True,
            )
    data = pd.DataFrame()
    same_month_contract.dropna(inplace=True)
    for idx, row in same_month_contract.iterrows():
        ticker = f"S:{active[:3]}{active[:3]} {row['m']}{str(row['y'])[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        price = synthetic_spread(active=active, m=row["m"], y=int(row["y"]), far_m=row["far_m"], far_y=int(row["far_y"]))
        if row["y"] >= today().year:
            print(ticker)
            price = bbg.bdh(ticker, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
        if isinstance(price.columns, pd.MultiIndex):
            price = price[ticker]
        price = price.loc[row["t1"] - dt.timedelta(days=14):row["last_t"], "PX_LAST"]
        if idx == same_month_contract.index[-1]:
            data = data.iloc[::-1].reset_index(drop=True)
            data[ticker] = price.reset_index(drop=True)
        else:
            data[ticker] = price.iloc[::-1].reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract["t1"] - dt.timedelta(days=14), t1=today())
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data["dates"] = trade_dates
    data.set_index("dates", inplace=True)
    ret_ticker = f"S:{active[:3]}{active[:3]} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-" f"{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty"
    return data.iloc[:-1, :], ret_ticker



def get_spread_data_qq(active="QQTA Comdty", mon=None, window=10, drop_year=False, custom_drop_year=None):
    contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
    contracts = contracts_.copy()
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts = contracts.loc[contracts["m"].isin(["V", "J"]), :]
    contracts["far_m"] = contracts["m"].shift(-1)
    contracts["far_y"] = contracts["y"].shift(-1)
    contracts["far_ticker"] = contracts["ticker"].shift(-1)
    contracts["t1"] = contracts["t"].shift(1)
    live_contract = contracts.iloc[np.where(contracts["t"] >= today())[0][0], :]
    if mon is None:
        same_month_contract = contracts.loc[
            (contracts["m"] == live_contract["m"]) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
        ]
    else:
        same_month_contract = contracts.loc[
            (contracts["m"] == mon) & (contracts["y"] <= live_contract["y"]) & (contracts["y"] >= live_contract["y"] - window), :
        ]
    if drop_year:
        with pd.option_context("mode.chained_assignment", None):
            same_month_contract.drop(
                same_month_contract.loc[same_month_contract["y"].isin([2020, 2022] if not custom_drop_year else custom_drop_year)].index,
                axis=0, inplace=True,
            )
    data = pd.DataFrame()
    same_month_contract.dropna(inplace=True)
    for idx, row in same_month_contract.iterrows():
        ticker = f"S:{active[:3]}{active[:3]} {row['m']}{str(row['y'])[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        price = synthetic_spread(active=active, m=row["m"], y=int(row["y"]), far_m=row["far_m"], far_y=int(row["far_y"]))
        if row["y"] >= today().year:
            print(ticker)
            price = bbg.bdh(ticker, ["PX_LAST"], sdate=price.index[0], edate=price.index[-1])
        if isinstance(price.columns, pd.MultiIndex):
            price = price[ticker]
        price = price.loc[row["t1"] - dt.timedelta(days=14):today(), "PX_LAST"]
        if idx == same_month_contract.index[-1]:
            data = data.iloc[::-1].reset_index(drop=True)
            data[ticker] = price.reset_index(drop=True)
        else:
            data[ticker] = price.iloc[::-1].reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract["t1"] - dt.timedelta(days=14), t1=today())
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data["dates"] = trade_dates
    data.set_index("dates", inplace=True)
    ret_ticker = f"S:{active[:3]}{active[:3]} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-" f"{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty"
    return data.iloc[:-1, :], ret_ticker


def update_seasonal_quaters():
    folder_path = f"{html_path}\\cross_cmds\\energy_spread\\"
    ins_list = ["QZTA Comdty", "QQTA Comdty"]
    for ins in ins_list:
        print(ins)
        if ins in ["TZTA Comdty"]:
            custom_drop_year = [2022]
        else:
            custom_drop_year = None
        df_table = pd.DataFrame()
        latest_date = 0
        dict_outright = {}
        dict_spread26 = {}
        figs = []
        outright, outright_ticker = get_outright_data(active=ins, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        if ins in ["QZTA Comdty"]:
            spread_q1, spread_q1_ticker = get_quarter_spread_data_qz(active=ins, spread=1, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
            spread_q2, spread_q2_ticker = get_quarter_spread_data_qz(active=ins, spread=2, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
            spread_q3, spread_q3_ticker = get_quarter_spread_data_qz(active=ins, spread=3, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
            spread_q4, spread_q4_ticker = get_quarter_spread_data_qz(active=ins, spread=4, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        else:
            spread_seasonal, spread_seasonal_ticker = get_spread_data_qq(active=ins, mon=None, window=12, drop_year=True, custom_drop_year=custom_drop_year)
        if isinstance(latest_date, int):
            latest_date = outright[outright_ticker].last_valid_index()
        if ins in ["QZTA Comdty"]:
            df = pd.DataFrame(0, index=[outright_ticker.rpartition(" ")[0], spread_q1_ticker.split(" ")[1], spread_q2_ticker.split(" ")[1], spread_q3_ticker.split(" ")[1], spread_q4_ticker.split(" ")[1]], columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"])
        else:
            df = pd.DataFrame(0, index=[outright_ticker.rpartition(" ")[0], spread_seasonal_ticker.split(" ")[1]], columns=["Current Price", "Percentile of 10yr Range", "Z-score of 10yr Range", "10yr Avg Price", "10yr Max", "10yr Min"])
        df.loc[outright_ticker.rpartition(" ")[0], :] = create_table(outright, outright_ticker, ex2020=True)
        if ins in ["QZTA Comdty"]:
            df.loc[spread_q1_ticker.split(" ")[1], :] = create_table(spread_q1, spread_q1_ticker, ex2020=True)
            df.loc[spread_q2_ticker.split(" ")[1], :] = create_table(spread_q2, spread_q2_ticker, ex2020=True)
            df.loc[spread_q3_ticker.split(" ")[1], :] = create_table(spread_q3, spread_q3_ticker, ex2020=True)
            df.loc[spread_q4_ticker.split(" ")[1], :] = create_table(spread_q4, spread_q4_ticker, ex2020=True)
        else:
            df.loc[spread_seasonal_ticker.split(" ")[1], :] = create_table(spread_seasonal, spread_seasonal_ticker, ex2020=True)
        df_table = pd.concat([df_table, df], axis=0)
        if ins in ["QZTA Comdty"]:
            figs.append(create_chart(spread_q1, spread_q1_ticker, title=ins + "_1st quarter spread"))
            figs.append(create_chart(spread_q2, spread_q2_ticker, title=ins + "_2nd quarter spread"))
            figs.append(create_chart(spread_q3, spread_q3_ticker, title=ins + "_3rd quarter spread"))
            figs.append(create_chart(spread_q4, spread_q4_ticker, title=ins + "_4th quarter spread"))
        else:
            figs.append(create_chart(spread_seasonal, spread_seasonal_ticker, title=ins + "_seasonal spread"))
        df_table.index.name = "Current price vs history"
        df_table.reset_index(inplace=True)
        df_html_table = table.html_format(
            df=df_table, header=f"{ins} current price vs historical range", precision=2,
            format_column={
                "Current price vs history": {"width": "120px", "text-align": "left"},
                "Current Price": {"width": "100px", "text-align": "center"},
                "Percentile of 10yr Range": {"width": "80px", "text-align": "center", "format": "{:.1%}", "bar": {"vmin": -1, "vmax": 1}},
                "Z-score of 10yr Range": {"width": "100px", "text-align": "center", "format": "{:.2f}"},
                "10yr Avg Price": {"width": "100px", "text-align": "center"},
                "10yr Max": {"width": "100px", "text-align": "center"},
                "10yr Min": {"width": "100px", "text-align": "center"},
            }, format_row={0: {"bottom_border": True}},
        )
        figs.insert(0, df_html_table)
        flat_season = season(active=ins, spread=False, sdate=dt.datetime(2016, 1, 1), drop_years=custom_drop_year)
        flat_season.index.name = "Contract"
        if ins == "QZTA Comdty":
            flat_season = flat_season.loc[["F", "J", "N", "V"], :]
        else:
            flat_season = flat_season.loc[["J", "V"], :]
        data_dump_perf_path = convert_path_to_linux(Path(f"{data_path}\\energy_spread\\seasonal_flat_perf_{ins}.csv"))
        if not data_dump_perf_path.parent.exists():
            data_dump_perf_path.parent.mkdir(parents=True)
        flat_season.to_csv(data_dump_perf_path)
        flat_season.reset_index(inplace=True)
        flat_season_html = table.html_format(
            df=flat_season, header=f"{ins} outright penultimate perf", precision=2,
            format_column={
                flat_season.columns[0]: {"width": "60px", "text-align": "center", "bold": True},
                tuple(flat_season.columns[1:]): {"width": "60px", "text-align": "center", "format": "{:.1%}"},
                flat_season.columns[-2]: {"width": "60px", "text-align": "center", "format": "{:.2f}", "bold": True},
                flat_season.columns[-1]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                flat_season.columns[-3]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                flat_season.columns[-4]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "right_border": True},
            },
        )
        figs.insert(0, flat_season_html)
        sprd_season = season(active=ins, spread=True, sdate=dt.datetime(2016, 1, 1), special_case="QZT" if ins == "QZTA Comdty" else "QQT", drop_years=custom_drop_year)
        sprd_season.index.name = "Contract"
        sprd_season.reset_index(inplace=True)
        sprd_season_html = table.html_format(
            df=sprd_season, header=f"{ins} spread penultimate perf", precision=2,
            format_column={
                sprd_season.columns[0]: {"width": "60px", "text-align": "center", "bold": True},
                tuple(sprd_season.columns[1:]): {"width": "60px", "text-align": "center"},
                sprd_season.columns[-2]: {"width": "60px", "text-align": "center", "bold": True},
                sprd_season.columns[-1]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                sprd_season.columns[-3]: {"width": "60px", "text-align": "center", "bold": True},
                sprd_season.columns[-4]: {"width": "60px", "text-align": "center", "right_border": True},
            },
        )
        figs.insert(0, sprd_season_html)
        sp_season = season(active=ins, spread=True, change=False, sdate=dt.datetime(2016, 1, 1), drop_years=custom_drop_year, special_case="QZT" if ins == "QZTA Comdty" else "QQT")
        sp_season.index.name = "Contract"
        sp_season.reset_index(inplace=True)
        sp_season_html = table.html_format(
            df=sp_season, header=f"{ins} spread penultimate price", precision=2,
            format_column={
                sp_season.columns[0]: {"width": "60px", "text-align": "center", "bold": True},
                tuple(sp_season.columns[1:]): {"width": "60px", "text-align": "center"},
                sp_season.columns[-2]: {"width": "60px", "text-align": "center", "bold": True},
                sp_season.columns[-1]: {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},
                sp_season.columns[-3]: {"width": "60px", "text-align": "center", "bold": True},
                sp_season.columns[-4]: {"width": "60px", "text-align": "center", "right_border": True},
            },
        )
        figs.insert(1, sp_season_html)
        table.figures_to_html(figs, filename=folder_path + f"seasonal_quarters_{ins}.html", task_name=report_name)


def update():
    update_price_range()
    update_seasonal()
    update_seasonal_quaters()


if __name__ == "__main__":
    update()
