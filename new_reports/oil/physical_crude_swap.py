import pandas as pd
import numpy as np
import datetime as dt
import plotly as py
import sys
from pandas.tseries.offsets import BDay
import holidays as hols
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today
from ecm.cmds.cdr import month_int2str, month_str2int
import ecm.cmds.pyg as pyg
from dateutil.relativedelta import relativedelta
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.to_html as html
from functools import partial
import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
from ecm.cmds.utils import convert_path_to_linux
from pyg_mongo import *
from ecm.cmds.config import url, root_path, html_path, data_path


def _unrecovered(message, *visible_arguments):
    raise NotImplementedError(message)


db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
outputs_json_oil = f"{root_path}\\outputs\\json\\oil"
outputs_html_oil_link = f"{root_path}\\outputs\\htmls\\oil\\links"
report_name = "Physical Crude and Swaps Page"
file_name = "physical_crude_swap"  # without .py
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
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY,
        start_datetime=dt.datetime(2023, 7, 1, 5, 0), timezone="Europe/London", task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'), background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


def create_table(data, name, inline=False, **kwargs):
    width1 = kwargs.get('width1', 80)
    width2 = kwargs.get('width2', 60)
    chart_columns = kwargs.get('chart_columns', None)
    chart_price = kwargs.get('chart_price', None)
    chg = data.diff()
    chg.columns = [f"{x}_chg" for x in data.columns]
    chg_mean = chg.rolling(65).mean()
    chg_mean.columns = [f"{x}_mean" for x in chg_mean.columns]
    chg_std = chg.rolling(65).std()
    chg_std.columns = [f"{x}_std" for x in chg_std.columns]
    data_ = pd.concat([data, chg, chg_mean, chg_std], axis=1)
    data_mv = data.dropna().rolling(20).mean()
    data_ori = data.copy()
    data_ori.columns = [f"{x}_chg" for x in data_ori.columns]
    data_ori_mean = data_mv.copy()
    data_ori_mean.columns = [f"{x}_mean" for x in data_ori.columns]
    data_ori_std = data.rolling(20).std()
    data_ori_std.columns = [f"{x}_std" for x in data_ori.columns]
    data_mv = pd.concat([data_mv, data_ori, data_ori_mean, data_ori_std], axis=1)
    lastest_mv = data_mv.iloc[-1:, :]
    lastest_mv.index = ['20d ma']
    data_ = data_.iloc[-10:, :]
    data_.index = data_.index.strftime('%d-%b-%y')
    data_ = pd.concat([data_, lastest_mv], axis=0)
    data_.index.name = name
    data_.reset_index(inplace=True)
    hide_cols = [x for x in data_.columns if '_' in x]
    format_dict = {name: {'width': '{:d}px'.format(width1), 'text-align': 'Center'}}
    charts = []
    if chart_columns is None:
        chart_columns = {tuple(data.columns): 20}
    for col in data.columns:
        format_dict[col] = {'width': '{:d}px'.format(width2), 'text-align': 'Center',
                            'highlight_z': [col, f'{col}_chg', f'{col}_chg_mean', f'{col}_chg_std']}
    for k, v in chart_columns.items():
        if isinstance(v, str) and v == 'seasonal':
            if isinstance(k, tuple):
                for col in k:
                    data_chart_ = pd.Series(np.nan, index=pd.bdate_range(dt.datetime(data[col].index[0].year, 1, 1),
                                                                         data[col].index[0] - dt.timedelta(1)))
                    if len(data_chart_) > 0:
                        data_chart_ = pd.concat([data_chart_, data[col]], axis=0)
                    else:
                        data_chart_ = data[col]
                    charts.append(chart.seasonal(df=data_chart_, title=f"{name}_{col}", ex2020=True,
                                                 freq="B", width=750, height=500))
            else:
                data_chart_ = pd.Series(np.nan, index=pd.bdate_range(dt.datetime(data[k].index[0].year, 1, 1),
                                                                     data[k].index[0] - dt.timedelta(1)))
                if len(data_chart_) > 0:
                    data_chart_ = pd.concat([data_chart_, data[k]], axis=0)
                else:
                    data_chart_ = data[k]
                charts.append(chart.seasonal(df=data_chart_, title=f"{name}_{k}", ex2020=True,
                                             freq="B", width=750, height=500))
        elif isinstance(v, pd.DataFrame):
            if isinstance(k, tuple):
                for col in k:
                    data1 = v.reindex(data.index, method='ffill')
                    charts.append(chart.line_chart(df=data[[col]], data_ply2=data1, secondary_y=True,
                                                   title=f"{name}_{col}", width=750, height=500))
            else:
                data1 = v.reindex(data.index, method='ffill')
                charts.append(chart.line_chart(df=data[[k]], data_ply2=data1, secondary_y=True,
                                               title=f"{name}_{k}", width=750, height=500))
        elif isinstance(v, int):
            if isinstance(k, tuple):
                for col in k:
                    data_chart = pd.concat([data[col].dropna(), data[col].dropna().rolling(v).mean()], axis=1)
                    data_chart.columns = [col, f'{v}d ma']
                    if data_chart.iloc[:, 0].dropna().index.min() < dt.datetime(2023, 1, 1):
                        charts.append(chart.seasonal_chart(df=data_chart[col], title=f"{name}_{col}", ex2020=True,
                                                          freq="B", width=750, height=500, vs_avg=True,
                                                          x_axis_title="Date", exclude_years=[2020, 2022]))
                    else:
                        charts.append(chart.line_chart(df=data_chart, title=f"{name}_{col}", width=750, height=500))
            else:
                data_chart = pd.concat([data[k].dropna(), data[k].dropna().rolling(v).mean()], axis=1)
                data_chart.columns = [k, f'{v}d ma']
                if data_chart.iloc[:, 0].dropna().index.min() < dt.datetime(2023, 1, 1):
                    charts.append(chart.seasonal_chart(df=data_chart[k], title=f"{name}_{k}", ex2020=True,
                                                      freq="B", width=750, height=500, vs_avg=True,
                                                      x_axis_title="Date", exclude_years=[2020, 2022]))
                else:
                    charts.append(chart.line_chart(df=data_chart, title=f"{name}_{k}", width=750, height=500))
    file_path = f"{outputs_html_oil_link}\\{name.replace('/', '_')}.html"
    table.figures_to_html(charts, file_path)
    chart_link = f'<a href="{file_path}">{name}</a>'
    html = table.html_format(df=data_, precision=2, background_color='F5F5F5', one_bg_color=True,
                             inline=inline, hide_cols=hide_cols, format_column=format_dict,
                             format_row={len(data_) - 2: {"bottom_border": True}})
    return html.replace(name, chart_link)


def get_monthly_contract(num=4, roll_day=10, months_ahead=1):
    mon_list = []
    if today().day > roll_day:
        mon1 = today() + relativedelta(months=months_ahead) + relativedelta(day=1)
    else:
        mon1 = today() + relativedelta(months=months_ahead - 1) + relativedelta(day=1)
    mon_list.append(mon1)
    for i in range(1, num):
        mon_list.append(mon1 + relativedelta(months=i))
    return mon_list


def get_price_table(contract, num=4, roll_day=10, months_ahead=1, mon_list=None, pdb_spread=True):
    if mon_list is None:
        mon_list = get_monthly_contract(num=num, roll_day=roll_day, months_ahead=months_ahead)
    mon_str_list = [dt.datetime.strftime(x, '%#m/%#d/%Y') if sys.platform.startswith("win") else dt.datetime.strftime(x, '%-m/%-d/%Y') for x in mon_list]
    mon_str_list1 = [dt.datetime.strftime(x, '%b-%Y') for x in mon_list]
    df = pd.DataFrame()
    data = sql.read_sql(f"Select * from ICE_OIL where CONTRACT='{contract}' order by TRADE_DATE, EXPIRATION_DATE")
    for idx, i in enumerate(mon_str_list):
        contract_data = data.loc[data['STRIP'] == i, ['TRADE_DATE', 'SETTLEMENT_PRICE']]
        contract_data.drop_duplicates(inplace=True)
        contract_data.set_index('TRADE_DATE', inplace=True)
        contract_data.index = pd.to_datetime(contract_data.index)
        contract_data.columns = [mon_str_list1[idx]]
        df = pd.concat([df, contract_data], axis=1)
    if contract == 'PDB':
        dbq = sql.read_sql(f"Select * from ICE_OIL where CONTRACT='DBQ' order by TRADE_DATE, EXPIRATION_DATE")
        dbq['STRIP'] = pd.to_datetime(dbq['STRIP'])
        for i in df.index:
            if i >= mon_list[0]:
                dbq_day = dbq.loc[(dbq['STRIP'] > i) & (dbq['STRIP'] < mon_list[1]) & (dbq['TRADE_DATE'] == i)]
                if pdb_spread:
                    df.loc[i, df.columns[0]] = dbq_day['SETTLEMENT_PRICE'].mean() - df.loc[i, df.columns[1]]
                else:
                    df.loc[i, df.columns[0]] = dbq_day['SETTLEMENT_PRICE'].mean()
            else:
                if pdb_spread:
                    df.loc[i, df.columns[0]] = df.loc[i, df.columns[0]] - df.loc[i, df.columns[1]]
    return df


def get_spread(df):
    df = -df.diff(axis=1)
    cols = df.columns[:-1]
    df.drop(df.columns[0], axis=1, inplace=True)
    df.columns = cols
    return df


def weighted_index(df):
    """
    front contract - 50%
    second contract - 30%
    third contract - 10%
    fourth contract - 10%
    """
    return df.iloc[:, 0] * 0.5 + df.iloc[:, 1] * 0.3 + df.iloc[:, 2] * 0.1 + df.iloc[:, 3] * 0.1


def eu_physical():
    forties = pyg.get_data(db, ticker="PCRUFRT2 Index")
    eko = pyg.get_data(db, ticker="PCRUEKO2 PLDP Index")
    cpc = pyg.get_data(db, ticker="PCRUTENG PLDP Index")
    azeri = pyg.get_data(db, ticker="PCRUAZCF PLDP Index")
    bonny = pyg.get_data(db, ticker="PCRUBLT2 PLDP Index")
    johan = pyg.get_data(db, platts_ticker="AJSVB00")
    saharan = pyg.get_data(db, ticker="PCRUSHBA PLDP Index")
    wti_deliver = pyg.get_data(db, ticker="NARI0125 Index", platts_ticker="WMCRB00")
    wti_fob = pyg.get_data(db, platts_ticker="ALNDB00")
    dfl_balmo = sql.read_sql(f"Select * from ICE_OIL where CONTRACT='DBG' order by TRADE_DATE, EXPIRATION_DATE")
    dfl_balmo["STRIP"] = pd.to_datetime(dfl_balmo["STRIP"])
    dfl_balmo["TRADE_DATE"] = pd.to_datetime(dfl_balmo["TRADE_DATE"])
    dfl_balmo = dfl_balmo.loc[dfl_balmo["TRADE_DATE"] < dfl_balmo["STRIP"], :]
    rows = dfl_balmo.groupby("TRADE_DATE")["STRIP"].idxmin()
    dfl_balmo = dfl_balmo.loc[rows]
    dfl_balmo = dfl_balmo[["TRADE_DATE", "SETTLEMENT_PRICE"]]
    dfl_balmo.set_index("TRADE_DATE", inplace=True)
    dfl_balmo = dfl_balmo.sort_index()
    dfl_balmo.columns = ["PX_LAST"]
    wti_fob_ = wti_deliver - 1.1
    wti_fob.columns = ["PX_LAST"]
    wti_fob = pd.concat([wti_fob_.loc[:dt.datetime(2023, 5, 1)], wti_fob], axis=0)
    eu_crude_lt = forties * 0.25 + eko * 0.25 + cpc * 0.167 + azeri * 0.167 + saharan * 0.166 - 0.28
    eu_crude = forties * 0.15 + wti_fob * 0.2 + eko * 0.15 + johan * 0.1 + cpc * 0.1 + azeri * 0.1 + _unrecovered('Crude 303: clipped Bonny weight and formula tail', bonny)
    eu_crude = pd.concat([eu_crude_lt.loc[:dt.datetime(2021, 6, 30), :], eu_crude.loc[dt.datetime(2021, 7, 1):, :]], axis=0)
    eu_crude.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_eu.csv"))
    eu_crude_1 = forties * 0.15 + wti_fob * 0.2 + eko * 0.15 + cpc * 0.125 + azeri * 0.125 + bonny * 0.125 + _unrecovered('Crude 306: clipped alternative EU index tail')
    eu_crude_1.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_eu_1.csv"))
    eu_all = pd.concat([eu_crude, dfl_balmo, forties, eko, johan, cpc, azeri, saharan, bonny, wti_fob], axis=1)
    eu_all.columns = ['Crd-P-EU', 'DFL Balmo', 'Forties', 'Eko', 'Johan', 'CPC', 'Azeri', 'Saharan', 'Bonny', 'WTI FOB']
    eu_all.fillna(method='ffill', inplace=True)
    eu_all = eu_all[['Crd-P-EU', 'DFL Balmo', 'Forties', 'Eko', 'WTI FOB', 'Johan', 'CPC', 'Azeri', 'Saharan', 'Bonny']]
    return eu_all


