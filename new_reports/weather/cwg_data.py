import pandas as pd
import datetime as dt
import sys
from dateutil.relativedelta import relativedelta
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today
from ecm.cmds.config import root_path
from io import StringIO
import requests
from loguru import logger as log
import time
import urllib3
import os  # TRANSCRIPTION: credential environment lookup.

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

report_name = "CWG data"
file_name = "cwg_data"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
go_back = 10


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
        start_datetime=dt.datetime(2023, 7, 1, 11, 5),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=300),
        repetition_duration=dt.timedelta(hours=6),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def cwg_url(endpoint):
    return f"https://api.commoditywx.com/v1/{endpoint}?apikey={os.environ['CWG_API_KEY']}"


def historical_actuals_us():
    sdate = dt.datetime(2000, 1, 1)
    reg_list = ["national", "5region", "iso"]
    for i in reg_list:
        first = sql.read_sql(f"Select MIN(AS_OF_DATE) from CWG_US_{i}").iloc[0, 0]
        if first is not None:
            edate = pd.to_datetime(first) - dt.timedelta(1)
        else:
            if i == "national":
                edate = dt.datetime(2010, 5, 10) - dt.timedelta(1)
            elif i == "5region":
                edate = dt.datetime(2015, 11, 23) - dt.timedelta(1)
            elif i == "iso":
                edate = dt.datetime(2020, 6, 4) - dt.timedelta(1)
        if edate > dt.datetime(2000, 1, 1):
            dts = pd.date_range(sdate, edate)
            all_data = pd.DataFrame()
            for val_date in dts:
                print(val_date)
                req = requests.get(cwg_url(f"northamerica_{i}_wdd_observations_{val_date.strftime('%Y%m%d')}.csv"),
                                   verify=False)
                if req.status_code == 200:
                    try:
                        data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                        if 'DATES' in data.columns:
                            data["AS_OF_DATE"] = val_date
                            all_data = pd.concat([all_data, data], axis=0, ignore_index=True)
                    except:
                        pass
            sql.to_sql(all_data, f"CWG_US_{i}", index=False)


def historical_actuals_global():
    sdate = dt.datetime(2000, 1, 1)
    reg_list = ["europe", "asia"]
    for i in reg_list:
        first = sql.read_sql(f"Select MIN(AS_OF_DATE) from CWG_{i} where REGION_NAME='{i}'").iloc[0, 0]
        if first is not None:
            edate = pd.to_datetime(first) - dt.timedelta(1)
        else:
            edate = dt.datetime(2018, 10, 24) - dt.timedelta(1)
        if edate > dt.datetime(2000, 1, 1):
            dts = pd.date_range(sdate, edate)
            all_data = pd.DataFrame()
            for val_date in dts:
                print(val_date)
                req = requests.get(cwg_url(f"{i}_base65F_wdd_observations_{val_date.strftime('%Y%m%d')}.csv"),
                                   verify=False)
                if req.status_code == 200:
                    try:
                        data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                        if 'DATES' in data.columns:
                            data["AS_OF_DATE"] = val_date
                            all_data = pd.concat([all_data, data], axis=0, ignore_index=True)
                    except:
                        pass
            sql.to_sql(all_data, f"CWG_{i}", index=False)

        first = sql.read_sql(f"Select MIN(AS_OF_DATE) from CWG_{i} where REGION_NAME<>'{i}' group by REGION_NAME")
        if len(first) > 1:
            edate = pd.to_datetime(first.iloc[:, 0]).max() - dt.timedelta(1)
        else:
            if i == "europe":
                edate = dt.datetime(2023, 1, 11) - dt.timedelta(1)
            elif i == "asia":
                raise NotImplementedError("Historical Asia regional fallback date is not photographed (source line 118)")
        if edate > dt.datetime(2000, 1, 1):
            dts = pd.date_range(sdate, edate)
            all_data = pd.DataFrame()
            for val_date in dts:
                print(val_date)
                req = requests.get(cwg_url(f"{i}_region_base65F_wdd_observations_{val_date.strftime('%Y%m%d')}.csv"),
                                   verify=False)
                if req.status_code == 200:
                    try:
                        data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                        if 'DATES' in data.columns:
                            data["AS_OF_DATE"] = val_date
                            all_data = pd.concat([all_data, data], axis=0, ignore_index=True)
                    except:
                        pass
            sql.to_sql(all_data, f"CWG_{i}", index=False)


