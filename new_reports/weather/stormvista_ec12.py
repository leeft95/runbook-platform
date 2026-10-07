import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import math
from dateutil.rrule import rrule, MINUTELY
from pandas.tseries.offsets import BDay
from dateutil.relativedelta import relativedelta, FR
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
import ecm.cmds.time_series as ts
import ecm.cmds.chart as chart
from ecm.cmds.cdr import today, month_int2str
from ecm.cmds.config import output_path, html_path, root_path, csv_path
from ecm.cmds.talib import realizedvol
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux


from weather_common import demand_forecast_chart
from weather_common import combine_actual_forecast_normal_global_cdd as cdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_global_hdd as hdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_global_tdd as tdd_fcst_asia_eu
from weather_common import combine_actual_forecast_normal_us as us_cdd_hdd_fcst_data
from weather_common import combine_actual_forecast_normal_us_tdd as us_tdd_fcst_data


send_to = ['Commods@elementcapital.com']
report_name = "Weather - Global EC12z"
file_name = "stormvista_ec12"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Day

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY | Days.SUNDAY,
        start_datetime=dt.datetime(2022, 7, 1, 18, 35),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=5),
        repetition_duration=dt.timedelta(minutes=120),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update_us_national(run='00'):
    fields = ['ew_cdd', 'gw_hdd']
    cycles = ['00', '12']
    has_latest_data = [False, False]
    for cycle in cycles:
        for idx, field in enumerate(fields):
            max_date = sql.read_sql(
                f"Select MAX(As_of_date) from CWG_StormVista_US_National where Cycle='{cycle}' and Field='{field}'")
            if max_date.iloc[0, 0] is not None:
                sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
            else:
                sdate = dt.datetime(2018, 7, 10)
            edate = today()
            if sdate <= edate:
                dts = pd.date_range(sdate, edate)
                for i in dts:
                    data = sv.us_wdd(i, field=field, cycle=cycle)
                    if len(data) > 0:
                        data.columns = ['Dates', 'Value', 'Flag']
                        data['Field'] = field
                        data['Cycle'] = cycle
                        data['As_of_date'] = i
                        sql.to_sql(data, 'CWG_StormVista_US_National', index=False)
                        if i == today() and cycle == run:
                            has_latest_data[idx] = True
            elif cycle == run:
                has_latest_data[idx] = True
    return has_latest_data


def update_us_regional():
    fields = ['ew_cdd', 'gw_hdd']
    cycles = ['00', '12']
    for cycle in cycles:
        for idx, field in enumerate(fields):
            max_date = sql.read_sql(
                f"Select MAX(As_of_date) from CWG_StormVista_US_Regional where Cycle='{cycle}' and Field='{field}'")
            if max_date.iloc[0, 0] is not None:
                sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
            else:
                sdate = dt.datetime(2018, 7, 10)
            edate = today()
            if sdate <= edate:
                dts = pd.date_range(sdate, edate)
                for i in dts:
                    raw = sv.us_wdd_regional(i, field=field, cycle=cycle)
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
                        sql.to_sql(data, 'CWG_StormVista_US_Regional', index=False)


def update_global(run='00'):
    fields = ['asia', 'europe', 'italy', 'uk', 'ttf', 'china', 'japan', 'skorea']
    cycles = ['00', '12']
    has_latest_data = [False, False, False, False, False, False, False, False]
    for cycle in cycles:
        for idx, field in enumerate(fields):
            max_date = sql.read_sql(
                f"Select MAX(As_of_date) from CWG_StormVista_Global_fcast where Cycle='{cycle}' and Region='{field}'")
            if max_date.iloc[0, 0] is not None:
                sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
            else:
                sdate = dt.datetime(2018, 7, 10)
            edate = today()
            if sdate <= edate:
                dts = pd.date_range(sdate, edate)
                for i in dts:
                    raw = sv.global_wdd(i, area=field, cycle=cycle)
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
                        sql.to_sql(data, 'CWG_StormVista_Global_fcast', index=False)
                        if i == today() and cycle == run:
                            has_latest_data[idx] = True
            elif cycle == run:
                has_latest_data[idx] = True
    return has_latest_data


