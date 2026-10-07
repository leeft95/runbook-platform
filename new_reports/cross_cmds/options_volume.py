import pandas as pd
import numpy as np
import datetime as dt
import time
import sys
import os
import re
from loguru import logger as log
from ecm.atom.clients import dremio_query
import getpass
from pandas.tseries.offsets import BDay
import plotly.graph_objects as go
import plotly as py
from plotly.subplots import make_subplots
import statsmodels.api as sm
from dateutils import relativedelta
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.to_html as to_html
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
import ecm.cmds.utils as ut
import ecm.cmds.talib as talib
from ecm.cmds.quant.options_calibration import calibrate_rth_to_bbg_asof
from ecm.cmds.config import root_path, output_path, html_path, gas_group, oil_group, macro_group, oil_group_no_mk
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, CDR
from ecm.cmds.pyg import get_data
from ecm.atom.services import fetch_series
if sys.platform.startswith("win"):
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
from ecm.data.api import RTHQueryClient
from copy import copy

send_to = "ltrindade"
send_to_macro = macro_group
send_to_oil = oil_group_no_mk
send_to_gas = ["jmcphillips@elementcapital.com", "rzhao@elementcapital.com", "ltrindade", "caitcheson@elementcapital.com"]  # source line 42: clipped list tail
report_name = "Options Volume Report"
file_name = "options_volume"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"
cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"
cc_json_folder = f"{output_path}\\json\\cross_cmds"
cc_pdf_folder = f"{output_path}\\pdf\\cross_cmds"
folder_path = f"{cc_csv_folder}\\market_scan\\"


def _photo_gap(source_line, visible_prefix):
    raise NotImplementedError(f"Unrecovered options_volume source line {source_line}: {visible_prefix}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 7, 30),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


ins_dict = {
    'CLA Comdty': [1, 2, 3, 'M1', 'Z1'],
    'COA Comdty': [1, 2, 3, 'M1', 'Z1'],
    'XBA Comdty': [1, 2, 3, 'M1', 'Z1'],
    'HOA Comdty': [1, 2, 3, 'M1', 'Z1'],
    'QSA Comdty': [1, 2, 3, 'M1', 'Z1'],
    'NGA Comdty': [1, 2, 3, 'F1', 'J1'],
    'TZTA Comdty': [1, 2, 3, 'F1', 'J1'],
}


def bar_chart(data, data1=None, title=None, **kwargs):
    file_path = kwargs.get('file_path', None)
    y1_axis_title = kwargs.get('y1_axis_title', None)
    y2_axis_title = kwargs.get('y2_axis_title', None)
    y3_axis_title = kwargs.get('y3_axis_title', None)
    y4_axis_title = kwargs.get('y4_axis_title', None)
    y5_axis_title = kwargs.get('y5_axis_title', None)
    y6_axis_title = kwargs.get('y6_axis_title', None)
    x_axis_title = kwargs.get('x_axis_title', None)
    bar_columns = kwargs.get('bar_columns', None)
    line_columns = kwargs.get('line_columns', None)
    data2 = kwargs.get('data2', None)
    data3 = kwargs.get('data3', None)
    second_y = kwargs.get('second_y', False)
    if isinstance(data1, dict):
        data_chart_type = data1.get("type", "Bar")
        data1 = data1.get("data1", pd.DataFrame())
    else:
        data_chart_type = "Bar"
    if data1 is None:
        if second_y:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
        else:
            fig = make_subplots()
    elif data1 is not None and data2 is None:
        if second_y:
            fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True,
                                vertical_spacing=_photo_gap(110, 'vertical_spacing='),
                                specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
        else:
            fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True,
                                vertical_spacing=_photo_gap(113, 'vertical_spacing='))
    else:
        if second_y:
            fig = make_subplots(rows=3, cols=1, row_heights=[0.6, 0.2, 0.2], shared_xaxes=True,
                                vertical_spacing=_photo_gap(116, 'vertical_spacing='),
                                specs=[[{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": True}]])
        else:
            fig = make_subplots(rows=3, cols=1, row_heights=[0.6, 0.2, 0.2], shared_xaxes=True,
                                vertical_spacing=_photo_gap(119, 'vertical_spacing='))
    if bar_columns is not None:
        for col in bar_columns:
            fig.add_trace(go.Bar(name=col, x=data.index, y=data[col].values, showlegend=True))
    else:
        for col in data.columns:
            fig.add_trace(go.Bar(name=col, x=data.index, y=data[col].values, showlegend=True))
    if line_columns is not None:
        if isinstance(line_columns, list):
            if "PX_OPEN" in line_columns and "PX_HIGH" in line_columns and "PX_LOW" in line_columns and "PX_LAST" in line_columns:
                fig.add_trace(go.Candlestick(x=data.index, open=data['PX_OPEN'], high=data['PX_HIGH'],
                                             **_photo_gap(132, 'low=')))
                fig.update_layout(xaxis_rangeslider_visible=False)
                line_columns = list(set(line_columns) - set(["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]))
            for col in line_columns:
                if "Price" in col:
                    fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                             line=_photo_gap(137, 'line=dict')))
                else:
                    fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                             line=_photo_gap(139, 'line=dict')))
        elif isinstance(line_columns, dict):
            if "PX_OPEN" in list(line_columns.keys()) and "PX_HIGH" in list(line_columns.keys()) and "PX_LOW" in list(line_columns.keys()) and "PX_LAST" in list(line_columns.keys()):
                fig.add_trace(go.Candlestick(x=data.index, open=data['PX_OPEN'], high=data['PX_HIGH'],
                                             **_photo_gap(144, 'low=')))
                fig.update_layout(xaxis_rangeslider_visible=False)
                line_columns.pop('PX_OPEN')
                line_columns.pop('PX_HIGH')
                line_columns.pop('PX_LOW')
                line_columns.pop('PX_LAST')
            for col, val in line_columns.items():
                if "Price" in col:
                    fig.add_trace(
                        go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                   line=dict(width=_photo_gap(153, '1.5 +'))),
                        row=1, col=1,
                        secondary_y=val)
                else:
                    fig.add_trace(
                        go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                   line=dict(width=_photo_gap(158, '1.5 +'))),
                        row=1, col=1,
                        secondary_y=val)
    fig['layout']['yaxis1']['title'] = y1_axis_title
    if second_y:
        fig['layout']['yaxis2']['title'] = y2_axis_title
    if data1 is not None:
        if data_chart_type == "Scatter":
            fig.add_trace(go.Scatter(x=data.index, y=data1[data1.columns[0]], showlegend=True, name=data1.columns[0]),
                          **_photo_gap(167, 'remaining trace/row arguments'))
        elif data_chart_type == "Bar":
            fig.add_trace(go.Bar(x=data.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0]),
                          **_photo_gap(169, 'remaining trace/row arguments'))
        else:
            fig.add_trace(go.Bar(x=data.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0]),
                          **_photo_gap(171, 'remaining trace/row arguments'))
        fig['layout']['yaxis3']['title'] = y3_axis_title
    if data2 is not None:
        fig.add_trace(go.Bar(name=data2.columns[0], x=data.index, y=data2.iloc[:, 0].values, showlegend=True),
                      row=_photo_gap(174, 'row='), col=1)
        fig['layout']['yaxis5']['title'] = y5_axis_title
    if data3 is not None:
        fig.add_trace(
            go.Scatter(x=data.index, y=data3.iloc[:, 0], showlegend=True, name=data3.columns[0],
                       line=_photo_gap(179, 'line=dict')),
            row=3, col=1, secondary_y=True)
        fig['layout']['yaxis6']['title'] = y6_axis_title
    fig.update_xaxes(rangebreaks=[
        dict(bounds=["sat", "mon"]),  # hide weekends
        dict(values=["2024-12-25", "2025-01-01"])  # hide Christmas and New Year's
    ])
    fig.update_layout(
        title={'text': title, 'x': 0.5, 'xanchor': 'center'},
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
        barmode='stack', width=750, height=500)
    if file_path is not None:
        py.offline.plot(fig, auto_open=False, filename=file_path)
    return fig


def get_option_chain(ticker):
    return bbg.bbulkref(ticker, 'OPT_CHAIN')


def get_bbg_data(opt_ticker, sdate=today() - dt.timedelta(days=35), edate=today()):
    return bbg.bdh(opt_ticker, ['PX_LAST', 'PX_VOLUME', 'OPEN_INT'], sdate=sdate, edate=edate)


def download_option_data(ticker, last_price):
    opt_ticker_list = get_option_chain(ticker)
    strikes = bbg.bref(list(opt_ticker_list.values), ['OPT_STRIKE_PX', 'OPT_PUT_CALL'])
    strikes_inuse = strikes.loc[
        (strikes['OPT_STRIKE_PX'] >= last_price * 0.75) &
        (strikes['OPT_STRIKE_PX'] <= _photo_gap(220, 'last_price upper multiplier')), :]
    strikes_inuse = strikes_inuse.sort_values('OPT_STRIKE_PX')
    for opt_ticker, row in strikes_inuse.iterrows():
        print(opt_ticker)
        exist_data = sql.read_sql(
            "Select * from FUT_Options where Ticker = '{:s}' order by StartDate".format(opt_ticker))
        if len(exist_data) > 1:
            sdate = dt.datetime.strptime(exist_data['StartDate'].iloc[-2], '%Y-%m-%d')
        else:
            sdate = today() - dt.timedelta(days=35)
        data = get_bbg_data(opt_ticker, sdate=sdate, edate=today() - BDay(1))
        if len(data) > 0:
            if 'PX_LAST' not in data.columns:
                data['PX_LAST'] = np.nan
            if 'PX_VOLUME' not in data.columns:
                data['PX_VOLUME'] = np.nan
            if 'OPEN_INT' not in data.columns:
                data['OPEN_INT'] = np.nan
            data = data[['PX_LAST', 'PX_VOLUME', 'OPEN_INT']]
            data.columns = ['Closep', 'Volume', 'OpenInt']
            data['Ticker'] = opt_ticker
            data['Active'] = ticker
            data['Strike'] = row['OPT_STRIKE_PX']
            data['PutCall'] = row['OPT_PUT_CALL']
            data.index.name = 'StartDate'
            sql_str = "Delete from FUT_Options where StartDate >= '{:s}' and Ticker = '{:s}'".format(
                dt.datetime.strftime(sdate, '%Y-%m-%d'), opt_ticker)
            sql.sql_execute(sql_str)
            sql.to_sql(data, 'FUT_Options', index=True)


