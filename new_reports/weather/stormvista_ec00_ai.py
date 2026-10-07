import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import math
import pytz
import urllib
import sqlalchemy as sa
from pandas.tseries.offsets import BDay
from dateutil.relativedelta import relativedelta, FR

from dateutil.rrule import rrule, MINUTELY
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.time_series as ts
from ecm.cmds.cdr import today
from ecm.cmds.config import output_path, html_path, root_path, csv_path, data_path
from ecm.cmds.talib import realizedvol, rolling_ols, seasonal_sd
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux

sys.path.append(convert_path_to_linux(f"{root_path}\\autoreports\\reports\\weather"))
sys.path.append(convert_path_to_linux(f"{root_path}\\model\\src"))
import teleconnection
from tracking.EC00_new_2 import cwg_monthly_cdd, cwg_monthly_hdd, get_ng_vs_tdd, get_ttf_vs_tdd, cwg_monthly_cdd_region, \
    cwg_monthly_hdd_region, cwg_monthly_cdd_global, cwg_monthly_hdd_global
from stormvista_ec46 import send_table as send_ec46
from weather_common import demand_forecast_chart
from weather_common import combine_actual_forecast_normal_global_cdd as cdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_global_hdd as hdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_global_tdd as tdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_us as us_cdd_hdd_fcst_data
from weather_common import combine_actual_forecast_normal_us_tdd as us_tdd_fcst_data

folder_path = "S:\\Michel Kikano\\Data\\US_TDD\\"
params = urllib.parse.quote_plus("DRIVER={SQL SERVER};"
                                "SERVER=NYSQL06v;"
                                "DATABASE=LO25;"
                                "TRUSTED_CONNECTION = YES")

engine = sa.create_engine("mssql+pyodbc:///?odbc_connect={}".format(params))

send_to = ['Commods@elementcapital.com']
send_to_quant = ['rzhao@elementcapital.com', 'ltrindade@elementcapital.com']
report_name = "AI Weather model"
file_name = "stormvista_ec00_ai"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
size_EC00 = 10000000 * 0.7


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY | Days.SUNDAY,
        start_datetime=dt.datetime(2022, 7, 1, 6, 27),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=5),
        repetition_duration=dt.timedelta(minutes=120),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update_us_national_ai(run='00'):
    fields = ['ew_cdd', 'gw_hdd']
    cycles = ['00', '06', '12', '18']
    models = ['ai-graphcast-gdas-ecmwf-eps']
    has_latest_data = [False, False]
    for cycle in cycles:
        for idx, field in enumerate(fields):
            for model in models:
                max_date = sql.read_sql(
                    f"Select MAX(As_of_date) from CWG_StormVista_US_National_AI where Cycle='{cycle}' and Field='{field}' and Model='{model}'")
                if max_date.iloc[0, 0] is not None:
                    sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
                else:
                    sdate = dt.datetime(2024, 8, 13)
                edate = today()
                if sdate <= edate:
                    dts = pd.date_range(sdate, edate)
                    for i in dts:
                        print(i)
                        data = sv.us_wdd(i, field=field, cycle=cycle, model=model)
                        if len(data) > 0:
                            data.columns = ['Dates', 'Value', 'Flag']
                            data['Field'] = field
                            data['Model'] = model
                            data['Cycle'] = cycle
                            data['As_of_date'] = i
                            sql.to_sql(data, 'CWG_StormVista_US_National_AI', index=False)
                            if i == today() and cycle == run and model == 'ai-graphcast-gdas-ecmwf-eps':
                                has_latest_data[idx] = True
                elif cycle == run:
                    has_latest_data[idx] = True
    return has_latest_data

def ng_tdd_chg(cdate, cycle='00', field='ew_cdd', model='ai-graphcast-gdas-ecmwf-eps'):
    """
    1d change of US national CDD/HDD
    """
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National_AI where Cycle='{cycle}' and Field='{field}' and Model='{model}' and "
         f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' order by "
         f"As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
    td.set_index('Dates', inplace=True)
    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    yd = yd.loc[td.index, :]
    return td['Value'].sum() - yd['Value'].sum()


def ng_tdd_chg_1115(cdate, cycle='00', field='ew_cdd', model='ai-graphcast-gdas-ecmwf-eps'):
    """
    1d change of US national CDD/HDD
    """
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National_AI where Cycle='{cycle}' and Field='{field}' and Model='{model}' and "
         f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' order by "
         f"As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
    td.set_index('Dates', inplace=True)
    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    yd = yd.loc[td.index, :]
    return td['Value'].iloc[10:].sum() - yd['Value'].iloc[10:].sum()


