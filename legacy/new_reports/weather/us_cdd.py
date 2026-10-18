import pandas as pd
import numpy as np
import datetime as dt
from pandas.tseries.offsets import BDay
from dateutil.relativedelta import relativedelta, FR
import holidays
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly as py
import sys
import os

os.environ['CMDSTAN'] = "C:\\local\\python\\miniconda\\envs\\ecm_cmds\\Library\\bin\\cmdstan"
import ecm.cmds.sql as sql
import ecm.cmds.table as table
import ecm.cmds.talib as talib
import ecm.cmds.time_series as ts
import ecm.cmds.bbg as bbg
import ecm.cmds.stormvista as sv

from ecm.cmds.config import output_path, html_path, root_path, gas_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, month_int2str
from ecm.cmds.utils import convert_path_to_linux

send_to = ['rzhao@elementcapital.com']
report_name = "Weather - US CWG CDD Update"
file_name = "us_cdd"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
weather_csv = f"{output_path}\\csvs\\weather"


def _unrecovered(location):
    """Recovery marker for text outside the supplied photographs."""
    raise NotImplementedError(f"Unrecovered source: {location}")


def get_power_demand():
    """
    Historical ResCom data
    """
    tickers = ['GSDEDUSP Index', 'HISTCNEC Index']
    rescom = bbg.bdh(tickers, ['PX_LAST'], sdate=dt.datetime(2010, 1, 1), edate=today())
    rescom.rename(columns={'GSDEDUSP Index': 'US Power demand actuals',
                           'HISTCNEC Index': 'US Gas CDD actuals'}, inplace=True)
    rescom['US Power demand actuals'] = rescom['US Power demand actuals'] / 1000000
    rescom.to_csv(r'\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\weather\US_cdd.csv')
    return rescom


def get_rescom():
    """
    Historical ResCom data
    """
    tickers = ['GSDEDUSR Index', 'HISTCNGH Index']
    rescom = bbg.bdh(tickers, ['PX_LAST'], sdate=dt.datetime(2010, 1, 1), edate=today())
    rescom.rename(columns={'GSDEDUSR Index': 'US ResCom demand actuals',
                           'HISTCNGH Index': 'US Gas HDD actuals'}, inplace=True)
    rescom['US ResCom demand actuals'] = rescom['US ResCom demand actuals'] / 1000000
    rescom.to_csv(r'\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\weather\US_gas.csv')
    return rescom


def get_power_demand_region():
    """
    Historical ResCom data
    """
    tickers = ['HISTCNEC Index', 'HISTSCEC Index', 'HISTESEC Index']
    rescom = bbg.bdh(tickers, ['PX_LAST'], sdate=dt.datetime(2010, 1, 1), edate=today())
    rescom.rename(columns={'HISTCNEC Index': 'US Total Elec CDD',
                           'HISTSCEC Index': 'US South Central Elec CDD',
                           'HISTESEC Index': 'US East Elec CDD'}, inplace=True)
    rescom.to_csv(r'\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\weather\US_cdd_region.csv')
    return rescom


def get_rescom_region_cwg():
    """
    Historical ResCom data from CWG
    """
    data = sql.read_sql(
        ("Select distinct * from (Select DATES, ELEC_CDD, [10Y_ELEC_CDD], REGION_NAME from CWG_US_5region "
         + _unrecovered('IMG_4899 line 79: SQL filter before IS_FORECAST') +
         "IS_FORECAST = 0 ) as t order by DATES")
    )
    data_sc_cdd = data.loc[data['REGION_NAME'] == 'South Central', ['DATES', 'ELEC_CDD', '10Y_ELEC_CDD']]
    data_sc_cdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_sc_cdd.set_index('DATES', inplace=True)
    data_east_cdd = data.loc[data['REGION_NAME'] == 'East', ['DATES', 'ELEC_CDD', '10Y_ELEC_CDD']]
    data_east_cdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_east_cdd.set_index('DATES', inplace=True)

    data1 = sql.read_sql("Select distinct * from (Select DATES, ELEC_CDD, [10Y_ELEC_CDD] from CWG_US_National" + _unrecovered('IMG_4899 line 89: SQL tail'))
    data1.drop_duplicates('DATES', keep='first', inplace=True)
    data1.set_index('DATES', inplace=True)
    rescom_cdd = pd.concat([data1['ELEC_CDD'], data_sc_cdd['ELEC_CDD'], data_east_cdd['ELEC_CDD']], axis=1)
    rescom_cdd.columns = ['US Total CDD', 'US South Central CDD', 'US East CDD']
    rescom_norm_cdd = pd.concat([data1['10Y_ELEC_CDD'], data_sc_cdd['10Y_ELEC_CDD'], data_east_cdd['10Y_ELEC_CDD']],
                                axis=1)
    rescom_norm_cdd.columns = ['US Total CDD', 'US South Central CDD', 'US East CDD']

    sql_str = ("select t1.* from CWG_US_5region t1 INNER JOIN (select max(AS_OF_DATE) as dt from "
               "CWG_US_5region) t2 on t1.AS_OF_DATE = t2.dt where t1.IS_FORECAST = 1")
    data_f = sql.read_sql(sql_str)
    sql_str = ("select t1.* from CWG_US_national t1 INNER JOIN (select max(AS_OF_DATE) as dt "
               "from CWG_US_national) t2 on t1.AS_OF_DATE = t2.dt where t1.IS_FORECAST = 1")
    data1_f = sql.read_sql(sql_str)
    data1_f.drop_duplicates('DATES', keep='first', inplace=True)
    data1_f.set_index('DATES', inplace=True)
    data_sc_f_cdd = data_f.loc[data_f['REGION_NAME'] == 'South Central', ['DATES', 'ELEC_CDD', '10Y_ELEC_CDD']]
    data_sc_f_cdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_sc_f_cdd.set_index('DATES', inplace=True)
    data_east_f_cdd = data_f.loc[data_f['REGION_NAME'] == 'East', ['DATES', 'ELEC_CDD', '10Y_ELEC_CDD']]
    data_east_f_cdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_east_f_cdd.set_index('DATES', inplace=True)
    rescom_norm_f_cdd = pd.concat(
        [data1_f['10Y_ELEC_CDD'], data_sc_f_cdd['10Y_ELEC_CDD'], data_east_f_cdd['10Y_ELEC_CDD']], axis=1)
    rescom_norm_f_cdd.columns = ['US Total CDD', 'US South Central CDD', 'US East CDD']
    rescom_norm_cdd = pd.concat([rescom_norm_cdd, rescom_norm_f_cdd], axis=0)
    rescom = rescom_cdd
    rescom_norm = rescom_norm_cdd
    rescom.index = pd.to_datetime(rescom.index)
    rescom_norm.index = pd.to_datetime(rescom_norm.index)
    return rescom, rescom_norm


def get_rescom_region_cwg_hdd():
    """
    Historical ResCom data from CWG
    """
    data = sql.read_sql(
        ("Select distinct * from CWG_US_5region where REGION_NAME in ('South Central', 'East') and "
         "IS_FORECAST = 0 order by DATES")
    )
    data_sc_hdd = data.loc[data['REGION_NAME'] == 'South Central', ['DATES', 'NG_HDD', '10Y_NG_HDD']]
    data_sc_hdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_sc_hdd.set_index('DATES', inplace=True)
    data_east_hdd = data.loc[data['REGION_NAME'] == 'East', ['DATES', 'NG_HDD', '10Y_NG_HDD']]
    data_east_hdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_east_hdd.set_index('DATES', inplace=True)

    data1 = sql.read_sql("Select distinct * from CWG_US_national where IS_FORECAST = 0 order by DATES")
    data1.drop_duplicates('DATES', keep='first', inplace=True)
    data1.set_index('DATES', inplace=True)
    rescom_hdd = pd.concat([data1['NG_HDD'], data_sc_hdd['NG_HDD'], data_east_hdd['NG_HDD']], axis=1)
    rescom_hdd.columns = ['US Total HDD', 'US South Central HDD', 'US East HDD']
    rescom_norm_hdd = pd.concat([data1['10Y_NG_HDD'], data_sc_hdd['10Y_NG_HDD'], data_east_hdd['10Y_NG_HDD']], axis=1)
    rescom_norm_hdd.columns = ['US Total HDD', 'US South Central HDD', 'US East HDD']

    sql_str = ("select t1.* from CWG_US_5region t1 INNER JOIN (select max(AS_OF_DATE) as dt from "
               "CWG_US_5region) t2 on t1.AS_OF_DATE = t2.dt where t1.IS_FORECAST = 1")
    data_f = sql.read_sql(sql_str)
    data_sc_f_hdd = data_f.loc[data_f['REGION_NAME'] == 'South Central', ['DATES', 'NG_HDD', '10Y_NG_HDD']]
    data_sc_f_hdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_sc_f_hdd.set_index('DATES', inplace=True)
    data_east_f_hdd = data_f.loc[data_f['REGION_NAME'] == 'East', ['DATES', 'NG_HDD', '10Y_NG_HDD']]
    data_east_f_hdd.drop_duplicates('DATES', keep='first', inplace=True)
    data_east_f_hdd.set_index('DATES', inplace=True)
    sql_str = ("select t1.* from CWG_US_national t1 INNER JOIN (select max(AS_OF_DATE) as dt "
               "from CWG_US_national) t2 on t1.AS_OF_DATE = t2.dt where t1.IS_FORECAST = 1")
    data1_f = sql.read_sql(sql_str)
    data1_f.drop_duplicates('DATES', keep='first', inplace=True)
    data1_f.set_index('DATES', inplace=True)
    rescom_norm_f_hdd = pd.concat([data1_f['10Y_NG_HDD'], data_sc_f_hdd['10Y_NG_HDD'], data_east_f_hdd['10Y_NG_HDD']],
                                axis=1)
    rescom_norm_f_hdd.columns = ['US Total HDD', 'US South Central HDD', 'US East HDD']
    rescom_norm_hdd = pd.concat([rescom_norm_hdd, rescom_norm_f_hdd], axis=0)
    rescom = rescom_hdd
    rescom_norm = rescom_norm_hdd
    rescom.index = pd.to_datetime(rescom.index)
    rescom_norm.index = pd.to_datetime(rescom_norm.index)
    return rescom, rescom_norm


def fit_demand_forecast(y, x, start=-1, hol=None, forecast=0):
    """
    kernel regression, y and x is pandas series
    """
    data = pd.concat([x, y], axis=1)
    data.columns = ['x', 'y']
    data.index.name = 'ds'
    data.reset_index(inplace=True)
    forecast = talib.ts_regression(data, hol=hol, start=start, forecast_periods=forecast)
    return forecast['yhat']


def us_weather_hdd_model(gas, hdd, start, hol=None, forecast=0):
    """
    Forecast gas demand based on hdd
    """
    return fit_demand_forecast(y=gas, x=hdd, start=start, hol=hol, forecast=forecast)


