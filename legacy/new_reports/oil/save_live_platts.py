import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
from pandas.tseries.offsets import BDay
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
from ecm.cmds.cdr import today
import ecm.cmds.time_series as ts
import getpass
from ecm.cmds.config import url, root_path, data_path
from ecm.atom.wintask.scheduler import ECMWinTask
from ecm.atom.wintask.utils import Days

report_name = "Save Platts live price"
file_name = "save_live_platts"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"

current_user = getpass.getuser()


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2025, 1, 2, 17, 0),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=10),
        repetition_duration=dt.timedelta(hours=3),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


ins_dict = {
    'Forties': ['PCRUFRT2 PLRT Index', 'AAGWZ00'],
    'Eko': ['PCRUEKO2 PLRT Index', 'AAGXB00'],
    'Urals': ['PCRUURD1 PLRT Index', 'AAGXJ00'],
    'CPC': ['PCRUTENG PLRT Index', 'AAHPL00'],
    'Saharan': ['PCRUSHBA PLRT Index', 'AAHPN00'],
    'Azeri': ['PCRUAZCF PLRT Index', 'AAHPM00'],
    'WTI FOB': ['NARI0148 PLRT Index', 'ALNDB00'],
    'Bonny': ['PCRUBLT2 PLRT Index', 'AAGXL00'],
    'Johan': ['NARI0118 PLRT Index', 'AJSVB00'],
    'CIF': ['PEURBG00 PLRT Index', 'AAVBG00'],
    'FOB': ['PEURGONW PLRT Index', 'AAJUS00'],
    '50ppm': ['PEURG50B PLRT Index', 'AAUQC00'],
    'Med': ['PEURM10C PLRT Index', 'AAWYZ00'],
    'USGC Pipe Diff': ['NAUG0074 PLRT Index', 'ADICA00'],
    'Sing Diff': ['PASOGOSM PLRT Index', 'POAIC00'],
}


def get_platts_from_bbg():
    save_folder = f"{data_path}\\platts\\live"
    for k, v in ins_dict.items():
        if os.path.exists(f"{save_folder}\\{k}.csv"):
            exist = ts.read_csv(f"{save_folder}\\{k}.csv", index_name="date")
            sdate = exist.index[-1]
        else:
            try:
                sdate = pyg.get_data(pyg.data_db("platts"), platts_ticker=v[1]).index[-1]
            except:
                sdate = today() - BDay(5)
        if sdate < today():
            try:
                if current_user == "mkikano":
                    live_price = bbg.bdh(v[0], ["PX_LAST"], sdate - BDay(5), today() + BDay(1))
                else:
                    live_price = bbg.get_platts(platts_ticker=v[1], sdate=sdate - BDay(5), edate=today() + BDay(1))
            except:
                live_price = bbg.get_platts(platts_ticker=v[1], sdate=sdate - BDay(5), edate=today() + BDay(1))

            if len(live_price) > 0:
                live_price.to_csv(f"{save_folder}\\{k}.csv")


def update():
    get_platts_from_bbg()


if __name__ == "__main__":
    update()
