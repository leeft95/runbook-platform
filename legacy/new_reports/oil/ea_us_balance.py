import pandas as pd
import numpy as np
import datetime as dt
import sys
import os
os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = "C:\local\certs\root.crt"
os.environ["REQUESTS_CA_BUNDLE"] = "C:\local\certs\root.crt"
os.environ["SSL_CERT_FILE"] = "C:\local\certs\root.crt"
import statsmodels.api as sm
import requests
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import BDay
import plotly.graph_objects as go
import plotly.express as px
import ecm.cmds.data as dv
import ecm.cmds.bbg as bbg
import ecm.cmds.chart as chart
import ecm.cmds.table as table
import ecm.cmds.sql as sql
import ecm.cmds.time_series as ts
from ecm.cmds.config import root_path, html_path, output_path, oil_group, csv_path, data_path
from ecm.cmds.email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
from tshistory.api import timeseries
import pytz
from io import BytesIO

send_to = oil_group
report_name = "EA US Balance"
file_name = "ea_us_balance"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text in ea_us_balance.py, source lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2023, 7, 1, 14, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def us_iir():
    total_USA = sql.read_sql(_missing_photo_text(
        "62", "select * from dbo.IIR_CDU_Latest where unitTypeGroup='Crude' and [plantPhysicalAddress.countryName",
        "eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')"))
    test = pd.date_range(start='2018-01-01', end='2026-01-01')
    newdata = pd.Series(0, index=test)
    for idx, row in total_USA.iterrows():
        test = pd.date_range(start=row.eventStartDate, end=row.eventEndDate)
        tbl = pd.Series(row['offlineCapacity.capacityOffline'], index=test)
        newdata = newdata.add(tbl, fill_value=0)
    newdata = newdata.to_frame('Cap_offline')
    newdata = newdata.loc[newdata.index < dt.datetime(today().year + 2, 1, 1)]
    return newdata


