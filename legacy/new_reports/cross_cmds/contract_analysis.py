import pandas as pd
import numpy as np
import datetime as dt
import time
import sys
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import BDay
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.talib as talib
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, getworkingdays, CDR
from ecm.cmds.utils import convert_path_to_linux
from ecm.cmds.config import root_path, output_path, csv_path, oil_group, gas_group


send_to = ["Commods@elementcapital.com"]
report_name = "Contract Analysis"
file_name = "contract_analysis"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"


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
        start_datetime=dt.datetime(2023, 7, 1, 8, 30),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


ins_list = [
    "CLA Comdty",
    "COA Comdty",
    "XBA Comdty",
    "HOA Comdty",
    "QSA Comdty",
    "NGA Comdty",
    "TZTA Comdty",
]
limit_dict = {
    "CLA Comdty": [-4, (
        "expiry limit: 6000 contracts. Close of trading 3 business days prior to last "
        "trading day of the contract"
    )],
    "COA Comdty": [-5, (
        "expiry limit: 6,000 contracts in the last five business days, up to and including the "
        "expiry day in the spot month, inclusive of futures-equivalent position in Brent Options."
    )],
    "XBA Comdty": [-4, (
        "expiry limit: 2000 contracts. Close of trading 3 business days prior to last "
        "trading day of the contract"
    )],
    "HOA Comdty": [-4, (
        "expiry limit: 2000 contracts. Close of trading 3 business days prior to last "
        "trading day of the contract"
    )],
    "NGA Comdty": [-4, (
        "expiry limit: 2000 contracts. Close of trading 3 business days prior to last "
        "trading day of the contract"
    )],
}


def get_contract_table(active=None):
    """
    get contracts expire table
    """
    contracts = pyg.get_data("spreads", active=active, item="sprd_chain")
    flat = pyg.get_data("contracts", active=active, item="fut_chain")
    flat["ticker_far"] = flat["ticker"].shift(-1)
    contracts.rename(columns={"t3": "t"}, inplace=True)
    flat.rename(columns={"t3": "t"}, inplace=True)
    contracts = pd.merge(
        contracts, flat[["t", "ticker", "ticker_far"]], how="left", left_on="t", right_on="t"
    )
    contracts.rename(columns={"ticker_x": "ticker"}, inplace=True)
    contracts.rename(columns={"ticker_y": "ticker_under"}, inplace=True)
    return contracts


def save_intraday_sharpe_old(ins):
    sdate = today() - relativedelta(months=2, day=1)
    edate = today() + relativedelta(months=1, day=30)
    contract_table = get_contract_table(ins)
    contract_table["last_t"] = contract_table["last_t"].shift(1)
    contracts = contract_table.loc[
        (contract_table["last_t"] >= sdate) & (contract_table["last_t"] <= edate), :
    ]
    contracts.reset_index(drop=True, inplace=True)

    result = []
    result1 = []
    for idx, row in contracts.iterrows():
        if idx >= 0 and idx < len(contracts) - 1:
            print(row["ticker"])
            ticker = row["ticker"]
            ticker_under = row["ticker_under"]

            contract_sdate = CDR(active=ins).bday_adj(row["last_t"], -4, adj="p")
            contract_edate = CDR(active=ins).bday_adj(row["last_t"], -1, adj="p")
            contract_sdate = contract_sdate + dt.timedelta(hours=19, minutes=20)
            contract_edate = contract_edate + dt.timedelta(hours=19, minutes=30)
            price = bbg.bdib(ticker, contract_sdate, contract_edate, interval=10)
            price = price["close"]
            chg = price.diff()
            sharpe = chg.mean() / chg.std() * np.sqrt(len(chg))
            result.append([ticker, price.index[0], price.index[-1], price[-1] - price[0], sharpe])
            price1 = bbg.bdib(ticker_under, contract_sdate, contract_edate, interval=10)
            price1 = price1["close"]
            chg1 = price1.diff()
            sharpe1 = chg1.mean() / chg1.std() * np.sqrt(len(chg1))
            result1.append(
                [ticker_under, price1.index[0], price1.index[-1], price1[-1] - price1[0], sharpe1]
            )

    df = pd.DataFrame(result, columns=["Ticker", "Start", "End", "Price Change", "Sharpe Ratio"])
    df.to_csv(convert_path_to_linux(f"{csv_path}\\cross_cmds\\contract_analysis_{ins}_sprd.csv"))
    df1 = pd.DataFrame(result1, columns=["Ticker", "Start", "End", "Price Change", "Sharpe Ratio"])
    df1.to_csv(convert_path_to_linux(f"{csv_path}\\cross_cmds\\contract_analysis_{ins}_flat.csv"))


