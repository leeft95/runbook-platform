import pandas as pd
import numpy as np
import datetime as dt
import sys
import os
from pandas.tseries.offsets import BDay
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import ecm.cmds.table as table
import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
import ecm.cmds.time_series as ts
from ecm.cmds.config import root_path, output_path, html_path, url, oil_group, gas_group, macro_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, datetime_range, getworkingdays
from ecm.cmds.utils import convert_path_to_linux
from multiprocessing import Pool
from ecm.cmds.quant.intraday_vol import get_ticker
from ecm.cmds.quant.intraday_vol import get_ticker_dict as intraday_vol_get_ticker_dict
from loguru import logger as log

report_name = "Volume Alert"
file_name = "intraday_volume_alert"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"
cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"
folder_path = f"{cc_csv_folder}\\10mins\\"


def get_fom_info():
    fom_path = "\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Market Scan\\FOM_vol_alert.csv"
    fom_comments = pd.read_csv(convert_path_to_linux(fom_path))
    fom_comments.set_index('Unnamed: 0', inplace=True)
    fom_comments_ = fom_comments.copy()
    fom_dict = {}
    sdates = []
    edates = []
    for idx, row in fom_comments_.iterrows():
        mkt_gp = row.name
        if len(row['FOM Dates']) == 10:
            try:
                fom_d0 = dt.datetime.strptime(row['FOM Dates'][:10], '%Y-%m-%d')
            except:
                fom_d0 = dt.datetime.strptime(row['FOM Dates'][:10], '%m/%d/%Y')
            fom_comments_.loc[idx, 'days'] = int(getworkingdays(fom_d0, today()))
            fom_comments_.loc[idx, 'FOM Dates'] = str(dt.datetime.strftime(fom_d0, '%d/%b'))
            fom_d1 = fom_d0 + dt.timedelta(days=1)
            sdates.append(fom_d0)
            edates.append(fom_d1)
        else:
            try:
                fom_d0 = dt.datetime.strptime(row['FOM Dates'][:10], '%Y-%m-%d')
            except:
                fom_d0 = dt.datetime.strptime(row['FOM Dates'][:10], '%m/%d/%Y')
            try:
                fom_d1 = dt.datetime.strptime(row['FOM Dates'][-10:], '%Y-%m-%d')
            except:
                fom_d1 = dt.datetime.strptime(row['FOM Dates'][-10:], '%m/%d/%Y')
            sdates.append(fom_d0)
            edates.append(fom_d1)
        fom_dict[mkt_gp] = {
            'sdate': fom_d0,
            'edate': fom_d1,
        }
    return fom_dict


