import time
import urllib
from io import StringIO
import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import math
from dateutil.rrule import rrule, MINUTELY
from dateutil.relativedelta import relativedelta, FR
from pandas.tseries.offsets import BDay
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.time_series as ts
from ecm.cmds.cdr import today
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
report_name = "Weather - Global EC46"
file_name = "stormvista_ec46"  # without .py
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
        start_datetime=dt.datetime(2023, 7, 1, 21, 15),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()

apikey = sv.apikey
baseURL = 'https://api.stormvistawxmodels.com/v1/model-data/'

columns_index = ["24H", "3D", "5D", "FRI"]

def downloadFile(url):
    downloaded = False
    cnt = 0
    while not downloaded and cnt < 2:
        try:
            resp = urllib.request.urlopen(url)
        except:
            print('File not found...waiting for {url}'.format(url=url))
            time.sleep(1)
            cnt += 1
        else:
            print('Downloaded {url}'.format(url=url))
            downloaded = True
    try:
        return resp.read()
    except:
        return 0



def EC46_world(fileDate, area, cycle='00z'):
    fileName = 'ecmwf-weekly/{date}/{cycle}/wdd/{area}.csv?apikey={apikey}' \
        .format(date=fileDate.strftime("%Y%m%d"), \
                cycle=cycle, \
                area=area, \
                apikey=apikey)
    modelData = downloadFile('{baseURL}{fileName}'.format(baseURL=baseURL, fileName=fileName))
    if modelData == 0:
        df = pd.DataFrame()
    else:
        s = str(modelData, 'utf-8')
        data = StringIO(s)
        df = pd.read_csv(data)
    return df



def EC46_US(fileDate, cycle='00z'):
    fileName = 'ecmwf-weekly/{date}/{cycle}/wdd/national.csv?apikey={apikey}' \
        .format(date=fileDate.strftime("%Y%m%d"), \
                cycle=cycle, \
                apikey=apikey)
    modelData = downloadFile('{baseURL}{fileName}'.format(baseURL=baseURL, fileName=fileName))
    if modelData == 0:
        df = pd.DataFrame()
    else:
        s = str(modelData, 'utf-8')
        data = StringIO(s)
        df = pd.read_csv(data)
    return df


def EC46_US_regions(fileDate, type, region, cycle='00z'):
    fileName = 'ecmwf-weekly/{date}/{cylce}/wdd/{type}_reg{region}.csv?apikey={apikey}' \
        .format(date=fileDate.strftime("%Y%m%d"), \
                cylce=cycle, \
                type=type, \
                region=region, \
                apikey=apikey)
    modelData = downloadFile('{baseURL}{fileName}'.format(baseURL=baseURL, fileName=fileName))
    if modelData == 0:
        df = pd.DataFrame()
    else:
        s = str(modelData, 'utf-8')
        data = StringIO(s)
        df = pd.read_csv(data)
    return df


def update_us_national():
    has_latest_data = False
    max_date = sql.read_sql(
        f"Select MAX(As_of_date) from CWG_StormVista_US_National_EC46")
    if max_date.iloc[0, 0] is not None:
        sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
    else:
        sdate = dt.datetime(2023, 11, 1)
    edate = today()
    if sdate <= edate:
        dts = pd.date_range(sdate, edate)
        for i in dts:
            raw = EC46_US(i)
            if len(raw) > 0:
                raw['Date'] = pd.to_datetime(raw['Date'])
                data = pd.DataFrame()
                for col in raw.columns[1:]:
                    data_ = raw[['Date', col]]
                    data_.columns = ['Dates', 'Value']
                    data_.loc[:, 'Field'] = col.lower()
                    data = pd.concat([data, data_], ignore_index=True, axis=0)
                data['As_of_date'] = i
                sql.to_sql(data, 'CWG_StormVista_US_National_EC46', index=False)
                if i == today():
                    has_latest_data = True
    return has_latest_data


def update_us_regional():
    fields = ['ew_cdd', 'gw_hdd', 'pw_cdd']
    for idx, field in enumerate(fields):
        max_date = sql.read_sql(
            f"Select MAX(As_of_date) from CWG_StormVista_US_Regional_EC46 where Field='{field}'")
        if max_date.iloc[0, 0] is not None:
            sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
        else:
            sdate = dt.datetime(2023, 11, 1)
        edate = today()
        if sdate <= edate:
            dts = pd.date_range(sdate, edate)
            for i in dts:
                raw = EC46_US_regions(i, type=field, region=5)
                if len(raw) > 0:
                    raw['Date'] = pd.to_datetime(raw['Date'])
                    data = pd.DataFrame()
                    for col in raw.columns[1:]:
                        data_ = raw[['Date', col]]
                        data_.columns = ['Dates', 'Value']
                        data_['Region'] = col
                        data = pd.concat([data, data_], ignore_index=True, axis=0)
                    data['Field'] = field
                    data['As_of_date'] = i
                    sql.to_sql(data, 'CWG_StormVista_US_Regional_EC46', index=False)