def hdd_forecast_chart():
    normals = pd.read_sql("select * from [LO25].[dbo].[CWG_Normals]")
    fcasts = pd.read_sql("select * from [dbo].[CWG_fifteenday_fcast_CDD_ELEC]")

    fcasts['AS_OF_DATE'] = pd.to_datetime(fcasts['AS_OF_DATE'])
    fcasts = fcasts.drop_duplicates(['DATES', 'AS_OF_DATE'], keep='last')
    fcasts = fcasts.sort_values('AS_OF_DATE')


    x = pd.DataFrame(fcasts['AS_OF_DATE'].unique()).tail(10)
    enddate = x[0].max()
    startdate = x[0].min()
    graphingdata = fcasts
    datareq = (fcasts['AS_OF_DATE'] > startdate) & (fcasts['AS_OF_DATE'] <= enddate)


    fcasts = fcasts.loc[datareq]


    pttable = fcasts.pivot_table(values='NG_CDD', index='DATES', columns='AS_OF_DATE')
    pttable = pttable.reset_index()

    graphingtable = pttable.copy()

    pttable['vs yest'] = pttable.iloc[:, -1] - pttable.iloc[:, -2]

    pttable['vs last week'] = pttable.iloc[:, -2] - pttable.iloc[:, -8]

    pttable = pttable.merge(normals['ng_hdd_10yr'], how='inner',
                            left_on=(pttable['DATES'].dt.month, pttable['DATES'].dt.day),
                            right_on=(normals['Month'], normals['Day']))

    graphingtable = graphingtable.merge(normals['ng_hdd_10yr'], how='inner',
                                        left_on=(graphingtable['DATES'].dt.month, graphingtable['DATES'].dt.day),
                                        right_on=(normals['Month'], normals['Day']))

    pttable = pttable.drop(columns=['key_0', 'key_1'])
    graphingtable = graphingtable.drop(columns=['key_0', 'key_1'])

    graphingtable = graphingtable.set_index(graphingtable['DATES'])

    yt = graphingtable[graphingtable.columns[-4:]]

    dataPanda2 = []
    for j in range(0, len(yt.columns)):
        trace = go.Scatter(x=yt.index, y=yt.iloc[:, j], connectgaps=True, name=str((yt.columns[j])), mode=_unrecovered('IMG_4902 line 249: Scatter mode and possible trailing arguments'))
        dataPanda2.append(trace)

    layout2 = go.Layout(title='1-15 run')
    fig2 = go.Figure(data=dataPanda2, layout=layout2)
    return fig2


def get_forecast_cdd():
    fcasts = sql.read_sql(
        "select distinct DATES, ELEC_CDD, [10Y_ELEC_CDD], IS_FORECAST, AS_OF_DATE from CWG_US_national where " + _unrecovered('IMG_4902 line 259: forecast SQL filter'))
    fcasts.columns = ['DATES', 'NG_CDD', '10Y_NG_CDD', 'IS_FORECAST', 'AS_OF_DATE']
    fcasts['AS_OF_DATE'] = pd.to_datetime(fcasts['AS_OF_DATE'])
    fcasts['DATES'] = pd.to_datetime(fcasts['DATES'])
    fcasts = fcasts.drop_duplicates(['DATES', 'AS_OF_DATE'], keep='last')
    fcasts = fcasts.sort_values('AS_OF_DATE')
    return fcasts


def get_forecast_hdd():
    fcasts = sql.read_sql(
        "select distinct DATES, NG_HDD, [10Y_NG_HDD], IS_FORECAST, AS_OF_DATE from CWG_US_national where IS" + _unrecovered('IMG_4902 line 270: forecast SQL filter tail'))
    fcasts['AS_OF_DATE'] = pd.to_datetime(fcasts['AS_OF_DATE'])
    fcasts['DATES'] = pd.to_datetime(fcasts['DATES'])
    fcasts = fcasts.drop_duplicates(['DATES', 'AS_OF_DATE'], keep='last')
    fcasts = fcasts.sort_values('AS_OF_DATE')
    return fcasts


def get_forecast_cdd_region(region='South Central'):
    start_date = today() - relativedelta(days=35)
    start_date = start_date.strftime('%Y-%m-%d')
    if region.lower() == 'total':
        fcasts_cdd = sql.read_sql(
            (f"select distinct DATES, ELEC_CDD, [10Y_ELEC_CDD], AS_OF_DATE from CWG_US_national "
             f"where AS_OF_DATE > '{start_date}' and IS_FORECAST=1 order by AS_OF_DATE, DATES")
        )
        fcasts_cdd['REGION_NAME'] = 'Total'
    else:
        fcasts_cdd = sql.read_sql(
            (f"select distinct DATES, ELEC_CDD, [10Y_ELEC_CDD], AS_OF_DATE, REGION_NAME from "
             f"CWG_US_5region where AS_OF_DATE > '{start_date}' and IS_FORECAST=1 order by AS_OF_DATE, DATES")
        )
        fcasts_cdd = fcasts_cdd.loc[fcasts_cdd['REGION_NAME'] == region, :]
    fcasts_cdd.columns = ['DATES', 'NG_CDD', '10Y_NG_CDD', 'AS_OF_DATE', 'REGION_NAME']
    fcasts_cdd['AS_OF_DATE'] = pd.to_datetime(fcasts_cdd['AS_OF_DATE'])
    fcasts_cdd['DATES'] = pd.to_datetime(fcasts_cdd['DATES'])
    fcasts_cdd = fcasts_cdd.drop_duplicates(['DATES', 'AS_OF_DATE', 'REGION_NAME'], keep='last')
    fcasts_cdd = fcasts_cdd.sort_values('AS_OF_DATE')
    fcasts = pd.DataFrame()
    dts = _unrecovered('IMG_4902/4903 line 299: date-iteration assignment hidden at image boundary')
    for i in dts:
        fcasts_cdd_ = (fcasts_cdd.loc[fcasts_cdd['AS_OF_DATE'] == i, :]).set_index('DATES').sort_index()
        fcasts = pd.concat([fcasts, fcasts_cdd_], axis=0)
    return fcasts.reset_index()


def demand_forecast_region(data, bbg_normal, region='South Central'):
    data_temp = data.copy()
    data_temp.dropna(axis=0, inplace=True)
    data_temp['Month'] = data_temp.index.month
    data_temp['Day'] = data_temp.index.day

    fcasts = get_forecast_cdd_region(region=region)
    fcast_date = np.sort(fcasts['AS_OF_DATE'].unique())
    current_day = fcasts['AS_OF_DATE'].max()
    hdd_fcasts0 = fcasts.loc[fcasts['AS_OF_DATE'] == fcast_date[-1], :].sort_values('DATES')

    if 0 < current_day.weekday() <= 5:
        last_day = pd.to_datetime(str(fcast_date[-2]))
        last_day1 = pd.to_datetime(str(fcast_date[-3]))
    elif current_day.weekday() == 0:
        last_day = pd.to_datetime(str(fcast_date[-2]))
        last_day1 = pd.to_datetime(str(fcast_date[-3]))  # -3 because there is no Sat in forecast
    elif current_day.weekday() == 6:
        last_day = pd.to_datetime(str(fcast_date[-2]))  # -2 because there is no Sat in forecast
        last_day1 = pd.to_datetime(str(fcast_date[-3]))
    hdd_fcasts1 = fcasts.loc[fcasts['AS_OF_DATE'] == last_day, :].sort_values('DATES')
    hdd_fcasts2 = fcasts.loc[fcasts['AS_OF_DATE'] == last_day1, :].sort_values('DATES')

    fcast_days = pd.date_range(current_day - dt.timedelta(days=14), hdd_fcasts0['DATES'].iloc[-1])
    hdd_df = pd.DataFrame(np.nan, index=fcast_days, columns=[current_day, last_day, last_day1])
    hdd_df.loc[hdd_fcasts2['DATES'], last_day1] = hdd_fcasts2['NG_CDD'].values
    hdd_df.loc[hdd_fcasts1['DATES'], last_day] = hdd_fcasts1['NG_CDD'].values
    hdd_df.loc[hdd_fcasts0['DATES'], current_day] = hdd_fcasts0['NG_CDD'].values

    hdd_df['ng_cdd_10yr'] = bbg_normal[f'US {region} CDD']
    hdd_df.rename(columns={'ng_cdd_10yr': 'Normal',
                           current_day: dt.datetime.strftime(current_day, '%Y-%m-%d'),
                           last_day: dt.datetime.strftime(last_day, '%Y-%m-%d'),
                           last_day1: dt.datetime.strftime(last_day1, '%Y-%m-%d'),
                           }, inplace=True)

    dts_5d = np.sort(fcast_date[-10:])[::-1]
    hdd_5d = pd.DataFrame(np.nan, index=hdd_fcasts0['DATES'], columns=dts_5d)
    for i in dts_5d:
        hdd_f = fcasts.loc[fcasts['AS_OF_DATE'] == i, ['DATES', 'NG_CDD']].sort_values('DATES')
        hdd_f.set_index('DATES', inplace=True)
        hdd_f = hdd_f['NG_CDD']
        hdd_n = bbg_normal.loc[bbg_normal.index > hdd_f.index[-1], f'US {region} CDD']
        hdd_fn = pd.concat([hdd_f, hdd_n], axis=0)
        hdd_5d[i] = hdd_fn.reindex(hdd_fcasts0['DATES'])
    return hdd_df, hdd_5d


def demand_forecast_cdd(data, bbg_normal):
    data_temp = data.copy()
    data_temp.dropna(axis=0, inplace=True)
    data_temp['Month'] = data_temp.index.month
    data_temp['Day'] = data_temp.index.day
    fcasts = get_forecast_cdd()
    fcast_date = np.sort(fcasts['AS_OF_DATE'].unique())

    i_holidays = holidays.country_holidays('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': i_holidays})

    hdd_fcasts0 = fcasts.loc[fcasts['AS_OF_DATE'] == fcast_date[-1], :].sort_values('DATES')
    fcasts0 = get_demand_forecast_cdd(hdd_fcasts0, data, hol=df_holidays)
    current_day = fcasts0['AS_OF_DATE'].iloc[0]

    if 0 < current_day.weekday() <= 5:
        last_day = pd.to_datetime(str(fcast_date[-2]))
        last_day1 = pd.to_datetime(str(fcast_date[-3]))
    elif current_day.weekday() == 0:
        last_day = pd.to_datetime(str(fcast_date[-2]))
        last_day1 = pd.to_datetime(str(fcast_date[-3]))  # -3 because there is no Sat in forecast
    elif current_day.weekday() == 6:
        last_day = pd.to_datetime(str(fcast_date[-2]))  # -2 because there is no Sat in forecast
        last_day1 = pd.to_datetime(str(fcast_date[-3]))
    hdd_fcasts1 = fcasts.loc[fcasts['AS_OF_DATE'] == last_day, :].sort_values('DATES')
    fcasts1 = get_demand_forecast_cdd(hdd_fcasts1, data, hol=df_holidays)
    hdd_fcasts2 = fcasts.loc[fcasts['AS_OF_DATE'] == last_day1, :].sort_values('DATES')
    fcasts2 = get_demand_forecast_cdd(hdd_fcasts2, data, hol=df_holidays)

    fcast_days = pd.date_range(current_day - dt.timedelta(days=7), fcasts0['DATES'].iloc[-1])
    fcast_df = pd.DataFrame(np.nan, index=fcast_days, columns=[current_day, last_day, last_day1])
    fcast_df.loc[fcasts2['DATES'], last_day1] = fcasts2['Demand'].values
    fcast_df.loc[fcasts1['DATES'], last_day] = fcasts1['Demand'].values
    fcast_df.loc[fcasts0['DATES'], current_day] = fcasts0['Demand'].values
    fcast_df['Actual'] = data['US Power demand actuals']
    fcast_df['Smooth'] = bbg_normal['US Power demand actuals']
    fcast_df.rename(columns={'Smooth': 'Normal',
                             current_day: dt.datetime.strftime(current_day, '%Y-%m-%d'),
                             last_day: dt.datetime.strftime(last_day, '%Y-%m-%d'),
                             last_day1: dt.datetime.strftime(last_day1, '%Y-%m-%d'),
                             }, inplace=True)

    hdd_df = pd.DataFrame(np.nan, index=fcast_days, columns=[current_day, last_day, last_day1])
    hdd_df.loc[fcasts2['DATES'], last_day1] = hdd_fcasts2['NG_CDD'].values
    hdd_df.loc[fcasts1['DATES'], last_day] = hdd_fcasts1['NG_CDD'].values
    hdd_df.loc[fcasts0['DATES'], current_day] = hdd_fcasts0['NG_CDD'].values

    hdd_df['ng_cdd_10yr'] = bbg_normal['US Gas CDD actuals']
    hdd_df.rename(columns={'ng_cdd_10yr': 'Normal',
                           current_day: dt.datetime.strftime(current_day, '%Y-%m-%d'),
                           last_day: dt.datetime.strftime(last_day, '%Y-%m-%d'),
                           last_day1: dt.datetime.strftime(last_day1, '%Y-%m-%d'),
                           }, inplace=True)

    return fcast_df, hdd_df