def us_national_tdd_chg(cdate, run='00', field='ew_cdd'):
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National where Cycle='{run}' and "
         f"Field='{field}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
         f"order by As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
    td.set_index('Dates', inplace=True)
    daily_fcst = pd.DataFrame(0, index=td.index, columns=["12H", "24H", "3D", "5D", "FRI 12Z"])
    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    yd = yd.loc[td.index, :]
    daily_fcst["24H"] = td["Value"] - yd["Value"]
    tdd_chg = td['Value'].sum() - yd['Value'].sum()
    d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
    d3.set_index('Dates', inplace=True)
    d3 = d3.loc[td.index, :]
    daily_fcst["3D"] = td["Value"] - d3["Value"]
    tdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
    d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
    d5.set_index('Dates', inplace=True)
    d5 = d5.loc[td.index, :]
    daily_fcst["5D"] = td["Value"] - d5["Value"]
    tdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
    if run == '00':
        fcast_last = sql.read_sql(
            (f"Select * from CWG_StormVista_US_National where Cycle='12' and Field='{field}' and "
             f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
        fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
        ydate = np.sort(fcast_last['As_of_date'].unique())
        td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
        td.set_index('Dates', inplace=True)
        if pd.to_datetime(ydate[-1]) == cdate:
            yd = fcast_last[(fcast_last['As_of_date'] == ydate[-2])]
        else:
            yd = fcast_last[(fcast_last['As_of_date'] == ydate[-1])]
        yd.set_index('Dates', inplace=True)
        yd = yd.loc[td.index, :]
        daily_fcst["12H"] = td["Value"] - yd["Value"]
        tdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
        dfri.set_index('Dates', inplace=True)
        dfri = dfri.loc[td.index, :]
        daily_fcst["FRI 12Z"] = td["Value"] - dfri["Value"]
        tdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
    else:
        fcast_last = sql.read_sql(
            (f"Select * from CWG_StormVista_US_National where Cycle='00' and Field='{field}' and "
             f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
        fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
        ydate = np.sort(fcast_last['As_of_date'].unique())
        td = fcast[(fcast['As_of_date'] == cdate) & (fcast['Flag'] == 1)]
        td.set_index('Dates', inplace=True)
        yd = fcast_last[(fcast_last['As_of_date'] == ydate[-1])]
        yd.set_index('Dates', inplace=True)
        yd = yd.loc[td.index, :]
        daily_fcst["12H"] = td["Value"] - yd["Value"]
        tdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
        dfri.set_index('Dates', inplace=True)
        dfri = dfri.loc[td.index, :]
        daily_fcst["FRI 12Z"] = td["Value"] - dfri["Value"]
        tdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
    tdd_chg_df = pd.DataFrame(np.nan, index=['12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['US National'])
    tdd_chg_df.loc['12H', 'US National'] = tdd_chg_12h
    tdd_chg_df.loc['24H', 'US National'] = tdd_chg
    tdd_chg_df.loc['3D', 'US National'] = tdd_chg_3d
    tdd_chg_df.loc['5D', 'US National'] = tdd_chg_5d
    tdd_chg_df.loc['FRI 12Z', 'US National'] = tdd_chg_fri
    if field[-3:] == 'cdd':
        tdd_chg_df.index.name = 'US CDD'
    elif field[-3:] == 'hdd':
        tdd_chg_df.index.name = 'US HDD'
    else:
        tdd_chg_df.index.name = 'US TDD'
    return tdd_chg_df, daily_fcst


def us_regional_tdd_chg(cdate, region='East', run='00', field='ew_cdd'):
    norm = sv.us_wdd_regional_climo(field=field)
    norm1 = norm.copy()
    yr = today().year
    if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
        pass
    else:
        norm.drop(59, axis=0, inplace=True)
    dts = [dt.datetime(yr, int(x[:2]), int(x[-2:])) for x in norm['Date']]
    norm['Date'] = dts
    norm['Date'] = pd.to_datetime(norm['Date'])
    norm.set_index('Date', inplace=True)
    yr1 = today().year + 1
    if yr1 % 4 == 0 and (yr1 % 100 != 0 or yr1 % 400 == 0):
        pass
    else:
        norm1.drop(59, axis=0, inplace=True)
    dts1 = [dt.datetime(yr+1, int(x[:2]), int(x[-2:])) for x in norm1['Date']]
    norm1['Date'] = dts1
    norm1['Date'] = pd.to_datetime(norm1['Date'])
    norm1.set_index('Date', inplace=True)
    norm = pd.concat([norm, norm1], axis=0)
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_Regional where Cycle='{run}' and Field='{field}' and "
         f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
         f"order by As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[fcast['As_of_date'] == cdate]
    td.set_index('Dates', inplace=True)
    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
    yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
    yd = yd.loc[td.index, :]
    tdd_chg = td['Value'].sum() - yd['Value'].sum()
    d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
    d3.set_index('Dates', inplace=True)
    norm_after_d3 = norm.loc[norm.index > d3.index[-1], region]
    d3 = pd.concat([d3, norm_after_d3.to_frame('Value')], axis=0)
    d3 = d3.loc[td.index, :]
    tdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
    d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
    d5.set_index('Dates', inplace=True)
    norm_after_d5 = norm.loc[norm.index > d5.index[-1], region]
    d5 = pd.concat([d5, norm_after_d5.to_frame('Value')], axis=0)
    d5 = d5.loc[td.index, :]
    tdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
    if run == '00':
        fcast_last = sql.read_sql(
            (f"Select * from CWG_StormVista_US_Regional where Cycle='12' and Field='{field}' and "
             f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
        fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
        ydate = np.sort(fcast_last['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        if pd.to_datetime(ydate[-1]) == cdate:
            yd = fcast_last[(fcast_last['As_of_date'] == ydate[-2])]
        else:
            yd = fcast_last[(fcast_last['As_of_date'] == ydate[-1])]
        yd.set_index('Dates', inplace=True)
        norm_after_yd = norm.loc[norm.index > yd.index[-1], region]
        yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
        yd = yd.loc[td.index, :]
        tdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
        dfri.set_index('Dates', inplace=True)
        norm_after_dfri = norm.loc[norm.index > dfri.index[-1], region]
        dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
        dfri = dfri.loc[td.index, :]
        tdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
    else:
        fcast_last = sql.read_sql(
            (f"Select * from CWG_StormVista_US_Regional where Cycle='00' and Field='{field}' and "
             f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
        fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
        ydate = np.sort(fcast_last['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        yd = fcast_last[(fcast_last['As_of_date'] == ydate[-1])]
        yd.set_index('Dates', inplace=True)
        yd = yd.loc[td.index, :]
        tdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
        dfri.set_index('Dates', inplace=True)
        norm_after_dfri = norm.loc[norm.index > dfri.index[-1], region]
        dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
        dfri = dfri.loc[td.index, :]
        tdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
    tdd_chg_df = pd.DataFrame(np.nan, index=['12H', '24H', '3D', '5D', 'FRI 12Z'], columns=[region])
    tdd_chg_df.loc['12H', region] = tdd_chg_12h
    tdd_chg_df.loc['24H', region] = tdd_chg
    tdd_chg_df.loc['3D', region] = tdd_chg_3d
    tdd_chg_df.loc['5D', region] = tdd_chg_5d
    tdd_chg_df.loc['FRI 12Z', region] = tdd_chg_fri
    if field[-3:] == 'cdd':
        tdd_chg_df.index.name = f'{region} CDD'
    elif field[-3:] == 'hdd':
        tdd_chg_df.index.name = f'{region} HDD'
    else:
        tdd_chg_df.index.name = f'{region} TDD'
    return tdd_chg_df


def global_tdd_chg(cdate, region='asia', run='00', field='pw_cdd'):
    norm = sv.global_wdd_climo(field=field, area=region)
    norm1 = norm.copy()
    yr = today().year
    if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
        pass
    else:
        norm.drop(59, axis=0, inplace=True)
    dts = [dt.datetime(yr, int(x[:2]), int(x[-2:])) for x in norm['Date']]
    norm['Date'] = dts
    norm['Date'] = pd.to_datetime(norm['Date'])
    norm.set_index('Date', inplace=True)
    yr1 = today().year + 1
    if yr1 % 4 == 0 and (yr1 % 100 != 0 or yr1 % 400 == 0):
        pass
    else:
        norm1.drop(59, axis=0, inplace=True)
    dts1 = [dt.datetime(yr+1, int(x[:2]), int(x[-2:])) for x in norm1['Date']]
    norm1['Date'] = dts1
    norm1['Date'] = pd.to_datetime(norm1['Date'])
    norm1.set_index('Date', inplace=True)
    norm = pd.concat([norm, norm1], axis=0)
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_Global_fcast where Cycle='{run}' and Field='{field}' and "
         f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
         f"order by As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[fcast['As_of_date'] == cdate]
    td.set_index('Dates', inplace=True)
    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
    yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
    yd = yd.loc[td.index, :]
    tdd_chg = td['Value'].sum() - yd['Value'].sum()
    d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
    d3.set_index('Dates', inplace=True)
    norm_after_d3 = norm.loc[norm.index > d3.index[-1], 'Value']
    d3 = pd.concat([d3, norm_after_d3.to_frame('Value')], axis=0)
    d3 = d3.loc[td.index, :]
    tdd_chg_3d = td['Value'].sum() - d3['Value'].sum()
    d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
    d5.set_index('Dates', inplace=True)
    norm_after_d5 = norm.loc[norm.index > d5.index[-1], 'Value']
    d5 = pd.concat([d5, norm_after_d5.to_frame('Value')], axis=0)
    d5 = d5.loc[td.index, :]
    tdd_chg_5d = td['Value'].sum() - d5['Value'].sum()
    if run == '00':
        fcast_last = sql.read_sql(
            (f"Select * from CWG_StormVista_Global_fcast where Cycle='12' and Field='{field}' and "
             f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
        fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
        ydate = np.sort(fcast_last['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        if pd.to_datetime(ydate[-1]) == cdate:
            yd = fcast_last[(fcast_last['As_of_date'] == ydate[-2])]
        else:
            yd = fcast_last[(fcast_last['As_of_date'] == ydate[-1])]
        yd.set_index('Dates', inplace=True)
        norm_after_yd = norm.loc[norm.index > yd.index[-1], 'Value']
        yd = pd.concat([yd, norm_after_yd.to_frame('Value')], axis=0)
        yd = yd.loc[td.index, :]
        tdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
        dfri.set_index('Dates', inplace=True)
        norm_after_dfri = norm.loc[norm.index > dfri.index[-1], 'Value']
        dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
        dfri = dfri.loc[td.index, :]
        tdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
    else:
        fcast_last = sql.read_sql(
            (f"Select * from CWG_StormVista_Global_fcast where Cycle='00' and Field='{field}' and "
             f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' "
             f"order by As_of_date, Dates"))
        fcast_last.Dates = pd.to_datetime(fcast_last.Dates)
        fcast_last.As_of_date = pd.to_datetime(fcast_last.As_of_date)
        ydate = np.sort(fcast_last['As_of_date'].unique())
        td = fcast[fcast['As_of_date'] == cdate]
        td.set_index('Dates', inplace=True)
        yd = fcast_last[(fcast_last['As_of_date'] == ydate[-1])]
        yd.set_index('Dates', inplace=True)
        yd = yd.loc[td.index, :]
        tdd_chg_12h = td['Value'].sum() - yd['Value'].sum()
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        dfri = fcast_last[(fcast_last['As_of_date'] == last_fri)]
        dfri.set_index('Dates', inplace=True)
        norm_after_dfri = norm.loc[norm.index > dfri.index[-1], 'Value']
        dfri = pd.concat([dfri, norm_after_dfri.to_frame('Value')], axis=0)
        dfri = dfri.loc[td.index, :]
        tdd_chg_fri = td['Value'].sum() - dfri['Value'].sum()
    tdd_chg_df = pd.DataFrame(np.nan, index=['12H', '24H', '3D', '5D', 'FRI 12Z'], columns=[region.upper()])
    tdd_chg_df.loc['12H', region.upper()] = tdd_chg_12h
    tdd_chg_df.loc['24H', region.upper()] = tdd_chg
    tdd_chg_df.loc['3D', region.upper()] = tdd_chg_3d
    tdd_chg_df.loc['5D', region.upper()] = tdd_chg_5d
    tdd_chg_df.loc['FRI 12Z', region.upper()] = tdd_chg_fri
    if field[-3:] == 'cdd':
        tdd_chg_df.index.name = f'{region.upper()} CDD'
    elif field[-3:] == 'hdd':
        tdd_chg_df.index.name = f'{region.upper()} HDD'
    else:
        tdd_chg_df.index.name = f'{region.upper()} TDD'
    return tdd_chg_df


def get_weather_index(date=today(), a='00', b="ecmwf-eps"):
    scand = sv.teleconnections(file_date=date, ind='scand', cycle=a, model=b)
    try:
        scand.loc['mean'] = scand.mean()
    except ValueError:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    scand = scand.drop('member', axis=1)
    scand = scand.transpose()
    nao = sv.teleconnections(file_date=date, ind='nao', cycle=a, model=b)
    nao.loc['mean'] = nao.mean()
    nao = nao.drop('member', axis=1)
    nao = nao.transpose()
    ao = sv.teleconnections(file_date=date, ind='ao', cycle=a, model=b)
    ao.loc['mean'] = ao.mean()
    ao = ao.drop('member', axis=1)
    ao = ao.transpose()
    ea = sv.teleconnections(file_date=date, ind='ea', cycle=a, model=b)
    ea.loc['mean'] = ea.mean()
    ea = ea.drop('member', axis=1)
    ea = ea.transpose()
    eawr = sv.teleconnections(file_date=date, ind='eawr', cycle=a, model=b)
    eawr.loc['mean'] = eawr.mean()
    eawr = eawr.drop('member', axis=1)
    eawr = eawr.transpose()
    epo = sv.teleconnections(file_date=date, ind='epo', cycle=a, model=b)
    epo.loc['mean'] = epo.mean()
    epo = epo.drop('member', axis=1)
    epo = epo.transpose()
    wpo = sv.teleconnections(file_date=date, ind='wpo', cycle=a, model=b)
    wpo.loc['mean'] = wpo.mean()
    wpo = wpo.drop('member', axis=1)
    wpo = wpo.transpose()
    pna = sv.teleconnections(file_date=date, ind='pna', cycle=a, model=b)
    pna.loc['mean'] = pna.mean()
    pna = pna.drop('member', axis=1)
    pna = pna.transpose()

    eu_index = pd.DataFrame()
    eu_index['SCAND'] = scand['mean']
    eu_index['NAO'] = -nao['mean']
    eu_index['AO'] = -ao['mean']
    eu_index['EA'] = -ea['mean']
    eu_index['EAWR'] = -eawr['mean']
    eu_index['EU Index'] = eu_index.sum(axis=1)
    eu_index.drop(eu_index.index[:9], inplace=True)
    eu_index.loc[date] = eu_index.mean()
    eu_index = eu_index[['EU Index', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR']]

    us_index = pd.DataFrame()
    us_index['EPO'] = -epo['mean']
    us_index['WPO'] = -wpo['mean']
    us_index['PNA'] = pna['mean']
    us_index['NAO'] = -nao['mean']
    us_index['US Index'] = us_index.sum(axis=1)
    us_index.drop(us_index.index[:9], inplace=True)
    us_index.loc[date] = us_index.mean()
    us_index = us_index[['US Index', 'EPO', 'WPO', 'PNA', 'NAO']]

    asia_index = pd.DataFrame()
    asia_index['EAWR'] = -eawr['mean']
    asia_index['WPO'] = -wpo['mean']
    asia_index['SCAND'] = scand['mean']
    asia_index['Asia Index'] = asia_index.sum(axis=1)
    asia_index.drop(asia_index.index[:9], inplace=True)
    asia_index.loc[date] = asia_index.mean()
    asia_index = asia_index[['Asia Index', 'EAWR', 'WPO', 'SCAND']]
    return eu_index.iloc[[-1], :], us_index.iloc[[-1], :], asia_index.iloc[[-1], :]


def update_weather_index(run='00', model="ecmwf-eps"):
    weather_folder = f"{csv_path}\\weather\\"
    if os.path.exists(convert_path_to_linux(weather_folder + f"EU_{run}_{model}.csv")):
        data_eu = ts.read_csv(weather_folder + f'EU_{run}_{model}.csv', index_name='Unnamed: 0')
        data_us = ts.read_csv(weather_folder + f'US_{run}_{model}.csv', index_name='Unnamed: 0')
        data_asia = ts.read_csv(weather_folder + f'Asia_{run}_{model}.csv', index_name='Unnamed: 0')
        sdate = data_eu.index[-1]
        data_eu = data_eu.iloc[:-1, :]
        data_us = data_us.iloc[:-1, :]
        data_asia = data_asia.iloc[:-1, :]
    else:
        data_eu = pd.DataFrame()
        data_us = pd.DataFrame()
        data_asia = pd.DataFrame()
        sdate = dt.datetime(2022, 11, 1)
    dts = pd.date_range(sdate, today())
    for d in dts:
        eu1, us1, asia1 = get_weather_index(date=d, a=run, b=model)
        if len(eu1) > 0 and len(us1) > 0 and len(asia1) > 0:
            data_eu = pd.concat([data_eu, eu1], axis=0)
            data_us = pd.concat([data_us, us1], axis=0)
            data_asia = pd.concat([data_asia, asia1], axis=0)
    data_eu.to_csv(convert_path_to_linux(weather_folder + f'EU_{run}_{model}.csv'))
    data_us.to_csv(convert_path_to_linux(weather_folder + f'US_{run}_{model}.csv'))
    data_asia.to_csv(convert_path_to_linux(weather_folder + f'Asia_{run}_{model}.csv'))


def weather_index_table_chart_old(run='00'):
    sdate = dt.datetime(2023, 10, 1)
    weather_folder = f"{csv_path}\\weather\\"
    data_eu = ts.read_csv(weather_folder + f'EU_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_eu1 = ts.read_csv(weather_folder + f'EU_{run}_gfs-ens-mem.csv', index_name='Unnamed: 0')
    data_us = ts.read_csv(weather_folder + f'US_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_us1 = ts.read_csv(weather_folder + f'US_{run}_gfs-ens-mem.csv', index_name='Unnamed: 0')
    data_asia = ts.read_csv(weather_folder + f'Asia_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_asia1 = ts.read_csv(weather_folder + f'Asia_{run}_gfs-ens-mem.csv', index_name='Unnamed: 0')
    data_eu = data_eu.loc[data_eu.index >= sdate, :]
    data_eu1 = data_eu1.loc[data_eu1.index >= sdate, :]
    data_us = data_us.loc[data_us.index >= sdate, :]
    data_us1 = data_us1.loc[data_us1.index >= sdate, :]
    data_asia = data_asia.loc[data_asia.index >= sdate, :]
    data_asia1 = data_asia1.loc[data_asia1.index >= sdate, :]
    df_eu = pd.concat([data_eu['EU Index'], data_eu1['EU Index']], axis=1)
    df_eu.columns = ['EC', 'GFS']
    fig_eu = chart.line_chart(df=df_eu, title='Europe - EC and GFS weather index', tickformat=False)
    df_us = pd.concat([data_us['US Index'], data_us1['US Index']], axis=1)
    df_us.columns = ['EC', 'GFS']
    fig_us = chart.line_chart(df=df_us, title='US - EC and GFS weather index', tickformat=False)
    df_asia = pd.concat([data_asia['Asia Index'], data_asia1['Asia Index']], axis=1)
    df_asia.columns = ['EC', 'GFS']
    fig_asia = chart.line_chart(df=df_asia, title='Asia - EC and GFS weather index', tickformat=False)
    tb_eu = pd.DataFrame(0, index=['12H', '24H', '3D', '5D'], columns=['EU Index', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR'])
    tb_us = pd.DataFrame(0, index=['12H', '24H', '3D', '5D'], columns=['US Index', 'EPO', 'WPO', 'PNA', 'NAO'])
    tb_asia = pd.DataFrame(0, index=['12H', '24H', '3D', '5D'], columns=['Asia Index', 'EAWR', 'WPO', 'SCAND'])
    if run == '00':
        data_eu_ = ts.read_csv(weather_folder + 'EU_12_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_us_ = ts.read_csv(weather_folder + 'US_12_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_asia_ = ts.read_csv(weather_folder + 'Asia_12_ecmwf-eps.csv', index_name='Unnamed: 0')
        if data_eu.index[-1] == data_eu_.index[-1]:
            tb_eu.loc['12H', :] = data_eu.iloc[-1] - data_eu_.iloc[-2]
            tb_us.loc['12H', :] = data_us.iloc[-1] - data_us_.iloc[-2]
            tb_asia.loc['12H', :] = data_asia.iloc[-1] - data_asia_.iloc[-2]
        else:
            tb_eu.loc['12H', :] = data_eu.iloc[-1] - data_eu_.iloc[-1]
            tb_us.loc['12H', :] = data_us.iloc[-1] - data_us_.iloc[-1]
            tb_asia.loc['12H', :] = data_asia.iloc[-1] - data_asia_.iloc[-1]
    elif run == '12':
        data_eu_ = ts.read_csv(weather_folder + 'EU_00_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_us_ = ts.read_csv(weather_folder + 'US_00_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_asia_ = ts.read_csv(weather_folder + 'Asia_00_ecmwf-eps.csv', index_name='Unnamed: 0')
        tb_eu.loc['12H', :] = data_eu.iloc[-1] - data_eu_.iloc[-1]
        tb_us.loc['12H', :] = data_us.iloc[-1] - data_us_.iloc[-1]
        tb_asia.loc['12H', :] = data_asia.iloc[-1] - data_asia_.iloc[-1]
    tb_eu.loc['24H', :] = data_eu.iloc[-1] - data_eu.iloc[-2]
    tb_us.loc['24H', :] = data_us.iloc[-1] - data_us.iloc[-2]
    tb_asia.loc['24H', :] = data_asia.iloc[-1] - data_asia.iloc[-2]
    tb_eu.loc['3D', :] = data_eu.iloc[-1] - data_eu.iloc[-4]
    tb_us.loc['3D', :] = data_us.iloc[-1] - data_us.iloc[-4]
    tb_asia.loc['3D', :] = data_asia.iloc[-1] - data_asia.iloc[-4]
    tb_eu.loc['5D', :] = data_eu.iloc[-1] - data_eu.iloc[-6]
    tb_us.loc['5D', :] = data_us.iloc[-1] - data_us.iloc[-6]
    tb_asia.loc['5D', :] = data_asia.iloc[-1] - data_asia.iloc[-6]
    return tb_eu, tb_us, tb_asia, fig_eu, fig_us, fig_asia


def weather_index_table_chart(run='00'):
    sdate = dt.datetime(2024, 10, 1)
    weather_folder = f"{csv_path}\\weather\\"
    data_eu_ori = ts.read_csv(weather_folder + f'EU_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_eu1 = ts.read_csv(weather_folder + f'EU_{run}_gfs-ens-mem.csv', index_name='Unnamed: 0')
    data_us_ori = ts.read_csv(weather_folder + f'US_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_us1 = ts.read_csv(weather_folder + f'US_{run}_gfs-ens-mem.csv', index_name='Unnamed: 0')
    data_asia_ori = ts.read_csv(weather_folder + f'Asia_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_asia1 = ts.read_csv(weather_folder + f'Asia_{run}_gfs-ens-mem.csv', index_name='Unnamed: 0')
    data_eu_ori['EU Combo'] = data_eu_ori['NAO'] + data_eu_ori['AO']
    data_eu_ori = data_eu_ori[['EU Index', 'EU Combo', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR']]
    data_eu1['EU Combo'] = data_eu1['NAO'] + data_eu1['AO']
    data_eu1 = data_eu1[['EU Index', 'EU Combo', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR']]
    data_us_ori['US Combo'] = data_us_ori['EPO'] + data_us_ori['PNA']
    data_us_ori = data_us_ori[['US Index', 'US Combo', 'EPO', 'WPO', 'PNA', 'NAO']]
    data_us1['US Combo'] = data_us1['EPO'] + data_us1['PNA']
    data_us1 = data_us1[['US Index', 'US Combo', 'EPO', 'WPO', 'PNA', 'NAO']]
    data_eu = data_eu_ori.copy()
    data_us = data_us_ori.copy()
    data_asia = data_asia_ori.copy()
    data_eu_ori = data_eu_ori * -1
    data_us_ori = data_us_ori * -1
    data_asia_ori = data_asia_ori * -1
    data_eu = data_eu * -1
    data_us = data_us * -1
    data_asia = data_asia * -1
    data_eu1 = data_eu1 * -1
    data_us1 = data_us1 * -1
    data_asia1 = data_asia1 * -1
    eu_season = chart.seasonal_chart_new(
        df=data_eu_ori[["EU Index"]].reindex(pd.date_range(data_eu_ori.index.min(), data_eu_ori.index[-1])),
        title="Europe - seasonal weather index",
        start_month=10, start_day=1, end_month=4, end_day=30, over_year=True,
        height=500, width=750)
    eu_combo_season = chart.seasonal_chart_new(
        df=data_eu_ori[["EU Combo"]].reindex(pd.date_range(data_eu_ori.index.min(), data_eu_ori.index[-1])),
        title="Europe Combo - seasonal weather index",
        start_month=10, start_day=1, end_month=4, end_day=30, over_year=True,
        height=500, width=750)
    us_season = chart.seasonal_chart_new(
        df=data_us_ori[["US Index"]].reindex(pd.date_range(data_us_ori.index.min(), data_us_ori.index[-1])),
        title="US - seasonal weather index",
        start_month=10, start_day=1, end_month=4, end_day=30, over_year=True,
        height=500, width=750)
    us_combo_season = chart.seasonal_chart_new(
        df=data_us_ori[["US Combo"]].reindex(pd.date_range(data_us_ori.index.min(), data_us_ori.index[-1])),
        title="US Combo - seasonal weather index",
        start_month=10, start_day=1, end_month=4, end_day=30, over_year=True,
        height=500, width=750)
    asia_season = chart.seasonal_chart_new(
        df=data_asia_ori[["Asia Index"]].reindex(pd.date_range(data_asia_ori.index.min(), data_asia_ori.index[-1])),
        title="Asia - seasonal weather index",
        start_month=10, start_day=1, end_month=4, end_day=30, over_year=True,
        height=500, width=750)
    vol_eu = data_eu.loc[data_eu.index.month.isin([10, 11, 12, 1, 2, 3])].std()
    vol_us = data_us.loc[data_us.index.month.isin([10, 11, 12, 1, 2, 3])].std()
    vol_asia = data_asia.loc[data_asia.index.month.isin([10, 11, 12, 1, 2, 3])].std()
    data_eu = data_eu.loc[data_eu.index >= sdate, :]
    data_eu1 = data_eu1.loc[data_eu1.index >= sdate, :]
    data_us = data_us.loc[data_us.index >= sdate, :]
    data_us1 = data_us1.loc[data_us1.index >= sdate, :]
    data_asia = data_asia.loc[data_asia.index >= sdate, :]
    data_asia1 = data_asia1.loc[data_asia1.index >= sdate, :]
    df_eu = pd.concat([data_eu['EU Index'], data_eu1['EU Index'],
        pd.Series(vol_eu['EU Index'], index=data_eu.index),
        pd.Series(-vol_eu['EU Index'], index=data_eu.index)], axis=1)
    df_eu.columns = ['EC', 'GFS', 'EC +1sd', 'EC -1sd']
    fig_eu = chart.line_chart(df=df_eu, title='Europe - EC and GFS weather index', tickformat=False, height=500, width=750,
        highlight_dict={'EC +1sd': {'color': 'black', 'width': 1, 'dash': 'dash'},
                        'EC -1sd': {'color': 'black', 'width': 1, 'dash': 'dash'}})
    df_eu_combo = pd.concat([data_eu['EU Combo'], data_eu1['EU Combo'],
        pd.Series(vol_eu['EU Combo'], index=data_eu.index),
        pd.Series(-vol_eu['EU Combo'], index=data_eu.index)], axis=1)
    df_eu_combo.columns = ['EC', 'GFS', 'EC +1sd', 'EC -1sd']
    fig_eu_combo = chart.line_chart(df=df_eu_combo, title='Europe Combo - EC and GFS weather index', tickformat=False, height=500, width=750,
        highlight_dict={'EC +1sd': {'color': 'black', 'width': 1, 'dash': 'dash'},
                        'EC -1sd': {'color': 'black', 'width': 1, 'dash': 'dash'}})
    df_us = pd.concat([data_us['US Index'], data_us1['US Index'],
        pd.Series(vol_us['US Index'], index=data_us.index),
        pd.Series(-vol_us['US Index'], index=data_us.index)], axis=1)
    df_us.columns = ['EC', 'GFS', 'EC +1sd', 'EC -1sd']
    fig_us = chart.line_chart(df=df_us, title='US - EC and GFS weather index', tickformat=False, height=500, width=750,
        highlight_dict={'EC +1sd': {'color': 'black', 'width': 1, 'dash': 'dash'},
                        'EC -1sd': {'color': 'black', 'width': 1, 'dash': 'dash'}})
    df_us_combo = pd.concat([data_us['US Combo'], data_us1['US Combo'],
        pd.Series(vol_us['US Combo'], index=data_us.index),
        pd.Series(-vol_us['US Index'], index=data_us.index)], axis=1)
    df_us_combo.columns = ['EC', 'GFS', 'EC +1sd', 'EC -1sd']
    fig_us_combo = chart.line_chart(df=df_us_combo, title='US Combo - EC and GFS weather index', tickformat=False, height=500, width=750,
        highlight_dict={'EC +1sd': {'color': 'black', 'width': 1, 'dash': 'dash'},
                        'EC -1sd': {'color': 'black', 'width': 1, 'dash': 'dash'}})
    df_asia = pd.concat([data_asia['Asia Index'], data_asia1['Asia Index'],
        pd.Series(vol_asia['Asia Index'], index=data_asia.index),
        pd.Series(-vol_asia['Asia Index'], index=data_asia.index)], axis=1)
    df_asia.columns = ['EC', 'GFS', 'EC +1sd', 'EC -1sd']
    fig_asia = chart.line_chart(df=df_asia, title='Asia - EC and GFS weather index', tickformat=False, height=500, width=750,
        highlight_dict={'EC +1sd': {'color': 'black', 'width': 1, 'dash': 'dash'},
                        'EC -1sd': {'color': 'black', 'width': 1, 'dash': 'dash'}})
    tb_eu = pd.DataFrame(0, index=['12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['EU Index', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR'])
    tb_us = pd.DataFrame(0, index=['12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['US Index', 'EPO', 'WPO', 'PNA', 'NAO'])
    tb_asia = pd.DataFrame(0, index=['12H', '24H', '3D', '5D', 'FRI 12Z'], columns=['Asia Index', 'EAWR', 'WPO', 'SCAND'])
    if run == '00':
        data_eu_ = ts.read_csv(weather_folder + 'EU_12_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_eu_['EU Combo'] = data_eu_['NAO'] + data_eu_['AO']
        data_eu_ = data_eu_[['EU Index', 'EU Combo', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR']]
        data_us_ = ts.read_csv(weather_folder + 'US_12_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_us_['US Combo'] = data_us_['EPO'] + data_us_['PNA']
        data_us_ = data_us_[['US Index', 'US Combo', 'EPO', 'WPO', 'PNA', 'NAO']]
        data_asia_ = ts.read_csv(weather_folder + 'Asia_12_ecmwf-eps.csv', index_name='Unnamed: 0')
        if data_eu.index[-1] == data_eu_.index[-1]:
            tb_eu.loc['12H', :] = data_eu.iloc[-1] - data_eu_.iloc[-2]
            tb_us.loc['12H', :] = data_us.iloc[-1] - data_us_.iloc[-2]
            tb_asia.loc['12H', :] = data_asia.iloc[-1] - data_asia_.iloc[-2]
        else:
            tb_eu.loc['12H', :] = data_eu.iloc[-1] - data_eu_.iloc[-1]
            tb_us.loc['12H', :] = data_us.iloc[-1] - data_us_.iloc[-1]
            tb_asia.loc['12H', :] = data_asia.iloc[-1] - data_asia_.iloc[-1]
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        tb_eu.loc['FRI 12Z', :] = data_eu.iloc[-1] - data_eu_.loc[last_fri, :]
        tb_us.loc['FRI 12Z', :] = data_us.iloc[-1] - data_us_.loc[last_fri, :]
        tb_asia.loc['FRI 12Z', :] = data_asia.iloc[-1] - data_asia_.loc[last_fri, :]
    elif run == '12':
        data_eu_ = ts.read_csv(weather_folder + 'EU_00_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_eu_['EU Combo'] = data_eu_['NAO'] + data_eu_['AO']
        data_eu_ = data_eu_[['EU Index', 'EU Combo', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR']]
        data_us_ = ts.read_csv(weather_folder + 'US_00_ecmwf-eps.csv', index_name='Unnamed: 0')
        data_us_['US Combo'] = data_us_['EPO'] + data_us_['PNA']
        data_us_ = data_us_[['US Index', 'US Combo', 'EPO', 'WPO', 'PNA', 'NAO']]
        data_asia_ = ts.read_csv(weather_folder + 'Asia_00_ecmwf-eps.csv', index_name='Unnamed: 0')
        tb_eu.loc['12H', :] = data_eu.iloc[-1] - data_eu_.iloc[-1]
        tb_us.loc['12H', :] = data_us.iloc[-1] - data_us_.iloc[-1]
        tb_asia.loc['12H', :] = data_asia.iloc[-1] - data_asia_.iloc[-1]
        last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
        tb_eu.loc['FRI 12Z', :] = data_eu.iloc[-1] - data_eu.loc[last_fri, :]
        tb_us.loc['FRI 12Z', :] = data_us.iloc[-1] - data_us.loc[last_fri, :]
        tb_asia.loc['FRI 12Z', :] = data_asia.iloc[-1] - data_asia.loc[last_fri, :]
    tb_eu.loc['24H', :] = data_eu.iloc[-1] - data_eu.iloc[-2]
    tb_us.loc['24H', :] = data_us.iloc[-1] - data_us.iloc[-2]
    tb_asia.loc['24H', :] = data_asia.iloc[-1] - data_asia.iloc[-2]
    tb_eu.loc['3D', :] = data_eu.iloc[-1] - data_eu.iloc[-4]
    tb_us.loc['3D', :] = data_us.iloc[-1] - data_us.iloc[-4]
    tb_asia.loc['3D', :] = data_asia.iloc[-1] - data_asia.iloc[-4]
    tb_eu.loc['5D', :] = data_eu.iloc[-1] - data_eu.iloc[-6]
    tb_us.loc['5D', :] = data_us.iloc[-1] - data_us.iloc[-6]
    tb_asia.loc['5D', :] = data_asia.iloc[-1] - data_asia.iloc[-6]
    tb_eu.rename(columns={'SCAND': 'Inv SCAND'}, inplace=True)
    tb_us.rename(columns={'PNA': 'Inv PNA'}, inplace=True)
    tb_asia.rename(columns={'SCAND': 'Inv SCAND'}, inplace=True)
    return tb_eu, tb_us, tb_asia, fig_eu, fig_eu_combo, fig_us, fig_us_combo, fig_asia, eu_season, eu_combo_season, us_season, us_combo_season, asia_season


def _unreadable_argument(line):
    raise NotImplementedError(f"stormvista_ec12 photographed line {line}: clipped argument")


def send_table(run='00'):
    cdate = today()
    live_contract = bbg.live_contract(active="NGA Comdty", seq=0, roll="t5")
    us_cdd_chg, us_cdd_daily = us_national_tdd_chg(cdate, run=run, field='ew_cdd')
    us_hdd_chg, us_hdd_daily = us_national_tdd_chg(cdate, run=run, field='gw_hdd')
    us_tdd_chg = us_cdd_chg + us_hdd_chg
    us_tdd_daily = us_cdd_daily + us_hdd_daily
    sc_cdd_chg = us_regional_tdd_chg(cdate, region='South Central', run=run, field='ew_cdd')
    sc_hdd_chg = us_regional_tdd_chg(cdate, region='South Central', run=run, field='gw_hdd')
    sc_tdd_chg = sc_cdd_chg + sc_hdd_chg
    east_cdd_chg = us_regional_tdd_chg(cdate, region='East', run=run, field='ew_cdd')
    east_hdd_chg = us_regional_tdd_chg(cdate, region='East', run=run, field='gw_hdd')
    east_tdd_chg = east_cdd_chg + east_hdd_chg
    europe_cdd_chg = global_tdd_chg(cdate, region='europe', run=run, field='pw_cdd')
    europe_hdd_chg = global_tdd_chg(cdate, region='europe', run=run, field='pw_hdd')
    europe_tdd_chg = europe_cdd_chg + europe_hdd_chg
    ttf_cdd_chg = global_tdd_chg(cdate, region='ttf', run=run, field='pw_cdd')
    ttf_hdd_chg = global_tdd_chg(cdate, region='ttf', run=run, field='pw_hdd')
    ttf_tdd_chg = ttf_cdd_chg + ttf_hdd_chg
    uk_cdd_chg = global_tdd_chg(cdate, region='uk', run=run, field='pw_cdd')
    uk_hdd_chg = global_tdd_chg(cdate, region='uk', run=run, field='pw_hdd')
    uk_tdd_chg = uk_cdd_chg + uk_hdd_chg
    italy_cdd_chg = global_tdd_chg(cdate, region='italy', run=run, field='pw_cdd')
    italy_hdd_chg = global_tdd_chg(cdate, region='italy', run=run, field='pw_hdd')
    italy_tdd_chg = italy_cdd_chg + italy_hdd_chg
    asia_cdd_chg = global_tdd_chg(cdate, region='asia', run=run, field='pw_cdd')
    asia_hdd_chg = global_tdd_chg(cdate, region='asia', run=run, field='pw_hdd')
    asia_tdd_chg = asia_cdd_chg + asia_hdd_chg
    china_cdd_chg = global_tdd_chg(cdate, region='china', run=run, field='pw_cdd')
    china_hdd_chg = global_tdd_chg(cdate, region='china', run=run, field='pw_hdd')
    china_tdd_chg = china_cdd_chg + china_hdd_chg
    japan_cdd_chg = global_tdd_chg(cdate, region='japan', run=run, field='pw_cdd')
    japan_hdd_chg = global_tdd_chg(cdate, region='japan', run=run, field='pw_hdd')
    japan_tdd_chg = japan_cdd_chg + japan_hdd_chg
    skorea_cdd_chg = global_tdd_chg(cdate, region='skorea', run=run, field='pw_cdd')
    skorea_hdd_chg = global_tdd_chg(cdate, region='skorea', run=run, field='pw_hdd')
    skorea_tdd_chg = skorea_cdd_chg + skorea_hdd_chg

    if run == "00":
        release_time = today() + dt.timedelta(hours=7, minutes=45)
    elif run == "12":
        release_time = today() + dt.timedelta(hours=19, minutes=45)
    if today().weekday() not in [5, 6]:
        ng_intraday = bbg.bdib(live_contract["ticker"], today() - dt.timedelta(days=14), _unreadable_argument(862),
            interval=5)
        ng_cur = ng_intraday.loc[ng_intraday.index <= release_time, "close"].iloc[-1]
        ng_12h = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(hours=12), "close"].iloc[-1]
        ng_24h = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=1), "close"].iloc[-1]
        ng_3d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=3), "close"].iloc[-1]
        ng_5d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=5), "close"].iloc[-1]
        daily_p = bbg.bdh(live_contract["ticker"], ["PX_LAST"],
            today() - BDay(1) + relativedelta(weekday=FR(-1)) - BDay(2),
            today() - BDay(1) + relativedelta(weekday=FR(-1)))
        ng_fri = daily_p["PX_LAST"].iloc[-1]
        ng_chg = pd.DataFrame(
            [ng_cur / ng_12h - 1, ng_cur / ng_24h - 1, ng_cur / ng_3d - 1, ng_cur / ng_5d - 1, ng_cur / ng_fri - 1],
            index=["12H", "24H", "3D", "5D", "FRI 12Z"], columns=["NG Chg"])
    else:
        ng_chg = pd.DataFrame(np.nan, index=["12H", "24H", "3D", "5D", "FRI 12Z"], columns=["NG Chg"])

    if live_contract["m"] in ["X", "Z", "F", "G", "H", "J"]:
        ng_exp = us_hdd_chg * 0.0017
    elif live_contract["m"] in ["K", "M", "N", "Q", "U", "V"]:
        ng_exp = us_cdd_chg * 0.0008
    ng_exp.columns = ["NG Exp Chg"]

    live_contract_tzt = bbg.live_contract(active="TZTA Comdty", seq=0, roll="t3")
    tzt_intraday = bbg.bdib(live_contract_tzt["ticker"], today() - dt.timedelta(days=14), _unreadable_argument(895),
        interval=5)
    tzt_cur = tzt_intraday.loc[tzt_intraday.index <= release_time, "close"].iloc[-1]
    tzt_12h = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(hours=12), "close"].iloc[-1]
    tzt_24h = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=1), "close"].iloc[-1]
    tzt_3d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=3), "close"].iloc[-1]
    tzt_5d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=5), "close"].iloc[-1]
    daily_tzt = bbg.bdh(live_contract_tzt["ticker"], ["PX_LAST"],
        today() - BDay(1) + relativedelta(weekday=FR(-1)) - BDay(2),
        today() - BDay(1) + relativedelta(weekday=FR(-1)))
    tzt_fri = daily_tzt["PX_LAST"].iloc[-1]
    tzt_chg = pd.DataFrame(
        [tzt_cur / tzt_12h - 1, tzt_cur / tzt_24h - 1, tzt_cur / tzt_3d - 1, tzt_cur / tzt_5d - 1, tzt_cur / tzt_fri - 1],
        index=["12H", "24H", "3D", "5D", "FRI 12Z"], columns=["TZT Chg"])

    if live_contract_tzt["m"] in ["X", "Z", "F", "G", "H", "J"]:
        tzt_exp = ttf_hdd_chg * 0.001
    elif live_contract_tzt["m"] in ["K", "M", "N", "Q", "U", "V"]:
        tzt_exp = ttf_cdd_chg * 0.000
    tzt_exp.columns = ["TZT Exp Chg"]

    ng_convert_dict = {10: 0.3, 11: 0.6, 12: 1.4, 1: 1.7, 2: 1.6, 3: 0.8, 4: 0.6, 5: 0, 6: 0, 7: 0, 8: 0, 9: ...}
    us_hdd_bcf_factor = []
    for i in us_tdd_daily.index:
        if ng_convert_dict[i.month] is Ellipsis:
            raise NotImplementedError("stormvista_ec12 photographed line 922: September coefficient clipped")
        us_hdd_bcf_factor.append(ng_convert_dict[i.month])
    us_hdd_bcf = us_hdd_daily.mul(pd.Series(us_hdd_bcf_factor, index=us_tdd_daily.index), axis=0).sum(axis=0)
    us_tdd_bcf = us_tdd_daily.mul(pd.Series(us_hdd_bcf_factor, index=us_tdd_daily.index), axis=0).sum(axis=0)
    ttf_hdd_bcf = ttf_hdd_chg * 36 / 1000
    ttf_tdd_bcf = ttf_tdd_chg * 36 / 1000
    asia_hdd_bcf = asia_hdd_chg * 25 / 1000
    asia_tdd_bcf = asia_tdd_chg * 25 / 1000
    us_hdd_bcf = us_hdd_bcf.to_frame("ResCom (BCF)")
    us_tdd_bcf = us_tdd_bcf.to_frame("ResCom (BCF)")
    ttf_hdd_bcf.columns = ["LDZ (BCM)"]
    ttf_tdd_bcf.columns = ["LDZ (BCM)"]
    asia_hdd_bcf.columns = ["LDZ (BCM)"]
    asia_tdd_bcf.columns = ["LDZ (BCM)"]
    us_cdd = pd.concat([us_cdd_chg, sc_cdd_chg, east_cdd_chg, ng_chg, ng_exp], axis=1)
    us_cdd.index.name = 'US CDD'
    us_cdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\us_cdd_stormvista.csv"))
    us_hdd = pd.concat([us_hdd_chg, sc_hdd_chg, east_hdd_chg, ng_chg, ng_exp, us_hdd_bcf], axis=1)
    us_hdd.index.name = 'US HDD'
    us_hdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\us_hdd_stormvista.csv"))
    us_tdd = pd.concat([us_tdd_chg, sc_tdd_chg, east_tdd_chg, ng_chg, ng_exp, us_tdd_bcf], axis=1)
    us_tdd.index.name = 'US TDD'
    us_tdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\us_tdd_stormvista.csv"))
    eu_cdd = pd.concat([europe_cdd_chg, ttf_cdd_chg, uk_cdd_chg, italy_cdd_chg, tzt_chg, tzt_exp], axis=1)
    eu_cdd.index.name = 'EU CDD'
    eu_cdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\eu_cdd_stormvista.csv"))
    eu_hdd = pd.concat([europe_hdd_chg, ttf_hdd_chg, uk_hdd_chg, italy_hdd_chg, tzt_chg, tzt_exp, ttf_hdd_bcf], axis=1)
    eu_hdd.index.name = 'EU HDD'
    eu_hdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\eu_hdd_stormvista.csv"))
    eu_tdd = pd.concat([europe_tdd_chg, ttf_tdd_chg, uk_tdd_chg, italy_tdd_chg, tzt_chg, tzt_exp, ttf_tdd_bcf], axis=1)
    eu_tdd.index.name = 'EU TDD'
    eu_tdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\eu_tdd_stormvista.csv"))
    asia_cdd = pd.concat([asia_cdd_chg, china_cdd_chg, japan_cdd_chg, skorea_cdd_chg], axis=1)
    asia_cdd.index.name = 'Asia CDD'
    asia_cdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\asia_cdd_stormvista.csv"))
    asia_hdd = pd.concat([asia_hdd_chg, china_hdd_chg, japan_hdd_chg, skorea_hdd_chg, asia_hdd_bcf], axis=1)
    asia_hdd.index.name = 'Asia HDD'
    asia_hdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\asia_hdd_stormvista.csv"))
    asia_tdd = pd.concat([asia_tdd_chg, china_tdd_chg, japan_tdd_chg, skorea_tdd_chg, asia_tdd_bcf], axis=1)
    asia_tdd.index.name = 'Asia TDD'
    asia_tdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\asia_tdd_stormvista.csv"))

    figs = []
    def add_divergence(data, field1="NG Chg", field2="US National"):
        data["div"] = 0
        data.loc[(data[field1] > 0) & (data[field2] < 0), "div"] = 1
        data.loc[(data[field1] < 0) & (data[field2] > 0), "div"] = -1
        return data

    us_cdd = add_divergence(us_cdd, "NG Chg", "US National")
    us_hdd = add_divergence(us_hdd, "NG Chg", "US National")
    us_tdd = add_divergence(us_tdd, "NG Chg", "US National")
    eu_cdd = add_divergence(eu_cdd, "TZT Chg", "TTF")
    eu_hdd = add_divergence(eu_hdd, "TZT Chg", "TTF")
    eu_tdd = add_divergence(eu_tdd, "TZT Chg", "TTF")

    if live_contract['m'] in ['M', 'N', 'Q', 'U', 'V']:
        current_date_ = today()
        current_month_ = current_date_.month
        current_year_ = current_date_.year
        next_month_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).month
        next_year_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).year
        ticker1_hdd = 'CECEM ' + month_int2str[current_month_] + str(current_year_)[-2:] + ' Index'
        ticker = [ticker1_hdd]
        ticker2_hdd = 'CECEM ' + month_int2str[next_month_] + str(next_year_)[-2:] + ' Index'
        ticker.append(ticker2_hdd)
        bbg_tdd = bbg.bdh(ticker, ['PX_LAST'], sdate=today() - dt.timedelta(days=35), edate=today())
        bbg_tdd.columns = ticker
        bbg_tdd2 = (bbg_tdd[ticker2_hdd]).to_frame(month_int2str[next_month_] + str(next_year_)[-2:])
        bbg_tdd1 = (bbg_tdd[ticker1_hdd]).to_frame(month_int2str[current_month_] + str(current_year_)[-2:])
        us_cdd = us_cdd.reset_index()
        figs.append(table.html_format(
            df=us_cdd, precision=1,
            hide_cols=["div"],
            format_column={tuple(us_cdd.columns): {'width': '100px', 'text-align': 'center'},
                us_cdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                us_cdd.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        us_cdd_national_data = us_cdd_hdd_fcst_data(cycle=run, area='national', is_cdd=True)
        us_cdd_east_data = us_cdd_hdd_fcst_data(cycle=run, area='East', is_cdd=True)
        us_cdd_sc_data = us_cdd_hdd_fcst_data(cycle=run, area='South Central', is_cdd=True)
        us_cdd_national_chart = demand_forecast_chart(us_cdd_national_data, title='1-15 CDD forecasts charts for US National', type='cdd')
        us_cdd_east_chart = demand_forecast_chart(us_cdd_east_data, title='1-15 CDD forecasts charts for US East', type='cdd')
        us_cdd_sc_chart = demand_forecast_chart(us_cdd_sc_data, title='1-15 CDD forecasts charts for South Central', type='cdd')
        us_cdd_figs = [us_cdd_national_chart, us_cdd_sc_chart, us_cdd_east_chart]
        figs.extend(us_cdd_figs)
        eu_cdd = eu_cdd.reset_index()
        figs.append(table.html_format(
            df=eu_cdd, precision=1,
            hide_cols=["div"],
            format_column={tuple(eu_cdd.columns): {'width': '100px', 'text-align': 'center'},
                eu_cdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                eu_cdd.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        eu_cdd_data = cdd_fcst_asia_eu(area='europe', cycle=run)
        eu_cdd_chart = demand_forecast_chart(eu_cdd_data, title='1-15 CDD forecasts charts for Europe', type='cdd')
        figs.append(eu_cdd_chart)
        asia_cdd = asia_cdd.reset_index()
        figs.append(table.html_format(
            df=asia_cdd, precision=1,
            format_column={tuple(asia_cdd.columns): {'width': '100px', 'text-align': 'center'}}))
        asia_cdd_data = cdd_fcst_asia_eu(area='asia', cycle=run)
        asia_cdd_chart = demand_forecast_chart(asia_cdd_data, title='1-15 CDD forecasts charts for Asia', type='cdd')
        figs.append(asia_cdd_chart)
        subject = f"Weather - Global CDD, EC{run}z"
        head = "CDDs"

    elif live_contract['m'] in ['Z', 'F', 'G', 'H', 'J']:
        current_date_ = today()
        current_month_ = current_date_.month
        current_year_ = current_date_.year
        next_month_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).month
        next_year_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).year
        ticker1_hdd = 'CEHGM ' + month_int2str[current_month_] + str(current_year_)[-2:] + ' Index'
        ticker = [ticker1_hdd]
        ticker2_hdd = 'CEHGM ' + month_int2str[next_month_] + str(next_year_)[-2:] + ' Index'
        ticker.append(ticker2_hdd)
        bbg_tdd = bbg.bdh(ticker, ['PX_LAST'], sdate=today() - dt.timedelta(days=35), edate=today())
        bbg_tdd.columns = ticker
        bbg_tdd2 = (bbg_tdd[ticker2_hdd]).to_frame(month_int2str[next_month_] + str(next_year_)[-2:])
        bbg_tdd1 = (bbg_tdd[ticker1_hdd]).to_frame(month_int2str[current_month_] + str(current_year_)[-2:])
        us_hdd = us_hdd.reset_index()
        figs.append(table.html_format(
            df=us_hdd, precision=1,
            hide_cols=["div"],
            format_column={tuple(us_hdd.columns): {'width': '100px', 'text-align': 'center'},
                us_hdd.columns[-4]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                us_hdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        us_hdd_national_data = us_cdd_hdd_fcst_data(cycle=run, area='national', is_cdd=False)
        us_hdd_east_data = us_cdd_hdd_fcst_data(cycle=run, area='East', is_cdd=False)
        us_hdd_sc_data = us_cdd_hdd_fcst_data(cycle=run, area='South Central', is_cdd=False)
        us_hdd_national_chart = demand_forecast_chart(us_hdd_national_data, title='1-15 HDD forecasts charts for US National', type='hdd')
        us_hdd_east_chart = demand_forecast_chart(us_hdd_east_data, title='1-15 HDD forecasts charts for US East', type='hdd')
        us_hdd_sc_chart = demand_forecast_chart(us_hdd_sc_data, title='1-15 HDD forecasts charts for South Central', type='hdd')
        us_hdd_figs = [us_hdd_national_chart, us_hdd_sc_chart, us_hdd_east_chart]
        figs.extend(us_hdd_figs)
        eu_hdd = eu_hdd.reset_index()
        figs.append(table.html_format(
            df=eu_hdd, precision=1,
            hide_cols=["div"],
            format_column={tuple(eu_hdd.columns): {'width': '100px', 'text-align': 'center'},
                eu_hdd.columns[-4]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                eu_hdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        eu_hdd_data = hdd_fcst_asia_eu(area='europe', cycle=run)
        eu_hdd_chart = demand_forecast_chart(eu_hdd_data, title='1-15 HDD forecasts charts for Europe', type='hdd')
        figs.append(eu_hdd_chart)
        asia_hdd = asia_hdd.reset_index()
        figs.append(table.html_format(
            df=asia_hdd, precision=1,
            format_column={tuple(asia_hdd.columns): {'width': '100px', 'text-align': 'center'}}))
        asia_hdd_data = hdd_fcst_asia_eu(area='asia', cycle=run)
        asia_hdd_chart = demand_forecast_chart(asia_hdd_data, title='1-15 HDD forecasts charts for Asia', type='hdd')
        figs.append(asia_hdd_chart)
        subject = f"Weather - Global HDD, EC{run}z"
        head = "HDDs"

    else:
        us_tdd = us_tdd.reset_index()
        figs.append(table.html_format(
            df=us_tdd, precision=1,
            hide_cols=["div"],
            format_column={tuple(us_tdd.columns): {'width': '100px', 'text-align': 'center'},
                us_tdd.columns[-4]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                us_tdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        us_tdd_national_data = us_tdd_fcst_data(cycle=run, area='national')
        us_tdd_east_data = us_tdd_fcst_data(cycle=run, area='East')
        us_tdd_sc_data = us_tdd_fcst_data(cycle=run, area='South Central')
        us_tdd_national_chart = demand_forecast_chart(us_tdd_national_data, title='1-15 TDD forecasts charts for US National', type='tdd')
        us_tdd_east_chart = demand_forecast_chart(us_tdd_east_data, title='1-15 TDD forecasts charts for US East', type='tdd')
        us_tdd_sc_chart = demand_forecast_chart(us_tdd_sc_data, title='1-15 TDD forecasts charts for South Central', type='tdd')
        us_tdd_figs = [us_tdd_national_chart, us_tdd_sc_chart, us_tdd_east_chart]
        figs.extend(us_tdd_figs)
        eu_tdd = eu_tdd.reset_index()
        figs.append(table.html_format(
            df=eu_tdd, precision=1,
            hide_cols=["div"],
            format_column={tuple(eu_tdd.columns): {'width': '100px', 'text-align': 'center'},
                eu_tdd.columns[-4]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                eu_tdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}))
        eu_tdd_data = tdd_fcst_asia_eu(area='europe', cycle=run)
        eu_tdd_chart = demand_forecast_chart(eu_tdd_data, title='1-15 TDD forecasts charts for Europe', type='tdd')
        figs.append(eu_tdd_chart)
        asia_tdd = asia_tdd.reset_index()
        figs.append(table.html_format(
            df=asia_tdd, precision=1,
            format_column={tuple(asia_tdd.columns): {'width': '100px', 'text-align': 'center'}}))
        asia_tdd_data = tdd_fcst_asia_eu(area='asia', cycle=run)
        asia_tdd_chart = demand_forecast_chart(asia_tdd_data, title='1-15 TDD forecasts charts for Asia', type='tdd')
        figs.append(asia_tdd_chart)
        subject = f"Weather - Global TDD, EC{run}z"
        head = "TDDs"

    figs.append("<br>")
    figs.append("<p style='font-size: 24px; font-family:Calibri; font-weight:bold'>Weather Index</p>")
    figs.append("<p style='font-size: 16px; font-family:Calibri'>Positive means warm. Negative means cold.</p>")
    (tb_eu, tb_us, tb_asia, fig_eu, fig_eu_combo, fig_us, fig_us_combo, fig_asia,
     fig_eu_s, fig_eu_combo_s, fig_us_s, fig_us_combo_s, fig_asia_s) = weather_index_table_chart(run=run)
    tb_eu.index.name = 'EU'
    tb_eu.reset_index(inplace=True)
    tb_us.index.name = 'US'
    tb_us.reset_index(inplace=True)
    tb_asia.index.name = 'Asia'
    tb_asia.reset_index(inplace=True)
    figs.append(table.html_format(tb_us, precision=1, format_column={tuple(tb_us.columns): {'width': '100px', 'text-align': 'center'}}))
    figs.append(table.html_format(tb_eu, precision=1, format_column={tuple(tb_eu.columns): {'width': '100px', 'text-align': 'center'}}))
    figs.append(table.html_format(tb_asia, precision=1, format_column={tuple(tb_asia.columns): {'width': '100px', 'text-align': 'center'}}))
    figs.append([fig_us, fig_us_s])
    figs.append([fig_us_combo, fig_us_combo_s])
    figs.append([fig_eu, fig_eu_s])
    figs.append([fig_eu_combo, fig_eu_combo_s])
    figs.append([fig_asia, fig_asia_s])

    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html(
        [table.html_text(head, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\weather\\{file_name}.html", task_name=report_name)
    send_email(send_to=send_to, subject=subject, body=figs, html_path=f"{html_path}\\weather\\{file_name}.html")


def tdd_12z():
    run = False
    if not os.path.exists(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_12z_run.csv")):
        run = True
        run_state = pd.DataFrame()
    else:
        run_state = pd.read_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_12z_run.csv"))
        run_state.set_index('Unnamed: 0', inplace=True)
        run_state = run_state.iloc[:, 0]
        if today().strftime('%Y-%m-%d') not in run_state.values:
            run = True
    run_us = update_us_national(run='12')
    update_us_regional()
    run_global = update_global(run='12')
    if run and all(run_us) and all(run_global):
        update_weather_index(run='12', model="ecmwf-eps")
        update_weather_index(run='12', model="gfs-ens-mem")
        send_table(run='12')
        run_state_new = pd.Series(today().strftime('%Y-%m-%d'), index=[0])
        if len(run_state) > 0:
            run_state = pd.concat([run_state, run_state_new], ignore_index=True, axis=0)
        else:
            run_state = run_state_new
        run_state.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_12z_run.csv"))


if __name__ == "__main__":
    tdd_12z()