def save_intraday_sharpe(ins):
    sdate = today() - relativedelta(months=1, day=1)
    edate = today() + relativedelta(months=1, day=30)
    contract_table = get_contract_table(ins)
    contract_table["last_t"] = contract_table["last_t"].shift(1)
    contracts = contract_table.loc[
        (contract_table["last_t"] >= sdate) & (contract_table["last_t"] <= edate), :
    ]
    contracts.reset_index(drop=True, inplace=True)

    result = []
    result1 = []
    for idx, row in contracts.iterrows():
        if idx >= 0 and idx < len(contracts) - 1:
            print(row["ticker"])
            ticker = row["ticker"]
            ticker_under = row["ticker_under"]

            contract_sdate = CDR(active=ins).bday_adj(today(), -4, adj="p")
            contract_edate = CDR(active=ins).bday_adj(today(), -1, adj="p")
            contract_sdate = contract_sdate + dt.timedelta(hours=19, minutes=20)
            contract_edate = contract_edate + dt.timedelta(hours=19, minutes=30)
            price = bbg.bdib(ticker, contract_sdate, contract_edate, interval=10)
            price = price["close"]
            chg = price.diff()
            sharpe = chg.mean() / chg.std() * np.sqrt(len(chg))
            result.append([ticker, price.index[0], price.index[-1], price[-1] - price[0], sharpe])
            price1 = bbg.bdib(ticker_under, contract_sdate, contract_edate, interval=10)
            price1 = price1["close"]
            chg1 = price1.diff()
            sharpe1 = chg1.mean() / chg1.std() * np.sqrt(len(chg1))
            result1.append(
                [ticker_under, price1.index[0], price1.index[-1], price1[-1] - price1[0], sharpe1]
            )

    df = pd.DataFrame(result, columns=["Ticker", "Start", "End", "Price Change", "Sharpe Ratio"])
    df.to_csv(convert_path_to_linux(f"{csv_path}\\cross_cmds\\contract_analysis_{ins}_sprd.csv"))
    df1 = pd.DataFrame(result1, columns=["Ticker", "Start", "End", "Price Change", "Sharpe Ratio"])
    df1.to_csv(convert_path_to_linux(f"{csv_path}\\cross_cmds\\contract_analysis_{ins}_flat.csv"))


def send_contract_expiry_analysis_alert():
    for ins in ins_list:
        if ins in ["CLA Comdty", "COA Comdty", "XBA Comdty", "HOA Comdty", "QSA Comdty"]:
            send_to = oil_group
        elif ins in ["NGA Comdty", "TZTA Comdty"]:
            send_to = gas_group
        contracts_ = pyg.get_data("contracts", active=ins, item="fut_chain")
        live_contract = contracts_.loc[(contracts_["last_t"] > today()), :].iloc[:2, :]
        next_contract = live_contract.iloc[-1, :]
        print(f"Next contract for {ins} is {next_contract['ticker']} expiring on {next_contract['last_t']}")
        for idx, row in live_contract.iterrows():
            penul_day = CDR(active=ins).bday_adj(live_contract.loc[idx, "last_t"], -1, adj="p")
            print(
                f"{row.ticker} | email_date: {penul_day.strftime('%Y-%m-%d')} | expiry: {row.last_t.strftime('%Y-%m-%d')}"
            )
            if penul_day == today():
                save_intraday_sharpe(ins)
                raise NotImplementedError("Missing expiry message/link tails: IMG_5118/5119 lines 223-226")
                send_email(
                    send_to=send_to,
                    subject=f"Contract analysis for {next_contract.ticker}",
                    body=[
                        f"{row['ticker']} will expire in 1 day. Here is the link to contract analysis templa [photo clipped]",
                        (
                            '<a href="https://elementcapital.atlassian.net/wiki/spaces/L025/pages/1774682130 [photo clipped]'
                            "https://elementcapital.atlassian.net/wiki/spaces/L025/pages/1774682130/Contract [photo clipped]"
                        ),
                        "Please see attachments for intraday sharpe ratio.",
                    ],
                    attachments=[
                        convert_path_to_linux(
                            f"{csv_path}\\cross_cmds\\contract_analysis_{ins}_sprd.csv"
                        ),
                        convert_path_to_linux(
                            f"{csv_path}\\cross_cmds\\contract_analysis_{ins}_flat.csv"
                        ),
                    ],
                )


def send_contract_position_limit(send_to):
    for key, val in limit_dict.items():
        contracts = pyg.get_data("contracts", active=key, item="fut_chain")
        live_contract = contracts.loc[(contracts["last_t"] > today()), :].iloc[:2, :]
        for idx, row in live_contract.iterrows():
            penul_day = CDR(active=key).bday_adj(live_contract.loc[idx, "last_t"], val[0], adj="p")
            if penul_day == today():
                send_email(
                    send_to=send_to,
                    subject=f"{live_contract.loc[idx, 'ticker']} Limit day",
                    body=[f"Next trading day is {row['ticker']} limit day.", val[1]],
                )


def update():
    send_contract_expiry_analysis_alert()
    send_contract_position_limit(send_to=send_to)


if __name__ == "__main__":
    update()