def demand_forecast_hdd(data, bbg_normal):
    data_temp = data.copy()
    data_temp.dropna(axis=0, inplace=True)
    data_temp['Month'] = data_temp.index.month
    data_temp['Day'] = data_temp.index.day
    fcasts = get_forecast_hdd()
    fcast_date = np.sort(fcasts['AS_OF_DATE'].unique())

    i_holidays = holidays.country_holidays('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': i_holidays})

    hdd_fcasts0 = fcasts.loc[fcasts['AS_OF_DATE'] == fcast_date[-1], :].sort_values('DATES')
    fcasts0 = get_demand_forecast_hdd(hdd_fcasts0, data, hol=df_holidays)
    current_day = fcasts0['AS_OF_DATE'].iloc[0]

    if 0 < current_day.weekday() <= 5:
        last_day = pd.to_datetime(str(fcast_date[-2]))
        last_day1 = pd.to_datetime(str(fcast_date[-3]))
    elif current_day.weekday() == 0:
        last_day = pd.to_datetime(str(fcast_date[-2]))
        last_day1 = pd.to_datetime(str(fcast_date[-3]))  # -3 because there is no Sat in forecast
    elif current_day.weekday() == 6:
        last_day = pd.to_datetime(str(fcast_date[-2]))  # -2 because there is no Sat in forecast
        last_day1 = pd.to_datetime(str(fcast_date[-3]))
    hdd_fcasts1 = fcasts.loc[fcasts['AS_OF_DATE'] == last_day, :].sort_values('DATES')
    fcasts1 = get_demand_forecast_hdd(hdd_fcasts1, data, hol=df_holidays)
    hdd_fcasts2 = fcasts.loc[fcasts['AS_OF_DATE'] == last_day1, :].sort_values('DATES')
    fcasts2 = get_demand_forecast_hdd(hdd_fcasts2, data, hol=df_holidays)

    fcast_days = pd.date_range(current_day - dt.timedelta(days=7), fcasts0['DATES'].iloc[-1])
    fcast_df = pd.DataFrame(np.nan, index=fcast_days, columns=[current_day, last_day, last_day1])
    fcast_df.loc[fcasts2['DATES'], last_day1] = fcasts2['Demand'].values
    fcast_df.loc[fcasts1['DATES'], last_day] = fcasts1['Demand'].values
    fcast_df.loc[fcasts0['DATES'], current_day] = fcasts0['Demand'].values
    fcast_df['Actual'] = data['US ResCom demand actuals']
    fcast_df['Smooth'] = bbg_normal['US ResCom demand actuals']
    fcast_df.rename(columns={'Smooth': 'Normal',
                             current_day: dt.datetime.strftime(current_day, '%Y-%m-%d'),
                             last_day: dt.datetime.strftime(last_day, '%Y-%m-%d'),
                             last_day1: dt.datetime.strftime(last_day1, '%Y-%m-%d'),
                             }, inplace=True)

    hdd_df = pd.DataFrame(np.nan, index=fcast_days, columns=[current_day, last_day, last_day1])
    hdd_df.loc[fcasts2['DATES'], last_day1] = hdd_fcasts2['NG_HDD'].values
    hdd_df.loc[fcasts1['DATES'], last_day] = hdd_fcasts1['NG_HDD'].values
    hdd_df.loc[fcasts0['DATES'], current_day] = hdd_fcasts0['NG_HDD'].values

    hdd_df['ng_hdd_10yr'] = bbg_normal['US Gas HDD actuals']
    hdd_df.rename(columns={'ng_hdd_10yr': 'Normal',
                           current_day: dt.datetime.strftime(current_day, '%Y-%m-%d'),
                           last_day: dt.datetime.strftime(last_day, '%Y-%m-%d'),
                           last_day1: dt.datetime.strftime(last_day1, '%Y-%m-%d'),
                           }, inplace=True)

    return fcast_df, hdd_df


def demand_forecast_chart(fcast_df, title, bbg_tdd=None, bbg_tdd1=None, cwg_tdd=None, cwg_tdd1=None):
    fcast_df = fcast_df.loc[fcast_df.index >= fcast_df.index[-1] - dt.timedelta(days=35), :]
    if bbg_tdd is not None and bbg_tdd1 is None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='cdd', data1=bbg_tdd)
    elif bbg_tdd is not None and bbg_tdd1 is not None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        bbg_tdd = pd.concat([bbg_tdd, cwg_tdd], axis=1)
        bbg_tdd1 = pd.concat(
            [bbg_tdd1, fcast_df.loc[fcast_df.index > bbg_tdd1.index[-1], 'Actual'].to_frame(bbg_tdd1.columns[0])],
            axis=0)
        bbg_tdd1 = pd.concat([bbg_tdd1, cwg_tdd1], axis=1)
        return get_chart(fcast_df, title=title, y_axis_title='cdd', data1=bbg_tdd, data2=bbg_tdd1)
    else:
        return get_chart(fcast_df, title=title, y_axis_title='cdd')


def daily_chg_table(hdd_df_ori):
    hdd_df1 = hdd_df_ori.iloc[:, [0, 1, 3]]
    hdd_df1.dropna(axis=0, inplace=True)
    hdd_df2 = hdd_df_ori.iloc[:, [1, 2, 3]]
    hdd_df2.dropna(axis=0, inplace=True)
    table_hdd = pd.DataFrame(0, index=[0, 1],
                             columns=['Date', 'Forecast change CDD', 'Forecast vs Normal CDD', 'CDD forecast',
                                      '10Y CDD'])
    table_hdd['Date'] = [hdd_df_ori.columns[0], hdd_df_ori.columns[1]]
    table_hdd.loc[0, '10Y CDD'] = hdd_df1['Normal'].mean()
    table_hdd.loc[1, '10Y CDD'] = hdd_df2['Normal'].mean()
    table_hdd.loc[0, 'CDD forecast'] = hdd_df1.iloc[:, 0].mean()
    table_hdd.loc[1, 'CDD forecast'] = hdd_df1.iloc[:, 1].mean()
    table_hdd.loc[0, 'Forecast change CDD'] = hdd_df1.iloc[:, 0].sum() - hdd_df1.iloc[:, 1].sum()
    table_hdd.loc[1, 'Forecast change CDD'] = hdd_df2.iloc[:, 0].sum() - hdd_df2.iloc[:, 1].sum()
    table_hdd.loc[0, 'Forecast vs Normal CDD'] = hdd_df1.iloc[:, 0].sum() - hdd_df1['Normal'].sum()
    table_hdd.loc[1, 'Forecast vs Normal CDD'] = hdd_df1.iloc[:, 1].sum() - hdd_df1['Normal'].sum()
    return table_hdd


def get_demand_forecast_cdd(fcasts0, data, hol=None):
    data_fcasts0 = pd.DataFrame(np.nan, index=fcasts0['DATES'], columns=data.columns)
    data_fcasts0['US Gas CDD actuals'] = fcasts0['NG_CDD'].values
    hdd0 = pd.concat([data.loc[:fcasts0['DATES'].iloc[0] - dt.timedelta(days=1), :], data_fcasts0], axis=0)
    start_loc = hdd0.index.get_loc(hdd0['US Power demand actuals'].last_valid_index()) - len(hdd0) + 1
    fcasts0_fit = us_weather_hdd_model(hdd0['US Power demand actuals'], hdd0['US Gas CDD actuals'], start=start_loc,
                                     hol=hol, forecast=0)
    fcasts0['Demand'] = fcasts0_fit[fcasts0['DATES']].values
    return fcasts0


def get_demand_forecast_hdd(fcasts0, data, hol=None):
    data_fcasts0 = pd.DataFrame(np.nan, index=fcasts0['DATES'], columns=data.columns)
    data_fcasts0['US Gas HDD actuals'] = fcasts0['NG_HDD'].values
    hdd0 = pd.concat([data.loc[:fcasts0['DATES'].iloc[0] - dt.timedelta(days=1), :], data_fcasts0], axis=0)
    start_loc = hdd0.index.get_loc(hdd0['US ResCom demand actuals'].last_valid_index()) - len(hdd0) + 1
    fcasts0_fit = us_weather_hdd_model(hdd0['US ResCom demand actuals'], hdd0['US Gas HDD actuals'], start=start_loc,
                                     hol=hol, forecast=0)
    fcasts0['Demand'] = fcasts0_fit[fcasts0['DATES']].values
    return fcasts0


def get_chart_old(data, title=None, **kwargs):
    y_axis_title = kwargs.get('y_axis_title', None)
    x_axis_title = kwargs.get('x_axis_title', None)
    file_path = kwargs.get('file_path', None)
    data1 = kwargs.get('data1', None)
    data2 = kwargs.get('data2', None)

    if data1 is None and data2 is None:
        fig = go.Figure()
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart_old original line 563: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart_old original line 571: clipped line style')))
        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    elif data1 is not None and data2 is None:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart_old original line 584: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart_old original line 592: clipped line style')))
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                     line=dict(width=2)), secondary_y=True)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                         line=dict(width=2)), secondary_y=True)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    else:
        fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True,
                            vertical_spacing=_unrecovered('IMG_4908 original line 609: subplot spacing'),
                            specs=[[{"secondary_y": True}], [{"secondary_y": True}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart_old original line 614: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart_old original line 622: clipped line style')))
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                     line=dict(width=2)), secondary_y=True)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                         line=dict(width=2)), secondary_y=True)

        if len(data2.columns) == 1:
            fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, 0], showlegend=True, name=data2.columns[0],
                                     line=dict(width=2)), row=2, col=1)
        else:
            for j in range(len(data2.columns)):
                fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, j], showlegend=True, name=data2.columns[j],
                                         line=dict(width=2)), row=2, col=1)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)

    if file_path is not None:
        py.offline.plot(fig, auto_open=False, filename=file_path)
    return fig