def update(send_to):
    api_key = os.environ['ENERGY_ASPECTS_API_KEY']
    dataset_details_url = 'https://api.energyaspects.com/data/datasets/timeseries/'
    US_Cr_b = ('251,252,253,254,255,257,258,259,260,261,262,263,264,265,266,268,269,270,'
               '271,272,273,274,275,277,278,279,280,281,282,283,284,285,286,287,288,290,'
               '291,292,293,294,295,296,297,298,299,301,302,303,304,305,306,307,308,309,'
               '310,311,313,314,315,316,317,6495,6496,6497,6498,6499,6500')
    to_retrieve = {'USBalance': US_Cr_b}
    col_one_list = dv.ea_release_dates(dataset_id="313", monthly=False)
    col_one_list_monthly = list(col_one_list[i] for i in [-9, -5, -1])
    col_one_list_monthly.sort(reverse=True)
    col_one_list_weekly = col_one_list[-30:]  # need last 6m
    col_one_list_weekly.sort(reverse=True)
    col_one_list1 = []
    col_one_list1.append(col_one_list[-1])
    col_one_list1.append(col_one_list[-5])
    overall_stocks = pd.DataFrame()
    overall_prod = pd.DataFrame()
    overall_runs = pd.DataFrame()
    all_stocks = pd.DataFrame()
    all_prod = pd.DataFrame()
    all_runs = pd.DataFrame()
    for i in range(0, len(col_one_list_monthly)):
        newdata = dv.energy_aspects(dataset_id=US_Cr_b, start='2010-01-01', release_date=col_one_list_monthly[i])
        stocks = newdata[['Date', 'Monthly EA forecast for crude oil inventories in United States in mb']]
        prod = newdata[['Date', 'Monthly EA forecast for crude oil production in United States in kb/d']]
        stocks.set_index('Date', inplace=True)
        prod.set_index('Date', inplace=True)
        prod.index = pd.to_datetime(prod.index)
        if pd.to_datetime(col_one_list_monthly[i]) < dt.datetime(2025, 5, 29):
            prod.loc[prod.index >= dt.datetime(2026, 1, 1), :] = np.nan
        stocks.columns = [col_one_list_monthly[i][:10]]
        prod.columns = [col_one_list_monthly[i][:10]]
        overall_stocks = pd.concat([overall_stocks, stocks], axis=1)
        overall_prod = pd.concat([overall_prod, prod], axis=1)
    for _idx, i in enumerate(col_one_list_weekly):
        runs = dv.energy_aspects(dataset_id='1679', start='2023-01-01', release_date=i)
        runs.set_index('Date', inplace=True)
        runs.index = pd.to_datetime(runs.index)
        runs.columns = [pd.to_datetime(i[:10]).strftime('%Y%m%d')]
        overall_runs = pd.concat([overall_runs, runs], axis=1)
    frames_stocks = []
    frames_prod = []
    all_indexes_stocks = set()
    all_indexes_prod = set()
    for i in range(0, len(col_one_list_weekly)):
        newdata = dv.energy_aspects(dataset_id=US_Cr_b, start='2010-01-01', release_date=col_one_list_weekly[i])
        stocks = newdata[['Date', 'Monthly EA forecast for crude oil inventories in United States in mb']]
        prod = newdata[['Date', 'Monthly EA forecast for crude oil production in United States in kb/d']]
        stocks.set_index('Date', inplace=True)
        prod.set_index('Date', inplace=True)
        stocks.columns = [col_one_list_weekly[i][:10]]
        prod.columns = [col_one_list_weekly[i][:10]]
        frames_stocks.append(stocks)
        frames_prod.append(prod)
        all_indexes_stocks.update(stocks.index)
        all_indexes_prod.update(prod.index)
    union_index_stocks = pd.Index(sorted(all_indexes_stocks))
    union_index_prod = pd.Index(sorted(all_indexes_prod))
    frames_stocks = [df.reindex(union_index_stocks) for df in frames_stocks]
    frames_prod = [df.reindex(union_index_prod) for df in frames_prod]
    all_stocks = pd.concat(frames_stocks, axis=1)
    all_prod = pd.concat(frames_prod, axis=1)
    all_stocks.index = pd.to_datetime(all_stocks.index)
    all_stocks_chg = all_stocks.diff()
    all_stocks_chg = all_stocks_chg.loc[all_stocks_chg.index >= today() + relativedelta(day=1)]
    all_stocks_chg = all_stocks_chg.iloc[:12, :]
    all_stocks_chg.index = all_stocks_chg.index.strftime("%b-%y")
    all_stocks_chg = all_stocks_chg.T
    all_stocks_chg.index.name = "Forecast Date"
    all_stocks_chg = all_stocks_chg.reset_index()
    evo_table = table.html_format(
        df=all_stocks_chg, precision=1, header="EA forecast of US monthly crude stocks change (Unit: mb)",
        format_column={'Forecast Date': {'width': '100px', 'text-align': 'center'},
                       tuple(all_stocks_chg.columns[1:]): {'width': '60px', 'text-align': 'center'}})
    newdata = dv.energy_aspects(dataset_id=US_Cr_b, start='2010-01-01')
    stocksdt = newdata[['Date', 'Monthly EA forecast for crude oil inventories in United States in mb']]
    stocksdt.set_index('Date', inplace=True)
    stocksdt.index = pd.to_datetime(stocksdt.index)
    stocksdt.columns = ['US crude stocks']
    dash_from = (stocksdt.index[np.where(stocksdt.index < today())[0][-1]]).strftime("%Y%m%d")
    fig = chart.seasonal_chart(
        df=stocksdt, freq='MS', ex2020=True, title='US Crude Stocks - most recent EA forecast',
        y_axis_title='Mbbl', width=900, height=600, dash_from=dash_from, vs_avg=False)
    cushing_ea = dv.energy_aspects(dataset_id="16063", start='2010-01-01')
    cushing_ea = cushing_ea[['Date', 'Monthly EA forecast for crude oil inventories in Cushing in kb']]
    cushing_ea.set_index('Date', inplace=True)
    cushing_ea.index = pd.to_datetime(cushing_ea.index)
    cushing_ea.columns = ['US cushing stocks']
    dash_from = (cushing_ea.index[np.where(cushing_ea.index >= today() + relativedelta(day=1))[0][0]]).strftime("%Y%m%d")
    fig_cush = chart.seasonal_chart(
        df=cushing_ea, freq='MS', ex2020=True, title='US Cushing Stocks - most recent EA forecast',
        y_axis_title='Mbbl', width=900, height=600, dash_from=dash_from, vs_avg=False)
    overall_stocks = overall_stocks.loc[overall_stocks.index > '2022-12-31']
    fig2 = chart.line_chart(
        df=overall_stocks, title='EA forecast of US Crude Stocks Evolution', tickformat=None, y_axis_title='Mbbl',
        highlight_dict={overall_stocks.columns[0]: {'color': 'black', 'width': 2},
                        overall_stocks.columns[1]: {'color': 'red', 'width': 1},
                        overall_stocks.columns[2]: {'color': 'green', 'width': 1, 'dash': 'dash'}})

    def cal_bal(folder=f"{data_path}\\EA\\US Gasoline", type="m", issue=-1):
        files = [x for x in os.listdir(convert_path_to_linux(folder)) if x[-5] == type]
        files.sort()
        if not isinstance(issue, int):
            file_dts = [dt.datetime.strptime(x[:8], "%Y%m%d") for x in files]
            cur_q = int((today().month - 1) / 3 + 1)
            last_day = dt.datetime(today().year, 3 * cur_q - 2, 1) - dt.timedelta(1)
            if last_day == dt.datetime(2024, 6, 30):
                issue = file_dts.index(dt.datetime(2024, 7, 17))
            else:
                issue = np.where(np.array(file_dts) <= last_day)[0][-1]
        data = pd.read_csv(convert_path_to_linux(f"{folder}\\{files[issue]}"), sep=' ', header=None)
        cols = data.iloc[0, :]
        cols = [f"{cols[x]}-{str(int(cols[x + 1]))}" for x in cols.index if x % 2 == 0]
        data = data.iloc[1:-1, :]
        data.dropna(inplace=True, axis=1)
        data.set_index(data.columns[0], inplace=True)
        data.columns = cols
        data = data.T
        data.index = [dt.datetime.strptime(x, "%b-%y") for x in data.index]
        data[data.columns[0]] = data[data.columns[0]].str.replace(',', '').astype(float)
        data[data.columns[1]] = data[data.columns[1]].str.replace(',', '').astype(float)
        data[data.columns[2]] = data[data.columns[2]].str.replace(',', '').astype(float)
        data[data.columns[3]] = data[data.columns[3]].str.replace(',', '').astype(float)
        data[data.columns[4]] = data[data.columns[4]].str.replace('(', '-', regex=False)
        data[data.columns[4]] = data[data.columns[4]].str.replace(')', '', regex=False).astype(float)
        bal = data.iloc[:, 0] + data.iloc[:, 1] - data.iloc[:, 2] - data.iloc[:, 3] + data.iloc[:, 4]
        bal = bal.to_frame("chg")
        bal["day"] = bal.index.daysinmonth
        return (bal["chg"] * bal["day"]).to_frame(files[issue][:8])

    mogas_fcst1 = cal_bal(folder=f"{data_path}\\EA\\US Gasoline", type="m", issue=-1)
    mogas_fcst2 = cal_bal(folder=f"{data_path}\\EA\\US Gasoline", type="m", issue="last quarter")
    mogas_fcst = pd.concat([mogas_fcst1, mogas_fcst2], axis=1)
    fig2_mo = chart.line_chart(
        df=mogas_fcst, title='US Gasoline Stocks Change Evolution', tickformat=None, y_axis_title='Mbbl',
        highlight_dict={mogas_fcst.columns[0]: {'color': 'black', 'width': 2},
                        mogas_fcst.columns[1]: {'color': 'red', 'width': 1}})
    disty_fcst1 = cal_bal(folder=f"{data_path}\\EA\\US Distillate", type="m", issue=-1)
    disty_fcst2 = cal_bal(folder=f"{data_path}\\EA\\US Distillate", type="m", issue="last quarter")
    disty_fcst = pd.concat([disty_fcst1, disty_fcst2], axis=1)
    fig2_disty = chart.line_chart(
        df=disty_fcst, title='US Disty Stocks Change Evolution', tickformat=None, y_axis_title='Mbbl',
        highlight_dict={disty_fcst.columns[0]: {'color': 'black', 'width': 2},
                        disty_fcst.columns[1]: {'color': 'red', 'width': 1}})
    proddt = newdata[['Date', 'Monthly EA forecast for crude oil production in United States in kb/d']]
    proddt.set_index('Date', inplace=True)
    proddt.index = pd.to_datetime(proddt.index)
    proddt_2019 = proddt.loc[proddt.index.year == 2019].max() / 1000
    overall_prod = overall_prod.loc[overall_prod.index > '2022-12-31']
    fig3 = chart.line_chart(
        df=overall_prod / 1000, title='US Crude Prod EA vs STEO forecast', tickformat=None, y_axis_title='Mbbl',
        highlight_dict={overall_prod.columns[0]: {'color': 'black', 'width': 2},
                        overall_prod.columns[1]: {'color': 'red', 'width': 1},
                        overall_prod.columns[2]: {'color': 'green', 'width': 1, 'dash': 'dash'}})
    fig3.add_hline(y=proddt_2019['Monthly EA forecast for crude oil production in United States in kb/d'],
                   name='Max 2019 prod', **_missing_photo_text('271', 'l'))
    EIA = dv.eia_api_key
    api_key = os.environ['ENERGY_ASPECTS_API_KEY']
    EIA_web = _missing_photo_text('280', f'https://api.eia.gov/v2/steo/data/?api_key={EIA}&frequency=monthly&data[0]=value&'
                                  'facets[seriesId][]=COPRPUS&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5')
    commercial = requests.get(EIA_web, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    df = db[['period', 'value']]
    df.columns = ['Date', 'STEO']
    df.set_index('Date', drop=True, inplace=True)
    df['Year'] = df.index.astype(str).str[:4]
    df['Month'] = df.index.astype(str).str[5:]
    df['Day'] = 1
    df['Date'] = pd.to_datetime(df[['Year', 'Month', 'Day']])
    df.set_index('Date', drop=True, inplace=True)
    df = df.drop(columns=['Year', 'Month', 'Day'])
    df = df.loc[df.index > '2022-12-31']
    fig3.add_trace(go.Scatter(x=df.index, y=df.STEO, name='STEO'))
    actual_runs = bbg.bdh("DOEPCRIN Index", ["PX_LAST"], sdate=today() - relativedelta(years=1), edate=today())
    last_actual_date = actual_runs.index[-1]
    EA_runs_allday = overall_runs.reindex(pd.date_range(overall_runs.index[0], overall_runs.index[-1] + _missing_photo_text('302', 'relati')))
    EA_runs_allday.fillna(method="ffill", inplace=True)
    overall_runs_w = EA_runs_allday.reindex(pd.date_range(today() - dt.timedelta(49), today() + dt.timedelta(35), freq='W-FRI'))
    overall_runs_w_ = EA_runs_allday.reindex(pd.date_range(EA_runs_allday.index[0], EA_runs_allday.index[-1], freq='W-FRI'))
    EA_runs = overall_runs_w.copy().iloc[:, 0].to_frame("EA Runs")
    ea_runs_adj = pd.Series(0, index=EA_runs.index)
    for i in ea_runs_adj.index:
        for _idx, j in enumerate(overall_runs.columns):
            if i >= today():
                ea_runs_adj[i] = EA_runs.loc[i, EA_runs.columns[0]]
                break
            elif dt.datetime.strptime(j, "%Y%m%d") < i + BDay(3):
                ea_runs_adj[i] = overall_runs_w.loc[i, overall_runs.columns[_idx]]
                break
    dict_ecm = timeseries().history(_missing_photo_text('319', 'energy_aspects.crude_oil.na.us.implied_refinery_runs.kbbl_d.monthly.for'))
    ecm_date = max(list(dict_ecm.keys()))
    ea_runs_m = dict_ecm[ecm_date].reindex(pd.date_range(overall_runs.index[0], overall_runs.index[-1])).fillna(method='ffill')
    ea_runs_w = ea_runs_m.reindex(pd.date_range(today() - dt.timedelta(49), today() + dt.timedelta(35), freq='W-FRI'))
    EA_runs["EA Runs"] = ea_runs_w
    last_runs = _missing_photo_text('326', 'dict_ecm[ecm_date].reindex(pd.date_range(overall_runs_w_.index[0], overall_runs_w_.index[-1]')
    last_runs.name = ecm_date.strftime("%Y%m%d")
    cur_q = int((today().month - 1) / 3 + 1)
    if cur_q == 1:
        last_q = 4
        yr_adj = 1
    else:
        last_q = cur_q - 1
        yr_adj = 0
    last_day = dt.datetime(today().year, 3 * cur_q - 2, 1) - dt.timedelta(1)
    last_q_day = dt.datetime(today().year - yr_adj, 3 * last_q - 2, 1) - dt.timedelta(1)
    if last_day == dt.datetime(2024, 6, 30):
        issue = "20240724"
        issue_runs = "20240626"
    else:
        issue_dt = _missing_photo_text('341', '[dt.datetime.strptime(x[:10], "%Y-%m-%d") for x in col_one_list_weekly if dt.datetime.str')
        issue = issue_runs = issue_dt.strftime("%Y%m%d")
    issue_dt1 = _missing_photo_text('343', '[dt.datetime.strptime(x[:10], "%Y-%m-%d") for x in col_one_list_weekly if dt.datetime.strptime')
    issue1 = issue_runs1 = issue_dt1.strftime("%Y%m%d")
    if issue_runs1 == "20240327":
        issue_runs1 = "20240424"
    if issue_runs1 == "20250227":
        issue_runs1 = "20250226"
    try:
        second_runs = overall_runs_w_.loc[last_day:, issue_runs]
    except:
        ecm_date = _missing_photo_text('352', 'list(dict_ecm.keys())[np.where(pd.DatetimeIndex(list(dict_ecm.keys())) >= issue_dt.astime')
        ea_runs_m = _missing_photo_text('353', 'dict_ecm[ecm_date].reindex(pd.date_range(overall_runs_w_.index[0], overall_runs_w_.index')
        second_runs = ea_runs_m.reindex(overall_runs_w_.index)
        second_runs.name = issue_runs
    if issue_dt1 < dt.datetime(2024, 12, 18):
        ea_runs_rev = pd.concat([last_runs, second_runs, actual_runs.reindex(overall_runs_w_.index)], axis=1)
        ea_runs_rev.rename(columns={"PX_LAST": "Actual Runs"}, inplace=True)
        fig4 = chart.line_chart(
            df=ea_runs_rev, title='US Crude EA Forecast vs Actual Runs', tickformat=None, y_axis_title='kbd',
            highlight_dict={ea_runs_rev.columns[0]: {'color': 'black', 'width': 2},
                            ea_runs_rev.columns[1]: {'color': 'red', 'width': 1},
                            ea_runs_rev.columns[2]: {'color': 'blue', 'width': 2}})
    else:
        third_runs = overall_runs_w_.loc[last_day:, issue_runs1]
        ea_runs_rev = pd.concat([last_runs, second_runs, third_runs, actual_runs.reindex(overall_runs_w_.index)], axis=1)
        ea_runs_rev.rename(columns={"PX_LAST": "Actual Runs"}, inplace=True)
        fig4 = chart.line_chart(
            df=ea_runs_rev, title='US Crude EA Forecast vs Actual Runs', tickformat=None, y_axis_title='kbd',
            highlight_dict={ea_runs_rev.columns[0]: {'color': 'black', 'width': 2},
                            ea_runs_rev.columns[1]: {'color': 'red', 'width': 1},
                            ea_runs_rev.columns[2]: {'color': 'orange', 'width': 1},
                            ea_runs_rev.columns[3]: {'color': 'blue', 'width': 2}})
    iir = us_iir()
    iir = (iir.reindex(np.unique(np.concatenate((actual_runs.index, EA_runs.index), axis=None)))).sort_index()
    iir_run_adj_outage = (17400000 - 250000 - iir["Cap_offline"]) / 1000  # remove 250k capacity because of cl [clipped]
    iir_adj_actual = iir_run_adj_outage - actual_runs["PX_LAST"]
    unplan_outage = iir_adj_actual.rolling(4).mean()
    unplan_outage_forecast = unplan_outage.loc[unplan_outage.last_valid_index()]
    unplan_outage = unplan_outage.shift(1)
    unplan_outage = unplan_outage.reindex(EA_runs.index)
    unplan_outage.loc[unplan_outage.index > last_actual_date] = unplan_outage_forecast
    iir_run_adj = iir_run_adj_outage.reindex(EA_runs.index) - unplan_outage
    iir_diff1 = iir.diff()
    iir_diff = iir - iir.loc[EA_runs.index[np.where(EA_runs.index <= last_actual_date)[0][-1]], :]
    iir_diff.loc[iir_diff.index <= last_actual_date] = iir_diff1.loc[iir_diff.index <= last_actual_date]
    EA_runs_iir = pd.Series(0, index=EA_runs.index)
    EA_runs_iir.loc[EA_runs_iir.index > last_actual_date] = actual_runs.iloc[-1, 0]
    EA_runs_iir.loc[EA_runs_iir.index <= last_actual_date] = actual_runs.loc[
        (actual_runs.index <= last_actual_date) & (actual_runs.index >= EA_runs_iir.index[0]), "PX_LAST"]
    EA_runs_iir = EA_runs_iir.shift(1)
    EA_runs_iir = EA_runs_iir - iir_diff.iloc[:, 0] / 1000
    EA_runs_iir = EA_runs_iir.to_frame("IIR Runs")
    EA_runs = pd.concat([EA_runs, EA_runs_iir], axis=1)
    importstotal = dv.kpler(_missing_photo_text('411', '/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2023-01-01&toZones=United%20States&'))
    importstotal = importstotal.rename(columns={"Total": "Kpler Imports"})
    importstotal.set_index('Date', drop=True, inplace=True)
    importstotal.index = pd.to_datetime(importstotal.index)
    importstotal.to_csv(convert_path_to_linux(_missing_photo_text('415', f"{csv_path}\\oil\\kpler\\kpler_us_crude_import_", 'dt.datetime.n')))
    fcast_locs = np.where(importstotal.index > today())[0]
    importstotal.loc[importstotal.index[fcast_locs], "Kpler Imports"] = importstotal["Kpler Imports"].iloc[fcast_locs[0] - 4:fcast_locs[0]].mean()
    weekly_exp_total = dv.kpler(
        '/v1/flows?flowDirection=Export&granularity=eia-weekly&startDate=2023-01-01&'
        'fromZones=United%20States&unit=kbd&split=Total&products=crude%2fco')
    weekly_exp_total = weekly_exp_total.rename(columns={"Total": "Kpler Exports"})
    weekly_exp_total.set_index('Date', drop=True, inplace=True)
    weekly_exp_total.index = pd.to_datetime(weekly_exp_total.index)
    weekly_exp_total.to_csv(convert_path_to_linux(_missing_photo_text('427', f"{csv_path}\\oil\\kpler\\kpler_us_crude_export_", 'dt.dateti')))
    fcast_locs = np.where(weekly_exp_total.index > today())[0]
    weekly_exp_total.loc[weekly_exp_total.index[fcast_locs], "Kpler Exports"] = weekly_exp_total["Kpler Exports"].iloc[fcast_locs[0] - 4:fcast_locs[0]].mean()
    importscad = dv.kpler(
        '/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2018-01-01&'
        'toZones=United%20States&fromZones=Canada&unit=kbd&split=Origin%20Countries&products=crude%2fco')
    importscad = importscad.rename(columns={"Canada": "Cad Water"})
    importscad.set_index('Date', drop=True, inplace=True)
    importscad.index = pd.to_datetime(importscad.index)
    stocks = bbg.bdh('DOESCRUD Index', ['PX_LAST'], dt.datetime(2023, 1, 1), today(), elms=[("periodicityAdjustment", "ACTUAL")])
    stocks = stocks.diff()
    stocks.columns = ['Actual Change']
    kpler_inv = dv.kpler(link=_missing_photo_text('444', '/v1/inventories?zones=US&period=eia-weekly&startDate=2023-01-01&split=byTankType&withoutEiaAdj'))
    kpler_inv = kpler_inv.rename(columns={"Level (kb)": "Kpler Stock Chg"})
    kpler_inv.set_index('Date', drop=True, inplace=True)
    kpler_inv.index = pd.to_datetime(kpler_inv.index)
    kpler_inv = kpler_inv[["Kpler Stock Chg"]].diff()
    kpler_inv = kpler_inv * stocks['Actual Change'].std() / kpler_inv["Kpler Stock Chg"].std()
    kpler_inv = kpler_inv.reindex(weekly_exp_total.index)
    data = bbg.bdh('DEPWIMCA Index', ['PX_LAST'], dt.datetime(2018, 1, 1), today(), elms=[("periodicityAdjustment", "ACTUAL")])
    data.columns = ['Canada_DOE']
    data = pd.concat([data, importscad], axis=1)
    data['Cad Pipe'] = data['Canada_DOE'] - data['Cad Water']
    model = sm.tsa.arima.ARIMA(data['Cad Pipe'].dropna(), order=(6, 1, 3))
    res = model.fit()
    d4 = res.predict(start=EA_runs.index[0], end=EA_runs.index[-1])
    d4 = d4.to_frame("Cad Pipe")
    actual_prod = bbg.bdh('DOETCRUD Index', ['PX_LAST'], dt.datetime(2023, 1, 1), today(), elms=[("periodicityAdjustment", "ACTUAL")])
    actual_prod = actual_prod["PX_LAST"]
    EA_runs.dropna(inplace=True)
    merged_df = EA_runs.merge(importstotal['Kpler Imports'], left_index=True, right_index=True)
    merged_df = merged_df.merge(weekly_exp_total['Kpler Exports'], left_index=True, right_index=True)
    merged_df = merged_df.merge(kpler_inv['Kpler Stock Chg'], left_index=True, right_index=True)
    merged_df = merged_df.merge(d4, left_index=True, right_index=True)
    merged_df['YearMonth'] = merged_df.index.to_period('M')
    proddt['YearMonth'] = proddt.index.to_period('M')
    test = pd.merge(merged_df, proddt, on='YearMonth')
    test.index = merged_df.index
    test.loc[:, "Kpler Exports"] = test.loc[:, "Kpler Exports"] + 150
    test = test.drop(columns=['YearMonth'])
    test = test.rename(columns={"Monthly EA forecast for crude oil production in United States in kb/d": "Production"})
    test["IIR Runs Adj"] = iir_run_adj
    test["Actual Imports"] = bbg.bdh("DOEICISP Index", ["PX_LAST"], sdate=test.index[0], edate=today())
    test["Actual Exports"] = bbg.bdh("DOECEXP Index", ["PX_LAST"], sdate=test.index[0], edate=today())
    actual_prod = actual_prod.reindex(test.index)
    test["Actual Production"] = actual_prod
    test["Actual Runs"] = actual_runs.reindex(test.index)
    raw = requests.get("https://ir.eia.gov/wpsr/psw01.xls", stream=True, verify=False)
    data = BytesIO(raw.content)
    eia_us_bal = pd.read_excel(data, "Data 2", header=2)
    eia_us_bal.set_index("Date", inplace=True)
    eia_us_bal.index = pd.to_datetime(eia_us_bal.index)
    model = sm.tsa.arima.ARIMA(_missing_photo_text('503', 'eia_us_bal["Weekly U.S. Unaccounted for Crude Oil  (Thousand Barrels per Day)'))
    res = model.fit()
    test['Adjust Factor'] = res.predict(start=test.index[0], end=test.index[-1])
    eia_us_bal = eia_us_bal.reindex(test.index)
    test['Actual Adjust Factor'] = eia_us_bal["Weekly U.S. Unaccounted for Crude Oil  (Thousand Barrels per Day)"]
    test['Transfer to Supply'] = eia_us_bal["Weekly U.S. Transfers to Crude Oil Supply of Crude Oil (Thousand Barrels per Day)"]
    test['Transfer to Supply'].fillna(0, inplace=True)
    test.loc[test.index > last_actual_date, 'Transfer to Supply'] = 720
    test['Total Supply'] = test['Production'] + test['Kpler Imports'] + test['Cad Pipe'] + test['Transfer to Supply']
    test['Total Demand'] = test['EA Runs'] + test['Kpler Exports']
    test['Daily Stock Chg'] = test['Total Supply'] - test['Total Demand'] + test['Adjust Factor']
    test['Calc Stock Chg - EA'] = test['Daily Stock Chg'] * 7
    test['Calc Stock Chg - IIR'] = (test['Total Supply'] - (test['IIR Runs'] + test['Kpler Exports']) + test['Adjust Factor']) * 7
    test['Calc Stock Chg - IIR Adj'] = (test['Total Supply'] - (test['IIR Runs Adj'] + test['Kpler Exports']) + test['Adjust Factor']) * 7
    ea_fcst_crude_chg = all_stocks.iloc[:, 0].diff()
    ea_fcst_crude_chg = ea_fcst_crude_chg.to_frame("Fcast Stock Chg - EA")
    ea_fcst_crude_chg["days"] = ea_fcst_crude_chg.index.days_in_month
    ea_fcst_crude_chg["Fcast Stock Chg - EA"] = _missing_photo_text('526', 'ea_fcst_crude_chg["Fcast Stock Chg - EA"]/ea_fcst_crude_chg')
    ea_fcst_crude_chg.drop("days", axis=1, inplace=True)
    bdts = pd.bdate_range(ea_fcst_crude_chg.index[0], ea_fcst_crude_chg.index[-1] + relativedelta(day=31))
    ea_fcst_crude_chg = ea_fcst_crude_chg.reindex(bdts, method="ffill")
    ea_fcst_crude_chg = ea_fcst_crude_chg.reindex(test.index)
    cushing_ea = dv.energy_aspects(dataset_id="16063", start=bdts[0].strftime("%Y-%m-%d"))
    cushing_ea.set_index("Date", inplace=True)
    cushing_ea.index = pd.to_datetime(cushing_ea.index)
    ea_fcst_cushing_chg = cushing_ea.iloc[:, 0].diff()
    ea_fcst_cushing_chg = ea_fcst_cushing_chg.to_frame("Fcast Cushing Chg - EA")
    _missing_photo_text('538-540')
    ea_fcst_cushing_chg = ea_fcst_cushing_chg.reindex(bdts, method="ffill")
    ea_fcst_cushing_chg = ea_fcst_cushing_chg.reindex(test.index)
    first_index_value = test.index[0]
    test = pd.concat([test, stocks, ea_fcst_crude_chg, ea_fcst_cushing_chg], axis=1)
    test["Total Imports"] = test["Kpler Imports"] + test["Cad Pipe"]
    smart_cush = ts.read_csv(f"{data_path}\\sell_side_consensus\\Cushing\\cushing.csv", index_name="Date")
    smart_cush = ts.convert_monthly(smart_cush, to="weekly", freq="W-FRI")
    test["Fcast Cushing Chg - CON"] = (smart_cush * 1000).reindex(test.index)
    bbg_cush = bbg.bdh('DOEASCUS Index', ['PX_LAST'], dt.datetime(2023, 1, 1), today(), elms=[("periodicityAdjustment", "ACTUAL")])
    test["Actual Cushing Chg"] = bbg_cush["PX_LAST"]
    bbg_whisper = bbg.bdh('WHISCRUD Index', ['PX_LAST'], dt.datetime(2023, 1, 1), today(), elms=[("periodicityAdjustment", "ACTUAL")])
    bbg_whisper = bbg_whisper.reindex(bdts, method="bfill")
    test["Whisper"] = bbg_whisper["PX_LAST"]
    test = test.loc[test.index >= first_index_value]
    test = test[["Production", "Kpler Imports", "Cad Pipe", "Total Imports", "Actual Imports", _missing_photo_text('560', 'Transfer to'),
                 "EA Runs", "IIR Runs", "IIR Runs Adj", "Actual Runs", "Kpler Exports", "Actual Exports",
                 "Adjust Factor", "Actual Adjust Factor", "Daily Stock Chg", "Fcast Stock Chg - EA",
                 "Calc Stock Chg - EA", "Calc Stock Chg - IIR", "Calc Stock Chg - IIR Adj", _missing_photo_text('563', 'Kpler Stock Chg'),
                 "Fcast Cushing Chg - EA", "Fcast Cushing Chg - CON", "Actual Cushing Chg"]]
    sloc = len(test.loc[~np.isnan(test["Actual Change"]), "Actual Change"]) - 1
    next_week_stock_chg, issue_date = dv.ea_us_oil_weekly(sheet_name="Fig 1 US inventory projections", date=_missing_photo_text('567'))
    test.loc[test.index[sloc + 1], "Fcast Stock Chg - EA"] = next_week_stock_chg.iloc[2, 2] * 1000
    test.loc[test.index[sloc + 1], "Fcast Cushing Chg - EA"] = next_week_stock_chg.iloc[2, 1] * 1000
    test.index = test.index.strftime("%Y-%m-%d")
    wtb = test.T.reset_index()
    wtb.rename(columns={"index": "Crude"}, inplace=True)
    wtb_html = table.html_format(
        df=wtb, precision=0, header="Unit: kb for weekly stock change, kbd for others",
        format_column={'Crude': {'width': '160px', 'text-align': 'center'},
                       tuple(wtb.columns[1:sloc]): {'width': '80px', 'text5-align': 'center'},
                       tuple(wtb.columns[sloc + 2:]): {'width': '80px', 'text-align': 'center'},
                       tuple(wtb.columns[sloc:sloc + 2]): {'width': '80px', 'text-align': 'center', 'right_border': True}},
        format_row={4: {'italic': True}, 5: {'bottom_border': True}, 6: {'bottom_border': True, 'bold': True},
                    10: {'italic': True, 'bold': True}, 12: {'bottom_border': True, 'italic': True},
                    13: {'bottom_border': True, 'bold': True}, 15: {'italic': True, 'bold': True},
                    16: {'bottom_border': True}, 21: {'italic': True},
                    23: {'italic': True, 'bottom_border': True, 'bold': True}, 24: {'bold': True},
                    25: {'bold': True}, 26: {'italic': True, 'bold': True}})
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(table.html_text(f"DOE Weekly Crude Forecast", style="font-family:Calibri;", tag='h1'))
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>"))
    figs.append(table.html_text(f"Latest EA release - {col_one_list[-1][:10]}<br>", style="font-family:Calibri;"))
    figs.append(_missing_photo_text('602', '<a href="https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774688156/EA+US+Crud'))
    figs += [wtb_html, [fig, fig_cush], evo_table, fig2, fig3, fig4, fig2_mo, fig2_disty]
    table.to_html(figs, f"{html_path}\\oil\\ea_us_balance.html", task_name=report_name)
    if today().weekday() == 1:
        send_email(send_to=send_to, subject='DOE Weekly Crude Forecast', body=figs, html_path=f"{html_path}\\oil\\ea_us_balance.html")


if __name__ == '__main__':
    _missing_photo_text('611 onward: main block body absent')