def download_all_tickers():
    for key, val in ins_dict.items():
        contracts = get_data("contracts", active=key, item="fut_chain")
        calculated = []
        for i in val:
            if isinstance(i, int):
                loc = np.where(contracts['t3'] > today())[0][i - 1]
                live_contract = contracts.iloc[loc, :]
            else:
                mon_contracts = contracts.loc[contracts['m'] == i[0], :]
                loc = np.where(mon_contracts['t3'] > today())[0][int(i[1]) - 1]
                live_contract = mon_contracts.iloc[loc, :]
            last_price = get_data("contracts_PX_LAST", active=key, m=live_contract['m'], y=live_contract['y'])
            if live_contract['ticker'] not in calculated:
                if key == 'TZTA Comdty':
                    download_option_data('FJS' + live_contract['ticker'][3:], last_price['PX_LAST'].iloc[-1])
                    calculated.append(live_contract['ticker'])
                else:
                    download_option_data(live_contract['ticker'], last_price['PX_LAST'].iloc[-1])
                    calculated.append(live_contract['ticker'])


def get_report_one_contract(key, df, df1, live_contract):
    if key == 'TZTA Comdty':
        options = df.loc[df['Active'] == 'FJS' + live_contract['ticker'][3:]]
        options1 = df1.loc[df1['Active'] == 'FJS' + live_contract['ticker'][3:]]
    else:
        options = df.loc[df['Active'] == live_contract['ticker']]
        options1 = df1.loc[df1['Active'] == live_contract['ticker']]
    common_items = set(options['Ticker']) & set(options1['Ticker'])
    options = options.loc[options['Ticker'].isin(common_items), :]
    options1 = options1.loc[options1['Ticker'].isin(common_items), :]
    total_call_volume = options.loc[options['PutCall'] == 'C', 'Volume'].sum()
    total_put_volume = options.loc[options['PutCall'] == 'P', 'Volume'].sum()
    total_call_oi = options.loc[options['PutCall'] == 'C', 'OpenInt'].sum()
    total_put_oi = options.loc[options['PutCall'] == 'P', 'OpenInt'].sum()
    total_call_oi1 = options1.loc[options1['PutCall'] == 'C', 'OpenInt'].sum()
    total_put_oi1 = options1.loc[options1['PutCall'] == 'P', 'OpenInt'].sum()
    top5_today = options.sort_values('Volume', ascending=False).iloc[:5, :]
    top5_yesterday = options1.loc[options1['Ticker'].isin(top5_today['Ticker']), :]
    top5_today = top5_today[['Ticker', 'Volume', 'OpenInt']]
    top5_today = top5_today.set_index(['Ticker'])
    top5_yesterday = top5_yesterday[['Ticker', 'Volume', 'OpenInt']]
    top5_yesterday = top5_yesterday.set_index(['Ticker'])
    top5_today['OI chg'] = top5_today['OpenInt'] - top5_yesterday['OpenInt']
    top5_today.drop(top5_today.loc[np.isnan(top5_today['Volume']), :].index, axis=0, inplace=True)
    top5_today.sort_values('Volume', ascending=False, inplace=True)
    top5_today.index = [i.rpartition(' ')[0] for i in top5_today.index]
    df_table = pd.DataFrame(0, index=['Total Calls', 'Total Puts'], columns=['Volume', 'OI chg'])
    df_table.loc['Total Calls', 'Volume'] = total_call_volume
    df_table.loc['Total Calls', 'OI chg'] = total_call_oi - total_call_oi1
    df_table.loc['Total Puts', 'Volume'] = total_put_volume
    df_table.loc['Total Puts', 'OI chg'] = total_put_oi - total_put_oi1
    df_table = pd.concat([df_table, top5_today[['Volume', 'OI chg']]], axis=0)
    df_table.columns = ['Volume_{:s}'.format(live_contract['m'] + str(live_contract['y'])[0]),
                        'OI chg_{:s}'.format(live_contract['m'] + str(live_contract['y'])[0])]
    return df_table, (options.loc[options['PutCall'] == 'C', 'Strike'].min(),
                      options.loc[options['PutCall'] == 'C', 'Strike'].max(),
                      options.loc[options['PutCall'] == 'P', 'Strike'].min(),
                      options.loc[options['PutCall'] == 'P', 'Strike'].max())


def create_html_table(df_table):
    cols = df_table.columns
    col1 = [i for i in cols if i[:6] == 'OI chg']
    col2 = [i for i in cols if i[:6] != 'OI chg']
    col2.append(col1[-1])
    col1.remove(col1[-1])
    return table.html_format(
        df=df_table,
        precision=0,
        format_column={tuple(col2): {'width': '80px', 'text-align': 'center'},
                       tuple(col1): {'width': '80px', 'text-align': 'center', 'right_border': True}})


def get_option_volume_chart_old(name, ticker):
    puts = bbg.bdh(ticker, ['AGGREGATE_Put_VOL'], sdate=today() - dt.timedelta(182), edate=today() - dt.timedelta(1))
    puts.dropna(inplace=True)
    calls = bbg.bdh(ticker, ['AGGREGATE_Call_VOL'], sdate=today() - dt.timedelta(182), edate=today() - dt.timedelta(1))
    calls.dropna(inplace=True)
    imp_vol = bbg.bdh(ticker, ['30DAY_IMPVOL_100.0%MNY_DF'], sdate=today() - dt.timedelta(182),
                      edate=today() - dt.timedelta(1))
    imp_vol = imp_vol.mean(axis=1)
    price = bbg.bdh(ticker[0], ['PX_LAST'], sdate=today() - dt.timedelta(182), edate=today() - dt.timedelta(1))
    if name not in ['TTF', 'EUA']:
        if name == "Gold":
            rr25d = -bbg.bdh("XAUUSD25R1M BGN Curncy", ['PX_LAST'], sdate=today() - dt.timedelta(182),
                             edate=today() - dt.timedelta(1))["PX_LAST"]
        elif name == "Silver":
            rr25d = -bbg.bdh("XAGUSD25R1M BGN Curncy", ['PX_LAST'], sdate=today() - dt.timedelta(182),
                             edate=today() - dt.timedelta(1))["PX_LAST"]
        else:
            call25d = bbg.bdh(ticker, ['1M_CALL_IMP_VOL_25DELTA_DFLT'], sdate=today() - dt.timedelta(182),
                              edate=today() - dt.timedelta(1))
            put25d = bbg.bdh(ticker, ['1M_PUT_IMP_VOL_25DELTA_DFLT'], sdate=today() - dt.timedelta(182),
                             edate=today() - dt.timedelta(1))
            rr25d = put25d.iloc[:, -1] - call25d.iloc[:, -1]
    cl = pd.DataFrame()
    cl[f'{name} call'] = calls.sum(axis=1)
    cl[f'{name} put'] = puts.sum(axis=1)
    cl_total = calls.sum(axis=1) + puts.sum(axis=1)
    cl_total = cl_total.fillna(0)
    cl[f'{name} Price'] = price['PX_LAST']
    cl[f'{name} 20d MA'] = cl_total.rolling(20).mean()
    cl = cl[cl.index >= today() - dt.timedelta(91)]
    cp_ratio = calls.sum(axis=1) / puts.sum(axis=1)
    cp_ratio = cp_ratio.reindex(cl.index)
    pc_ratio = -puts.sum(axis=1) / calls.sum(axis=1)
    pc_ratio = pc_ratio.reindex(cl.index)
    cp_ratio[cp_ratio < 1] = pc_ratio[cp_ratio < 1]
    imp_vol = imp_vol.diff().reindex(cl.index)
    if name not in ['TTF', 'EUA']:
        rr25d = rr25d.reindex(cl.index)
        rr25d.fillna(method='ffill', inplace=True)
        return bar_chart(cl, data1=cp_ratio.to_frame('call/put ratio'),
                         data2=imp_vol.to_frame('imp vol chg'),
                         data3=rr25d.to_frame('1m 25D RR'),
                         title=f'{name} - Total option volume trades - lots',
                         y1_axis_title='volume',
                         y2_axis_title=f"{ticker[0].rpartition(' ')[0]} price",
                         y3_axis_title='call/put ratio',
                         y5_axis_title='imp vol chg',
                         y6_axis_title='1m 25D RR',
                         bar_columns=[f'{name} call', f'{name} put'],
                         line_columns={f'{name} Price': True, f'{name} 20d MA': False},
                         second_y=True), puts.index[-1]
    else:
        return bar_chart(cl, data1=cp_ratio.to_frame('call/put ratio'),
                         data2=imp_vol.to_frame('imp vol chg'),
                         title=f'{name} - Total option volume trades - lots',
                         y1_axis_title='volume',
                         y2_axis_title=f"{ticker[0].rpartition(' ')[0]} price",
                         y3_axis_title='call/put ratio',
                         y5_axis_title='imp vol chg',
                         y6_axis_title='1m 25D RR',
                         bar_columns=[f'{name} call', f'{name} put'],
                         line_columns={f'{name} Price': True, f'{name} 20d MA': False},
                         second_y=True), puts.index[-1]


def convert_ticker(ticker):
    if ticker[:2] == "GK":
        ticker_ = f"NG{ticker[2:]}"
    elif ticker[:3] == "MZB":
        cntrct = ticker.split(" ")[0].split("MZB")[-1].replace("H", "Z").replace("M", "Z").replace("U", "Z")
        suffix = ticker.split(" ")[-1]
        ticker_ = f"MZB{cntrct} {suffix}"
    elif ticker[:2] == "MO":
        cntrct = ticker.split(" ")[0].split("MO")[-1].replace("H", "Z").replace("M", "Z").replace("U", "Z")
        suffix = ticker.split(" ")[-1]
        ticker_ = f"MO{cntrct} {suffix}"
    else:
        ticker_ = ticker
    m = re.search(r'[\d].$', ticker_.partition(" ")[0])
    if m is None:
        return f"{ticker_.partition(' ')[0][:-1]}2{ticker_.partition(' ')[0][-1]} {ticker_.partition(' ')[-1]}"
    else:
        return ticker_


def get_ma_cross(series, num_days=20, latest=True):
    mva = series.rolling(num_days).mean()
    above = series > mva
    prev = above.shift()
    cross_series = pd.Series(0, index=series.index, dtype="int8")
    cross_series[above & (prev == False)] = 1
    cross_series[(~above) & (prev == True)] = -1
    cross_series[mva.isna()] = 0
    if latest:
        return mva, cross_series.iloc[-1]
    else:
        return mva, cross_series


