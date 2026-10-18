import pandas as pd
import numpy as np
import datetime as dt
import plotly as py
import sys
from pandas.tseries.offsets import BDay
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today, month_str2int
from ecm.cmds.ticker import next_ticker
from ecm.cmds.cdr import month_int2str, month_str2int
import ecm.cmds.pyg as pyg
from dateutil.relativedelta import relativedelta
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from functools import partial
import ecm.cmds.bbg as bbg
from ecm.cmds.utils import convert_path_to_linux
from pyg_mongo import *
from ecm.cmds.config import url, root_path, html_path

db = partial(mongo_table, db="data", table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
outputs_json_oil = f"{root_path}\\outputs\\json\\oil"
outputs_html_oil_link = f"{root_path}\\outputs\\htmls\\oil\\links"
report_name = "Physical Gasoil and Swaps Page"
file_name = "physical_gasoil_swap"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text in physical_gasoil_swap.py, source lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 5, 10), timezone="Europe/London", task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'), background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


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


def get_price_table_bbg(ticker, start_month, start_year):
    gen_list = 'FGHJKMNQUVXZ'
    if ticker.split(" ")[0][-1] == "A":
        live_contract = f"{ticker.split('A Comdty')[0]}{gen_list[start_month - 1]}{str(start_year)[-1]} Comdty"
    else:
        live_contract = f"{ticker.split(' Comdty')[0]} {gen_list[start_month - 1]}{str(start_year)[-2:]} Comdty"
    ticker2 = next_ticker(live_contract, gen_list)
    ticker3 = next_ticker(ticker2, gen_list)
    ticker4 = next_ticker(ticker3, gen_list)
    ticker_list = [live_contract, ticker2, ticker3, ticker4]
    df = bbg.bdh(ticker_list, ['PX_LAST'], sdate=today() - dt.timedelta(days=182), edate=today() - _missing_photo_text('114', 'dt.timede'))
    if ticker in ["TC5FM Comdty"]:
        df.columns = [dt.datetime(2020 + int(x.split(' ')[1][-1]), month_str2int[x.split(' ')[1][-3]], 1).strftime('%b-%Y') for x in ticker_list]
    else:
        df.columns = [dt.datetime(2020 + int(x.split(' ')[0][-1]), month_str2int[x.split(' ')[0][-2]], 1).strftime('%b-%Y') for x in ticker_list]
    return df


def weighted_index(df):
    """
    front contract - 50%
    second contract - 30%
    third contract - 10%
    fourth contract - 10%
    """
    return df.iloc[:, 0] * 0.5 + df.iloc[:, 1] * 0.3 + df.iloc[:, 2] * 0.1 + df.iloc[:, 3] * 0.1


def eu_physical(eu_ticker, eu_price, sdate):
    flat_ticker = bbg.live_contract("QSA Comdty")["ticker"]
    qs1 = bbg.bdh(flat_ticker, ['PX_LAST'], sdate=sdate, edate=today())
    barge = pyg.get_data(db, platts_ticker="AAJUS00")
    barge_diff = barge.iloc[:, 0] - qs1['PX_LAST'].reindex(barge.index)
    cif = pyg.get_data(db, platts_ticker="AAVBG00")
    cif_diff = cif.iloc[:, 0] - qs1['PX_LAST'].reindex(cif.index)
    med = pyg.get_data(db, platts_ticker="AAWYZ00")
    med_diff = med.iloc[:, 0] - qs1['PX_LAST'].reindex(med.index)
    fifty = pyg.get_data(db, platts_ticker="AAUQC00")
    fifty_diff = fifty.iloc[:, 0] - qs1['PX_LAST'].reindex(fifty.index)
    jet = pyg.get_data(db, platts_ticker="PJAAU00")
    jet_diff = jet.iloc[:, 0] - qs1['PX_LAST'].reindex(jet.index)
    barge01 = pyg.get_data(db, platts_ticker="AAYWT00")
    barge01_diff = barge01.iloc[:, 0] - qs1['PX_LAST'].reindex(barge01.index)
    regrade = jet.iloc[:, 0] / 7.878 - cif.iloc[:, 0] / 7.45
    eu_index = cif_diff * 0.4 + med_diff * 0.3 + barge_diff * 0.3
    eu_price = eu_price.reindex(eu_index.index, method="ffill")
    df_eu = pd.concat([eu_index, eu_price, barge_diff, cif_diff, med_diff, fifty_diff, barge01_diff, jet_diff, regrade], axis=1)
    df_eu.columns = ['GO-P-EU', eu_ticker.split(' ')[0], '10ppm FOB ARA', '10ppm CIF NWE', '10ppm CIF Med', _missing_photo_text('163', '50ppm'),
                     '0.1 Barge', 'Jet Diff', 'NWE Regrade']
    df_eu.fillna(method="ffill", inplace=True)
    df_eu = df_eu.loc[df_eu.index >= sdate, :]
    df_eu.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\eu_physical_gasoil_detail.csv"))
    return df_eu