def update_us():
    """
    req = requests.get(cwg_url(f"northamerica_national_wdd_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
    req = requests.get(cwg_url(f"northamerica_national_wdd_observations_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
    req = requests.get(cwg_url(f"northamerica_5region_wdd_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
    req = requests.get(cwg_url(f"northamerica_5region_wdd_observations_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
    req = requests.get(cwg_url(f"northamerica_iso_wdd_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
    req = requests.get(cwg_url(f"northamerica_iso_wdd_observations_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
    last = sql.read_sql(f"Select t1.* from CWG_US_{i} t1 INNER JOIN (Select MAX(AS_OF_DATE) as dt from CWG_US_{i}) t2
    on t1.AS_OF_DATE = t2.dt)")
    """
    reg_list = ["national", "5region", "iso"]
    for i in reg_list:
        last = sql.read_sql(f"Select MAX(AS_OF_DATE) from CWG_US_{i}").iloc[0, 0]
        if last is not None:
            sdate = pd.to_datetime(last) + dt.timedelta(1)
        else:
            if i == "national":
                sdate = dt.datetime(2010, 5, 10)
            elif i == "5region":
                sdate = dt.datetime(2015, 11, 23)
            elif i == "iso":
                sdate = dt.datetime(2020, 6, 4)
        if sdate <= today():
            dts = pd.date_range(sdate, today())
            for val_date in dts:
                print(val_date)
                req = requests.get(cwg_url(f"northamerica_{i}_wdd_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
                if req.status_code == 200:
                    try:
                        data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                        if 'DATES' in data.columns:
                            data = data[:-1]
                            data["AS_OF_DATE"] = val_date
                            sql.to_sql(data, f"CWG_US_{i}", index=False)
                    except:
                        pass


def update_global():
    reg_list = ["europe", "asia"]
    for i in reg_list:
        last = sql.read_sql(f"Select MAX(AS_OF_DATE) from CWG_{i} where REGION_NAME='{i}'").iloc[0, 0]
        if last is not None:
            sdate = pd.to_datetime(last) + dt.timedelta(1)
        else:
            sdate = dt.datetime(2018, 10, 24)

        if sdate <= today():
            dts = pd.date_range(sdate, today())
            for val_date in dts:
                print(val_date)
                req = requests.get(cwg_url(f"{i}_base65F_wdd_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
                if req.status_code == 200:
                    try:
                        data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                        if 'DATES' in data.columns:
                            data = data[:-1]
                            data["REGION_NAME"] = i.lower()
                            data["AS_OF_DATE"] = val_date
                            sql.to_sql(data, f"CWG_{i}", index=False)
                    except:
                        pass

        last = sql.read_sql(f"Select MAX(AS_OF_DATE) from CWG_{i} where REGION_NAME<>'{i}'").iloc[0, 0]
        if last is not None:
            sdate = pd.to_datetime(last) + dt.timedelta(1)
        else:
            if i == "europe":
                sdate = dt.datetime(2019, 12, 2)
            elif i == "asia":
                sdate = dt.datetime(2021, 12, 1)
        if sdate <= today():
            dts = pd.date_range(sdate, today())
            for val_date in dts:
                print(val_date)
                req = requests.get(cwg_url(f"{i}_region_base65F_wdd_{val_date.strftime('%Y%m%d')}.csv"), verify=False)
                if req.status_code == 200:
                    try:
                        data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                        if 'DATES' in data.columns:
                            data = data[:-1]
                            data["AS_OF_DATE"] = val_date
                            sql.to_sql(data, f"CWG_{i}", index=False)
                    except:
                        pass


def update_cwg_asia():
    """
    Actual Asia WDD
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_Actual_Asia] where REGION='Asia'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('asia_base65F_wdd_observations_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    }, inplace=True)
            datareq['REGION'] = 'Asia'
            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_Actual_Asia", index=False)
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual Asia region WDD
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_Actual_Asia] where REGION='China'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('asia_region_base65F_wdd_observations_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    'REGION_NAME': 'REGION',
                                    }, inplace=True)
            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_Actual_Asia", index=False)
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual Asia WDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_Fcast_Asia] where REGION='Asia'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        is_downloaded = False
        max_retries = 5
        retry_count = 0
        while not is_downloaded and retry_count < max_retries:
            try:
                fifday = requests.get(cwg_url('asia_base65F_wdd_{}.csv'.format(val_d)), verify=False)
                if fifday.status_code == 200:
                    is_downloaded = True
                elif fifday.status_code == 429:
                    retry_count += 1
                    log.warning(f"Rate limit exceeded when downloading asia_base65F_wdd_{val_d}.csv, retrying")
                    time.sleep(10)
                else:
                    log.error(f"Failed to download asia_base65F_wdd_{val_d}.csv, status code: {fifday.status_code}")
                    break
            except Exception as e:
                retry_count += 1
                log.error(f"Error downloading asia_base65F_wdd_{val_d}.csv: {e} (attempt {retry_count}/{max_retries})")
                time.sleep(10)
        if not is_downloaded:
            log.error(f"Failed to download asia_base65F_wdd_{val_d}.csv after {max_retries} attempts, skipping")
            continue
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day = fifteen_day.loc[fifteen_day['IS_FORECAST'] == True, :]
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    }, inplace=True)
            datareq['REGION'] = 'Asia'
            datareq['AS_OF_DATE'] = val_date
            if len(df2) == 0 or df2.loc[df2['AS_OF_DATE'] == (val_date)].empty:
                print(val_date)
                sql.to_sql(datareq, "CWG_Fcast_Asia", index=False)

    """
    Actual Asia region WDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_Fcast_Asia] where REGION='China'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('asia_region_base65F_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day = fifteen_day.loc[fifteen_day['IS_FORECAST'] == True, :]
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq['DATES'] = pd.to_datetime(datareq['DATES'])
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    'REGION_NAME': 'REGION',
                                    }, inplace=True)
            datareq['AS_OF_DATE'] = val_date
            if len(df2) == 0 or df2.loc[df2['AS_OF_DATE'] == (val_date)].empty:
                print(val_date)
                sql.to_sql(datareq, "CWG_Fcast_Asia", index=False)


def update_cwg_asia_add_india():
    """
    Actual Asia region WDD
    """
    total_df = pd.DataFrame()
    for i in range(0, 3600):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('asia_region_base65F_wdd_observations_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if 'DATES' in fifteen_day.columns and "India" in fifteen_day["REGION_NAME"].to_list():
            fifteen_day = fifteen_day.loc[fifteen_day["REGION_NAME"] == "India", :]
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    'REGION_NAME': 'REGION',
                                    }, inplace=True)
            datareq = datareq[['DATES', 'POP_HDD', 'POP_HDD_30Y', 'POP_HDD_10Y',
                               'LAST_Y_POP_HDD', 'POP_CDD', 'POP_CDD_30Y', 'POP_CDD_10Y',
                               'LAST_Y_POP_CDD', 'REGION']]
            total_df = pd.concat([total_df, datareq], axis=0)
    sql.to_sql(total_df, "CWG_Actual_Asia", index=False)

    """
    Actual Asia region WDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_Fcast_Asia] where REGION='China'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('asia_region_base65F_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day = fifteen_day.loc[fifteen_day['IS_FORECAST'] == True, :]
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq['DATES'] = pd.to_datetime(datareq['DATES'])
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    'REGION_NAME': 'REGION',
                                    }, inplace=True)
            datareq['AS_OF_DATE'] = val_date
            if len(df2) == 0 or df2.loc[df2['AS_OF_DATE'] == (val_date)].empty:
                print(val_date)
                sql.to_sql(datareq, "CWG_Fcast_Asia", index=False)


def update_cwg_europe():
    """
    Actual Europe WDD
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_Actual_Europe] where REGION='Europe'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('europe_base65F_wdd_observations_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            if fifteen_day["DATES"].iloc[-1] == "END.":
                datareq.drop(fifteen_day.index[-1], axis=0, inplace=True)
            datareq['DATES'] = pd.to_datetime(datareq['DATES'])
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    }, inplace=True)
            datareq['REGION'] = 'Europe'
            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_Actual_Europe", index=False)
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual Europe region WDD
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_Actual_Europe] where REGION='TTF'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('europe_region_base65F_wdd_observations_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            if fifteen_day["DATES"].iloc[-1] == "END.":
                datareq.drop(fifteen_day.index[-1], axis=0, inplace=True)
            datareq['DATES'] = pd.to_datetime(datareq['DATES'])
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    'REGION_NAME': 'REGION',
                                    }, inplace=True)
            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_Actual_Europe", index=False)
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual Europe WDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_Fcast_Europe] where REGION='Europe'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('europe_base65F_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day = fifteen_day.loc[fifteen_day['IS_FORECAST'] == True, :]
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    }, inplace=True)
            datareq['REGION'] = 'Europe'
            datareq['AS_OF_DATE'] = val_date
            if len(df2) == 0 or df2.loc[df2['AS_OF_DATE'] == (val_date)].empty:
                print(val_date)
                sql.to_sql(datareq, "CWG_Fcast_Europe", index=False)

    """
    Actual Europe region WDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_Fcast_Europe] where REGION='TTF'")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
        fifday = requests.get(cwg_url('europe_region_base65F_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')
        if ('DATES' in fifteen_day.columns):
            fifteen_day = fifteen_day.loc[fifteen_day['IS_FORECAST'] == True, :]
            datareq = fifteen_day.drop('IS_FORECAST', axis=1)
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            datareq.rename(columns={'30Y_POP_HDD': 'POP_HDD_30Y',
                                    '10Y_POP_HDD': 'POP_HDD_10Y',
                                    '30Y_POP_CDD': 'POP_CDD_30Y',
                                    '10Y_POP_CDD': 'POP_CDD_10Y',
                                    'REGION_NAME': 'REGION',
                                    }, inplace=True)
            datareq['AS_OF_DATE'] = val_date
            if len(df2) == 0 or df2.loc[df2['AS_OF_DATE'] == (val_date)].empty:
                print(val_date)
                sql.to_sql(datareq, "CWG_Fcast_Europe", index=False)


def update_us_other():
    """
    Actual 5region
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_CDD_ELEC_Actual_Region]")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_5region_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] < value_date]
            datareq = data[['DATES', 'REGION_NAME', 'ELEC_CDD', '10Y_ELEC_CDD', 'IS_FORECAST']]

            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_CDD_ELEC_Actual_Region")
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual HDDs
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_HDD_Actual]")
    df_hdd = sql.read_sql(query2)
    datapanda = []
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_national_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] < value_date]
            datareq = data[['DATES', 'NG_HDD', '10Y_NG_HDD', 'IS_FORECAST']]
            datapanda.append(datareq)

            if any(~datareq['DATES'].isin(df_hdd['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_HDD_Actual")
                df_hdd = pd.concat([df_hdd, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual CDDs
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_CDD_Actual]")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_national_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] < value_date]
            datareq = data[['DATES', 'POP_CDD', '10Y_POP_CDD', 'IS_FORECAST']]

            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_CDD_Actual")
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    Actual ELEC CDDs
    """
    query2 = ("select distinct (DATES) from [dbo].[CWG_CDD_ELEC_Actual]")
    df2 = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_national_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] < value_date]
            datareq = data[['DATES', 'ELEC_CDD', '10Y_ELEC_CDD', 'IS_FORECAST']]

            if any(~datareq['DATES'].isin(df2['DATES'])):
                print(val_date)
                datareq = datareq[~datareq['DATES'].isin(df2['DATES'])]
                sql.to_sql(datareq, "CWG_CDD_ELEC_Actual")
                df2 = pd.concat([df2, datareq['DATES'].to_frame('DATES')], axis=0)

    """
    next 2 weeks HDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_fifteenday_fcast]")
    df_hdd_frcst = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_national_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] >= value_date]
            datareq = data[['DATES', 'NG_HDD', '10Y_NG_HDD', 'IS_FORECAST']]
            datareq['AS_OF_DATE'] = val_date
            df_hdd_frcst['AS_OF_DATE'] = pd.to_datetime(df_hdd_frcst['AS_OF_DATE'])
            if (df_hdd_frcst.loc[df_hdd_frcst['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(datareq, "CWG_fifteenday_fcast")

    """
    next 2 weeks CDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_fifteenday_fcast_CDD]")
    df_cdd_frcst = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_national_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] >= value_date]
            datareq = data[['DATES', 'POP_CDD', '10Y_POP_CDD', 'IS_FORECAST']]
            datareq['AS_OF_DATE'] = val_date
            if (df_cdd_frcst.loc[df_cdd_frcst['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(datareq, "CWG_fifteenday_fcast_CDD")

    """
    next 2 weeks ELEC CDD forecast
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_fifteenday_fcast_CDD_ELEC]")
    df_cdd_frcst = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_national_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] >= value_date]
            datareq = data[['DATES', 'ELEC_CDD', '10Y_ELEC_CDD', 'IS_FORECAST']]
            datareq['AS_OF_DATE'] = val_date
            if (df_cdd_frcst.loc[df_cdd_frcst['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(datareq, "CWG_fifteenday_fcast_CDD_ELEC")

    """
    next 2 weeks ELEC CDD forecast - Regions
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_fifteenday_fcast_CDD_ELEC_Region]")
    df_cdd_frcst = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('northamerica_5region_wdd_{}.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        fifteen_day = fifteen_day[:-1]

        if ('DATES' in fifteen_day.columns):
            fifteen_day['DATES'] = pd.to_datetime(fifteen_day['DATES'])
            data = fifteen_day.loc[fifteen_day['DATES'] >= value_date]
            datareq = data[['DATES', 'REGION_NAME', 'ELEC_CDD', '10Y_ELEC_CDD', 'IS_FORECAST']]
            datareq = datareq[datareq['REGION_NAME'].isin(['South Central', 'East'])]
            datareq['AS_OF_DATE'] = val_date
            if (df_cdd_frcst.loc[df_cdd_frcst['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(datareq, "CWG_fifteenday_fcast_CDD_ELEC_Region")

    """
    forecast for balance of current month HDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_MONTH]")
    df_bom = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('ng_hdd_{}_bal_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew = x[['National', 'Unnamed: 4', 'Unnamed: 5', 'Unnamed: 6']]
            xnew.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew['AS_OF_DATE'] = val_date
            xnew['FCAST_MONTH'] = val_month
            df_bom['AS_OF_DATE'] = pd.to_datetime(df_bom['AS_OF_DATE'])
            if (df_bom.loc[df_bom['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_MONTH")

    """
    forecast for balance of current month CDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_MONTH_CDD]")
    df_bom = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('elec_cdd_{}_bal_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew = x[['National', 'Unnamed: 4', 'Unnamed: 5', 'Unnamed: 6']]
            xnew.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew['AS_OF_DATE'] = val_date
            xnew['FCAST_MONTH'] = val_month
            df_bom['AS_OF_DATE'] = pd.to_datetime(df_bom['AS_OF_DATE'])
            if (df_bom.loc[df_bom['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_MONTH_CDD")

    """
    forecast for balance of current month regional CDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_MONTH_CDD_Region]")
    df_bom = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('elec_cdd_{}_bal_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew2 = x[['East', 'Unnamed: 9', 'Unnamed: 10', 'Unnamed: 11']]
            xnew2.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew2['AS_OF_DATE'] = val_date
            xnew2['FCAST_MONTH'] = val_month
            xnew2['REGION_NAME'] = 'East'

            xnew1 = x[['South Central', 'Unnamed: 14', 'Unnamed: 15', 'Unnamed: 16']]
            xnew1.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew1['AS_OF_DATE'] = val_date
            xnew1['FCAST_MONTH'] = val_month
            xnew1['REGION_NAME'] = 'South Central'

            xnew = pd.concat([xnew1, xnew2], axis=0)
            df_bom['AS_OF_DATE'] = pd.to_datetime(df_bom['AS_OF_DATE'])
            if (df_bom.loc[df_bom['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_MONTH_CDD_Region")

    """
    forecast for balance of current month regional CDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_MONTH_HDD_Region]")
    df_bom = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('ng_hdd_{}_bal_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew2 = x[['East', 'Unnamed: 9', 'Unnamed: 10', 'Unnamed: 11']]
            xnew2.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew2['AS_OF_DATE'] = val_date
            xnew2['FCAST_MONTH'] = val_month
            xnew2['REGION_NAME'] = 'East'

            xnew1 = x[['South Central', 'Unnamed: 14', 'Unnamed: 15', 'Unnamed: 16']]
            xnew1.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew1['AS_OF_DATE'] = val_date
            xnew1['FCAST_MONTH'] = val_month
            xnew1['REGION_NAME'] = 'South Central'

            xnew = pd.concat([xnew1, xnew2], axis=0)
            df_bom['AS_OF_DATE'] = pd.to_datetime(df_bom['AS_OF_DATE'])
            if (df_bom.loc[df_bom['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_MONTH_HDD_Region")

    """
    forecast for next month HDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_NEXT_MONTH]")
    df_nm = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1) + relativedelta(months=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('ng_hdd_{}_bal_next_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew = x[['National', 'Unnamed: 4', 'Unnamed: 5', 'Unnamed: 6']]
            xnew.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew['AS_OF_DATE'] = val_date
            xnew['FCAST_MONTH'] = val_month
            df_nm['AS_OF_DATE'] = pd.to_datetime(df_nm['AS_OF_DATE'])
            if (df_nm.loc[df_nm['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_NEXT_MONTH")

    """
    forecast for next month CDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_NEXT_MONTH_CDD]")
    df_nm = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1) + relativedelta(months=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('elec_cdd_{}_bal_next_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew = x[['National', 'Unnamed: 4', 'Unnamed: 5', 'Unnamed: 6']]
            xnew.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew['AS_OF_DATE'] = val_date
            xnew['FCAST_MONTH'] = val_month
            df_nm['AS_OF_DATE'] = pd.to_datetime(df_nm['AS_OF_DATE'])
            if (df_nm.loc[df_nm['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_NEXT_MONTH_CDD")

    """
    forecast for next month regional CDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_NEXT_MONTH_CDD_Region]")
    df_nm = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1) + relativedelta(months=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('elec_cdd_{}_bal_next_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew2 = x[['East', 'Unnamed: 9', 'Unnamed: 10', 'Unnamed: 11']]
            xnew2.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew2['AS_OF_DATE'] = val_date
            xnew2['FCAST_MONTH'] = val_month
            xnew2['REGION_NAME'] = 'East'

            xnew1 = x[['South Central', 'Unnamed: 14', 'Unnamed: 15', 'Unnamed: 16']]
            xnew1.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew1['AS_OF_DATE'] = val_date
            xnew1['FCAST_MONTH'] = val_month
            xnew1['REGION_NAME'] = 'South Central'

            xnew = pd.concat([xnew1, xnew2], axis=0)
            df_nm['AS_OF_DATE'] = pd.to_datetime(df_nm['AS_OF_DATE'])
            if (df_nm.loc[df_nm['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_NEXT_MONTH_CDD_Region")

    """
    forecast for next month regional HDD
    """
    query2 = ("select distinct (AS_OF_DATE) from [dbo].[CWG_BALANCE_OF_NEXT_MONTH_HDD_Region]")
    df_nm = sql.read_sql(query2)
    for i in range(0, go_back):
        val_date = today() - dt.timedelta(i)
        val_month = val_date.replace(day=1) + relativedelta(months=1)
        print(val_date)
        value_date = pd.to_datetime(val_date)
        val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')

        fifday = requests.get(cwg_url('ng_hdd_{}_bal_next_daily.csv'.format(val_d)), verify=False)
        t3 = fifday.content
        s3 = str(t3, 'utf-8')
        data3 = StringIO(s3)
        fifteen_day = pd.read_csv(data3, sep=',')

        if (len(fifteen_day.columns) > 1):
            x = fifteen_day[-1:]
            xnew2 = x[['East', 'Unnamed: 9', 'Unnamed: 10', 'Unnamed: 11']]
            xnew2.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew2['AS_OF_DATE'] = val_date
            xnew2['FCAST_MONTH'] = val_month
            xnew2['REGION_NAME'] = 'East'

            xnew1 = x[['South Central', 'Unnamed: 14', 'Unnamed: 15', 'Unnamed: 16']]
            xnew1.columns = ['National', 'Last Year', '30Y', '10Y']
            xnew1['AS_OF_DATE'] = val_date
            xnew1['FCAST_MONTH'] = val_month
            xnew1['REGION_NAME'] = 'South Central'

            xnew = pd.concat([xnew1, xnew2], axis=0)
            df_nm['AS_OF_DATE'] = pd.to_datetime(df_nm['AS_OF_DATE'])
            if (df_nm.loc[df_nm['AS_OF_DATE'] == (value_date)].empty):
                print(val_date)
                sql.to_sql(xnew, "CWG_BALANCE_OF_NEXT_MONTH_HDD_Region")


def update_global_bom():
    """
    forecast for balance of current month HDD
    """
    regions = ["asia", "europe"]
    sub_regions1 = ["Asia", "China", "Japan", "Skorea", "India"]
    sub_regions2 = ["Europe", "Iberia", "Italy", "UK", "Russia", "TTF", "Germany", "France"]
    metric = ["pop_cdd", "pop_hdd"]
    for j in regions:
        for k in metric:
            last = sql.read_sql(f"Select MAX(AS_OF_DATE) from CWG_BALANCE_OF_MONTH_Global where Region='{j}' and Metric='{k}'").iloc[0, 0]
            if last is not None:
                sdate = pd.to_datetime(last) + dt.timedelta(1)
            else:
                sdate = dt.datetime(2025, 1, 1)
            if sdate <= today():
                for i in pd.date_range(sdate, today()):
                    val_date = i
                    val_month = val_date.replace(day=1)
                    print(val_date, k, j)
                    val_d = val_date.strftime('%Y') + val_date.strftime('%m') + val_date.strftime('%d')
                    try:
                        fifday = requests.get(cwg_url(f'{j}_base65F_{k}_{val_d}_bal_daily.csv'), verify=False)
                        t3 = fifday.content
                        s3 = str(t3, 'utf-8')
                        data3 = StringIO(s3)
                        fifteen_day = pd.read_csv(data3, sep=',')
                    except:
                        fifteen_day = pd.DataFrame()
                    if (len(fifteen_day.columns) > 1):
                        fifteen_day = fifteen_day.drop(["Unnamed: 1"], axis=1)
                        fifteen_day.set_index("Unnamed: 0", inplace=True)
                        fifteen_day_data = fifteen_day.iloc[1:, :].apply(pd.to_numeric)
                        total = fifteen_day_data.sum(axis=0).to_frame().T
                        xnew_all = pd.DataFrame()
                        if j == "asia":
                            sub_regions = sub_regions1
                        elif j == "europe":
                            sub_regions = sub_regions2
                        for idx, m in enumerate(sub_regions):
                            xnew = total.iloc[:, list(range(idx*5, idx*5+5))]
                            xnew.columns = ['Value', 'chg', 'Last Year', '30Y', '10Y']
                            xnew.drop('chg', axis=1, inplace=True)
                            pd.options.mode.chained_assignment = None
                            xnew.loc[0, 'AS_OF_DATE'] = val_date
                            xnew.loc[0, 'FCAST_MONTH'] = val_month
                            xnew.loc[0, 'Region'] = m
                            xnew.loc[0, 'Metric'] = k
                            pd.options.mode.chained_assignment = 'warn'
                            xnew_all = pd.concat([xnew_all, xnew], axis=0, ignore_index=True)
                        sql.to_sql(xnew_all, "CWG_BALANCE_OF_MONTH_Global")


def update_seasonal_forecast():
    """
    https://api.commoditywx.com/v1/monthlyddtotals_{dateyyyymm}.csv
    """
    reg_list = ["us", "asia", "europe"]
    for i in reg_list:
        raise NotImplementedError("CWG seasonal latest-date subquery is clipped at source line 1120")
        last_data = last_data[pd.to_datetime(last_data["Issued_Date"]) <= today()]
        last_data.sort_values("Month_Season", inplace=True)
        last_data.sort_values("Issued_Date", inplace=True)
        last_data.drop_duplicates(subset=["Month_Season"], inplace=True)
        last_data.reset_index(inplace=True, drop=True)
        if len(last_data) > 0:
            last = last_data["As_of_date"].iloc[-1]
            sdate = pd.to_datetime(last)
        else:
            sdate = today() - dt.timedelta(1)
        if sdate <= today():
            latest_as_of_date = today()
            if i == 'us':
                req = requests.get(cwg_url(f"monthlyddtotals_{latest_as_of_date.strftime('%Y%m')}.csv"), verify=False)
            else:
                req = requests.get(cwg_url(f"{i}_monthlyddtotals_{latest_as_of_date.strftime('%Y%m')}.csv"), verify=False)
            if req.status_code == 200:
                latest_data = pd.read_csv(StringIO(str(req.content, 'utf-8')), sep=',')
                if len(latest_data) > 0:
                    latest_data.rename(columns={"Month/Season": "Month_Season"}, inplace=True)
                    latest_data.columns = [x.lstrip() for x in latest_data.columns]
                    latest_data.sort_values("Month_Season", inplace=True)
                    latest_data.sort_values("Issued_Date", inplace=True)
                    latest_data.reset_index(inplace=True, drop=True)
                    any_bad_data = latest_data[pd.to_datetime(latest_data["Issued_Date"]) > today()]
                    if len(any_bad_data) > 0:
                        raise ValueError(f"Data for region {i} contains future Issued_Date values.")
                    latest_data = latest_data[pd.to_datetime(latest_data["Issued_Date"]) <= today()]
                    latest_data.reset_index(inplace=True, drop=True)
                    latest_data["Region"] = i
                    latest_data["As_of_date"] = latest_as_of_date
                    sql.to_sql(latest_data, f"CWG_Seasonal_Forecast", index=False)
                    print(f"Inserted/Updated CWG_Seasonal_Forecast for region {i} as of date {latest_as_of_date}")


def update():
    update_us()
    update_global()
    update_cwg_asia()
    update_cwg_europe()
    update_us_other()
    update_global_bom()
    update_seasonal_forecast()


if __name__ == "__main__":
    update()