def ng_tdd_12h_chg(cdate, cycle='00', field='ew_cdd', model='ai-graphcast-gdas-ecmwf-eps'):
    """
    1d change of US national CDD/HDD
    """
    fcast00 = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National_AI where Cycle='00' and Field='{field}' and Model='{model}' and "
         f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' order by "
         f"As_of_date, Dates"))
    fcast00.Dates = pd.to_datetime(fcast00.Dates)
    fcast00.As_of_date = pd.to_datetime(fcast00.As_of_date)
    fcast12 = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National_AI where Cycle='12' and Field='{field}' and Model='{model}' and "
         f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' order by "
         f"As_of_date, Dates"))
    fcast12.Dates = pd.to_datetime(fcast12.Dates)
    fcast12.As_of_date = pd.to_datetime(fcast12.As_of_date)
    if cycle == '00':
        ydate = np.sort(fcast12['As_of_date'].unique())
        td = fcast00[(fcast00['As_of_date'] == cdate) & (fcast00['Flag'] == 1)]
        td = td.iloc[:-1, :]
        td.set_index('Dates', inplace=True)
        yd = fcast12[(fcast12['As_of_date'] == ydate[-1])]
    elif cycle == '12':
        ydate = np.sort(fcast00['As_of_date'].unique())
        td = fcast12[(fcast12['As_of_date'] == cdate) & (fcast12['Flag'] == 1)]
        td.set_index('Dates', inplace=True)
        yd = fcast00[(fcast00['As_of_date'] == ydate[-1])]
    yd.set_index('Dates', inplace=True)
    yd = yd.loc[td.index, :]
    return td['Value'].sum() - yd['Value'].sum()


def cal_trade(live_contract, size_per_trade=size_EC00, base_ccy='USD', vop=10000):
    trade_date = today()
    price = bbg.bdh(live_contract['ticker'], ['PX_LAST'], trade_date - dt.timedelta(days=56), trade_date)
    price = price['PX_LAST']
    price_d = price.diff() / price.shift(1) * 100
    vol = realizedvol(price_d, rollwindow=30, annualize=260)
    last_vol = vol[vol.index < trade_date][-1]
    size_in_usd = size_per_trade * 10 / last_vol
    return size_in_usd / (vop * price[-1]), live_contract['ticker']


def send_trade_ng():
    live_contract = bbg.live_contract(active="NGA Comdty", seq=0, roll="t3")
    if today().weekday() not in [5, 6]:
        tdd_str = 'TDD'
        cdd_chg = ng_tdd_chg_1115(today(), cycle='00', field='ew_cdd')
        hdd_chg = ng_tdd_chg_1115(today(), cycle='00', field='gw_hdd')
        tdd_chg = cdd_chg + hdd_chg
        cdd_chg_12 = ng_tdd_12h_chg(today(), cycle='00', field='ew_cdd')
        hdd_chg_12 = ng_tdd_12h_chg(today(), cycle='00', field='gw_hdd')
        tdd_chg_12 = cdd_chg_12 + hdd_chg_12
        num_contracts, live_ticker = cal_trade(live_contract=live_contract)
        if live_ticker[2] in ['M', 'N', 'Q', 'U', 'V']:
            if tdd_chg > 2:
                trade_body = f"BUY {int(num_contracts)} {live_ticker}. {tdd_str} 11-15d 24H forecast change: {tdd_chg:.1f}."
            elif tdd_chg < -2:
                trade_body = f"SELL {int(num_contracts)} {live_ticker}. {tdd_str} 11-15d 24H forecast change: {tdd_chg:.1f}."
            else:
                trade_body = f"No trade. {tdd_str} 11-15d forecast change {tdd_chg:.1f}."
        else:
            if tdd_chg > 2:
                trade_body = f"BUY {int(num_contracts)} {live_ticker}. {tdd_str} 11-15d 24H forecast change: {tdd_chg:.1f}."
            elif tdd_chg < -2:
                trade_body = f"SELL {int(num_contracts)} {live_ticker}. {tdd_str} 11-15d 24H forecast change: {tdd_chg:.1f}."
            else:
                trade_body = f"No trade. {tdd_str} 11-15d forecast change {tdd_chg:.1f}."
        trade_body += f"<br>TDD 0-14d 12H forecast change {tdd_chg_12:.1f}."
        send_email(send_to=send_to,
                   subject=f"SYS - NG AI-GRAPHCAST change on {dt.datetime.strftime(today(), '%Y-%m-%d')} is {tdd_chg:.1f}",
                   body=trade_body)


def tdd_00z():
    run = False
    if not os.path.exists(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_00z_ai.csv")):
        run = True
        run_state = pd.DataFrame()
    else:
        run_state = pd.read_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_00z_ai.csv"))
        run_state.set_index("Unnamed: 0", inplace=True)
        run_state = run_state.iloc[:, 0]
        if today().strftime('%Y-%m-%d') not in run_state.values:
            run = True
    run_us = update_us_national_ai(run='00')
    if run and all(run_us):
        send_trade_ng()
        run_state_new = pd.Series(today().strftime('%Y-%m-%d'), index=[0])
        if len(run_state) > 0:
            run_state = pd.concat([run_state, run_state_new], ignore_index=True, axis=0)
        else:
            run_state = run_state_new
        run_state.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_00z_ai.csv"))


if __name__ == "__main__":
    tdd_00z()