def update_global():
    fields = ['asia', 'europe', 'italy', 'uk', 'ttf', 'china', 'japan', 'skorea']
    has_latest_data = [False, False, False, False, False, False, False, False]
    for idx, field in enumerate(fields):
        max_date = sql.read_sql(
            f"Select MAX(As_of_date) from CWG_StormVista_Global_fcast_EC46 where Region='{field}'")
        if max_date.iloc[0, 0] is not None:
            sdate = pd.to_datetime(max_date.iloc[0].iloc[0]) + dt.timedelta(days=1)
        else:
            sdate = dt.datetime(2023, 11, 1)
        edate = today()
        if sdate <= edate:
            dts = pd.date_range(sdate, edate)
            for i in dts:
                raw = EC46_world(i, area=field)
                if len(raw) > 0:
                    raw['Date'] = pd.to_datetime(raw['Date'])
                    data = pd.DataFrame()
                    for col in raw.columns[1:]:
                        data_ = raw[['Date', col]]
                        data_.columns = ['Dates', 'Value']
                        data_['Field'] = col.lower()
                        data = pd.concat([data, data_], ignore_index=True, axis=0)
                    data['Region'] = field
                    data['As_of_date'] = i
                    sql.to_sql(data, 'CWG_StormVista_Global_fcast_EC46', index=False)
                    if i == today():
                        has_latest_data[idx] = True
    return has_latest_data


def _unreadable_empty_overlap():
    raise NotImplementedError("EC46 change calculation: photographed empty-overlap fallback is clipped")


def us_national_tdd_chg(cdate, field='ew_cdd'):
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_National_EC46 where Field='{field}' and "
         f"As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' and "
         f"As_of_date <= '{dt.datetime.strftime(cdate, '%Y-%m-%d')}' order by "
         f"As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[fcast['As_of_date'] == cdate]
    td.set_index('Dates', inplace=True)
    compare_dts = td.index[:]
    td = td.loc[compare_dts, :]
    daily_fcst = pd.DataFrame(0, index=td.index, columns=columns_index)

    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    common_dates_1d = td.index.intersection(yd.index)
    daily_fcst.loc[common_dates_1d, "24H"] = td.loc[common_dates_1d, "Value"] - yd.loc[common_dates_1d, "Value"]
    tdd_chg = (td.loc[common_dates_1d, 'Value'] - yd.loc[common_dates_1d, 'Value']).sum() if len(common_dates_1d) > 0 else _unreadable_empty_overlap()

    d2 = fcast[(fcast['As_of_date'] == ydate[-3])]
    d2.set_index('Dates', inplace=True)
    common_dates_2d = td.index.intersection(d2.index)
    tdd_chg_2d = (td.loc[common_dates_2d, 'Value'] - d2.loc[common_dates_2d, 'Value']).sum() if len(common_dates_2d) > 0 else _unreadable_empty_overlap()

    d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
    d3.set_index('Dates', inplace=True)
    common_dates_3d = td.index.intersection(d3.index)
    daily_fcst.loc[common_dates_3d, "3D"] = td.loc[common_dates_3d, "Value"] - d3.loc[common_dates_3d, "Value"]
    tdd_chg_3d = (td.loc[common_dates_3d, 'Value'] - d3.loc[common_dates_3d, 'Value']).sum() if len(common_dates_3d) > 0 else _unreadable_empty_overlap()

    d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
    d5.set_index('Dates', inplace=True)
    common_dates_5d = td.index.intersection(d5.index)
    daily_fcst.loc[common_dates_5d, "5D"] = td.loc[common_dates_5d, "Value"] - d5.loc[common_dates_5d, "Value"]
    tdd_chg_5d = (td.loc[common_dates_5d, 'Value'] - d5.loc[common_dates_5d, 'Value']).sum() if len(common_dates_5d) > 0 else _unreadable_empty_overlap()

    last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
    dfri = fcast[(fcast['As_of_date'] == last_fri)]
    dfri.set_index('Dates', inplace=True)
    common_dates_fri = td.index.intersection(dfri.index)
    daily_fcst.loc[common_dates_fri, "FRI"] = td.loc[common_dates_fri, "Value"] - dfri.loc[common_dates_fri, "Value"]
    tdd_chg_fri = (td.loc[common_dates_fri, 'Value'] - dfri.loc[common_dates_fri, 'Value']).sum() if len(common_dates_fri) > 0 else _unreadable_empty_overlap()
    tdd_chg_df = pd.DataFrame(np.nan, index=columns_index, columns=['US National'])
    tdd_chg_df.loc['24H', 'US National'] = tdd_chg
    tdd_chg_df.loc['3D', 'US National'] = tdd_chg_3d
    tdd_chg_df.loc['5D', 'US National'] = tdd_chg_5d
    tdd_chg_df.loc['FRI', 'US National'] = tdd_chg_fri
    if field[-3:] == 'cdd':
        tdd_chg_df.index.name = 'US CDD'
    elif field[-3:] == 'hdd':
        tdd_chg_df.index.name = 'US HDD'
    else:
        tdd_chg_df.index.name = 'US TDD'
    return tdd_chg_df, daily_fcst


