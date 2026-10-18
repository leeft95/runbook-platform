import datetime as dt
import ecm.cmds.pyg as pyg
import ecm.cmds.cdr as cdr
import ecm.cmds.bbg as bbg
from functools import partial
from pyg_mongo import *
from pyg_cell import *
from ecm.atom.services.tools import rvx_query_frame
from ecm.data.api import RTHQueryClient
from fastparquet import write, ParquetFile
import pandas as pd
import os
import sys
import pytz
from pyg_base import mkdir
from ecm.cmds.config import root_path, data_path
from ecm.cmds.utils import convert_path_to_linux

report_name = "Update Intraday Prices"
file_name = "intraday"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\data\\{file_name}.py"


def _unrecovered(location):
    """Recovery marker: this expression extends beyond the supplied photograph."""
    raise NotImplementedError(f"Unrecovered source: {location}")


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
        start_datetime=dt.datetime(2022, 7, 1, 5, 25),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f"{report_name}", filepath=f"{file_path}"),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def get_intraday_price(base_ticker='NG'):
    import getpass
    user = getpass.getuser()
    if user == "pmlo25_svc":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_TOKEN_PMLO25_SVC"]
    elif user == "rzhao":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_TOKEN_RZHAO"]
    if base_ticker[-1] == ' ':
        folder_path = mkdir(convert_path_to_linux(f"{data_path}\\intraday\\{base_ticker[0]}\\"))
    else:
        folder_path = mkdir(convert_path_to_linux(f"{data_path}\\intraday\\{base_ticker}\\"))
    contracts = pyg.get_data('contracts', active=f"{base_ticker}A Comdty", item='fut_chain')
    contracts['last_t'] = pd.to_datetime(contracts['last_t'])
    contracts = contracts.loc[(contracts['last_t'] >= dt.datetime(2010, 1, 1)) & (contracts['last_t'] <= _unrecovered('IMG_5013/5014 line 60: dt.datetime upper bound'))]
    filenames = os.listdir(folder_path)
    for idx, row in contracts.iterrows():
        update = True
        print(row['ticker'])
        if f"{row['ticker']}.parq" in filenames:
            md_time = os.path.getmtime(f"{folder_path}/{row['ticker']}.parq")
            if row['last_t'] < dt.datetime.utcfromtimestamp(md_time):
                update = False
        if update:
            sdate = row['fut_first_trade_dt']
            edate = row['last_t']
            try:
                data = RTHQueryClient.load_minute_bars(
                    "futures", sdate, edate,
                    ops_codes=[f"{base_ticker} COMDTY {row['ticker'][len(base_ticker):len(base_ticker)+3]}"],
                    fields=["price_first", "price_max", "price_min", "price_last", "volume"],
                )
                data.index = data.index.tz_localize(pytz.timezone("UTC")).tz_convert(
                    pytz.timezone("US/Eastern")).tz_localize(None)
            except:
                data = None
            if data is not None and not data['price_last'].isna().values.all():
                data = data[["price_first", "price_max", "price_min", "price_last", "volume"]]
                if len(data) > 0:
                    data.columns = ['openp', 'highp', 'lowp', 'closep', 'volume']
                    write(f"{folder_path}/{row['ticker']}.parq", data)


def get_intraday_sprd(base_ticker='NG'):
    import getpass
    user = getpass.getuser()
    if user == "pmlo25_svc":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_TOKEN_PMLO25_SVC"]
    elif user == "rzhao":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_TOKEN_RZHAO"]
    folder_path = convert_path_to_linux(f"{data_path}\\intraday\\{base_ticker}_sprd\\")
    contracts = pyg.get_data('spreads', active=f"{base_ticker}A Comdty", item='sprd_chain')
    contracts['last_t'] = pd.to_datetime(contracts['last_t'])
    contracts = contracts.loc[(contracts['last_t'] >= dt.datetime(2010, 1, 1)) & (contracts['last_t'] <= _unrecovered('IMG_5014/5015 line 104: dt.datetime upper bound'))]
    filenames = os.listdir(folder_path)
    for idx, row in contracts.iterrows():
        update = True
        print(row['ticker'])
        if f"{row['ticker'][2:]}.parq" in filenames:
            md_time = os.path.getmtime(f"{folder_path}{row['ticker'][2:]}.parq")
            if row['last_t'] < dt.datetime.utcfromtimestamp(md_time):
                update = False
        if update:
            sdate = row['fut_first_trade_dt']
            edate = row['last_t']
            sprd_ticker = ' '.join(row['ticker'].split(' ')[1].split('-'))
            data = RTHQueryClient.load_minute_bars(
                "futures", sdate, edate,
                ops_codes=[f"{base_ticker} COMDTY {sprd_ticker}"],
                fields=["price_first", "price_max", "price_min", "price_last", "volume"],
            )
            data.index = data.index.tz_localize(pytz.timezone("UTC")).tz_convert(
                pytz.timezone("US/Eastern")).tz_localize(None)
            if data is not None:
                data = data[["price_first", "price_max", "price_min", "price_last", "volume"]]
                if len(data) > 0:
                    data.columns = ['openp', 'highp', 'lowp', 'closep', 'volume']
                    write(f"{folder_path}{row['ticker'][2:]}.parq", data)


def update():
    get_intraday_price(base_ticker='NG')
    get_intraday_price(base_ticker='TZT')
    get_intraday_sprd(base_ticker='QS')
    get_intraday_price(base_ticker='QS')
    get_intraday_price(base_ticker='CL')
    get_intraday_price(base_ticker='CO')
    get_intraday_sprd(base_ticker='CO')
    get_intraday_price(base_ticker='XB')
    get_intraday_price(base_ticker='HO')
    get_intraday_price(base_ticker='HG')
    get_intraday_price(base_ticker='GC')


if __name__ == '__main__':
    update()
