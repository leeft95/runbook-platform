import pandas as pd
import numpy as np
import datetime as dt
import time
import sys
from ecm.cmds.config import root_path, html_path, oil_group, macro_group, url

sys.path.append(f"{root_path}\\autoreports\\reports\\cross_cmds")
import sma200dw
from pandas.tseries.offsets import BDay
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.talib as talib
import ecm.cmds.ticker as tk
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today, getworkingdays, CDR
import ecm.cmds.time_series as ts
import ecm.cmds.ticker as ticker

send_to_gas = ["jmcphillips@elementcapital.com", "rzhao@elementcapital.com", "caitcheson@elementcapital.com"]  # source line 22: clipped list tail
send_to = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "Oil futures price range"
file_name = "oil_price_range"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"


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
        start_datetime=dt.datetime(2023, 7, 1, 6, 10),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


ins_dict = {
    "EU Crude": ['COA Comdty', "Crd-P-EU", "Forties", "Eko", "WTI FOB", "Johan", "CPC", "Azeri", "Saharan"],  # line 53 clipped continuation
    "US Crude": ['CLA Comdty', "Crd-P-US", "WTI Cash", "Midland", "MEH", "Bakken", "SaddleHorn", "WCS Cush"],  # line 54 clipped continuation
    "Asia Crude": ['DATA Comdty', "Crd-P-A", "Oman", "Alshaheen", "Upper Zakum", "Murban", "Tupi", "WTI SG"],
    "EU Gasoil": ['QSA Comdty', "GO-P-EU", "10ppm FOB ARA", "10ppm CIF NWE", "10ppm CIF Med", "50ppm"],  # line 56 next label begins 0.1
    "US Gasoil": ['HOA Comdty', "GO-P-US", "USGC pipe", "NYH Barges", "Group3", "NYH Jet Diff"],
    "Asia Gasoil": ["GO-P-A", "Sing Premium", "Regrade", "MOPAG", "India"],
    "EU Gasoline": ["MOGAS-P-EU", "EBOB Cash", "E10", "Unlead Med Diff", "Nap Cash"],
    "US Gasoline": ["XBA Comdty", "MOGAS-P-US", "RBOB USGC pipe", "RBOB NYH Barges", "Prem Group3"],  # line 60 next label begins Colonia
    "Asia Gasoline": ["MOGAS-P-A", "Sing Gasoline", "Sing Nap", "Ron"],
}


def _photo_gap(source_line, visible_prefix):
    raise NotImplementedError(f"Unrecovered oil_price_range source line {source_line}: {visible_prefix}")


def synthetic_spread(active, y, m, far_y=None, far_m=None, sdate=None, edate=None, pct=False):
    """
    synthetic spread is calculated as front outright contact - far outright contract
    """
    if active in ['LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty']:
        fields = ['LAST_PRICE']
    else:
        fields = ['PX_LAST']
    if active == "DATA Comdty" and (int(y) < 2019 or (int(y) == 2019 and m in ["F", "G", "H"])):
        front = pyg.get_data("contracts_PX_LAST", active="TOA Comdty", y=y, m=m)
    else:
        front = pyg.get_data("contracts_PX_LAST", active=active, y=y, m=m)
    if active == "DATA Comdty" and (int(far_y) < 2019 or (int(far_y) == 2019 and far_m in ["F", "G", "H"])):
        far = pyg.get_data("contracts_PX_LAST", active="TOA Comdty", y=far_y, m=far_m)
    else:
        far = pyg.get_data("contracts_PX_LAST", active=active, y=far_y, m=far_m)
    if pct:
        spread = (front - far) / far
    else:
        spread = front - far
    spread.columns = ['PX_LAST']
    return spread.loc[sdate:edate, :]


def get_5y_outright_data(active='CLA Comdty', go=None):
    contracts = pyg.get_data("contracts", active=active, item="fut_chain")
    if active == "DATA Comdty":
        contracts1 = pyg.get_data("contracts", active="TOA Comdty", item="fut_chain")
        contracts = pd.concat([contracts1.loc[contracts1['last_t'] < dt.datetime(2019, 4, 25), :], contracts], axis=0)
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts['t1'] = contracts['t'].shift(1)
    live_contract = contracts.iloc[np.where(contracts['t'] > today())[0][0], :]
    same_month_contract = contracts.loc[_photo_gap(99, "(contracts['m'] == live_contract['m']) & (contracts['y'] <= live_con")]
    data = pd.DataFrame()
    for idx, row in same_month_contract.iterrows():
        price = pyg.get_data("contracts_PX_LAST", active=tk.as_active(row['ticker']), m=row['m'], y=row['y'])
        if row['ticker'] == live_contract['ticker']:
            live_price = bbg.bdh(row['ticker'], ['PX_LAST'], sdate=price.index[-1], edate=today() + BDay(1))
            price = pd.concat([price.iloc[:-1, :], live_price], axis=0)
        price = price.loc[row['t1'] - dt.timedelta(days=14):row['last_t'], 'PX_LAST']
        data[row['ticker']] = price.reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract['t1'] - dt.timedelta(days=14), t1=_photo_gap(111, 'live_contract'))
    trade_dates = pd.DatetimeIndex(trade_dates)
    trade_dates = price.index.union(trade_dates[np.where(trade_dates > price.index[-1])])
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    try:
        data['dates'] = trade_dates
    except:
        print('stop')
    data.set_index('dates', inplace=True)
    return data, live_contract['ticker']