def get_chart(data, title=None, **kwargs):
    y_axis_title = kwargs.get('y_axis_title', None)
    x_axis_title = kwargs.get('x_axis_title', None)
    file_path = kwargs.get('file_path', None)
    data1 = kwargs.get('data1', None)
    data2 = kwargs.get('data2', None)

    if data1 is None and data2 is None:
        fig = go.Figure()
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 664: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 672: clipped line style')))
        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    elif data1 is not None and data2 is None:
        fig = make_subplots(rows=3, cols=1, row_heights=[0.67, 0.33], shared_xaxes=True,
                            vertical_spacing=_unrecovered('IMG_4909 original line 682: subplot spacing'),
                            specs=[[{"secondary_y": False}], [{"secondary_y": False}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 687: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 695: clipped line style')))
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                     line=dict(width=2)), row=2, col=1)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                         line=dict(width=2)), row=2, col=1)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    else:
        fig = make_subplots(rows=3, cols=1, row_heights=[0.5, 0.25, 0.25], shared_xaxes=True,
                            vertical_spacing=_unrecovered('IMG_4909 original line 712: subplot spacing'),
                            specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 717: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 725: clipped line style')))
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                     line=dict(width=2)), row=2, col=1)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                         line=dict(width=2)), row=2, col=1)

        if len(data2.columns) == 1:
            fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, 0], showlegend=True, name=data2.columns[0],
                                     line=dict(width=2)), row=3, col=1)
        else:
            for j in range(len(data2.columns)):
                fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, j], showlegend=True, name=data2.columns[j],
                                         line=dict(width=2)), row=3, col=1)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=800)

    if file_path is not None:
        py.offline.plot(fig, auto_open=False, filename=file_path)
    return fig


def current_month_hdd_forecast():
    """
    For current month from CWG : to use to for current  month 10Y HDD, Y-1 HDD
    """
    dfnew = pd.read_sql("select * from [dbo].[CWG_BALANCE_OF_MONTH]", engine)
    dfnew = dfnew.sort_values(by=['AS_OF_DATE'])
    dfnew = dfnew.drop_duplicates()

    xlatest = dfnew.iloc[-10:]
    xlatest = xlatest.rename(columns={"National": "Fcast", "10Y": "Normal"})
    xlatest.drop('30Y', axis=1, inplace=True)
    xlatest = xlatest.set_index('AS_OF_DATE')
    xlatest.index = pd.to_datetime(xlatest.index)
    delat = xlatest
    delat['Fcast'] = delat['Fcast'].astype(str).astype(float).round()
    delat['Last Year'] = delat['Last Year'].astype(str).astype(float).round()
    delat['Normal'] = delat['Normal'].astype(str).astype(float).round()
    delat.sort_index(ascending=False, inplace=True)
    delat.index = delat.index.strftime('%Y-%m-%d')
    delat = delat.reset_index()
    return delat


def next_hdd_forecast():
    """
    For next month from CWG : to use to for next month 10Y HDD, Y-1 HDD
    """
    dfnext = pd.read_sql("select * from [dbo].[CWG_BALANCE_OF_NEXT_MONTH]", engine)
    dfnext = dfnext.sort_values(by=['AS_OF_DATE'])
    dfnext = dfnext.drop_duplicates()
    dfnext = dfnext.rename(columns={"National": "Fcast", "10Y": "Normal"})
    dfnext.drop('30Y', axis=1, inplace=True)
    dfnext['Fcast'] = dfnext['Fcast'].astype(str).astype(float).round()
    dfnext['Last Year'] = dfnext['Last Year'].astype(str).astype(float).round()
    dfnext['Normal'] = dfnext['Normal'].astype(str).astype(float).round()
    dfnext = dfnext.set_index('AS_OF_DATE')
    dfnext.index = dfnext.index.strftime('%Y-%m-%d')
    dfnext = dfnext.reset_index()
    return dfnext


def monthly_cdd_forecast(data, fcasts, m, y, data_normal, bbg_fcast, region):
    fdom = dt.datetime(y, m, 1)
    dts = pd.date_range(start=fdom, end=fdom + relativedelta(day=31))
    out_dts = []
    fcast_date = np.sort(fcasts['AS_OF_DATE'].unique())
    for d in fcast_date:
        fcasts0 = fcasts.loc[fcasts['AS_OF_DATE'] == d, :]
        if len(list(set(fcasts0['DATES']).intersection(dts))) > 0:
            out_dts.append(d)

    out_df = pd.DataFrame(np.nan, index=out_dts,
                          columns=['BBG Fcast', 'BBG Normal', 'CWG Fcast', 'CWG Normal', 'Last Year'])
    for d in out_dts:
        fcasts0 = fcasts.loc[fcasts['AS_OF_DATE'] == d, :].sort_values('DATES')
        hdd0 = fcasts0
        hdd0.set_index('DATES', inplace=True)
        df = pd.Series(np.nan, index=dts)
        if hdd0.index[0] <= dts[0]:
            df[:hdd0.index[-1]] = hdd0.loc[dts[0]:, 'NG_CDD']
            df[hdd0.index[-1] + dt.timedelta(days=1):] = data_normal[hdd0.index[-1] + dt.timedelta(days=1):]
        elif hdd0.index[-1] < dts[-1]:
            df[:hdd0.index[0] - dt.timedelta(days=1)] = data.loc[dts[0]:hdd0.index[0] - dt.timedelta(days=1),
                                                              f'US {region} CDD']
            df[hdd0.index[0]: hdd0.index[-1]] = hdd0['NG_CDD']
            df[hdd0.index[-1] + dt.timedelta(days=1):] = data_normal[hdd0.index[-1] + dt.timedelta(days=1):]
        else:
            df[:hdd0.index[0] - dt.timedelta(days=1)] = data.loc[dts[0]:hdd0.index[0] - dt.timedelta(days=1),
                                                              f'US {region} CDD']
            df[hdd0.index[0]:] = hdd0.loc[:dts[-1], 'NG_CDD']
        out_df.loc[d, 'BBG Fcast'] = df.sum()
        out_df.loc[d, 'Last Year'] = data.loc[
            (data.index.year == y - 1) & (data.index.month == m), f'US {region} CDD'].sum()

    if region == 'Total':
        dfnew_cdd = sql.read_sql(
            "select * from [dbo].[CWG_BALANCE_OF_MONTH_CDD] order by FCAST_MONTH, AS_OF_DATE")
        dfnew_cdd = dfnew_cdd.drop_duplicates()
        dfnew_cdd.loc[:, 'National'] = dfnew_cdd['National'].astype(float)
        dfnew_cdd.loc[:, 'Last Year'] = dfnew_cdd['Last Year'].astype(float)
        dfnew_cdd.loc[:, '30Y'] = dfnew_cdd['30Y'].astype(float)
        dfnew_cdd.loc[:, '10Y'] = dfnew_cdd['10Y'].astype(float)
        dfnew_cdd.loc[:, 'AS_OF_DATE'] = pd.to_datetime(dfnew_cdd['AS_OF_DATE'])
        dfnew_cdd.loc[:, 'FCAST_MONTH'] = pd.to_datetime(dfnew_cdd['FCAST_MONTH'])
    else:
        dfnew_cdd = sql.read_sql(
            "select * from [dbo].[CWG_BALANCE_OF_MONTH_CDD_Region] order by FCAST_MONTH, AS_OF_DATE")
        dfnew_cdd = dfnew_cdd.loc[dfnew_cdd['REGION_NAME'] == region, :]
        dfnew_cdd = dfnew_cdd.drop_duplicates()
        dfnew_cdd.loc[:, 'National'] = dfnew_cdd['National'].astype(float)
        dfnew_cdd.loc[:, 'Last Year'] = dfnew_cdd['Last Year'].astype(float)
        dfnew_cdd.loc[:, '30Y'] = dfnew_cdd['30Y'].astype(float)
        dfnew_cdd.loc[:, '10Y'] = dfnew_cdd['10Y'].astype(float)
        dfnew_cdd.loc[:, 'AS_OF_DATE'] = pd.to_datetime(dfnew_cdd['AS_OF_DATE'])
        dfnew_cdd.loc[:, 'FCAST_MONTH'] = pd.to_datetime(dfnew_cdd['FCAST_MONTH'])
    dfnew = dfnew_cdd.copy()
    for i in dfnew_cdd['FCAST_MONTH'].unique():
        dfnew_cdd_month = dfnew_cdd.loc[dfnew_cdd['FCAST_MONTH'] == i, :].set_index('AS_OF_DATE')
        dfnew.loc[dfnew['FCAST_MONTH'] == i, 'National'] = (dfnew_cdd_month['National']).values
        dfnew.loc[dfnew['FCAST_MONTH'] == i, 'Last Year'] = (dfnew_cdd_month['Last Year']).values
        dfnew.loc[dfnew['FCAST_MONTH'] == i, '30Y'] = (dfnew_cdd_month['30Y']).values
        dfnew.loc[dfnew['FCAST_MONTH'] == i, '10Y'] = (dfnew_cdd_month['10Y']).values
    xlatest = dfnew.rename(columns={"National": "Fcast", "10Y": "Normal"})
    xlatest.drop('30Y', axis=1, inplace=True)
    xlatest = xlatest.set_index('AS_OF_DATE')
    xlatest.index = pd.to_datetime(xlatest.index)
    xlatest['FCAST_MONTH'] = pd.to_datetime(xlatest['FCAST_MONTH'])

    if region == 'Total':
        dfnext_cdd = sql.read_sql(
            "select * from [dbo].[CWG_BALANCE_OF_NEXT_MONTH_CDD] order by FCAST_MONTH, AS_OF_DATE")
        dfnext_cdd = dfnext_cdd.drop_duplicates()
        dfnext_cdd.loc[:, 'National'] = dfnext_cdd['National'].astype(float)
        dfnext_cdd.loc[:, 'Last Year'] = dfnext_cdd['Last Year'].astype(float)
        dfnext_cdd.loc[:, '30Y'] = dfnext_cdd['30Y'].astype(float)
        dfnext_cdd.loc[:, '10Y'] = dfnext_cdd['10Y'].astype(float)
        dfnext_cdd.loc[:, 'AS_OF_DATE'] = pd.to_datetime(dfnext_cdd['AS_OF_DATE'])
        dfnext_cdd.loc[:, 'FCAST_MONTH'] = pd.to_datetime(dfnext_cdd['FCAST_MONTH'])
    else:
        dfnext_cdd = sql.read_sql(
            "select * from [dbo].[CWG_BALANCE_OF_NEXT_MONTH_CDD_Region] order by FCAST_MONTH, AS_OF_DATE")
        dfnext_cdd = dfnext_cdd.loc[dfnext_cdd['REGION_NAME'] == region, :]
        dfnext_cdd = dfnext_cdd.drop_duplicates()
        dfnext_cdd.loc[:, 'National'] = dfnext_cdd['National'].astype(float)
        dfnext_cdd.loc[:, 'Last Year'] = dfnext_cdd['Last Year'].astype(float)
        dfnext_cdd.loc[:, '30Y'] = dfnext_cdd['30Y'].astype(float)
        dfnext_cdd.loc[:, '10Y'] = dfnext_cdd['10Y'].astype(float)
        dfnext_cdd.loc[:, 'AS_OF_DATE'] = pd.to_datetime(dfnext_cdd['AS_OF_DATE'])
        dfnext_cdd.loc[:, 'FCAST_MONTH'] = pd.to_datetime(dfnext_cdd['FCAST_MONTH'])
    dfnext = dfnext_cdd.copy()
    for i in dfnext_cdd['FCAST_MONTH'].unique():
        dfnext_cdd_month = dfnext_cdd.loc[dfnext_cdd['FCAST_MONTH'] == i, :].set_index('AS_OF_DATE')
        dfnext.loc[dfnext['FCAST_MONTH'] == i, 'National'] = (dfnext_cdd_month['National']).values
        dfnext.loc[dfnext['FCAST_MONTH'] == i, 'Last Year'] = (dfnext_cdd_month['Last Year']).values
        dfnext.loc[dfnext['FCAST_MONTH'] == i, '30Y'] = (dfnext_cdd_month['30Y']).values
        dfnext.loc[dfnext['FCAST_MONTH'] == i, '10Y'] = (dfnext_cdd_month['10Y']).values
    xlatest1 = dfnext.rename(columns={"National": "Fcast", "10Y": "Normal"})
    xlatest1.drop('30Y', axis=1, inplace=True)
    xlatest1 = xlatest1.set_index('AS_OF_DATE')
    xlatest1.index = pd.to_datetime(xlatest1.index)
    xlatest1['FCAST_MONTH'] = pd.to_datetime(xlatest1['FCAST_MONTH'])

    xlatest = pd.concat([xlatest1[:dts[0] - dt.timedelta(days=1)], xlatest[dts[0]:]], axis=0)

    out_df.loc[:, 'BBG Normal'] = data_normal.sum()
    out_df.loc[:, 'CWG Normal'] = float(xlatest.loc[xlatest['FCAST_MONTH'] == dts[0], 'Normal'][0])
    out_df.loc[:, 'FCAST_MONTH'] = dt.datetime.strftime(fdom, '%Y-%m-%d')
    out_df.loc[:, 'BBG Fcast'] = bbg_fcast[np.intersect1d(out_df.index, bbg_fcast.index)]
    out_df.loc[:, 'CWG Fcast'] = xlatest['Fcast'].astype(float).round()
    out_df.index = out_df.index.strftime('%Y-%m-%d')
    out_df.index.name = 'AS_OF_DATE'
    out_df.sort_index(ascending=False, inplace=True)
    out_df.reset_index(inplace=True)
    return out_df


