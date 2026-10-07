import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
from pandas.tseries.offsets import BDay
from dateutil.relativedelta import relativedelta, FR
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
import ecm.cmds.time_series as ts
from ecm.cmds.config import output_path, html_path, root_path, gas_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux

from weather_common import demand_forecast_chart
from weather_common import combine_actual_forecast_normal_global_cdd as cdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_global_hdd as hdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_global_tdd as tdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_us as us_cdd_hdd_fcst_data
from weather_common import combine_actual_forecast_normal_us_tdd as us_tdd_fcst_data

send_to = gas_group
report_name = "Weather - Global GFS00z"
file_name = "stormvista_gfs00"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"


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
        start_datetime=dt.datetime(2023, 7, 1, 6, 32),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=10),
        repetition_duration=dt.timedelta(minutes=120),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def download_tdd_us_gfs():
    fields = ['ew_cdd', 'gw_hdd']
    cycles = ['00', '06', '12', '18']
    for cycle in cycles:
        for field in fields:
            max_date = sql.read_sql(
                f"Select MAX(As_of_date) from CWG_StormVista_US_National_GFS where Cycle='{cycle}' and Field='{field}'")
            if max_date.iloc[0, 0] is not None:
                sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
            else:
                sdate = dt.datetime(2018, 7, 8)
            edate = today()
            if sdate <= edate:
                dts = pd.date_range(sdate, edate)
                for i in dts:
                    print(i)
                    data = sv.us_wdd(i, field=field, cycle=cycle, model="gfs-ens")
                    if len(data) > 0:
                        data.columns = ['Dates', 'Value', 'Flag']
                        data['Field'] = field
                        data['Cycle'] = cycle
                        data['As_of_date'] = i
                        sql.to_sql(data, 'CWG_StormVista_US_National_GFS', index=False)


def download_tdd_regional_gfs():
    fields = ['ew_cdd', 'gw_hdd']
    cycles = ['00', '06', '12', '18']
    for cycle in cycles:
        for field in fields:
            max_date = sql.read_sql(
                f"Select MAX(As_of_date) from CWG_StormVista_US_Regional_GFS where Cycle='{cycle}' and Field='{field}'")
            if max_date.iloc[0, 0] is not None:
                sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
            else:
                sdate = dt.datetime(2018, 7, 8)
            edate = today()
            if sdate <= edate:
                dts = pd.date_range(sdate, edate)
                for i in dts:
                    print(i)
                    raw = sv.us_wdd_regional(i, field=field, cycle=cycle, model="gfs-ens")
                    if len(raw) > 0:
                        raw['Date'] = pd.to_datetime(raw['Date'])
                        data = pd.DataFrame()
                        for col in raw.columns[1:]:
                            data_ = raw[['Date', col]]
                            data_.columns = ['Dates', 'Value']
                            data_['Region'] = col
                            data = pd.concat([data, data_], ignore_index=True, axis=0)
                        data['Field'] = field
                        data['Cycle'] = cycle
                        data['As_of_date'] = i
                        sql.to_sql(data, 'CWG_StormVista_US_Regional_GFS', index=False)


def download_tdd_global_gfs():
    fields = ['asia', 'ttf']
    cycles = ['00', '06', '12', '18']
    for cycle in cycles:
        for field in fields:
            max_date = sql.read_sql(
                f"Select MAX(As_of_date) from CWG_StormVista_Global_fcast_GFS where Cycle='{cycle}' and Region='{field}'")
            if max_date.iloc[0, 0] is not None:
                sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
            else:
                sdate = dt.datetime(2019, 6, 10)
            edate = today()
            if sdate <= edate:
                dts = pd.date_range(sdate, edate)
                for i in dts:
                    print(i)
                    raw = sv.global_wdd(i, area=field, cycle=cycle, model="gfs-ens")
                    if len(raw) > 0:
                        raw['Date'] = pd.to_datetime(raw['Date'])
                        data = pd.DataFrame()
                        for col in raw.columns[1:]:
                            data_ = raw[['Date', col]]
                            data_.columns = ['Dates', 'Value']
                            data_['Field'] = col.lower()
                            data = pd.concat([data, data_], ignore_index=True, axis=0)
                        data['Region'] = field
                        data['Cycle'] = cycle
                        data['As_of_date'] = i
                        sql.to_sql(data, 'CWG_StormVista_Global_fcast_GFS', index=False)