def get_5y_spread_data(active='CLA Comdty', spread=1, go=None):
    contracts_ = pyg.get_data("spreads", active=active, item="sprd_chain")
    contracts = contracts_.copy()
    if active == "DATA Comdty":
        contracts1 = pyg.get_data("contracts", active="TOA Comdty", item="fut_chain")
        contracts1['far_y'] = contracts1['y'].shift(-1)
        contracts1['far_m'] = contracts1['m'].shift(-1)
        contracts1.loc[contracts1.index[:-1], 'ticker'] = [
            f"S:DATDAT {x['m']}{str(x['y'])[-2:]}-{x['far_m']}{str(int(float(x['far_y'])))[-2:]} Comdty"
            for i, x in contracts1.iterrows() if i < len(contracts1) - 1]
        contracts = pd.concat([contracts1.loc[contracts1['last_t'] < dt.datetime(2019, 4, 25), :], contracts], axis=0)
        contracts['last_t'] = contracts['last_t'].shift(1)
        contracts['t1'] = contracts['t1'].shift(1)
        contracts['t3'] = contracts['t3'].shift(1)
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts['t1'] = contracts['t'].shift(1)
    contracts.reset_index(inplace=True, drop=True)
    if isinstance(spread, int) and spread > 1:
        contracts['t'] = contracts['t'].shift(spread - 1)
        contracts['t1'] = contracts['t1'].shift(spread - 1)
    elif spread == '2-6':
        contracts['far_y'] = contracts['far_y'].fillna(0).astype(str)
        contracts['t'] = contracts['t'].shift(1)
        contracts['t1'] = contracts['t1'].shift(1)
        contracts['far_m'] = contracts['far_m'].shift(-3)
        contracts['far_y'] = contracts['far_y'].shift(-3)
        contracts = contracts.loc[~contracts['far_m'].isna()]
        contracts['ticker'] = [
            f"{x['ticker'].split(' ')[0]} {x['m']}{str(x['y'])[-2:]}-{x['far_m']}{str(int(float(x['far_y'])))[-2:]} Comdty"
            for i, x in contracts.iterrows()]
    elif spread == '2-4':
        contracts['far_y'] = contracts['far_y'].fillna(0).astype(str)
        contracts['t'] = contracts['t'].shift(1)
        contracts['t1'] = contracts['t1'].shift(1)
        contracts['far_m'] = contracts['far_m'].shift(-1)
        contracts['far_y'] = contracts['far_y'].shift(-1)
        contracts = contracts.loc[~contracts['far_m'].isna()]
        contracts['ticker'] = [
            f"{x['ticker'].split(' ')[0]} {x['m']}{str(x['y'])[-2:]}-{x['far_m']}{str(int(float(x['far_y'])))[-2:]} Comdty"
            for i, x in contracts.iterrows()]
    live_contract = contracts.iloc[np.where(contracts['t'] >= today())[0][0], :]
    same_month_contract = contracts.loc[_photo_gap(171, "(contracts['m'] == live_contract['m']) & (contracts['y'] <= live_con")]
    data = pd.DataFrame()
    for idx, row in same_month_contract.iterrows():
        if active == 'TZTA Comdty' or spread in ['2-6', '2-4']:
            price = synthetic_spread(active=active, m=row['m'], y=int(row['y']), far_m=row['far_m'],
                                     far_y=int(float(row['far_y'])))
            if active == 'TZTA Comdty' and row['y'] >= today().year:
                ticker = f"{active[:3]}{row['m']}{str(row['y'])[-1]}{row['far_m']}{str(int(float(row['far_y'])))[-1]} Comdty"
                print(ticker)
                price = bbg.bdh(ticker, ['PX_LAST'], sdate=price.index[0], edate=price.index[-1])
        else:
            try:
                price = pyg.get_data("spreads_PX_LAST", active=active, m=row['m'], y=row['y'], far_m=row['far_m'],
                                     far_y=row['far_y'])
            except:
                price = synthetic_spread(active=active, m=row['m'], y=int(row['y']), far_m=row['far_m'],
                                         far_y=int(float(row['far_y'])))
            price.columns = ['PX_LAST']
            if row['ticker'] == live_contract['ticker']:
                live_price = bbg.bdh(row['ticker'], ['PX_LAST'], sdate=price.index[-1], edate=today() + BDay(1))
                price = pd.concat([price.iloc[:-1, :], live_price], axis=0)
        price = price.loc[row['t1'] - dt.timedelta(days=14):row['last_t'], 'PX_LAST']
        data[row['ticker']] = price.reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract['t1'] - dt.timedelta(days=14), t1=_photo_gap(198, 'live_contract'))
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data['dates'] = trade_dates
    data.set_index('dates', inplace=True)
    return data, live_contract['ticker']