def us_regional_tdd_chg(cdate, region='East', field='ew_cdd'):
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_US_Regional_EC46 where Field='{field}' and "
         f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' and "
         f"As_of_date <= '{dt.datetime.strftime(cdate, '%Y-%m-%d')}' "
         f"order by As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[fcast['As_of_date'] == cdate]
    td.set_index('Dates', inplace=True)
    compare_dts = td.index
    td = td.loc[compare_dts, :]

    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    common_dates_1d = td.index.intersection(yd.index)
    tdd_chg = (td.loc[common_dates_1d, 'Value'] - yd.loc[common_dates_1d, 'Value']).sum() if len(common_dates_1d) > 0 else _unreadable_empty_overlap()

    d2 = fcast[(fcast['As_of_date'] == ydate[-3])]
    d2.set_index('Dates', inplace=True)
    common_dates_2d = td.index.intersection(d2.index)
    tdd_chg_2d = (td.loc[common_dates_2d, 'Value'] - d2.loc[common_dates_2d, 'Value']).sum() if len(common_dates_2d) > 0 else _unreadable_empty_overlap()

    d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
    d3.set_index('Dates', inplace=True)
    common_dates_3d = td.index.intersection(d3.index)
    tdd_chg_3d = (td.loc[common_dates_3d, 'Value'] - d3.loc[common_dates_3d, 'Value']).sum() if len(common_dates_3d) > 0 else _unreadable_empty_overlap()

    d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
    d5.set_index('Dates', inplace=True)
    common_dates_5d = td.index.intersection(d5.index)
    tdd_chg_5d = (td.loc[common_dates_5d, 'Value'] - d5.loc[common_dates_5d, 'Value']).sum() if len(common_dates_5d) > 0 else _unreadable_empty_overlap()

    last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
    dfri = fcast[(fcast['As_of_date'] == last_fri)]
    dfri.set_index('Dates', inplace=True)
    common_dates_fri = td.index.intersection(dfri.index)
    tdd_chg_fri = (td.loc[common_dates_fri, 'Value'] - dfri.loc[common_dates_fri, 'Value']).sum() if len(common_dates_fri) > 0 else _unreadable_empty_overlap()
    tdd_chg_df = pd.DataFrame(np.nan, index=columns_index, columns=[region])
    tdd_chg_df.loc['24H', region] = tdd_chg
    tdd_chg_df.loc['3D', region] = tdd_chg_3d
    tdd_chg_df.loc['5D', region] = tdd_chg_5d
    tdd_chg_df.loc['FRI', region] = tdd_chg_fri
    if field[-3:] == 'cdd':
        tdd_chg_df.index.name = f'{region} CDD'
    elif field[-3:] == 'hdd':
        tdd_chg_df.index.name = f'{region} HDD'
    else:
        tdd_chg_df.index.name = f'{region} TDD'
    return tdd_chg_df