def us_physical(us_ticker, us_price, sdate):
    usgc = pyg.get_data(db, ticker="NAUG0074 PLDP Index")
    nyh_barges = pyg.get_data(db, ticker="NAPN006E PLDP Index")
    group3 = pyg.get_data(db, ticker="NAPI0006 Index")
    nyh_jet = pyg.get_data(db, platts_ticker="ADIGA00")
    us_index = usgc.iloc[:, 0] * 0.4 + nyh_barges.iloc[:, 0] * 0.5 + group3.iloc[:, 0] * 0.1  # + nyh_jet.iloc [clipped]
    us_price = us_price.reindex(us_index.index, method="ffill")
    df_us = pd.concat([us_index, us_price, usgc, nyh_barges, group3], axis=1)
    df_us.columns = ['GO-P-US', us_ticker.split(' ')[0], 'USGC pipe', 'NYH Barges', 'Group3']
    df_us.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\us_physical_gasoil_detail.csv"))
    df_us = df_us.loc[df_us.index >= sdate, :]
    return df_us


def asia_physical(sdate):
    sing_gasoil = pyg.get_data(db, ticker="PASOGOSM PLDP Index")
    sing_jet = pyg.get_data(db, platts_ticker="PJABF00")
    ppm10 = pyg.get_data(db, platts_ticker="AAOVC00")
    mopag = pyg.get_data(db, platts_ticker="AAIDU00")
    wci = pyg.get_data(db, platts_ticker="AAQWN00")
    regrade_sing = sing_jet.iloc[:, 0] - ppm10.iloc[:, 0]
    wci_diff = wci.iloc[:, 0] - ppm10.iloc[:, 0]
    sing_index = sing_gasoil.iloc[:, 0] * 0.7 + regrade_sing * 0.3  # + mopag.iloc[:, 0] * 0.2 + wci_diff * 0. [clipped]
    gst = get_price_table('GST', num=5, months_ahead=2,
                          roll_day=pd.bdate_range(today() + relativedelta(day=1), today() + relativedelta(day=31))[-1].day)
    gst_sprd = get_spread(gst)
    df_east = pd.concat([sing_index, gst_sprd.iloc[:, 0], sing_gasoil, regrade_sing], axis=1)
    df_east.columns = ['GO-P-A', f'Singapore Gasoil {gst_sprd.columns[0][:3]}-{gst_sprd.columns[1][:3]}', *_missing_photo_text('202', 'S')]
    df_east.fillna(method='ffill', inplace=True)
    df_east.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\asia_physical_gasoil_detail.csv"))
    df_east = df_east.loc[df_east.index >= sdate, :]
    return df_east