def winter_hdd(a_df, winsum):
    """
    historical and 10Y normal daily HDDs from CWG
    """

    season = a_df.copy()

    season['month'] = season.index.month
    season['year'] = season.index.year
    season['day'] = season.index.day


    season.loc[(season['month'] >= 4), 'Season'] = 'S'
    season.loc[(season['month'] >= 10) | (season['month'] <= 3), 'Season'] = 'W'


    season.loc[(season['month'] >= 4), 'Syr'] = (season['year']).astype(str)
    season.loc[(season['month'] < 4), 'Syr'] = (season['year'] - 1).astype(str)
    season['Season_year'] = season['Season'] + season['Syr'].astype(str)

    season['Month_year'] = season['month'].astype(str) + "-" + season['year'].astype(str)

    season['Actuals_vs_Normal'] = season['NG_CDD'] - season['10Y_NG_CDD']

    season['Cumulative'] = season.groupby('Season_year')['NG_CDD'].cumsum()

    season['Cumulative of Actual_vs_Normal per season'] = season.groupby('Season_year')['Actuals_vs_Normal'].cumsum()

    season['day_count'] = season.groupby('Season_year').cumcount() + 1

    season['Cumulative of Actual_vs_Normal per month'] = season.groupby(['year', 'month'])['Actuals_vs_Normal'].cumsum()

    season['Cumulative_monthly'] = season.groupby(['year', 'month'])['NG_CDD'].cumsum()

    winter = season.loc[(season['Season'] == winsum) & (season.index >= '2010-10-01')]
    return winter


def cumulative_hdd_chart(winter, hdd_df, title='Cumulative CDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    base_date = hdd_df.index[0] - dt.timedelta(days=1)
    if base_date.month >= 9:
        date_idx = pd.date_range(dt.datetime(base_date.year, 10, 1), dt.datetime(base_date.year + 1, 3, 31))
    elif base_date.month < 4:
        date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 3, 31))
    if len(date_idx) < len(winterpvt2_email):
        winterpvt2_email = winterpvt2_email.iloc[:-1, :]
    winterpvt2_email['dates'] = date_idx
    winterpvt2_email.set_index('dates', inplace=True)

    dataPanda6 = []

    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color=_unrecovered('IMG_4914 original line 997: color')))
            dataPanda6.append(trace)
        elif j == len(winterpvt2_email.columns) - 1:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color='black', dash='dash'))
            dataPanda6.append(trace)
        else:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines')
            dataPanda6.append(trace)

    layout6 = go.Layout(title=title, width=900, height=600)
    fig6 = go.Figure(data=dataPanda6, layout=layout6)
    return fig6


def cumulative_cdd_chart(winter, hdd_df, title='Cumulative CDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    base_date = hdd_df.index[0] - dt.timedelta(days=1)
    date_idx = pd.date_range(dt.datetime(base_date.year, 4, 1), dt.datetime(base_date.year, 9, 30))
    if len(date_idx) < len(winterpvt2_email):
        winterpvt2_email = winterpvt2_email.iloc[:-1, :]
    winterpvt2_email['dates'] = date_idx
    winterpvt2_email.set_index('dates', inplace=True)

    dataPanda6 = []

    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color=_unrecovered('IMG_4915 original line 1043: color')))
            dataPanda6.append(trace)
        elif j == len(winterpvt2_email.columns) - 1:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color='black', dash='dash'))
            dataPanda6.append(trace)
        else:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines')
            dataPanda6.append(trace)

    layout6 = go.Layout(title=title, width=900, height=600)
    fig6 = go.Figure(data=dataPanda6, layout=layout6)
    return fig6


def witer_month_table(winter, winsum='W'):
    'HDD vs 10Y normal by month for each winter'
    df_eom2 = winter[['Actuals_vs_Normal']]

    df_eom2 = df_eom2.resample("MS").sum()
    df_eom2['month'] = df_eom2.index.month
    df_eom2['year'] = df_eom2.index.year


    df_eom2.loc[(df_eom2['month'] >= 4), 'Season'] = 'S'
    df_eom2.loc[(df_eom2['month'] >= 10) | (df_eom2['month'] <= 3), 'Season'] = 'W'
    df_eom2.loc[(df_eom2['month'] >= 4), 'Syr'] = (df_eom2['year']).astype(str)
    df_eom2.loc[(df_eom2['month'] < 4), 'Syr'] = (df_eom2['year'] - 1).astype(str)
    df_eom2['Season_year'] = df_eom2['Season'] + df_eom2['Syr'].astype(str)

    df_eom2_winter = df_eom2.loc[(df_eom2['Season'] == winsum) & (df_eom2.index >= '2016-10-01')]

    df_eom2_winter['Actuals_vs_Normal'] = df_eom2_winter['Actuals_vs_Normal'].astype('float')

    df_eom2_winterpvt = pd.pivot_table(df_eom2_winter, columns=['Season_year'], index=['month'],
                                      values='Actuals_vs_Normal')

    if winsum == 'W':
        df_eom2_winterpvt = df_eom2_winterpvt.reindex([10, 11, 12, 1, 2, 3])
        df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
        df_eom2_winterpvt.insert(loc=0, column='month', value=['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Total'])
    elif winsum == 'S':
        df_eom2_winterpvt = df_eom2_winterpvt.reindex([4, 5, 6, 7, 8, 9])
        df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
        df_eom2_winterpvt.insert(loc=0, column='month', value=['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Total'])

    df_eom2_winterpvt.index.name = None
    df_eom2_winterpvt.columns.name = None
    df_eom2_winterpvt.reset_index(drop=True, inplace=True)
    return df_eom2_winterpvt