def global_tdd_chg(cdate, region='asia', field='pw_cdd'):
    fcast = sql.read_sql(
        (f"Select * from CWG_StormVista_Global_fcast_EC46 where Field='{field}' and "
         f"Region='{region}' and As_of_date > '{dt.datetime.strftime(cdate - dt.timedelta(days=14), '%Y-%m-%d')}' and "
         f"As_of_date <= '{dt.datetime.strftime(cdate, '%Y-%m-%d')}' "
         f"order by As_of_date, Dates"))
    fcast.Dates = pd.to_datetime(fcast.Dates)
    fcast.As_of_date = pd.to_datetime(fcast.As_of_date)
    ydate = np.sort(fcast['As_of_date'].unique())
    td = fcast[fcast['As_of_date'] == cdate]
    td.set_index('Dates', inplace=True)
    compare_dts = td.index
    td = td.loc[compare_dts, :]

    yd = fcast[(fcast['As_of_date'] == ydate[-2])]
    yd.set_index('Dates', inplace=True)
    common_dates_1d = td.index.intersection(yd.index)
    tdd_chg = (td.loc[common_dates_1d, 'Value'] - yd.loc[common_dates_1d, 'Value']).sum() if len(common_dates_1d) > 0 else _unreadable_empty_overlap()

    d3 = fcast[(fcast['As_of_date'] == ydate[-4])]
    d3.set_index('Dates', inplace=True)
    common_dates_3d = td.index.intersection(d3.index)
    tdd_chg_3d = (td.loc[common_dates_3d, 'Value'] - d3.loc[common_dates_3d, 'Value']).sum() if len(common_dates_3d) > 0 else _unreadable_empty_overlap()

    d5 = fcast[(fcast['As_of_date'] == ydate[-6])]
    d5.set_index('Dates', inplace=True)
    common_dates_5d = td.index.intersection(d5.index)
    tdd_chg_5d = (td.loc[common_dates_5d, 'Value'] - d5.loc[common_dates_5d, 'Value']).sum() if len(common_dates_5d) > 0 else _unreadable_empty_overlap()

    last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
    dfri = fcast[(fcast['As_of_date'] == last_fri)]
    dfri.set_index('Dates', inplace=True)
    common_dates_fri = td.index.intersection(dfri.index)
    tdd_chg_fri = (td.loc[common_dates_fri, 'Value'] - dfri.loc[common_dates_fri, 'Value']).sum() if len(common_dates_fri) > 0 else _unreadable_empty_overlap()
    tdd_chg_df = pd.DataFrame(np.nan, index=columns_index, columns=[region.upper()])
    tdd_chg_df.loc['24H', region.upper()] = tdd_chg
    tdd_chg_df.loc['3D', region.upper()] = tdd_chg_3d
    tdd_chg_df.loc['5D', region.upper()] = tdd_chg_5d
    tdd_chg_df.loc['FRI', region.upper()] = tdd_chg_fri
    if field[-3:] == 'cdd':
        tdd_chg_df.index.name = f'{region.upper()} CDD'
    elif field[-3:] == 'hdd':
        tdd_chg_df.index.name = f'{region.upper()} HDD'
    else:
        tdd_chg_df.index.name = f'{region.upper()} TDD'
    return tdd_chg_df


def _unreadable_argument(source_line):
    raise NotImplementedError(f"EC46 photographed argument/value clipped at source line {source_line}")