def get_option_volume_chart(name, ticker, thr=0):
    sdate = today() - BDay(365)
    edate = today() - BDay(1)
    if name == "LME Copper":
        puts = bbg.bdh("HGA Comdty", ["AGGREGATE_Put_VOL"], sdate=sdate, edate=edate)
        puts.dropna(inplace=True)
        calls = bbg.bdh("HGA Comdty", ["AGGREGATE_Call_VOL"], sdate=sdate, edate=edate)
        calls.dropna(inplace=True)
    else:
        if len(ticker) == 1:
            puts = bbg.bdh(ticker[-1], ["AGGREGATE_Put_VOL"], sdate=sdate, edate=edate)
        else:
            puts = bbg.bdh(ticker, ["AGGREGATE_Put_VOL"], sdate=sdate, edate=edate).sum(axis=1).to_frame("AGGREGATE_Put_VOL")
        puts.dropna(inplace=True)
        if len(ticker) == 1:
            calls = bbg.bdh(ticker[-1], ["AGGREGATE_Call_VOL"], sdate=sdate, edate=edate)
        else:
            calls = bbg.bdh(ticker, ["AGGREGATE_Call_VOL"], sdate=sdate, edate=edate).sum(axis=1).to_frame("AGGREGATE_Call_VOL")
        calls.dropna(inplace=True)
    client = RTHQueryClient
    if ticker[0][:2] in ["C ", "W ", "S ", "BO", "SM", "SB", "CT"]:
        imp_vol = bbg.bdh(ticker, ["30DAY_IMPVOL_100.0%MNY_DF"], sdate=sdate, edate=edate)
        atm_vol = copy(imp_vol)
        imp_vol = imp_vol.mean(axis=1)
    elif name == "LME Copper":
        imp_vol = bbg.bdh("LPR1 Comdty", ["PX_LAST"], sdate=sdate, edate=edate)
        atm_vol = copy(imp_vol)
        imp_vol = imp_vol.mean(axis=1)
    else:
        imp_vol_bbg = bbg.bdh(ticker, ["30DAY_IMPVOL_100.0%MNY_DF"], sdate=sdate, edate=edate)
        if len(ticker) > 1 and len(imp_vol_bbg.columns) > 1:
            imp_vol_bbg = imp_vol_bbg[ticker[0]].combine_first(imp_vol_bbg[ticker[1]]).to_frame("30DAY_IMPVOL_100.0%MNY_DF")
        else:
            imp_vol_bbg.columns = ["30DAY_IMPVOL_100.0%MNY_DF"]
        imp_vol_c = client.get_bvol(ops_codes=convert_ticker(ticker[0]), start_date=today() - BDay(90), end_date=edate, specific_call="0.5C")
        if len(imp_vol_c) > 0:
            imp_vol_c = imp_vol_c.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
            imp_vol_c = imp_vol_c.loc[~imp_vol_c["0.5D"].isna()]
            imp_vol_c = imp_vol_c[~imp_vol_c.index.duplicated(keep="last")]
        imp_vol_p = client.get_bvol(ops_codes=convert_ticker(ticker[0]), start_date=today() - BDay(90), end_date=edate, specific_call="0.5P")
        if len(imp_vol_p) > 0:
            imp_vol_p = imp_vol_p.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
            imp_vol_p = imp_vol_p.loc[~imp_vol_p["0.5D"].isna()]
            imp_vol_p = imp_vol_p[~imp_vol_p.index.duplicated(keep="last")]
        imp_vol_rth = (imp_vol_c["0.5D"] + imp_vol_p["0.5D"]) / 2 * 100
        imp_vol_rth = imp_vol_rth.to_frame("30DAY_IMPVOL_100.0%MNY_DF")
        imp_vol_rth.index = pd.to_datetime(imp_vol_rth.index)
        try:
            _, _, func, _ = calibrate_rth_to_bbg_asof(imp_vol_rth["30DAY_IMPVOL_100.0%MNY_DF"], imp_vol_bbg["30DAY_IMPVOL_100.0%MNY_DF"])
            imp_vol_rth_calibrated = imp_vol_rth.copy()["30DAY_IMPVOL_100.0%MNY_DF"].apply(func)
            imp_vol = imp_vol_bbg["30DAY_IMPVOL_100.0%MNY_DF"].combine_first(imp_vol_rth_calibrated).to_frame("30DAY_IMPVOL_100.0%MNY_DF")
        except Exception as e:
            log.error(f"Calibrate RTH to BBG failed for {ticker[0]}: {e}")
            imp_vol = imp_vol_rth.combine_first(imp_vol_bbg)
        imp_vol = imp_vol[~imp_vol.index.duplicated(keep="first")]
        atm_vol = copy(imp_vol)
        imp_vol = imp_vol.mean(axis=1)
        if imp_vol.empty:
            imp_vol = bbg.bdh(ticker, ["30DAY_IMPVOL_100.0%MNY_DF"], sdate=sdate, edate=edate)
            atm_vol = copy(imp_vol)
            imp_vol = imp_vol.mean(axis=1)
    if ticker[0][:3] == "MZB":
        price = bbg.bdh("MZBA Comdty", ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"], sdate=sdate, edate=today())
    else:
        price = bbg.bdh(ticker[0], ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"], sdate=sdate, edate=today())
    if name == "Gold":
        rr25d = -bbg.bdh("XAUUSD25R1M BGN Curncy", ["PX_LAST"], sdate=sdate, edate=edate)["PX_LAST"]
        imp_vol = bbg.bdh("XAUUSDV1M BGN Curncy", ["PX_LAST"], sdate=sdate, edate=edate)["PX_LAST"]
    elif name == "Silver":
        rr25d = -bbg.bdh("XAGUSD25R1M BGN Curncy", ["PX_LAST"], sdate=sdate, edate=edate)["PX_LAST"]
        imp_vol = bbg.bdh("XAGUSDV1M BGN Curncy", ["PX_LAST"], sdate=sdate, edate=edate)["PX_LAST"]
    elif name == "LME Copper":
        d25_c_ticker = "LPP1 Comdty"
        d25_p_ticker = "LPC1 Comdty"
        d25_c = bbg.bdh(d25_c_ticker, ["PX_LAST"], sdate=today() - BDay(90), edate=today() - dt.timedelta(1))
        d25_p = bbg.bdh(d25_p_ticker, ["PX_LAST"], sdate=today() - BDay(90), edate=today() - dt.timedelta(1))
        rr25d = d25_p["PX_LAST"] - d25_c["PX_LAST"]
    elif name in ["Brent", "WTI", "NG", "TTF", "EUA"]:
        call25d = bbg.bdh(ticker, ["1M_CALL_IMP_VOL_25DELTA_DFLT"], sdate=sdate, edate=edate)
        if len(ticker) > 1 and len(call25d.columns) > 1:
            call25d = call25d[ticker[0]].combine_first(call25d[ticker[1]]).to_frame("1M_CALL_IMP_VOL_25DELTA_DFLT")
        put25d = bbg.bdh(ticker, ["1M_PUT_IMP_VOL_25DELTA_DFLT"], sdate=sdate, edate=edate)
        if len(ticker) > 1 and len(put25d.columns) > 1:
            put25d = put25d[ticker[0]].combine_first(put25d[ticker[1]]).to_frame("1M_PUT_IMP_VOL_25DELTA_DFLT")
        rr25d = put25d.iloc[:, -1] - call25d.iloc[:, -1]
        d25_c = client.get_bvol(ops_codes=convert_ticker(ticker[0]), start_date=today() - BDay(90), end_date=edate, specific_call="0.25C")
        if len(d25_c) > 0:
            d25_c = d25_c.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
            d25_c.loc[d25_c["0.25C"] < 0, "0.25C"] = np.nan
            d25_c = d25_c[~d25_c.index.duplicated(keep="last")]
        d25_p = client.get_bvol(ops_codes=convert_ticker(ticker[0]), start_date=today() - BDay(90), end_date=edate, specific_call="0.25P")
        if len(d25_p) > 0:
            d25_p = d25_p.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
            d25_p.loc[d25_p["0.25P"] < 0, "0.25P"] = np.nan
            d25_p = d25_p[~d25_p.index.duplicated(keep="last")]
        rr25d_rth = (d25_p["0.25P"] - d25_c["0.25C"]) * 100
        if not rr25d_rth.empty:
            rr25d_rth.index = rr25d_rth.index.astype('datetime64[ns]')
        else:
            rr25d_rth = pd.DataFrame()
        if not rr25d_rth.empty:
            try:
                _, _, func, diag = calibrate_rth_to_bbg_asof(rr25d_rth, rr25d)
                calibrated_rth = rr25d_rth.apply(func)
                rr25d = rr25d.combine_first(calibrated_rth)
            except Exception as e:
                log.error(f"Calibrate RTH to BBG failed for {ticker[0]}: {e}")
                rr25d = rr25d.combine_first(rr25d_rth)
        else:
            call25d = bbg.bdh(ticker, ["1M_CALL_IMP_VOL_25DELTA_DFLT"], sdate=sdate, edate=edate)
            put25d = bbg.bdh(ticker, ["1M_PUT_IMP_VOL_25DELTA_DFLT"], sdate=sdate, edate=edate)
            rr25d = put25d.iloc[:, -1] - call25d.iloc[:, -1]
        rr25d = rr25d[~rr25d.duplicated()]
    else:
        call25d = bbg.bdh(ticker, ["1M_CALL_IMP_VOL_25DELTA_DFLT"], sdate=sdate, edate=edate)
        put25d = bbg.bdh(ticker, ["1M_PUT_IMP_VOL_25DELTA_DFLT"], sdate=sdate, edate=edate)
        rr25d = put25d.iloc[:, -1] - call25d.iloc[:, -1]
    price_chg = 100 * np.log(price['PX_LAST'] / price['PX_LAST'].shift(1))
    hvol_5d = np.sqrt(252) * price_chg.rolling(5).std()
    hvol_8d = np.sqrt(252) * price_chg.rolling(8).std()
    hvol_13d = np.sqrt(252) * price_chg.rolling(13).std()
    hvol_34d = np.sqrt(252) * price_chg.rolling(34).std()
    hvol_frame = pd.DataFrame([hvol_8d, hvol_13d, hvol_34d, imp_vol]).T
    hvol_frame.columns = ["HVOL(8D)", "HVOL(13D)", "HVOL(34D)", "IMP VOL"]
    hvol_frame = hvol_frame[hvol_frame.index >= today() - dt.timedelta(91)]
    exch_dates = CDR(ticker[0] if name not in ['NG', 'EUA'] else ticker[-1]).drange(hvol_frame.index[0], hvol_frame.index[-1])
    hvol_frame = hvol_frame.reindex(exch_dates).ffill()
    hvol_last_px = price["PX_LAST"].to_frame("PX_LAST").reindex(hvol_frame.index).ffill()
    hivg_chart = chart.line_chart(df=hvol_frame, y_axis_title="Vol", p1y2_axis_title="Price", data_p1y2=hvol_last_px,
                                secondary_y=True, tickformat=None, width=750, height=500,
                                highlight_dict={"PX_LAST": {"color": "black", "width": 2, "dash": "dash"},
                                                "IMP VOL": {"width": 2, "color": _photo_gap(624, 'IMP VOL: width 2, col...')}})
    hivg_chart.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    hivg_chart.update_layout(title={'text': f"HIVG chart for {ticker[0] if name not in ['NG'] else ticker[-1]}", 'x': .5, 'xanchor': 'center'},
                             legend=dict(orientation="h", yanchor="bottom", y=-.25, xanchor="center", x=.5), barmode='stack', width=750, height=500)
    mva_20d_vol, result_vol = get_ma_cross(imp_vol, num_days=20)
    mva_20d_rr, result_rr = get_ma_cross(rr25d, num_days=20)
    data_mva_vol = mva_20d_vol.to_frame("20D MVA Vol")
    data_mva_rr = mva_20d_rr.to_frame("20D MVA RR")
    data_imp_vol = imp_vol.to_frame("Imp Vol")
    data_rr25d = rr25d.to_frame("1m 25D RR")
    full_data_vol = pd.concat([data_imp_vol, data_mva_vol], axis=1)
    full_data_rr = pd.concat([data_rr25d, data_mva_rr], axis=1)
    plot_data_mva_vol_6m = full_data_vol[full_data_vol.index >= today() - relativedelta(months=6)]
    plot_data_mva_rr_6m = full_data_rr[full_data_rr.index >= today() - relativedelta(months=6)]
    mva_20d_vol_chart = chart.line_chart(df=plot_data_mva_vol_6m, y_axis_title="Vol", x_axis_title="date",
                                       title=f"{ticker[0] if name not in ['NG'] else ticker[-1]} 20D MVA Vol", tickformat=None,
                                       hovertemplate="%{x|%b/%d} %{y}", width=750, height=500)
    mva_20d_vol_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-.25, xanchor="center", x=.5))
    mva_20d_rr_chart = chart.line_chart(df=plot_data_mva_rr_6m, y_axis_title="25D RR", x_axis_title="date",
                                      title=f"{ticker[0] if name not in ['NG'] else ticker[-1]} 20D MVA RR", tickformat=None,
                                      hovertemplate="%{x|%b/%d} %{y}", width=750, height=500)
    mva_20d_rr_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-.25, xanchor="center", x=.5))
    cl = pd.DataFrame()
    cl[f'{name} call'] = calls.sum(axis=1)
    cl[f'{name} put'] = puts.sum(axis=1)
    cl_total = calls.sum(axis=1) + puts.sum(axis=1)
    cl_total = cl_total.fillna(0)
    cl[f'{name} Price'] = price['PX_LAST']
    cl[f'{name} 20d MA'] = cl_total.rolling(20).mean()
    cl_chart_data = cl[cl.index >= today() - dt.timedelta(91)]
    cp_ratio = calls.sum(axis=1) / puts.sum(axis=1)
    cp_ratio = cp_ratio.reindex(cl_chart_data.index)
    pc_ratio = -puts.sum(axis=1) / calls.sum(axis=1)
    pc_ratio = pc_ratio.reindex(cl_chart_data.index)
    cp_ratio[cp_ratio < 1] = pc_ratio[cp_ratio < 1]
    imp_vol = imp_vol.diff().reindex(cl.index)
    imp_vol = imp_vol.reindex(cl.index)
    price = price.reindex(cl.index)
    price.fillna(method="ffill", inplace=True)
    rr25d = rr25d.reindex(cl.index)
    rr25d = rr25d.to_frame('1m 25D RR')
    rr25d["atm vol"] = atm_vol
    rr25d["rr chg"] = rr25d["1m 25D RR"].diff()
    rr25d["imp vol chg"] = imp_vol
    rr25d = pd.concat([rr25d, price], axis=1)
    rr25d.fillna(method="ffill", inplace=True)
    rr25d_chg = rr25d.iloc[:, 0].diff()[-1]
    price_diff = rr25d["PX_LAST"].diff()
    price_diff_z = price_diff / price_diff.rolling(30).std()
    rr_chart_diff_data = rr25d[price_diff_z.abs() > 1.5]
    rr_chart_diff_data["rrchg/px_chg"] = rr_chart_diff_data["rr chg"] / _photo_gap(722, 'rr_chart_diff_data["PX_LAST"].diff...')
    exch_dates = CDR(ticker[0] if name not in ['NG', 'EUA'] else ticker[-1]).drange(today() - BDay(90), edate)
    rr_chart_diff_data = rr_chart_diff_data.reindex(exch_dates).fillna(0.0)
    rr25d["rrchg_px_chg"] = rr25d["rr chg"].rolling(5).mean() * rr25d["PX_LAST"].diff().rolling(5).mean()
    rr25d_chart_data = rr25d.reindex(cl_chart_data.index)
    rr_px_chg_chart = chart.line_chart(df=rr_chart_diff_data[["rrchg/px_chg"]],
                                      data_p2y1=price_diff.reindex(rr_chart_diff_data.index).to_frame("Δ Px"),
                                      highlight_dict={"Δ Px": {"mode": "bars"}},
                                      title=f"{ticker[0] if name not in ['NG'] else ticker[-1]} Δ RR / Δ Px (1.5SD)",
                                      y_axis_title="Δ RR/Δ Px", p2y1_axis_title="Δ Px", x_axis_title="date",
                                      hovertemplate="%{x|%b/%d} %{y}", subplots=2, tickformat=None)
    rr_px_chart = chart.line_chart(df=rr25d[["rrchg_px_chg"]].reindex(exch_dates),
                                  data_p2y1=rr25d["PX_LAST"].diff().to_frame("Δ Px").reindex(exch_dates),
                                  title=f"{ticker[0] if name not in ['NG'] else ticker[-1]} Δ RR * Δ Px (5DMVA)",
                                  y_axis_title="(Δ RR * Δ Px) (5DMVA)", p2y1_axis_title="Δ Px", highlight_dict={"Δ Px": {"mode": "bars"}},
                                  x_axis_title="date", hovertemplate="%{x|%b/%d} %{y}", subplots=2, tickformat=None)
    cl_alert = cl_total[-1] / cl_total.rolling(5).mean()[-2] > thr or (cp_ratio[-1] > 2.5 or cp_ratio[-1] < _photo_gap(752, 'call-put lower alert threshold'))
    if result_vol:
        vol_alert = True
    else:
        vol_alert = False
    if result_rr:
        rr_alert = True
    else:
        rr_alert = False
    if cl_alert or vol_alert or rr_alert:
        is_alert = True
    else:
        is_alert = False
    cp_chart = bar_chart(data=cl_chart_data, data1=cp_ratio.to_frame('call/put ratio'),
                         title=f'{name} - Total option volume trades - lots', y1="volume", y2=f"{ticker[0].rpartition(' ')[0]} price",
                         y3='call/put ratio', bar_columns=[f'{name} call', f'{name} put'],
                         line_columns={f'{name} Price': True, f'{name} 20d MA': False}, second_y=True)
    vol_chart = bar_chart(data=rr25d_chart_data[["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "1m 25D RR"]],
                          data1=rr25d_chart_data[["imp vol chg"]], title=f'{name} - 1M RR', y1="Price", y2='RR', y3="Imp vol chg",
                          bar_columns=[], line_columns={'PX_OPEN': False, 'PX_HIGH': False, 'PX_LOW': False, 'PX_LAST': False, "1m 25D RR": True}, second_y=True)
    rr_chart = bar_chart(data=rr25d_chart_data[["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "atm vol"]],
                         data1=rr25d_chart_data[["rr chg"]], title=f'{name} - 1M ATM Vol', y1="Price", y2='ATM VOL', y3="RR chg",
                         bar_columns=[], line_columns={'PX_OPEN': False, 'PX_HIGH': False, 'PX_LOW': False, 'PX_LAST': False, 'atm vol': True}, second_y=True)
    last_date = puts.index[-1]
    alert_df_col_name = f"<a href='{html_path}\\cross_cmds\\{name}_charts.html'>{mkt_to_ins.get(name, name)}</a>"
    table.to_html([[cp_chart, hivg_chart], [rr_chart, vol_chart]], path=ut.convert_path_to_linux(f"{html_path}\\cross_cmds\\{name}_charts.html"))
    if pd.isna(imp_vol[-1]):
        if ticker[0][:2] in ["C ", "W ", "S ", "BO", "SM", "SB", "CT"]:
            alert_vol = imp_vol[-2]
        else:
            alert_vol = imp_vol[-1]
    else:
        alert_vol = imp_vol[-1]
    alert_df = pd.DataFrame([cl_total[-1] / cl_total.rolling(5).mean()[-2], cp_ratio[-1], alert_vol, result_vol,
                             *_photo_gap(808, 'rr...; remaining alert values')], columns=[alert_df_col_name],
                            index=['volume ratio', 'call put ratio', '1m vol change', *_photo_gap(809, 'remaining alert labels')])
    return (cp_chart, vol_chart, rr_chart, hivg_chart, rr_px_chg_chart, rr_px_chart,
            mva_20d_vol_chart, mva_20d_rr_chart, is_alert, last_date, alert_df)


test_dict = {'WTI': ['CLA Comdty', 'ENA Comdty']}
chart_dict_map = {'Brent': 'COA', 'WTI': 'CLA', 'NG': 'NGA', 'TTF': 'TZTA', 'EUA': 'MOA', 'LME Copper': 'LPA', 'Gold': 'GCA', 'Silver': 'SIA'}
all_dict = {
    'Brent': ['COA Comdty'], 'WTI': ['CLA Comdty', 'ENA Comdty'], 'NG': ['GKA Comdty', 'NGA Comdty'],
    'TTF': ['TZTA Comdty', 'FJSA Comdty'], 'EUA': ['MZBA Comdty', 'MOA Comdty'],
    'COMEX Copper': ['HGA Comdty'], 'LME Copper': ['LPA Comdty'], 'Gold': ['GCA Comdty'], 'Silver': ['SIA Comdty'],
    'Corn': ['C A Comdty'], 'Wheat': ['W A Comdty'], 'Soybean': ['S A Comdty'], 'SoyOil': ['BOA Comdty'],
    'SoyMeal': ['SMA Comdty'], 'Sugar': ['SBA Comdty'], 'Cotton': ['CTA Comdty'],
}
gas_dict = {'TTF': ['TZTA Comdty', 'FJSA Comdty'], 'EUA': ['MZBA Comdty', 'MOA Comdty'], 'NG': ['GKA Comdty', 'NGA Comdty']}
oil_dict = {'Brent': ['COA Comdty'], 'WTI': ['CLA Comdty', 'ENA Comdty']}
metal_dict = {'COMEX Copper': ['HGA Comdty'], 'LME Copper': ['LPA Comdty'], 'Gold': ['GCA Comdty'], 'Silver': ['SIA Comdty']}
ags_dict = {'Wheat': 'W A', 'Soybean': 'S A', 'SoyOil': 'BOA', 'SoyMeal': 'SMA', 'Sugar': 'SBA', 'Cotton': 'CTA', 'Corn': 'C A'}
mkt_to_ins = {'Brent': 'COA', 'WTI': 'CLA', 'NG': 'NGA', 'TTF': 'TZTA', 'EUA': 'MOA', 'LME Copper': 'LPA', 'COMEX Copper': 'HGA',
              'Gold': 'GCA', 'Silver': 'SIA', 'Wheat': 'W A', 'Soybean': 'S A', 'SoyOil': 'BOA', 'SoyMeal': 'SMA', 'Sugar': 'SBA', 'Cotton': 'CTA', 'Corn': 'C A'}


def get_gen_month(ticker):
    ticker_dict = tk.decompose_ticker(ticker)
    if ticker_dict['active'] in ['SMA Comdty', 'BOA Comdty']:
        return 'FHKNZ'
    elif ticker_dict['active'] in ['S A Comdty']:
        return 'FHKNX'
    elif ticker_dict['active'] in ['GCA Comdty']:
        return 'GJMQZ'
    elif ticker_dict['active'] in ['SIA Comdty']:
        return 'HKNUZ'
    else:
        return bbg.bref(ticker, ['FUT_GEN_MONTH']).iloc[0, 0]


def get_active_contracts(val):
    tickers = []
    for i in val:
        if i == "MZBA Comdty":
            eua_month = {1: "H", 2: "H", 3: "M", 4: "M", 5: "M", 6: "U", 7: "U", 8: "U", 9: "Z", 10: "Z", 11: "Z", 12: "Z"}
            if today().month == 12:
                eua_year = str(today().year + 1)[-1]
            else:
                eua_year = str(today().year)[-1]
            active_contract = f"MZB{eua_month[today().month]}{eua_year} Comdty"
        else:
            active_contract = bbg.bref(i, ['TICKER']).iloc[0, 0] + ' ' + i.rpartition(' ')[-1]
            expiry = bbg.bref(active_contract, ['LAST_TRADEABLE_DT', 'FUT_NOTICE_FIRST']).iloc[0, :].min()
            if pd.to_datetime(expiry) > today() - BDay(3):
                gen_m = get_gen_month(active_contract)
                active_contract = tk.next_ticker(active_contract, gen_m)
        tickers.append(active_contract)
    return tickers


def agg_options_all(report_type):
    if report_type == 'test':
        ticker_dict = test_dict
    elif report_type.lower() == 'all':
        ticker_dict = all_dict
        subject = 'Cross Commodity Options Report'
        filename = f"{html_path}\\cross_cmds\\total_options_volume.html"
    elif report_type.lower() == 'oil':
        ticker_dict = oil_dict
        subject = 'WTI/Brent options'
        filename = f"{html_path}\\cross_cmds\\oil_options_volume.html"
    elif report_type.lower() == 'gas':
        ticker_dict = gas_dict
        subject = 'GAS/EUA options'
        filename = f"{html_path}\\cross_cmds\\gas_eua_options_volume.html"
    elif report_type.lower() == 'metal':
        ticker_dict = metal_dict
        subject = 'Metal options'
        filename = f"{html_path}\\cross_cmds\\metal_options_volume.html"
    figs = []
    email_figs = []
    last_date_list = []
    chart_dict = {}
    for key, val in ticker_dict.items():
        active_contracts = get_active_contracts(val)
        html_chart, html_chart1, html_chart2, _, last_date, _df = get_option_volume_chart(key, active_contracts)
        email_html = to_html._figure_to_html_table([html_chart, html_chart2, html_chart1], num_columns=3, email_mode=True)
        email_figs.append(email_html)
        figs.append([html_chart, html_chart2, html_chart1])
        last_date_list.append(last_date)
    return figs, email_figs


def generate_regression(series_1, series_2, regression_name, run_date, series_1_name, series_2_name):
    series_1 = series_1.bfill()
    series_2 = series_2.bfill()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series_1, y=series_2, text=series_1.index.strftime('%Y-%m-%d').to_list(),
                             opacity=.8, showlegend=True, mode='markers', name=regression_name))
    fig.add_trace(go.Scatter(x=series_1.iloc[-13:-1], y=series_2.iloc[-13:-1],
                             text=series_1.index[-13:-1].strftime('%Y-%m-%d').to_list(),
                             opacity=.8, showlegend=True, mode='markers', name='last 13 points', marker=dict(color='black', size=8)))
    fig.add_trace(go.Scatter(x=series_1.iloc[[-1]], y=series_2.iloc[[-1]], text=[series_1.index[-1].strftime('%Y-%m-%d')],
                             opacity=.8, showlegend=True, mode='markers', name='latest point', marker=dict(color='red', size=12)))
    x = sm.add_constant(series_1)
    y = series_2
    lm = sm.OLS(y, x).fit()
    reg_param = pd.DataFrame(np.nan, index=range(1, 13), columns=['a', 'b', 'e'])
    reg_param.loc[regression_name, ['a', 'b']] = lm.params
    reg_param.loc[regression_name, 'e'] = lm.scale ** .5
    y_fit = x.dot(lm.params)
    fig.add_trace(go.Scatter(x=series_1, y=y_fit, opacity=.8, showlegend=True, mode='lines', name='fit',
                             text=series_1.index.strftime('%Y-%m-%d').to_list(), marker=dict(color='grey', size=2)))
    fig.add_trace(go.Scatter(x=series_1, y=y_fit + 1 * lm.scale ** .5, mode='lines', name='+1sd',
                             text=series_1.index.strftime('%Y-%m-%d').to_list(), line=dict(color='grey', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=series_1, y=y_fit - 1 * lm.scale ** .5, mode='lines', name='-1sd',
                             text=series_1.index.strftime('%Y-%m-%d').to_list(), line=dict(color='grey', width=2, dash='dash')))
    fig.update_traces(hovertemplate='date: %{text} <br>x: %{x} <br>y: %{y}')
    fig.update_layout(title={'text': _photo_gap(1022, f"Last 180 day {regression_name} as of {run_date.strftime('%Y-%m-%d')}<br> rsqr:{{lm.rs..."), 'x': .5, 'xanchor': 'center'},
                       legend=dict(orientation="h", yanchor="bottom", y=-.25, xanchor="center", x=.5),
                       xaxis_title=series_1_name, yaxis_title=series_2_name, width=900, height=600)
    return fig


def get_vol(chart_dict=None, ins_list=None, only_imp_v_realised=False):
    if not chart_dict:
        chart_dict = {}
    log.info("Running Get Vol")
    if not ins_list:
        ins_list = ['CLA', 'COA', 'NGA', 'TZTA', 'MOA', 'LPA', 'HGA', 'GCA', 'SIA']
    sdate = today() - BDay(365)
    edate = today() - BDay(1)
    fields = ['PX_LAST', "30DAY_IMPVOL_100.0%MNY_DF", "3MTH_IMPVOL_100.0%MNY_DF", "6MTH_IMPVOL_100.0%MNY_DF", "12MTH_IMPVOL_100.0%MNY_DF"]
    df_total = pd.DataFrame()
    df_oil = pd.DataFrame()
    df_gas = pd.DataFrame()
    df_total1 = pd.DataFrame()
    df_oil1 = pd.DataFrame()
    df_gas1 = pd.DataFrame()
    imp_vol_vs_realised_charts = []
    data_dict_imp_vol_vs_realised_charts = {}
    for ins in ins_list:
        log.info(f"Processing {ins} Comdty")
        key = ins
        if ins == 'TZTA':
            ins = 'FJSA'
        if ins == 'MOA':
            eua_month = {1: "H", 2: "H", 3: "M", 4: "M", 5: "M", 6: "U", 7: "U", 8: "U", 9: "Z", 10: "Z", 11: "Z", 12: "H"}
            if today().month == 12:
                eua_year = str(today().year + 1)[-1]
            else:
                eua_year = str(today().year)[-1]
            gen_month = "HMUZ"
            ticker = f"MZB{eua_month[today().month]}{eua_year} Comdty"
            cdr_ticker = f"MO{eua_month[today().month]}{eua_year} Comdty"
        else:
            flat_ticker = bbg.bref(f"{ins} Comdty", ['TICKER'])  # .iloc[0, 0]
            if isinstance(flat_ticker.columns, pd.MultiIndex):
                ticker = flat_ticker.iloc[0, 1] + " Comdty"
            else:
                ticker = flat_ticker.iloc[0, 0] + " Comdty"
            gen_month = get_gen_month(ticker)
        if ins != 'MOA':
            ticker = tk.next_ticker(ticker, gen_month)
        df = pd.DataFrame()
        df1 = pd.DataFrame()
        price = bbg.bdh(ticker, fields, sdate, edate)
        tr_raw = bbg.bdh(ticker, ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"], sdate, edate)
        tr_raw["HL"] = tr_raw.PX_HIGH - tr_raw.PX_LOW
        tr_raw["HC_p"] = abs(tr_raw.PX_HIGH - tr_raw.shift(1).PX_LAST)
        tr_raw["LC_p"] = abs(tr_raw.PX_LOW - tr_raw.shift(1).PX_LAST)
        tr_raw["5DATR"] = tr_raw[["HL", "HC_p", "LC_p"]].fillna(0).max(axis=1).rolling(5).mean()
        price["5D_MVA_ATR"] = tr_raw["5DATR"]
        client = RTHQueryClient
        if ticker.startswith("FJS"):
            ticker = ticker.replace("FJS", "TZT")
        imp_vol_c = client.get_bvol(ops_codes=convert_ticker(ticker), start_date=today() - BDay(90), end_date=edate, specific_call="0.5C")
        if len(imp_vol_c) > 0:
            imp_vol_c = imp_vol_c.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
            imp_vol_c = imp_vol_c.loc[~imp_vol_c["0.5D"].isna()]
            imp_vol_c = imp_vol_c[~imp_vol_c.index.duplicated(keep="last")]
        imp_vol_p = client.get_bvol(ops_codes=convert_ticker(ticker), start_date=today() - BDay(90), end_date=edate, specific_call="0.5P")
        if len(imp_vol_p) > 0:
            imp_vol_p = imp_vol_p.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
            imp_vol_p = imp_vol_p.loc[~imp_vol_p["0.5D"].isna()]
            imp_vol_p = imp_vol_p[~imp_vol_p.index.duplicated(keep="last")]
        imp_vol = (imp_vol_c["0.5D"] + imp_vol_p["0.5D"]) / 2 * 100
        if len(imp_vol) > 0:
            try:
                _, _, func, _ = calibrate_rth_to_bbg_asof(imp_vol, price["30DAY_IMPVOL_100.0%MNY_DF"])
                imp_vol = imp_vol.apply(func)
                imp_vol = imp_vol.to_frame('30DAY_IMPVOL_100.0%MNY_DF')
                imp_vol.index = pd.to_datetime(imp_vol.index)
            except Exception as e:
                log.error(f"Error Calibrating RTH to BBG for {ticker}: {e}")
                imp_vol = pd.DataFrame()
        if isinstance(price.columns, pd.MultiIndex):
            price = price[ticker]
        if not imp_vol.empty:
            price['30DAY_IMPVOL_100.0%MNY_DF'] = price['30DAY_IMPVOL_100.0%MNY_DF'].combine_first(imp_vol['30DAY_IMPVOL_100.0%MNY_DF'])
        price.index.name = "date"
        price["BRK_EVN_VS_5D_MVA_ATR"] = (price["PX_LAST"] * (price["30DAY_IMPVOL_100.0%MNY_DF"] / 100)) / _photo_gap(1130, 'remaining break-even / ATR expression')
        price_bbg = price[:price["3MTH_IMPVOL_100.0%MNY_DF"].last_valid_index()]
        price = price[:price["30DAY_IMPVOL_100.0%MNY_DF"].last_valid_index()]
        price["3MTH_IMPVOL_100.0%MNY_DF"] = price["30DAY_IMPVOL_100.0%MNY_DF"].rolling(60).mean()
        price["6MTH_IMPVOL_100.0%MNY_DF"] = price["30DAY_IMPVOL_100.0%MNY_DF"].rolling(80).mean()
        price["12MTH_IMPVOL_100.0%MNY_DF"] = price["30DAY_IMPVOL_100.0%MNY_DF"].rolling(120).mean()
        if len(price) > 0:
            price = price[~price.index.duplicated(keep="first")]
            price_bbg = price_bbg[~price_bbg.index.duplicated(keep="first")]
            price.fillna(method='ffill', inplace=True)
            price.fillna(method='bfill', inplace=True)
            price_bbg.fillna(method='ffill', inplace=True)
            price_bbg.fillna(method='bfill', inplace=True)
            price_chg = 100 * np.log(price['PX_LAST'] / price['PX_LAST'].shift(1))
            hvol_5d = np.sqrt(252) * price_chg.rolling(5).std()
            hvol_8d = np.sqrt(252) * price_chg.rolling(8).std()
            hvol_13d = np.sqrt(252) * price_chg.rolling(13).std()
            hvol_34d = np.sqrt(252) * price_chg.rolling(34).std()
            hvol_50d = np.sqrt(252) * price_chg.rolling(50).std()
            price_diff = price.diff()
            price_diff_bbg = price_bbg.diff()
            price_diff.drop('PX_LAST', axis=1, inplace=True)
            price_diff_bbg.drop('PX_LAST', axis=1, inplace=True)
            price_diff["chg_vol/chg_px"] = price_diff["30DAY_IMPVOL_100.0%MNY_DF"] / price_chg
            price_z = price_diff / price_diff.rolling(250).std()
            price_z_bbg = price_diff_bbg / price_diff_bbg.rolling(250).std()
            price_chg_z = price_chg / price_chg.rolling(30).std()
            price_vol_z = price_chg_z * price_z["30DAY_IMPVOL_100.0%MNY_DF"]
            plot_df = (price_chg.rolling(5).mean() * price_diff["30DAY_IMPVOL_100.0%MNY_DF"].rolling(5).mean()).to_frame("chg_px_chg_vol")
            vol_px_chart = chart.line_chart(df=plot_df[["chg_px_chg_vol"]],
                                            data_p2y1=price["PX_LAST"].reindex(plot_df.index).diff().to_frame("Δ Px"),
                                            title=f"{ticker} Δ Px * Δ Vol (5DMVA)", y_axis_title="(Δ vol * chg px) (5DMVA)",
                                            highlight_dict={"Δ Px": {"mode": "bars"}}, p2y1_axis_title="Δ Px", x_axis_title="date",
                                            hovertemplate="%{x|%b/%d} %{y}", subplots=2, tickformat=None)
            fltrd_prc_chg = price_chg[price_chg_z.abs() > 1.5]
            fltrd_prc_chg = fltrd_prc_chg.reindex(price_chg_z.index)
            exchg_dates = CDR(ticker if ins not in ["MOA"] else cdr_ticker).drange(today() - BDay(180), edate)
            d_plot_df = (price_diff["30DAY_IMPVOL_100.0%MNY_DF"] / fltrd_prc_chg).reindex(exchg_dates).to_frame(_photo_gap(1180, 'clipped ratio chart column name / call tail'))
            dvol_by_dpx_chart = chart.line_chart(df=d_plot_df, data_p2y1=price["PX_LAST"].reindex(d_plot_df.index).diff().to_frame("Δ Px"),
                                                highlight_dict={"Δ Px": {"mode": "bars"}}, title=f"{ticker} Δ Vol / Δ Px (1.5SD)",
                                                y_axis_title="Change in vol / chg px", p2y1_axis_title="Δ Px", x_axis_title="date",
                                                hovertemplate="%{x|%b/%d} %{y}", subplots=2, tickformat=None)
            sdate_regg = today() - BDay(180)
            d_vol_price_regression = generate_regression(price_chg.loc[sdate_regg:], price_diff["30DAY_IMPVOL_100.0%MNY_DF"].loc[sdate_regg:],
                                                        f"{ticker} Δ Vol vs Δ Px", price_chg.index[-1], "Δ Price", "Δ Vol")
            vol_price_regression = generate_regression(price["PX_LAST"].loc[sdate_regg:], price_diff["30DAY_IMPVOL_100.0%MNY_DF"].loc[sdate_regg:],
                                                      f"{ticker} Δ Vol vs Px", price.index[-1], "Price", "Δ Vol")
            px_change_figs = [vol_px_chart, chart_dict.get(key, f"Missing {key}"), dvol_by_dpx_chart,
                              *_photo_gap(1210, 'chart...; remaining price-change figures')]
            figs_ = to_html._figure_to_html_table(px_change_figs, num_columns=2, email_mode=False)
            table.to_html([figs_], path=ut.convert_path_to_linux(f"{html_path}\\cross_cmds\\{ins}_vol_px.html"))
            df['Name'] = np.nan
            df['3m IMP Chg'] = price_diff_bbg['3MTH_IMPVOL_100.0%MNY_DF']
            df['BE/5DMVATR'] = price['BRK_EVN_VS_5D_MVA_ATR']
            df["1m vs 8d"] = price['30DAY_IMPVOL_100.0%MNY_DF'] - hvol_8d
            df['1m vs 8d zscore'] = df['1m vs 8d'] / df['1m vs 8d'].rolling(250).std()
            df['3m vs 13d'] = price['3MTH_IMPVOL_100.0%MNY_DF'] - hvol_8d.reindex(price.index)
            df['3m vs 13d zscore'] = df['3m vs 13d'] / df['3m vs 13d'].rolling(250).std()
            df['6m vs 34d'] = price['6MTH_IMPVOL_100.0%MNY_DF'] - hvol_34d.reindex(price.index)
            df['6m vs 34d zscore'] = df['6m vs 34d'] / df['6m vs 34d'].rolling(250).std()
            df['12m vs 50d'] = price['12MTH_IMPVOL_100.0%MNY_DF'] - hvol_50d.reindex(price.index)
            df['12m vs 50d zscore'] = df['12m vs 50d'] / df['12m vs 50d'].rolling(250).std()
            df['13d realized'] = hvol_13d
            df['13d realized zscore'] = (hvol_13d - hvol_13d.rolling(250).mean()) / hvol_13d
            df['thr'] = 1.5
            df['_thr'] = -1.5
            df['Name'] = f"<a href='{html_path}\\cross_cmds\\{ins}_vol_px.html'>{ins}</a>"
            df['_last_update'] = price.index[-1].strftime("%Y-%m-%d")
            df.fillna(method='ffill', inplace=True)
            price_z1 = df[['1m vs 8d zscore', '3m vs 13d zscore', '6m vs 34d zscore', '12m vs 50d zscore']]
            if ins in ['COA', 'NGA', 'FJSA', 'HGA', 'GCA']:
                exchg_dates = CDR(ticker if ins not in ["MOA"] else cdr_ticker).drange(today() - BDay(180), edate)
                plot_data = df[["1m vs 8d", "3m vs 13d", "12m vs 50d"]].reindex(exchg_dates)
                if (vol_v_real_df_1m := data_dict_imp_vol_vs_realised_charts.get("1m vs 8d", None)) is not None:
                    data_dict_imp_vol_vs_realised_charts["1m vs 8d"] = pd.concat([vol_v_real_df_1m, plot_data[["1m vs 8d"]].rename(columns={"1m vs 8d": ins})], axis=1)
                else:
                    data_dict_imp_vol_vs_realised_charts["1m vs 8d"] = plot_data[["1m vs 8d"]].rename(columns={"1m vs 8d": ins})
                if (vol_v_real_df_3m := data_dict_imp_vol_vs_realised_charts.get("3m vs 13d", None)) is not None:
                    data_dict_imp_vol_vs_realised_charts["3m vs 13d"] = pd.concat([vol_v_real_df_3m, plot_data[["3m vs 13d"]].rename(columns={"3m vs 13d": ins})], axis=1)
                else:
                    data_dict_imp_vol_vs_realised_charts["3m vs 13d"] = plot_data[["3m vs 13d"]].rename(columns={"3m vs 13d": ins})
                if (vol_v_real_df_12m := data_dict_imp_vol_vs_realised_charts.get("12m vs 50d", None)) is not None:
                    data_dict_imp_vol_vs_realised_charts["12m vs 50d"] = pd.concat([vol_v_real_df_12m, plot_data[["12m vs 50d"]].rename(columns={"12m vs 50d": ins})], axis=1)
                else:
                    data_dict_imp_vol_vs_realised_charts["12m vs 50d"] = plot_data[["12m vs 50d"]].rename(columns={"12m vs 50d": ins})
            if any(price_z1.iloc[-1, :] > 1.5) or any(price_z1.iloc[-1, :] < -1.5):
                df_total = pd.concat([df_total, df.iloc[-1:, :]], axis=0)
                if ins in ['CLA', 'COA']:
                    df_oil = pd.concat([df_oil, df.iloc[-1:, :]], axis=0)
                elif ins in ['NGA', 'TZTA', 'MOA', 'FJSA', 'MZBA']:
                    df_gas = pd.concat([df_gas, df.iloc[-1:, :]], axis=0)
            df1['Name'] = np.nan
            df1['1m IV Chg'] = price_diff['30DAY_IMPVOL_100.0%MNY_DF']
            df1['1m IV Chg zscore'] = price_z['30DAY_IMPVOL_100.0%MNY_DF']
            df1['Price * IV (1m)'] = price_vol_z
            df1['Price Chg'] = price_chg
            df1['3m IV Chg'] = price_diff['3MTH_IMPVOL_100.0%MNY_DF']
            df1['3m IV Chg zscore'] = price_z['3MTH_IMPVOL_100.0%MNY_DF']
            df1['6m IV Chg'] = price_diff['6MTH_IMPVOL_100.0%MNY_DF']
            df1['6m IV Chg zscore'] = price_z['6MTH_IMPVOL_100.0%MNY_DF']
            df1['12m IV Chg'] = price_diff['12MTH_IMPVOL_100.0%MNY_DF']
            df1['12m IV Chg zscore'] = price_z['12MTH_IMPVOL_100.0%MNY_DF']
            df1['thr'] = 1.5
            df1['_thr'] = -1.5
            df1['Name'] = f"<a href='{html_path}\\cross_cmds\\{ins}_vol_px.html'>{ins}</a>"
            df1['_last_update'] = price.index[-1].strftime("%Y-%m-%d")
            df1.fillna(method='ffill', inplace=True)
            if any(price_z.iloc[-1, :] > 1.5) or any(price_z.iloc[-1, :] < -1.5) or _photo_gap(1274, 'np.abs(price_vol_z[-1]) ...'):
                df_total1 = pd.concat([df_total1, df1.iloc[-1:, :]], axis=0)
                if ins in ['CLA', 'COA']:
                    df_oil1 = pd.concat([df_oil1, df1.iloc[-1:, :]], axis=0)
                elif ins in ['NGA', 'TZTA', 'MOA', 'FJSA', 'MZBA']:
                    df_gas1 = pd.concat([df_gas1, df1.iloc[-1:, :]], axis=0)
    for key, value in data_dict_imp_vol_vs_realised_charts.items():
        imp_vs_realised_plot = chart.line_chart(df=value, y_axis_title="vol vs realised", x_axis_title="Date", tickformat=None, title=key)
        imp_vol_vs_realised_charts.append(imp_vs_realised_plot)
    figs_imp_vol_v_realized = to_html._figure_to_html_table(imp_vol_vs_realised_charts, num_columns=3, email_mode=False)
    if only_imp_v_realised:
        return figs_imp_vol_v_realized
    table.to_html([figs_imp_vol_v_realized], path=ut.convert_path_to_linux(f"{html_path}\\cross_cmds\\vol_v_realised.html"))
    df_total.reset_index(drop=True, inplace=True)
    df_total.to_csv(ut.convert_path_to_linux(f"{folder_path}imp_vs_real_vol.csv"))
    df_oil.reset_index(drop=True, inplace=True)
    df_oil.to_csv(ut.convert_path_to_linux(f"{folder_path}imp_vs_real_vol_oil.csv"))
    df_gas.reset_index(drop=True, inplace=True)
    df_gas.to_csv(ut.convert_path_to_linux(f"{folder_path}imp_vs_real_vol_gas.csv"))
    df_total1.reset_index(drop=True, inplace=True)
    df_total1.to_csv(ut.convert_path_to_linux(f"{folder_path}imp_vs_real_vol_ivchg.csv"))
    df_oil1.reset_index(drop=True, inplace=True)
    df_oil1.to_csv(ut.convert_path_to_linux(f"{folder_path}imp_vs_real_vol_oil_ivchg.csv"))
    df_gas1.reset_index(drop=True, inplace=True)
    df_gas1.to_csv(ut.convert_path_to_linux(f"{folder_path}imp_vs_real_vol_gas_ivchg.csv"))
    return df_total, df_total1


def vol_alert(subset=None):
    df_option = pd.DataFrame()
    figs_option = []
    chart_dict = {}
    web_chart_dict = {}
    for key, val in all_dict.items():
        if isinstance(subset, list) and key not in subset:
            continue
        log.info(f"Generating Charts for {key}")
        if key in ['EUA']:
            active_contracts = get_active_contracts(val)
        else:
            active_contracts = get_active_contracts(val)
        (fig_option, fig_option_1, fig_option_2, fig_option_3, rr_px_delta_chart, rr_px_chg_chart,
         mva_20d_vol_chart, mva_20d_rr_chart, is_alert, last_date, df) = get_option_volume_chart(key, active_contracts)
        if chart_key := chart_dict_map.get(key, None):
            chart_dict[chart_key] = rr_px_chg_chart
            chart_dict[f"{chart_key}_2"] = rr_px_delta_chart
        if len(df) > 0 and is_alert:
            df_option = pd.concat([df_option, df], axis=0)
            figs_option.append([fig_option, fig_option_2, fig_option_1, fig_option_3])
            figs_option.append([mva_20d_vol_chart, mva_20d_rr_chart])
        web_chart_dict[key] = [fig_option, fig_option_2, fig_option_1, fig_option_3, mva_20d_vol_chart, mva_20d_rr_chart]
    if len(df_option) > 0:
        df_option.index.name = 'Name'
        df_option.reset_index(inplace=True)
        html_option = table.html_format(df_option, precision=1, show_date=True,
                                        hide_cols=['cross_vol', *_photo_gap(1341, 'cr...; remaining hidden columns')],
                                        format_column={
                                            'Name': {'width': '100px', 'text-align': 'center', 'right_border': True},
                                            'volume ratio': {'width': '100px', 'text-align': 'center'},
                                            'call put ratio': {'width': '100px', 'text-align': 'center'},
                                            '1m vol change': {'width': '100px', 'text-align': 'center', 'highlight': _photo_gap(1346, 'highlight settings')},
                                            '1m RR change': {'width': '100px', 'text-align': 'center', 'highlight': _photo_gap(1347, 'highlight settings')},
                                        })
        html_option = html_option + table.html_text("<i>Green highlight indicates cross above 20D SMA<br>Red highlight indicates cross below 20D SMA</i>")
        table.to_html(figs_option, path=ut.convert_path_to_linux(f"{folder_path}charts\\range_vol_option.html"))
    else:
        html_option = 'No range vol in options volume'
    if isinstance(subset, list):
        ins_list = [mkt_to_ins.get(x, None) for x in subset]
    else:
        ins_list = None
    imp_vs_real_vol, iv_chg = get_vol(chart_dict=chart_dict, ins_list=ins_list)
    if len(imp_vs_real_vol) > 0:
        html_imp_vs_real = table.html_format(
            df=imp_vs_real_vol, precision=2, hide_cols=['thr', '_thr', '_last_update', '3m IMP Chg'], show_date=True,
            format_column={
                'Name': {'width': '60px', 'text-align': 'left', 'right_border': True},
                'BE/5DMVATR': {'width': '100px', 'text-align': 'center', 'right_border': True},
                '1m vs 8d': {'width': '100px', 'text-align': 'center'},
                '1m vs 8d zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['1m vs 8d zscore', 'thr', '_thr']},
                '3m vs 13d': {'width': '100px', 'text-align': 'center'},
                '3m vs 13d zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['3m vs 13d zscore', 'thr', '_thr']},
                '6m vs 34d': {'width': '100px', 'text-align': 'center'},
                '6m vs 34d zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['6m vs 34d zscore', 'thr', '_thr']},
                '12m vs 50d': {'width': '100px', 'text-align': 'center'},
                '12m vs 50d zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['12m vs 50d zscore', 'thr', '_thr']},
                '13d realized': {'width': '100px', 'text-align': 'center'},
                '13d realized zscore': {'width': '100px', 'text-align': 'center'},
            })
    else:
        html_imp_vs_real = 'No implied vs realized vol alert'
    if len(iv_chg) > 0:
        html_iv_chg = table.html_format(
            df=iv_chg, precision=2, hide_cols=['thr', '_thr', '_last_update'], show_date=True,
            format_column={
                'Name': {'width': '60px', 'text-align': 'left', 'right_border': True},
                '1m IV Chg': {'width': '100px', 'text-align': 'center'},
                'Price Chg': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['Price * IV (1m)', 'thr', '_thr']},
                'Price * IV (1m)': {'width': '100px', 'text-align': 'center', 'right_border': False, 'highlight': ['Price * IV (1m)', 'thr', '_thr']},
                '1m IV Chg zscore': {'width': '100px', 'text-align': 'center', 'right_border': False, 'highlight': ['1m IV Chg zscore', 'thr', '_thr']},
                '3m IV Chg': {'width': '100px', 'text-align': 'center'},
                '3m IV Chg zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['3m IV Chg zscore', 'thr', '_thr']},
                '6m IV Chg': {'width': '100px', 'text-align': 'center'},
                '6m IV Chg zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['6m IV Chg zscore', 'thr', '_thr']},
                '12m IV Chg': {'width': '100px', 'text-align': 'center'},
                '12m IV Chg zscore': {'width': '100px', 'text-align': 'center', 'right_border': True, 'highlight': ['12m IV Chg zscore', 'thr', '_thr']},
            })
    else:
        html_iv_chg = 'No implied vol change alert'
    return [
        "<div style='font-family:Calibri;' >", '<br><b>Option volume alert: </b><br>', html_option,
        '*Ags are on a two day lag for vol and rr<br>',
        u'<a href="{}charts\\range_vol_option.html">Option Charts</a><br>'.format(folder_path),
        '<br><b>Implied vs realized volatility alert: </b><br>',
        f"<a href='{html_path}\\cross_cmds\\vol_v_realised.html'>Implied vs Realized Charts</a></br>",
        html_imp_vs_real, '<br><b>Implied volatility change alert: </b><br>', html_iv_chg, '</br>',
        '<b>Volatility Indexes</b><br>',
        '<a href="https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/2176090113/Index+Formulas">Index Formulas</a>',
    ], web_chart_dict


def get_macro_index_components():
    sdate = today() - BDay(365)
    edate = today() - BDay(1)
    tickers = {"ES": "ES1 Index", "TY": "TY1 Comdty", "EURUSD": "EURUSD 1M"}
    bbg_tickers = {"ES": "ES1 Index", "TY": "TY1 Comdty", "EURUSD": "EURUSDV1M Curncy"}
    macro_vol = {}
    index = pd.bdate_range(sdate, edate)
    for k, v in tickers.items():
        if k == "TY":
            contract = bbg.bref(v, ["FUT_CUR_GEN_TICKER"]).iloc[0][0]
            rvx_ticker = f"{contract} F C"
        elif k == "ES":
            rvx_ticker = "SPX 1M"
        else:
            rvx_ticker = v
        bbg_ticker_ = bbg.bref(bbg_tickers[k], ["TICKER"]).iloc[0][0]
        if not pd.isna(bbg_ticker_):
            suffix = bbg_tickers[k].split(" ")[-1]
            bbg_ticker = bbg_ticker_ + " " + suffix
        else:
            bbg_ticker = bbg_tickers[k]
        field = "30DAY_IMPVOL_100.0%MNY_DF" if not k == "EURUSD" else "PX_LAST"
        bbg_data = bbg.bdh(bbg_ticker, [field], sdate, edate)
        if not bbg_data.empty:
            bbg_data = bbg_data[field]
            bbg_data = bbg_data.reindex(index)
            bbg_data.name = k
        rvx_data = fetch_series(rvx_ticker, "ATMVOL", sdate, edate)
        rvx_data.name = k
        if k == "TY":
            rvx_data = rvx_data * 100
        data = bbg_data.combine_first(rvx_data).ffill() if not bbg_data.empty else rvx_data.ffill()
        data = data.dropna()
        data = data.replace(0, np.nan)
        data = data.fillna(method='ffill')
        if data.empty:
            print(f"Missing data for {k}")
        data = data.reindex(index)
        macro_vol[k] = data
    return macro_vol


def get_cmd_index_components():
    cmds_vol_dict = {"CO": "COA Comdty", "LP": "LPA Comdty", "GC": "GCA Comdty", "SI": "SIA Comdty"}
    cmds_vol = {}
    client = RTHQueryClient
    sdate = today() - BDay(365)
    edate = today() - BDay(1)
    index = pd.bdate_range(sdate, edate)
    for k, v in cmds_vol_dict.items():
        contract = bbg.bref(v, ['TICKER']).iloc[0][0]
        ticker = f"{contract} Comdty"
        bbg_data = bbg.bdh(ticker, ["30DAY_IMPVOL_100.0%MNY_DF"], sdate, edate)
        bbg_data = bbg_data["30DAY_IMPVOL_100.0%MNY_DF"]
        bbg_data = bbg_data.reindex(index)
        bbg_data.name = k
        imp_vol_c = client.get_bvol(ops_codes=convert_ticker(ticker), start_date=today() - BDay(90), end_date=edate, specific_call="0.5C")
        if len(imp_vol_c) > 0:
            imp_vol_c = imp_vol_c.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
        imp_vol_p = client.get_bvol(ops_codes=convert_ticker(ticker), start_date=today() - BDay(90), end_date=edate, specific_call="0.5P")
        if len(imp_vol_p) > 0:
            imp_vol_p = imp_vol_p.reset_index(level=['ric', 'ticker', 'option_expiry', 'underlying_settle_price'])
        imp_vol = (imp_vol_c["0.5D"] + imp_vol_p["0.5D"]) / 2 * 100
        if len(imp_vol) > 0:
            imp_vol = imp_vol.drop_duplicates().dropna()
            imp_vol.index = pd.to_datetime(imp_vol.index)
        data = imp_vol
        data = data[~data.index.duplicated(keep="last")]
        data.name = k
        data = bbg_data.combine_first(data).ffill()
        data = data.reindex(index)
        cmds_vol[k] = data
    return cmds_vol


macro_weights = {"ES": .5, "TY": .3, "EURUSD": .2}
cmds_weights = {"CO": .4, "LP": .3, "GC": .2, "SI": .1}


def generate_index_data():
    macro_data = get_macro_index_components()
    macro = pd.DataFrame(macro_data.values()).T
    macro_weighted = macro * pd.Series(macro_weights)
    macro_weighted["MacroVol"] = macro_weighted.fillna(method='ffill').sum(axis=1)
    macro["MacroVol"] = macro_weighted["MacroVol"]
    macro_weighted["MacroVol_20D_SMA"] = macro_weighted["MacroVol"].rolling(20).mean()
    _, result_macro = get_ma_cross(macro["MacroVol"], num_days=20, latest=False)
    macro_weighted["MacroVol_Cross"] = result_macro
    macro["MacroVol_Cross"] = result_macro
    cmds_data = get_cmd_index_components()
    cmds = pd.DataFrame(cmds_data.values()).T
    cmds_weighted = cmds * pd.Series(cmds_weights)
    cmds_weighted["CmdsVol"] = cmds_weighted.fillna(method='ffill').sum(axis=1)
    cmds["CmdsVol"] = cmds_weighted["CmdsVol"]
    cmds_weighted["CmdsVol_20D_SMA"] = cmds_weighted["CmdsVol"].rolling(20).mean()
    _, result_cmds = get_ma_cross(cmds["CmdsVol"], num_days=20, latest=False)
    cmds_weighted["CmdsVol_Cross"] = result_cmds
    cmds["CmdsVol_Cross"] = result_cmds
    index_data = {"Macro": macro, "MacroWeighted": macro_weighted, "Cmds": cmds, "CmdsWeighted": cmds_weighted}
    return index_data


def get_per_component_vol_index():
    macro_data = get_macro_index_components()
    macro = pd.DataFrame(macro_data.values()).T
    sma_df_macro = {}
    for col in macro.columns:
        tmp_df = pd.DataFrame()
        rolling_sma_macro, result = get_ma_cross(macro[col], num_days=20, latest=False)
        tmp_df[f"{col}"] = macro[col]
        tmp_df[col + "_20D_SMA"] = rolling_sma_macro.dropna()
        tmp_df[col + "_Cross"] = result
        sma_df_macro[col] = tmp_df
    cmds_data = get_cmd_index_components()
    cmds = pd.DataFrame(cmds_data.values()).T
    sma_df_cmds = {}
    for col in cmds.columns:
        tmp_df = pd.DataFrame()
        rolling_sma_cmds, result = get_ma_cross(cmds[col], num_days=20, latest=False)
        tmp_df[f"{col}"] = cmds[col]
        tmp_df[col + "_20D_SMA"] = rolling_sma_cmds.dropna()
        tmp_df[col + "_Cross"] = result
        sma_df_cmds[col] = tmp_df
    return sma_df_macro, sma_df_cmds


def get_vol_index_chart(df, title, alt_widths=False):
    if alt_widths:
        width = 900
        height = 600
    else:
        width = 750
        height = 500
    return chart.line_chart(df=df, title=title, y_axis_title="Vol Index", x_axis_title="Date", tickformat=None, width=width, height=height)


def generate_vol_index_charts(alt_widths=False):
    index_data = generate_index_data()
    macro_plot_data = index_data["MacroWeighted"][["MacroVol", "MacroVol_20D_SMA"]].loc["2024-04-01":]
    macro_chart = get_vol_index_chart(macro_plot_data, "Macro Vol Index", alt_widths=alt_widths)
    cmds_plot_data = index_data["CmdsWeighted"][["CmdsVol", "CmdsVol_20D_SMA"]].loc["2024-04-01":]
    cmds_chart = get_vol_index_chart(cmds_plot_data, "Cmds Vol Index", alt_widths=alt_widths)
    return dict(macro=macro_chart, cmds=cmds_chart)


def send_options_report(dev=False):
    user = getpass.getuser()
    if user == "pmlo25_svc":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_PML025_SVC"]
    elif user == "rzhao":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_RZHAO"]
    index_vol_charts = generate_vol_index_charts()
    html_tables, web_charts_dict = vol_alert()
    figs_all = []
    figs_all_email = []
    figs_gas = []
    figs_gas_email = []
    figs_oil = []
    figs_oil_email = []
    figs_metal = []
    figs_metal_email = []
    figs_ags = []
    figs_all.append(list(index_vol_charts.values()))
    for k in all_dict.keys():
        figs = web_charts_dict.get(k, [f'Missing {k}'])
        figs_web = to_html._figure_to_html_table(figs, num_columns=3, email_mode=False)
        if k == "Brent":
            figs_email_raw = list(index_vol_charts.values()) + figs
        else:
            figs_email_raw = figs
        figs_email = to_html._figure_to_html_table(figs_email_raw, num_columns=2, email_mode=True)
        figs_all.append(figs_web)
        figs_all_email.append(figs_email)
        if k in gas_dict.keys():
            figs_gas.append(figs_web)
            figs_gas_email.append(figs_email)
        if k in oil_dict.keys():
            figs_oil.append(figs_web)
            figs_oil_email.append(figs_email)
        if k in metal_dict.keys():
            figs_metal.append(figs_web)
            figs_metal_email.append(figs_email)
        if k in ags_dict.keys():
            figs_ags.append(figs_web)
    if not dev:
        send_email(send_to=send_to_macro, subject='Cross-Commods Options Report', body=html_tables + figs_all_email,
                   **_photo_gap(1678, 'clipped send_email call tail'))
        send_email(send_to=_photo_gap(42, 'gas recipient list tail'), subject='GAS/EUA options', body=html_tables[:4] + figs_gas_email,
                   **_photo_gap(1679, 'clipped send_email call tail'))
        send_email(send_to=send_to_oil, subject='WTI/Brent options', body=html_tables[:4] + figs_oil_email,
                   **_photo_gap(1680, 'clipped send_email call tail'))
        send_email(send_to=["rzhao@elementcapital.com", "ltrindade"], subject='Metal options', body=html_tables[:4] + figs_metal_email,
                   **_photo_gap(1681, 'clipped send_email call tail'))
    else:
        send_email(send_to=["ltrindade"], subject='Cross-Commods Options Report', body=html_tables + figs_all_email,
                   **_photo_gap(1683, 'clipped send_email call tail'))
        send_email(send_to=["ltrindade"], subject='GAS/EUA options', body=html_tables[:4] + figs_gas_email,
                   **_photo_gap(1684, 'clipped send_email call tail'))
        send_email(send_to=["ltrindade"], subject='WTI/Brent options', body=html_tables[:4] + figs_oil_email,
                   **_photo_gap(1685, 'clipped send_email call tail'))
        send_email(send_to=["ltrindade"], subject='Metal options', body=html_tables[:4] + figs_metal_email,
                   **_photo_gap(1686, 'clipped send_email call tail'))
    table.to_html(html_tables + figs_all, path=f"{html_path}\\cross_cmds\\total_options_volume.html", task_name=report_name)
    table.to_html(figs_gas, path=f"{html_path}\\cross_cmds\\gas_eua_options_volume.html", task_name=report_name)
    table.to_html(figs_oil, path=f"{html_path}\\cross_cmds\\oil_options_volume.html", task_name=report_name)
    table.to_html(figs_metal, path=f"{html_path}\\cross_cmds\\metal_options_volume.html", task_name=report_name)
    table.to_html(figs_ags, path=f"{html_path}\\cross_cmds\\ags_options_volume.html", task_name=report_name)


if __name__ == '__main__':
    send_options_report(dev=False)