def send_us_cdd(send_to=send_to):
    tbs = []
    tbs1 = []

    data, bbg_normal = get_rescom_region_cwg()
    data_hdd, bbg_normal_hdd = get_rescom_region_cwg_hdd()

    bbg_normal_total_cdd = bbg.bdh('TENYCNEC Index', ['PX_LAST'], sdate=dt.datetime(2009, 1, 1),
                                  edate=today() + dt.timedelta(days=364 * 2))
    bbg_normal_sc_cdd = bbg.bdh('TENYSECC Index', ['PX_LAST'], sdate=dt.datetime(2009, 1, 1),
                               edate=today() + dt.timedelta(days=364 * 2))
    bbg_normal_east_cdd = bbg.bdh('TENYESEC Index', ['PX_LAST'], sdate=dt.datetime(2009, 1, 1),
                                 edate=today() + dt.timedelta(days=364 * 2))
    bbg_normal_cdd = pd.concat([bbg_normal_total_cdd, bbg_normal_sc_cdd, bbg_normal_east_cdd], axis=1)
    bbg_normal_cdd.columns = ['US Total CDD', 'US South Central CDD', 'US East CDD']

    bbg_normal_ = bbg_normal_cdd

    hdd_df, hdd_5d = demand_forecast_region(data, bbg_normal, region='Total')
    hdd_df_sc, hdd_sc_5d = demand_forecast_region(data, bbg_normal, region='South Central')
    hdd_df_east, hdd_east_5d = demand_forecast_region(data, bbg_normal, region='East')

    try:
        hdd_df.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_latest.xlsx"))
    except:
        pass

    try:
        hdd_df_sc.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_latest_sc.xlsx"))
    except:
        pass

    try:
        hdd_df_east.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_latest_east.xlsx"))
    except:
        pass

    table_hdd = pd.DataFrame(0, index=['1D', '3D', '5D', 'FRI'], columns=['US Total', 'South Central', 'East'])
    last_fri = today() - BDay(1) + relativedelta(weekday=FR(-1))
    if last_fri in [dt.datetime(2025, 4, 18), dt.datetime(2025, 7, 4)]:
        last_fri = last_fri - dt.timedelta(days=1)
    table_hdd.loc['1D', 'US Total'] = (hdd_5d.iloc[:, 0] - hdd_5d.iloc[:, 1]).sum()
    table_hdd.loc['3D', 'US Total'] = (hdd_5d.iloc[:, 0] - hdd_5d.iloc[:, 3]).sum()
    table_hdd.loc['5D', 'US Total'] = (hdd_5d.iloc[:, 0] - hdd_5d.iloc[:, 5]).sum()
    table_hdd.loc['FRI', 'US Total'] = (hdd_5d.iloc[:, 0] - hdd_5d.loc[:, last_fri]).sum()
    table_hdd.loc['1D', 'South Central'] = (hdd_sc_5d.iloc[:, 0] - hdd_sc_5d.iloc[:, 1]).sum()
    table_hdd.loc['3D', 'South Central'] = (hdd_sc_5d.iloc[:, 0] - hdd_sc_5d.iloc[:, 3]).sum()
    table_hdd.loc['5D', 'South Central'] = (hdd_sc_5d.iloc[:, 0] - hdd_sc_5d.iloc[:, 5]).sum()
    table_hdd.loc['FRI', 'South Central'] = (hdd_sc_5d.iloc[:, 0] - hdd_sc_5d.loc[:, last_fri]).sum()
    table_hdd.loc['1D', 'East'] = (hdd_east_5d.iloc[:, 0] - hdd_east_5d.iloc[:, 1]).sum()
    table_hdd.loc['3D', 'East'] = (hdd_east_5d.iloc[:, 0] - hdd_east_5d.iloc[:, 3]).sum()
    table_hdd.loc['5D', 'East'] = (hdd_east_5d.iloc[:, 0] - hdd_east_5d.iloc[:, 5]).sum()
    table_hdd.loc['FRI', 'East'] = (hdd_east_5d.iloc[:, 0] - hdd_east_5d.loc[:, last_fri]).sum()

    table_hdd.index.name = 'Change'
    table_hdd.reset_index(inplace=True)
    table1 = table.html_format(table_hdd, precision=1,
                               format_column={'Change': {'width': '100px', 'text-align': 'center'},
                                              'US Total': {'width': '100px', 'text-align': 'center'},
                                              'South Central': {'width': '100px', 'text-align': 'center'},
                                              'East': {'width': '100px', 'text-align': 'center'},
                                              })

    actual_hdd = (data.loc[today() - dt.timedelta(days=35):, 'US Total CDD']).to_frame("Actual")
    hdd_df = pd.concat([hdd_df, actual_hdd], axis=1)
    current_date_ = dt.datetime.strptime(hdd_df.columns[0], '%Y-%m-%d')
    current_month_ = current_date_.month
    current_year_ = current_date_.year
    next_month_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).month
    next_year_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).year
    ticker1_cdd = 'CECEM ' + month_int2str[current_month_] + str(current_year_)[-2:] + ' Index'
    ticker = [ticker1_cdd]
    if current_date_.day > 15:
        ticker2_cdd = 'CECEM ' + month_int2str[next_month_] + str(next_year_)[-2:] + ' Index'
        ticker.append(ticker2_cdd)
    bbg_tdd = bbg.bdh(ticker, ['PX_LAST'], sdate=today() - dt.timedelta(days=35), edate=today())
    if len(ticker) > 1:
        bbg_tdd2 = (bbg_tdd[ticker2_cdd]).to_frame(
            month_int2str[next_month_] + str(next_year_)[-2:])
        bbg_tdd1 = (bbg_tdd[ticker1_cdd]).to_frame(
            month_int2str[current_month_] + str(current_year_)[-2:])
    else:
        if ticker1_cdd in bbg_tdd.columns:
            idx_col = ticker1_cdd
        else:
            idx_col = "PX_LAST"
        bbg_tdd1 = (bbg_tdd[idx_col]).to_frame(
            month_int2str[current_month_] + str(current_year_)[-2:])

    tbs.append('Lastest forecast is on {:s}'.format(hdd_df.columns[0]))
    tbs.append('<br><br>')
    tbs.append('CDD forecast DoD changes (using CWG data):')
    tbs.append(table1)
    tbs.append('<br>')

    tbs.append('StormVista table (ECMWF-EPS):')
    sv_hdd = pd.read_csv(convert_path_to_linux(f"{weather_csv}\\us_cdd_stormvista.csv"))
    tbs.append(table.html_format(sv_hdd, precision=1,
                                 format_column={tuple(sv_hdd.columns): {'width': '100px', 'text-align': 'center'},
                                                sv_hdd.columns[-2]: {'width': '100px', 'text-align': 'center',
                                                                     'format': '{:.1%}'},
                                                sv_hdd.columns[-1]: {'width': '100px', 'text-align': 'center',
                                                                     'format': '{:.1%}'}}
                                 ))
    tbs.append('<br>')

    current_date = dt.datetime.strptime(hdd_df.columns[0], '%Y-%m-%d')
    current_month = current_date.month
    current_year = current_date.year
    next_month = (current_date + relativedelta(day=31) + relativedelta(days=1)).month
    next_year = (current_date + relativedelta(day=31) + relativedelta(days=1)).year

    data_normal = bbg_normal_[(bbg_normal_.index.month == current_month) & (bbg_normal_.index.year == current_year)]
    fcasts_total = get_forecast_cdd_region(region='Total')
    fcasts_sc = get_forecast_cdd_region(region='South Central')
    fcasts_east = get_forecast_cdd_region(region='East')

    this_month_hdd_forecast = monthly_cdd_forecast(data, fcasts_total, current_month, current_year,
                                                  data_normal['US Total CDD'],
                                                  bbg_tdd1[month_int2str[current_month_] + str(current_year_)[-2:]],
                                                  region='Total')
    front_ticker = (bbg.live_contract(active="NGA Comdty"))["ticker"]
    front_price = bbg.bdh(front_ticker, ['PX_LAST'],
                          sdate=dt.datetime.strptime(this_month_hdd_forecast['AS_OF_DATE'].iloc[-1], '%Y-%m-%d'),
                          edate=dt.datetime.strptime(this_month_hdd_forecast['AS_OF_DATE'].iloc[0], '%Y-%m-%d'),
                          elms=[('nonTradingDayFillOption', 'ALL_CALENDAR_DAYS'),
                                ('nonTradingDayFillMethod', 'PREVIOUS_VALUE')])
    front_price = front_price.reindex(pd.to_datetime(this_month_hdd_forecast['AS_OF_DATE']))
    this_month_hdd_forecast.insert(1, 'Price', front_price['PX_LAST'].values)
    this_month_hdd_forecast_html = table.html_format(this_month_hdd_forecast, background_color='lightyellow',
                                                     precision=0,
                                                     format_column={
                                                         'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                                                         'Price': {'width': '100px', 'text-align': 'center',
                                                                   'format': '{:.3f}'},
                                                         'BBG Fcast': {'width': '80px', 'text-align': 'center'},
                                                         'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                                                         'Last Year': {'width': '80px', 'text-align': 'center'},
                                                         'BBG Normal': {'width': '80px', 'text-align': 'center'},
                                                         'CWG Normal': {'width': '80px', 'text-align': 'center'},
                                                         'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})

    ticker_cdd = 'SECEM ' + month_int2str[current_month] + str(current_year)[-2:] + ' Index'
    this_month_data_sc = bbg.bdh([ticker_cdd], ['PX_LAST'], sdate=today() - dt.timedelta(days=56),
                                edate=today()).sum(axis=1)
    this_month_hdd_forecast_sc = monthly_cdd_forecast(data, fcasts_sc, current_month, current_year,
                                                     data_normal['US South Central CDD'], this_month_data_sc,
                                                     region='South Central')
    front_price = front_price.reindex(pd.to_datetime(this_month_hdd_forecast_sc['AS_OF_DATE']))
    this_month_hdd_forecast_sc.insert(1, 'Price', front_price['PX_LAST'].values)
    this_month_hdd_forecast_sc_html = table.html_format(this_month_hdd_forecast_sc, background_color='lightyellow',
                                                     precision=0,
                                                     format_column={
                                                         'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                                                         'Price': {'width': '100px', 'text-align': 'center',
                                                                   'format': '{:.3f}'},
                                                         'BBG Fcast': {'width': '80px', 'text-align': 'center'},
                                                         'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                                                         'Last Year': {'width': '80px', 'text-align': 'center'},
                                                         'BBG Normal': {'width': '80px', 'text-align': 'center'},
                                                         'CWG Normal': {'width': '80px', 'text-align': 'center'},
                                                         'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})

    tbs1.append('Current Month - South Central CDD forecast')
    tbs1.append(this_month_hdd_forecast_sc_html)
    tbs1.append('<br>')

    ticker_cdd = 'EECEM ' + month_int2str[current_month] + str(current_year)[-2:] + ' Index'
    this_month_data_east = bbg.bdh([ticker_cdd], ['PX_LAST'], sdate=today() - dt.timedelta(days=56),
                                edate=today()).sum(axis=1)
    this_month_hdd_forecast_east = monthly_cdd_forecast(data, fcasts_east, current_month, current_year,
                                                     data_normal['US East CDD'], this_month_data_east,
                                                     region='East')
    front_price = front_price.reindex(pd.to_datetime(this_month_hdd_forecast_east['AS_OF_DATE']))
    this_month_hdd_forecast_east.insert(1, 'Price', front_price['PX_LAST'].values)
    this_month_hdd_forecast_east_html = table.html_format(this_month_hdd_forecast_east, background_color='lightyellow',
                                                     precision=0,
                                                     format_column={
                                                         'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                                                         'Price': {'width': '100px', 'text-align': 'center',
                                                                   'format': '{:.3f}'},
                                                         'BBG Fcast': {'width': '80px', 'text-align': 'center'},
                                                         'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                                                         'Last Year': {'width': '80px', 'text-align': 'center'},
                                                         'BBG Normal': {'width': '80px', 'text-align': 'center'},
                                                         'CWG Normal': {'width': '80px', 'text-align': 'center'},
                                                         'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})

    tbs1.append('Current Month - East CDD forecast')
    tbs1.append(this_month_hdd_forecast_east_html)
    tbs1.append('<br>')

    show_next_month = False
    if hdd_df.index[-1].month == next_month and (today() >= _unrecovered('IMG_4919 original line 1308: threshold after dt.datetime(current_year, current_month, 1) +')):
        data_normal = bbg_normal_[(bbg_normal_.index.month == next_month) & (bbg_normal_.index.year == next_year)]

        next_month_hdd_forecast = monthly_cdd_forecast(data, fcasts_total, next_month, next_year,
                                                       data_normal['US Total CDD'],
                                                       bbg_tdd2[month_int2str[next_month_] + str(next_year_)[-2:]],
                                                       region='Total')
        second_ticker = (bbg.live_contract(active="NGA Comdty", seq=1))["ticker"]
        second_price = bbg.bdh(second_ticker, ['PX_LAST'],
                               sdate=dt.datetime.strptime(next_month_hdd_forecast['AS_OF_DATE'].iloc[-1], '%Y-%m-%d'),
                               edate=dt.datetime.strptime(next_month_hdd_forecast['AS_OF_DATE'].iloc[0], '%Y-%m-%d'),
                               elms=[('nonTradingDayFillOption', 'ALL_CALENDAR_DAYS'),
                                     ('nonTradingDayFillMethod', 'PREVIOUS_VALUE')])
        second_price = second_price.reindex(pd.to_datetime(next_month_hdd_forecast['AS_OF_DATE']))
        next_month_hdd_forecast.insert(1, 'Price', second_price['PX_LAST'].values)
        show_next_month = True
        next_month_hdd_forecast_html = table.html_format(next_month_hdd_forecast, background_color='lightgreen',
                                                         precision=0,
                                                         format_column={
                                                             'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                                                             'Price': {'width': '100px', 'text-align': 'center',
                                                                       'format': '{:.3f}'},
                                                             'BBG Fcast': {'width': '80px', 'text-align': 'center'},
                                                             'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                                                             'Last Year': {'width': '80px', 'text-align': 'center'},
                                                             'BBG Normal': {'width': '80px', 'text-align': 'center'},
                                                             'CWG Normal': {'width': '80px', 'text-align': 'center'},
                                                             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})

        ticker_cdd = 'SECEM ' + month_int2str[next_month] + str(next_year)[-2:] + ' Index'
        next_month_data_sc = bbg.bdh([ticker_cdd], ['PX_LAST'], sdate=today() - dt.timedelta(days=56),
                                           edate=today()).sum(axis=1)
        next_month_hdd_forecast_sc = monthly_cdd_forecast(data, fcasts_sc, next_month, next_year,
                                                               data_normal['US South Central CDD'], next_month_data_sc,
                                                               region='South Central')
        second_price = second_price.reindex(pd.to_datetime(next_month_hdd_forecast_sc['AS_OF_DATE']))
        next_month_hdd_forecast_sc.insert(1, 'Price', second_price['PX_LAST'].values)
        next_month_hdd_forecast_sc_html = table.html_format(next_month_hdd_forecast_sc, background_color='lightgreen',
                                                         precision=0,
                                                         format_column={
                                                             'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                                                             'Price': {'width': '100px', 'text-align': 'center',
                                                                       'format': '{:.3f}'},
                                                             'BBG Fcast': {'width': '80px', 'text-align': 'center'},
                                                             'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                                                             'Last Year': {'width': '80px', 'text-align': 'center'},
                                                             'CWG Normal': {'width': '80px', 'text-align': 'center'},
                                                             'BBG Normal': {'width': '80px', 'text-align': 'center'},
                                                             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})
        tbs1.append('Next Month - South Central CDD forecast')
        tbs1.append(next_month_hdd_forecast_sc_html)
        tbs1.append('<br>')

        ticker_cdd = 'EECEM ' + month_int2str[next_month] + str(next_year)[-2:] + ' Index'
        next_month_data_east = bbg.bdh([ticker_cdd], ['PX_LAST'], sdate=today() - dt.timedelta(days=56),
                                           edate=today()).sum(axis=1)
        next_month_hdd_forecast_east = monthly_cdd_forecast(data, fcasts_east, next_month, next_year,
                                                               data_normal['US East CDD'], next_month_data_east,
                                                               region='East')
        second_price = second_price.reindex(pd.to_datetime(next_month_hdd_forecast_east['AS_OF_DATE']))
        next_month_hdd_forecast_east.insert(1, 'Price', second_price['PX_LAST'].values)
        next_month_hdd_forecast_east_html = table.html_format(next_month_hdd_forecast_east, background_color='lightgreen',
                                                         precision=0,
                                                         format_column={
                                                             'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                                                             'Price': {'width': '100px', 'text-align': 'center',
                                                                       'format': '{:.3f}'},
                                                             'BBG Fcast': {'width': '80px', 'text-align': 'center'},
                                                             'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                                                             'Last Year': {'width': '80px', 'text-align': 'center'},
                                                             'CWG Normal': {'width': '80px', 'text-align': 'center'},
                                                             'BBG Normal': {'width': '80px', 'text-align': 'center'},
                                                             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})
        tbs1.append('Next Month - East CDD forecast')
        tbs1.append(next_month_hdd_forecast_east_html)
        tbs1.append('<br>')
        tbs1.append('<br>')
    cwg_tdd = this_month_hdd_forecast[["AS_OF_DATE", "CWG Fcast"]]
    cwg_tdd.set_index("AS_OF_DATE", inplace=True)
    cwg_tdd.index = pd.to_datetime(cwg_tdd.index)
    cwg_tdd.columns = ["CWG " + bbg_tdd1.columns[0]]
    cwg_tdd = cwg_tdd.reindex(bbg_tdd1.index).fillna(method="ffill")
    if len(ticker) > 1 and 'next_month_hdd_forecast' in locals():
        cwg_tdd1 = next_month_hdd_forecast[["AS_OF_DATE", "CWG Fcast"]]
        cwg_tdd1.set_index("AS_OF_DATE", inplace=True)
        cwg_tdd1.index = pd.to_datetime(cwg_tdd1.index)
        cwg_tdd1.columns = ["CWG " + bbg_tdd2.columns[0]]
        cwg_tdd1 = cwg_tdd1.reindex(bbg_tdd2.index).fillna(method="ffill")
        fig1 = demand_forecast_chart(hdd_df, title='1-15 CDD forecasts charts for US TOTAL', bbg_tdd=bbg_tdd1,
                                     bbg_tdd1=bbg_tdd2, cwg_tdd=cwg_tdd, cwg_tdd1=cwg_tdd1)
    else:
        fig1 = demand_forecast_chart(hdd_df, title='1-15 CDD forecasts charts for US TOTAL', bbg_tdd=bbg_tdd1,
                                     cwg_tdd=this_month_hdd_forecast["CWG Fcast"])
    hdd_df_sc['Actual'] = data['US South Central CDD']
    fig2 = demand_forecast_chart(hdd_df_sc, title='1-15 CDD forecasts charts for US South Central')
    hdd_df_east['Actual'] = data['US East CDD']
    fig3 = demand_forecast_chart(hdd_df_east, title='1-15 CDD forecasts charts for US East')
    tbs.append(fig1)
    tbs.append(fig2)
    tbs.append(fig3)

    tbs.append('Current Month - Total CDD forecast')
    tbs.append(this_month_hdd_forecast_html)
    tbs.append('<br>')

    if 'next_month_hdd_forecast_html' in locals():
        tbs.append('Next Month - Total CDD forecast')
        tbs.append(next_month_hdd_forecast_html)
        tbs.append('<br>')

    table.figures_to_html(tbs1, filename=f"{html_path}\\weather\\links\\us_weather_tables_cdd_sc_east.html")
    tbs.append(
        u'<a href="{}\\weather\\links\\us_weather_tables_cdd_sc_east.html">Link to South Central and East tables</a>'.format(
            html_path))
    tbs.append('<br>')
    tbs.append('<br>')

    df2_cdd = sql.read_sql(
        ("select min(DATES) as dt, ELEC_CDD, [10Y_ELEC_CDD] from CWG_US_national where "
         "IS_FORECAST=0 group by ELEC_CDD,[10Y_ELEC_CDD] order by dt")
    )
    df2_cdd = df2_cdd.drop_duplicates(subset=['dt'])
    df2_cdd.columns = ['dt', 'NG_CDD', '10Y_NG_CDD']
    df2_cdd = df2_cdd.rename(columns={"dt": "Date"})
    df2_cdd['Date'] = pd.to_datetime(df2_cdd['Date'])
    df2_cdd.set_index('Date', inplace=True)
    a_df = df2_cdd
    a_df.columns = ['NG_CDD', '10Y_NG_CDD']
    a_df['NG_CDD'] = data['US Total CDD']
    a_df['10Y_NG_CDD'] = bbg_normal['US Total CDD']
    a_df.dropna(inplace=True)

    df2_hdd = sql.read_sql(
        ("select min(DATES) as dt, NG_HDD, [10Y_NG_HDD] from CWG_US_national where "
         "IS_FORECAST=0 group by NG_HDD,[10Y_NG_HDD] order by dt")
    )
    df2_hdd = df2_hdd.drop_duplicates(subset=['dt'])
    df2_hdd.columns = ['dt', 'NG_HDD', '10Y_NG_HDD']
    df2_hdd = df2_hdd.rename(columns={"dt": "Date"})
    df2_hdd['Date'] = pd.to_datetime(df2_hdd['Date'])
    df2_hdd.set_index('Date', inplace=True)
    h_df = df2_hdd
    h_df.columns = ['NG_CDD', '10Y_NG_CDD']
    h_df['NG_CDD'] = data_hdd['US Total HDD']
    h_df['10Y_NG_CDD'] = bbg_normal_hdd['US Total HDD']
    h_df.dropna(inplace=True)

    fcast_date = np.sort(fcasts_total['AS_OF_DATE'].unique())
    latest_hdd = fcasts_total.loc[fcasts_total['AS_OF_DATE'] == fcast_date[-1], :].sort_values('DATES')
    latest_hdd.set_index('DATES', inplace=True)
    latest_hdd['10Y_NG_CDD'] = bbg_normal['US Total CDD']

    if (latest_hdd.index[0] - a_df.index[-1]).days > 1:
        previous_hdd = fcasts_total.loc[fcasts_total['AS_OF_DATE'] == fcast_date[-2], :].sort_values('DATES')
        previous_hdd.set_index('DATES', inplace=True)
        hdd_fcast = pd.concat([previous_hdd[['NG_CDD', '10Y_NG_CDD']].iloc[0:1], latest_hdd[['NG_CDD', '10Y_NG_CDD']]],
                              axis=0)
    else:
        hdd_fcast = latest_hdd[['NG_CDD', '10Y_NG_CDD']]
    if len(hdd_fcast) > 0:
        a_df = pd.concat([a_df, hdd_fcast], axis=0)
        hdd_fcast.columns = ['NG_CDD', '10Y_NG_CDD']

    a_df.columns = ['NG_CDD', '10Y_NG_CDD']
    ng_convert_dict = {'Oct': 0.3, 'Nov': 0.6, 'Dec': 1.4, 'Jan': 1.7, 'Feb': 1.6, 'Mar': 0.8, 'Apr': 0.6,
                       **_unrecovered('IMG_4922 original line 1491: dictionary tail after Apr'),
                       'Jun': 0, 'Jul': 0, 'Aug': 0, 'Sep': 0}
    if (today() + dt.timedelta(10)).month in [4, 5, 6, 7, 8, 9]:
        summer = winter_hdd(h_df, winsum='W')
        summer_table = witer_month_table(summer, winsum='W')
        winter = winter_hdd(a_df, winsum='S')
        winter_table = witer_month_table(winter, winsum='S')
    else:
        summer = winter_hdd(h_df, winsum='S')
        summer_table = witer_month_table(summer, winsum='S')
        winter = winter_hdd(a_df, winsum='W')
        winter_table = witer_month_table(winter, winsum='W')
    current_month_str = str(dt.datetime.strftime(dt.datetime(current_year, current_month, 1), '%b'))
    current_year_str = winter_table.columns[-1]
    winter_table.loc[winter_table['month'] == 'Total', current_year_str] = winter_table[current_year_str].iloc[
        :-1].sum()

    convert_bcf = [ng_convert_dict[i] for i in summer_table["month"].iloc[:-1]]
    convert_bcf = pd.Series(convert_bcf, index=summer_table.index[:-1])
    summer_table_bcf = summer_table.copy()
    summer_table_bcf.loc[summer_table_bcf.index[:-1], summer_table_bcf.columns[1:]] = summer_table_bcf.iloc[:-1, 1:].apply(
        lambda x: np.asarray(x) * np.asarray(convert_bcf), axis=0)  # * -1
    summer_table_bcf.loc[summer_table_bcf.index[-1], summer_table_bcf.columns[1:]] = summer_table_bcf.iloc[:-1, 1:].sum(
        axis=0)
    summer_table_html = table.html_format(summer_table_bcf, precision=1, format_column={
        summer_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[6]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[7]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        summer_table.columns[9]: {'width': '80px', 'text-align': 'center'},
    })
    winter_table_html = table.html_format(winter_table, precision=0, format_column={
        winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[7]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[9]: {'width': '80px', 'text-align': 'center'},
    })

    tbs.append('Total BCF change vs 10Y Normal - last season: ')
    tbs.append(summer_table_html)
    tbs.append('<br>')
    tbs.append('Total CDD vs 10Y Normal - current and next month include CDD forecasts: ')
    tbs.append(winter_table_html)
    tbs.append('<br>')

    convert_bcf = [ng_convert_dict[i] for i in winter_table["month"].iloc[:-1]]
    convert_bcf = pd.Series(convert_bcf, index=winter_table.index[:-1])
    winter_table_bcf = winter_table.copy()
    winter_table_bcf.loc[winter_table_bcf.index[:-1], winter_table_bcf.columns[1:]] = winter_table_bcf.iloc[:-1, 1:].apply(
        lambda x: np.asarray(x) * np.asarray(convert_bcf), axis=0)
    winter_table_bcf.loc[winter_table_bcf.index[-1], winter_table_bcf.columns[1:]] = winter_table_bcf.iloc[:-1, 1:].sum(axis=0)
    winter_table_bcf_html = table.html_format(winter_table_bcf, precision=1, format_column={
        winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[7]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[9]: {'width': '80px', 'text-align': 'center'},
    })

    if (today() + dt.timedelta(10)).month in [4, 5, 6, 7, 8, 9]:
        tbs.append(cumulative_cdd_chart(winter, hdd_fcast))
    else:
        tbs.append(cumulative_hdd_chart(winter, hdd_fcast))

    df2_cdd = sql.read_sql(
        ("select min(DATES) as dt, ELEC_CDD, [10Y_ELEC_CDD] from CWG_US_5region where "
         "REGION_NAME='South Central' and IS_FORECAST=0 group by ELEC_CDD,[10Y_ELEC_CDD] order by dt")
    )
    df2_cdd = df2_cdd.drop_duplicates(subset=['dt'])
    df2_cdd.columns = ['dt', 'NG_CDD', '10Y_NG_CDD']
    df2_cdd = df2_cdd.rename(columns={"dt": "Date"})
    df2_cdd['Date'] = pd.to_datetime(df2_cdd['Date'])
    df2_cdd.set_index('Date', inplace=True)
    a_df = df2_cdd
    a_df.columns = ['NG_CDD', '10Y_NG_CDD']
    a_df['NG_CDD'] = data['US South Central CDD']
    a_df['10Y_NG_CDD'] = bbg_normal['US South Central CDD']
    a_df.dropna(inplace=True)

    fcast_date = np.sort(fcasts_sc['AS_OF_DATE'].unique())
    latest_hdd = fcasts_sc.loc[fcasts_sc['AS_OF_DATE'] == fcast_date[-1], :].sort_values('DATES')
    latest_hdd.set_index('DATES', inplace=True)
    latest_hdd['10Y_NG_CDD'] = bbg_normal['US South Central CDD']

    if (latest_hdd.index[0] - a_df.index[-1]).days > 1:
        previous_hdd = fcasts_sc.loc[fcasts_sc['AS_OF_DATE'] == fcast_date[-2], :].sort_values('DATES')
        previous_hdd.set_index('DATES', inplace=True)
        hdd_fcast = pd.concat([previous_hdd[['NG_CDD', '10Y_NG_CDD']].iloc[0:1], latest_hdd[['NG_CDD', '10Y_NG_CDD']]],
                              axis=0)
    else:
        hdd_fcast = latest_hdd
    if len(hdd_fcast) > 0:
        hdd_fcast = hdd_fcast[['NG_CDD', '10Y_NG_CDD']]
        a_df = pd.concat([a_df, hdd_fcast], axis=0)

    a_df.columns = ['NG_CDD', '10Y_NG_CDD']
    if today().month in [4, 5, 6, 7, 8, 9]:
        winter = winter_hdd(a_df, winsum='S')
        winter_table = witer_month_table(winter, winsum='S')
    else:
        winter = winter_hdd(a_df, winsum='W')
        winter_table = witer_month_table(winter, winsum='W')
    current_month_str = str(dt.datetime.strftime(dt.datetime(current_year, current_month, 1), '%b'))
    current_year_str = winter_table.columns[-1]
    winter_table.loc[winter_table['month'] == 'Total', current_year_str] = winter_table[current_year_str].iloc[
        :-1].sum()
    winter_table_html = table.html_format(winter_table, precision=0, format_column={
        winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[7]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[9]: {'width': '80px', 'text-align': 'center'},
    })

    tbs.append('South Central CDD vs 10Y Normal - current and next month include CDD forecasts: ')
    tbs.append(winter_table_html)
    tbs.append('<br>')
    if today().month in [4, 5, 6, 7, 8, 9]:
        tbs.append(cumulative_cdd_chart(winter, hdd_fcast))
    else:
        tbs.append(cumulative_hdd_chart(winter, hdd_fcast))

    df2_cdd = sql.read_sql(
        ("select min(DATES) as dt, ELEC_CDD, [10Y_ELEC_CDD] from CWG_US_5region where "
         "REGION_NAME='East' group by ELEC_CDD,[10Y_ELEC_CDD] order by dt")
    )
    df2_cdd = df2_cdd.drop_duplicates(subset=['dt'])
    df2_cdd.columns = ['dt', 'NG_CDD', '10Y_NG_CDD']
    df2_cdd = df2_cdd.rename(columns={"dt": "Date"})
    df2_cdd['Date'] = pd.to_datetime(df2_cdd['Date'])
    df2_cdd.set_index('Date', inplace=True)
    a_df = df2_cdd
    a_df.columns = ['NG_CDD', '10Y_NG_CDD']
    a_df['NG_CDD'] = data['US East CDD']
    a_df['10Y_NG_CDD'] = bbg_normal['US East CDD']
    a_df.dropna(inplace=True)

    fcast_date = np.sort(fcasts_east['AS_OF_DATE'].unique())
    latest_hdd = fcasts_east.loc[fcasts_east['AS_OF_DATE'] == fcast_date[-1], :].sort_values('DATES')
    latest_hdd.set_index('DATES', inplace=True)
    latest_hdd['10Y_NG_CDD'] = bbg_normal['US East CDD']

    if (latest_hdd.index[0] - a_df.index[-1]).days > 1:
        previous_hdd = fcasts_east.loc[fcasts_east['AS_OF_DATE'] == fcast_date[-2], :].sort_values('DATES')
        previous_hdd.set_index('DATES', inplace=True)
        hdd_fcast = pd.concat([previous_hdd[['NG_CDD', '10Y_NG_CDD']].iloc[0:1], latest_hdd[['NG_CDD', '10Y_NG_CDD']]],
                              axis=0)
    else:
        hdd_fcast = latest_hdd
    if len(hdd_fcast) > 0:
        hdd_fcast = hdd_fcast[['NG_CDD', '10Y_NG_CDD']]
        a_df = pd.concat([a_df, hdd_fcast], axis=0)

    a_df.columns = ['NG_CDD', '10Y_NG_CDD']
    if today().month in [4, 5, 6, 7, 8, 9]:
        winter = winter_hdd(a_df, winsum='S')
        winter_table = witer_month_table(winter, winsum='S')
    else:
        winter = winter_hdd(a_df, winsum='W')
        winter_table = witer_month_table(winter, winsum='W')
    current_month_str = str(dt.datetime.strftime(dt.datetime(current_year, current_month, 1), '%b'))
    current_year_str = winter_table.columns[-1]
    winter_table.loc[winter_table['month'] == 'Total', current_year_str] = winter_table[current_year_str].iloc[
        :-1].sum()
    winter_table_html = table.html_format(winter_table, precision=0, format_column={
        winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[7]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[9]: {'width': '80px', 'text-align': 'center'},
    })

    tbs.append('East CDD vs 10Y Normal - current and next month include CDD forecasts: ')
    tbs.append(winter_table_html)
    tbs.append('<br>')
    if today().month in [4, 5, 6, 7, 8, 9]:
        tbs.append(cumulative_cdd_chart(winter, hdd_fcast))
    else:
        tbs.append(cumulative_hdd_chart(winter, hdd_fcast))
    tbs.append(
        u'<a href="{}\\weather\\us_tdd.html">Link to US TDD</a>'.format(html_path)
    )
    tbs.append('<br>')

    tbs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + tbs,
        f"{html_path}\\weather\\us_cdd_hdd.html", task_name="Weather - Global TDD")
    send_email(send_to=send_to, subject=report_name, body=tbs, html_path=f"{html_path}\\weather\\us_cdd_hdd.html")