def get_5y_quarter_spread_data(active='CLA Comdty', spread=1, go=None):
    contracts = pyg.get_data("contracts", active=active, item="fut_chain")
    contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts = contracts.loc[contracts['m'].isin(['H', 'M', 'U', 'Z']), :]
    contracts['far_m'] = contracts['m'].shift(-1)
    contracts['far_y'] = contracts['y'].shift(-1)
    contracts['far_ticker'] = contracts['ticker'].shift(-1)
    contracts['t1'] = contracts['t'].shift(1)
    if isinstance(spread, int) and spread > 1:
        contracts['t'] = contracts['t'].shift(spread - 1)
        contracts['t1'] = contracts['t1'].shift(spread - 1)
    live_contract = contracts.iloc[np.where(contracts['t'] >= today())[0][0], :]
    same_month_contract = contracts.loc[_photo_gap(222, "(contracts['m'] == live_contract['m']) & (contracts['y'] <= live_con")]
    data = pd.DataFrame()
    same_month_contract.dropna(inplace=True)
    for idx, row in same_month_contract.iterrows():
        price = synthetic_spread(active=active, m=row['m'], y=int(row['y']), far_m=row['far_m'],
                                 far_y=int(row['far_y']))
        ticker = f"S:{active[:2]}{active[:2]} {row['m']}{str(row['y'])[-2:]}-{row['far_m']}{str(int(row['far_y']))[-2:]} Comdty"
        if row['y'] == today().year:
            print(ticker)
            price = bbg.bdh(ticker, ['PX_LAST'], sdate=price.index[0], edate=price.index[-1])
        price = price.loc[row['t1'] - dt.timedelta(days=14):row['last_t'], 'PX_LAST']
        data[ticker] = price.reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract['t1'] - dt.timedelta(days=14), t1=_photo_gap(237, 'live_contract'))
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data['dates'] = trade_dates
    data.set_index('dates', inplace=True)
    return data, (f"S:{active[:2]}{active[:2]} {live_contract['m']}{str(int(live_contract['y']))[-2:]}-"
                  f"{live_contract['far_m']}{str(int(live_contract['far_y']))[-2:]} Comdty")


def get_synthetic_spread(active='CLA Comdty', spread=1, go=None):
    if active in ['LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'CCA Comdty', 'KCA Comdty',
                  'CTA Comdty', 'LCA Comdty', 'FCA Comdty', 'LHA Comdty', 'GCA Comdty', 'SIA Comdty']:
        contracts = pyg.get_data("contracts", active=active, item="fut_chain")
        contracts.rename(columns={"t3": "t"}, inplace=True)
    else:
        contracts = pyg.get_data("spreads", active=active, item="sprd_chain")
        contracts.rename(columns={"t3": "t"}, inplace=True)
    contracts['t1'] = contracts['t'].shift(1)
    if isinstance(spread, int) and spread > 1:
        contracts['t'] = contracts['t'].shift(spread - 1)
        contracts['t1'] = contracts['t1'].shift(spread - 1)
    elif spread == "1-13":
        contracts['far_m'] = contracts['m']
        contracts['far_y'] = contracts['y'] + 1
    live_contract = contracts.iloc[np.where(contracts['t'] >= today())[0][0], :]
    same_month_contract = contracts.loc[_photo_gap(267, "(contracts['m'] == live_contract['m']) & (contracts['y'] <= live_con")]
    data = pd.DataFrame()
    for idx, row in same_month_contract.iterrows():
        price = synthetic_spread(active=active, m=row['m'], y=row['y'], far_m=row['far_m'], far_y=row['far_y'],
                                 pct=True)
        if row['y'] == today().year:
            if active in ['C A Comdty', 'S A Comdty', 'W A Comdty']:
                ticker = _photo_gap(275, "f\"{active[0]}_{row['m']}{str(row['y'])[-1]}{active[0]}_{row['far_m']}{str(row['far")
            else:
                ticker = _photo_gap(277, "f\"{active[:2]}{row['m']}{str(row['y'])[-1]}{active[:2]}{row['far_m']}{str(row['far")
            if active in ['NGA Comdty', 'LPA Comdty', 'LAA Comdty']:
                ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-2:]} Comdty"
                ticker1 = f"{active[:2]}{row['far_m']}{str(row['far_y'])[-2:]} Comdty"
            else:
                ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-1]} Comdty"
                ticker1 = f"{active[:2]}{row['far_m']}{str(row['far_y'])[-1]} Comdty"
            print(ticker)
            if active in ['LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty']:
                if active in ['LPA Comdty', 'LAA Comdty']:
                    ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-2:]} Comdty"
                else:
                    ticker0 = f"{active[:2]}{row['m']}{str(row['y'])[-1]} Comdty"
                if len(price) == 0 or price.index[-1] < today() - BDay(1):
                    sdate = today() - dt.timedelta(days=364)
                    edate = today()
                    price = bbg.bdh(ticker0, ['PX_LAST'], sdate=sdate, edate=edate)
                    price1 = bbg.bdh(ticker1, ['PX_LAST'], sdate=sdate, edate=edate)
                    price = (price - price1) / price
                else:
                    price = bbg.bdh(ticker0, ['PX_LAST'], sdate=price.index[0], edate=price.index[-1])
                    _photo_gap('298-299', 'two lines between refreshed ticker0 price and outer else are not photographed')
            else:
                if len(price) == 0 or price.index[-1] < today() - BDay(1):
                    sdate = today() - dt.timedelta(days=364)
                    edate = today()
                    price = bbg.bdh(ticker, ['PX_LAST'], sdate=sdate, edate=edate)
                    price0 = bbg.bdh(ticker0, ['PX_LAST'], sdate=sdate, edate=edate)
                    price = price / price0
                else:
                    price = bbg.bdh(ticker, ['PX_LAST'], sdate=price.index[0], edate=price.index[-1])
                    price0 = bbg.bdh(ticker0, ['PX_LAST'], sdate=price.index[0], edate=price.index[-1])
                    price = price / price0
        price = price.loc[row['t1'] - dt.timedelta(days=14):row['last_t'], 'PX_LAST']
        data[row['ticker']] = price.reset_index(drop=True)
    trade_dates = CDR(active=active).drange(t0=live_contract['t1'] - dt.timedelta(days=14), t1=_photo_gap(316, 'live_contract'))
    if len(trade_dates) < len(data):
        data = data.iloc[:len(trade_dates), :]
    elif len(trade_dates) > len(data):
        trade_dates = trade_dates[:len(data)]
    data['dates'] = trade_dates
    data.set_index('dates', inplace=True)
    return data, live_contract['ticker']