def update_physical():
    sdate = dt.datetime(2018, 1, 1)
    eu_ticker = bbg.live_spread_ticker('QSA Comdty', spread="12")
    us_ticker = bbg.live_spread_ticker('HOA Comdty', spread="12")
    sdate_chart = today() - BDay(260)
    edate_chart = today() - BDay(1)
    eu_price = bbg.bdh([eu_ticker], ['PX_LAST'], sdate_chart, edate_chart)
    if eu_price.columns == ['PX_LAST']:
        eu_price.columns = [eu_ticker]
    us_price = bbg.bdh([us_ticker], ['PX_LAST'], sdate_chart, edate_chart)
    if us_price.columns == ['PX_LAST']:
        us_price.columns = [us_ticker]
    figs = []
    df_eu = eu_physical(eu_ticker, eu_price, sdate)
    df_us = us_physical(us_ticker, us_price, sdate)
    df_east = asia_physical(sdate)
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>EU Index = "
                "CIF Diff * 0.4 + Med Diff * 0.3 + Barge Diff * 0.3</p>")
    seasonal_cols = list(df_eu.columns)
    seasonal_cols.pop(1)
    figs.append(table.table_with_link(data=df_eu, name='EU Gasoil', folder=outputs_html_oil_link,
                                      inline=False, width1=100, width2=80, drop_cols=[2020, 2022, 2023],
                                      chart_columns={tuple(seasonal_cols): "seasonal", df_eu.columns[1]: 20}))
    df_eu = pd.concat([df_eu, eu_price], axis=1)
    df_eu_chart = df_eu.copy()
    df_eu_chart = df_eu_chart.loc[df_eu_chart.index >= sdate_chart, :]
    df_eu_chart.dropna(inplace=True)
    eu_fig = chart.line_chart(df=df_eu_chart[['GO-P-EU']], data_ply2=df_eu_chart[[eu_ticker]], secondary_y=True,
                              title='EU gasoil index vs QS first spread', y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(eu_fig)
    figs.append('<br>')
    eu_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_physical_gasoil_fig.json"))
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>US</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>US Index = "
                "USGC pipe * 0.4 + NYH Barges * 0.5 + Group3 * 0.1</p>")
    seasonal_cols = list(df_us.columns)
    seasonal_cols.pop(1)
    figs.append(table.table_with_link(data=df_us, name='US Gasoil', folder=outputs_html_oil_link,
                                      inline=False, width1=100, width2=80, drop_cols=[2020, 2022, 2023],
                                      chart_columns={tuple(seasonal_cols): "seasonal", df_us.columns[1]: 20}))
    df_us = pd.concat([df_us, us_price], axis=1)
    df_us_chart = df_us.copy()
    df_us_chart = df_us_chart.loc[df_us_chart.index >= sdate_chart, :]
    df_us_chart.dropna(inplace=True)
    us_fig = chart.line_chart(df=df_us_chart[['GO-P-US']], data_ply2=df_us_chart[[us_ticker]], secondary_y=True,
                              title='US gasoil index vs HO first spread', y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(us_fig)
    figs.append('<br>')
    us_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\us_physical_gasoil_fig.json"))
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Asia</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>East Index = "
                "Sing Premium * 0.7 + Regrade * 0.3 </p>")
    seasonal_cols = list(df_east.columns)
    seasonal_cols.pop(1)
    figs.append(table.table_with_link(data=df_east, name='Asia Gasoil', folder=outputs_html_oil_link,
                                      inline=False, width1=100, width2=80, drop_cols=[2020, 2022, 2023],
                                      chart_columns={tuple(seasonal_cols): "seasonal", df_east.columns[1]: 20}))
    df_east_chart = df_east.copy()
    df_east_chart = df_east_chart.loc[df_east_chart.index >= sdate_chart, :]
    df_east_chart.dropna(inplace=True)
    asia_fig = chart.line_chart(df=df_east_chart[['GO-P-A']], data_ply2=df_east_chart[[df_east_chart.columns[1]]],
                                secondary_y=True, title='Asia gasoil index vs Singapore Gasoil Swaps',
                                y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(asia_fig)
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_physical_gasoil_fig.json"))
    figs.insert(1, "<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global</p>")
    figs.insert(2, "<p style='font-size: 16px; text-align:left; font-family:Calibri'>Global Index = "
                   "(EU Index + US Index + Asia Index) / 3</p>")
    figs.insert(3, "<p style='font-size: 16px; text-align:left; font-family:Calibri'>Blend front spread = "
                   "(Singapore Gasoil Swaps + ICE Gasoil/7.45 + HO*0.42) / 3</p>")
    global_index = (df_eu["GO-P-EU"] / 7.45 + df_us["GO-P-US"] * 0.42 + df_east["GO-P-A"]) / 3  # convert to [clipped]
    blend = (df_east.iloc[:, 1] + eu_price.iloc[:, 0] / 7.45 + us_price.iloc[:, 0] * 0.42) / 3  # convert to [clipped]
    df_global = pd.concat([global_index, blend, df_eu["GO-P-EU"] / 7.45, df_us["GO-P-US"] * 0.42, df_east["GO-P-A"]], axis=1)
    df_global.columns = ["GO-P-Global", "Blend Gasoil Front Spread", "GO-P-EU", "GO-P-US", "GO-P-A"]
    df_global.fillna(method="ffill", inplace=True)
    df_global.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_physical_gasoil_detail.csv"))
    figs.insert(4, table.table_with_link(data=df_global, name='Global Gasoil', folder=outputs_html_oil_link,
                                        inline=False, width1=100, width2=80, drop_cols=[2020, 2022, 2023]))
    df_global = df_global.loc[df_global.index >= sdate_chart, :]
    df_global.dropna(inplace=True)
    global_fig = chart.line_chart(df=df_global[["GO-P-Global"]], data_ply2=df_global[[df_global.columns[1]]],
                                  secondary_y=True, title='Global physical gasoil vs Blend first spread',
                                  y_axis_title='Index', ply2_axis_title='Spread $/bbl', width=750, height=500)
    global_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    figs.insert(5, global_fig)
    figs.append('<br>')
    global_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoil_fig.json"))
    figs.append('<br>')
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Physical Gasoil Page", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\physical_gasoil_page.html", task_name=report_name)