def forecast_power_demand():
    data = get_power_demand()
    sdate = data['US Power demand actuals'].first_valid_index()
    data = data.loc[data.index >= sdate, :]

    bbg_normal = bbg.bdh('TENYCNEC Index', ['PX_LAST'], sdate=dt.datetime(2009, 1, 1),
                         edate=today() + dt.timedelta(days=364 * 2))
    bbg_normal.to_csv(r'\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\weather\US_cdd_normal.csv')
    bbg_normal.columns = ['US Gas CDD actuals']

    i_holidays = holidays.country_holidays('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': i_holidays})

    fitted = talib.ts_forecast(data.dropna()['US Power demand actuals'], hol=df_holidays,
                               forecast_periods=_unrecovered('IMG_4926/4927 original line 1740: forecast_periods and remaining arguments'))
    pd_normal = fitted.loc[data.first_valid_index(): bbg_normal.index[-1], 'yhat']
    pd_normal_by_year = ts.data_by_year(pd_normal, freq='D')
    pd_normal_by_year.fillna(method='ffill', inplace=True)
    pd_normal_by_year_mean = pd_normal_by_year.rolling(10, min_periods=1, axis=1).mean()
    bbg_normal['US Power demand actuals'] = np.nan
    for yr in pd_normal_by_year_mean.columns:
        bbg_normal.loc[bbg_normal.index.year == yr, 'US Power demand actuals'] = pd_normal_by_year_mean.loc[
            _unrecovered('IMG_4927 original line 1747: index expression ending bbg_normal.loc[bbg_normal.index.year == yr, :]) - 1'), yr].values

    fcast_df, hdd_df = demand_forecast_cdd(data, bbg_normal)

    add_days = pd.date_range(fcast_df.index[-1] + relativedelta(days=1),
                             fcast_df.index[-1] + relativedelta(years=1, months=1) + relativedelta(day=31))
    fcast_df_norm = bbg_normal.loc[add_days, 'US Power demand actuals']
    fcast_df_norm = fcast_df_norm.to_frame('Normal')
    fcast_df_save = pd.concat([fcast_df, fcast_df_norm], axis=0)
    fcast_df_save.drop(fcast_df_save.columns[1:4], axis=1, inplace=True)
    fcast_df_save.columns = ['Forecast', 'Normal']
    fcast_df_save.loc[:fcast_df_save['Forecast'].last_valid_index(), 'Normal'] = np.nan
    fcast_df_save.loc[~np.isnan(fcast_df_save['Forecast']), 'Normal'] = fcast_df_save.loc[
        ~np.isnan(fcast_df_save['Forecast']), 'Forecast']
    fcast_df_save.drop('Forecast', axis=1, inplace=True)
    fcast_df_save.dropna(inplace=True)
    try:
        fcast_df_save.to_excel(convert_path_to_linux(f"{weather_csv}\\power_forecast_latest.xlsx"))
    except:
        pass


