import pandas as pd
import numpy as np
import datetime as dt
import sys
from ecm.cmds.config import root_path
from ecm.cmds.utils import convert_path_to_linux
sys.path.append(f"{root_path}\\autoreports\\reports\\oil")
import eia_weekly_petroleum
import math
import glob
import os
import plotly as py
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dateutil.relativedelta import relativedelta
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds._email import send_email
from functools import partial
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.cdr as cdr
import ecm.cmds.talib as talib
from pyg_mongo import *
from pyg_cell import *
from ecm.cmds.config import url, html_path, oil_group, data_path, csv_path
from ecm.cmds.utils import convert_path_to_linux
from pathlib import Path


def _unrecovered(location, *visible_values):
    raise NotImplementedError(f"Photographed source is clipped or absent: {location}")


send_to = ["mkikano@elementcapital.com", "jmcphillips@elementcapital.com", "rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "DOE report bbg"
file_name = "doe_stocks_bbg"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


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
        start_datetime=dt.datetime(2023, 7, 1, 14, 31),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=30),
        repetition_duration=dt.timedelta(hours=3),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


def inventory_model(send_to):
    inv = get_oil_inventory(cdr.today())
    db = partial(mongo_table, db='data', table='eia_weekly', url=url, pk=['name', 'ticker', 'field'])
    total_crude = bbg.bdh("DOESCRUD Index", ["PX_LAST"], dt.datetime(2010, 1, 1), cdr.today())
    total_crude = total_crude["PX_LAST"]
    total_crude_chg = total_crude.diff() / total_crude
    total_crude_chg_4wm = total_crude_chg.rolling(4).mean()
    inv_chg_4wm_by_year = ts.data_by_year(total_crude_chg_4wm * 100, freq='W', start_day=1)
    window = 4
    inv_chg_by_year_z = pd.DataFrame(np.nan, index=inv_chg_4wm_by_year.index, columns=inv_chg_4wm_by_year.columns)
    for i in range(window, inv_chg_4wm_by_year.shape[1]):
        for j in range(0, inv_chg_4wm_by_year.shape[0]):
            if inv_chg_4wm_by_year.columns[i] in [2021, 2022, 2023, 2024]:
                rank_window_data = inv_chg_4wm_by_year.iloc[j, i - window - 1:i]
                rank_window_data = rank_window_data.drop(2020)
                inv_chg_by_year_z.loc[j, inv_chg_4wm_by_year.columns[i]] = (inv_chg_4wm_by_year.iloc[j, i] - rank_window_data.mean()) / rank_window_data.std()
            else:
                inv_chg_by_year_z.loc[j, inv_chg_4wm_by_year.columns[i]] = (inv_chg_4wm_by_year.iloc[j, i] - inv_chg_4wm_by_year.iloc[j, i - window:i].mean()) / inv_chg_4wm_by_year.iloc[j, i - window:i].std()
    inv1 = pd.Series(np.nan, index=inv.index)
    for yr in inv_chg_by_year_z.columns:
        if len(inv1.loc[inv1.index.year == yr]) == 52:
            inv1.loc[inv1.index.year == yr] = inv_chg_by_year_z[yr].values[:-1]
        elif len(inv1.loc[inv1.index.year == yr]) == 53:
            inv1.loc[inv1.index.year == yr] = inv_chg_by_year_z[yr].values
        else:
            inv1.loc[inv1.index.year == yr] = inv_chg_by_year_z[yr].values[:len(inv1.loc[inv1.index.year == yr])]
    inv1 = inv1[inv1.index >= dt.datetime(2005, 1, 1)]
    weekdays = pd.bdate_range(dt.datetime(2005, 1, 1), inv1.index[-1])
    new_idx = pd.bdate_range(dt.datetime(total_crude_chg_4wm.index[-1].year, 1, 1), dt.datetime(total_crude_chg_4wm.index[-1].year, 12, 31), freq="W-FRI")
    data1 = inv1.reindex(weekdays)
    data1.fillna(method='ffill', inplace=True)
    data1_chart = data1.reindex(new_idx)
    cur_yr = total_crude.index[-1].year
    if 2020 in range(cur_yr - 5, cur_yr):
        yr_list = list(range(cur_yr - 5, cur_yr))
        yr_list.remove(2020)
    else:
        yr_list = list(range(cur_yr - 4, cur_yr))
    figs = []
    figs.append(chart.seasonal(
        df=total_crude_chg_4wm * 100,
        data_p2y1=data1_chart.to_frame('4y z-score'),
        start=dt.datetime(2018, 1, 1), freq='W',
        title='DOE Crude total storgae (ex SPR) change in percentage - 4w SMA',
        y_axis_title='%', p2y1_axis_title='4y z-score',
        highlight_dict={'4y z-score': {"color": "red", "width": 2}},
    ))
    padd2 = inv["DOESCRU2 Index"]
    cushing = inv["DOESCROK Index"]
    padd2_cushing = padd2 - cushing
    padd2_cushing_chg = padd2_cushing.diff() / padd2_cushing
    padd2_cushing_chg_4wm = talib.mva(padd2_cushing_chg.values, 4, 'e')
    padd2_cushing_chg_4wm = pd.Series(padd2_cushing_chg_4wm, index=padd2_cushing_chg.index)
    inv_chg_4wm_by_year = ts.data_by_year(padd2_cushing_chg_4wm, freq='W', start_day=1)
    inv_chg_by_year_z = pd.DataFrame(np.nan, index=inv_chg_4wm_by_year.index, columns=inv_chg_4wm_by_year.columns)
    for i in range(window, inv_chg_4wm_by_year.shape[1]):
        for j in range(0, inv_chg_4wm_by_year.shape[0]):
            if inv_chg_4wm_by_year.columns[i] in [2021, 2022, 2023, 2024]:
                rank_window_data = inv_chg_4wm_by_year.iloc[j, i - window - 1:i]
                rank_window_data = rank_window_data.drop(2020)
                inv_chg_by_year_z.loc[j, inv_chg_4wm_by_year.columns[i]] = (inv_chg_4wm_by_year.iloc[j, i] - rank_window_data.mean()) / rank_window_data.std()
            else:
                inv_chg_by_year_z.loc[j, inv_chg_4wm_by_year.columns[i]] = (inv_chg_4wm_by_year.iloc[j, i] - inv_chg_4wm_by_year.iloc[j, i - window:i].mean()) / inv_chg_4wm_by_year.iloc[j, i - window:i].std()
    inv1 = pd.Series(np.nan, index=inv.index)
    for yr in inv_chg_by_year_z.columns:
        if len(inv1.loc[inv1.index.year == yr]) == 52:
            inv1.loc[inv1.index.year == yr] = inv_chg_by_year_z[yr].values[:-1]
        elif len(inv1.loc[inv1.index.year == yr]) == 53:
            inv1.loc[inv1.index.year == yr] = inv_chg_by_year_z[yr].values
        else:
            inv1.loc[inv1.index.year == yr] = inv_chg_by_year_z[yr].values[:len(inv1.loc[inv1.index.year == yr])]
    inv1 = inv1[inv1.index >= dt.datetime(2005, 1, 1)]
    weekdays = pd.bdate_range(dt.datetime(2005, 1, 1), inv1.index[-1]+dt.timedelta(5))
    data2 = inv1.reindex(weekdays)
    data2.fillna(method='ffill', inplace=True)
    new_idx = pd.bdate_range(dt.datetime(padd2_cushing_chg_4wm.index[-1].year, 1, 1), dt.datetime(padd2_cushing_chg_4wm.index[-1].year, 12, 31), freq="W-FRI")
    data2_chart = data2.reindex(new_idx)
    figs.append(chart.seasonal(
        df=padd2_cushing_chg_4wm * 100,
        data_p2y1=data2_chart.to_frame('4y z-score'),
        start=dt.datetime(2018, 1, 1), freq='W',
        title='DOE PADD2 - Cushing stocks change in percentage - 4w EMA',
        y_axis_title='%', p2y1_axis_title='4y z-score',
        highlight_dict={'4y z-score': {"color": "red", "width": 2}},
    ))
    actual = pyg.get_cell(db, ticker="DOEASCRD Index", field="PX_LAST")
    actual.go()
    actual = actual.data["PX_LAST"]
    whisper = pyg.get_cell(db, ticker="WHISCRUD Index", field="PX_LAST")
    whisper.go()
    whisper = whisper.data["PX_LAST"]
    actual_ = ts.reindex(actual, to_index=whisper.index)
    whisper_ = ts.reindex(whisper, to_index=actual.index, method="bfill")
    whisper_4wm = (whisper_ / total_crude).rolling(4).mean()
    whisper_4wm_by_year = ts.data_by_year(whisper_4wm, freq='W', start_day=1)
    data3 = (whisper_4wm_by_year[cur_yr] - whisper_4wm_by_year.loc[:, yr_list].mean(axis=1)) / whisper_4wm_by_year.loc[:, yr_list].std(axis=1)
    forecast_miss = pd.concat([actual_, whisper], axis=1)
    forecast_miss.columns = ["Actual", "Whisper"]
    live = bbg.live_contract(active="CLA Comdty")
    price = pyg.get_cell("contracts_PX_LAST", active="CLA Comdty", m=live["m"], y=live["y"]).go()
    price = price.data
    price_cl = price.copy()
    price = ts.reindex(price, to_index=forecast_miss.index, method="ffill")
    figs.append(chart.line_chart(
        df=forecast_miss.iloc[-52:, :], data_p2y1=price.iloc[-52:, :],
        title='DOE total change in Crude Oil inventory actual vs whisper',
        y_axis_title='kbbl', p2y1_axis_title='price', subplots=[0.7, 0.3],
        secondary_y=False, width=750, height=500,
    ))
    live_co = bbg.live_contract(active="COA Comdty")
    price_co = pyg.get_cell("contracts_PX_LAST", active="COA Comdty", m=live_co["m"], y=live_co["y"]).go()
    price_co = price_co.data
    signal = ((1 / (1 + math.e ** (-data1 * 2))) * 2 - 1)
    position = -np.sign(signal[-1]) * _unrecovered("doe_stocks_bbg.py line208 cal_size call suffix and result selection", cal_size, price_co.iloc[:, 0], 3000000, 10)
    position_yd = -np.sign(signal[-2]) * _unrecovered("doe_stocks_bbg.py line209 cal_size call suffix and result selection", cal_size, price_co.iloc[:, 0], 3000000, 10)
    live_sprd = bbg.live_spread_ticker(active="CLA Comdty", spread="12")
    price_sprd = bbg.bdh(live_sprd, ["PX_LAST"], sdate=cdr.today() - dt.timedelta(days=91), edate=cdr.today())
    factor = talib.realizedvol(price_cl['PX_LAST'].diff(), rollwindow=30, annualize=260) / talib.realizedvol(price_sprd['PX_LAST'].diff(), rollwindow=30, annualize=260)
    signal_cl = ((1 / (1 + math.e ** (-data2 * 2))) * 2 - 1)
    position_cl = -factor.iloc[-1] * signal_cl[-1] * _unrecovered("doe_stocks_bbg.py line217 cal_size call suffix and result selection", cal_size, price_cl.iloc[:, 0], 6000000)
    position_yd_cl = -factor.iloc[-2] * signal_cl[-2] * _unrecovered("doe_stocks_bbg.py line218 cal_size call suffix and result selection", cal_size, price_cl.iloc[:, 0], 6000000)
    tb = pd.DataFrame(np.nan, index=['Crude', 'PADD2-Cushing', 'Whisper'], columns=['Weekly Chg (kb)', '4w average change (%)', '4y z-score', 's-curve signal'])
    tb.loc['Crude', 'Weekly Chg (kb)'] = total_crude.diff().iloc[-1]
    tb.loc['Crude', '4w average change (%)'] = total_crude_chg_4wm.iloc[-1]
    tb.loc['Crude', '4y z-score'] = data1[data1.last_valid_index()]
    tb.loc['Crude', 's-curve signal'] = signal[signal.last_valid_index()]
    tb.loc['Crude', 'Contract'] = live_co["ticker"].split(" ")[0]
    tb.loc['Crude', 'Position'] = position
    tb.loc['Crude', 'Position chg'] = position - position_yd
    tb.loc['PADD2-Cushing', 'Weekly Chg (kb)'] = padd2_cushing.diff().iloc[-1]
    tb.loc['PADD2-Cushing', '4w average change (%)'] = padd2_cushing_chg_4wm.iloc[-1]
    tb.loc['PADD2-Cushing', '4y z-score'] = data2[data2.last_valid_index()]
    tb.loc['PADD2-Cushing', 's-curve signal'] = signal_cl[signal_cl.last_valid_index()]
    tb.loc['PADD2-Cushing', 'Contract'] = live_sprd.split(" ")[0]
    tb.loc['PADD2-Cushing', 'Position'] = position_cl
    tb.loc['PADD2-Cushing', 'Position chg'] = position_cl - position_yd_cl
    tb.loc['Whisper', 'Weekly Chg (kb)'] = whisper.iloc[-1]
    tb.loc['Whisper', '4w average change (%)'] = whisper_4wm.iloc[-1]
    tb.loc['Whisper', '4y z-score'] = data3[data3.last_valid_index()]
    tb.index.name = 'Stocks Change'
    tb.reset_index(inplace=True)
    html_table = table.html_table(tb, precision=2, format_column={
        'Stocks Change': {'width': '100px', 'text-align': 'Center'},
        'Weekly Chg (kb)': {'width': '100px', 'text-align': 'center', 'format': '{:,.0f}'},
        '4w average change (%)': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
        '4y z-score': {'width': '100px', 'text-align': 'center'},
        's-curve signal': {'width': '100px', 'text-align': 'center'},
        'Contract': {'width': '100px', 'text-align': 'center'},
        'Position': {'width': '100px', 'text-align': 'center', 'format': '{:,.0f}'},
        'Position chg': {'width': '100px', 'text-align': 'center', 'format': '{:,.0f}'},
    })
    figs.insert(0, html_table)
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("SYS - DOE-OIL", style="font-family:Calibri;", tag='h1')] + figs, f"{html_path}\\oil\\doe_stocks_sys_oil.html", task_name=report_name)
    send_email(send_to=send_to, subject="SYS - DOE-OIL", body=figs, html_path="{html_path}\\oil\\doe_stocks_sys_oil.html")