def update_swap():
    qs26_ticker = bbg.live_spread_ticker('QSA Comdty', spread="26")
    sdate_chart = today() - BDay(260)
    edate_chart = today() - BDay(1)
    qs26_price = bbg.bdh([qs26_ticker], ['PX_LAST'], sdate_chart, edate_chart)
    roll_day = pd.bdate_range(today() + relativedelta(day=1), today() + relativedelta(day=31))[-1].day
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global Swap Index</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>Global Index = "
                "Asia Index * 0.5 + Europe Index * 0.5</p>")
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU Swap</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>EU Index = "
                "10ppm CIF * 0.4 + 10ppm Med * 0.3 + 10ppm Barges * 0.3</p>")
    ulf = get_price_table('ULF', roll_day=roll_day)
    uli = get_price_table('ULI', roll_day=roll_day)
    ule = get_price_table('ULE', roll_day=roll_day)
    ulj = get_price_table('ULJ', roll_day=roll_day)
    eu_index = ulf * 0.4 + uli * 0.3 + ule * 0.3
    eu_summary = pd.concat([weighted_index(eu_index), qs26_price.reindex(eu_index.index), weighted_index(ule),
                            weighted_index(ulf), weighted_index(uli), weighted_index(ulj)], axis=1)
    eu_summary.columns = ['GO-S-EU', qs26_price.columns[0].split(' ')[0], 'FOB ARA', 'CIF NWE', 'CIF Med', 'Jet Diff']
    eu_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\eu_gasoil_swap_detail.csv"))
    existing_cols = eu_index.columns.to_list()
    eu_index_ = pd.concat([qs26_price.reindex(eu_index.index), eu_index], axis=1)
    eu_index_.columns = [x.split(' ')[0] for x in qs26_price.columns] + existing_cols
    figs.append(table.table_with_link(data=eu_index_, name='Gasoil Europe', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('436'), width1=100, width2=80))
    eu_index_chart = pd.concat([weighted_index(eu_index), qs26_price], axis=1)
    eu_index_chart.columns = ['GO-S-EU', qs26_price.columns[0]]
    eu_index_chart.dropna(inplace=True)
    eu_fig = chart.line_chart(df=eu_index_chart[[eu_index_chart.columns[0]]], data_ply2=eu_index_chart[[eu_index_chart.columns[1]]],
                              secondary_y=True, title='EU swap index vs QS 2-6 spread', y_axis_title='Index', ply2_axis_title='Spread')
    eu_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_gasoil_swaps_fig.json"))
    figs.append(eu_fig)
    figs.append('<br>')
    figs.append(table.table_with_link(data=ulf, name='10ppm CIF', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=uli, name='10ppm Med', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=ule, name='10ppm Barges', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=ulj, name='Jet Diff', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    figs.append('<br>')
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Asia Swap</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>Asia Index = "
                "East/West Arb / 7.45 * 0.5 + Singapore Gasoil swaps * 0.5</p>")
    bap = get_price_table('BAP', roll_day=roll_day)
    gst = get_price_table('GST', num=6, roll_day=roll_day)
    baq = get_price_table('BAQ', roll_day=roll_day)
    gst_sprd = get_spread(gst).iloc[:, :4]
    gst_sprd1 = gst.iloc[:, 1] - gst.iloc[:, 5]
    btw = get_price_table('WMJ', roll_day=roll_day)
    ew_arb = bap + btw.reindex(bap.index, method='ffill')
    east_index = ew_arb / 7.45 * 0.5 + gst_sprd * 0.5
    asia_summary = pd.concat([weighted_index(east_index), gst_sprd1, weighted_index(bap), weighted_index(btw),
                              weighted_index(ew_arb), weighted_index(baq)], axis=1)
    asia_summary.columns = ['GO-S-A', f'Singapore Gasoil {gst.columns[1][:3]}-{gst.columns[5][:3]}',
                             *_missing_photo_text('483', 'East/W'), 'East/West Arb', 'Regrade']
    asia_summary.fillna(method="ffill", inplace=True)
    asia_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\asia_gasoil_swap_detail.csv"))
    figs.append(table.table_with_link(data=east_index, name='Asia Index', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('488'), width1=100, width2=80))
    asia_index_chart = asia_summary.iloc[:, :2]
    asia_index_chart.dropna(inplace=True)
    asia_fig = chart.line_chart(df=asia_index_chart.loc[asia_index_chart.index >= sdate_chart, [asia_index_chart.columns[0]]],
                                data_ply2=asia_index_chart.loc[asia_index_chart.index >= sdate_chart, [asia_index_chart.columns[1]]],
                                secondary_y=True, title='Asia swap index', y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(asia_fig)
    figs.append('<br>')
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_gasoil_swaps_fig.json"))
    figs.append(table.table_with_link(data=bap, name='East/West Gasoil', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=gst_sprd, name='Singapore Gasoil swaps', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('508'), width1=100, width2=80))
    figs.append(table.table_with_link(data=btw, name='Freight Middle East to Japan', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('511'), width1=100, width2=80))
    figs.append('<br>')
    figs.append(table.table_with_link(data=ew_arb, name='East/West Arb', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=baq, name='Regrade', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    gasoil_index = east_index * 0.5 + eu_index / 7.45 * 0.5
    figs.insert(3, table.table_with_link(data=gasoil_index, name='Gasoil Index', folder=outputs_html_oil_link,
                                        inline=False, width1=100, width2=80))
    blend = (asia_summary.iloc[:, 1] + qs26_price.iloc[:, 0] / 7.45) / 2  # convert to $/bbl
    global_index_chart = pd.concat([weighted_index(gasoil_index), blend], axis=1)
    global_index_chart.columns = ['GO-S-Global', "Blend Gasoil 2-6 Spread"]
    global_index_chart.dropna(inplace=True)
    global_fig = chart.line_chart(df=global_index_chart[[global_index_chart.columns[0]]],
                                  data_ply2=global_index_chart[[global_index_chart.columns[1]]], secondary_y=True,
                                  title='Global swap index vs Blend 2-6 spread', y_axis_title='Index',
                                  ply2_axis_title='Spread $/bbl', width=750, height=500)
    global_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    global_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_gasoil_swaps_fig.json"))
    figs.insert(4, global_fig)
    figs.append('<br>')
    global_index_chart = pd.concat([global_index_chart, eu_summary[["GO-S-EU"]] / 7.45, asia_summary[["GO-S-A"]]], axis=1)
    global_index_chart.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_gasoil_swap_detail.csv"))
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Gasoil Swaps Page", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\gasoil_swaps_page.html", task_name=report_name)


def update_physical_and_swap():
    sdate_chart = today() - BDay(260)
    eu_physical = ts.read_csv(f"{outputs_csv_oil}\\eu_physical_gasoil_detail.csv", index_name="date")
    us_physical = ts.read_csv(f"{outputs_csv_oil}\\us_physical_gasoil_detail.csv", index_name="date")
    asia_physical = ts.read_csv(f"{outputs_csv_oil}\\asia_physical_gasoil_detail.csv", index_name="Unnamed: 0")
    global_physical = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoil_detail.csv", index_name="Unnamed: 0")
    eu_swap = ts.read_csv(f"{outputs_csv_oil}\\eu_gasoil_swap_detail.csv", index_name="TRADE_DATE")
    asia_swap = ts.read_csv(f"{outputs_csv_oil}\\asia_gasoil_swap_detail.csv", index_name="TRADE_DATE")
    global_swap = ts.read_csv(f"{outputs_csv_oil}\\global_gasoil_swap_detail.csv", index_name="Unnamed: 0")
    figs = []
    table_row = []
    table_row1 = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append([_missing_photo_text('581', '<a href="https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774687323/Gasoil+pa'),
                 '&emsp;', u'<a href="{}\\oil\\physical_gasoil_page.html">Physical</a>'.format(html_path),
                 '&emsp;', u'<a href="{}\\oil\\gasoil_swaps_page.html">Swaps</a>'.format(html_path),
                 '&emsp;', u'<a href="{}\\oil\\global_freight_page.html">Freight</a>'.format(html_path)])
    figs.append('<br>')
    global_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global</p>")
    table_row.append(table.table_with_link(data=global_physical, name='Global Phys Gasoil', folder=outputs_html_oil_link,
                                          inline=True, width1=100, width2=80))
    total_freight = ts.read_csv(f"{outputs_csv_oil}\\global_clean_freight.csv", index_name='TRADE_DATE')
    total_freight = total_freight.loc[total_freight.index >= sdate_chart, :]
    table_row.append(table.table_with_link(data=total_freight, name='Clean Freight BOM', folder=outputs_html_oil_link,
                                          inline=False, width1=100, width2=80))
    table_row1.append(table.table_with_link(data=global_swap, name='Global Gasoil Swap', folder=outputs_html_oil_link,
                                           inline=_missing_photo_text('614'), width1=100, width2=80))
    total_freight_swap = ts.read_csv(f"{outputs_csv_oil}\\global_clean_freight_swap.csv", index_name='TRADE_DATE')
    total_freight_swap = total_freight_swap.loc[total_freight_swap.index >= sdate_chart, :]
    table_row1.append(table.table_with_link(data=total_freight_swap, name='Clean Freight Swap', folder=outputs_html_oil_link,
                                           inline=False, width1=100, width2=80))
    fig_charts = [py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoil_fig.json")),
                  py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_clean_freight_fig.json"))]
    fig_charts1 = [py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_gasoil_swaps_fig.json")),
                   py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\clean_freight_swap_fig.json"))]
    figs.append(table.figs_to_grid(table_row + fig_charts, columns=2))
    figs.append(table.figs_to_grid(table_row1 + fig_charts1, columns=2))
    figs.append("</div>")
    eu_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU</p>")
    eu_figs.append(table.table_with_link(data=eu_physical, name='EU Phys Gasoil', folder=outputs_html_oil_link,
                                        inline=_missing_photo_text('646'), width1=100, width2=80, drop_cols=[2020, 2022, 2023]))
    eu_figs.append(table.table_with_link(data=eu_swap, name='EU Gasoil Swap', folder=outputs_html_oil_link,
                                        width1=100, width2=80, drop_cols=[2020, 2022, 2023], **_missing_photo_text('648')))
    eu_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_physical_gasoil_fig.json")))
    eu_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_gasoil_swaps_fig.json")))
    figs.append(table.figs_to_grid(eu_figs, columns=2))
    us_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>US</p>")
    us_figs.append(table.table_with_link(data=us_physical, name='US Phys Gasoil', folder=outputs_html_oil_link,
                                        inline=_missing_photo_text('660'), width1=100, width2=80, drop_cols=[2020, 2022, 2023]))
    us_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\us_physical_gasoil_fig.json")))
    figs.append(table.figs_to_grid(us_figs, columns=1))
    asia_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Asia</p>")
    asia_figs.append(table.table_with_link(data=asia_physical, name='Asia Phys Gasoil', folder=outputs_html_oil_link,
                                          inline=_missing_photo_text('668'), width1=100, width2=80, drop_cols=[2020, 2022, 2023]))
    asia_figs.append(table.table_with_link(data=asia_swap, name='Asia Gasoil Swap', folder=outputs_html_oil_link,
                                          inline=_missing_photo_text('671'), width1=100, width2=80, drop_cols=[2020, 2022, 2023]))
    asia_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_physical_gasoil_fig.json")))
    asia_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_gasoil_swaps_fig.json")))
    figs.append(table.figs_to_grid(asia_figs, columns=2))
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html([table.html_text("Physical Gasoil and Swaps Page", style="font-family:Calibri;", tag='h1')] + figs,
                  f"{html_path}\\oil\\physical_gasoil_and_swaps_page.html", task_name=report_name)


def update():
    update_physical()
    update_swap()
    update_physical_and_swap()


if __name__ == "__main__":
    update()