def create_table(data_, ticker, ex2020=False):
    data = data_.copy()
    if ex2020:
        for col in data.columns:
            if isinstance(col, int):
                if col == 2020 or col == 2022:
                    data.drop(col, axis=1, inplace=True)
            elif col.split(' ')[0][-2:] == '20' or col.split(' ')[0][-2:] == '22':
                data.drop(col, axis=1, inplace=True)
    cur_price = data.loc[data[ticker].last_valid_index(), ticker]
    cols = data.columns.drop(ticker)
    x = data.loc[data[ticker].last_valid_index(), cols].values
    if ticker == "Crd-P-EU":
        print("break")
    pct = (talib.percentilerank(x[~np.isnan(x)], cur_price) - 0.5) * 2
    avg = data.loc[data[ticker].last_valid_index(), cols].mean()
    max5 = data.loc[data[ticker].last_valid_index(), cols].max()
    min5 = data.loc[data[ticker].last_valid_index(), cols].min()
    se = data.loc[data[ticker].last_valid_index(), cols].std()
    zscore = (cur_price - avg) / se
    return [cur_price, pct, zscore, avg, max5, min5]


def create_chart(data, ticker, title):
    cols = data.columns.drop(ticker)
    avg = data[cols].mean(axis=1)
    data2 = data[ticker] - avg
    fig = chart.line_chart(
        df=data,
        title=title,
        data_p2y1=data2.to_frame('Current vs Avg'),
        subplots=[0.7, 0.3],
        highlight_dict={ticker: _photo_gap(359, "{'color':"),
                        'Current vs Avg': {'color': 'black', 'mode': 'lines'}}
    )
    return fig


def create_html_table(df_table, header):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            'Current price vs history': {'width': '120px', 'text-align': 'left'},
            'Current Price': {'width': '100px', 'text-align': 'center'},
            'Percentile of 5yr Range': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'bar': True},
            'Z-score of 5yr Range': {'width': '100px', 'text-align': 'center', 'format': '{:.2f}'},
            '5yr Avg Price': {'width': '100px', 'text-align': 'center'},
            '5yr Max': {'width': '100px', 'text-align': 'center'},
            '5yr Min': {'width': '100px', 'text-align': 'center'},
        },
        header=header,
    )


def create_html_table_1y(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            'Name': {'width': '120px', 'text-align': 'left'},
            'Carry yield': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
            'Percentile of 20yr Range': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'bar': True},
            'Z-score of 20yr Range': {'width': '100px', 'text-align': 'center', 'format': '{:.2f}'},
            '20yr Avg yield': {'width': '100px', 'text-align': 'center', 'format': '{:.2f}'},
            '20yr Max': {'width': '100px', 'text-align': 'center', 'format': '{:.2f}'},
            '20yr Min': {'width': '100px', 'text-align': 'center', 'format': '{:.2f}'},
        },
        format_row={(5, 9, 14, 18, 20, 22): {'bottom_border': True}},
    )


def create_html_table_gas(df_table):
    return table.html_format(
        df=df_table,
        precision=2,
        format_column={
            'Current price vs history': {'width': '120px', 'text-align': 'left'},
            'Current Price': {'width': '100px', 'text-align': 'center'},
            'Percentile of 10yr Range': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'bar': True},
            'Z-score of 10yr Range': {'width': '100px', 'text-align': 'center', 'format': '{:.2f}'},
            '10yr Avg Price': {'width': '100px', 'text-align': 'center'},
            '10yr Max': {'width': '100px', 'text-align': 'center'},
            '10yr Min': {'width': '100px', 'text-align': 'center'},
        },
        format_row={2: {'bottom_border': True}},
    )