ins_dict = {
    'COA Comdty': ['OIL', [22, 23]],
    'CLA Comdty': ['OIL', [22, 23]],
    'XBA Comdty': ['OIL', [22, 23]],
    'HOA Comdty': ['OIL', [22, 23]],
    'QSA Comdty': ['OIL', [22, 23]],
    'NGA Comdty': ['GAS', [22, 23]],
    'NGVF Comdty': ['GAS', [22, 23]],
    'NGHJ Comdty': ['GAS', [22, 23]],
    'NGJV Comdty': ['GAS', [22, 23]],
    'TZTA Comdty': ['GAS', [17, 7]],
    'TZTVF Comdty': ['GAS', [17, 7]],
    'TZTHJ Comdty': ['GAS', [17, 7]],
    'TZTJV Comdty': ['GAS', [17, 7]],
    'QQT1 Comdty': ['GAS', [17, 7]],
    'QQT2 Comdty': ['GAS', [17, 7]],
    'QTTF6 Comdty': ['GAS', [17, 7]],
    'QZT1 Comdty': ['GAS', [17, 7]],
    'QZT2 Comdty': ['GAS', [17, 7]],
    'QTT2 Comdty': ['GAS', [17, 7]],
    'QTT3 Comdty': ['GAS', [17, 7]],
    'MOA Comdty': ['GAS', [17, 7]],
    'JXY1 Comdty': ['GAS', [17, 7]],
    'JXY2 Comdty': ['GAS', [17, 7]],
    'XE1 Comdty': ['GAS', [17, 7]],
    'XE2 Comdty': ['GAS', [17, 7]],
    'TM1 Comdty': ['GAS', [17, 7]],
    'XA1 Comdty': ['GAS', [17, 7]],
    'GCA Comdty': ['PM', [22, 23]],
    'SIA Comdty': ['PM', [22, 23]],
    'PLA Comdty': ['PM', [22, 23]],
    'PAA Comdty': ['PM', [22, 23]],
    'BTCA Curncy': ['MC', [22, 23]],
    'DCRA Curncy': ['MC', [22, 23]],
    'HGA Comdty': ['BM', [22, 23]],
    'LMCADS03 Comdty': ['BM', [22, 23]],
    'LMAHDS03 Comdty': ['BM', [22, 23]],
    'LMZSDS03 Comdty': ['BM', [22, 23]],
    'LMNIDS03 Comdty': ['BM', [22, 23]],
    'CUA Comdty': ['BM', [22, 23]],
    'AAA Comdty': ['BM', [22, 23]],
    'ZNAA Comdty': ['BM', [22, 23]],
    'ESA Index': ['MC', [22, 23]],
    'NQA Index': ['MC', [22, 23]],
    'NHA Index': ['MC', [22, 23]],
    'HIA Index': ['MC', [22, 23]],
    'XUA Index': ['MC', [22, 23]],
    'TYA Comdty': ['MC', [22, 23]],
    'EAA Curncy': ['MC', [22, 23]],
    'BPA Curncy': ['MC', [22, 23]],
    'ADA Curncy': ['MC', [22, 23]],
    'JYA Curncy': ['MC', [22, 23]],
    'CDA Curncy': ['MC', [22, 23]],
    'S:COCO 1-2 Comdty': ['OIL', [22, 1]],
    'S:COCO 2-3 Comdty': ['OIL', [22, 1]],
    'S:COCO 3-4 Comdty': ['OIL', [22, 1]],
    'S:COCO Jun-Dec Comdty': ['OIL', [22, 1]],
    'S:COCO Dec-Dec Comdty': ['OIL', [22, 1]],
    'S:CLCL 1-2 Comdty': ['OIL', [22, 23]],
    'S:CLCL 2-3 Comdty': ['OIL', [22, 23]],
    'S:CLCL 3-4 Comdty': ['OIL', [22, 23]],
    'S:CLCL Jun-Dec Comdty': ['OIL', [22, 23]],
    'S:CLCL Dec-Dec Comdty': ['OIL', [22, 23]],
    'S:XBXB 1-2 Comdty': ['OIL', [22, 23]],
    'S:XBXB 2-3 Comdty': ['OIL', [22, 23]],
    'S:HOHO 1-2 Comdty': ['OIL', [22, 23]],
    'S:HOHO 2-3 Comdty': ['OIL', [22, 23]],
    'S:TZTTZT 1-2 Comdty': ['GAS', [22, 23]],
    'S:TZTTZT 2-3 Comdty': ['GAS', [22, 23]],
    'S:NGNG 1-2 Comdty': ['GAS', [22, 23]],
    'S:NGNG 2-3 Comdty': ['GAS', [22, 23]],
    'S:QQTQQT 1-2 Comdty': ['GAS', [22, 23]],
    'S:QQTQQT 2-3 Comdty': ['GAS', [22, 23]],
    'S:QZTQZT 1-2 Comdty': ['GAS', [22, 23]],
    'S:QZTQZT 2-3 Comdty': ['GAS', [22, 23]],
    'S:QZTQZT 3-4 Comdty': ['GAS', [22, 23]],
    'S:QSQS 1-2 Comdty': ['OIL', [22, 23]],
    'S:QSQS 2-3 Comdty': ['OIL', [22, 23]],
    'S:QSQS 3-4 Comdty': ['OIL', [22, 23]],
    'S:QSQS Jun-Dec Comdty': ['OIL', [22, 23]],
    'S:QSQS Dec-Dec Comdty': ['OIL', [22, 23]],
    'S:DATDAT 2-3 Comdty': ['OIL', [22, 23]],
    'S:DATDAT 3-4 Comdty': ['OIL', [22, 23]],
}


