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
from ecm.cmds.cdr import today, datetime_range
from ecm.cmds.utils import convert_path_to_linux

send_to = ['rzhao@elementcapital.com', 'ltrindade@elementcapital.com']
report_name = "MA crossing alert"
file_name = "intraday_cross_ma"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"

cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"
folder_path = f"{cc_csv_folder}\\200\\"


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
        start_datetime=dt.datetime(2023, 7, 1, 1, 4),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=10),
        repetition_duration=dt.timedelta(hours=20),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


ticker_dict = {
    'Macro': ['SPX Index', 'SX5E Index', 'SHSZ300 Index', 'MSZZCYDE Index', 'BCOM Index',
              'USGG10YR Index', 'USYC2Y5Y Index', 'DXY Curncy', 'EURUSD Curncy', 'AUDUSD Curncy'],
    'NRG': ['CO1 Comdty', 'CO12 Comdty', 'CO24 Comdty', 'NG1 Comdty', 'NG12 Comdty', 'NG24 Comdty',
            'TZT1 Comdty', 'TZT12 Comdty', 'TZT24 Comdty', 'XOP US Equity'],
    'MTL': ['LMCADS03 Comdty', 'LMAHDS03 Comdty', 'LMNIDS03 Comdty', 'LMZSDS03 Comdty', 'SXPP Index',
            'XME US Equity'],
    'PM': ['XAUUSD Curncy', 'XAGUSD Curncy', 'GDX US Equity', 'GDXJ US Equity'],
    'AGS': ['C 1 Comdty', 'C 5 Comdty', 'S 1 Comdty', 'S 5 Comdty', 'W 1 Comdty', 'W 5 Comdty'],
    'CMD Index': ['BCOM Index', 'BCOMEN Index', 'BCOMIN Index', 'BCOMAG Index'],
}


def get_price(ticker, edate, weekly=False):
    elms = [('periodicitySelection', 'WEEKLY')] if weekly else None
    file_name = '{:s}_w.csv'.format(ticker) if weekly else '{:s}.csv'.format(ticker)
    if os.path.exists(convert_path_to_linux(folder_path + file_name)):
        price_history = ts.read_csv(folder_path + file_name, index_name='date')
        sdate = price_history.index[-2]
        price_new = bbg.bdh(ticker, ['PX_LAST'], sdate, edate, elms=elms)
        if isinstance(price_new.columns, pd.MultiIndex):
            price_new = price_new[ticker]
        price = pd.concat([price_history.iloc[:-2, :], price_new], axis=0)
    else:
        sdate = today() - (dt.timedelta(days=364) if not weekly else dt.timedelta(days=364 * 5))
        price = bbg.bdh(ticker, ['PX_LAST'], sdate, edate, elms=elms)
        if isinstance(price.columns, pd.MultiIndex):
            price = price[ticker]
    return price