def send_table(run_date: dt.datetime = None, send=True):
    cdate = run_date or today()
    live_contract = bbg.live_contract(active="NGA Comdty", seq=0, roll="t5")
    us_cdd_chg, us_cdd_daily = us_national_tdd_chg(cdate, field='ew_cdd')
    us_hdd_chg, us_hdd_daily = us_national_tdd_chg(cdate, field='gw_hdd')
    us_tdd_chg = us_cdd_chg + us_hdd_chg
    us_tdd_daily = us_cdd_daily + us_hdd_daily
    sc_cdd_chg = us_regional_tdd_chg(cdate, region='South Central', field='ew_cdd')
    sc_hdd_chg = us_regional_tdd_chg(cdate, region='South Central', field='gw_hdd')
    sc_tdd_chg = sc_cdd_chg + sc_hdd_chg
    east_cdd_chg = us_regional_tdd_chg(cdate, region='East', field='ew_cdd')
    east_hdd_chg = us_regional_tdd_chg(cdate, region='East', field='gw_hdd')
    east_tdd_chg = east_cdd_chg + east_hdd_chg
    europe_cdd_chg = global_tdd_chg(cdate, region='europe', field='pw_cdd')
    europe_hdd_chg = global_tdd_chg(cdate, region='europe', field='pw_hdd')
    europe_tdd_chg = europe_cdd_chg + europe_hdd_chg
    ttf_cdd_chg = global_tdd_chg(cdate, region='ttf', field='pw_cdd')
    ttf_hdd_chg = global_tdd_chg(cdate, region='ttf', field='pw_hdd')
    ttf_tdd_chg = ttf_cdd_chg + ttf_hdd_chg
    uk_cdd_chg = global_tdd_chg(cdate, region='uk', field='pw_cdd')
    uk_hdd_chg = global_tdd_chg(cdate, region='uk', field='pw_hdd')
    uk_tdd_chg = uk_cdd_chg + uk_hdd_chg
    italy_cdd_chg = global_tdd_chg(cdate, region='italy', field='pw_cdd')
    italy_hdd_chg = global_tdd_chg(cdate, region='italy', field='pw_hdd')
    italy_tdd_chg = italy_cdd_chg + italy_hdd_chg
    asia_cdd_chg = global_tdd_chg(cdate, region='asia', field='pw_cdd')
    asia_hdd_chg = global_tdd_chg(cdate, region='asia', field='pw_hdd')
    asia_tdd_chg = asia_cdd_chg + asia_hdd_chg
    china_cdd_chg = global_tdd_chg(cdate, region='china', field='pw_cdd')
    china_hdd_chg = global_tdd_chg(cdate, region='china', field='pw_hdd')
    china_tdd_chg = china_cdd_chg + china_hdd_chg
    japan_cdd_chg = global_tdd_chg(cdate, region='japan', field='pw_cdd')
    japan_hdd_chg = global_tdd_chg(cdate, region='japan', field='pw_hdd')
    japan_tdd_chg = japan_cdd_chg + japan_hdd_chg
    skorea_cdd_chg = global_tdd_chg(cdate, region='skorea', field='pw_cdd')
    skorea_hdd_chg = global_tdd_chg(cdate, region='skorea', field='pw_hdd')
    skorea_tdd_chg = skorea_cdd_chg + skorea_hdd_chg

    release_time = today() + dt.timedelta(hours=19, minutes=30)
    if today().weekday() not in [5, 6]:
        ng_intraday = bbg.bdib(live_contract["ticker"], today() - dt.timedelta(days=14), _unreadable_argument(451),
                               interval=5)
        ng_cur = ng_intraday.loc[ng_intraday.index <= release_time, "close"].iloc[-1]
        ng_1d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=1), "close"].iloc[-1]
        ng_3d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=3), "close"].iloc[-1]
        ng_5d = ng_intraday.loc[ng_intraday.index <= release_time - dt.timedelta(days=5), "close"].iloc[-1]
        daily_p = bbg.bdh(live_contract["ticker"], ["PX_LAST"], today() - BDay(1) + relativedelta(weekday=FR(-1)),
                          today() - BDay(1) + relativedelta(weekday=FR(-1)))
        ng_fri = daily_p["PX_LAST"].iloc[-1]
        ng_chg = pd.DataFrame(
            [ng_cur / ng_1d - 1, ng_cur / ng_3d - 1, ng_cur / ng_5d - 1, ng_cur/ng_fri-1],
            index=columns_index,
            columns=["NG Chg"]
        )
    else:
        ng_chg = pd.DataFrame(
            np.nan,
            index=columns_index,
            columns=["NG Chg"]
        )

    live_contract_tzt = bbg.live_contract(active="TZTA Comdty", seq=0, roll="t3")
    tzt_intraday = bbg.bdib(live_contract_tzt["ticker"], today() - dt.timedelta(days=14), _unreadable_argument(472),
                            interval=5)
    tzt_cur = tzt_intraday.loc[tzt_intraday.index <= release_time, "close"].iloc[-1]
    tzt_1d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=1), "close"].iloc[-1]
    tzt_3d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=3), "close"].iloc[-1]
    tzt_5d = tzt_intraday.loc[tzt_intraday.index <= release_time - dt.timedelta(days=5), "close"].iloc[-1]
    daily_tzt = bbg.bdh(live_contract_tzt["ticker"], ["PX_LAST"], today() - BDay(1) + relativedelta(weekday=FR(-1)),
                        today() - BDay(1) + relativedelta(weekday=FR(-1)))
    tzt_fri = daily_tzt["PX_LAST"].iloc[-1]
    tzt_chg = pd.DataFrame(
        [tzt_cur / tzt_1d - 1, tzt_cur / tzt_3d - 1, tzt_cur / tzt_5d - 1, tzt_cur / tzt_fri - 1],
        index=columns_index,
        columns=["TZT Chg"]
    )

    ng_convert_dict = {10: 0.3, 11: 0.6, 12: 1.4, 1: 1.7, 2: 1.6, 3: 0.8, 4: 0.6, 5: 0, 6: 0, 7: 0, 8: 0, 9: ...}
    us_hdd_bcf_factor = []
    for i in us_tdd_daily.index:
        if ng_convert_dict[i.month] is Ellipsis:
            _unreadable_argument(488)
        us_hdd_bcf_factor.append(ng_convert_dict[i.month])
    us_hdd_bcf = us_hdd_daily.mul(pd.Series(us_hdd_bcf_factor, index=us_hdd_daily.index), axis=0).sum(axis=0)
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

    us_cdd = pd.concat([us_cdd_chg, sc_cdd_chg, east_cdd_chg, ng_chg], axis=1)
    us_cdd.index.name = "US CDD"
    us_cdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\us_cdd_stormvista_ec46.csv"))
    us_hdd = pd.concat([us_hdd_chg, sc_hdd_chg, east_hdd_chg, ng_chg, us_hdd_bcf], axis=1)
    us_hdd.index.name = "US HDD"
    us_hdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\us_hdd_stormvista_ec46.csv"))
    us_tdd = pd.concat([us_tdd_chg, sc_tdd_chg, east_tdd_chg, ng_chg, us_tdd_bcf], axis=1)
    us_tdd.index.name = "US TDD"
    us_tdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\us_tdd_stormvista_ec46.csv"))

    eu_cdd = pd.concat([europe_cdd_chg, ttf_cdd_chg, uk_cdd_chg, italy_cdd_chg, tzt_chg], axis=1)
    eu_cdd.index.name = "EU CDD"
    eu_cdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\eu_cdd_stormvista_ec46.csv"))
    eu_hdd = pd.concat([europe_hdd_chg, ttf_hdd_chg, uk_hdd_chg, italy_hdd_chg, tzt_chg, ttf_hdd_bcf], axis=1)
    eu_hdd.index.name = "EU HDD"
    eu_hdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\eu_hdd_stormvista_ec46.csv"))
    eu_tdd = pd.concat([europe_tdd_chg, ttf_tdd_chg, uk_tdd_chg, italy_tdd_chg, tzt_chg, ttf_tdd_bcf], axis=1)
    eu_tdd.index.name = "EU TDD"
    eu_tdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\eu_tdd_stormvista_ec46.csv"))

    asia_cdd = pd.concat([asia_cdd_chg, china_cdd_chg, japan_cdd_chg, skorea_cdd_chg], axis=1)
    asia_cdd.index.name = "Asia CDD"
    asia_cdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\asia_cdd_stormvista_ec46.csv"))
    asia_hdd = pd.concat([asia_hdd_chg, china_hdd_chg, japan_hdd_chg, skorea_hdd_chg, asia_hdd_bcf], axis=1)
    asia_hdd.index.name = "Asia HDD"
    asia_hdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\asia_hdd_stormvista_ec46.csv"))
    asia_tdd = pd.concat([asia_tdd_chg, china_tdd_chg, japan_tdd_chg, skorea_tdd_chg, asia_tdd_bcf], axis=1)
    asia_tdd.index.name = "Asia TDD"
    asia_tdd.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\asia_tdd_stormvista_ec46.csv"))

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

    figs = []
    figs.append("<p style='font-size: 20px; font-family:Calibri; font-weight:bold'>EC46: 1-45d</p>")
    if live_contract['m'] in ['M', 'N', 'Q', 'U', 'V']:
        us_cdd = us_cdd.reset_index()
        figs.append(table.html_format(
            df=us_cdd,
            precision=1,
            hide_cols=["div"],
            format_column={tuple(us_cdd.columns): {'width': '100px', 'text-align': 'center'},
                           us_cdd.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}',
                                                'highlight': ['NG Chg', 'div']}}
        ))
        us_cdd_national_data = us_cdd_hdd_fcst_data(cycle=None, area='national', is_cdd=True, model="EC46")
        us_cdd_east_data = us_cdd_hdd_fcst_data(cycle=None, area='East', is_cdd=True, model="EC46")
        us_cdd_sc_data = us_cdd_hdd_fcst_data(cycle=None, area='South Central', is_cdd=True, model="EC46")
        us_cdd_national_chart = demand_forecast_chart(us_cdd_national_data, title='1-45d CDD forecasts charts for US National', type='cdd')
        us_cdd_east_chart = demand_forecast_chart(us_cdd_east_data, title='1-45d CDD forecasts charts for US East', type='cdd')
        us_cdd_sc_chart = demand_forecast_chart(us_cdd_sc_data, title='1-45d CDD forecasts charts for South Central', type='cdd')
        us_cdd_figs = [us_cdd_national_chart, us_cdd_sc_chart, us_cdd_east_chart]
        figs.extend(us_cdd_figs)
        eu_cdd = eu_cdd.reset_index()
        figs.append(table.html_format(
            df=eu_cdd,
            precision=1,
            hide_cols=["div"],
            format_column={tuple(eu_cdd.columns): {'width': '100px', 'text-align': 'center'},
                           eu_cdd.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}',
                                                'highlight': ['TZT Chg', 'div']}}
        ))
        eu_cdd_data = cdd_fcst_asia_eu(area='europe', cycle=None, model="EC46")
        eu_cdd_chart = demand_forecast_chart(eu_cdd_data, title='1-45d CDD forecasts charts for Europe', type='cdd')
        figs.append(eu_cdd_chart)
        asia_cdd = asia_cdd.reset_index()
        figs.append(table.html_format(
            df=asia_cdd,
            precision=1,
            format_column={tuple(asia_cdd.columns): {'width': '100px', 'text-align': 'center'}}
        ))
        asia_cdd_data = cdd_fcst_asia_eu(area='asia', cycle=None, model="EC46")
        asia_cdd_chart = demand_forecast_chart(asia_cdd_data, title='1-45d CDD forecasts charts for Asia', type='cdd')
        figs.append(asia_cdd_chart)
        china_cdd_data = cdd_fcst_asia_eu(area='china', cycle=None, model="EC46")
        china_cdd_chart = demand_forecast_chart(china_cdd_data, title='1-45d CDD forecasts charts for China', type='cdd')
        figs.append(china_cdd_chart)
        japan_cdd_data = cdd_fcst_asia_eu(area='japan', cycle=None, model="EC46")
        japan_cdd_chart = demand_forecast_chart(japan_cdd_data, title='1-45d CDD forecasts charts for Japan', type='cdd')
        figs.append(japan_cdd_chart)
        skorea_cdd_data = cdd_fcst_asia_eu(area='skorea', cycle=None, model="EC46")
        skorea_cdd_chart = demand_forecast_chart(skorea_cdd_data, title='1-45d CDD forecasts charts for Skorea', type='cdd')
        figs.append(skorea_cdd_chart)
        subject = f"Weather - Global CDDs, Euro Weeklies for {cdate.strftime('%Y-%m-%d')}"
        head = "CDDs"
    elif live_contract['m'] in ['Z', 'F', 'G', 'H', 'J']:
        us_hdd = us_hdd.reset_index()
        figs.append(table.html_format(
            df=us_hdd,
            precision=1,
            hide_cols=["div"],
            format_column={tuple(us_hdd.columns): {'width': '100px', 'text-align': 'center'},
                           us_hdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}',
                                                'highlight': ['NG Chg', 'div']}}
        ))
        us_hdd_national_data = us_cdd_hdd_fcst_data(cycle=None, area='national', is_cdd=False, model="EC46")
        us_hdd_east_data = us_cdd_hdd_fcst_data(cycle=None, area='East', is_cdd=False, model="EC46")
        us_hdd_sc_data = us_cdd_hdd_fcst_data(cycle=None, area='South Central', is_cdd=False, model="EC46")
        us_hdd_national_chart = demand_forecast_chart(us_hdd_national_data, title='1-45d HDD forecasts charts for US National', type='hdd')
        us_hdd_east_chart = demand_forecast_chart(us_hdd_east_data, title='1-45d HDD forecasts charts for US East', type='hdd')
        us_hdd_sc_chart = demand_forecast_chart(us_hdd_sc_data, title='1-45d HDD forecasts charts for South Central', type='hdd')
        us_hdd_figs = [us_hdd_national_chart, us_hdd_sc_chart, us_hdd_east_chart]
        figs.extend(us_hdd_figs)
        eu_hdd = eu_hdd.reset_index()
        figs.append(table.html_format(
            df=eu_hdd,
            precision=1,
            hide_cols=["div"],
            format_column={tuple(eu_hdd.columns): {'width': '100px', 'text-align': 'center'},
                           eu_hdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}',
                                                'highlight': ['TZT Chg', 'div']}}
        ))
        eu_hdd_data = hdd_fcst_asia_eu(area='europe', cycle=None, model="EC46")
        eu_hdd_chart = demand_forecast_chart(eu_hdd_data, title='1-45d HDD forecasts charts for Europe', type='hdd')
        figs.append(eu_hdd_chart)
        asia_hdd = asia_hdd.reset_index()
        figs.append(table.html_format(
            df=asia_hdd,
            precision=1,
            format_column={tuple(asia_hdd.columns): {'width': '100px', 'text-align': 'center'}}
        ))
        asia_hdd_data = hdd_fcst_asia_eu(area='asia', cycle=None, model="EC46")
        asia_hdd_chart = demand_forecast_chart(asia_hdd_data, title='1-45d HDD forecasts charts for Asia', type='hdd')
        figs.append(asia_hdd_chart)
        china_hdd_data = hdd_fcst_asia_eu(area='china', cycle=None, model="EC46")
        china_hdd_chart = demand_forecast_chart(china_hdd_data, title='1-45d HDD forecasts charts for China', type='hdd')
        figs.append(china_hdd_chart)
        japan_hdd_data = hdd_fcst_asia_eu(area='japan', cycle=None, model="EC46")
        japan_hdd_chart = demand_forecast_chart(japan_hdd_data, title='1-45d HDD forecasts charts for Japan', type='hdd')
        figs.append(japan_hdd_chart)
        skorea_hdd_data = hdd_fcst_asia_eu(area='skorea', cycle=None, model="EC46")
        skorea_hdd_chart = demand_forecast_chart(skorea_hdd_data, title='1-45d HDD forecasts charts for Skorea', type='hdd')
        figs.append(skorea_hdd_chart)
        subject = f"Weather - Global HDD, Euro Weeklies for {cdate.strftime('%Y-%m-%d')}"
        head = "HDDs"
    else:
        us_tdd = us_tdd.reset_index()
        figs.append(table.html_format(
            df=us_tdd,
            precision=1,
            hide_cols=["div"],
            format_column={tuple(us_tdd.columns): {'width': '100px', 'text-align': 'center'},
                           us_tdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}',
                                                'highlight': ['NG Chg', 'div']}}
        ))
        us_tdd_national_data = us_tdd_fcst_data(cycle=None, area='national', model="EC46")
        us_tdd_east_data = us_tdd_fcst_data(cycle=None, area='East', model="EC46")
        us_tdd_sc_data = us_tdd_fcst_data(cycle=None, area='South Central', model="EC46")
        us_tdd_national_chart = demand_forecast_chart(us_tdd_national_data, title='1-45d TDD forecasts charts for US National', type='tdd')
        us_tdd_east_chart = demand_forecast_chart(us_tdd_east_data, title='1-45d TDD forecasts charts for US East', type='tdd')
        us_tdd_sc_chart = demand_forecast_chart(us_tdd_sc_data, title='1-45d TDD forecasts charts for South Central', type='tdd')
        us_tdd_figs = [us_tdd_national_chart, us_tdd_sc_chart, us_tdd_east_chart]
        figs.extend(us_tdd_figs)
        eu_tdd = eu_tdd.reset_index()
        figs.append(table.html_format(
            df=eu_tdd,
            precision=1,
            hide_cols=["div"],
            format_column={tuple(eu_tdd.columns): {'width': '100px', 'text-align': 'center'},
                           eu_tdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}',
                                                'highlight': ['TZT Chg', 'div']}}
        ))
        eu_tdd_data = tdd_fcst_asia_eu(area='europe', cycle=None, model="EC46")
        eu_tdd_chart = demand_forecast_chart(eu_tdd_data, title='1-45d TDD forecasts charts for Europe', type='tdd')
        figs.append(eu_tdd_chart)
        asia_tdd = asia_tdd.reset_index()
        figs.append(table.html_format(
            df=asia_tdd,
            precision=1,
            format_column={tuple(asia_tdd.columns): {'width': '100px', 'text-align': 'center'}}
        ))
        asia_tdd_data = tdd_fcst_asia_eu(area='asia', cycle=None, model="EC46")
        asia_tdd_chart = demand_forecast_chart(asia_tdd_data, title='1-45d TDD forecasts charts for Asia', type='tdd')
        china_tdd_data = tdd_fcst_asia_eu(area='china', cycle=None, model="EC46")
        china_tdd_chart = demand_forecast_chart(china_tdd_data, title='1-45d TDD forecasts charts for China', type='tdd')
        japan_tdd_data = tdd_fcst_asia_eu(area='japan', cycle=None, model="EC46")
        japan_tdd_chart = demand_forecast_chart(japan_tdd_data, title='1-45d TDD forecasts charts for Japan', type='tdd')
        skorea_tdd_data = tdd_fcst_asia_eu(area='skorea', cycle=None, model="EC46")
        skorea_tdd_chart = demand_forecast_chart(skorea_tdd_data, title='1-45d TDD forecasts charts for Skorea', type='tdd')
        figs.append(asia_tdd_chart)
        figs.append(china_tdd_chart)
        figs.append(japan_tdd_chart)
        figs.append(skorea_tdd_chart)
        subject = f"Weather - Global TDD, Euro Weeklies for {cdate.strftime('%Y-%m-%d')}"
        head = "TDDs"

    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(head, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\weather\\{file_name}.html", task_name=report_name)
    send_email(send_to=send_to, subject=subject, body=figs, html_path=f"{html_path}\\weather\\{file_name}.html")


def tdd_ec46():
    run = False
    if not os.path.exists(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_46_run.csv")):
        run = True
        run_state = pd.DataFrame()
    else:
        run_state = pd.read_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_46_run.csv"))
        run_state.set_index("Unnamed: 0", inplace=True)
        run_state = run_state.iloc[:, 0]
        if today().strftime('%Y-%m-%d') not in run_state.values:
            run = True
    run_us = update_us_national()
    update_us_regional()
    run_global = update_global()
    if run and run_us and all(run_global):
        send_table()
        run_state_new = pd.Series(today().strftime('%Y-%m-%d'), index=[0])
        if len(run_state) > 0:
            run_state = pd.concat([run_state, run_state_new], ignore_index=True, axis=0)
        else:
            run_state = run_state_new
        run_state.to_csv(convert_path_to_linux(f"{output_path}\\csvs\\weather\\EC_46_run.csv"))


if __name__ == "__main__":
    tdd_ec46()