def forecast_rescom():
    data = get_rescom()
    sdate = data['US ResCom demand actuals'].first_valid_index()
    data = data.loc[data.index >= sdate, :]

    bbg_normal = bbg.bdh('TENYCNGH Index', ['PX_LAST'], sdate=dt.datetime(2009, 1, 1),
                         edate=today() + dt.timedelta(days=364 * 2))
    bbg_normal.to_csv(r'\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\weather\US_gas_normal.csv')
    bbg_normal.columns = ['US Gas HDD actuals']

    i_holidays = holidays.country_holidays('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': i_holidays})

    fitted = talib.ts_forecast(data.dropna()['US ResCom demand actuals'], hol=df_holidays,
                               forecast_periods=_unrecovered('IMG_4927 original line 1787: forecast_periods and remaining arguments'))
    bbg_normal['US ResCom demand actuals'] = fitted.loc[data.first_valid_index(): bbg_normal.index[-1], 'yhat']

    fcast_df, hdd_df = demand_forecast_hdd(data, bbg_normal)

    add_days = pd.date_range(fcast_df.index[-1] + relativedelta(days=1),
                             fcast_df.index[-1] + relativedelta(years=1, months=1) + relativedelta(day=31))
    fcast_df_norm = bbg_normal.loc[add_days, 'US ResCom demand actuals']
    fcast_df_norm = fcast_df_norm.to_frame('Normal')
    fcast_df_save = pd.concat([fcast_df, fcast_df_norm], axis=0)
    fcast_df_save.drop(fcast_df_save.columns[1:4], axis=1, inplace=True)
    fcast_df_save.columns = ['Forecast', 'Normal']
    fcast_df_save.loc[:fcast_df_save['Forecast'].last_valid_index(), 'Normal'] = np.nan
    fcast_df_save.loc[~np.isnan(fcast_df_save['Forecast']), 'Normal'] = fcast_df_save.loc[
        ~np.isnan(fcast_df_save['Forecast']), 'Forecast']
    fcast_df_save.drop('Forecast', axis=1, inplace=True)
    fcast_df_save.dropna(inplace=True)
    try:
        fcast_df_save.to_excel(convert_path_to_linux(f"{weather_csv}\\rescom_forecast_latest.xlsx"))
    except:
        pass


def update(send_to=send_to):
    send_us_cdd(send_to=send_to)


if __name__ == '__main__':
    update()