def alert_200dw(send_to):
    idx = []
    raise NotImplementedError("Incomplete configured ticker lists: IMG_5210 lines 52-56")
    for key, val in ticker_dict.items():
        idx += val
    res_df = pd.DataFrame(np.nan, index=idx, columns=['PX_LAST', '200D', '200W', '200D_Cross', '200W_Cross'])
    res_df.index.name = 'Name'
    edate = today()
    body = []

    if os.path.exists(convert_path_to_linux(f"{cc_csv_folder}\\intraday_200dw\\intraday_200dw_{today().strftime('%Y-%m-%d')}.csv")):
        exist_res_df = pd.read_csv(convert_path_to_linux(f"{cc_csv_folder}\\intraday_200dw\\intraday_200dw_{today().strftime('%Y-%m-%d')}.csv"))

        if len(exist_res_df) > 0:
            cross_up_d = list(exist_res_df.loc[exist_res_df['200D_Cross'] == 1, 'Name'].values)
            cross_down_d = list(exist_res_df.loc[exist_res_df['200D_Cross'] == -1, 'Name'].values)
            cross_up_w = list(exist_res_df.loc[exist_res_df['200W_Cross'] == 1, 'Name'].values)
            cross_down_w = list(exist_res_df.loc[exist_res_df['200W_Cross'] == -1, 'Name'].values)
            exist_res_df.set_index('Name', inplace=True)
        else:
            cross_up_d = []
            cross_down_d = []
            cross_up_w = []
            cross_down_w = []
            exist_res_df = pd.DataFrame()
    else:
        cross_up_d = []
        cross_down_d = []
        cross_up_w = []
        cross_down_w = []
        exist_res_df = pd.DataFrame()

    for key, val in ticker_dict.items():
        print(f"Processing 200dw {key}")
        for ticker in val:
            daily_price = get_price(ticker, edate)
            mv_200d = daily_price.rolling(200).mean()

            weekly_price = get_price(ticker, edate, weekly=True)
            mv_200w = weekly_price.rolling(200).mean()

            if (daily_price['PX_LAST'].iloc[-1] > mv_200d['PX_LAST'].iloc[-1] and
                    daily_price['PX_LAST'].iloc[-2] < mv_200d['PX_LAST'].iloc[-2] and
                    ticker not in cross_up_d):
                res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200D'] = mv_200d['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200W'] = mv_200w['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200D_Cross'] = 1
                body.append(f'{ticker} crossed up 200D MA <br>')
            elif (daily_price['PX_LAST'].iloc[-1] < mv_200d['PX_LAST'].iloc[-1] and
                    daily_price['PX_LAST'].iloc[-2] > mv_200d['PX_LAST'].iloc[-2] and
                    ticker not in cross_down_d):
                res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200D'] = mv_200d['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200W'] = mv_200w['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200D_Cross'] = -1
                body.append(f'{ticker} crossed down 200D MA <br>')
            else:
                res_df.loc[ticker, '200D_Cross'] = 0

            if (weekly_price['PX_LAST'].iloc[-1] > mv_200w['PX_LAST'].iloc[-1] and
                    weekly_price['PX_LAST'].iloc[-2] < mv_200w['PX_LAST'].iloc[-2] and
                    ticker not in cross_up_w):
                res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200D'] = mv_200d['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200W'] = mv_200w['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200W_Cross'] = 1
                body.append(f'{ticker} crossed up 200W MA <br>')
            elif (weekly_price['PX_LAST'].iloc[-1] < mv_200w['PX_LAST'].iloc[-1] and
                    weekly_price['PX_LAST'].iloc[-2] > mv_200w['PX_LAST'].iloc[-2] and
                    ticker not in cross_down_w):
                res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200D'] = mv_200d['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200W'] = mv_200w['PX_LAST'].iloc[-1]
                res_df.loc[ticker, '200W_Cross'] = -1
                body.append(f'{ticker} crossed down 200W MA <br>')
            else:
                res_df.loc[ticker, '200W_Cross'] = 0

    res_df.dropna(inplace=True)
    if len(res_df) > 0:
        res_df.index.name = 'Name'
        res_df = pd.concat([exist_res_df, res_df], axis=0)
        res_df.index.name = 'Name'
        res_df.to_csv(convert_path_to_linux(f"{cc_csv_folder}\\intraday_200dw\\intraday_200dw_{today().strftime('%Y-%m-%d')}.csv"))
        if send_to is not None:
            send_email(send_to=send_to, subject='200D/W MA alert', send_from='cmdalrt', body=body)