def us_physical():
    bakken = pyg.get_data(db, ticker="BKCUSPOT LINK Index")
    saddlehorn = pyg.get_data(db, ticker="PSHCM1 LINK Index")
    meh = pyg.get_data(db, ticker="WMEHSPOT LINK Index")
    midland = pyg.get_data(db, ticker="PWTMSPOT LINK Index")
    wcs_cush = pyg.get_data(db, ticker="WC1DM1 LINK Index")
    wti_cash = pyg.get_data(db, ticker="LNKSCASH LINK Index")
    mars = pyg.get_data(db, ticker="USCSMARS Index")
    us_crude = pd.concat([bakken, saddlehorn, meh, midland, wcs_cush, mars, wti_cash], axis=1)
    us_crude.fillna(method='ffill', inplace=True)
    us_crude1 = pd.concat([meh, midland, wcs_cush, wti_cash, mars], axis=1)
    us_crude1.columns = ['MEH', 'Midland', 'WCS Cush', "WTI Cash", "MARS"]
    us_crude1.fillna(method='ffill', inplace=True)
    us_crude1.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_trade_us.csv"))
    us_crude_vol = us_crude.diff().rolling(30).std()
    us_crude_vol.fillna(method='ffill', inplace=True)
    us_crude_vol.fillna(method='bfill', inplace=True)
    us_crude_vol_adj = ([0.1, 0.0, 0.4, 0.3, 0.1, 0.1, 0.0] / us_crude_vol).divide(
        ([0.1, 0.0, 0.4, 0.3, 0.1, 0.1, 0.0] / us_crude_vol).sum(axis=1), axis=0)
    us_index = (us_crude * us_crude_vol_adj).iloc[:, [0, 2, 3, 4, 5]].sum(axis=1, skipna=False)
    us_index = us_index * 0.7 + wti_cash.iloc[:, 0] * 0.3
    us_index.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_us.csv"))
    us_crude_vol_adj_1 = ([0.0, 0.0, 0.4, 0.3, 0.3, 0.0, 0.0] / us_crude_vol).divide(
        ([0.0, 0.0, 0.4, 0.3, 0.3, 0.0, 0.0] / us_crude_vol).sum(axis=1), axis=0)
    us_index_1 = (us_crude * us_crude_vol_adj_1).iloc[:, [2, 3, 4]].sum(axis=1, skipna=False)
    us_index_1.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_us_1.csv"))
    us_all = pd.concat([us_index, us_crude], axis=1)
    us_all.columns = ['Crd-P-US', 'Bakken', 'SaddleHorn', 'MEH', 'Midland', 'WCS Cush', "MARS", "WTI Cash"]
    us_all.fillna(method='ffill', inplace=True)
    us_all = us_all[['Crd-P-US', 'WTI Cash', 'Midland', 'MEH', 'Bakken', 'SaddleHorn', 'WCS Cush', 'MARS']]
    return us_all


def us_physical_nolink():
    meh = bbg.bdh("USCSMEHC Index", ["PX_LAST"], dt.datetime(2018, 1, 1), today())
    midland = bbg.bdh("USCSWTIM Index", ["PX_LAST"], dt.datetime(2022, 8, 3), today())
    wcs_cush = pyg.get_data(db, ticker="PCUC1002 PLDP Index")
    mars = pyg.get_data(db, ticker="USCSMARS Index")
    us_crude = pd.concat([meh, midland, wcs_cush, mars], axis=1)
    us_crude.fillna(method='ffill', inplace=True)
    us_crude_vol = us_crude.diff().rolling(30).std()
    us_crude_vol.fillna(method='ffill', inplace=True)
    us_crude_vol.fillna(method='bfill', inplace=True)
    us_crude_vol_adj = ([0.4, 0.4, 0.1, 0.1] / us_crude_vol).divide(
        ([0.4, 0.4, 0.1, 0.1] / us_crude_vol).sum(axis=1), axis=0)
    us_index = (us_crude * us_crude_vol_adj).iloc[:, [0, 1, 2, 3]].sum(axis=1, skipna=False)
    us_index.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_us.csv"))
    us_crude_vol_adj_1 = ([0.4, 0.3, 0.3, 0.0] / us_crude_vol).divide(
        ([0.4, 0.3, 0.3, 0.0] / us_crude_vol).sum(axis=1), axis=0)
    us_index_1 = (us_crude * us_crude_vol_adj_1).iloc[:, [0, 1, 2]].sum(axis=1, skipna=False)
    us_index_1.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_us_1.csv"))
    us_all = pd.concat([us_index, us_crude], axis=1)
    us_all.columns = ['Crd-P-US', 'MEH', 'Midland', 'WCS Cush', 'MARS']
    us_all.fillna(method='ffill', inplace=True)
    us_all = us_all[['Crd-P-US', 'Midland', 'MEH', 'WCS Cush', 'MARS']]
    return us_all


def asia_physical():
    murban_dub = pyg.get_data(db, ticker="NARP0049 PLDP Index")
    alshaheen = pyg.get_data(db, ticker="PCRUAHDS Index")
    tupi_qingdao = pyg.get_data(db, ticker="NARP0059 PLDP Index")
    wti_sg = pyg.get_data(db, ticker="NARP005F PLDP Index")
    oman = pyg.get_data(db, platts_ticker="DBDOC00")
    zakum = pyg.get_data(db, platts_ticker="DBDUZ00")
    dubai_cash = pyg.get_data(db, platts_ticker="DBDDC00")
    oman_lt_rv = ts.read_csv(f"{data_path}\\bbg\\GCM00567 Index.csv", index_name="date")
    oman_lt_fp = ts.read_csv(f"{data_path}\\bbg\\GIOS0098 Index.csv", index_name="date")
    murban_lt_fp = ts.read_csv(f"{data_path}\\bbg\\GIOS0099 Index.csv", index_name="date")
    dubai_lt_fp = ts.read_csv(f"{data_path}\\bbg\\GIOS0097 Index.csv", index_name="date")
    murban_lt_rv = murban_lt_fp - (oman_lt_fp - oman_lt_rv)
    dubai_lt_rv = dubai_lt_fp - (oman_lt_fp - oman_lt_rv)
    dubai_cash = pd.concat([dubai_lt_rv, dubai_cash], axis=0)
    oman = pd.concat([oman_lt_rv, oman], axis=0)
    murban_dub = pd.concat([murban_lt_rv.loc[:"2018-07-01"], murban_dub], axis=0)
    asia_crude_lt = murban_dub * 0.25 + oman * 0.25 + alshaheen * 0.25 + dubai_cash * 0.25 + 0.28
    asia_crude = murban_dub * 0.2 + oman * 0.25 + zakum * 0.2 + alshaheen * 0.2 + tupi_qingdao * 0.1 + _unrecovered('Crude 394: clipped WTI SG weight and formula tail', wti_sg)
    asia_crude = pd.concat([asia_crude_lt.loc[:"2021-05-31"], asia_crude.loc["2021-06-01":]], axis=0)
    asia_crude.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_index_asia.csv"))
    asia_all = pd.concat([asia_crude, dubai_cash, murban_dub, alshaheen, tupi_qingdao, wti_sg, oman, zakum], axis=1)
    asia_all.columns = ['Crd-P-A', 'Dubai', 'Murban', 'Alshaheen', 'Tupi', 'WTI SG', 'Oman', 'Upper Zakum']
    asia_all.fillna(method='ffill', inplace=True)
    asia_all = asia_all[['Crd-P-A', 'Dubai', 'Oman', 'Alshaheen', 'Upper Zakum', 'Murban', 'Tupi', 'WTI SG']]
    return asia_all


