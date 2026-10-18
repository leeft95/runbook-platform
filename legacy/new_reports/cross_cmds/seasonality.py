import pandas as pd
import numpy as np
import sys
import datetime as dt
import time
from ecm.cmds.config import root_path, html_path, oil_group, macro_group, gas_group
from pandas.tseries.offsets import BDay
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.talib as talib
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, getworkingdays, CDR

send_to_dev = None  # ["ltrindade"]
send_to_gas = send_to_dev or gas_group
send_to = send_to_dev or ["rzhao@elementcapital.com"]
report_name = "Seasonality"
file_name = "seasonality"  # without .py
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
        start_datetime=dt.datetime(2023, 7, 1, 6, 20),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()



ins_list = ['CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty', 'NGA Comdty', 'TZTA Comdty']
flat_m_list = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]
sprd_m_list = ["F-G", "G-H", "H-J", "J-K", "K-M", "M-N", "N-Q", "Q-U", "U-V", "V-X", "X-Z", "Z-F"]


def season(active, spread):
    sdate = dt.datetime(2010, 1, 1)
    if spread:
        contracts = pyg.get_data("spreads", active=active, item="sprd_chain")
        m_list = sprd_m_list
    else:
        contracts = pyg.get_data("contracts", active=active, item="fut_chain")
        m_list = flat_m_list
    raise NotImplementedError("Missing contract horizon: IMG_5425/5426 line 61")
    contracts["start_t"] = contracts["t1"].shift(1)
    season_df = pd.DataFrame(0, index=range(2010, today().year + 1), columns=m_list)
    for i in m_list:
        if "-" in i:
            same_month = contracts.loc[contracts["m"] == i[0], :]
        else:
            same_month = contracts.loc[contracts["m"] == i, :]
        all_price = pd.DataFrame()
        for idx, row in same_month.iterrows():
            if row["start_t"] <= today():
                if row['t1'] >= today():
                    price = bbg.bdh(row["ticker"], ['PX_LAST'], row['start_t'], today())
                else:
                    if spread:
                        raise NotImplementedError("Missing spread query: IMG_5426 line 76")
                    else:
                        price = pyg.get_data("contracts_PX_LAST", active=active, m=row['m'], y=row['y'])
                    price = price.loc[(price.index >= row["start_t"]) & (price.index <= row["t1"])]
                if spread:
                    season_df.loc[row['y'], i] = price.iloc[-1, 0] - price.iloc[0, 0]
                else:
                    season_df.loc[row['y'], i] = (price.iloc[-1, 0] - price.iloc[0, 0]) / price.iloc[0, 0]
                all_price = pd.concat([all_price, price.reset_index(drop=True)], axis=1)
    season_df.loc["Mean"] = season_df.mean(axis=0)
    season_df.loc["Z-score"] = season_df.mean(axis=0) / season_df.std(axis=0)
    season_df.loc["Hit ratio"] = season_df[season_df > 0].count(axis=0) / season_df.count(axis=0)
    return season_df


if __name__ == "__main__":
    season(active="COA Comdty", spread=False)