def get_price(ticker, use_bbg=True):
    if os.path.exists(f"{folder_path}{ticker}.csv"):
        try:
            price_history = ts.read_csv(f"{folder_path}{ticker}.csv", index_name='time')
            exist_sdate = price_history.index[-2]
            if use_bbg:
                price_new = bbg.bdib(ticker, sdate=exist_sdate, edate=dt.datetime.now(), interval=10)
                price = pd.concat([price_history.iloc[:-2, :], price_new], axis=0)
            else:
                price = price_history
        except:
            price = bbg.bdib(ticker, sdate=today() - dt.timedelta(days=91), edate=dt.datetime.now(), interval=10)
    else:
        price = bbg.bdib(ticker, sdate=today() - dt.timedelta(days=91), edate=dt.datetime.now(), interval=10)
    price.to_csv(convert_path_to_linux(f"{folder_path}{ticker}.csv"))
    return price


def get_gen_month(ticker):
    ticker_dict = tk.decompose_ticker(ticker)
    if ticker_dict['active'] in ['SMA Comdty', 'BOA Comdty']:
        return 'FHKNZ'
    elif ticker_dict['active'] in ['GCA Comdty']:
        return 'GJMQZ'
    elif ticker_dict['active'] in ['SIA Comdty']:
        return 'HKNUZ'
    else:
        raise NotImplementedError("Photo gap: missing get_gen_month branch, source 177-178")
        ret = bbg.bref(ticker, ['FUT_GEN_MONTH'])  # .iloc[0, 0]
        if isinstance(ret.columns, pd.MultiIndex):
            ret = ret.iloc[0, 1]
        else:
            ret = ret.iloc[0, 0]
        return ret


def send_alert_email(alert_dict, asset_class: str, fom_dict):
    df = pd.DataFrame.from_dict(alert_dict, orient='index',
                               columns=['UTC', 'Volume', '10min price chg', 'Zscore', 'Mean vol', 'Delta vs Ref Vwap'])
    df['UTC'] = df['UTC'].dt.strftime('%H:%M')
    df['Names'] = [x.split(' ')[0] for x in df.index]
    for i in df.index:
        name = i.split(' ')[0]
        file_path = f"{html_path}\\cross_cmds\\links\\{i}.html"
        chart_link = f'<a href="{file_path}">{name}</a>'
        df.at[i, 'Name'] = chart_link
    subject_ticker = ','.join(df['Names'])
    df.drop(columns=['Names'], inplace=True)
    df.reset_index(inplace=True, drop=True)
    df = df.set_index("Name").reset_index()
    df_html = table.html_format(
        df=df,
        precision=2,
        format_column={'Name': {'width': '100px', 'text-align': 'Center'},
                       'UTC': {'width': '100px', 'text-align': 'Center'},
                       'Volume': {'width': '100px', 'text-align': 'Center', 'format': '{:,.0f}'},
                       '10min price chg': {'width': '100px', 'text-align': 'Center'},
                       'Zscore': {'width': '100px', 'text-align': 'Center'},
                       'Mean vol': {'width': '100px', 'text-align': 'Center'},
                       'Delta vs Ref Vwap': {'width': '100px', 'text-align': 'Center'},
                       })
    if asset_class == "GAS":
        send_to = gas_group
    elif asset_class == "OIL":
        send_to = oil_group
    else:
        send_to = macro_group
    fom_dict = get_fom_info()
    sdate = fom_dict.get(asset_class, {}).get('sdate', today() - dt.timedelta(days=1))
    edate = fom_dict.get(asset_class, {}).get('edate', today())
    vwap_text = f"VWAP from {sdate.strftime('%Y-%m-%d')} to {edate.strftime('%Y-%m-%d')}"
    send_email(send_to=send_to,
               subject=f'{subject_ticker} Volume Alert {asset_class}', send_from='cmdalrt',
               body=["Contracts that have high volume:<br/>", f"{vwap_text}", df_html])