def get_oil_inventory(run_day):
    inv = bbg.bdh(['DOESCRUD Index', 'DOESCROK Index', 'DOESCRU2 Index', 'DOESTCRD Index', 'DOESTMGS Index', 'DOESDIST Index', 'DOESDIS1 Index', 'DOESDIS2 Index', 'DOESDIS3 Index'], ['PX_LAST'], sdate=dt.datetime(2004, 1, 1), edate=run_day)
    release = pd.read_csv(convert_path_to_linux(r"\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\inventory\release.csv"))
    release.set_index('Unnamed: 0', inplace=True)
    release.drop_duplicates(inplace=True)
    release.reset_index(drop=True, inplace=True)
    try:
        last_date = dt.datetime.strptime(release['value'].iloc[-1], '%Y/%m/%d %H:%M:%S')
    except:
        last_date = dt.datetime.strptime(release['value'].iloc[-1], '%m/%d/%Y %H:%M')
    if last_date <= run_day:
        release1 = bbg.bbulkref(['DOEASCRD Index'], ['ECO_FUTURE_RELEASE_DATE_LIST'], option=[("START_DT", dt.datetime.strftime(last_date, format='%Y%m%d')), ("END_DT", "20241231")])
        release = pd.concat([release, release1.to_frame('value')], axis=0, ignore_index=True)
        release.to_csv(r"\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\inventory\release.csv")
    sdate = dt.datetime(2005, 1, 5)
    sloc_release = np.where(pd.to_datetime(release['value']) >= sdate)[0][0]
    sloc = np.where(inv.index < sdate)[0][-1]
    eloc = np.where(pd.to_datetime(release['value']) > inv.index[-1])[0][0]
    inv['release'] = np.nan
    inv.loc[inv.index[sloc]:, 'release'] = release['value'].iloc[sloc_release:eloc + 1].values
    inv.drop(inv[inv['release'].isna()].index, inplace=True)
    inv = inv.reset_index().set_index('release')
    inv.index = pd.to_datetime(inv.index)
    inv.index = inv.index.normalize()
    inv.to_csv(convert_path_to_linux(_unrecovered("doe_stocks_bbg.py line289 model DOE CSV filename suffix", r"\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\model\DOE")))
    return inv


def cal_size(price, size_per_trade=2000000, target_vol=10, shift=1, vpp=1000, currency="USD"):
    """
    input is pandas series
    """
    price_d = price.diff() / price.shift(1) * 100
    vol = talib.realizedvol(price_d, rollwindow=30, annualize=260)
    if shift == 0:
        size_in_usd = size_per_trade * target_vol / vol
    else:
        size_in_usd = size_per_trade * target_vol / vol.shift(shift)
    if currency == 'USD':
        return size_in_usd / (vpp * price)
    else:
        if currency == 'EUR':
            if len(price) > 0:
                eur = bbg.bdh('EURUSD Curncy', ['PX_LAST'], price.index[0], price.index[-1])
                eur = eur['PX_LAST'].reindex(price.index)
            else:
                eur = bbg.bdh('EURUSD Curncy', ['PX_LAST'], cdr.today(), cdr.today())
            return size_in_usd / (vpp * price * eur)
        else:
            raise Exception('Base currency is not USD!')


def eia_dataset(id):
    api_key = os.environ['ENERGY_ASPECTS_API_KEY']
    dataset_details_url = 'https://api.energyaspects.com/data/datasets/timeseries/'
    return dataset_details_url + id + f'?api_key={api_key}'


def eia_release_schedule(id):
    to_retrieve = {"name": id}
    releases = {}
    for dataset in to_retrieve:
        ids = to_retrieve[dataset].split(",")
        cnt = 0
        success = False
        while not success or cnt > len(id.split(',')):
            try:
                response = pd.read_json(eia_dataset(ids[cnt]))
                releases[dataset] = response.metadata.release_dates[-20:]
                success = True
            except:
                cnt += 1
    histreleases = pd.DataFrame.from_dict(releases)
    histreleases = histreleases.sort_values(by=['name'], ascending=False)
    col_one_list = []
    col_one_list.append(histreleases['name'].iloc[0])
    col_one_list.append(histreleases.loc[pd.to_datetime(histreleases['name']) <= pd.to_datetime(histreleases['name'].iloc[0]) - relativedelta(months=1)].iloc[0, 0])
    return col_one_list


def data_by_year_min_max_avg(demand, ytd=False):
    demand_by_year = ts.data_by_year(demand, freq="W")
    if len(demand_by_year) > 52:
        demand_by_year = demand_by_year.iloc[:52, :]
    if ytd:
        demand_by_year = demand_by_year.cumsum(axis=0)
    demand_by_year['Max'] = demand_by_year.loc[:, [2018, 2019, 2021, 2023, 2024, 2025]].max(axis=1)
    demand_by_year['Min'] = demand_by_year.loc[:, [2018, 2019, 2021, 2023, 2024, 2025]].min(axis=1)
    demand_by_year['2018-2025 Avg'] = demand_by_year.loc[:, [2018, 2019, 2021, 2023, 2024, 2025]].mean(axis=1)
    return demand_by_year.iloc[:, -6:]