def update(send_to, go=None):
    outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
    crude = ts.read_csv(f"{outputs_csv_oil}\\global_physical_crude_detail.csv", index_name='date')
    crude.drop(crude.columns[1], axis=1, inplace=True)
    gasoil = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoil_detail.csv", index_name="Unnamed: 0")
    gasoil.drop(gasoil.columns[1], axis=1, inplace=True)
    gasoline = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoline_detail.csv", index_name="date")
    gasoline.drop(gasoline.columns[1], axis=1, inplace=True)
    eu_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_eu.csv", index_name="date")
    us_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_us.csv", index_name="date")
    asia_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_asia.csv", index_name="date")
    eu_gasoil = ts.read_csv(f"{outputs_csv_oil}\\eu_physical_gasoil_detail.csv", index_name="date")
    us_gasoil = ts.read_csv(f"{outputs_csv_oil}\\us_physical_gasoil_detail.csv", index_name="date")
    asia_gasoil = ts.read_csv(f"{outputs_csv_oil}\\asia_physical_gasoil_detail.csv", index_name="Unnamed: 0")
    eu_gasoline = ts.read_csv(f"{outputs_csv_oil}\\eu_physical_gasoline_detail.csv", index_name="date")
    us_gasoline = ts.read_csv(f"{outputs_csv_oil}\\us_physical_gasoline_detail.csv", index_name="date")
    asia_gasoline = ts.read_csv(f"{outputs_csv_oil}\\asia_physical_gasoline_detail.csv", index_name="date")
    folder_path = f"{html_path}\\cross_cmds\\energy_spread\\"
    tbs = []
    tbs.append("<div style='font-family:Calibri;' >")
    tbs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    tbs_alert = []
    tbs_alert.append("<div style='font-family:Calibri;' >")
    tbs_alert.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    tbs_alert.append("Alert - 5y percentile < -0.9 or > 0.9")
    latest_date = 0
    dict_outright = {}
    dict_spread26 = {}
    _photo_gap('53/54/56/60', 'ins_dict has clipped physical instrument list tails')
    for k, v in ins_dict.items():
        print(k)
        figs = []
        alert_df = pd.DataFrame()
        alert_fig = []
        df_table = pd.DataFrame(columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
        for ins in v:
            if ins.rpartition(" ")[-1] == "Comdty":
                outright, outright_ticker = get_5y_outright_data(active=ins, go=go)
                spread1, spread1_ticker = get_5y_spread_data(active=ins, spread=1, go=go)
                spread2, spread2_ticker = get_5y_spread_data(active=ins, spread=2, go=go)
                if ins not in ["DATA Comdty"]:
                    spread_q1, spread_q1_ticker = get_5y_quarter_spread_data(active=ins, spread=1, go=None)
                    spread_q2, spread_q2_ticker = get_5y_quarter_spread_data(active=ins, spread=2, go=None)
                if ins == "DATA Comdty":
                    spread26, spread26_ticker = get_5y_spread_data(active=ins, spread='2-4', go=go)
                else:
                    spread26, spread26_ticker = get_5y_spread_data(active=ins, spread='2-6', go=go)
                if isinstance(latest_date, int):
                    latest_date = outright[outright_ticker].last_valid_index()
                if ins in ["DATA Comdty"]:
                    df = pd.DataFrame(0, index=[outright_ticker.rpartition(' ')[0], spread1_ticker.rpartition(' ')[0][-11:], spread2_ticker.rpartition(' ')[0][-11:]], columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
                    df.loc[outright_ticker.rpartition(' ')[0], :] = create_table(outright, outright_ticker, ex2020=True)
                    df.loc[spread1_ticker.rpartition(' ')[0][-11:], :] = create_table(spread1, spread1_ticker, ex2020=True)
                    df.loc[spread2_ticker.rpartition(' ')[0][-11:], :] = create_table(spread2, spread2_ticker, ex2020=True)
                    df.loc[spread26_ticker.rpartition(' ')[0][-11:], :] = create_table(spread26, spread26_ticker, ex2020=True)
                else:
                    df = pd.DataFrame(0, index=[outright_ticker.rpartition(' ')[0], spread1_ticker.rpartition(' ')[0][-10:], spread2_ticker.rpartition(' ')[0][-10:], spread_q1_ticker.rpartition(' ')[0][-10:], spread_q2_ticker.rpartition(' ')[0][-10:]], columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
                    df.loc[outright_ticker.rpartition(' ')[0], :] = create_table(outright, outright_ticker, ex2020=True)
                    df.loc[spread1_ticker.rpartition(' ')[0][-10:], :] = create_table(spread1, spread1_ticker, ex2020=True)
                    df.loc[spread2_ticker.rpartition(' ')[0][-10:], :] = create_table(spread2, spread2_ticker, ex2020=True)
                    df.loc[spread_q1_ticker.rpartition(' ')[0][-10:], :] = create_table(spread_q1, spread_q1_ticker, ex2020=True)
                    df.loc[spread_q2_ticker.rpartition(' ')[0][-10:], :] = create_table(spread_q2, spread_q2_ticker, ex2020=True)
                    df.loc[spread26_ticker.rpartition(' ')[0][-10:], :] = create_table(spread26, spread26_ticker, ex2020=True)
                df_table = pd.concat([df_table, df], axis=0)
                figs.append(create_chart(outright, outright_ticker, title=ins + '_Outright contract'))
                figs.append(create_chart(spread1, spread1_ticker, title=ins + '_1st spread'))
                figs.append(create_chart(spread2, spread2_ticker, title=ins + '_2nd spread'))
                if ins not in ["DATA Comdty"]:
                    figs.append(create_chart(spread_q1, spread_q1_ticker, title=ins + '_1st quarter spread'))
                    figs.append(create_chart(spread_q2, spread_q2_ticker, title=ins + '_2nd quarter spread'))
                figs.append(create_chart(spread26, spread26_ticker, title=ins + '_2-6 spread'))
                dict_outright[ins] = outright
                dict_spread26[ins] = spread26
                for _idx, row in df.iterrows():
                    if row["Percentile of 5yr Range"] < -0.9 or row["Percentile of 5yr Range"] > 0.9:
                        alert_df = pd.concat([alert_df, df.loc[[_idx], :]], axis=0)
                        alert_fig.append(figs[df.index.get_loc(_idx)])
            else:
                print(ins)
                try:
                    if k == 'EU Crude':
                        data = eu_crude[ins]
                    elif k == 'US Crude':
                        data = us_crude[ins]
                    elif k == 'Asia Crude':
                        data = asia_crude[ins]
                    elif k == 'EU Gasoil':
                        data = eu_gasoil[ins]
                    elif k == 'US Gasoil':
                        data = us_gasoil[ins]
                    elif k == 'Asia Gasoil':
                        data = asia_gasoil[ins]
                    elif k == 'EU Gasoline':
                        data = eu_gasoline[ins]
                    elif k == 'US Gasoline':
                        data = us_gasoline[ins]
                    elif k == 'Asia Gasoline':
                        data = asia_gasoline[ins]
                except KeyError:
                    print(f"{ins} not found in physical data")
                    continue
                data_by_year = ts.data_by_year(data, freq="B")
                data_by_year = data_by_year.loc[:, ~data_by_year.columns.isin([2020, 2022])].iloc[:, -6:]
                try:
                    df_table.loc[ins, :] = create_table(data_by_year, data_by_year.columns[-1], ex2020=True)
                except:
                    df_table.loc[ins, :] = np.nan
                figs.append(chart.seasonal_chart(data[data.index >= dt.datetime(2018, 1, 1)].to_frame(ins),
                                                 **_photo_gap(545, 'seasonal_chart arguments after data')))
                if df_table.loc[ins, "Percentile of 5yr Range"] < -0.9 or df_table.loc[ins, "Percentile of 5yr Range"] > 0.9:
                    alert_df = pd.concat([alert_df, df_table.loc[[ins], :]], axis=0)
                    alert_fig.append(chart.seasonal_chart(data[data.index >= dt.datetime(2018, 1, 1)].to_frame(ins),
                                                          **_photo_gap(549, 'seasonal_chart arguments after data')))
        df_table.index.name = 'Current price vs history'
        df_table.reset_index(inplace=True)
        df_html_table = create_html_table(df_table, k)
        figs.insert(0, df_html_table)
        table.figures_to_html(figs, filename=folder_path + k + "_charts.html")
        tbs.append(df_html_table)
        tbs.append(u'<a href="{}\\{}_charts.html">Charts</a><br>'.format(folder_path, k))
        if len(alert_df) > 0:
            alert_df.index.name = 'Current price vs history'
            alert_df.reset_index(inplace=True)
            alert_df_html = create_html_table(alert_df, k)
            alert_fig.insert(0, alert_df_html)
            table.figures_to_html(alert_fig, filename=folder_path + k + "_alerts.html")
            tbs_alert.append(alert_df_html)
            tbs_alert.append(u'<a href="{}\\{}_alerts.html">Charts</a><br>'.format(folder_path, k))

    def cal_blend(dict_outright, dict_spread26, w_dict):
        blend_outright = pd.DataFrame(0, index=dict_outright['COA Comdty'].index,
                                      columns=range(0, len(dict_outright['COA Comdty'].columns)))
        blend_spread = pd.DataFrame(0, index=dict_spread26['COA Comdty'].index,
                                    columns=range(0, len(dict_spread26['COA Comdty'].columns)))
        for ins in ['CLA Comdty', 'COA Comdty', 'DATA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty']:
            temp_df = dict_outright[ins].copy()
            temp_sprd = dict_spread26[ins].copy()
            temp_df.rename(columns={x: y for x, y in zip(temp_df.columns, range(0, len(temp_df.columns)))}, inplace=True)
            temp_sprd.rename(columns={x: y for x, y in zip(temp_sprd.columns, range(0, len(temp_sprd.columns)))},
                             inplace=True)
            if ins == 'HOA Comdty':
                blend_outright = blend_outright + temp_df * 0.42 * w_dict[ins]
                blend_spread = blend_spread + temp_sprd * 0.42 * w_dict[ins]
            elif ins == 'XBA Comdty':
                blend_outright = blend_outright + temp_df * 0.42 * w_dict[ins]
                blend_spread = blend_spread + temp_sprd * 0.42 * w_dict[ins]
            elif ins == 'QSA Comdty':
                blend_outright = blend_outright + temp_df / 7.45 * w_dict[ins]
                blend_spread = blend_spread + temp_sprd / 7.45 * w_dict[ins]
            elif ins == 'COA Comdty':
                blend_outright = blend_outright + temp_df * w_dict[ins]
                blend_spread = blend_spread + temp_sprd * w_dict[ins]
            elif ins == 'CLA Comdty':
                blend_outright = blend_outright + temp_df * w_dict[ins]
                blend_spread = blend_spread + temp_sprd * w_dict[ins]
            elif ins == 'DATA Comdty':
                blend_outright = blend_outright + temp_df * w_dict[ins]
                blend_spread = blend_spread + temp_sprd * w_dict[ins]
        blend_outright.dropna(axis=0, how='all', inplace=True)
        blend_spread.dropna(axis=0, how='all', inplace=True)
        blend_outright.columns = [ticker.decompose_ticker(x)['y'] for x in dict_outright['COA Comdty'].columns]
        blend_spread.columns = [ticker.decompose_ticker(x)['y'] for x in dict_spread26['COA Comdty'].columns]
        return blend_outright, blend_spread

    df_table = pd.DataFrame(columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
    blend_flat_gasoline, blend_sprd_gasoline = cal_blend(
        dict_outright, dict_spread26,
        w_dict={'CLA Comdty': 0.0, 'COA Comdty': 0.0, 'DATA Comdty': 0.0, 'XBA Comdty': 1.0, 'HOA Comdty': 0.0, 'QSA Comdty': 0.0}
    )
    figs = []
    alert_df = pd.DataFrame()
    alert_fig = []
    df_table.loc["Blended Flat", :] = create_table(blend_flat_gasoline, blend_flat_gasoline.columns[-1], ex2020=True)
    df_table.loc["Blended 2-6 Spread", :] = create_table(blend_sprd_gasoline, blend_sprd_gasoline.columns[-1], ex2020=True)
    figs.append(create_chart(blend_flat_gasoline, blend_flat_gasoline.columns[-1], title='Blended Flat'))
    figs.append(create_chart(blend_sprd_gasoline, blend_sprd_gasoline.columns[-1], title='Blended Spread'))
    for ins in gasoline.columns:
        data = gasoline[ins]
        data_by_year = ts.data_by_year(data, freq="B", start_day=1)
        data_by_year = data_by_year.iloc[:, -6:]
        df_table.loc[ins, :] = create_table(data_by_year, data_by_year.columns[-1], ex2020=True)
        figs.append(chart.seasonal_chart(data[data.index >= dt.datetime(2018, 1, 1)].to_frame(ins), title=ins,
                                         **_photo_gap(627, 'seasonal_chart arguments after title=ins')))
    for _idx, row in df_table.iterrows():
        if row["Percentile of 5yr Range"] < -0.9 or row["Percentile of 5yr Range"] > 0.9:
            alert_df = pd.concat([df_table.loc[[_idx], :], alert_df], axis=0)
            alert_fig.insert(0, figs[df_table.index.get_loc(_idx)])
    df_table.index.name = 'Current price vs history'
    df_table.reset_index(inplace=True)
    df_html_table = create_html_table(df_table, 'Global Gasoline')
    figs.insert(0, df_html_table)
    table.figures_to_html(figs, filename=folder_path + 'Global Gasoline_charts.html', task_name=report_name)
    tbs.insert(2, df_html_table)
    tbs.insert(3, u'<a href="{}\\Global Gasoline_charts.html">Charts</a><br>'.format(folder_path))
    if len(alert_df) > 0:
        alert_df.index.name = 'Current price vs history'
        alert_df.reset_index(inplace=True)
        alert_df_html = create_html_table(alert_df, 'Global Gasoline')
        alert_fig.insert(0, alert_df_html)
        table.figures_to_html(alert_fig, filename=folder_path + 'Global Gasoline_alerts.html', task_name=report_name)
        tbs_alert.insert(3, alert_df_html)
        tbs_alert.insert(4, u'<a href="{}\\Global Gasoline_alerts.html">Charts</a><br>'.format(folder_path, k))

    df_table = pd.DataFrame(columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
    blend_flat_gasoil, blend_sprd_gasoil = cal_blend(
        dict_outright, dict_spread26,
        w_dict={'CLA Comdty': 0.0, 'COA Comdty': 0.0, 'DATA Comdty': 0.0, 'XBA Comdty': 0.0, 'HOA Comdty': 0.5, 'QSA Comdty': 0.5}
    )
    figs = []
    alert_df = pd.DataFrame()
    alert_fig = []
    df_table.loc["Blended Flat", :] = create_table(blend_flat_gasoil, blend_flat_gasoil.columns[-1], ex2020=True)
    df_table.loc["Blended 2-6 Spread", :] = create_table(blend_sprd_gasoil, blend_sprd_gasoil.columns[-1], ex2020=True)
    figs.append(create_chart(blend_flat_gasoil, blend_flat_gasoil.columns[-1], title='Blended Flat'))
    figs.append(create_chart(blend_sprd_gasoil, blend_sprd_gasoil.columns[-1], title='Blended Spread'))
    for ins in gasoil.columns:
        data = gasoil[ins]
        data_by_year = ts.data_by_year(data, freq="B")
        data_by_year = data_by_year.iloc[:, -6:]
        try:
            df_table.loc[ins, :] = create_table(data_by_year, data_by_year.columns[-1], ex2020=True)
        except:
            df_table.loc[ins, :] = np.nan
        figs.append(chart.seasonal_chart(data[data.index >= dt.datetime(2018, 1, 1)].to_frame(ins), title=ins,
                                         **_photo_gap(675, 'seasonal_chart arguments after title=ins')))
    for _idx, row in df_table.iterrows():
        if row["Percentile of 5yr Range"] < -0.9 or row["Percentile of 5yr Range"] > 0.9:
            alert_df = pd.concat([df_table.loc[[_idx], :], alert_df], axis=0)
            alert_fig.insert(0, figs[df_table.index.get_loc(_idx)])
    df_table.index.name = 'Current price vs history'
    df_table.reset_index(inplace=True)
    df_html_table = create_html_table(df_table, 'Global Gasoil')
    figs.insert(0, df_html_table)
    table.figures_to_html(figs, filename=folder_path + 'Global Gasoil_charts.html', task_name=report_name)
    tbs.insert(2, df_html_table)
    tbs.insert(3, u'<a href="{}\\Global Gasoil_charts.html">Charts</a><br>'.format(folder_path))
    if len(alert_df) > 0:
        alert_df.index.name = 'Current price vs history'
        alert_df.reset_index(inplace=True)
        alert_df_html = create_html_table(alert_df, 'Global Gasoil')
        alert_fig.insert(0, alert_df_html)
        table.figures_to_html(alert_fig, filename=folder_path + 'Global Gasoil_alerts.html', task_name=report_name)
        tbs_alert.insert(3, alert_df_html)
        tbs_alert.insert(4, u'<a href="{}\\Global Gasoil_alerts.html">Charts</a><br>'.format(folder_path, k))

    df_table = pd.DataFrame(columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
    blend_flat_crude, blend_sprd_crude = cal_blend(
        dict_outright, dict_spread26,
        w_dict={'CLA Comdty': 0.3, 'COA Comdty': 0.28, 'DATA Comdty': 0.42, 'XBA Comdty': 0.0, 'HOA Comdty': 0.0, 'QSA Comdty': 0.0}
    )
    figs = []
    alert_df = pd.DataFrame()
    alert_fig = []
    df_table.loc["Blended Flat", :] = create_table(blend_flat_crude, blend_flat_crude.columns[-1], ex2020=True)
    df_table.loc["Blended 2-6 Spread", :] = create_table(blend_sprd_crude, blend_sprd_crude.columns[-1], ex2020=True)
    figs.append(create_chart(blend_flat_crude, blend_flat_crude.columns[-1], title='Blended Flat'))
    figs.append(create_chart(blend_sprd_crude, blend_sprd_crude.columns[-1], title='Blended Spread'))
    for ins in crude.columns:
        data = crude[ins]
        data_by_year = ts.data_by_year(data, freq="B")
        data_by_year = data_by_year.iloc[:, -6:]
        df_table.loc[ins, :] = create_table(data_by_year, data_by_year.columns[-1], ex2020=True)
        figs.append(chart.seasonal_chart(data[data.index >= dt.datetime(2018, 1, 1)].to_frame(ins), title=ins,
                                         **_photo_gap(720, 'seasonal_chart arguments after title=ins')))
    for _idx, row in df_table.iterrows():
        if row["Percentile of 5yr Range"] < -0.9 or row["Percentile of 5yr Range"] > 0.9:
            alert_df = pd.concat([df_table.loc[[_idx], :], alert_df], axis=0)
            alert_fig.insert(0, figs[df_table.index.get_loc(_idx)])
    df_table.index.name = 'Current price vs history'
    df_table.reset_index(inplace=True)
    df_html_table = create_html_table(df_table, 'Global Crude')
    figs.insert(0, df_html_table)
    table.figures_to_html(figs, filename=folder_path + 'Global Crude_charts.html', task_name=report_name)
    tbs.insert(2, df_html_table)
    tbs.insert(3, u'<a href="{}\\Global Crude_charts.html">Charts</a><br>'.format(folder_path))
    if len(alert_df) > 0:
        alert_df.index.name = 'Current price vs history'
        alert_df.reset_index(inplace=True)
        alert_df_html = create_html_table(alert_df, 'Global Crude')
        alert_fig.insert(0, alert_df_html)
        table.figures_to_html(alert_fig, filename=folder_path + 'Global Crude_alerts.html', task_name=report_name)
        tbs_alert.insert(3, alert_df_html)
        tbs_alert.insert(4, u'<a href="{}\\Global Crude_alerts.html">Charts</a><br>'.format(folder_path, k))

    df_table = pd.DataFrame(columns=['Current Price', 'Percentile of 5yr Range', 'Z-score of 5yr Range', '5yr Avg Price', '5yr Max', '5yr Min'])
    blend_flat_crude, blend_sprd_crude = cal_blend(
        dict_outright, dict_spread26,
        w_dict={'CLA Comdty': 0.167, 'COA Comdty': 0.167, 'DATA Comdty': 0.167, 'XBA Comdty': 0.167, 'HOA Comdty': 0.166, 'QSA Comdty': 0.166}
    )
    figs = []
    alert_df = pd.DataFrame()
    alert_fig = []
    df_table.loc["Blended Flat", :] = create_table(blend_flat_crude, blend_flat_crude.columns[-1], ex2020=True)
    df_table.loc["Blended 2-6 Spread", :] = create_table(blend_sprd_crude, blend_sprd_crude.columns[-1], ex2020=True)
    figs.append(create_chart(blend_flat_crude, blend_flat_crude.columns[-1], title='Blended Flat'))
    figs.append(create_chart(blend_sprd_crude, blend_sprd_crude.columns[-1], title='Blended Spread'))
    data = (2 * crude.iloc[:, 0] + gasoil.iloc[:, 0] + gasoline.iloc[:, 0]) / 4
    data_by_year = ts.data_by_year(data, freq="B")
    data_by_year = data_by_year.loc[:, ~data_by_year.columns.isin([2020, 2022])].iloc[:, -6:]
    try:
        df_table.loc["Physical Oil", :] = create_table(data_by_year, data_by_year.columns[-1], ex2020=True)
    except:
        df_table.loc["Physical Oil", :] = np.nan
    figs.append(chart.seasonal_chart(data[data.index >= dt.datetime(2018, 1, 1)].to_frame(ins), title=ins,
                                     **_photo_gap(767, 'seasonal_chart remaining arguments beginning f')))
    for _idx, row in df_table.iterrows():
        if row["Percentile of 5yr Range"] < -0.9 or row["Percentile of 5yr Range"] > 0.9:
            alert_df = pd.concat([df_table.loc[[_idx], :], alert_df], axis=0)
            alert_fig.insert(0, figs[df_table.index.get_loc(_idx)])
    df_table.index.name = 'Current price vs history'
    df_table.reset_index(inplace=True)
    df_html_table = create_html_table(df_table, 'Composite Oil')
    figs.insert(0, df_html_table)
    table.figures_to_html(figs, filename=folder_path + 'Composite Oil_charts.html', task_name=report_name)
    tbs.insert(2, df_html_table)
    tbs.insert(3, u'<a href="{}\\Composite Oil_charts.html">Charts</a><br>'.format(folder_path))
    if len(alert_df) > 0:
        alert_df.index.name = 'Current price vs history'
        alert_df.reset_index(inplace=True)
        alert_df_html = create_html_table(alert_df, 'Composite Oil')
        alert_fig.insert(0, alert_df_html)
        table.figures_to_html(alert_fig, filename=folder_path + 'Composite Oil_alerts.html', task_name=report_name)
        tbs_alert.insert(3, alert_df_html)
        tbs_alert.insert(4, u'<a href="{}\\Composite Oil_alerts.html">Charts</a><br>'.format(folder_path, k))

    table.figures_to_html(tbs, filename=folder_path + "oil_price_range_full_table.html", task_name=report_name)
    tbs_alert.append(u'<a href="{}\\oil_price_range_full_table.html">Full Tables</a><br>'.format(folder_path))
    table.figures_to_html(
        [table.html_text("Physical Oil Percential Alerts", style="font-family:Calibri;", tag='h1')] + tbs_alert,
        folder_path + "oil_price_range.html", task_name=report_name)
    if today().weekday() == 0:
        send_email(send_to=send_to, subject='Oil price range', body=tbs_alert)


if __name__ == '__main__':
    update(send_to=send_to)