def alert_100dw(send_to):
    idx = []
    for key, val in ticker_dict.items():
        if key in ['CMD Index']:
            idx += val
    res_df = pd.DataFrame(np.nan, index=idx, columns=['PX_LAST', '100D', '100W', '100D_Cross', '100W_Cross'])
    res_df.index.name = 'Name'
    edate = today()
    body = []

    if os.path.exists(convert_path_to_linux(f"{cc_csv_folder}\\intraday_200dw\\intraday_100dw_{today().strftime('%Y-%m-%d')}.csv")):
        exist_res_df = pd.read_csv(convert_path_to_linux(f"{cc_csv_folder}\\intraday_200dw\\intraday_100dw_{today().strftime('%Y-%m-%d')}.csv"))

        if len(exist_res_df) > 0:
            cross_up_d = list(exist_res_df.loc[exist_res_df['100D_Cross'] == 1, 'Name'].values)
            cross_down_d = list(exist_res_df.loc[exist_res_df['100D_Cross'] == -1, 'Name'].values)
            cross_up_w = list(exist_res_df.loc[exist_res_df['100W_Cross'] == 1, 'Name'].values)
            cross_down_w = list(exist_res_df.loc[exist_res_df['100W_Cross'] == -1, 'Name'].values)
            exist_res_df.set_index('Name', inplace=True)
        else:
            cross_up_d = []
            cross_down_d = []
            cross_up_w = []
            cross_down_w = []
            exist_res_df = pd.DataFrame()
    else:
        cross_up_d = []
        cross_down_d = []
        cross_up_w = []
        cross_down_w = []
        exist_res_df = pd.DataFrame()

    for key, val in ticker_dict.items():
        print(f"Processing 100dw {key}")
        if key in ['CMD Index']:
            for ticker in val:
                daily_price = get_price(ticker, edate)
                mv_100d = daily_price.rolling(100).mean()

                weekly_price = get_price(ticker, edate, weekly=True)
                mv_100w = weekly_price.rolling(100).mean()

                if (daily_price['PX_LAST'].iloc[-1] > mv_100d['PX_LAST'].iloc[-1] and
                        daily_price['PX_LAST'].iloc[-2] < mv_100d['PX_LAST'].iloc[-2] and
                        ticker not in cross_up_d):
                    res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100D'] = mv_100d['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100W'] = mv_100w['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100D_Cross'] = 1
                    body.append(f'{ticker} crossed up 100D MA <br>')
                elif (daily_price['PX_LAST'].iloc[-1] < mv_100d['PX_LAST'].iloc[-1] and
                        daily_price['PX_LAST'].iloc[-2] > mv_100d['PX_LAST'].iloc[-2] and
                        ticker not in cross_down_d):
                    res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100D'] = mv_100d['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100W'] = mv_100w['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100D_Cross'] = -1
                    body.append(f'{ticker} crossed down 100D MA <br>')
                else:
                    res_df.loc[ticker, '100D_Cross'] = 0

                if (weekly_price['PX_LAST'].iloc[-1] > mv_100w['PX_LAST'].iloc[-1] and
                        weekly_price['PX_LAST'].iloc[-2] < mv_100w['PX_LAST'].iloc[-2] and
                        ticker not in cross_up_w):
                    res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '200D'] = mv_100d['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '200W'] = mv_100w['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '200W_Cross'] = 1
                    body.append(f'{ticker} crossed up 100W MA <br>')
                elif (weekly_price['PX_LAST'].iloc[-1] < mv_100w['PX_LAST'].iloc[-1] and
                        weekly_price['PX_LAST'].iloc[-2] > mv_100w['PX_LAST'].iloc[-2] and
                        ticker not in cross_down_w):
                    res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100D'] = mv_100d['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100W'] = mv_100w['PX_LAST'].iloc[-1]
                    res_df.loc[ticker, '100W_Cross'] = -1
                    body.append(f'{ticker} crossed down 100W MA <br>')
                else:
                    res_df.loc[ticker, '100W_Cross'] = 0

    res_df.dropna(inplace=True)
    if len(res_df) > 0:
        res_df.index.name = 'Name'
        res_df = pd.concat([exist_res_df, res_df], axis=0)
        res_df.index.name = 'Name'
        res_df.to_csv(convert_path_to_linux(f"{cc_csv_folder}\\intraday_200dw\\intraday_100dw_{today().strftime('%Y-%m-%d')}.csv"))
        if send_to is not None:
            send_email(send_to=send_to, subject='100D/W MA alert', send_from='cmdalrt', body=body)


def update():
    alert_200dw(send_to=send_to)
    alert_100dw(send_to=send_to)


if __name__ == "__main__":
    update()