def update_physical():
    start_date = dt.datetime(2018, 1, 1)
    chart_sdate = today() - BDay(260)
    eu_crude = eu_physical()
    us_crude = us_physical()
    asia_crude = asia_physical()
    total_crude = asia_crude['Crd-P-A'] * 0.42 + eu_crude['Crd-P-EU'] * 0.28 + us_crude['Crd-P-US'] * 0.3
    total_crude.fillna(method='ffill', inplace=True)
    co12_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="12")
    cl12_ticker = bbg.live_spread_ticker(active='CLA Comdty', spread="12")
    dat12_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="23")
    co12_price = (pyg.get_data("spreads", active="COA Comdty", item="PX_LAST_gen")[0]).to_frame(co12_ticker)
    cl12_price = (pyg.get_data("spreads", active="CLA Comdty", item="PX_LAST_gen")[0]).to_frame(cl12_ticker)
    dat12_price = (pyg.get_data("spreads", active="DATA Comdty", item="PX_LAST_gen")[1]).to_frame(dat12_ticker)
    co12_price = co12_price.reindex(total_crude.index, method='ffill')
    cl12_price = cl12_price.reindex(total_crude.index, method='ffill')
    dat12_price = dat12_price.reindex(total_crude.index, method='ffill')
    total_price = co12_price[co12_ticker].fillna(method='ffill') * 0.28 + cl12_price[cl12_ticker].fillna(
        method='ffill') * 0.3 + dat12_price[dat12_ticker].fillna(method='ffill') * 0.42
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_unrecovered('Crude 431: clipped wiki link suffix', 'https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774687014/Crude+Ind'))
    existing_cols = eu_crude.columns.to_list()
    eu_crude = pd.concat([co12_price.reindex(eu_crude.index), eu_crude], axis=1)
    eu_crude.columns = [x.split(' ')[0] for x in co12_price.columns] + existing_cols
    new_cols = [eu_crude.columns[1]] + [eu_crude.columns[0]] + eu_crude.columns[2:].to_list()
    eu_crude = eu_crude[new_cols]
    eu_crude.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_detail_eu.csv"))
    figs.append(create_table(data=eu_crude.loc[eu_crude.index >= start_date, :], name='EU Phys Crude',
                             inline=False, width1=100, width2=80,
                             chart_columns={tuple(eu_crude.columns): 'seasonal'}))
    eu_df = pd.concat([eu_crude['Crd-P-EU'].to_frame('EU Phys Crude'), co12_price], axis=1)
    eu_df.dropna(inplace=True)
    eu_df = eu_df.loc[eu_df.index >= chart_sdate, :]
    figs.append(chart.line_chart(df=eu_df[['EU Phys Crude']], data_ply2=eu_df[[co12_ticker]],
                                 secondary_y=True, title='EU phys crude index vs CO frt sprd',
                                 y_axis_title='Index', ply2_axis_title='Spread'))
    existing_cols = us_crude.columns.to_list()
    us_crude = pd.concat([cl12_price.reindex(us_crude.index), us_crude], axis=1)
    us_crude.columns = [x.split(' ')[0] for x in cl12_price.columns] + existing_cols
    new_cols = [us_crude.columns[1]] + [us_crude.columns[0]] + us_crude.columns[2:].to_list()
    us_crude = us_crude[new_cols]
    us_crude.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_detail_us.csv"))
    figs.append(create_table(data=us_crude.loc[us_crude.index >= start_date, :], name='US Phys Crude (Link)',
                             inline=False, width1=100, width2=80,
                             chart_columns={tuple(us_crude.columns): 'seasonal'}))
    us_df = pd.concat([us_crude['Crd-P-US'].to_frame('US Phys Crude'), cl12_price], axis=1)
    us_df.dropna(inplace=True)
    us_df = us_df.loc[us_df.index >= chart_sdate, :]
    figs.append(chart.line_chart(df=us_df[['US Phys Crude']], data_ply2=us_df[[cl12_ticker]],
                                 secondary_y=True, title='US phys crude index vs CL frt sprd',
                                 y_axis_title='Index', ply2_axis_title='Spread'))
    existing_cols = asia_crude.columns.to_list()
    asia_crude = pd.concat([dat12_price.reindex(asia_crude.index), asia_crude], axis=1)
    asia_crude.columns = [x.split(' ')[0] for x in dat12_price.columns] + existing_cols
    new_cols = [asia_crude.columns[1]] + [asia_crude.columns[0]] + asia_crude.columns[2:].to_list()
    asia_crude = asia_crude[new_cols]
    asia_crude.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\physical_crude_detail_asia.csv"))
    figs.append(create_table(data=asia_crude.loc[asia_crude.index >= start_date, :], name='Asia Phys Crude',
                             inline=False, width1=100, width2=80,
                             chart_columns={tuple(asia_crude.columns): 'seasonal'}))
    asia_df = pd.concat([asia_crude['Crd-P-A'].to_frame('Asia Phys Crude'), dat12_price], axis=1)
    asia_df.dropna(inplace=True)
    asia_df = asia_df.loc[asia_df.index >= chart_sdate, :]
    figs.append(chart.line_chart(df=asia_df[['Asia Phys Crude']], data_ply2=asia_df[[dat12_ticker]],
                                 secondary_y=True, title='Asia phys crude index vs DAT frt sprd',
                                 y_axis_title='Index', ply2_axis_title='Spread'))
    total_df = pd.concat([total_crude.to_frame('Crd-P-Global'), total_price.to_frame('Blend frt sprd'), eu_crude['Crd-P-EU'],
                          us_crude['Crd-P-US'], asia_crude['Crd-P-A']], axis=1)
    total_df.columns = ['Crd-P-Global', 'Blend frt sprd', 'Crd-P-EU', 'Crd-P-US', 'Crd-P-A']
    total_df.fillna(method='ffill', inplace=True)
    total_df.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_physical_crude_detail.csv"))
    figs.insert(2, create_table(data=total_df.loc[total_df.index >= start_date, :], name='Global Phys Crude',
                                inline=False, width1=100, width2=80, chart_columns={tuple(total_df.columns): 'seasonal'}))
    total_df.dropna(inplace=True)
    total_df = total_df.loc[total_df.index >= chart_sdate, :]
    global_fig = chart.line_chart(df=total_df[['Crd-P-Global']], data_ply2=total_df[['Blend frt sprd']],
                                  secondary_y=True, title='Global phys crude index vs blend frt sprd',
                                  y_axis_title='Index', ply2_axis_title='Spread', height=500, width=750)
    global_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    figs.insert(3, global_fig)
    figs.append('<br>')
    global_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_crude_fig.json"))
    figs.append('<br> Highlight colors: <br>')
    figs.append(_unrecovered('Crude 551: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Physical Crude Page", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\physical_crude_page.html")


def balmo_price(contract, next_day=True, strip=False):
    dfl_balmo = sql.read_sql(f"Select * from ICE_OIL where CONTRACT='{contract}' order by TRADE_DATE, EXPIRATION_DATE")
    dfl_balmo["STRIP"] = pd.to_datetime(dfl_balmo["STRIP"])
    dfl_balmo["TRADE_DATE"] = pd.to_datetime(dfl_balmo["TRADE_DATE"])
    if next_day:
        dfl_balmo = dfl_balmo.loc[dfl_balmo["TRADE_DATE"] < dfl_balmo["STRIP"], :]
    else:
        dfl_balmo = dfl_balmo.loc[dfl_balmo["TRADE_DATE"] <= dfl_balmo["STRIP"], :]
    rows = dfl_balmo.groupby("TRADE_DATE")["STRIP"].idxmin()
    dfl_balmo = dfl_balmo.loc[rows]
    if strip:
        dfl_balmo = dfl_balmo[["TRADE_DATE", "SETTLEMENT_PRICE", "STRIP"]]
        dfl_balmo.columns = ["TRADE_DATE", "PX_LAST", "STRIP"]
    else:
        dfl_balmo = dfl_balmo[["TRADE_DATE", "SETTLEMENT_PRICE"]]
        dfl_balmo.columns = ["TRADE_DATE", "PX_LAST"]
    dfl_balmo.set_index("TRADE_DATE", inplace=True)
    dfl_balmo = dfl_balmo.sort_index()
    return dfl_balmo


def update_swap():
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_unrecovered('Crude 583: clipped wiki link suffix', 'https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774687014/Crude+Ind'))
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global</p>")
    figs.append('<br>')
    co26_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="26")
    cl26_ticker = bbg.live_spread_ticker(active='CLA Comdty', spread="26")
    dat26_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="24")
    sdate = today() - BDay(260)
    edate = today() - BDay(1)
    dat26_price = bbg.bdh([dat26_ticker], ['PX_LAST'], sdate, edate)
    co_gen = pyg.get_data("contracts", active="COA Comdty", item="PX_LAST_gen")
    cl_gen = pyg.get_data("contracts", active="CLA Comdty", item="PX_LAST_gen")
    co26_price = (co_gen.iloc[:, 1] - co_gen.iloc[:, 5]).to_frame(co26_ticker)
    cl26_price = (cl_gen.iloc[:, 1] - cl_gen.iloc[:, 5]).to_frame(cl26_ticker)
    try:
        total_price = co26_price[co26_ticker].fillna(method='ffill') * 0.28 + cl26_price[cl26_ticker].fillna(
            method='ffill') * 0.3 + dat26_price[dat26_ticker].fillna(method='ffill') * 0.42
    except:
        total_price = co26_price[co26_ticker].fillna(method='ffill') * 0.28 + cl26_price[cl26_ticker].fillna(
            method='ffill') * 0.3 + dat26_price["PX_LAST"].fillna(method='ffill') * 0.42
    total_price.fillna(method='ffill', inplace=True)
    ticker_list = []
    for i in range(1, 4):
        ticker_list.append(bbg.live_spread_ticker(active='COA Comdty', spread=f"{str(i)}{str(i + 1)}"))
    co_sprd_price = bbg.bdh(ticker_list, ['PX_LAST'], sdate, edate)
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Europe</p>")
    figs.append('<br>')
    dbf = get_price_table('DBF')
    tdl = get_price_table('TDL')  # freight TD3C MIDDLE EAST TO CHINA
    wf2 = get_price_table('WF2')  # freight TD22
    bod = get_price_table('BOD')
    pdb = get_price_table('PDB', 5)
    cfd2 = bbg.bdh("ECM2W2 PVMO Index", ["PX_LAST"], dt.datetime(2018, 1, 1), today() - dt.timedelta(1))
    cfd6 = bbg.bdh("ECM2W6 PVMO Index", ["PX_LAST"], dt.datetime(2018, 1, 1), today() - dt.timedelta(1))
    cfd = cfd2 - cfd6
    cfd.fillna(method="ffill", inplace=True)
    cfd = cfd.iloc[:, 0]
    cfd_ = pd.concat([cfd] * dbf.columns.size, axis=1)
    cfd_.columns = dbf.columns
    pdb_sprd = get_spread(pdb.iloc[:, 1:])
    pdb_sprd = pd.concat([pdb.iloc[:, [0]], pdb_sprd], axis=1)
    eu_crude = pdb_sprd * 0.3 + cfd_ * 0.17 + dbf * 0.25 + bod * 0.14 - tdl * 0.135 * 0.14
    eu_summary = pd.concat([weighted_index(eu_crude), cfd2, cfd, weighted_index(dbf), weighted_index(tdl),
                            weighted_index(bod), weighted_index(pdb_sprd)], axis=1)
    eu_summary.columns = ['Crd-S-EU', 'CFD W2', 'CFD26', 'DFL', 'TD3', 'Brent/Dubai', 'Dtd sprds']
    eu_summary = eu_summary[['Crd-S-EU', 'CFD W2', 'CFD26', 'DFL', 'Dtd sprds', 'Brent/Dubai', 'TD3']]
    eu_summary.index.name = "TRADE_DATE"
    eu_summary.fillna(method="ffill", inplace=True)
    eu_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\eu_swap_detail.csv"))
    existing_cols = eu_crude.columns.to_list()
    eu_crude_ = pd.concat([co26_price.reindex(eu_crude.index), eu_crude], axis=1)
    eu_crude_.columns = [x.split(' ')[0] for x in co26_price.columns] + existing_cols
    figs.append(create_table(eu_crude_, name='EU Crude Swap', inline=False, width1=100, width2=80))
    eu_crude_chart = pd.concat([weighted_index(eu_crude), co26_price], axis=1)
    eu_crude_chart.columns = ['EU Crude swap', co26_price.columns[0]]
    eu_crude_chart.dropna(inplace=True)
    eu_crude_chart = eu_crude_chart.loc[eu_crude_chart.index > sdate]
    eu_fig = chart.line_chart(df=eu_crude_chart[[eu_crude_chart.columns[0]]],
                              data_ply2=eu_crude_chart[[eu_crude_chart.columns[1]]],
                              title='EU Crude Swap vs CO 2-6 spread', secondary_y=True,
                              y_axis_title='Index', ply2_axis_title='Spread')
    eu_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_swaps_fig.json"))
    figs.append(eu_fig)
    figs.append('<br>')
    co_sprd_price['DFL'] = np.nan
    co_sprd_price = co_sprd_price[[co_sprd_price.columns[-1]] + co_sprd_price.columns[:-1].to_list()]
    figs.append(create_table(dbf, name='DFL', inline=True, width1=100, width2=80,
                             chart_columns={dbf.columns[0]: 20, dbf.columns[1]: co_sprd_price.iloc[:, [0]],
                                            dbf.columns[2]: co_sprd_price.iloc[:, [1]],
                                            dbf.columns[3]: co_sprd_price.iloc[:, [2]]}))
    figs.append(create_table(tdl, name='TD3', inline=True, width1=100, width2=80))
    figs.append(create_table(bod, name='Brent/Dubai', inline=True, width1=100, width2=80))
    figs.append(create_table(pdb_sprd, name='Dtd sprds', inline=False, width1=100, width2=80))
    figs.append('<br>')
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>US</p>")
    figs.append('<br>')
    how = get_price_table('HOW')
    mlt = get_price_table('MLT')
    arv = get_price_table('ARV', roll_day=25, months_ahead=2)
    wf5 = get_price_table('WF5')
    hoy = get_price_table('HOY', 5)
    hoy_sprd = get_spread(hoy.iloc[:, 1:])
    hoy_sprd.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\how_sprd.csv"))
    month_col = [dt.datetime.strptime(x, '%b-%Y') for x in arv.columns]
    mars_ticker = [f"YVA{month_int2str[x.month]}{str(x.year)[-1]} Comdty" for x in month_col]
    mars = bbg.bdh(mars_ticker, ['PX_LAST'], sdate, edate)
    mars = mars[mars_ticker]
    mars = mars.reindex(arv.index, method='ffill')
    mars.columns = arv.columns
    arv_ = arv.copy()
    arv_.columns = how.columns
    mars_ = mars.copy()
    mars_.columns = how.columns
    how_agg = weighted_index(how)
    mlt_agg = weighted_index(mlt)
    arv_agg = weighted_index(arv_)
    mars_agg = weighted_index(mars_)
    wf5_agg = weighted_index(wf5)
    us_crude_agg = pd.concat([how_agg, mlt_agg, arv_agg, mars_agg, wf5_agg * 0.13642], axis=1)
    us_crude_vol = us_crude_agg.diff().rolling(30).std()
    us_crude_vol.fillna(method='ffill', inplace=True)
    us_crude_vol.fillna(method='bfill', inplace=True)
    vw = ((np.array([0.5, 0.5, 0.1, 0.1, 0.2]) / 1.4) / us_crude_vol).divide(
        ((np.array([0.5, 0.5, 0.1, 0.1, 0.2]) / 1.4) / us_crude_vol).sum(axis=1), axis=0)
    us_crude = how * vw.iloc[-1, 0] + mlt * vw.iloc[-1, 1] + arv_ * vw.iloc[-1, 2] + mars_ * vw.iloc[
        -1, 3] - wf5 * 0.13642 * vw.iloc[-1, 4]
    us_summary = pd.concat([weighted_index(us_crude), weighted_index(how), weighted_index(mlt), weighted_index(arv_),
                            weighted_index(mars_), weighted_index(wf5)], axis=1)
    us_summary.columns = ['Crd-S-US', 'Meh', 'Midland', 'WCS Houston', 'MARS', 'TA Freight']
    us_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\us_swap_detail.csv"))
    existing_cols = us_crude.columns.to_list()
    us_crude_ = pd.concat([cl26_price.reindex(us_crude.index), us_crude], axis=1)
    us_crude_.columns = [x.split(' ')[0] for x in cl26_price.columns] + existing_cols
    us_crude_.fillna(method="ffill", inplace=True)
    figs.append(create_table(us_crude_, name='US Crude Swap', inline=False, width1=100, width2=80))
    us_crude_chart = pd.concat([weighted_index(us_crude), cl26_price], axis=1)
    us_crude_chart.columns = ['US Crude Swap', cl26_price.columns[0]]
    us_crude_chart.dropna(inplace=True)
    us_crude_chart = us_crude_chart.loc[us_crude_chart.index > sdate]
    us_fig = chart.line_chart(df=us_crude_chart[[us_crude_chart.columns[0]]],
                              data_ply2=us_crude_chart[[us_crude_chart.columns[1]]],
                              title='US Crude swap vs CL 2-6 spread', secondary_y=True,
                              y_axis_title='Index', ply2_axis_title='Spread')
    us_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\us_swaps_fig.json"))
    figs.append(us_fig)
    figs.append('<br>')
    figs.append(create_table(how, name='Meh', inline=True, width1=100, width2=80))
    figs.append(create_table(mlt, name='Midland', inline=True, width1=100, width2=80))
    figs.append(create_table(arv, name='WCS Houston', inline=False, width1=100, width2=80))
    figs.append('<br>')
    figs.append(create_table(mars, name='MARS', inline=True, width1=100, width2=80))
    figs.append(create_table(wf5, name='TA Freight', inline=False, width1=100, width2=80))
    figs.append('<br>')
    figs_freight = []
    figs_freight.append("<div style='font-family:Calibri;' >")
    figs_freight.append('<br>')
    td3c = get_price_table("TDL", roll_day=25, months_ahead=1)
    td22 = get_price_table("WF2", roll_day=25, months_ahead=1)
    td25 = get_price_table("WF5", roll_day=25, months_ahead=1)
    td3c_balmo = balmo_price("TDM", next_day=False)
    td3c_da = balmo_price("TDM", next_day=True, strip=True)
    td22_balmo = balmo_price("WF3", next_day=False)
    td22_da = balmo_price("WF3", next_day=True, strip=True)
    td25_balmo = balmo_price("DUR", next_day=False)
    td25_da = balmo_price("DUR", next_day=True, strip=True)
    td3c_balmo.columns = ["BALMO"]
    td3c_da.columns = ["NextDay", "STRIP"]
    td22_balmo.columns = ["BALMO"]
    td22_da.columns = ["NextDay", "STRIP"]
    td25_balmo.columns = ["BALMO"]
    td25_da.columns = ["NextDay", "STRIP"]
    td3c_balmo_ = pd.concat([td3c_balmo, td3c_da], axis=1)
    td22_balmo_ = pd.concat([td22_balmo, td22_da], axis=1)
    td25_balmo_ = pd.concat([td25_balmo, td25_da], axis=1)

    def get_cash_freight(data):
        data['expiry_last'] = data.index + pd.offsets.BMonthEnd(1)
        calendar_exchange = hols.financial_holidays('IFEU')
        data['bdays'] = data.apply(lambda x: calendar_exchange.get_working_days_count(x.STRIP, x.expiry_last), axis=1)
        data['Spot'] = data.BALMO * (data.bdays + 1) - data.NextDay * data.bdays
        data.loc[data.index.month != data.STRIP.dt.month, 'Spot'] = _unrecovered('Crude 771: clipped month-boundary Spot assignment', data)
        return data[['Spot']]

    td3c_cash = get_cash_freight(td3c_balmo_)
    td22_cash = get_cash_freight(td22_balmo_)
    td25_cash = get_cash_freight(td25_balmo_)
    td3c_balmo = pd.concat([td3c_cash.reindex(td3c.index), td3c_balmo.reindex(td3c.index), td3c], axis=1)
    td22_balmo = pd.concat([td22_cash.reindex(td22.index), td22_balmo.reindex(td22.index), td22], axis=1)
    td25_balmo = pd.concat([td25_cash.reindex(td25.index), td25_balmo.reindex(td25.index), td25], axis=1)
    figs_freight.append(_unrecovered('Crude 781: clipped freight section heading', "<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'"))
    figs_freight.append("Global Freight Index = TD3C * 0.6 + TD22 * 0.2 + TD25 * 0.2")
    figs_freight.append('<br>')
    global_freight = td3c_balmo * 0.6 + td22_balmo * 0.2 + td25_balmo * 0.2
    figs_freight.append(create_table(global_freight, name='Global Crude Freight', inline=True, width1=100, width2=80))
    figs_freight.append(create_table(td3c_balmo, name='TD3C', inline=True, width1=100, width2=80))
    figs_freight.append(create_table(td22_balmo, name='TD22', inline=True, width1=100, width2=80))
    figs_freight.append(create_table(td25_balmo, name='TD25', inline=False, width1=100, width2=80))
    figs_freight.append('<br>')
    freight_chart = pd.concat([global_freight.iloc[:, 0], td3c_balmo.iloc[:, 0]], axis=1)
    freight_chart.columns = ['Global', 'TD3C']
    freight_chart = freight_chart.loc[freight_chart.index > sdate, :]
    freight_chart1 = pd.concat([td22_balmo.iloc[:, 0], td25_balmo.iloc[:, 0]], axis=1)
    freight_chart1.columns = ['TD22', 'TD25']
    freight_chart1 = freight_chart1.loc[freight_chart1.index > sdate, :]
    freight_fig = chart.line_chart(df=freight_chart, data_ply2=freight_chart1, secondary_y=True,
                                   title='Global Crude Freight Spot', y_axis_title='Global/TD3C', ply2_axis_title='TD22/TD25',
                                   highlight_dict={'Global': {'color': 'black', 'width': 2}}, height=500, width=750)
    freight_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    freight_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_freight_cash_fig.json"))
    freight_swap_chart = pd.concat([(global_freight.iloc[:, 1] + global_freight.iloc[:, 2]) / 2,
                                    (td3c_balmo.iloc[:, 1] + td3c_balmo.iloc[:, 2]) / 2], axis=1)
    freight_swap_chart.columns = ['Global', 'TD3C']
    freight_swap_chart = freight_swap_chart.loc[freight_swap_chart.index > sdate, :]
    freight_swap_chart1 = pd.concat([(td22_balmo.iloc[:, 1] + td22_balmo.iloc[:, 2]) / 2,
                                     (td25_balmo.iloc[:, 1] + td25_balmo.iloc[:, 2]) / 2], axis=1)
    freight_swap_chart1.columns = ['TD22', 'TD25']
    freight_swap_chart1 = freight_swap_chart1.loc[freight_swap_chart1.index > sdate, :]
    freight_swap_fig = chart.line_chart(df=freight_swap_chart, data_ply2=freight_swap_chart1, secondary_y=True,
                                        title='Global Crude Freight BOM+M1', y_axis_title='Global/TD3C', ply2_axis_title='TD22/TD25',
                                        highlight_dict={'Global': {'color': 'black', 'width': 2}}, height=500, width=750)
    freight_swap_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    freight_swap_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_freight_bom_fig.json"))
    figs_freight.append([freight_fig, freight_swap_fig])
    figs_freight.append('<br>')
    tc2 = get_price_table("WNU", roll_day=25, months_ahead=1)
    tc5 = get_price_table("WMJ", roll_day=25, months_ahead=1)
    tc2_balmo = balmo_price("WNT", next_day=False)
    tc5_balmo = balmo_price("WNX", next_day=False)
    tc2_balmo.columns = ["BALMO"]
    tc5_balmo.columns = ["BALMO"]
    tc2_balmo = pd.concat([tc2_balmo.reindex(tc2.index), tc2], axis=1)
    tc5_balmo = pd.concat([tc5_balmo.reindex(tc5.index), tc5], axis=1)
    figs_freight.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Clean Freight</p>")
    figs_freight.append('<br>')
    global_clean_freight = tc2_balmo * 0.5 + tc5_balmo * 0.5
    figs_freight.append(create_table(global_clean_freight, name='Global Clean Freight', inline=True, width1=100, width2=80))
    figs_freight.append(create_table(tc2_balmo, name='TC2', inline=True, width1=100, width2=80))
    figs_freight.append(create_table(tc5_balmo, name='TC5', inline=False, width1=100, width2=80))
    figs_freight.append('<br>')
    freight_chart = pd.concat([global_clean_freight.iloc[:, 0], tc2_balmo.iloc[:, 0], tc5_balmo.iloc[:, 0]], axis=1)
    freight_chart.columns = ['Global', 'TC2', 'TC5']
    freight_chart = freight_chart.loc[freight_chart.index > sdate, :]
    freight_fig = chart.line_chart(df=freight_chart, secondary_y=True, title='Global Clean Freight',
                                   y_axis_title='$/ton', highlight_dict={'Global': {'color': 'black', 'width': 2}},
                                   height=500, width=750)
    freight_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    freight_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_clean_freight_fig.json"))
    clean_freight_swap_chart = pd.concat([weighted_index(global_clean_freight), weighted_index(tc2), weighted_index(tc5)], axis=1)
    clean_freight_swap_chart.columns = ['Global', 'TD2', 'TC5']
    clean_freight_swap_chart = clean_freight_swap_chart.loc[clean_freight_swap_chart.index > sdate, :]
    clean_freight_swap_fig = chart.line_chart(df=clean_freight_swap_chart, title='Global Clean Freight Swap',
                                             highlight_dict={'Global': {'color': 'black', 'width': 2}}, height=500, width=750)
    clean_freight_swap_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    clean_freight_swap_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\clean_freight_swap_fig.json"))
    figs_freight.append([freight_fig, clean_freight_swap_fig])
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Singapore</p>")
    figs.append('<br>')
    tickers = []
    contracts = pyg.get_data("contracts", active='COA Comdty', item='fut_chain')
    roll = "t3"
    tickers.append((contracts.loc[contracts[roll] > today(), :].iloc[0, :])["ticker"])
    tickers.append((contracts.loc[contracts[roll] > today(), :].iloc[1, :])["ticker"])
    tickers.append((contracts.loc[contracts[roll] > today(), :].iloc[2, :])["ticker"])
    tickers.append((contracts.loc[contracts[roll] > today(), :].iloc[3, :])["ticker"])
    tickers.append((contracts.loc[contracts[roll] > today(), :].iloc[4, :])["ticker"])
    tickers_flat = ['MUC' + x[2] + '2' + x[3] + tickers[idx + 1][4:] for idx, x in enumerate(tickers[:-1])]
    tickers = ['MUC' + x[2:4] + tickers[idx + 1][2:] for idx, x in enumerate(tickers[:-1])]
    murban_price = bbg.bdh(tickers, ['PX_LAST'], sdate, edate)
    murban_price.columns = [x.split(' ')[0] for x in murban_price.columns]
    murban_flat = bbg.bdh(tickers_flat, ['PX_LAST'], sdate, edate)
    murban_flat.columns = [dt.datetime.strptime(x, '%m/%Y').strftime('%b-%Y') for x in _unrecovered('Crude 921: clipped Bloomberg reference fields/result selection', murban_flat)]
    dbi = get_price_table('DBI', num=6)
    dbi_sprd = murban_flat - dbi[murban_flat.columns]
    dbi_sprd.columns = dbi.columns[:4]
    murban_price_ = murban_price.copy()
    murban_price_.columns = dbi.columns[:4]
    murban_china = murban_flat.iloc[:, 0] + td3c[murban_flat.columns[0]] / 7.64
    cl12_contract = bbg.live_contract(active='CLA Comdty')
    cl12_price = bbg.bdh(cl12_contract['ticker'], ['PX_LAST'], sdate, edate)['PX_LAST']
    cl12_my = bbg.bref(cl12_contract['ticker'], "FUT_MONTH_YR").iloc[0, 0]
    cl12_my = cl12_my.split(" ")[0].capitalize() + "-" + str(2000 + int(cl12_my.split(" ")[1]))
    meh_ticker = f"WMEHM {cl12_contract['m']}{str(int(cl12_contract['y']))[-2:]} LINK Index"
    meh_china = bbg.bdh(meh_ticker, ['PX_LAST'], sdate, edate)['PX_LAST'] + cl12_price + td22[cl12_my] / 7.64
    asia_crude = (dbi_sprd * 0.5 + murban_price_ * 0.5 + tdl * 0.135 * 0.2 - bod * 0.2) / 1.4
    asia_summary = pd.concat([weighted_index(asia_crude), weighted_index(dbi_sprd),
                              weighted_index(murban_price_), weighted_index(bod), weighted_index(tdl)], axis=1)
    asia_summary.columns = ['Crd-S-A', 'Murban/Dubai', 'Murban Spreads', 'Brent/Dubai', 'TD3']
    asia_summary.index.name = 'TRADE_DATE'
    asia_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\asia_swap_detail.csv"))
    existing_cols = asia_crude.columns.to_list()
    asia_crude_ = pd.concat([dat26_price.reindex(asia_crude.index), asia_crude], axis=1)
    asia_crude_.columns = [x.split(' ')[0] for x in dat26_price.columns] + existing_cols
    figs.append(create_table(asia_crude_, name='Asia Crude Swap', inline=True, width1=100, width2=80))
    figs.append(create_table(dbi_sprd, name='Murban/Dubai', inline=True, width1=100, width2=80))
    figs.append(create_table(murban_price, name='Murban sprd', inline=True, width1=100, width2=80))
    figs.append(create_table(bod, name='Brent/Dubai', inline=False, width1=100, width2=80))
    figs.append('<br>')
    asia_crude_chart = pd.concat([weighted_index(asia_crude), dat26_price], axis=1)
    asia_crude_chart.columns = ['Asia Crude swap', dat26_price.columns[0]]
    asia_crude_chart.dropna(inplace=True)
    asia_crude_chart = asia_crude_chart.loc[asia_crude_chart.index > sdate]
    asia_fig = chart.line_chart(df=asia_crude_chart[[asia_crude_chart.columns[0]]],
                                data_ply2=asia_crude_chart[[asia_crude_chart.columns[1]]],
                                title='Asia Crude Swap vs DAT 2-4 spread', secondary_y=True,
                                y_axis_title='Index', ply2_axis_title='Spread')
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_swaps_fig.json"))
    figs.append(asia_fig)
    us_crude.columns = eu_crude.columns
    total_index = asia_crude * 0.42 + eu_crude * 0.28 + us_crude * 0.3
    total_summary = pd.concat([weighted_index(total_index), weighted_index(eu_crude), weighted_index(us_crude),
                               weighted_index(asia_crude)], axis=1)
    total_summary.columns = ['Crd-S-Global', 'Crd-S-EU', 'Crd-S-US', 'Crd-S-A']
    total_summary.index.name = 'TRADE_DATE'
    total_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_swap_detail.csv"))
    freight = pd.concat([td3c_balmo.iloc[:, 0] * 0.6 + td22_balmo.iloc[:, 0] * 0.2 + td25_balmo.iloc[:, 0] * 0.2,
                          td3c_balmo.iloc[:, 0], td25_balmo.iloc[:, 0], td22_balmo.iloc[:, 0]], axis=1)
    freight.columns = ['Freight', 'TD3C (ME-CHN)', 'TD25 (USGC-ARA)', 'TD22 (USGC-CHN)']
    freight.index.name = 'TRADE_DATE'
    freight.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_freight.csv"))
    freight = pd.concat([(td3c_balmo.iloc[:, 1] + td3c_balmo.iloc[:, 2]) / 2 * 0.6 + (td22_balmo.iloc[:, 1] + td22_balmo.iloc[:, 2]) / 2 * 0.2 + (td25_balmo.iloc[:, 1] + td25_balmo.iloc[:, 2]) / 2 * 0.2,
                          (td3c_balmo.iloc[:, 1] + td3c_balmo.iloc[:, 2]) / 2, (td25_balmo.iloc[:, 1] + td25_balmo.iloc[:, 2]) / 2,
                          (td22_balmo.iloc[:, 1] + td22_balmo.iloc[:, 2]) / 2], axis=1)
    freight.columns = ['Freight', 'TD3C (ME-CHN)', 'TD25 (USGC-ARA)', 'TD22 (USGC-CHN)']
    freight.index.name = 'TRADE_DATE'
    freight.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_freight_swap.csv"))
    clean_freight = pd.concat([tc2_balmo.iloc[:, 0] * 0.5 + tc5_balmo.iloc[:, 0] * 0.5,
                                tc2_balmo.iloc[:, 0], tc5_balmo.iloc[:, 0]], axis=1)
    clean_freight.columns = ['Freight', 'TC2 (NWE-USAC)', 'TC5 (ME-JP)']
    clean_freight.index.name = 'TRADE_DATE'
    clean_freight.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_clean_freight.csv"))
    clean_freight_swap = pd.concat([weighted_index(tc2) * 0.5 + weighted_index(tc5) * 0.5,
                                    weighted_index(tc2), weighted_index(tc5)], axis=1)
    clean_freight_swap.columns = ['Freight', 'TC2 (NWE-USAC)', 'TC5 (ME-JP)']
    clean_freight_swap.index.name = 'TRADE_DATE'
    clean_freight_swap.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_clean_freight_swap.csv"))
    existing_cols = total_index.columns.to_list()
    total_index_ = pd.concat([total_price.reindex(total_index.index), total_index], axis=1)
    total_index_.columns = ['Blend 2-6 sprd'] + existing_cols
    figs.insert(3, create_table(total_index_, name='Global Crude Swap', inline=False, width1=100, width2=80))
    total_crude_chart = pd.concat([weighted_index(total_index), total_price], axis=1)
    total_crude_chart.columns = ['Global Crude Swap', 'Blend 2-6 spread']
    total_crude_chart.dropna(inplace=True)
    total_crude_chart = total_crude_chart.loc[total_crude_chart.index > sdate]
    total_fig = chart.line_chart(df=total_crude_chart[[total_crude_chart.columns[0]]],
                                 data_ply2=total_crude_chart[[total_crude_chart.columns[1]]],
                                 title='Global Crude Swap vs Blend 2-6 spread', secondary_y=True,
                                 y_axis_title='Index', ply2_axis_title='Spread', height=500, width=750)
    total_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    total_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_swaps_fig.json"))
    figs.insert(4, total_fig)
    figs.append('<br>')
    figs.append('<br> Highlight colors: <br>')
    figs.append(_unrecovered('Crude 1042: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Crude Swaps Page", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\crude_swaps_page.html")
    figs_freight.append('<br> Highlight colors: <br>')
    figs_freight.append(_unrecovered('Crude 1051: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs_freight.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs_freight.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html([table.html_text("Global Freight Page", style="font-family:Calibri;", tag='h1')] + figs_freight,
                   f"{html_path}\\oil\\global_freight_page.html")


def atlantic_basin():
    start_date = dt.datetime(2018, 1, 1)
    saharan = pyg.get_data(db, ticker="PCRUSHBA PLDP Index")
    cpc = pyg.get_data(db, ticker="PCRUTENG PLDP Index")
    eko = pyg.get_data(db, ticker="PCRUEKO2 PLDP Index")
    forties = pyg.get_data(db, ticker="PCRUFRT2 Index")
    bonny = pyg.get_data(db, ticker="PCRUBLT2 PLDP Index")
    egina = pyg.get_data(db, ticker="NARI0114 PLDP Index")
    azeri = pyg.get_data(db, ticker="PCRUAZCF PLDP Index")
    meh = pyg.get_data(db, ticker="USCSMEHC Index")
    midland = pyg.get_data(db, ticker="USCSWTIM Index")
    co12_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="12")
    sdate = today() - BDay(260)
    edate = today() - BDay(1)
    co12_price = bbg.bdh([co12_ticker], ['PX_LAST'], sdate, edate)
    cl1_ticker = (bbg.live_contract(active='CLA Comdty', seq=0))["ticker"]
    cl2_ticker = (bbg.live_contract(active='CLA Comdty', seq=1))["ticker"]
    hrt1_ticker = 'HRT' + cl1_ticker[2:]
    hrt2_ticker = 'HRT' + cl2_ticker[2:]
    meh_prices = bbg.bdh([cl1_ticker, cl2_ticker, hrt1_ticker, hrt2_ticker], ['PX_LAST'], sdate, edate)
    meh_sprd1 = (meh_prices[hrt1_ticker] + meh_prices[cl1_ticker]) - (meh_prices[hrt2_ticker] + meh_prices[cl2_ticker])
    sprd_price = co12_price.iloc[:, 0] * 0.5 + meh_sprd1 * 0.5
    ab_index = saharan * 0.05 + cpc * 0.05 + eko * 0.2 + forties * 0.1 + \
        midland * 0.1 + meh * 0.2 + bonny * 0.1 + egina * 0.1 + azeri * 0.1
    df = pd.concat([ab_index, sprd_price, saharan, cpc, eko, forties, meh, midland, bonny, egina, azeri], axis=1)
    df.columns = ['AB Index', 'CO and MEH sprd', 'Saharan', 'CPC', 'Ekofisk', 'Forties', 'MEH', 'Midland', 'Bonny',
                  'Egina', 'Azeri']
    df.fillna(method='ffill', inplace=True)
    df.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\sweet_crude_detail.csv"))
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("AB Index = Saharan*0.05 + CPC*0.05 + Ekofisk*0.2 + Forties*0.1 + Midland*0.1 + "
                "MEH*0.2 + Bonny*0.1 + Egina*0.1 + Azeri*0.1 <br>")
    figs.append(create_table(df.loc[df.index >= start_date, :], name='Atlantic Basin', inline=False, width1=100, width2=80))
    sprd_price = sprd_price.reindex(df.index)
    sprd_price.fillna(method='ffill', inplace=True)
    sweet_crude_fig = chart.line_chart(df=df.loc[df.index >= sdate, ['AB Index']],
                                       data_ply2=sprd_price[sprd_price.index >= sdate].to_frame('spread'),
                                       title='Atlantic Basin index vs CO and MEH frt sprd', secondary_y=True,
                                       y_axis_title='Index', ply2_axis_title='Spread')
    sweet_crude_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\sweet_crude_fig.json"))
    figs.append(sweet_crude_fig)
    wti_price = bbg.bdh(['WMEHSPOT LINK Index', 'WMEHM1 LINK Index', 'LNKSMDSW Index', 'PWTMM1 LINK Index', 'LNKSCASH Index'],
                        ['PX_LAST'], sdate, edate)
    wti_price = wti_price.reindex(meh_prices.index, method='ffill')
    meh_struct = (wti_price['WMEHSPOT LINK Index'] + meh_prices[cl1_ticker]) - (
        wti_price['WMEHM1 LINK Index'] + meh_prices[cl2_ticker])
    middy = (wti_price['LNKSMDSW Index'] + meh_prices[cl1_ticker]) - (
        wti_price['PWTMM1 LINK Index'] + meh_prices[cl2_ticker])
    mont_list = [dt.datetime(2020 + int(cl1_ticker[3]), month_str2int[cl1_ticker[2]], 1),
                 dt.datetime(2020 + int(cl2_ticker[3]), month_str2int[cl2_ticker[2]], 1)]
    dated_price = get_price_table('PDB', mon_list=mont_list, pdb_spread=False)
    dated_struct = dated_price.iloc[:, 0] - dated_price.iloc[:, 1]
    cash_roll = wti_price['LNKSCASH Index']
    struct_df = pd.concat([meh_struct, middy, dated_struct, cash_roll], axis=1)
    struct_df.columns = ['MEH', 'Middy', 'Dated', 'Cash roll']
    struct_df.fillna(method='ffill', inplace=True)
    figs.append('<br>')
    figs.append(create_table(data=struct_df, name='Phys Structure', inline=False, width1=100, width2=80))
    figs.append('<br> Highlight colors: <br>')
    figs.append(_unrecovered('Crude 1153: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Atlantic Basin Physical Sweet Index", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\ab_index.html")


def sour_index():
    start_date = dt.datetime(2018, 1, 1)
    murban = pyg.get_data(db, ticker="NARP0049 PLDP Index")
    alshaheen = pyg.get_data(db, ticker="PCRUAHDS Index")
    oman = pyg.get_data(db, platts_ticker="DBDOC00")
    zakum = pyg.get_data(db, platts_ticker="DBDUZ00")
    dubai_cash = pyg.get_data(db, platts_ticker="DBDDC00")
    mars = pyg.get_data(db, ticker="USCSMARS Index")
    johan = pyg.get_data(db, platts_ticker="AJSVB00")
    basrah_m = bbg.bdh("ZOSPBMAS Index", ["PX_LAST"], start_date, today() + relativedelta(day=31))
    basrah = basrah_m.reindex(pd.date_range(dt.datetime(2021, 1, 1), today() + relativedelta(day=31))).fillna(
        method=_unrecovered('Crude 1171: clipped Basrah fill method'))
    basrah = basrah.reindex(pd.bdate_range(dt.datetime(2021, 1, 1), today() - BDay(1)))
    basrah.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\basrah_medium_asia.csv"))
    dat12_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="23")
    sdate = today() - BDay(260)
    edate = today() - BDay(1)
    dat12_price = bbg.bdh([dat12_ticker], ['PX_LAST'], sdate, edate).iloc[:, 0]
    sc_index = (murban + alshaheen + oman + zakum + dubai_cash + mars + johan + basrah) / 8
    df = pd.concat([sc_index, dat12_price, dubai_cash, murban, alshaheen, oman, zakum, johan, basrah, mars], axis=1)
    df.columns = ['Sour Index', 'DAT frt sprd', 'Dubai', 'Murban', 'Alshaheen', 'Oman', 'Upper Zakum', 'Johan',
                  'Basrah Medium', 'Mars']
    df.fillna(method="ffill", inplace=True)
    df.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\sour_crude_detail.csv"))
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("Sour Index = (Dubai + Murban + Alshaheen + Oman + Upper Zakum + "
                "Johan + Urals + Basrah Medium + Mars)/9 <br>")
    figs.append(create_table(df.loc[df.index >= start_date, :], name='Sour Crude', inline=False, width1=100, width2=80))
    sprd_price = dat12_price.reindex(df.index)
    sprd_price.fillna(method='ffill', inplace=True)
    sour_crude_fig = chart.line_chart(df=df.loc[df.index >= sdate, ['Sour Index']],
                                      data_ply2=sprd_price.loc[sprd_price.index >= sdate].to_frame('spread'),
                                      title='Sour Crude index vs Dat frt sprd', secondary_y=True,
                                      y_axis_title='Index', ply2_axis_title='Spread')
    sour_crude_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\sour_crude_fig.json"))


def update_physical_and_swap():
    start_date = dt.datetime(2018, 1, 1)
    eu_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_eu.csv", index_name="date")
    us_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_us.csv", index_name="date")
    asia_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_asia.csv", index_name="date")
    total_crude = asia_crude['Crd-P-A'] * 0.42 + eu_crude['Crd-P-EU'] * 0.28 + us_crude['Crd-P-US'] * 0.3
    total_crude.fillna(method='ffill', inplace=True)
    co12_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="12")
    cl12_ticker = bbg.live_spread_ticker(active='CLA Comdty', spread="12")
    dat12_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="23")
    sdate = today() - BDay(260)
    edate = today() - BDay(1)
    co12_price = (pyg.get_data("spreads", active="COA Comdty", item="PX_LAST_gen")[0]).to_frame(co12_ticker)
    cl12_price = (pyg.get_data("spreads", active="CLA Comdty", item="PX_LAST_gen")[0]).to_frame(cl12_ticker)
    dat12_price = (pyg.get_data("spreads", active="DATA Comdty", item="PX_LAST_gen")[1]).to_frame(dat12_ticker)
    co12_price = co12_price.reindex(total_crude.index, method='ffill')
    cl12_price = cl12_price.reindex(total_crude.index, method='ffill')
    dat12_price = dat12_price.reindex(total_crude.index, method='ffill')
    total_price = co12_price[co12_ticker].fillna(method='ffill') * 0.28 + cl12_price[cl12_ticker].fillna(
        method='ffill') * 0.3 + dat12_price[dat12_ticker].fillna(method='ffill') * 0.42
    co26_ticker = bbg.live_spread_ticker('COA Comdty', spread="26")
    cl26_ticker = bbg.live_spread_ticker('CLA Comdty', spread="26")
    dat26_ticker = bbg.live_spread_ticker('DATA Comdty', spread="24")
    dat26_price = bbg.bdh([dat26_ticker], ['PX_LAST'], sdate, edate)
    co_gen = pyg.get_data("contracts", active="COA Comdty", item="PX_LAST_gen")
    cl_gen = pyg.get_data("contracts", active="CLA Comdty", item="PX_LAST_gen")
    co26_price = (co_gen.iloc[:, 1] - co_gen.iloc[:, 5]).to_frame(co26_ticker)
    cl26_price = (cl_gen.iloc[:, 1] - cl_gen.iloc[:, 5]).to_frame(cl26_ticker)
    try:
        total_price_26 = co26_price[co26_ticker].fillna(method='ffill') * 0.28 + cl26_price[cl26_ticker].fillna(
            method='ffill') * 0.3 + dat26_price[dat26_ticker].fillna(method='ffill') * 0.42
    except:
        total_price_26 = co26_price[co26_ticker].fillna(method='ffill') * 0.28 + cl26_price[cl26_ticker].fillna(
            method='ffill') * 0.3 + dat26_price["PX_LAST"].fillna(method='ffill') * 0.42
    price26_save = pd.concat([total_price_26.to_frame('Blend 2-6 sprd'), co26_price, cl26_price, dat26_price], axis=1)
    price26_save.fillna(method='ffill', inplace=True)
    price26_save.index.name = 'TRADE_DATE'
    price26_save.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_crude_26.csv"))
    dat_flat_ticker = bbg.live_contract(active="DATA Comdty", seq=1, roll="t1")["ticker"]
    dat_price = bbg.bdh([dat_flat_ticker], ['PX_LAST'], sdate, edate)
    dat_price.columns = [dat_flat_ticker]
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(''.join([_unrecovered('Crude 1259: clipped wiki link suffix', 'https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774687014/'),
                         '&emsp;', u'<a href="{}\\oil\\physical_crude_page.html">Physical</a>'.format(html_path),
                         '&emsp;', u'<a href="{}\\oil\\crude_swaps_page.html">Swaps</a>'.format(html_path),
                         '&emsp;', u'<a href="{}\\oil\\ab_index.html">Atlantic Basin</a>'.format(html_path),
                         '&emsp;', u'<a href="{}\\oil\\global_freight_page.html">Freight</a>'.format(html_path)]))
    figs.append('<br>')
    sweet_crude = ts.read_csv(f"{outputs_csv_oil}\\sweet_crude_detail.csv", index_name="date")
    sweet_crude_table = create_table(sweet_crude.loc[sweet_crude.index >= start_date, :], name='Atlantic Basin',
                                    **_unrecovered('Crude 1273: clipped sweet crude table arguments'))
    sweet_crude_fig = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\sweet_crude_fig.json"))
    sour_crude = ts.read_csv(f"{outputs_csv_oil}\\sour_crude_detail.csv", index_name="date")
    sour_crude_table = create_table(sour_crude.loc[sour_crude.index >= start_date, :], name='Sour Crude',
                                   **_unrecovered('Crude 1276: clipped sour crude table arguments'))
    sour_crude_fig = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\sour_crude_fig.json"))
    figs.append([sweet_crude_table, sour_crude_table])
    figs.append([sweet_crude_fig, sour_crude_fig])
    figs.append('</div>')
    figs.append('<br>')
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global</p>")
    figs.append('<br>')
    table_row = []
    table_row1 = []
    total_df = ts.read_csv(f"{outputs_csv_oil}\\global_physical_crude_detail.csv", index_name='date')
    table_row.append(create_table(data=total_df.loc[total_df.index >= start_date, :], name='Global Phys Crude',
                                  inline=True, width1=100, width2=80, chart_columns={tuple(total_df.columns): "seasonal"}))
    total_freight = ts.read_csv(f"{outputs_csv_oil}\\global_freight.csv", index_name='TRADE_DATE')
    table_row.append(create_table(data=total_freight.tail(100), name='Crude Freight Spot', inline=False, width1=100, width2=120))
    total_swap = ts.read_csv(f"{outputs_csv_oil}\\global_swap_detail.csv", index_name='TRADE_DATE')
    existing_cols = total_swap.columns.to_list()
    total_swap = pd.concat([total_price_26.reindex(total_swap.index), total_swap], axis=1)
    total_swap.columns = ['Blend 2-6 sprd'] + existing_cols
    new_cols = [total_swap.columns[1]] + [total_swap.columns[0]] + total_swap.columns[2:].to_list()
    total_swap = total_swap[new_cols]
    total_swap.fillna(method="ffill", inplace=True)
    table_row1.append(create_table(data=total_swap.tail(100), name='Global Crude Swap', inline=True, width1=100, width2=80))
    total_freight_swap = ts.read_csv(f"{outputs_csv_oil}\\global_freight_swap.csv", index_name='TRADE_DATE')
    table_row1.append(create_table(data=total_freight_swap.tail(100), name='Crude Freight BOM+M1', inline=False, width1=100, width2=120))
    fig_charts = [py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_crude_fig.json")),
                  py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_freight_cash_fig.json"))]
    fig_charts1 = [py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_swaps_fig.json")),
                   py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_freight_bom_fig.json"))]
    figs.append(table.figs_to_grid(table_row + fig_charts, columns=2))
    figs.append(table.figs_to_grid(table_row1 + fig_charts1, columns=2))
    figs.append('</div>')
    eu_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU</p>")
    eu_figs.append(create_table(data=eu_crude.loc[eu_crude.index >= start_date, :], name='EU Phys Crude',
                                  inline=True, width1=100, width2=80, chart_columns={tuple(eu_crude.columns): "seasonal"}))
    eu_swap = ts.read_csv(f"{outputs_csv_oil}\\eu_swap_detail.csv", index_name='TRADE_DATE')
    existing_cols = eu_swap.columns.to_list()
    eu_swap = pd.concat([co26_price.reindex(eu_swap.index), eu_swap], axis=1)
    eu_swap.columns = [x.split(' ')[0] for x in co26_price.columns] + existing_cols
    new_cols = [eu_swap.columns[1]] + [eu_swap.columns[0]] + eu_swap.columns[2:].to_list()
    eu_swap = eu_swap[new_cols]
    eu_figs.append(create_table(data=eu_swap.tail(100), name='EU Crude Swap', inline=False, width1=100, width2=80,
                                  chart_columns={eu_swap.columns[0]: eu_swap.iloc[:, [1]], eu_swap.columns[1]: 20,
                                                 tuple(eu_swap.columns[2:]): eu_swap.iloc[:, [1]]}))
    eu_df = pd.concat([eu_crude['Crd-P-EU'].to_frame('EU Phys Crude'), co12_price], axis=1)
    eu_df.dropna(inplace=True)
    eu_df = eu_df.loc[eu_df.index > sdate, :]
    eu_figs.append(chart.line_chart(df=eu_df[['EU Phys Crude']], data_ply2=eu_df[[co12_ticker]],
                                      title='EU crude index vs CO frt sprd', secondary_y=True,
                                      y_axis_title='Index', ply2_axis_title='Spread'))
    eu_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_swaps_fig.json")))
    figs.append(table.figs_to_grid(eu_figs, columns=2))
    us_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>US</p>")
    us_figs.append(create_table(data=us_crude.loc[us_crude.index >= start_date, :], name='US Phys Crude',
                                  inline=True, width1=100, width2=80, chart_columns={tuple(us_crude.columns): "seasonal"}))
    us_swap = ts.read_csv(f"{outputs_csv_oil}\\us_swap_detail.csv", index_name='TRADE_DATE')
    existing_cols = us_swap.columns.to_list()
    us_swap = pd.concat([cl26_price.reindex(us_swap.index), us_swap], axis=1)
    us_swap.columns = [x.split(' ')[0] for x in cl26_price.columns] + existing_cols
    new_cols = [us_swap.columns[1]] + [us_swap.columns[0]] + us_swap.columns[2:].to_list()
    us_swap = us_swap[new_cols]
    us_swap.fillna(method="ffill", inplace=True)
    us_figs.append(create_table(data=us_swap.tail(100), name='US Crude Swap', inline=False, width1=100, width2=80,
                                  chart_columns={us_swap.columns[0]: us_swap.iloc[:, [1]], us_swap.columns[1]: 20,
                                                 tuple(us_swap.columns[2:]): us_swap.iloc[:, [1]]}))
    us_df = pd.concat([us_crude['Crd-P-US'].to_frame('US Phys Crude'), cl12_price], axis=1)
    us_df.dropna(inplace=True)
    us_df = us_df.loc[us_df.index > sdate, :]
    us_figs.append(chart.line_chart(df=us_df[['US Phys Crude']], data_ply2=us_df[[cl12_ticker]],
                                      title='US crude index vs CL frt sprd', secondary_y=True,
                                      y_axis_title='Index', ply2_axis_title='Spread'))
    us_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\us_swaps_fig.json")))
    figs.append(table.figs_to_grid(us_figs, columns=2))
    asia_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Asia</p>")
    figs.append('<br>')
    asia_figs.append(create_table(data=asia_crude.loc[asia_crude.index >= start_date, :], name='Asia Phys Crude',
                                 inline=True, width1=100, width2=80, chart_columns={tuple(asia_crude.columns): "seasonal"}))
    asia_swap = ts.read_csv(f"{outputs_csv_oil}\\asia_swap_detail.csv", index_name='TRADE_DATE')
    existing_cols = asia_swap.columns.to_list()
    asia_swap = pd.concat([dat26_price.reindex(asia_swap.index), asia_swap], axis=1)
    asia_swap.columns = [x.split(' ')[0] for x in dat26_price.columns] + existing_cols
    new_cols = [asia_swap.columns[1]] + [asia_swap.columns[0]] + asia_swap.columns[2:].to_list()
    asia_swap = asia_swap[new_cols]
    asia_figs.append(create_table(data=asia_swap.tail(100), name='Asia Crude Swap', inline=False, width1=100, width2=80,
                                  chart_columns={asia_swap.columns[0]: asia_swap.iloc[:, [1]], asia_swap.columns[1]: 20,
                                                 tuple(asia_swap.columns[2:]): asia_swap.iloc[:, [1]]}))
    asia_df = pd.concat([asia_crude['Crd-P-A'].to_frame('Asia Phys Crude'), dat12_price], axis=1)
    asia_df.dropna(inplace=True)
    asia_df = asia_df.loc[asia_df.index > sdate, :]
    asia_figs.append(chart.line_chart(df=asia_df[['Asia Phys Crude']], data_ply2=asia_df[[dat12_ticker]],
                                      title='Asia crude index vs DAT frt sprd', secondary_y=True,
                                      y_axis_title='Index', ply2_axis_title='Spread'))
    asia_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_swaps_fig.json")))
    figs.append(table.figs_to_grid(asia_figs, columns=2))
    figs.append('<br> Highlight colors: <br>')
    figs.append(_unrecovered('Crude 1478: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html([table.html_text("Physical Crude and Swaps Page", style="font-family:Calibri;", tag='h1')] + figs,
                   f"{html_path}\\oil\\physical_crude_and_swaps_page.html", task_name=report_name)


def arb():
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    co12_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="12")
    cl12_ticker = bbg.live_spread_ticker(active='CLA Comdty', spread="12")
    dat23_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="23")
    sdate = today() - BDay(260)
    edate = today() - BDay(1)
    co12_price = bbg.bdh([co12_ticker], ['PX_LAST'], sdate, edate)
    cl12_price = bbg.bdh([cl12_ticker], ['PX_LAST'], sdate, edate)
    dat23_price = bbg.bdh([dat23_ticker], ['PX_LAST'], sdate, edate)
    td3c = get_price_table("TDL", roll_day=20, months_ahead=1)
    td22 = get_price_table("WF2", roll_day=20, months_ahead=1)
    td25 = get_price_table("WF5", roll_day=20, months_ahead=1)
    td7 = get_price_table("WNC", roll_day=20, months_ahead=1)
    dated = get_price_table("PDB", roll_day=20, months_ahead=1)
    cl1_contract = bbg.live_contract(active='CLA Comdty', seq=0, roll="t3")
    cl1_price = bbg.bdh(cl1_contract['ticker'], ['PX_LAST'], sdate, edate)['PX_LAST']
    cl1_my = bbg.bref(cl1_contract['ticker'], "FUT_MONTH_YR").iloc[0, 0]
    cl1_my = cl1_my.split(" ")[0].capitalize() + "-" + str(2000 + int(cl1_my.split(" ")[1]))
    meh_ticker = f"WMEHM {cl1_contract['m']}{str(int(cl1_contract['y']))[-2:]} LINK Index"
    meh_price = bbg.bdh(meh_ticker, ['PX_LAST'], sdate, edate)
    meh_china = meh_price['PX_LAST'] + cl1_price + td22[cl1_my] / 7.64
    meh_eu = meh_price['PX_LAST'] + cl1_price + td25[cl1_my] / 7.64
    mars_ticker = f"PMRSM {cl1_contract['m']}{str(int(cl1_contract['y']))[-2:]} LINK Index"
    mars_china = bbg.bdh(mars_ticker, ['PX_LAST'], sdate, edate)['PX_LAST'] + cl1_price + td22[cl1_my] / 7.64
    cl2_contract = bbg.live_contract(active='CLA Comdty', seq=1, roll="t3")
    cl2_my = bbg.bref(cl2_contract['ticker'], "FUT_MONTH_YR").iloc[0, 0]
    cl2_my = cl2_my.split(" ")[0].capitalize() + "-" + str(2000 + int(cl2_my.split(" ")[1]))
    murban_ticker = f"MUC{cl2_contract['m']}{str(int(cl2_contract['y']))[-2:]} Comdty"
    murban_price = bbg.bdh(murban_ticker, ['PX_LAST'], sdate, edate)
    murban_china = murban_price.iloc[:, 0] + td3c[cl2_my] / 7.64
    dubai_ticker = f"DAT{cl2_contract['m']}{str(int(cl2_contract['y']))[-1:]} Comdty"
    dubai_price = bbg.bdh(dubai_ticker, ['PX_LAST'], sdate, edate)
    dubai_china = dubai_price.iloc[:, 0] + td3c[cl2_my] / 7.64
    brent_price = dated[cl2_my] + td7[cl2_my] / 7.64
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>MEH vs Brent</p>")
    figs.append('<br>')
    meh_brent = pd.concat([co12_price, meh_eu - brent_price], axis=1)
    meh_brent.columns = [co12_ticker.split(" ")[0], _unrecovered('Crude 1536: clipped MEH Dated label suffix', f'MEH-{cl1_my.split("-")[0]}/Dated-')]
    meh_brent.index.name = 'TRADE_DATE'
    meh_brent = meh_brent.loc[meh_brent.index >= sdate, :]
    meh_brent.fillna(method='ffill', inplace=True)
    figs.append(create_table(meh_brent, name='MEH Brent Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    meh_brent_fig = chart.line_chart(df=meh_brent[[meh_brent.columns[0]]], data_ply2=meh_brent[[meh_brent.columns[1]]],
                                     title='MEH/Dated vs Brent front spread', secondary_y=True,
                                     y_axis_title='Spread', ply2_axis_title='Arb')
    meh_brent_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\meh_brent_fig.json"))
    figs.append(meh_brent_fig)
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>MEH vs Murban</p>")
    figs.append('<br>')
    meh_murban = pd.concat([cl12_price, meh_china - murban_china], axis=1)
    meh_murban.fillna(method='ffill', inplace=True)
    meh_murban.columns = [cl12_ticker.split(" ")[0], _unrecovered('Crude 1557: clipped MEH Murban label suffix', f'MEH-{cl1_my.split("-")[0]}/Murban-')]
    meh_murban.index.name = 'TRADE_DATE'
    meh_murban = meh_murban.loc[meh_murban.index >= sdate, :]
    figs.append(create_table(meh_murban, name='MEH Murban Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    meh_murban_fig = chart.line_chart(df=meh_murban[[meh_murban.columns[0]]], data_ply2=meh_murban[[meh_murban.columns[1]]],
                                      title='MEH/Murban to China vs WTI front spread', secondary_y=True,
                                      y_axis_title='Spread', ply2_axis_title='Arb')
    meh_murban_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\meh_murban_fig.json"))
    figs.append(meh_murban_fig)
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>MARS vs Dubai</p>")
    figs.append('<br>')
    mars_dubai = pd.concat([dat23_price, mars_china - dubai_china], axis=1)
    mars_dubai.columns = [dat23_ticker.split(" ")[0], _unrecovered('Crude 1576: clipped MARS Dubai label suffix', f'MARS-{cl1_my.split("-")[0]}/Dubai-')]
    mars_dubai.index.name = 'TRADE_DATE'
    mars_dubai = mars_dubai.loc[mars_dubai.index >= sdate, :]
    mars_dubai.fillna(method='ffill', inplace=True)
    figs.append(create_table(mars_dubai, name='MARS Dubai Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    mars_dubai_fig = chart.line_chart(df=mars_dubai[[mars_dubai.columns[0]]], data_ply2=mars_dubai[[mars_dubai.columns[1]]],
                                      title='MARS/Dubai to China vs Dubai front spread', secondary_y=True,
                                      y_axis_title='Spread', ply2_axis_title='Arb')
    mars_dubai_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\mars_dubai_fig.json"))
    figs.append(mars_dubai_fig)
    figs.append('<br> Highlight colors: <br>')
    figs.append(_unrecovered('Crude 1594: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html([table.html_text("Crude Arb", style="font-family:Calibri;", tag='h1')] + figs,
                   f"{html_path}\\oil\\crude_arb.html")


def arb_roll():
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_unrecovered('Crude 1605: clipped crude arb wiki link', 'https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/2201550867/Crude+Arb'))
    sdate = today() - BDay(260)
    edate = today() - BDay(1)
    cl_contracts = pyg.get_data("contracts", active="CLA Comdty", item="fut_chain")
    co_contracts = pyg.get_data("contracts", active="COA Comdty", item="fut_chain")
    cl_contracts = cl_contracts.loc[(cl_contracts["t3"] >= sdate) & (cl_contracts["t3"] <= edate + _unrecovered('Crude 1611: clipped contract end offset'))]
    co_contracts = co_contracts.loc[(co_contracts["t3"] >= sdate) & (co_contracts["t3"] <= edate + _unrecovered('Crude 1612: clipped contract end offset'))]
    cl_contracts.reset_index(drop=True, inplace=True)
    co_contracts.reset_index(drop=True, inplace=True)
    meh_dtd_gen = pd.DataFrame()
    meh_eko_gen = pd.DataFrame()
    meh_murban_gen = pd.DataFrame()
    forties_murban_gen = pd.DataFrame()
    mars_dubai_gen = pd.DataFrame()
    co12_gen = pd.DataFrame()
    cl12_gen = pd.DataFrame()
    dat23_gen = pd.DataFrame()
    eko = pyg.get_data(db, ticker="PCRUEKO2 PLDP Index")
    forties = pyg.get_data(db, ticker="PCRUFRT2 Index")
    co12_ori = bbg.bdh("S:COCO 1-2 Comdty", ["PX_LAST"], sdate, edate)
    for idx, row in cl_contracts.iterrows():
        if row["last_t"] < edate:
            row1 = cl_contracts.loc[idx + 1, :]
            row2 = cl_contracts.loc[idx + 2, :]
            if idx == 0:
                contract_sdate = sdate
            else:
                contract_sdate = cl_contracts.loc[idx - 1, "t3"]
            contract_edate = row["t3"]
            cl1 = pyg.get_data("contracts_PX_LAST", active="CLA Comdty", m=row["m"], y=row["y"])
            meh = pyg.get_data("contracts_PX_LAST", active="WMEHM Index", m=row["m"], y=row["y"])
            mars = pyg.get_data("contracts_PX_LAST", active="PMRSM Index", m=row["m"], y=row["y"])
            dtd = pyg.get_data("contracts_PX_LAST", active="CDBSM Index", m=row1["m"], y=row1["y"])
            murban = pyg.get_data("contracts_PX_LAST", active="MUCA Comdty", m=row1["m"], y=row1["y"])
            dubai = pyg.get_data("contracts_PX_LAST", active="DATA Comdty", m=row1["m"], y=row1["y"])
            td3c = pyg.get_data("contracts_PX_LAST", active="ZHEA Comdty", m=row1["m"], y=row1["y"])
            td22 = pyg.get_data("contracts_PX_LAST", active="PTYA Comdty", m=row["m"], y=row["y"])
            td25 = pyg.get_data("contracts_PX_LAST", active="PUBA Comdty", m=row["m"], y=row["y"])
            td7 = pyg.get_data("contracts_PX_LAST", active="ATOA Comdty", m=row1["m"], y=row1["y"])
            cl12 = pyg.get_data("spreads_PX_LAST", active="CLA Comdty", m=row["m"], y=row["y"], far_m=row1["m"], far_y=row1["y"])
            dat23 = pyg.get_data("spreads_PX_LAST", active="DATA Comdty", m=row1["m"], y=row1["y"], far_m=row2["m"], far_y=row2["y"])
            cl1 = cl1.loc[(cl1.index > contract_sdate) & (cl1.index <= contract_edate), :]
            meh = meh.reindex(cl1.index)
            mars = mars.reindex(cl1.index)
            dtd = dtd.reindex(cl1.index)
            murban = murban.reindex(cl1.index)
            dubai = dubai.reindex(cl1.index)
            td3c = td3c.reindex(cl1.index)
            td22 = td22.reindex(cl1.index)
            td25 = td25.reindex(cl1.index)
            td7 = td7.reindex(cl1.index)
            cl12 = cl12.reindex(cl1.index)
            co12 = co12_ori.reindex(cl1.index)
            dat23 = dat23.reindex(cl1.index)
            eko_ = eko.copy().reindex(cl1.index)
            forties_ = forties.copy().reindex(cl1.index)
            meh_dtd = meh + cl1 + td25 / 7.64 - (dtd + td7 / 7.64)
            meh_dtd.fillna(method="ffill", inplace=True)
            meh_dtd_gen = pd.concat([meh_dtd_gen, meh_dtd], axis=0)
            meh_eko = meh + cl1 + td25 / 7.64 - (dtd + td7 / 7.64 + eko_)
            meh_eko.fillna(method="ffill", inplace=True)
            meh_eko_gen = pd.concat([meh_eko_gen, meh_eko], axis=0)
            meh_murban = meh + cl1 + td22 / 7.64 - (murban + td3c / 7.64)
            meh_murban.fillna(method="ffill", inplace=True)
            meh_murban_gen = pd.concat([meh_murban_gen, meh_murban], axis=0)
            forties_murban = (dtd + td7 / 7.64 + forties_) - (murban + td3c / 7.64)
            forties_murban.fillna(method="ffill", inplace=True)
            forties_murban_gen = pd.concat([forties_murban_gen, forties_murban], axis=0)
            mars_dubai = mars + cl1 + td22 / 7.64 - (dubai + td3c / 7.64)
            mars_dubai.fillna(method="ffill", inplace=True)
            mars_dubai_gen = pd.concat([mars_dubai_gen, mars_dubai], axis=0)
            cl12_gen = pd.concat([cl12_gen, cl12], axis=0)
            co12_gen = pd.concat([co12_gen, co12], axis=0)
            dat23_gen = pd.concat([dat23_gen, dat23], axis=0)
    co12_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="12")
    cl12_ticker = bbg.live_spread_ticker(active='CLA Comdty', spread="12")
    dat23_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="23")
    co12_price = bbg.bdh([co12_ticker], ['PX_LAST'], sdate, edate)
    cl12_price = bbg.bdh([cl12_ticker], ['PX_LAST'], sdate, edate)
    dat23_price = bbg.bdh([dat23_ticker], ['PX_LAST'], sdate, edate)
    td3c = get_price_table("TDL", roll_day=20, months_ahead=1)
    td22 = get_price_table("WF2", roll_day=20, months_ahead=1)
    td25 = get_price_table("WF5", roll_day=20, months_ahead=1)
    td7 = get_price_table("WNC", roll_day=20, months_ahead=1)
    dated = get_price_table("PDB", roll_day=20, months_ahead=1)
    cl1_contract = bbg.live_contract(active='CLA Comdty', seq=0, roll="t3")
    cl1_price = bbg.bdh(cl1_contract['ticker'], ['PX_LAST'], sdate, edate)['PX_LAST']
    cl1_my = bbg.bref(cl1_contract['ticker'], "FUT_MONTH_YR").iloc[0, 0]
    cl1_my = cl1_my.split(" ")[0].capitalize() + "-" + str(2000 + int(cl1_my.split(" ")[1]))
    meh_ticker = f"WMEHM {cl1_contract['m']}{str(int(cl1_contract['y']))[-2:]} LINK Index"
    meh_price = bbg.bdh(meh_ticker, ['PX_LAST'], sdate, edate)
    meh_china = meh_price['PX_LAST'] + cl1_price + td22[cl1_my] / 7.64
    meh_eu = meh_price['PX_LAST'] + cl1_price + td25[cl1_my] / 7.64
    mars_ticker = f"PMRSM {cl1_contract['m']}{str(int(cl1_contract['y']))[-2:]} LINK Index"
    mars_china = bbg.bdh(mars_ticker, ['PX_LAST'], sdate, edate)['PX_LAST'] + cl1_price + td22[cl1_my] / 7.64
    cl2_contract = bbg.live_contract(active='CLA Comdty', seq=1, roll="t3")
    cl2_my = bbg.bref(cl2_contract['ticker'], "FUT_MONTH_YR").iloc[0, 0]
    cl2_my = cl2_my.split(" ")[0].capitalize() + "-" + str(2000 + int(cl2_my.split(" ")[1]))
    murban_ticker = f"MUC{cl2_contract['m']}{str(int(cl2_contract['y']))[-2:]} Comdty"
    murban_price = bbg.bdh(murban_ticker, ['PX_LAST'], sdate, edate)
    murban_china = murban_price.iloc[:, 0] + td3c[cl2_my] / 7.64
    dubai_ticker = f"DAT{cl2_contract['m']}{str(int(cl2_contract['y']))[-1:]} Comdty"
    dubai_price = bbg.bdh(dubai_ticker, ['PX_LAST'], sdate, edate)
    dubai_china = dubai_price.iloc[:, 0] + td3c[cl2_my] / 7.64
    brent_price = dated[cl2_my] + td7[cl2_my] / 7.64
    eko_price = dated[cl2_my] + td7[cl2_my] / 7.64 + eko.iloc[:, 0]
    forties_china = dated[cl2_my] + td3c[cl2_my] / 7.64 + forties.iloc[:, 0]
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>MEH vs Brent</p>")
    figs.append('<br>')
    co12_gen = pd.concat([co12_gen, co12_price.loc[co12_price.index > co12_gen.index[-1]]], axis=0)
    meh_dtd_live = (meh_eu - brent_price).to_frame("PX_LAST")
    meh_eko_live = (meh_eu - eko_price).to_frame("PX_LAST")
    meh_dtd_gen = pd.concat([meh_dtd_gen, meh_dtd_live.loc[meh_dtd_live.index > meh_dtd_gen.index[-1]]], axis=0)
    meh_eko_gen = pd.concat([meh_eko_gen, meh_eko_live.loc[meh_eko_live.index > meh_eko_gen.index[-1]]], axis=0)
    meh_brent = pd.concat([co12_gen, meh_eko_gen, meh_dtd_gen], axis=1)
    meh_brent.columns = [co12_ticker.rpartition(" ")[0], 'MEH/EKO', _unrecovered('Crude 1743: clipped MEH Dated label suffix', f'MEH-{cl1_my.split("-")[0]}/Dated-')]
    meh_brent.index.name = 'TRADE_DATE'
    meh_brent = meh_brent.loc[meh_brent.index >= sdate, :]
    meh_brent.fillna(method='ffill', inplace=True)
    figs.append(create_table(meh_brent, name='MEH Brent Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    meh_brent_fig = chart.line_chart(df=meh_brent[[meh_brent.columns[0]]], data_ply2=meh_brent[[meh_brent.columns[1]]],
                                     title='MEH/EKO vs Brent front spread', secondary_y=True,
                                     y_axis_title='Spread', ply2_axis_title='Arb')
    meh_brent_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\meh_brent_fig.json"))
    meh_brent_fig2 = chart.line_chart(df=meh_brent[[meh_brent.columns[0]]], data_ply2=meh_brent[[meh_brent.columns[2]]],
                                      title='MEH/Dtd vs Brent front spread', secondary_y=True,
                                      y_axis_title='Spread', ply2_axis_title='Arb')
    meh_brent_fig2.write_json(convert_path_to_linux(f"{outputs_json_oil}\\meh_brent_fig2.json"))
    figs.append([meh_brent_fig, meh_brent_fig2])
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>MEH vs Murban</p>")
    figs.append('<br>')
    cl12_gen = pd.concat([cl12_gen, cl12_price.loc[cl12_price.index > cl12_gen.index[-1]]], axis=0)
    meh_murban_live = (meh_china - murban_china).to_frame("PX_LAST")
    meh_murban_gen = pd.concat([meh_murban_gen, meh_murban_live.loc[meh_murban_live.index > meh_murban_gen.index[-1]]], axis=0)
    meh_murban = pd.concat([cl12_gen, meh_murban_gen], axis=1)
    meh_murban.fillna(method='ffill', inplace=True)
    meh_murban.columns = [cl12_ticker.split(" ")[0], _unrecovered('Crude 1774: clipped MEH Murban label suffix', f'MEH-{cl1_my.split("-")[0]}/Murban-')]
    meh_murban.index.name = 'TRADE_DATE'
    meh_murban = meh_murban.loc[meh_murban.index >= sdate, :]
    figs.append(create_table(meh_murban, name='MEH Murban Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    meh_murban_fig = chart.line_chart(df=meh_murban[[meh_murban.columns[0]]], data_ply2=meh_murban[[meh_murban.columns[1]]],
                                      title='MEH/Murban to China vs WTI front spread', secondary_y=True,
                                      y_axis_title='Spread', ply2_axis_title='Arb')
    meh_murban_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\meh_murban_fig.json"))
    figs.append(meh_murban_fig)
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Forties vs Murban</p>")
    figs.append('<br>')
    co12_gen = pd.concat([co12_gen, co12_price.loc[co12_price.index > co12_gen.index[-1]]], axis=0)
    forties_murban_live = (forties_china - murban_china).to_frame("PX_LAST")
    forties_murban_gen = pd.concat([forties_murban_gen, forties_murban_live.loc[forties_murban_live.index > forties_murban_gen.index[-1]]], axis=0)
    forties_murban = pd.concat([co12_gen, forties_murban_gen], axis=1)
    forties_murban.fillna(method='ffill', inplace=True)
    forties_murban.columns = [co12_ticker.split(" ")[0], f'Forties-{cl2_my.split("-")[0]}/Murban-{cl2_my.split("-")[0]} to China']
    forties_murban.index.name = 'TRADE_DATE'
    forties_murban = forties_murban.loc[forties_murban.index >= sdate, :]
    figs.append(create_table(forties_murban, name='Forties Murban Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    forties_murban_fig = chart.line_chart(df=forties_murban[[forties_murban.columns[0]]], data_ply2=forties_murban[[forties_murban.columns[1]]],
                                          title='Forties/Murban to China vs Brent front spread', secondary_y=True,
                                          y_axis_title='Spread', ply2_axis_title='Arb')
    forties_murban_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\forties_murban_fig.json"))
    figs.append(forties_murban_fig)
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>MARS vs Dubai</p>")
    figs.append('<br>')
    dat23_gen = pd.concat([dat23_gen, dat23_price.loc[dat23_price.index > dat23_gen.index[-1]]], axis=0)
    mars_dubai_live = (mars_china - dubai_china).to_frame("PX_LAST")
    mars_dubai_gen = pd.concat([mars_dubai_gen, mars_dubai_live.loc[mars_dubai_live.index > mars_dubai_gen.index[-1]]], axis=0)
    mars_dubai = pd.concat([dat23_gen, mars_dubai_gen], axis=1)
    mars_dubai.columns = [dat23_ticker.split(" ")[0], _unrecovered('Crude 1821: clipped MARS Dubai label suffix', f'MARS-{cl1_my.split("-")[0]}/Dubai-')]
    mars_dubai.index.name = 'TRADE_DATE'
    mars_dubai = mars_dubai.loc[mars_dubai.index >= sdate, :]
    mars_dubai.fillna(method='ffill', inplace=True)
    figs.append(create_table(mars_dubai, name='MARS Dubai Arb', inline=False, width1=100, width2=120))
    figs.append('<br>')
    mars_dubai_fig = chart.line_chart(df=mars_dubai[[mars_dubai.columns[0]]], data_ply2=mars_dubai[[mars_dubai.columns[1]]],
                                      title='MARS/Dubai to China vs Dubai front spread', secondary_y=True,
                                      y_axis_title='Spread', ply2_axis_title='Arb')
    mars_dubai_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\mars_dubai_fig.json"))
    figs.append(mars_dubai_fig)
    figs.append('<br> Highlight colors: <br>')
    figs.append(_unrecovered('Crude 1839: clipped daily highlight description ending', 'Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd'))
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html([table.html_text("Crude Arb", style="font-family:Calibri;", tag='h1')] + figs,
                   f"{html_path}\\oil\\crude_arb.html")


def update():
    update_physical()
    update_swap()
    atlantic_basin()
    sour_index()
    update_physical_and_swap()
    arb_roll()


if __name__ == '__main__':
    update()