def process_alerts(i, val, ticker, last_ticker, roll_date, fom_dict, edate):
    alert_dict_oil = {}
    alert_dict_gas = {}
    alert_dict_pm = {}
    alert_dict_bm = {}
    alert_dict_macro = {}
    if ticker is None:
        log.error(f"[{i}] ticker is None! Skipping. last_ticker={last_ticker}, roll_date={roll_date}")
        return alert_dict_oil, alert_dict_gas, alert_dict_pm, alert_dict_bm, alert_dict_macro
    if not isinstance(val, (list, tuple)) or len(val) < 2:
        log.error(f"[{i}] Invalid val format: {val}. Expected [asset_class, hours]. Skipping.")
        return alert_dict_oil, alert_dict_gas, alert_dict_pm, alert_dict_bm, alert_dict_macro
    log.info(f"Processing: {i} -> active_contract={ticker}, last_contract={last_ticker}, roll_date={roll_date}")
    ac = val[0]
    active_time = val[1]
    fom_dates = fom_dict.get(ac, None)
    if fom_dates is None:
        log.warning(f"[{i}] No FOM dates found for asset class '{ac}'. Skipping.")
        return alert_dict_oil, alert_dict_gas, alert_dict_pm, alert_dict_bm, alert_dict_macro
    sdate_vwap = fom_dates.get("sdate").strftime("%Y-%m-%d")
    edate_vwap = fom_dates.get("edate").strftime("%Y-%m-%d")
    try:
        intraday_price = get_price(ticker)
        log.debug(f"[{i}] Retrieved {len(intraday_price)} price rows for {ticker}")
    except Exception as e:
        log.error(f"[{i}] Failed to get price for {ticker}: {e}")
        intraday_price = pd.DataFrame()
    try:
        vwap_overrides = [
            ("VWAP_START_TIME", "00:00:00"),
            ("VWAP_END_TIME", "23:00:00"),
            ("VWAP_START_DT", f"{fom_dates.get('sdate').strftime('%Y%m%d')}"),
            ("VWAP_END_DT", f"{fom_dates.get('edate').strftime('%Y%m%d')}"),
        ]
        alert_vwap_data = bbg.bdh(ticker, ["EQY_WEIGHTED_AVG_PX"], ovrds=vwap_overrides, **fom_dates)
    except Exception as e:
        log.warning(f"[{i}] Failed to get VWAP for {ticker}: {e}")
        alert_vwap_data = pd.DataFrame()
    if len(intraday_price) > 1:
        if i in ['QZT1 Comdty', 'QZT2 Comdty', 'QQT1 Comdty', 'QQT2 Comdty', 'QTT1 Comdty', 'QTT2 Comdty']:
            intraday_price['volume'] = intraday_price['volume'] / 5
        intraday_price = intraday_price.iloc[:-1, :]
        if edate is not None:
            intraday_price = intraday_price.loc[:edate, :]
        date_range_by_minute = pd.DatetimeIndex([dt for dt in datetime_range(intraday_price.index[0],
                                                                           intraday_price.index[-1],
                                                                           dt.timedelta(minutes=10))])
        date_range_by_minute = date_range_by_minute[date_range_by_minute.dayofweek != 5]
        date_range_by_minute = date_range_by_minute[date_range_by_minute.dayofweek != 6]
        volume_by_minute = intraday_price[['volume', 'close']].reindex(date_range_by_minute)
        volume_by_minute.fillna(value=0, inplace=True)
        volume_by_minute['date'] = volume_by_minute.index.date
        volume_by_minute['time'] = volume_by_minute.index.time
        volume_at_minute = volume_by_minute.loc[
            volume_by_minute['time'] == volume_by_minute['time'].iloc[-1], ['volume', 'close']]
        volume_at_minute.drop(volume_at_minute.loc[volume_at_minute.volume == 0].index, axis=0, inplace=True)
        volume_by_minute.drop(volume_by_minute.loc[volume_by_minute['volume'] == 0].index, axis=0, inplace=True)
        if last_ticker is not None and roll_date is not None and roll_date < today() + BDay(3):
            intraday_price_last = get_price(last_ticker)
            if len(intraday_price_last) > 10:
                if edate is not None:
                    intraday_price_last = intraday_price_last.loc[:edate, :]
                date_range_by_minute_last = pd.DatetimeIndex([d for d in
                                                            datetime_range(intraday_price_last.index[0],
                                                                           intraday_price_last.index[-1],
                                                                           dt.timedelta(minutes=10))])
                date_range_by_minute_last = date_range_by_minute_last[date_range_by_minute_last.dayofweek != 5]
                date_range_by_minute_last = date_range_by_minute_last[date_range_by_minute_last.dayofweek != 6]
                volume_by_minute_last = intraday_price_last[['volume', 'close']].reindex(date_range_by_minute_last)
                volume_by_minute_last.fillna(value=0, inplace=True)
                volume_by_minute_last = volume_by_minute_last  # .to_frame('volume')
                volume_by_minute_last['date'] = volume_by_minute_last.index.date
                volume_by_minute_last['time'] = volume_by_minute_last.index.time
                volume_at_minute_last = volume_by_minute_last.loc[
                    volume_by_minute_last['time'] == volume_by_minute['time'].iloc[-1], ['volume', 'close']]
                volume_at_minute_last.drop(volume_at_minute_last.loc[volume_at_minute_last.volume == 0].index, axis=0,
                                           inplace=True)
                volume_by_minute_last.drop(
                    volume_by_minute_last.loc[volume_by_minute_last['volume'] == 0].index, axis=0, inplace=True)
                replace_daily_volume = volume_at_minute_last[volume_at_minute_last.index < roll_date].reindex(
                    volume_at_minute[volume_at_minute.index < roll_date].index)
                volume_at_minute = pd.concat([volume_at_minute_last[volume_at_minute_last.index < roll_date],
                                             volume_at_minute[volume_at_minute.index >= roll_date]], axis=0)
                volume_by_minute = pd.concat([volume_by_minute_last[volume_by_minute_last.index < roll_date],
                                             volume_by_minute[volume_by_minute.index >= roll_date]], axis=0)
        if len(volume_at_minute) > 20:
            if len(volume_by_minute) > 2640:
                raise NotImplementedError("Photo gap: intraday_volume_alert_new ticker-list right edges, source 342-355")
                if i in ['COA Comdty', 'CLA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty', 'NGA Comdty',
                         'NGVF Comdty',
                         'GCA Comdty', 'SIA Comdty', 'PLA Comdty', 'PAA Comdty', 'BTCA Curncy', 'HGA Comdty',
                         'C A Comdty', 'S A Comdty', 'SMA Comdty', 'BOA Comdty', 'W A Comdty', 'KWA Comdty',
                         'KCA Comdty', 'CTA Comdty', 'ESA Index', 'NQA Index', 'NHA Index', 'TYA Comdty',
                         'EAA Curncy', 'BPA Curncy', 'ADA Curncy', 'JYA Curncy', 'CDA Curncy',
                         'S:COCO 1-2 Comdty', 'S:COCO 2-3 Comdty', 'S:COCO 3-4 Comdty', 'S:COCO Jun-Dec Comdty',
                         'S:COCO Dec-Dec Comdty',
                         'S:CLCL 1-2 Comdty', 'S:CLCL 2-3 Comdty', 'S:CLCL 3-4 Comdty', 'S:CLCL Jun-Dec Comdty',
                         'S:CLCL Dec-Dec Comdty',
                         'S:XBXB 1-2 Comdty', 'S:HOHO 1-2 Comdty', 'S:NGNG 1-2 Comdty',
                         'S:QSQS 1-2 Comdty', 'S:QSQS 2-3 Comdty', 'S:QSQS 3-4 Comdty', 'S:QSQS Jun-Dec Comdty',
                         'S:QSQS Dec-Dec Comdty',
                         'S:COCO Dec2-Dec3 Comdty', 'S:CLCL Dec2-Dec3 Comdty', 'S:QSQS Dec2-Dec3 Comdty']:
                    raise NotImplementedError("Photo gap: active-hours filtering, source 357-359")
                    vol_mean = volume_by_minute_active['volume'].iloc[-1440:-1].mean()
                    close_mean = volume_by_minute_active['close'].iloc[-1440:-1].mean()
                else:
                    vol_mean = volume_by_minute['volume'].iloc[-2640:-1].mean()
                    close_mean = volume_by_minute['close'].iloc[-2640:-1].mean()
            else:
                vol_mean = volume_by_minute['volume'].mean()
                close_mean = volume_by_minute['close'].mean()
            zscore = (volume_at_minute.volume[-1] - volume_at_minute.volume[-21:-1].mean()) / volume_at_minute.volume[-21:-1].std()
            zscore1 = volume_at_minute.volume[-1] / vol_mean
            if not alert_vwap_data.empty:
                zscore_vwap = volume_at_minute.close[-1] - alert_vwap_data.mean()[-1]
            else:
                zscore_vwap = 0
            if ((zscore > 2.5 and zscore1 > 8) or (zscore > 4 and zscore1 > 6)) and volume_at_minute.index[
                -1] + dt.timedelta(minutes=30) > dt.datetime.utcnow():
                chart_data = intraday_price.iloc[-300:, :]
                fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True,
                                    vertical_spacing=0.02)
                fig.add_trace(go.Candlestick(x=chart_data.index,
                                             open=chart_data['open'],
                                             high=chart_data['high'],
                                             low=chart_data['low'],
                                             close=chart_data['close']))
                if not alert_vwap_data.empty:
                    fig.add_trace(go.Scatter(
                        name=f'Mean VWAP from {sdate_vwap} -> {edate_vwap}',
                        x=[chart_data.index.min(), chart_data.index.max()],
                        y=[alert_vwap_data.mean()[-1], alert_vwap_data.mean()[-1]],
                        mode="lines",
                        marker=dict(color='rgba(80, 26, 80, 0.8)')
                    ), row=1, col=1)
                fig.add_trace(
                    go.Bar(x=chart_data.index, y=chart_data['volume'], showlegend=True, name='volume'), row=2,
                    col=1)
                fig.update_layout(title={'text': ticker, 'x': 0.5, 'xanchor': 'center'},
                                  width=1500, height=600,
                                  xaxis_rangeslider_visible=False)
                fig.update_xaxes(
                    rangebreaks=[
                        dict(bounds=["sat", "mon"]),  # hide weekends
                        {'pattern': 'hour', 'bounds': active_time}
                    ])
                log.info(f"Alerting on {ticker}")
                table.figures_to_html([fig], filename=f"{html_path}\\cross_cmds\\links\\{ticker}.html")
                if ac == 'OIL':
                    alert_dict_oil[ticker] = [volume_at_minute.index[-1], volume_at_minute.volume[-1],
                                                intraday_price['close'].diff()[-1], zscore, zscore1, zscore_vwap]
                elif ac == 'GAS':
                    alert_dict_gas[ticker] = [volume_at_minute.index[-1], volume_at_minute.volume[-1],
                                                intraday_price['close'].diff()[-1], zscore, zscore1, zscore_vwap]
                elif ac == 'PM':
                    alert_dict_pm[ticker] = [volume_at_minute.index[-1], volume_at_minute.volume[-1],
                                                intraday_price['close'].diff()[-1], zscore, zscore1, zscore_vwap]
                elif ac == 'BM':
                    alert_dict_bm[ticker] = [volume_at_minute.index[-1], volume_at_minute.volume[-1],
                                                intraday_price['close'].diff()[-1], zscore, zscore1, zscore_vwap]
                else:
                    alert_dict_macro[ticker] = [volume_at_minute.index[-1], volume_at_minute.volume[-1],
                                                intraday_price['close'].diff()[-1], zscore, zscore1, zscore_vwap]
    return alert_dict_oil, alert_dict_gas, alert_dict_pm, alert_dict_bm, alert_dict_macro


