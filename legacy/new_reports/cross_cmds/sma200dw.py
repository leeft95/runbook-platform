import pandas as pd
import numpy as np
import datetime as dt
import time
import sys
import os
import ecm.cmds.table as table
import ecm.cmds.bbg as bbg
import ecm.cmds.time_series as ts
from ecm.cmds.config import root_path, output_path
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux

send_to = ["rzhao@elementcapital.com"]
report_name = "Commodity 200D 200W"
file_name = "sma200dw"  # without .py
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
        start_datetime=dt.datetime(2023, 7, 1, 17, 0),
        timezone="Europe/London",
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
    'AGS': ['C 1 Comdty', 'C 5 Comdty', 'S 1 Comdty', 'S 5 Comdty', 'W 1 Comdty', 'W 5 Comdty']
}


def get_summary():
    idx = []
    for key, val in ticker_dict.items():
        idx += val
    res_df = pd.DataFrame(np.nan, index=idx,
                          columns=['Category', 'PX_LAST', '200D', '200W', 'Delta on 200D', 'Delta on 200W',
                                   '200D_Cross', '200W_Cross'])
    res_df.index.name = 'Name'
    edate = today()
    for key, val in ticker_dict.items():
        for ticker in val:
            print(ticker)
            if os.path.exists(folder_path + '{:s}.csv'.format(ticker)):
                daily_price_history = ts.read_csv(folder_path + '{:s}.csv'.format(ticker), index_name='date')
                sdate = daily_price_history.index[-2]
                daily_price_new = bbg.bdh(ticker, ['PX_LAST'], sdate, edate)
                daily_price = pd.concat([daily_price_history.iloc[:-2, :], daily_price_new], axis=0)
            else:
                sdate = today() - dt.timedelta(days=364)
                daily_price = bbg.bdh(ticker, ['PX_LAST'], sdate, edate)
            daily_price.to_csv(convert_path_to_linux(f"{folder_path}{ticker}.csv"))
            mv_200d = daily_price.rolling(200).mean()
            res_df.loc[ticker, 'PX_LAST'] = daily_price['PX_LAST'].iloc[-1]
            res_df.loc[ticker, '200D'] = mv_200d['PX_LAST'].iloc[-1]
            res_df.loc[ticker, 'Delta on 200D'] = (daily_price['PX_LAST'].iloc[-1] - mv_200d['PX_LAST'].iloc[-1]) / \
                                                mv_200d['PX_LAST'].iloc[-1]
            raise NotImplementedError("Missing daily-cross comparisons: IMG_5428 lines 86/90")

            if os.path.exists(folder_path + '{:s}_w.csv'.format(ticker)):
                weekly_price_history = ts.read_csv(folder_path + '{:s}_w.csv'.format(ticker), index_name='date')
                sdate = weekly_price_history.index[-2]
                weekly_price_new = bbg.bdh(ticker, ['PX_LAST'], sdate, edate, elms=[('periodicitySelection', 'WEEKLY')])
                weekly_price = pd.concat([weekly_price_history.iloc[:-2, :], weekly_price_new], axis=0)
            else:
                sdate = today() - dt.timedelta(days=364 * 5)
                weekly_price = bbg.bdh(ticker, ['PX_LAST'], sdate, edate, elms=[('periodicitySelection', 'WEEKLY')])
            weekly_price.to_csv(convert_path_to_linux(f"{folder_path}{ticker}_w.csv"))
            mv_200w = weekly_price.rolling(200).mean()
            res_df.loc[ticker, '200W'] = mv_200w['PX_LAST'].iloc[-1]
            res_df.loc[ticker, 'Delta on 200W'] = (weekly_price['PX_LAST'].iloc[-1] - mv_200w['PX_LAST'].iloc[-1]) / \
                                                mv_200w['PX_LAST'].iloc[-1]
            raise NotImplementedError("Missing weekly-cross comparisons: IMG_5428 lines 111/115")
            res_df.loc[ticker, 'Category'] = key
    raise NotImplementedError("Incomplete ticker lists: IMG_5427 lines 48-52")
    res_df.to_csv(convert_path_to_linux(f"{cc_csv_folder}\\Commodity_200D_200W.csv"))
    return res_df


def update(send_to):
    res_df_all = get_summary()
    res_df_all.index.name = 'Name'
    res_df = res_df_all.loc[(res_df_all['200D_Cross'] != 0) | (res_df_all['200W_Cross'] != 0), :]
    if len(res_df) > 0:
        res_df.reset_index(inplace=True)
        res_html = table.html_format(
            df=res_df,
            precision=3,
            hide_cols=['200D_Cross', '200W_Cross'],
            format_column={'Name': {'width': '120px', 'text-align': 'left'},
                           'Category': {'width': '80px', 'text-align': 'center'},
                           'PX_LAST': {'width': '100px', 'text-align': 'center'},
                           '200D': {'width': '100px', 'text-align': 'center'},
                           '200W': {'width': '100px', 'text-align': 'center'},
                           'Delta on 200D': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                           'Delta on 200W': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}
                           },
        )
        res_df_all.reset_index(inplace=True)
        res_all_html = table.html_format(
            df=res_df_all,
            precision=3,
            hide_cols=['200D_Cross', '200W_Cross'],
            format_column={'Name': {'width': '120px', 'text-align': 'left'},
                           'Category': {'width': '80px', 'text-align': 'center'},
                           'PX_LAST': {'width': '100px', 'text-align': 'center'},
                           '200D': {'width': '100px', 'text-align': 'center'},
                           '200W': {'width': '100px', 'text-align': 'center'},
                           'Delta on 200D': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                           'Delta on 200W': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}
                           },
            format_row={(11, 21, 27, 31): {'bottom_border': True}}
        )
        if send_to is not None:
            if sys.platform.startswith("linux"):
                raise NotImplementedError("Missing email-link path conversion: IMG_5429 line 163")
            else:
                excel_link = cc_csv_folder
            send_email(send_to=send_to, subject='Commodity 200D 200W',
                       body=[res_html, res_all_html,
                             u'<a href="{}\\Commodity_200D_200W.csv">Excel</a>'.format(excel_link),
                             '<br><br>This is automated email sent at {:s}. <br><br>'.format(
                                 time.strftime('%Y-%m-%d %H:%M'))])
        return res_html
    else:
        return 0


if __name__ == '__main__':
    update(send_to=send_to)