def get_us_change_gfs(live_contract, run='00'):
    cdate = today()
    cdd_chg_df = pd.DataFrame(np.nan, index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['US'])
    hdd_chg_df = pd.DataFrame(np.nan, index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['US'])
    if live_contract['m'] in ['K', 'M', 'N', 'Q', 'U', 'V', 'X']:
        fcast = sql.read_sql(
            (f"Select * from CWG_StormVista_US_National_GFS where Cycle='{run}' and Field='ew_cdd' "
             f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast.Dates = pd.to_datetime(fcast.Dates)
        fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
        ydate = np.sort(fcast['As_of_date'].unique())
        td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
        td.set_index('Dates', inplace=True)
        yd = fcast[(fcast['As_of_date'] == cdate - dt.timedelta(days=1))]
        if len(yd) == 0:
            raise ValueError('Data is not updated!')
        else:
            yd.set_index('Dates', inplace=True)
            yd = yd.loc[td.index, :]
            cdd_chg = td['Value'].sum() - yd['Value'].sum()
        d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
        d3.set_index('Dates', inplace=True)
        d3 = d3.loc[td.index, :]
        cdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
        d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
        d5.set_index('Dates', inplace=True)
        d5 = d5.loc[td.index, :]
        cdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
        if run != "12":
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='12' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            dfri = dfri.loc[td.index, :]
            cdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        else:
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast[(fcast['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            dfri = dfri.loc[td.index, :]
            cdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        if run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='12' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='00' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='18' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        if run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='00' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='06' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='18' and Field='ew_cdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        cdd_chg_df.loc['6H', 'US'] = cdd_chg_6h
        cdd_chg_df.loc['12H', 'US'] = cdd_chg_12h
        cdd_chg_df.loc['24H', 'US'] = cdd_chg
        cdd_chg_df.loc['3D', 'US'] = cdd_chg_3d
        cdd_chg_df.loc['5D', 'US'] = cdd_chg_5d
        cdd_chg_df.loc['FRI 12Z', 'US'] = cdd_chg_fri
        cdd_chg_df.index.name = 'US CDD'
    if live_contract['m'] in ['X', 'Z', 'F', 'G', 'H', 'J', 'K']:
        fcast = sql.read_sql(
            (f"Select * from CWG_StormVista_US_National_GFS where Cycle='{run}' and Field='gw_hdd' "
             f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast.Dates = pd.to_datetime(fcast.Dates)
        fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
        ydate = np.sort(fcast['As_of_date'].unique())
        td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
        td.set_index('Dates', inplace=True)
        yd = fcast[(fcast['As_of_date'] == cdate - dt.timedelta(days=1))]
        if len(yd) == 0:
            raise ValueError('Data is not updated!')
        else:
            yd.set_index('Dates', inplace=True)
            yd = yd.loc[td.index, :]
            hdd_chg = td['Value'].sum() - yd['Value'].sum()
        d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
        d3.set_index('Dates', inplace=True)
        d3 = d3.loc[td.index, :]
        hdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
        d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
        d5.set_index('Dates', inplace=True)
        d5 = d5.loc[td.index, :]
        hdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
        if run != "12":
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='12' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            dfri = dfri.loc[td.index, :]
            hdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        else:
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast[(fcast['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            dfri = dfri.loc[td.index, :]
            hdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        if run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='12' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='00' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='18' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        if run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='00' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='06' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_National_GFS where Cycle='18' and Field='gw_hdd' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        hdd_chg_df.loc['6H', 'US'] = hdd_chg_6h
        hdd_chg_df.loc['12H', 'US'] = hdd_chg_12h
        hdd_chg_df.loc['24H', 'US'] = hdd_chg
        hdd_chg_df.loc['3D', 'US'] = hdd_chg_3d
        hdd_chg_df.loc['5D', 'US'] = hdd_chg_5d
        hdd_chg_df.loc['FRI 12Z', 'US'] = hdd_chg_fri
        hdd_chg_df.index.name = 'US HDD'
    if live_contract['m'] in ['M', 'N', 'Q', 'U', 'V']:
        cdd_chg_df.index.name = 'CDD'
        dd_chg_df = cdd_chg_df.reset_index()
    elif live_contract['m'] in ['Z', 'F', 'G', 'H', 'J']:
        hdd_chg_df.index.name = 'HDD'
        dd_chg_df = hdd_chg_df.reset_index()
    else:
        dd_chg_df = cdd_chg_df + hdd_chg_df
        dd_chg_df.index.name = 'TDD'
        dd_chg_df.reset_index(inplace=True)
    return dd_chg_df, cdd_chg_df, hdd_chg_df


def get_regional_change_gfs(live_contract, region='South Central', run='00'):
    cdate = today()
    cdd_chg_df = pd.DataFrame(np.nan, index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=[region])
    hdd_chg_df = pd.DataFrame(np.nan, index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=[region])
    if live_contract['m'] in ['K', 'M', 'N', 'Q', 'U', 'V', 'X']:
        norm = sv.us_wdd_regional_climo(field='ew_cdd')
        yr = today().year
        if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
            pass
        else:
            norm.drop(59, axis=0, inplace=True)
        dts = [dt.datetime(yr, int(x[:2]), int(x[-2:])) for x in norm['Date']]
        norm['Date'] = dts
        norm['Date'] = pd.to_datetime(norm['Date'])
        norm.set_index('Date', inplace=True)
        fcast = sql.read_sql(
            (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='{run}' and Field='ew_cdd' and Region='{region}' "
             f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast.Dates = pd.to_datetime(fcast.Dates)
        fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
        ydate = np.sort(fcast['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        yd = fcast[(fcast['As_of_date'] == cdate - dt.timedelta(days=1))]
        if len(yd) == 0:
            raise ValueError('Data is not updated!')
        else:
            yd.set_index('Dates', inplace=True)
            norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
            yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
            yd = yd.loc[td.index, :]
            cdd_chg = td['Value'].sum() - yd['Value'].sum()
        d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
        d3.set_index('Dates', inplace=True)
        norm_after_d3 = norm.loc[norm.index > d3.index[-1], region]
        d3 = pd.concat([d3, norm_after_d3.to_frame('Value')], axis=0)
        d3 = d3.loc[td.index, :]
        cdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
        d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
        d5.set_index('Dates', inplace=True)
        norm_after_d5 = norm.loc[norm.index > d5.index[-1], region]
        d5 = pd.concat([d5, norm_after_d5.to_frame('Value')], axis=0)
        d5 = d5.loc[td.index, :]
        cdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
        if run != "12":
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='12' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], region]
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            cdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        else:
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast[(fcast['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], region]
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            cdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        if run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='12' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='00' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='18' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        if run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='00' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='06' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='18' and Field='ew_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        cdd_chg_df.loc['6H', region] = cdd_chg_6h
        cdd_chg_df.loc['12H', region] = cdd_chg_12h
        cdd_chg_df.loc['24H', region] = cdd_chg
        cdd_chg_df.loc['3D', region] = cdd_chg_3d
        cdd_chg_df.loc['5D', region] = cdd_chg_5d
        cdd_chg_df.loc['FRI 12Z', region] = cdd_chg_fri
        cdd_chg_df.index.name = 'US CDD'
    if live_contract['m'] in ['X', 'Z', 'F', 'G', 'H', 'J', 'K']:
        norm = sv.us_wdd_regional_climo(field='gw_hdd')
        norm1 = norm.copy()
        yr = today().year
        yr1 = today().year + 1
        if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
            pass
        else:
            norm.drop(59, axis=0, inplace=True)
        dts = [dt.datetime(yr, int(x[:2]), int(x[-2:])) for x in norm['Date']]
        norm['Date'] = dts
        norm['Date'] = pd.to_datetime(norm['Date'])
        norm.set_index('Date', inplace=True)
        if yr1 % 4 == 0 and (yr1 % 100 != 0 or yr1 % 400 == 0):
            pass
        else:
            norm1.drop(59, axis=0, inplace=True)
        dts1 = [dt.datetime(yr1, int(x[:2]), int(x[-2:])) for x in norm1['Date']]
        norm1['Date'] = dts1
        norm1['Date'] = pd.to_datetime(norm1['Date'])
        norm1.set_index('Date', inplace=True)
        norm = pd.concat([norm, norm1], axis=0)
        fcast = sql.read_sql(
            (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='{run}' and Field='gw_hdd' and Region='{region}' "
             f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast.Dates = pd.to_datetime(fcast.Dates)
        fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
        ydate = np.sort(fcast['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        yd = fcast[(fcast['As_of_date'] == cdate - dt.timedelta(days=1))]
        if len(yd) == 0:
            raise ValueError('Data is not updated!')
        else:
            yd.set_index('Dates', inplace=True)
            norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
            yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
            yd = yd.loc[td.index, :]
            hdd_chg = td['Value'].sum() - yd['Value'].sum()
        d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
        d3.set_index('Dates', inplace=True)
        norm_after_d3 = norm.loc[norm.index > d3.index[-1], region]
        d3 = pd.concat([d3, norm_after_d3.to_frame('Value')], axis=0)
        d3 = d3.loc[td.index, :]
        hdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
        d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
        d5.set_index('Dates', inplace=True)
        norm_after_d5 = norm.loc[norm.index > d5.index[-1], region]
        d5 = pd.concat([d5, norm_after_d5.to_frame('Value')], axis=0)
        d5 = d5.loc[td.index, :]
        hdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
        if run != "12":
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='12' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], region]
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            hdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        else:
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast[(fcast['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], region]
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            hdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        if run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='12' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='00' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='18' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        if run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='00' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='06' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_US_Regional_GFS where Cycle='18' and Field='gw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        hdd_chg_df.loc['6H', region] = hdd_chg_6h
        hdd_chg_df.loc['12H', region] = hdd_chg_12h
        hdd_chg_df.loc['24H', region] = hdd_chg
        hdd_chg_df.loc['3D', region] = hdd_chg_3d
        hdd_chg_df.loc['5D', region] = hdd_chg_5d
        hdd_chg_df.loc['FRI 12Z', region] = hdd_chg_fri
        hdd_chg_df.index.name = 'US HDD'
    if live_contract['m'] in ['M', 'N', 'Q', 'U', 'V']:
        cdd_chg_df.index.name = 'CDD'
        dd_chg_df = cdd_chg_df.reset_index()
    elif live_contract['m'] in ['Z', 'F', 'G', 'H', 'J']:
        hdd_chg_df.index.name = 'HDD'
        dd_chg_df = hdd_chg_df.reset_index()
    else:
        dd_chg_df = cdd_chg_df + hdd_chg_df
        dd_chg_df.index.name = 'TDD'
        dd_chg_df.reset_index(inplace=True)
    return dd_chg_df, cdd_chg_df, hdd_chg_df


def get_global_change_gfs(live_contract, region='asia', run='00'):
    cdate = today()
    cdd_chg_df = pd.DataFrame(np.nan, index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=[region])
    hdd_chg_df = pd.DataFrame(np.nan, index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=[region])
    if live_contract['m'] in ['K', 'M', 'N', 'Q', 'U', 'V', 'X']:
        norm = sv.global_wdd_climo(field='pw_cdd', area=region)
        yr = today().year
        if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
            pass
        else:
            norm.drop(59, axis=0, inplace=True)
        dts = [dt.datetime(yr, int(x[:2]), int(x[-2:])) for x in norm['Date']]
        norm['Date'] = dts
        norm['Date'] = pd.to_datetime(norm['Date'])
        norm.set_index('Date', inplace=True)
        fcast = sql.read_sql(
            (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='{run}' and Field='pw_cdd' and Region='{region}' "
             f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast.Dates = pd.to_datetime(fcast.Dates)
        fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
        ydate = np.sort(fcast['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        yd = fcast[(fcast['As_of_date'] == cdate - dt.timedelta(days=1))]
        if len(yd) == 0:
            raise ValueError('Data is not updated!')
        else:
            yd.set_index('Dates', inplace=True)
            norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
            yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
            yd = yd.loc[td.index, :]
            cdd_chg = td['Value'].sum() - yd['Value'].sum()
        d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
        d3.set_index('Dates', inplace=True)
        norm_after_d3 = norm.loc[norm.index > d3.index[-1], 'Value']
        d3 = pd.concat([d3, norm_after_d3.to_frame('Value')], axis=0)
        d3 = d3.loc[td.index, :]
        cdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
        d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
        d5.set_index('Dates', inplace=True)
        norm_after_d5 = norm.loc[norm.index > d5.index[-1], 'Value']
        d5 = pd.concat([d5, norm_after_d5.to_frame('Value')], axis=0)
        d5 = d5.loc[td.index, :]
        cdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
        if run != "12":
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='12' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], 'Value']
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            cdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        else:
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast[(fcast['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], 'Value']
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            cdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        if run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='12' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='00' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='18' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        if run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='00' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='06' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='18' and Field='pw_cdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                cdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        cdd_chg_df.loc['6H', region] = cdd_chg_6h
        cdd_chg_df.loc['12H', region] = cdd_chg_12h
        cdd_chg_df.loc['24H', region] = cdd_chg
        cdd_chg_df.loc['3D', region] = cdd_chg_3d
        cdd_chg_df.loc['5D', region] = cdd_chg_5d
        cdd_chg_df.loc['FRI 12Z', region] = cdd_chg_fri
        cdd_chg_df.index.name = 'US CDD'
    if live_contract['m'] in ['X', 'Z', 'F', 'G', 'H', 'J', 'K']:
        norm = sv.global_wdd_climo(field='pw_hdd', area=region)
        norm1 = norm.copy()
        yr = today().year
        yr1 = today().year + 1
        if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
            pass
        else:
            norm.drop(59, axis=0, inplace=True)
        dts = [dt.datetime(yr, int(x[:2]), int(x[-2:])) for x in norm['Date']]
        norm['Date'] = dts
        norm['Date'] = pd.to_datetime(norm['Date'])
        norm.set_index('Date', inplace=True)
        if yr1 % 4 == 0 and (yr1 % 100 != 0 or yr1 % 400 == 0):
            pass
        else:
            norm1.drop(59, axis=0, inplace=True)
        dts1 = [dt.datetime(yr1, int(x[:2]), int(x[-2:])) for x in norm1['Date']]
        norm1['Date'] = dts1
        norm1['Date'] = pd.to_datetime(norm1['Date'])
        norm1.set_index('Date', inplace=True)
        norm = pd.concat([norm, norm1], axis=0)
        fcast = sql.read_sql(
            (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='{run}' and Field='pw_hdd' and Region='{region}' "
             f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast.Dates = pd.to_datetime(fcast.Dates)
        fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
        ydate = np.sort(fcast['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        yd = fcast[(fcast['As_of_date'] == cdate - dt.timedelta(days=1))]
        if len(yd) == 0:
            raise ValueError('Data is not updated!')
        else:
            yd.set_index('Dates', inplace=True)
            norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
            yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
            yd = yd.loc[td.index, :]
            hdd_chg = td['Value'].sum() - yd['Value'].sum()
        d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
        d3.set_index('Dates', inplace=True)
        norm_after_d3 = norm.loc[norm.index > d3.index[-1], 'Value']
        d3 = pd.concat([d3, norm_after_d3.to_frame('Value')], axis=0)
        d3 = d3.loc[td.index, :]
        hdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
        d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
        d5.set_index('Dates', inplace=True)
        norm_after_d5 = norm.loc[norm.index > d5.index[-1], 'Value']
        d5 = pd.concat([d5, norm_after_d5.to_frame('Value')], axis=0)
        d5 = d5.loc[td.index, :]
        hdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
        if run != "12":
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='12' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], 'Value']
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            hdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        else:
            last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
            dfri = fcast[(fcast['As_of_date'] == last_fri)]
            dfri.set_index('Dates', inplace=True)
            norm_after_dfri = norm.loc[norm.index > dfri.index[-1], 'Value']
            dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
            dfri = dfri.loc[td.index, :]
            hdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
        if run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='12' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='00' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        elif run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='18' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        if run == '06':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='00' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '12':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='06' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate)]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        elif run == '00':
            fcast_last = sql.read_sql(
                (f"Select * from CWG_StormVista_Global_fcast_GFS where Cycle='18' and Field='pw_hdd' and Region='{region}' "
                 f"and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
                 f"order by As_of_date, Dates"))
            fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
            fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
            ydate = np.sort(fcast_last['As_of_date'].unique())
            td = fcast[fcast['As_of_date'] == cdate]
            td.set_index('Dates', inplace=True)
            yd = fcast_last[(fcast_last['As_of_date'] == cdate - dt.timedelta(days=1))]
            if len(yd) == 0:
                raise ValueError('Data is not updated!')
            else:
                yd.set_index('Dates', inplace=True)
                norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
                yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
                yd = yd.loc[td.index, :]
                hdd_chg_6h = td['Value'].sum() - yd['Value'].sum()
        hdd_chg_df.loc['6H', region] = hdd_chg_6h
        hdd_chg_df.loc['12H', region] = hdd_chg_12h
        hdd_chg_df.loc['24H', region] = hdd_chg
        hdd_chg_df.loc['3D', region] = hdd_chg_3d
        hdd_chg_df.loc['5D', region] = hdd_chg_5d
        hdd_chg_df.loc['FRI 12Z', region] = hdd_chg_fri
        hdd_chg_df.index.name = 'US HDD'
    if live_contract['m'] in ['M', 'N', 'Q', 'U', 'V']:
        cdd_chg_df.index.name = 'CDD'
        dd_chg_df = cdd_chg_df.reset_index()
    elif live_contract['m'] in ['Z', 'F', 'G', 'H', 'J']:
        hdd_chg_df.index.name = 'HDD'
        dd_chg_df = hdd_chg_df.reset_index()
    else:
        dd_chg_df = cdd_chg_df + hdd_chg_df
        dd_chg_df.index.name = 'TDD'
        dd_chg_df.reset_index(inplace=True)
    return dd_chg_df, cdd_chg_df, hdd_chg_df


def _unreadable_argument(line):
    raise NotImplementedError(f"stormvista_gfs00 photographed line {line}: clipped argument")


def get_gfs_change(cycle='00', field='gw_hdd', hours=12):
    file_path = f"\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\US_TDD\\GFS_{field}_{hours}h_{cycle}.csv"
    if os.path.exists(file_path):
        daily_chg_exist = ts.read_csv(file_path, index_name='Unnamed: 0')
        sdate = daily_chg_exist.index[-1]
    else:
        sdate = dt.datetime(2018, 7, 8)
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National_GFS where Cycle='{cycle}' and Field='{field}' and "
         f"As_of_date >='{sdate - dt.timedelta(days=7)}' order by As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    drop_dates = []
    if hours == 24:
        cycle1 = cycle
        day_adj = -1
        if cycle in ['12', '18']:
            drop_dates = [dt.datetime(2020, 8, 15), dt.datetime(2020, 8, 16)]
    elif hours == 12:
        if cycle == '00':
            cycle1 = '12'
            day_adj = -1
            drop_dates = [dt.datetime(2020, 8, 15), dt.datetime(2020, 8, 16)]
        elif cycle == '06':
            cycle1 = '18'
            day_adj = -1
            drop_dates = [dt.datetime(2020, 8, 15), dt.datetime(2020, 8, 16)]
        elif cycle == '12':
            cycle1 = '00'
            day_adj = 0
        elif cycle == '18':
            cycle1 = '06'
            day_adj = 0
    elif hours == 6:
        if cycle == '00':
            cycle1 = '18'
            day_adj = -1
            drop_dates = [dt.datetime(2020, 8, 15), dt.datetime(2020, 8, 16)]
        elif cycle == '06':
            cycle1 = '00'
            day_adj = 0
        elif cycle == '12':
            cycle1 = '06'
            day_adj = 0
        elif cycle == '18':
            cycle1 = '12'
            day_adj = 0
    if cycle1 != cycle:
        fcast1 = sql.read_sql(
            (f"Select * from CWG_StormVista_US_National_GFS where Cycle='{cycle1}' and Field='{field}' and "
             f"As_of_date >='{sdate - dt.timedelta(days=7)}' order by As_of_date, Dates"))
        fcast1.Dates = pd.to_datetime(fcast1.Dates)
        fcast1.As_of_date = pd.to_datetime(fcast1.As_of_date)
    else:
        fcast1 = fcast
    if len(drop_dates) > 0:
        fcast.drop(fcast[fcast['As_of_date'].isin(drop_dates)].index, axis=0, inplace=True)
        fcast1.drop(fcast1[fcast1['As_of_date'].isin(drop_dates)].index, axis=0, inplace=True)
    dts = fcast['As_of_date'].unique()
    daily_chg = pd.Series(0.0, index=dts)
    for idx, i in enumerate(dts):
        if idx > 0:
            td = fcast[(fcast['As_of_date'] == i) & (fcast['Flag'] == 1)]
            td.set_index('Dates', inplace=True)
            yd = fcast1[(fcast1['As_of_date'] == pd.to_datetime(i) + dt.timedelta(day_adj))]
            yd.set_index('Dates', inplace=True)
            if yd.empty:
                continue
            yd = yd.loc[td.index, :]
            daily_chg[i] = td['Value'].sum() - yd['Value'].sum()
    if daily_chg.index[-1] >= sdate:
        daily_chg = pd.concat([daily_chg_exist.iloc[:-1, 0], daily_chg[daily_chg.index >= sdate]], axis=0)
        daily_chg.to_csv(convert_path_to_linux(file_path))
    else:
        daily_chg = daily_chg_exist
    return daily_chg


def seasonal_zscore(data):
    df_index = (data.reset_index())['index']
    df_index = df_index.to_frame('Dates')
    df_index['m'] = data.index.month
    df_index['d'] = data.index.day
    sdate_cdd = dt.datetime(2020, 1, 1)
    sloc_cdd = data.index.get_loc(sdate_cdd)
    i = len(data) - 1
    if df_index.loc[i, 'm'] == 2 and df_index.loc[i, 'd'] == 29:
        center_dates = df_index.loc[(df_index['m'] == 2) & (df_index['d'] == 28), 'Dates']
    else:
        center_dates = df_index.loc[(df_index['m'] == df_index.loc[i, 'm']) & (
            df_index['d'] == df_index.loc[i, 'd']), 'Dates']
    center_loc = [idx for idx, val in center_dates.items() if val <= df_index.loc[i, 'Dates']]
    expand_loc = [list(range(x - 20, x + 20)) for x in center_loc[-5:]]
    expand_loc = [x for sublist in expand_loc for x in sublist if (x >= 0) & (x < i)]
    data_sample = data.iloc[expand_loc]
    data_sample.dropna(inplace=True)
    return data.iloc[i] / data_sample.std()


def get_gfs_zscore(run='00'):
    chg_hdd_24 = get_gfs_change(cycle=run, field='gw_hdd', hours=24)
    zscore_hdd_24 = seasonal_zscore(chg_hdd_24)
    chg_hdd_12 = get_gfs_change(cycle=run, field='gw_hdd', hours=12)
    zscore_hdd_12 = seasonal_zscore(chg_hdd_12)
    chg_hdd_6 = get_gfs_change(cycle=run, field='gw_hdd', hours=6)
    zscore_hdd_6 = seasonal_zscore(chg_hdd_6)
    hdd_chg_df = pd.DataFrame([zscore_hdd_6, zscore_hdd_12, zscore_hdd_24, np.nan, np.nan, np.nan],
        index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['US Zscore'])
    hdd_chg_df.index.name = 'HDD'
    chg_cdd_24 = get_gfs_change(cycle=run, field='ew_cdd', hours=24)
    zscore_cdd_24 = seasonal_zscore(chg_cdd_24)
    chg_cdd_12 = get_gfs_change(cycle=run, field='ew_cdd', hours=12)
    zscore_cdd_12 = seasonal_zscore(chg_cdd_12)
    chg_cdd_6 = get_gfs_change(cycle=run, field='ew_cdd', hours=6)
    zscore_cdd_6 = seasonal_zscore(chg_cdd_6)
    cdd_chg_df = pd.DataFrame([zscore_cdd_6, zscore_cdd_12, zscore_cdd_24, np.nan, np.nan, np.nan],
        index=['6H', '12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['US Zscore'])
    cdd_chg_df.index.name = 'CDD'
    return cdd_chg_df, hdd_chg_df


def send_table_gfs(run='00', send_to=send_to, file_name=file_name, report_name=report_name):
    live_contract = bbg.live_contract(active="NGA Comdty", seq=0, roll="t5")
    dd_us, cdd_us, hdd_us = get_us_change_gfs(live_contract, run=run)
    dd_sc, cdd_sc, hdd_sc = get_regional_change_gfs(live_contract, region='South Central', run=run)
    dd_east, cdd_east, hdd_east = get_regional_change_gfs(live_contract, region='East', run=run)
    dd_ttf, cdd_ttf, hdd_ttf = get_global_change_gfs(live_contract, region='ttf', run=run)
    dd_asia, cdd_asia, hdd_asia = get_global_change_gfs(live_contract, region='asia', run=run)
    cdd_z, hdd_z = get_gfs_zscore(run=run)
    if run == "00":
        release_time = today() + dt.timedelta(hours=6, minutes=30)
    elif run == "06":
        release_time = today() + dt.timedelta(hours=12, minutes=30)
    elif run == "12":
        release_time = today() + dt.timedelta(hours=18, minutes=30)
    if today().weekday() not in [5, 6]:
        ng_intraday = bbg.bdib(live_contract["ticker"], today() - dt.timedelta(days=14), _unreadable_argument(1545), interval=5)
        ng_cur = ng_intraday.loc[ng_intraday.index <= release_time, "close"].iloc[-1]
        ng_6h = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(hours=6), "close"].iloc[-1]
        ng_12h = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(hours=12), "close"].iloc[-1]
        ng_24h = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=1), "close"].iloc[-1]
        ng_3d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=3), "close"].iloc[-1]
        ng_5d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=5), "close"].iloc[-1]
        daily_p = bbg.bdh(live_contract["ticker"], ["PX_LAST"],
            today() - BDay(1) + relativedelta(weekday=FR(-1)) - BDay(2),
            today() - BDay(1) + relativedelta(weekday=FR(-1)))
        ng_fri = daily_p["PX_LAST"].iloc[-1]
        ng_chg = pd.DataFrame(
            [ng_cur / ng_6h - 1, ng_cur / ng_12h - 1, ng_cur / ng_24h - 1, ng_cur / ng_3d - 1, ng_cur / ng_5d - 1, ng_cur / ng_fri - 1],
            index=["6H", "12H", "24H", "3D", "5D", "FRI 12Z"], columns=["NG Chg"])
    else:
        ng_chg = pd.DataFrame(np.nan, index=["6H", "12H", "24H", "3D", "5D", "FRI 12Z"], columns=["NG Chg"])
    ng_chg.reset_index(inplace=True, drop=True)
    if live_contract["m"] in ['X', 'Z', 'F', 'G', 'H', 'J']:
        ng_exp = hdd_us * 0.0014
    elif live_contract["m"] in ['K', 'M', 'N', 'Q', 'U', 'V']:
        ng_exp = cdd_us * 0.0007
    ng_exp.columns = ["NG Exp Chg"]
    ng_exp.reset_index(inplace=True, drop=True)

    live_contract_tzt = bbg.live_contract(active="TZTA Comdty", seq=0, roll="t3")
    tzt_intraday = bbg.bdib(live_contract_tzt["ticker"], today() - dt.timedelta(days=14), _unreadable_argument(1580), interval=5)
    tzt_cur = tzt_intraday.loc[tzt_intraday.index <= release_time, "close"].iloc[-1]
    tzt_6h = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(hours=6), "close"].iloc[-1]
    tzt_12h = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(hours=12), "close"].iloc[-1]
    tzt_24h = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=1), "close"].iloc[-1]
    tzt_3d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=3), "close"].iloc[-1]
    tzt_5d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=5), "close"].iloc[-1]
    tzt_daily_p = bbg.bdh(live_contract_tzt["ticker"], ["PX_LAST"],
        today() - BDay(1) + relativedelta(weekday=FR(-1)) - BDay(2),
        today() - BDay(1) + relativedelta(weekday=FR(-1)))
    tzt_fri = tzt_daily_p["PX_LAST"].iloc[-1]
    tzt_chg = pd.DataFrame(
        [tzt_cur / tzt_6h - 1, tzt_cur / tzt_12h - 1, tzt_cur / tzt_24h - 1, tzt_cur / tzt_3d - 1, tzt_cur / tzt_5d - 1, tzt_cur / tzt_fri - 1],
        index=["6H", "12H", "24H", "3D", "5D", "FRI 12Z"], columns=["TZT Chg"])
    tzt_chg.reset_index(inplace=True, drop=True)
    if live_contract_tzt["m"] in ['X', 'Z', 'F', 'G', 'H', 'J']:
        tzt_exp = hdd_ttf * 0.001
    elif live_contract_tzt["m"] in ['K', 'M', 'N', 'Q', 'U', 'V']:
        tzt_exp = cdd_ttf * 0.0
    tzt_exp.columns = ["TZT Exp Chg"]
    tzt_exp.reset_index(inplace=True, drop=True)

    figs = []
    def add_divergence(data, field1="NG Chg", field2="US National"):
        data["div"] = 0
        data.loc[(data[field1] > 0) & (data[field2] < 0), "div"] = 1
        data.loc[(data[field1] < 0) & (data[field2] > 0), "div"] = -1
        return data

    ng_convert_dict = {10: 0.3, 11: 0.6, 12: 1.4, 1: 1.7, 2: 1.6, 3: 0.8, 4: 0.6, 5: 0, 6: 0, 7: 0, 8: 0, 9: ...}
    us_hdd_bcf_factor = ng_convert_dict[today().month]
    if us_hdd_bcf_factor is Ellipsis:
        raise NotImplementedError("stormvista_gfs00 photographed line 1617: September coefficient clipped")
    us_hdd_bcf = hdd_us * us_hdd_bcf_factor
    us_tdd_bcf = dd_us.set_index(dd_us.columns[0]) * us_hdd_bcf_factor
    ttf_hdd_bcf = hdd_ttf * 36 / 1000
    ttf_tdd_bcf = dd_ttf.set_index(dd_ttf.columns[0]) * 36 / 1000
    asia_hdd_bcf = hdd_asia * 25 / 1000
    asia_tdd_bcf = dd_asia.set_index(dd_asia.columns[0]) * 25 / 1000
    us_hdd_bcf.columns = ["ResCom (BCF)"]
    us_tdd_bcf.columns = ["ResCom (BCF)"]
    ttf_hdd_bcf.columns = ["LDZ (BCM)"]
    ttf_tdd_bcf.columns = ["LDZ (BCM)"]
    asia_hdd_bcf.columns = ["LDZ (BCM)"]
    asia_tdd_bcf.columns = ["LDZ (BCM)"]
    us_tdd_bcf.reset_index(inplace=True)
    ttf_tdd_bcf.reset_index(inplace=True)
    asia_tdd_bcf.reset_index(inplace=True)

    if live_contract['m'] in ['X', 'K']:
        figs.append("<p style='font-size: 24px; font-family:Calibri; font-weight:bold'>TDDs</p>")
        subject = f"Weather - Global TDD, GFS{run}z"
        head = "TDD"
        dd_z = (cdd_z.reset_index())['US Zscore'] + (hdd_z.reset_index())['US Zscore']
        dd_chg_df = pd.concat([dd_us, dd_z, dd_sc['South Central'], dd_east['East'], ng_chg, ng_exp, us_tdd_bcf["ResCom (BCF)"]], axis=1)
        dd_chg_df.columns = [f'{dd_us.columns[0]}', 'US', 'US Zscore', 'South Central', 'East', 'NG Chg', 'NG Exp Chg', 'ResCom (BCF)']
        dd_chg_df = add_divergence(dd_chg_df, "NG Chg", "US")
        figs.append(table.html_format(
            df=dd_chg_df, precision=1, hide_cols=["div"],
            format_column={
                tuple(dd_chg_df.columns): {'width': '100px', 'text-align': 'center'},
                dd_chg_df.columns[-4]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': ...},
                dd_chg_df.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        us_tdd_national_data = us_tdd_fcst_data(cycle=run, area='national', model="GFS")
        us_tdd_east_data = us_tdd_fcst_data(cycle=run, area='East', model="GFS")
        us_tdd_sc_data = us_tdd_fcst_data(cycle=run, area='South Central', model="GFS")
        us_tdd_national_chart = demand_forecast_chart(us_tdd_national_data, title='1-15 TDD forecasts charts for US National', type='tdd')
        us_tdd_east_chart = demand_forecast_chart(us_tdd_east_data, title='1-15 TDD forecasts charts for US East', type='tdd')
        us_tdd_sc_chart = demand_forecast_chart(us_tdd_sc_data, title='1-15 TDD forecasts charts for South Central', type='tdd')
        us_tdd_figs = [us_tdd_national_chart, us_tdd_sc_chart, us_tdd_east_chart]
        figs.extend(us_tdd_figs)
        dd_chg_df = pd.concat([dd_ttf, ttf_tdd_bcf["LDZ (BCM)"], dd_asia['asia'], asia_tdd_bcf["LDZ (BCM)"], tzt_chg, tzt_exp], axis=1)
        dd_chg_df.columns = ['Others', 'EU', 'EU LDZ (BCM)', 'Asia', 'Asia LDZ (BCM)', 'TZT Chg', 'TZT Exp Chg']
        dd_chg_df = add_divergence(dd_chg_df, "TZT Chg", "EU")
        figs.append(table.html_format(
            df=dd_chg_df, precision=1, hide_cols=["div"],
            format_column={
                tuple(dd_chg_df.columns): {'width': '100px', 'text-align': 'center'},
                dd_chg_df.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': ...},
                dd_chg_df.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        eu_tdd_data = tdd_fcst_asia_eu(area='ttf', cycle=run, model="GFS")
        eu_tdd_chart = demand_forecast_chart(eu_tdd_data, title='1-15 TDD forecasts charts for Europe', type='tdd')
        figs.append(eu_tdd_chart)
        asia_tdd_data = tdd_fcst_asia_eu(area='asia', cycle=run, model="GFS")
        asia_tdd_chart = demand_forecast_chart(asia_tdd_data, title='1-15 TDD forecasts charts for Asia', type='tdd')
        figs.append(asia_tdd_chart)
        cdd_chg_df = pd.concat([cdd_us, cdd_ttf, cdd_asia], axis=1)
        cdd_chg_df.columns = ['US', 'EU', 'Asia']
        cdd_chg_df.index.name = 'CDD'
        cdd_chg_df.reset_index(inplace=True)
        hdd_chg_df = pd.concat([hdd_us, hdd_ttf, hdd_asia], axis=1)
        hdd_chg_df.columns = ['US', 'EU', 'Asia']
        hdd_chg_df.index.name = 'HDD'
        hdd_chg_df.reset_index(inplace=True)
    elif live_contract['m'] in ['Z', 'F', 'G', 'H', 'J']:
        figs.append("<p style='font-size: 24px; font-family:Calibri; font-weight:bold'>HDDs</p>")
        subject = f"Weather - Global HDD, GFS{run}z"
        head = "HDD"
        dd_z = (hdd_z.reset_index())['US Zscore']
        dd_chg_df = pd.concat([dd_us, dd_z, dd_sc['South Central'], dd_east['East'], ng_chg, ng_exp, us_tdd_bcf["ResCom (BCF)"]], axis=1)
        dd_chg_df.columns = [f'{dd_us.columns[0]}', 'US', 'US Zscore', 'South Central', 'East', 'NG Chg', 'NG Exp Chg', 'ResCom (BCF)']
        dd_chg_df = add_divergence(dd_chg_df, "NG Chg", "US")
        figs.append(table.html_format(
            df=dd_chg_df, precision=1, hide_cols=["div"],
            format_column={
                tuple(dd_chg_df.columns): {'width': '100px', 'text-align': 'center'},
                dd_chg_df.columns[-4]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': ...},
                dd_chg_df.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        us_hdd_national_data = us_cdd_hdd_fcst_data(cycle=run, area='national', is_cdd=False, model="GFS")
        us_hdd_east_data = us_cdd_hdd_fcst_data(cycle=run, area='East', is_cdd=False, model="GFS")
        us_hdd_sc_data = us_cdd_hdd_fcst_data(cycle=run, area='South Central', is_cdd=False, model="GFS")
        us_hdd_national_chart = demand_forecast_chart(us_hdd_national_data, title='1-15 HDD forecasts charts for US National', type='hdd')
        us_hdd_east_chart = demand_forecast_chart(us_hdd_east_data, title='1-15 HDD forecasts charts for US East', type='hdd')
        us_hdd_sc_chart = demand_forecast_chart(us_hdd_sc_data, title='1-15 HDD forecasts charts for South Central', type='hdd')
        us_hdd_figs = [us_hdd_national_chart, us_hdd_sc_chart, us_hdd_east_chart]
        figs.extend(us_hdd_figs)
        dd_chg_df = pd.concat([dd_ttf, ttf_tdd_bcf["LDZ (BCM)"], dd_asia['asia'], asia_tdd_bcf["LDZ (BCM)"], tzt_chg, tzt_exp], axis=1)
        dd_chg_df.columns = ['Others', 'EU', 'EU LDZ (BCM)', 'Asia', 'Asia LDZ (BCM)', 'TZT Chg', 'TZT Exp Chg']
        dd_chg_df = add_divergence(dd_chg_df, "TZT Chg", "EU")
        figs.append(table.html_format(
            df=dd_chg_df, precision=1, hide_cols=["div"],
            format_column={
                tuple(dd_chg_df.columns): {'width': '100px', 'text-align': 'center'},
                dd_chg_df.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': ...},
                dd_chg_df.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        eu_hdd_data = hdd_fcst_asia_eu(area='ttf', cycle=run, model="GFS")
        eu_hdd_chart = demand_forecast_chart(eu_hdd_data, title='1-15 HDD forecasts charts for Europe', type='hdd')
        figs.append(eu_hdd_chart)
        asia_hdd_data = hdd_fcst_asia_eu(area='asia', cycle=run, model="GFS")
        asia_hdd_chart = demand_forecast_chart(asia_hdd_data, title='1-15 HDD forecasts charts for Asia', type='hdd')
        figs.append(asia_hdd_chart)
        hdd_chg_df = pd.concat([hdd_us, hdd_ttf, hdd_asia], axis=1)
        hdd_chg_df.columns = ['US', 'EU', 'Asia']
    elif live_contract['m'] in ['M', 'N', 'Q', 'U', 'V']:
        figs.append("<p style='font-size: 24px; font-family:Calibri; font-weight:bold'>CDDs</p>")
        subject = f"Weather - Global CDD, GFS{run}z"
        head = "CDD"
        dd_z = (cdd_z.reset_index())['US Zscore']
        dd_chg_df = pd.concat([dd_us, dd_z, dd_sc['South Central'], dd_east['East'], ng_chg], axis=1)
        dd_chg_df.columns = [f'{dd_us.columns[0]}', 'US', 'US Zscore', 'South Central', 'East', 'NG Chg']
        dd_chg_df = add_divergence(dd_chg_df, "NG Chg", "US")
        figs.append(table.html_format(
            df=dd_chg_df, precision=1, hide_cols=["div"],
            format_column={
                tuple(dd_chg_df.columns): {'width': '100px', 'text-align': 'center'},
                dd_chg_df.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': ...}}))
        us_hdd_national_data = us_cdd_hdd_fcst_data(cycle=run, area='national', is_cdd=True, model="GFS")
        us_hdd_east_data = us_cdd_hdd_fcst_data(cycle=run, area='East', is_cdd=True, model="GFS")
        us_hdd_sc_data = us_cdd_hdd_fcst_data(cycle=run, area='South Central', is_cdd=True, model="GFS")
        us_hdd_national_chart = demand_forecast_chart(us_hdd_national_data, title='1-15 CDD forecasts charts for US National', type='cdd')
        us_hdd_east_chart = demand_forecast_chart(us_hdd_east_data, title='1-15 CDD forecasts charts for US East', type='cdd')
        us_hdd_sc_chart = demand_forecast_chart(us_hdd_sc_data, title='1-15 CDD forecasts charts for South Central', type='cdd')
        us_hdd_figs = [us_hdd_national_chart, us_hdd_sc_chart, us_hdd_east_chart]
        figs.extend(us_hdd_figs)
        dd_chg_df = pd.concat([dd_ttf, dd_asia['asia'], tzt_chg], axis=1)
        dd_chg_df.columns = ['Others', 'EU', 'Asia', 'TZT Chg']
        dd_chg_df = add_divergence(dd_chg_df, "TZT Chg", "EU")
        figs.append(table.html_format(
            df=dd_chg_df, precision=1, hide_cols=["div"],
            format_column={
                tuple(dd_chg_df.columns): {'width': '100px', 'text-align': 'center'},
                dd_chg_df.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': ...}}))
        eu_cdd_data = cdd_fcst_asia_eu(area='ttf', cycle=run, model="GFS")
        eu_cdd_chart = demand_forecast_chart(eu_cdd_data, title='1-15 CDD forecasts charts for Europe', type='cdd')
        figs.append(eu_cdd_chart)
        asia_cdd_data = cdd_fcst_asia_eu(area='asia', cycle=run, model="GFS")
        asia_cdd_chart = demand_forecast_chart(asia_cdd_data, title='1-15 CDD forecasts charts for Asia', type='cdd')
        figs.append(asia_cdd_chart)
        cdd_chg_df = pd.concat([cdd_us, cdd_ttf, cdd_asia], axis=1)
        cdd_chg_df.columns = ['US', 'EU', 'Asia']

    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(head, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\weather\\{file_name}.html", task_name=report_name)
    send_email(send_to=send_to, subject=subject, body=figs, html_path=f"{html_path}\\weather\\{file_name}.html")


def gfs_run(cycle='00', send_to=send_to, file_name=file_name, report_name=report_name):
    download_tdd_us_gfs()
    download_tdd_regional_gfs()
    download_tdd_global_gfs()
    run_status = pd.read_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\GFS_saved_run.csv"))
    run_status.columns = ['run', 'result']
    run_status.set_index('run', inplace=True)
    if run_status.loc[int(cycle), 'result'] == 0:
        max_date1 = sql.read_sql(
            f"Select MAX(As_of_date) from CWG_StormVista_US_National_GFS where Cycle='{cycle}' and Field='gw_hdd'")
        max_date2 = sql.read_sql(
            f"Select MAX(As_of_date) from CWG_StormVista_Global_fcast_GFS where Cycle='{cycle}' and Region='ttf'")
        max_date3 = sql.read_sql(
            f"Select MAX(As_of_date) from CWG_StormVista_Global_fcast_GFS where Cycle='{cycle}' and Region='asia'")
        if max_date1.iloc[0, 0] == max_date2.iloc[0, 0] == max_date3.iloc[0, 0] == today().strftime('%Y-%m-%d'):
            if cycle in ['00', '06', '12']:
                send_table_gfs(run=cycle, send_to=send_to, file_name=file_name, report_name=report_name)
                run_status.loc[int(cycle), 'result'] = 1
                run_status.loc[run_status.index != int(cycle), 'result'] = 0
                run_status.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\GFS_saved_run.csv"))


def update():
    gfs_run(cycle='00', send_to=send_to, file_name=file_name)


if __name__ == "__main__":
    update()