def seasonal_chart_min_max_avg(demand_by_year, title, y_axis_title=None, y_range=None, width=750, height=500):
    cur_yr = demand_by_year.columns[2]
    data1 = demand_by_year[cur_yr] - demand_by_year.iloc[:, 5]
    data1 = data1.to_frame("Cur Yr vs 5y Avg")
    data1["Cur Yr vs Y-1"] = demand_by_year[cur_yr] - demand_by_year.iloc[:, 1]
    if "EA latest" in demand_by_year.columns:
        return chart.line_chart(
            df=demand_by_year, data_p2y1=data1, subplots=[0.7, 0.3],
            title=title, y_axis_title=y_axis_title,
            highlight_dict={
                demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                demand_by_year.columns[2]: {"color": "#ff7f0e", "width": 2},
                "Max": {"color": "lightgrey", "width": 0},
                "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                "EA latest": {"color": "blue", "width": 2},
                "EA previous": {"color": "blue", "width": 2, "dash": "dash"},
                "2018-2025 Avg": {"color": "black", "width": 2, "dash": "dash"},
                "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
                "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            }, tickformat=None, y_range=y_range, width=width, height=height,
        )
    elif "Consensus" in demand_by_year.columns:
        return chart.line_chart(
            df=demand_by_year, data_p2y1=data1, subplots=[0.7, 0.3],
            title=title, y_axis_title=y_axis_title,
            highlight_dict={
                demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                demand_by_year.columns[2]: {"color": "#ff7f0e", "width": 2},
                "Max": {"color": "lightgrey", "width": 0},
                "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                "Consensus": {"color": "blue", "width": 2, "dash": "dash"},
                "2018-2025 Avg": {"color": "black", "width": 2, "dash": "dash"},
                "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
                "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            }, tickformat=None, y_range=y_range, width=width, height=height,
        )
    else:
        return chart.line_chart(
            df=demand_by_year, data_p2y1=data1, subplots=[0.7, 0.3],
            title=title, y_axis_title=y_axis_title,
            highlight_dict={
                demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                demand_by_year.columns[2]: {"color": "#ff7f0e", "width": 2},
                "Max": {"color": "lightgrey", "width": 0},
                "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                
                "2018-2025 Avg": {"color": "black", "width": 2, "dash": "dash"},
                "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
                "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
            }, tickformat=None, y_range=y_range, width=width, height=height,
        )


def new_stocks_chart(data, title, **kwargs):
    ytd = kwargs.get("ytd", False)
    cum_ytd = kwargs.get("cum_ytd", False)
    ex_year = kwargs.get("ex_year", [2020])
    freq = kwargs.get("freq", "W")
    y_axis_title = kwargs.get("y_axis_title", 'kb')
    p1y2_axis_title = kwargs.get("p1y2_axis_title", 'kb')
    width = kwargs.get("width", 750)
    height = kwargs.get("height", 500)
    data_by_year = ts.data_by_year(data, freq=freq)
    if len(data_by_year) > 52:
        data_by_year = data_by_year.iloc[:52, :]
    if ytd:
        data_by_year = data_by_year - data_by_year.iloc[0, :]
    elif cum_ytd:
        data_by_year = data_by_year.cumsum(axis=0)
    if ex_year is not None:
        data_by_year.drop(ex_year, axis=1, inplace=True)
    cur_yr = data_by_year.iloc[:, -1]
    last_yr = data_by_year.iloc[:, -2]
    avg_yr = data_by_year.iloc[:, :-1].mean(axis=1)
    data_by_year["Delta vs Average"] = cur_yr - avg_yr
    data_by_year["Delta vs Last Year"] = cur_yr - last_yr
    data_by_year = data_by_year.iloc[:, -3:]
    fig = chart.line_chart(
        df=data_by_year.iloc[:, -2:], data_p1y2=data_by_year.iloc[:, [0]],
        title=title, secondary_y=True,
        highlight_dict={
            data_by_year.columns[0]: {"color": "black", "width": 2},
            data_by_year.columns[1]: {"mode": "bars"},
            data_by_year.columns[2]: {"mode": "bars"},
        }, width=width, height=height, y_axis_title=y_axis_title,
        p1y2_axis_title=p1y2_axis_title, tickformat=False,
    )
    return fig


def create_stocks_table(maindata):
    latest = maindata.copy()
    latest = latest.iloc[-1:]
    latest = latest.T
    latest.columns = ['Latest']
    fourweekaverage = maindata.rolling(window=4).mean()
    fourweekaverage['Change in stock (kbd)'] = (maindata['Stocks'].diff())
    fourweekaverage['Change in stock (kbd)'] = fourweekaverage['Change in stock (kbd)'].rolling(window=4).mean() / 7
    fourweekaverage['Stocks'] = fourweekaverage['Stocks']
    fourweekaverage = fourweekaverage.iloc[-1:]
    fourweekaverage = fourweekaverage.T
    fourweekaverage.columns = ['4 week average']
    oneweekchange = maindata.diff()
    oneweekchange['Change in stock (kbd)'] = oneweekchange['Stocks'] / 7
    oneweekchange['Stocks'] = oneweekchange['Stocks']
    oneweekchange = oneweekchange.iloc[-1:]
    oneweekchange = oneweekchange.T
    oneweekchange.columns = ['1 week change']
    fourweekchange = maindata.diff(periods=4)
    fourweekchange['Change in stock (kbd)'] = fourweekchange['Stocks'] / 28
    fourweekchange['Stocks'] = fourweekchange['Stocks']
    fourweekchange = fourweekchange.iloc[-1:]
    fourweekchange = fourweekchange.T
    fourweekchange.columns = ['4 week change']
    week_num = maindata.index.strftime('%W').astype('int')
    years = maindata.index.year
    current_week = week_num[-1]
    current_year = years[-1]
    maindata['Change in stock (kbd)'] = (maindata['Stocks'].diff()) / 7
    maindata_4wc = maindata.diff(periods=4)
    fourweekaverage1 = maindata_4wc.loc[(years == current_year - 1) & (week_num == current_week), :]
    fourweekaverage1['Stocks'] = fourweekaverage1['Stocks']
    fourweekaverage1 = fourweekaverage1.T
    fourweekaverage1.columns = ['4w chg Y-1']
    fourweekaverage2 = maindata_4wc.loc[(years.isin([2018, 2019, 2021, 2023, 2024, 2025])) & (week_num == current_week), :].mean(axis=0)
    fourweekaverage2 = fourweekaverage2.to_frame('4w chg 18-25')
    fourweekaverage2_next = maindata_4wc.shift(-4).loc[(years.isin([2018, 2019, 2021, 2023, 2024, 2025])) & (week_num == current_week), :].mean(axis=0)
    fourweekaverage2_next = fourweekaverage2_next.to_frame('Next 4w chg 18-25')
    yoy = maindata.iloc[-1, :] - maindata.loc[(years == current_year - 1) & (week_num == current_week), :]
    yoy = yoy.T
    yoy.columns = ['YoY chg']
    tbl = pd.concat([latest, oneweekchange, fourweekchange, fourweekaverage1, fourweekaverage2, fourweekaverage2_next, yoy], axis=1)
    tbl.loc[tbl.index[:-1], "last_update"] = maindata.apply(pd.Series.last_valid_index).dt.strftime("%Y-%m-%d")
    tbl.rename(index={'Stocks': 'Stocks (kb)'}, inplace=True)
    return tbl


def eia_stocks():
    figs = []
    sdate = dt.datetime(2015, 1, 1)
    edate = cdr.today()
    demand = bbg.bdh('DOEDTPRD Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    demand = demand["PX_LAST"]
    stocks = bbg.bdh('DOESESPR Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    stocks = stocks["PX_LAST"]
    runs = bbg.bdh('DOEPCRIN Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    runs = runs["PX_LAST"]
    stockscrude = bbg.bdh('DOESCRUD Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    stockscrude = stockscrude["PX_LAST"]
    disty = bbg.bdh('DOESDIST Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty = disty["PX_LAST"]
    mogas = bbg.bdh('DOESTMGS Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    mogas = mogas["PX_LAST"]
    jet = bbg.bdh('DOESJETK Index', ["PX_LAST"], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    jet = jet["PX_LAST"]
    dem_sto = pd.concat([stocks, stockscrude, mogas, disty, runs, demand], axis=1)
    dem_sto.columns = ["Liquids", "Crude", "Gasoline", "Distillates", "Runs", "Demand"]
    dem_sto_tb = pd.DataFrame(0, index=['Latest', '1 week change', '4 week change'], columns=["Liquids", "Crude", "Gasoline", "Distillates", "Runs", "Demand"])
    dem_sto_tb.loc['Latest', :] = dem_sto.iloc[-1, :]
    dem_sto_tb.loc['1 week change', :] = dem_sto.diff().iloc[-1, :]
    dem_sto_tb.loc['4 week change', :] = dem_sto.iloc[-1, :] - dem_sto.iloc[-5, :]
    dem_sto_tb.loc['4 week change', 'Demand'] = dem_sto.rolling(4).mean().iloc[-1, -1]
    dem_sto['week num'] = dem_sto.index.strftime('%W').astype('int')
    dem_sto['year'] = dem_sto.index.year
    current_week = dem_sto['week num'].iloc[-1]
    current_year = dem_sto['year'].iloc[-1]
    dem_sto_4wc = dem_sto[["Liquids", "Crude", "Gasoline", "Distillates", "Runs", "Demand"]].diff(periods=4)
    dem_sto_4wc['week num'] = dem_sto['week num']
    dem_sto_4wc['year'] = dem_sto['year']
    dem_sto_tb.loc['4w chg Y-1', :] = (dem_sto_4wc.loc[(dem_sto_4wc['year'] == current_year - 1) & (dem_sto_4wc['week num'] == current_week), :]).iloc[0, :]
    dem_sto_tb.loc['4w chg 18-25', :] = (dem_sto_4wc.loc[(dem_sto_4wc['year'].isin([2018, 2019, 2021, 2023, 2024, 2025])) & (dem_sto_4wc['week num'] == current_week), :]).mean(axis=0)
    dem_sto_tb.loc['Next 4w chg 18-25', :] = (dem_sto_4wc.shift(-4).loc[(dem_sto_4wc['year'].isin([2018, 2019, 2021, 2023, 2024, 2025])) & (dem_sto_4wc['week num'] == current_week), :]).mean(axis=0)
    dem_sto_tb.loc['YoY chg', :] = (dem_sto.iloc[-1, :] - dem_sto.loc[(dem_sto['year'] == current_year - 1) & (dem_sto['week num'] == current_week), :]).iloc[0, :]
    dem_sto_tb.loc['4w chg Y-1', 'Demand'] = (dem_sto[['Demand']].rolling(4).mean()).loc[(dem_sto['year'] == current_year - 1) & (dem_sto['week num'] == current_week)].iloc[0, 0]
    dem_sto_tb.loc['4w chg 18-25', 'Demand'] = (dem_sto[['Demand']].rolling(4).mean()).loc[(dem_sto['year'].isin([2018, 2019, 2021, 2023, 2024, 2025])) & (dem_sto['week num'] == current_week)].mean().iloc[0]
    dem_sto_tb.loc['Next 4w chg 18-25', 'Demand'] = (dem_sto[['Demand']].rolling(4).mean().shift(-4)).loc[(dem_sto['year'].isin([2018, 2019, 2021, 2023, 2024, 2025])) & (dem_sto['week num'] == current_week)].mean().iloc[0]
    dem_sto_tb = dem_sto_tb.T
    dem_sto_tb.loc[:, "last_update"] = dem_sto[["Liquids", "Crude", "Gasoline", "Distillates", "Runs", "Demand"]].apply(pd.Series.last_valid_index).dt.strftime("%Y-%m-%d")
    dem_sto_tb.index.name = 'Total'
    dem_sto_tb.index = ["Demand (Outright)" if x == "Demand" else x for x in dem_sto_tb.index]
    dem_sto_tb = dem_sto_tb.reset_index()
    figs.append(table.html_format(df=dem_sto_tb, header="Runs, Demand and Stocks (mb), average 4w level for Demand", show_date=True, precision=0, format_column={tuple(dem_sto_tb.columns): {'width': '120px', 'text-align': 'center'}}))
    total_liquids_chart = chart.seasonal_chart(
        df=(stocks.loc[stocks.index >= dt.datetime(2017, 1, 1)]).to_frame("stocks"),
        title="Total liquids stock", freq="W",
        highlight={
            stocks.index[-1].year: {"width": 2, "color": "black", "mode": "lines+markers"},
            stocks.index[-1].year - 1: {"width": 1, "color": "blue"},
            "Cur Yr vs 5y Avg": {"color": "black", "width": 1},
            "Cur Yr vs Y-1": {"color": "black", "dash": "dash", "width": 1},
        }, y_axis_title='kb', x_axis_title='Date', width=750, height=500,
    )
    stocks_2017 = stocks.loc[stocks.index >= dt.datetime(2017, 1, 1)]
    data_by_year = ts.data_by_year(stocks_2017, freq='W')
    data_by_year0 = data_by_year - data_by_year.iloc[0, :]
    dts = pd.date_range(dt.datetime(data_by_year0.columns[-1], 1, 1), dt.datetime(data_by_year0.columns[-1], 12, 31), freq='W')
    if len(dts) < data_by_year0.shape[0]:
        data_by_year0 = data_by_year0.iloc[:len(dts), :]
    data_by_year0['Date'] = dts
    data_by_year0 = data_by_year0.set_index('Date')
    data_by_year0.drop([2020], axis=1, inplace=True)
    data1 = data_by_year0.iloc[:, -1] - data_by_year0.iloc[:, -6:-1].mean(axis=1)
    data1 = data1.to_frame('Cur Yr vs Avg')
    data1['Cur Yr vs Yr-1'] = data_by_year0.iloc[:, -1] - data_by_year0.iloc[:, -2]
    ytd_liquids_chart = chart.line_chart(
        df=data_by_year0, data_p2y1=data1, subplots=[0.7, 0.3],
        highlight_dict={
            data_by_year0.columns[-1]: {"color": "black", "width": 2, "mode": "lines+markers"},
            data_by_year0.columns[-2]: {"color": "blue", "width": 2},
            'Cur Yr vs Avg': {"color": "black"}, 'Cur Yr vs Yr-1': {"color": "black", "dash": "dash"},
        }, title="YTD change of liquids stocks", y_axis_title='kb', width=750, height=500,
    )
    figs.append([total_liquids_chart, ytd_liquids_chart])
    tracker_figs = tracker_charts()
    figs += tracker_figs
    demand_by_year = data_by_year_min_max_avg(demand)
    ea_demand = _unrecovered("doe_stocks_bbg.py line636 Energy Aspects dataset ID list suffix", '818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,834,835,836,837,838,839,84')
    col_one_list = eia_release_schedule(ea_demand)
    overall = pd.DataFrame()
    for i in range(0, len(col_one_list)):
        newdata = dv.energy_aspects(dataset_id=ea_demand, start='2010-01-01', release_date=col_one_list[i])
        dataneeded = kpler.convert_to_ts(newdata, columns=['Monthly EA forecast for liquids demand in United States in kb/d'], forecast=True)
        dataneeded.columns = ['{}'.format(col_one_list[i])]
        overall = pd.concat([overall, dataneeded], axis=1)
    overall.index = pd.to_datetime(overall.index)
    overall = overall.reindex(pd.date_range(overall.index[0], overall.index[-1], freq='W-FRI'), method='ffill')
    overall = overall.loc[(overall.index >= dt.datetime(edate.year, 1, 1)) & (overall.index <= dt.datetime(edate.year, 12, 31))]
    try:
        demand_by_year.loc[:len(overall), "EA latest"] = overall.iloc[:, 0].values
    except:
        demand_by_year.loc[:len(overall)-1, "EA latest"] = overall.iloc[:, 0].values
    total_supply_chart = seasonal_chart_min_max_avg(demand_by_year, title="Total Product Supplied", y_axis_title="Demand")
    data4wk = bbg.bdh('DOEDTPS4 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    seasonal = data_by_year_min_max_avg(data4wk['PX_LAST'])
    try:
        seasonal['vs 2018-2025 Avg'] = seasonal[edate.year] - seasonal['2018-2025 Avg']
        seasonal['vs 24'] = seasonal[edate.year] - seasonal[2024]
        seasonal['vs 25'] = seasonal[edate.year] - seasonal[2025]
    except:
        seasonal['vs 2018-2025 Avg'] = seasonal[edate.year - 1] - seasonal['2018-2025 Avg']
        seasonal['vs 24'] = seasonal[edate.year - 1] - seasonal[2024]
        seasonal['vs 25'] = seasonal[edate.year - 1] - seasonal[2025]
    seasonal = seasonal.iloc[:, -3:]
    if len(seasonal.dropna(how="all", axis=0)) < 2:
        seasonal.loc[1, :] = seasonal.loc[0, :]
    total_supply_4wmv_chart = chart.line_chart(df=seasonal, title='Total Oil Product Supplied 4 week avg vs history', tickformat=None, width=750, height=500)
    figs.append([total_supply_chart, total_supply_4wmv_chart])
    runs = bbg.bdh('DOEPCRIN Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    runs_by_year = data_by_year_min_max_avg(runs['PX_LAST'])
    crude_runs_chart = seasonal_chart_min_max_avg(runs_by_year, title="Crude runs", y_axis_title="Runs")
    stockscrude = bbg.bdh('DOESCRUD Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    stockscrude_chg = stockscrude['PX_LAST'].diff()
    stockscrude_by_year = data_by_year_min_max_avg(stockscrude_chg, ytd=True)
    consen_data = pd.read_csv(convert_path_to_linux(_unrecovered("doe_stocks_bbg.py line688 consensus CSV filename suffix", r"\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\oil\Consensus Cru")))
    consen_data = consen_data.loc[consen_data['US balances'] == 'Street', :]
    consen_data.set_index('US balances', inplace=True)
    consen_data = (consen_data.T).iloc[:, 0]
    consen_data.index = [dt.datetime.strptime(f"{x}-2023", '%b-%Y') for x in consen_data.index]
    consen_data = pd.Series([consen_data[x] / x.days_in_month for x in consen_data.index], index=consen_data.index)
    days = pd.date_range(consen_data.index[0], consen_data.index[-1] + relativedelta(day=31), freq='d')
    consen_data_d = consen_data.reindex(days, method='ffill')
    consen_data_cd = consen_data_d.cumsum()
    wks = pd.date_range(consen_data.index[0], consen_data.index[-1] + relativedelta(day=31), freq='W-FRI')
    consen_data_cw = consen_data_cd.reindex(wks)
    stockscrude_by_year['Consensus'] = consen_data_cw.iloc[:len(stockscrude_by_year)].values
    crude_stocks_chart = seasonal_chart_min_max_avg(stockscrude_by_year, title="Crude Stock YTD change", y_axis_title="Stocks")
    figs.append([crude_runs_chart, crude_stocks_chart])
    disty = bbg.bdh('DOESDIST Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty_chg = disty['PX_LAST'].diff()
    disty_by_year = data_by_year_min_max_avg(disty_chg, ytd=True)
    disty_chart = seasonal_chart_min_max_avg(disty_by_year, title='Disty Stock YTD change', y_axis_title="Stocks")
    mogas = bbg.bdh('DOESTMGS Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    mogas_chg = mogas['PX_LAST'].diff()
    mogas_by_year = data_by_year_min_max_avg(mogas_chg, ytd=True)
    mogas_chart = seasonal_chart_min_max_avg(mogas_by_year, title='Mogas Stock YTD change', y_axis_title="Stocks")
    figs.append([disty_chart, mogas_chart])
    return figs, stocks.loc[stocks.index >= dt.datetime(2017, 1, 1)], jet.loc[jet.index >= dt.datetime(2017, 1, 1)]


def eia_crude():
    figs = []
    sdate = dt.datetime(2015, 1, 1)
    edate = cdr.today()
    maindata = bbg.bdh(['DOETCRUD Index', 'DOEICISP Index', 'DOESCRUD Index', 'DOEPCRIN Index', 'DOEBCEXP Index', _unrecovered("doe_stocks_bbg.py line723 adjustment ticker suffix", 'DOESUNC')], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    maindata.columns = ['Production', 'Imports', 'Stocks', 'Runs', 'Exports', 'Adjustment']
    maindata = maindata[['Stocks', 'Runs', 'Exports', 'Production', 'Imports', 'Adjustment']]
    tbl = create_stocks_table(maindata)
    consensus_crude = dv.energy_aspects(dataset_id="6470", start="2023-01-01")
    ea_last_update = dv.ea_release_dates(dataset_id="6470")
    consensus_crude.set_index("Date", inplace=True)
    consensus_crude.index = pd.to_datetime(consensus_crude.index)
    consensus_crude = consensus_crude * 1000
    consensus_crude = consensus_crude.iloc[:, 0]
    consensus_crude = pd.Series([consensus_crude[x] / x.days_in_month for x in consensus_crude.index], index=consensus_crude.index)
    days = pd.date_range(consensus_crude.index[0], consensus_crude.index[-1] + relativedelta(day=31), freq='d')
    consen_data_d = consensus_crude.reindex(days, method='ffill')
    consen_stock_1w = consen_data_d[maindata.index[-2] + relativedelta(days=1):maindata.index[-1]].mean()
    consen_stock_4w = consen_data_d[maindata.index[-5] + relativedelta(days=1):maindata.index[-1]].mean()
    consen_stock_kbd = pd.DataFrame([np.nan, consen_stock_1w, consen_stock_4w, np.nan, np.nan, np.nan, *_unrecovered("doe_stocks_bbg.py line746 remaining consensus row entries")], columns=['Consensus Stocks chg (kbd)'], index=tbl.columns).T
    tbl = pd.concat([tbl, consen_stock_kbd], axis=0)
    tbl.index.name = 'EIA Crude'
    tbl = tbl.reset_index()
    figs.append(table.html_format(df=tbl, header="DOE Crude report detailed", show_date=True, precision=0, format_column={tuple(tbl.columns): {'width': '120px', 'text-align': 'center'}}))
    crude_stocks_chart = new_stocks_chart(
        data=(maindata.loc[maindata.index >= dt.datetime(2017, 1, 1), "Stocks"]),
        title="Total crude stocks", y_axis_title="Storage vs past (kb)", p1y2_axis_title="Total Storage (kb)",
        ytd=False, cum_ytd=False, ex_year=[2020], freq="W", width=750, height=500,
    )
    disty_p2 = bbg.bdh('DOESCRU2 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty_p3 = bbg.bdh('DOESCRU3 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty = disty_p2 + disty_p3
    disty_chg = disty['PX_LAST']
    disty_by_year = data_by_year_min_max_avg(disty_chg, ytd=False)
    p2_stocks_chart = seasonal_chart_min_max_avg(disty_by_year, title="P2+P3 stock", y_axis_title="Stocks (mb)")
    disty = bbg.bdh('DOESCROK Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty_chg = disty['PX_LAST']
    disty_by_year = data_by_year_min_max_avg(disty_chg, ytd=False)
    cushing_chart = seasonal_chart_min_max_avg(disty_by_year, title="Cushing stock", y_axis_title="Stocks (mb)")
    around_cushing = bbg.bdh(['DOESCRU2 Index', 'DOESCRU3 Index', 'DOESCROK Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    around_cushing.columns = ['p2 Stocks', 'p3 Stocks', 'Cush Stocks']
    around_cushing['Stocks'] = around_cushing['p2 Stocks'] + around_cushing['p3 Stocks'] - around_cushing['Cush Stocks']
    ac_by_year = data_by_year_min_max_avg(around_cushing['Stocks'])
    around_cushing_stock = seasonal_chart_min_max_avg(ac_by_year, title="Oil Around Cushing", y_axis_title="Stocks (mb)")
    figs.append([crude_stocks_chart, cushing_chart])
    figs.append([around_cushing_stock, p2_stocks_chart])
    runs = bbg.bdh('DOEPCRIN Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    runs_by_year = data_by_year_min_max_avg(runs['PX_LAST'])
    crude_runs_chart = seasonal_chart_min_max_avg(runs_by_year, title="Crude runs", y_axis_title="Runs")
    production = bbg.bdh('DOETCRUD Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    production_by_year = data_by_year_min_max_avg(production['PX_LAST'])
    crude_production_chart = seasonal_chart_min_max_avg(production_by_year, title="Crude production", y_axis_title="Production")
    export_by_year = data_by_year_min_max_avg(maindata['Exports'])
    export_chart = seasonal_chart_min_max_avg(export_by_year, title="Exports", y_axis_title="Exports")
    figs.append([crude_runs_chart, crude_production_chart])
    yieldsdata = bbg.bdh(['DEPWIMCA Index', 'DEPWIMSA Index', 'DEPWIMMX Index', 'DEPWIMIQ Index', 'DEPWIMCO Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    yieldsdata.columns = ['Canada', 'Saudi', 'Mexico', 'Iraq', 'Colombia']
    yieldsdata['Sour Proxy'] = yieldsdata.sum(axis=1)
    sour_by_year = data_by_year_min_max_avg(yieldsdata['Sour Proxy'])
    sour_import = seasonal_chart_min_max_avg(sour_by_year, title="Sour imports", y_axis_title="Imports")
    canada_by_year = data_by_year_min_max_avg(yieldsdata['Canada'])
    canada_import = seasonal_chart_min_max_avg(canada_by_year, title="Canada imports", y_axis_title="Imports")
    saudi_by_year = data_by_year_min_max_avg(yieldsdata['Saudi'])
    saudi_import = seasonal_chart_min_max_avg(saudi_by_year, title="Saudi imports", y_axis_title="Imports")
    figs.append([export_chart, sour_import])
    figs.append([canada_import, saudi_import])
    return figs, maindata.loc[maindata.index >= dt.datetime(2017, 1, 1), "Stocks"]


def eia_mogas():
    figs = []
    sdate = dt.datetime(2015, 1, 1)
    edate = cdr.today()
    maindata = bbg.bdh(['DOETMGLA Index', 'DOEIMGAS Index', 'DOESTMGS Index', 'DOEDMGAS Index', 'DOEPCRIN Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    maindata.columns = ['Production', 'Imports', 'Stocks', 'Demand', 'Runs']
    maindata = maindata[['Stocks', 'Demand', 'Runs', 'Production', 'Imports']]
    tbl = create_stocks_table(maindata)
    tbl.index.name = 'EIA Mogas'
    tbl = tbl.reset_index()
    figs.append(table.html_format(df=tbl, header="DOE Mogas report detailed", show_date=True, precision=0, format_column={tuple(tbl.columns): {'width': '120px', 'text-align': 'center'}}))
    mogas_chart = new_stocks_chart(
        data=(maindata.loc[maindata.index >= dt.datetime(2017, 1, 1), "Stocks"]),
        title="Total Mogas stocks", y_axis_title="Storage vs past (kb)", p1y2_axis_title="Total Storage (kb)",
        ytd=False, cum_ytd=False, ex_year=[2020], freq="W", width=750, height=500,
    )
    demand_by_year = data_by_year_min_max_avg(maindata['Demand'])
    demand_chart = seasonal_chart_min_max_avg(demand_by_year, title="Demand", y_axis_title="Demand", y_range=_unrecovered("doe_stocks_bbg.py line869 demand chart y_range"))
    data4wk = bbg.bdh('DOEDMG4 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    seasonal = data_by_year_min_max_avg(data4wk['PX_LAST'])
    try:
        seasonal['vs 2018-2025 Avg'] = seasonal[edate.year] - seasonal['2018-2025 Avg']
        seasonal['vs 24'] = seasonal[edate.year] - seasonal[2024]
        seasonal['vs 25'] = seasonal[edate.year] - seasonal[2025]
    except:
        seasonal['vs 2018-2025 Avg'] = seasonal[edate.year - 1] - seasonal['2018-2025 Avg']
        seasonal['vs 24'] = seasonal[edate.year - 1] - seasonal[2024]
        seasonal['vs 25'] = seasonal[edate.year - 1] - seasonal[2025]
    seasonal = seasonal.iloc[:, -3:]
    if len(seasonal.dropna(how="all", axis=0)) < 2:
        seasonal.loc[1, :] = seasonal.loc[0, :]
    demand_4w_chart = chart.line_chart(df=seasonal, title='Mogas Product Supplied 4 week avg vs history', tickformat=None, width=750, height=500)
    disty = bbg.bdh('DOESGAS1 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty_chg = disty['PX_LAST'].diff()
    disty_by_year = data_by_year_min_max_avg(disty_chg, ytd=True)
    p1_mogas_chart = seasonal_chart_min_max_avg(disty_by_year, title="P1 Mogas stock change", y_axis_title="Stocks")
    yieldsdata = bbg.bdh(['DOETMGP3 Index', 'DOEPFEP3 Index', 'DOEPBCP3 Index', 'DOEPCRP3 Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    yieldsdata.columns = ['Prod', 'Ethanol', 'MGBC', 'Runs']
    yieldsdata['Yield'] = (yieldsdata['Prod'] - yieldsdata['Ethanol'] - yieldsdata['MGBC']) / yieldsdata['Runs']
    yield_by_year = data_by_year_min_max_avg(yieldsdata['Yield'])
    p3_yield_chart = seasonal_chart_min_max_avg(yield_by_year, title="P3 yields", y_axis_title="Yields")
    demdata = bbg.bdh(['DOEPFEP1 Index', 'DOEPBCP5 Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    demdata.columns = ['P1 Implied', 'P5 Implied']
    p1_by_year = data_by_year_min_max_avg(demdata['P1 Implied'])
    p1_demand_chart = seasonal_chart_min_max_avg(p1_by_year, title="P1 demand", y_axis_title="Demand")
    p5_by_year = data_by_year_min_max_avg(demdata['P5 Implied'])
    p5_demand_chart = seasonal_chart_min_max_avg(p5_by_year, title="P5 demand", y_axis_title="Demand")
    p123stocks = bbg.bdh(['DOESGAS1 Index', 'DOESGAS2 Index', 'DOESGAS3 Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    p123stocks['Stocks'] = p123stocks.sum(axis=1)
    p123_by_year = data_by_year_min_max_avg(p123stocks['Stocks'])
    p123_chart = seasonal_chart_min_max_avg(p123_by_year, title="P1+P2+P3 stocks", y_axis_title="Stocks")
    figs.append([mogas_chart, p123_chart])
    figs.append([demand_chart, demand_4w_chart])
    figs.append([p1_mogas_chart, p1_demand_chart])
    figs.append([p3_yield_chart, p5_demand_chart])
    return figs, maindata.loc[maindata.index >= dt.datetime(2017, 1, 1), "Stocks"]


def eia_disty():
    figs = []
    sdate = dt.datetime(2015, 1, 1)
    edate = cdr.today()
    maindata = bbg.bdh(['DOETDIST Index', 'DOEBDIST Index', 'DOESDIST Index', 'DOEDDIST Index', 'DOEPCRIN Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    maindata.columns = ['Production', 'Exports', 'Stocks', 'Demand', 'Runs']
    maindata = maindata[['Stocks', 'Demand', 'Runs', 'Production', 'Exports']]
    tbl = create_stocks_table(maindata)
    tbl.index.name = 'EIA Disty'
    tbl = tbl.reset_index()
    figs.append(table.html_format(df=tbl, header="DOE Disty report detailed", show_date=True, precision=0, format_column={tuple(tbl.columns): {'width': '120px', 'text-align': 'center'}}))
    disty_chart = new_stocks_chart(
        data=(maindata.loc[maindata.index >= dt.datetime(2017, 1, 1), "Stocks"]),
        title="Total Distillate stocks", y_axis_title="Storage vs past (kb)", p1y2_axis_title="Total Storage (kb)",
        ytd=False, cum_ytd=False, ex_year=[2020], freq="W", width=750, height=500,
    )
    demand_by_year = data_by_year_min_max_avg(maindata["Demand"])
    disty_demand_chart = seasonal_chart_min_max_avg(demand_by_year, title="Demand", y_axis_title="Demand", **_unrecovered("doe_stocks_bbg.py line967 demand chart trailing arguments"))
    data4wk = bbg.bdh('DOEDDFO4 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    seasonal = data_by_year_min_max_avg(data4wk['PX_LAST'])
    try:
        seasonal['vs 2018-2025 Avg'] = seasonal[edate.year] - seasonal['2018-2025 Avg']
        seasonal['vs 24'] = seasonal[edate.year] - seasonal[2024]
        seasonal['vs 25'] = seasonal[edate.year] - seasonal[2025]
    except:
        seasonal['vs 2018-2025 Avg'] = seasonal[edate.year - 1] - seasonal['2018-2025 Avg']
        seasonal['vs 24'] = seasonal[edate.year - 1] - seasonal[2024]
        seasonal['vs 25'] = seasonal[edate.year - 1] - seasonal[2025]
    seasonal = seasonal.iloc[:, -3:]
    if len(seasonal.dropna(how="all", axis=0)) < 2:
        seasonal.loc[1, :] = seasonal.loc[0, :]
    disty_demand_4w_chart = chart.line_chart(df=seasonal, title='Disty Product Supplied 4 week avg vs history', tickformat=None, width=750, height=500)
    disty = bbg.bdh('DOESDIS1 Index', ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    disty_chg = disty['PX_LAST'].diff()
    disty_by_year = data_by_year_min_max_avg(disty_chg, ytd=True)
    p1_disty_chart = seasonal_chart_min_max_avg(disty_by_year, title="P1 Disty stock change", y_axis_title="Stocks")
    p123stocks = bbg.bdh(['DOESDIS1 Index', 'DOESDIS2 Index', 'DOESDIS3 Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    p123stocks['Stocks'] = p123stocks.sum(axis=1)
    p123_by_year = data_by_year_min_max_avg(p123stocks['Stocks'])
    p123_disty_chart = seasonal_chart_min_max_avg(p123_by_year, title="P1+P2+P3 stocks", y_axis_title="Stocks")
    yieldsdata = bbg.bdh(['DOETDIP3 Index', 'DOEPFEP3 Index', 'DOEPBCP3 Index', 'DOEPCRP3 Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    yieldsdata.columns = ['Prod', 'Ethanol', 'MGBC', 'Runs']
    yieldsdata['Yield'] = (yieldsdata['Prod']) / yieldsdata['Runs']
    yield_by_year = data_by_year_min_max_avg(yieldsdata['Yield'])
    p3_yield_chart = seasonal_chart_min_max_avg(yield_by_year, title="P3 yields", y_axis_title="Yields")
    disty_chg = p123stocks['DOESDIS3 Index'].diff()
    disty_by_year = data_by_year_min_max_avg(disty_chg, ytd=True)
    p3_disty_chart = seasonal_chart_min_max_avg(disty_by_year, title="P3 Disty stock change", y_axis_title="Stocks")
    figs.append([disty_chart, p123_disty_chart])
    figs.append([disty_demand_chart, disty_demand_4w_chart])
    figs.append([p1_disty_chart, p3_disty_chart, p3_yield_chart])
    return figs, maindata.loc[maindata.index >= dt.datetime(2017, 1, 1), "Stocks"]


def us_refinery_stocks(sdate=dt.datetime(2025, 11, 1)):
    us_runs_doe = bbg.bdh("DOEPCRIN Index", ["PX_LAST"], sdate, cdr.today())
    total_stocks_doe = bbg.bdh("DOESCRUD Index", ["PX_LAST"], sdate, cdr.today())
    padd2_stocks_doe = bbg.bdh("DOESCRU2 Index", ["PX_LAST"], sdate, cdr.today())
    padd3_stocks_doe = bbg.bdh("DOESCRU3 Index", ["PX_LAST"], sdate, cdr.today())
    padd2_runs_doe = bbg.bdh("DOEPCRP2 Index", ["PX_LAST"], sdate, cdr.today())
    padd3_runs_doe = bbg.bdh("DOEPCRP3 Index", ["PX_LAST"], sdate, cdr.today())
    cushing_doe = bbg.bdh("DOESCROK Index", ["PX_LAST"], sdate, cdr.today())
    mogas_doe = bbg.bdh("DOESTMGS Index", ["PX_LAST"], sdate, cdr.today())
    disty_doe = bbg.bdh("DOESDIST Index", ["PX_LAST"], sdate, cdr.today())
    ea = pd.read_excel(convert_path_to_linux(_unrecovered("doe_stocks_bbg.py line1037 EA benchmark workbook path suffix", r"\\elementcapital.corp\ecns01\PM\Michel Kikano\CODE\data\sell_side_c")), sheet_name="2019 - 2026 Balances")
    total = ea.iloc[2:26, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd1 = ea.iloc[30:52, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd2 = ea.iloc[56:78, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd3 = ea.iloc[82:105, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd4 = ea.iloc[109:131, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd5 = ea.iloc[135:, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    ea_date = "EA-Dec25"
    cur_q = int((cdr.today().month - 1) / 3 + 1)
    last_day = dt.datetime(cdr.today().year, 3 * cur_q - 2, 1) - dt.timedelta(1)
    last_day_yr = dt.datetime(cdr.today().year - 1, 12, 31)
    cushing_ea_release = dv.ea_release_dates("16063", monthly=False)
    for i in range(len(cushing_ea_release)-1, 0, -1):
        if dt.datetime.strptime(cushing_ea_release[i][:10], "%Y-%m-%d") < last_day:
            cushing_ea_latest_release = cushing_ea_release[i]
            break
    for i in range(len(cushing_ea_release)-1, 0, -1):
        if dt.datetime.strptime(cushing_ea_release[i][:10], "%Y-%m-%d") < last_day_yr:
            cushing_ea_benchmark_release = cushing_ea_release[i]
            break
    cushing_ea_latest = dv.energy_aspects(dataset_id="16063", start=sdate.strftime("%Y-%m-%d"), release_date=cushing_ea_latest_release)
    cushing_ea_latest.set_index("Date", inplace=True)
    cushing_ea_latest.index = pd.to_datetime(cushing_ea_latest.index)
    us_ea_latest = dv.energy_aspects(dataset_id=("268,279,313,16063"), start=sdate.strftime("%Y-%m-%d"), release_date=cushing_ea_latest_release)
    us_ea_benchmark = dv.energy_aspects(dataset_id=("268,279,313,16063"), start=sdate.strftime("%Y-%m-%d"), release_date=cushing_ea_benchmark_release)
    us_ea_latest.set_index("Date", inplace=True)
    us_ea_latest.index = pd.to_datetime(us_ea_latest.index)
    us_ea_benchmark.set_index("Date", inplace=True)
    us_ea_benchmark.index = pd.to_datetime(us_ea_benchmark.index)
    us_ea_latest_release = cushing_ea_latest_release[:10]

    def last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", issue=-1, sheet_name=None, date_format="%b-%y"):
        files = [x for x in os.listdir(convert_path_to_linux(folder))]
        files.sort()
        if not isinstance(issue, int):
            file_dts = [dt.datetime.strptime(x[:8], "%Y%m%d") for x in files]
            last_day = issue
            issue = np.where(np.array(file_dts) <= last_day)[0][-1]
        if sheet_name is None:
            sheet_name = "Fig 2 Cushing balances"
        data = pd.read_excel(convert_path_to_linux(f"{folder}\\{files[issue]}"), sheet_name=sheet_name)
        data.set_index(data.columns[0], inplace=True)
        data = data.T
        data.index = [dt.datetime.strptime(x, date_format) for x in data.index]
        last_file_date = dt.datetime.strptime(files[issue][:8], "%Y%m%d")
        if '%y' not in date_format.lower():
            year = last_file_date.year
            new_index = []
            for i, date_val in enumerate(data.index):
                if i > 0 and date_val.month < data.index[i-1].month:
                    year += 1
                new_index.append(date_val.replace(year=year))
            data.index = pd.DatetimeIndex(new_index)
        return data, last_file_date

    latest_padd2, latest_padd2_date = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", sheet_name=_unrecovered("doe_stocks_bbg.py line1111 PADD2 sheet name/call tail", "F"))
    latest_padd3, latest_padd3_date = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", sheet_name=_unrecovered("doe_stocks_bbg.py line1112 PADD3 sheet name/call tail", "F"))
    total_stocks_ea = us_ea_benchmark['Monthly EA forecast for crude oil inventories in United States in mb']
    total_stocks_ea_w = total_stocks_ea.resample("W-FRI").last().fillna(method="ffill")
    total_stocks_ea_latest = us_ea_latest['Monthly EA forecast for crude oil inventories in United States in mb']
    total_stocks_ea_latest_w = total_stocks_ea_latest.resample("W-FRI").last().fillna(method="ffill")
    total_stocks = pd.concat([total_stocks_doe / 1000, total_stocks_ea_w, total_stocks_ea_latest_w], axis=1)
    total_stocks.columns = ["DOE", ea_date, f"EA-{us_ea_latest_release}"]
    total_stocks = total_stocks.loc[total_stocks.index >= total_stocks_doe.index[0], :]
    total_benchmark, benchmark_date = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", sheet_name=_unrecovered("doe_stocks_bbg.py line1124 total benchmark spreadsheet call tail", "Fi"))
    total_latest, latest_date = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", sheet_name=_unrecovered("doe_stocks_bbg.py line1125 total latest spreadsheet call tail", "Fig 4 U"))
    total_runs_ea = total_benchmark["Runs"]
    total_runs_ea_w = total_runs_ea.resample("W-FRI").last().fillna(method="ffill")
    total_runs_ea_1 = total_latest["Runs"]
    total_runs_ea_1_w = total_runs_ea_1.resample("W-FRI").last().fillna(method="ffill")
    us_runs = pd.concat([us_runs_doe / 1000, total_runs_ea_w / 1000, total_runs_ea_1_w / 1000], axis=1)
    us_runs.columns = ["DOE", ea_date, f"EA-{us_ea_latest_release}"]
    us_runs = us_runs.loc[us_runs.index >= us_runs_doe.index[0], :]
    padd2_stocks_ea = us_ea_benchmark['Monthly EA forecast for crude oil inventories in PADD 2 in mb']
    padd2_stocks_ea_w = padd2_stocks_ea.resample("W-FRI").last().fillna(method="ffill")
    padd2_stocks_ea_latest = us_ea_latest['Monthly EA forecast for crude oil inventories in PADD 2 in mb']
    padd2_stocks_ea_latest_w = padd2_stocks_ea_latest.resample("W-FRI").last().fillna(method="ffill")
    padd2_stocks = pd.concat([padd2_stocks_doe / 1000, padd2_stocks_ea_w, padd2_stocks_ea_latest_w], axis=1)
    padd2_stocks.columns = ["DOE", ea_date, f"EA-{us_ea_latest_release}"]
    padd2_stocks = padd2_stocks.loc[padd2_stocks.index >= padd2_stocks_doe.index[0], :]
    padd2_runs_ea = padd2.loc[[padd2.index[0], "Runs"], :].T
    padd2_runs_ea.set_index(padd2_runs_ea.columns[0], inplace=True)
    padd2_runs_ea.index = pd.to_datetime(padd2_runs_ea.index)
    padd2_runs_ea_w = padd2_runs_ea.resample("W-FRI").last().fillna(method="ffill")
    padd2_runs_ea_1 = latest_padd2["Runs"]
    padd2_runs_ea_1_w = padd2_runs_ea_1.resample("W-FRI").last().fillna(method="ffill")
    padd2_runs = pd.concat([padd2_runs_doe / 1000, padd2_runs_ea_w / 1000, padd2_runs_ea_1_w / 1000], axis=1)
    padd2_runs.columns = ["DOE", ea_date, f"EA-{us_ea_latest_release}"]
    padd2_runs = padd2_runs.loc[padd2_runs.index >= padd2_runs_doe.index[0], :]
    padd3_stocks_ea = us_ea_benchmark['Monthly EA forecast for crude oil inventories in PADD 3 in mb']
    padd3_stocks_ea_w = padd3_stocks_ea.resample("W-FRI").last().fillna(method="ffill")
    padd3_stocks_ea_latest = us_ea_latest['Monthly EA forecast for crude oil inventories in PADD 3 in mb']
    padd3_stocks_ea_latest_w = padd3_stocks_ea_latest.resample("W-FRI").last().fillna(method="ffill")
    padd3_stocks = pd.concat([padd3_stocks_doe / 1000, padd3_stocks_ea_w, padd3_stocks_ea_latest_w], axis=1)
    padd3_stocks.columns = ["DOE", ea_date, f"EA-{us_ea_latest_release}"]
    padd3_stocks = padd3_stocks.loc[padd3_stocks.index >= padd3_stocks_doe.index[0], :]
    padd3_runs_ea = padd3.loc[[padd3.index[0], "Runs"], :].T
    padd3_runs_ea.set_index(padd3_runs_ea.columns[0], inplace=True)
    padd3_runs_ea.index = pd.to_datetime(padd3_runs_ea.index)
    padd3_runs_ea_w = padd3_runs_ea.resample("W-FRI").last().fillna(method="ffill")
    padd3_runs_ea_1 = latest_padd3["Runs"]
    padd3_runs_ea_1_w = padd3_runs_ea_1.resample("W-FRI").last().fillna(method="ffill")
    padd3_runs = pd.concat([padd3_runs_doe / 1000, padd3_runs_ea_w / 1000, padd3_runs_ea_1_w / 1000], axis=1)
    padd3_runs.columns = ["DOE", ea_date, f"EA-{us_ea_latest_release}"]
    padd3_runs = padd3_runs.loc[padd3_runs.index >= padd3_runs_doe.index[0], :]
    cushing_ea = dv.energy_aspects(dataset_id="16063", start=sdate.strftime("%Y-%m-%d"), release_date=cushing_ea_benchmark_release)
    cushing_ea_release = cushing_ea_latest_release[:10]
    cushing_ea.set_index("Date", inplace=True)
    cushing_ea.index = pd.to_datetime(cushing_ea.index)
    cushing_ea_w = cushing_ea.resample("W-FRI").last().fillna(method="ffill")
    cushing_ea_latest_w = cushing_ea_latest.resample("W-FRI").last().fillna(method="ffill")
    cushing = pd.concat([cushing_doe / 1000, cushing_ea_w / 1000, cushing_ea_latest_w / 1000], axis=1)
    cushing.columns = ["DOE", ea_date, f"EA-{cushing_ea_release}"]
    cushing = cushing.loc[cushing.index >= padd3_stocks_doe.index[0], :]

    def cal_bal(folder=f"{data_path}\\EA\\US Gasoline", type="m", issue=-1):
        files = [x for x in os.listdir(convert_path_to_linux(folder)) if x[-5] == type]
        files.sort()
        if isinstance(issue, dt.datetime):
            file_dts = [dt.datetime.strptime(x[:8], "%Y%m%d") for x in files]
            last_day = issue
            if last_day == dt.datetime(2024, 12, 18):
                issue = file_dts.index(dt.datetime(2025, 1, 15))
            else:
                issue = np.where(np.array(file_dts) <= last_day)[0][-1]
        elif not isinstance(issue, int):
            file_dts = [dt.datetime.strptime(x[:8], "%Y%m%d") for x in files]
            cur_q = int((cdr.today().month - 1) / 3 + 1)
            last_day = dt.datetime(cdr.today().year, 3 * cur_q - 2, 1) - dt.timedelta(1)
            if last_day == dt.datetime(2024, 12, 31):
                issue = file_dts.index(dt.datetime(2025, 1, 15))
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
        return bal["chg"] * bal["day"], f"{dt.datetime.strptime(files[issue][:8], '%Y%m%d').strftime('%Y-%m-%d')}"
    mo_ea_benchmark_w, mo_benchmark_date = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", **_unrecovered("doe_stocks_bbg.py line1228 weekly benchmark spreadsheet call tail"))
    mo_ea_benchmark_w = mo_ea_benchmark_w.iloc[:, -1] * 1000
    mo_ea_benchmark, _ = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", issue=_unrecovered("doe_stocks_bbg.py line1230 monthly benchmark issue date and spreadsheet call tail", dt.datetime, 2025, 12))
    mo_ea_benchmark = mo_ea_benchmark.iloc[:, -1] * 1000
    mo_ea_benchmark.sort_index(inplace=True)
    mo_ea_benchmark = mo_ea_benchmark.cumsum()
    mo_ea_benchmark_m_to_w = mo_ea_benchmark.resample("W-FRI").last().fillna(method="ffill")
    if mo_ea_benchmark_w.index[-1] < mo_ea_benchmark.index[-1]:
        mo_ea_benchmark_w = mo_ea_benchmark_m_to_w
    else:
        mo_ea_benchmark_w = mo_ea_benchmark_w.cumsum() + mo_ea_benchmark_m_to_w.loc[mo_ea_benchmark_w.index[0]]
        mo_ea_benchmark_w = pd.concat([mo_ea_benchmark_m_to_w.loc[mo_ea_benchmark_m_to_w.index < mo_ea_benchmark_w.index[0]], mo_ea_benchmark_w], axis=0)
    mo_ea_benchmark_w = mo_ea_benchmark_w.loc[mo_ea_benchmark_w.index >= mogas_doe.index[0]]
    mo_ea_benchmark_w = mo_ea_benchmark_w.loc[mo_ea_benchmark_w.index[0]] * -1 + mo_ea_benchmark_w
    mo_ea_benchmark_w = mogas_doe.loc[mo_ea_benchmark_w.index[0], "PX_LAST"] + mo_ea_benchmark_w
    mo_ea_latest, mo_ea_latest_release = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", issue=last_day, **_unrecovered("doe_stocks_bbg.py line1244 latest spreadsheet call tail"))
    mo_ea_latest = mo_ea_latest.iloc[:, -1] * 1000
    if mo_ea_latest_release == '2025-01-15':
        mo_ea_latest = mo_ea_benchmark.copy()
    else:
        mo_ea_latest = mo_ea_latest.cumsum()
    mo_ea_latest_w = mo_ea_latest.resample("W-FRI").last().fillna(method="ffill")
    mo_ea_latest_w = mo_ea_latest_w.loc[mo_ea_latest_w.index >= mogas_doe.index[0]]
    mo_ea_latest_w = mo_ea_latest_w.loc[mo_ea_latest_w.index[0]] * -1 + mo_ea_latest_w
    mo_ea_latest_w = mogas_doe.loc[mo_ea_latest_w.index[0], "PX_LAST"] + mo_ea_latest_w
    mogas = pd.concat([mogas_doe / 1000, mo_ea_benchmark_w / 1000, mo_ea_latest_w / 1000], axis=1)
    mogas.columns = ["DOE", ea_date, f"EA-{mo_ea_latest_release}"]
    mogas = mogas.loc[mogas.index >= padd3_stocks_doe.index[0], :]
    disty_ea_benchmark_w, disty_benchmark_date = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", **_unrecovered("doe_stocks_bbg.py line1258 weekly benchmark spreadsheet call tail"))
    disty_ea_benchmark_w = disty_ea_benchmark_w.iloc[:, -1] * 1000
    disty_ea_benchmark, _ = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", issue=_unrecovered("doe_stocks_bbg.py line1260 monthly benchmark issue date and spreadsheet call tail", dt.datetime, 2025, 12))
    disty_ea_benchmark = disty_ea_benchmark.iloc[:, -1] * 1000
    disty_ea_benchmark.sort_index(inplace=True)
    disty_ea_benchmark = disty_ea_benchmark.cumsum()
    disty_ea_benchmark_m_to_w = disty_ea_benchmark.resample("W-FRI").last().fillna(method="ffill")
    if disty_ea_benchmark_w.index[-1] < disty_ea_benchmark.index[-1]:
        disty_ea_benchmark_w = disty_ea_benchmark_m_to_w
    else:
        disty_ea_benchmark_w = disty_ea_benchmark_w.cumsum() + disty_ea_benchmark_m_to_w.loc[disty_ea_benchmark_w.index[0]]
        disty_ea_benchmark_w = pd.concat([disty_ea_benchmark_m_to_w.loc[disty_ea_benchmark_m_to_w.index < disty_ea_benchmark_w.index[0]], disty_ea_benchmark_w], axis=0)
    disty_ea_benchmark_w = disty_ea_benchmark_w.loc[disty_ea_benchmark_w.index >= mogas_doe.index[0]]
    disty_ea_benchmark_w = disty_ea_benchmark_w.loc[disty_ea_benchmark_w.index[0]] * -1 + disty_ea_benchmark_w
    disty_ea_benchmark_w = disty_doe.loc[disty_ea_benchmark_w.index[0], "PX_LAST"] + disty_ea_benchmark_w
    disty_ea_latest, disty_ea_latest_release = last_file(folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", issue=last_day, **_unrecovered("doe_stocks_bbg.py line1274 latest spreadsheet call tail"))
    disty_ea_latest = disty_ea_latest.iloc[:, -1] * 1000
    if disty_ea_latest_release == '2025-01-15':
        disty_ea_latest = disty_ea_benchmark.copy()
    else:
        disty_ea_latest = disty_ea_latest.cumsum()
    disty_ea_latest_w = disty_ea_latest.resample("W-FRI").last().fillna(method="ffill")
    disty_ea_latest_w = disty_ea_latest_w.loc[disty_ea_latest_w.index >= mogas_doe.index[0]]
    disty_ea_latest_w = disty_ea_latest_w.loc[disty_ea_latest_w.index[0]] * -1 + disty_ea_latest_w
    disty_ea_latest_w = disty_doe.loc[disty_ea_latest_w.index[0], "PX_LAST"] + disty_ea_latest_w
    disty = pd.concat([disty_doe / 1000, disty_ea_benchmark_w / 1000, disty_ea_latest_w / 1000], axis=1)
    disty.columns = ["DOE", ea_date, f"EA-{disty_ea_latest_release}"]
    disty = disty.loc[disty.index >= padd3_stocks_doe.index[0], :]
    return total_stocks, us_runs, padd2_stocks, padd2_runs, padd3_stocks, padd3_runs, cushing, mogas, disty


def tracker_charts():
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(table.html_text("Tracker", style="font-family:Calibri; font-size: 16px;", tag='b'))
    total_stocks, us_runs, padd2_stocks, padd2_runs, padd3_stocks, padd3_runs, cushing, mogas, disty = us_refinery_stocks(sdate=dt.datetime(2024, 11, 1))
    us_crude_chart = chart.line_chart(df=total_stocks, title="US Total Crude Stocks - DOE vs EA", y_axis_title="mbd", highlight_dict={"DOE": {"mode": "markers+lines"}, "EA-Dec24": {"dash": "dash"}}, tickformat=None, width=750, height=500)
    padd23_crude_chart = chart.line_chart(df=padd2_stocks + padd3_stocks, title="PADD2+3 Crude Stocks - DOE vs EA", y_axis_title="mbd", highlight_dict={"DOE": {"mode": "markers+lines"}, "EA-Dec24": {"dash": "dash"}}, tickformat=None, width=750, height=500)
    figs.append([us_crude_chart, padd23_crude_chart])
    us_refinery_chart = chart.line_chart(df=us_runs, title="US Refinery - DOE vs EA", y_axis_title="mbd", highlight_dict={"DOE": {"mode": "markers+lines"}, "EA-Dec24": {"dash": "dash"}}, tickformat=None, width=750, height=500)
    padd23_refinery_chart = chart.line_chart(df=padd2_runs + padd3_runs, title="PADD2+3 Refinery - DOE vs EA", y_axis_title="mbd", highlight_dict={"DOE": {"mode": "markers+lines"}, "EA-Dec24": {"dash": "dash"}}, tickformat=None, width=750, height=500)
    figs.append([us_refinery_chart, padd23_refinery_chart])
    mogas_chart = chart.line_chart(df=mogas, title="Mogas stocks - DOE vs EA", y_axis_title="mbd", highlight_dict={"DOE": {"mode": "markers+lines"}, "EA-Dec24": {"dash": "dash"}}, tickformat=None, width=750, height=500)
    disty_chart = chart.line_chart(df=disty, title="Disty stocks - DOE vs EA", y_axis_title="mbd", highlight_dict={"DOE": {"mode": "markers+lines"}, "EA-Dec24": {"dash": "dash"}}, tickformat=None, width=750, height=500)
    figs.append([mogas_chart, disty_chart])
    return figs


def eia_report(send_to):
    liquids, liq_stocks_data, jet_stocks = eia_stocks()
    print("Liquids Done")
    crude, crude_stocks_data = eia_crude()
    print("Crude Done")
    mogas, mogas_stocks_data = eia_mogas()
    print("Mogas Done")
    disty, disty_stocks_data = eia_disty()
    print("Disty Done")
    liquids_bar = new_stocks_chart(data=liq_stocks_data, title="Total Liquids stocks", y_axis_title="Storage vs past (kb)", p1y2_axis_title="Total Storage (kb)", ytd=False, cum_ytd=False, ex_year=[2020], freq="W", width=750, height=500)
    total_crude_proucts_data = pd.concat([crude_stocks_data.to_frame("stocks"), jet_stocks.to_frame("stocks"), mogas_stocks_data.to_frame("stocks"), disty_stocks_data.to_frame("stocks")], axis=1).sum(axis=1)
    total_crude_proucts_bar = new_stocks_chart(data=total_crude_proucts_data, title="Total Crude+Gasoline+Disti+Jet stocks", y_axis_title="Storage vs past (kb)", p1y2_axis_title="Total Storage (kb)", ytd=False, cum_ytd=False, ex_year=[2020], freq="W", width=750, height=500)
    total_crude_products_seasonal = chart.seasonal_chart(
        df=total_crude_proucts_data, title="Total Crude+Gasoline+Disti+Jet stocks - Seasonal", freq='W',
        highlight_dict={total_crude_proucts_data.index[-1].year: {"color": "black", "width": 2, "mode": "markers+lines"}},
        y_axis_title="kb", width=750, height=500,
    )
    data_by_year = ts.data_by_year(total_crude_proucts_data, freq='W')
    data_by_year0 = data_by_year - data_by_year.iloc[0, :]
    dts = pd.date_range(dt.datetime(data_by_year0.columns[-1], 1, 1), dt.datetime(data_by_year0.columns[-1], 12, 31), freq='W')
    if len(dts) < data_by_year0.shape[0]:
        data_by_year0 = data_by_year0.iloc[:len(dts), :]
    data_by_year0['Date'] = dts
    data_by_year0 = data_by_year0.set_index('Date')
    data_by_year0.drop([2020], axis=1, inplace=True)
    data1 = data_by_year0.iloc[:, -1] - data_by_year0.iloc[:, -6:-1].mean(axis=1)
    data1 = data1.to_frame('Cur Yr vs Avg')
    data1['Cur Yr vs Yr-1'] = data_by_year0.iloc[:, -1] - data_by_year0.iloc[:, -2]
    ytd_total_crude_products = chart.line_chart(
        df=data_by_year0, data_p2y1=data1, subplots=[0.7, 0.3],
        highlight_dict={
            data_by_year0.columns[-1]: {"color": "black", "width": 2},
            data_by_year0.columns[-2]: {"color": "blue", "width": 2},
            'Cur Yr vs Avg': {"color": "black"}, 'Cur Yr vs Yr-1': {"color": "black", "dash": "dash"},
        }, title="YTD change of Crude+Gasoline+Disti+Jet stocks", y_axis_title='kb', width=750, height=500,
    )
    additional_figs = [liquids_bar, total_crude_proucts_bar]
    additional_figs2 = [total_crude_products_seasonal, ytd_total_crude_products]
    liquids_raw = liquids.copy()
    table_with_link = liquids[0]
    liquids.insert(1, additional_figs)
    liquids.insert(3, additional_figs2)
    table_with_link = table_with_link.replace('Liquids', u'<a href="{}\\oil\\links\\{}_liquids.html">Liquids</a>'.format(html_path, file_name))
    table_with_link = table_with_link.replace('Crude', u'<a href="{}\\oil\\links\\{}_crude.html">Crude</a>'.format(html_path, file_name))
    table_with_link = table_with_link.replace('Gasoline', u'<a href="{}\\oil\\links\\{}_mogas.html">Gasoline</a>'.format(html_path, file_name))
    table_with_link = table_with_link.replace('Distillates', u'<a href="{}\\oil\\links\\{}_disty.html">Distillates</a>'.format(html_path, file_name))
    liquids[0] = table_with_link
    full_html = liquids + crude + mogas + disty
    table.to_html([table.html_text("DOE liquids report", style="font-family:Calibri;", tag='h1')] + liquids_raw, f"{html_path}\\oil\\links\\{file_name}_liquids.html")
    table.to_html([table.html_text("DOE crude report", style="font-family:Calibri;", tag='h1')] + crude, f"{html_path}\\oil\\links\\{file_name}_crude.html")
    table.to_html([table.html_text("DOE mogas report", style="font-family:Calibri;", tag='h1')] + mogas, f"{html_path}\\oil\\links\\{file_name}_mogas.html")
    table.to_html([table.html_text("DOE disty report", style="font-family:Calibri;", tag='h1')] + disty, f"{html_path}\\oil\\links\\{file_name}_disty.html")
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(table.html_text(report_name, style="font-family:Calibri;", tag='h1'))
    figs += full_html
    table.to_html(figs, f"{html_path}\\oil\\{file_name}.html")
    figs_send = []
    figs_send.append("<div style='font-family:Calibri;' >")
    figs_send.append(f"Last update {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    figs_send += [table_with_link] + liquids[1:] + crude + mogas + disty
    email_subject = "Oil DOE Report"
    send_email(send_to=send_to, subject=email_subject, body=figs_send, html_path=f"{html_path}\\oil\\{file_name}.html")


def update():
    release = bbg.bbulkref(['DOEASCRD Index'], ['ECO_FUTURE_RELEASE_DATE_LIST'], option=[("START_DT", "20241231"), ("END_DT", "20261231"), ("TIME_ZONE_OVERRIDE", _unrecovered("doe_stocks_bbg.py line1476 release timezone override value"))])
    release.columns = ["value"]
    release.drop_duplicates(inplace=True)
    release['value'] = pd.to_datetime(release['value'])
    release_dates = pd.DatetimeIndex(release['value']).normalize()
    td = cdr.today()
    completed = False
    record_path = Path(convert_path_to_linux(f"{data_path}\\DOE\\record.csv"))
    if not record_path.exists():
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_csv = pd.DataFrame(columns=["date", "completed"])
        record_csv.to_csv(record_path, index=False)
    else:
        record_csv = pd.read_csv(record_path)
        record_csv['date'] = pd.to_datetime(record_csv['date']).dt.strftime("%Y-%m-%d")
    print(record_csv.to_string())
    print(f"Checking if {td.strftime('%Y-%m-%d')} is in record")
    if td.strftime("%Y-%m-%d") in record_csv['date'].values:
        completed = record_csv.loc[record_csv['date'] == td.strftime("%Y-%m-%d"), 'completed'].values[0]
    if not completed:
        print(f"Not completed for {td.strftime('%Y-%m-%d')}")
        print(f"Next release dates:\n{release.loc[np.where(release_dates >= td), 'value']}")
    if not completed and td in release_dates and release.loc[np.where(release_dates == td)[0][0], 'value'].time() < dt.datetime.now().time():
        eia_report(send_to)
        new_record = pd.DataFrame({"date": td.strftime("%Y-%m-%d"), "completed": True}, index=[0])
        record_csv = pd.concat([record_csv, new_record])
        record_csv.to_csv(record_path, index=False)
        inventory_model(send_to)


if __name__ == "__main__":
    update()