def update(edate=None):
    """Run intraday volume alert processing.

    Now sources tickers from intraday_vol.get_ticker_dict so DB backed
    configuration / hours overrides can be honored. Falls back to
    local ins_dict if upstream returns empty.
    """
    alert_dict_oil = {}
    alert_dict_gas = {}
    alert_dict_pm = {}
    alert_dict_bm = {}
    alert_dict_macro = {}
    vwap_track_date_range = get_fom_info()
    try:
        ticker_runtime_dict = intraday_vol_get_ticker_dict(ins_dict, force_update=False)
    except Exception as exc:  # noqa: BLE001
        log.warning(f"Failed to load intraday vol runtime ticker dict from module; using local ins_dict. Error: {exc}")
        ticker_runtime_dict = {}
    if not ticker_runtime_dict:
        log.info("Using fallback mode: resolving tickers from local ins_dict")
        args = []
        for i, val in ins_dict.items():
            try:
                if i in ['LMCADS03 Comdty', 'LMAHDS03 Comdty', 'LMZSDS03 Comdty', 'LMNIDS03 Comdty']:
                    ticker = i
                    last_ticker = None
                    roll_date = None
                    log.debug(f"[{i}] Static ticker (LME): {ticker}")
                else:
                    ticker, last_ticker, roll_date = get_ticker(i)
                    log.debug(f"[{i}] Resolved: active={ticker}, last={last_ticker}, roll={roll_date}")
                args.append((i, val, ticker, last_ticker, roll_date, vwap_track_date_range, edate))
            except Exception as e:
                log.error(f"[{i}] Failed to resolve ticker: {e}", exc_info=True)
                continue
        log.info(f"Fallback mode: prepared {len(args)} tickers for processing")
    else:
        log.info(f"Using DB-backed ticker dict with {len(ticker_runtime_dict)} tickers")
        args = []
        for (asset_class, generic_ticker), data in ticker_runtime_dict.items():
            active_contract = data.get("active_contract")
            last_contract = data.get("last_contract")
            roll_date_val = data.get("roll_date")
            hours = data.get("hours", [22, 23])
            if active_contract is None:
                log.error(f"[{generic_ticker}] active_contract is None in ticker_runtime_dict! Data: {data}")
                continue
            args.append((generic_ticker, [asset_class, hours], active_contract, last_contract, roll_date_val, vwap_track_date_range, edate))
        log.info(f"DB mode: prepared {len(args)} tickers for processing")
    if not args:
        log.error("No tickers to process! Check ticker resolution logic.")
        return
    log.info(f"Starting multiprocessing pool with {len(args)} tasks...")
    with Pool(10) as pool:
        results = pool.starmap(process_alerts, args)
    log.info(f"Pool completed. Processing {len(results)} results...")
    for (alert_oil, alert_gas, alert_pm, alert_bm, alert_macro) in results:
        alert_dict_oil.update(alert_oil)
        alert_dict_gas.update(alert_gas)
        alert_dict_pm.update(alert_pm)
        alert_dict_bm.update(alert_bm)
        alert_dict_macro.update(alert_macro)
    log.info(f"Alert summary: OIL={len(alert_dict_oil)}, GAS={len(alert_dict_gas)}, "
             f"PM={len(alert_dict_pm)}, BM={len(alert_dict_bm)}, MACRO={len(alert_dict_macro)}")
    if alert_dict_oil:
        log.info(f"Sending OIL alerts for: {list(alert_dict_oil.keys())}")
        send_alert_email(alert_dict_oil, "OIL", vwap_track_date_range)
    if alert_dict_gas:
        log.info(f"Sending GAS alerts for: {list(alert_dict_gas.keys())}")
        send_alert_email(alert_dict_gas, "GAS", vwap_track_date_range)
    if alert_dict_macro:
        log.info(f"Sending MACRO alerts for: {list(alert_dict_macro.keys())}")
        send_alert_email(alert_dict_macro, "Macro", vwap_track_date_range)
    if alert_dict_bm:
        log.info(f"Sending BM alerts for: {list(alert_dict_bm.keys())}")
        send_alert_email(alert_dict_bm, "Base Metal", vwap_track_date_range)
    if alert_dict_pm:
        log.info(f"Sending PM alerts for: {list(alert_dict_pm.keys())}")
        send_alert_email(alert_dict_pm, "Precious Metal", vwap_track_date_range)
    if not any([alert_dict_oil, alert_dict_gas, alert_dict_pm, alert_dict_bm, alert_dict_macro]):
        log.info("No alerts triggered for any asset class.")
    log.info("Update complete.")


if __name__ == "__main__":
    update()
