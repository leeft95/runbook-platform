import pandas as pd
import numpy as np
import datetime as dt
import plotly as py
import sys
from pandas.tseries.offsets import BDay
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today
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
report_name = "Physical Gasoline and Swaps Page"
file_name = "physical_gasoline_swap"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text in physical_gasoline_swap.py, source lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 5, 20), timezone="Europe/London", task_name=report_name,
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


def weighted_index(df):
    """
    front contract - 50%
    second contract - 30%
    third contract - 10%
    fourth contract - 10%
    """
    return df.iloc[:, 0] * 0.5 + df.iloc[:, 1] * 0.3 + df.iloc[:, 2] * 0.1 + df.iloc[:, 3] * 0.1


def update_physical():
    xb12_ticker = bbg.live_spread_ticker('XBA Comdty', spread="12")
    sdate_chart = today() - BDay(260)
    edate_chart = today() - BDay(1)
    xb12_price = bbg.bdh([xb12_ticker], ['PX_LAST'], sdate_chart, edate_chart) * 0.42  # convert to $/bbl
    if xb12_price.columns == ['PX_LAST']:
        xb12_price.columns = [xb12_ticker]
    sdate = dt.datetime(2022, 1, 1)
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>Global Index = "
                "(EU Index + US Index + Asia Index) / 3</p>")
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU Gasoline</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>EU Index = "
                "EBOB cash * 0.4 + E10 cash * 0.3 + MED Diff * 0.2 + Nap cash * 0.1</p>")
    ebob_swap = bbg.bdh('FSNOM1 Index', ['FAIR_VALUE_SNAPSHOT_AT_1630'], sdate=dt.datetime(2010, 1, 1), edate=_missing_photo_text('136'))
    nap_swap = bbg.bdh('FSNNM1 Index', ['FAIR_VALUE_SNAPSHOT_AT_1630'], sdate=dt.datetime(2010, 1, 1), edate=_missing_photo_text('137'))
    barge = pyg.get_data(db, platts_ticker="AAQZV00")
    ebob_cash = barge.iloc[:, 0] - ebob_swap['FAIR_VALUE_SNAPSHOT_AT_1630'].reindex(barge.index)
    e10 = pyg.get_data(db, platts_ticker="AGEFA00")
    e10_diff = e10.iloc[:, 0] - barge.iloc[:, 0].reindex(e10.index)
    med = pyg.get_data(db, platts_ticker="AAWZA00")
    med_diff = med.iloc[:, 0] - barge.iloc[:, 0].reindex(med.index)
    nap = pyg.get_data(db, platts_ticker="PAAAL00")
    nap_cash = nap.iloc[:, 0] - nap_swap['FAIR_VALUE_SNAPSHOT_AT_1630'].reindex(nap.index)
    reformate = pyg.get_data(db, platts_ticker="AAXPM00")
    ref_diff = reformate.iloc[:, 0] - barge.iloc[:, 0].reindex(med.index)
    eu_index = ebob_cash * 0.4 + e10_diff * 0.3 + med_diff * 0.2 + nap_cash * 0.1
    aeo = get_price_table('AEO', num=5, months_ahead=2,
                          roll_day=pd.bdate_range(today() + relativedelta(day=1), today() + relativedelta(day=31))[-1].day)
    eu_price = aeo.iloc[:, 0] - aeo.iloc[:, 1]
    df_eu = pd.concat([eu_index, eu_price, ebob_cash, e10_diff, med_diff, nap_cash, ref_diff], axis=1)
    df_eu.columns = ['MOGAS-P-EU', f"EBOB {aeo.columns[0][:3]}-{aeo.columns[1][:3]}", 'EBOB Cash', 'E10', *_missing_photo_text('163', 'M')]
    df_eu.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\eu_physical_gasoline_detail.csv"))
    df_eu = df_eu.loc[df_eu.index >= sdate, :]
    figs.append(table.table_with_link(data=df_eu, name='EU Gasoline', folder=outputs_html_oil_link,
                                      inline=False, width1=100, width2=80))
    df_eu_chart = df_eu.loc[df_eu.index >= sdate_chart, :]
    df_eu_chart.dropna(inplace=True)
    asia_fig = chart.line_chart(df=df_eu_chart[[df_eu_chart.columns[0]]], data_ply2=df_eu_chart[[df_eu_chart.columns[1]]],
                                secondary_y=True, title='EU physical gasoline vs EBOB first spread',
                                y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(asia_fig)
    figs.append('<br>')
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_physical_gasoline_fig.json"))
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>US Gasoline</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>US Index = "
                "USGC pipe * 0.3 + NYH Barges * 0.4 + Group3 * 0.1 + Linden * 0.1 + Colonial Cycle * 0.1</p>")
    usgc = pyg.get_data(db, ticker="NAUG006C PLDP Index")
    nyh_barges = pyg.get_data(db, ticker="NAPN005C PLDP Index")
    group3 = pyg.get_data(db, ticker="NAUG00AE PLDP Index")
    linden = pyg.get_data(db, platts_ticker="AANYX40")
    cycle2 = pyg.get_data(db, platts_ticker="AAELD00")
    cycle3 = pyg.get_data(db, platts_ticker="AAELE00")
    colonial_cycle = cycle2.iloc[:, 0] - cycle3.iloc[:, 0].reindex(cycle2.index)
    us_index = usgc.iloc[:, 0] * 0.3 + nyh_barges.iloc[:, 0] * 0.4 + group3.iloc[:, 0] * 0.1 + colonial_cycle * 0.1 + linden.iloc[:, 0] * 0.1
    us_price = xb12_price.reindex(us_index.index, method="ffill")
    df_us = pd.concat([us_index, us_price, usgc, nyh_barges, group3, colonial_cycle, linden], axis=1)
    df_us.columns = ['MOGAS-P-US', xb12_ticker.split(' ')[0], 'RBOB USGC pipe', 'RBOB NYH Barges', *_missing_photo_text('206', 'Prem Gro'), 'Linden']
    df_us.fillna(method='ffill', inplace=True)
    df_us.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\us_physical_gasoline_detail.csv"))
    df_us = df_us.loc[df_us.index >= sdate, :]
    figs.append(table.table_with_link(data=df_us, name='US Gasoline', folder=outputs_html_oil_link,
                                      inline=False, width1=100, width2=80))
    df_us_chart = df_us.loc[df_us.index >= sdate_chart, :]
    df_us_chart.dropna(inplace=True)
    asia_fig = chart.line_chart(df=df_us_chart[[df_us_chart.columns[0]]], data_ply2=df_us_chart[[df_us_chart.columns[1]]],
                                secondary_y=True, title='US physical gasoline vs XB first spread',
                                y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(asia_fig)
    figs.append('<br>')
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\us_physical_gasoline_fig.json"))
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>East Gasoline</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>East Index = "
                "Sing gasoline * 0.4 + Sing Nap / 8.9 * 0.2 + Ron * 0.4</p>")
    sing_gasoline = pyg.get_data(db, platts_ticker="AAXER00")
    sing_nap = pyg.get_data(db, ticker="PASONMOP PLDP Index")
    ron92 = pyg.get_data(db, platts_ticker="PGAEY00")
    ron95 = pyg.get_data(db, platts_ticker="PGAEZ00")
    ron = ron95.iloc[:, 0] - ron92.iloc[:, 0]
    sing_index = sing_gasoline.iloc[:, 0] * 0.4 + sing_nap.iloc[:, 0] / 8.9 * 0.2 + ron * 0.4
    smt = get_price_table('SMT', num=5, months_ahead=2,
                          roll_day=pd.bdate_range(today() + relativedelta(day=1), today() + relativedelta(day=31))[-1].day)
    sing_price = smt.iloc[:, 0] - smt.iloc[:, 1]
    df_east = pd.concat([sing_index, sing_price, sing_gasoline, sing_nap, ron], axis=1)
    df_east.columns = ['MOGAS-P-A', f"Sing Mogas {smt.columns[0][:3]}-{smt.columns[1][:3]}", 'Sing Gasoline', *_missing_photo_text('253')]
    df_east.fillna(method='ffill', inplace=True)
    df_east.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\asia_physical_gasoline_detail.csv"))
    df_east = df_east.loc[df_east.index >= sdate, :]
    figs.append(table.table_with_link(data=df_east, name='East Gasoline', folder=outputs_html_oil_link,
                                      inline=False, width1=100, width2=80))
    df_east_chart = df_east.loc[df_east.index >= sdate_chart, :]
    df_east_chart.dropna(inplace=True)
    asia_fig = chart.line_chart(df=df_east_chart[[df_east_chart.columns[0]]], data_ply2=df_east_chart[[df_east_chart.columns[1]]],
                                secondary_y=True, title='Asia physical gasoline vs Sing first spread',
                                y_axis_title='Index', ply2_axis_title='Spread')
    figs.append(asia_fig)
    figs.append('<br>')
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_physical_gasoline_fig.json"))
    global_index = (df_eu["MOGAS-P-EU"] / 8.33 + df_us["MOGAS-P-US"] * 0.42 + df_east["MOGAS-P-A"]) / 3
    blend = (df_east.iloc[:, 1] + df_eu.iloc[:, 1] / 8.33 + us_price.iloc[:, 0] * 0.42) / 3  # convert to $/ [clipped]
    df_global = pd.concat([global_index, blend, df_eu["MOGAS-P-EU"] / 8.33, df_us["MOGAS-P-US"] * 0.42, df_east["MOGAS-P-A"]], axis=1)
    df_global.columns = ["MOGAS-P-Global", "Blend Gasoline Front Spread", "MOGAS-P-EU", "MOGAS-P-US", "MOGAS-P-A"]
    df_global.fillna(method="ffill", inplace=True)
    df_global.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_physical_gasoline_detail.csv"))
    figs.insert(3, table.table_with_link(data=df_global, name='Global Gasoline', folder=outputs_html_oil_link,
                                        inline=False, width1=100, width2=80))
    df_global = df_global.loc[df_global.index >= sdate_chart, :]
    df_global.dropna(inplace=True)
    global_fig = chart.line_chart(df=df_global[["MOGAS-P-Global"]], data_ply2=df_global[[df_global.columns[1]]],
                                  secondary_y=True, title='Global physical gasoline vs blend front spread',
                                  y_axis_title='Index', ply2_axis_title='Spread', width=750, height=500)
    global_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    figs.insert(4, global_fig)
    figs.append('<br>')
    global_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoline_fig.json"))
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Physical Gasoline Page", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\physical_gasoline_page.html", task_name=report_name)


def update_swap():
    xb26_ticker = bbg.live_spread_ticker('XBA Comdty', spread="26")
    sdate_chart = today() - BDay(260)
    edate_chart = today() - BDay(1)
    xb26_price = bbg.bdh([xb26_ticker], ['PX_LAST'], sdate_chart, edate_chart)
    roll_day = pd.bdate_range(today() + relativedelta(day=1), today() + relativedelta(day=31))[-1].day
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_missing_photo_text('339', "<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Gasoline"))
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>Gasoline Index = "
                "East Index * 0.2 + West Index * 0.8</p>")
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>West</p>")
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>West Index = "
                "TA Arb Rin adj * 0.3 + EBOB * 0.4 + Naphtha * 0.2 + Gas/Nap * 0.2</p>")
    gdo = get_price_table('GDO', roll_day=roll_day)
    aeo = get_price_table('AEO', num=6, roll_day=roll_day)
    wnu = get_price_table('WNU', roll_day=roll_day)
    teu = get_price_table('TEU', roll_day=roll_day)
    nec = get_price_table('NEC', num=5, roll_day=roll_day)
    rvo = get_price_table('RVO', roll_day=roll_day)
    aeo_sprd = get_spread(aeo).iloc[:, :4]
    aeo_sprd1 = aeo.iloc[:, 1] - aeo.iloc[:, 5]
    nec_sprd = get_spread(nec)
    ta_arb_rin = gdo - rvo * 100
    west_index_1 = ta_arb_rin * 0.3 + aeo_sprd * 0.4 + nec_sprd * 0.2 + teu * 0.1
    west_summary = pd.concat([weighted_index(west_index_1), aeo_sprd1.reindex(west_index_1.index), weighted_index(gdo),
                              weighted_index(aeo_sprd), weighted_index(wnu), weighted_index(teu), weighted_index(nec_sprd),
                              weighted_index(rvo), weighted_index(ta_arb_rin)], axis=1)
    west_summary.columns = ['MOGAS-S-EU', f"EBOB {aeo.columns[1][:3]}-{aeo.columns[5][:3]}", 'TA Arb', 'EBOB',
                            'TC2 $/mt', 'Gas/Nap', 'Naphtha', 'RVO Arb', 'TA Arb Rin adj']
    west_summary.fillna(method="ffill", inplace=True)
    west_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\eu_gasoline_swap_detail.csv"))
    existing_cols = west_index_1.columns.to_list()
    west_index = pd.concat([aeo_sprd1.reindex(west_index_1.index), west_index_1], axis=1)
    west_index.columns = [f"EBOB {aeo.columns[1][:3]}-{aeo.columns[5][:3]}"] + existing_cols
    west_index.fillna(method="ffill", inplace=True)
    figs.append(table.table_with_link(data=west_index, name='Gasoline West Index', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('378'), width1=100, width2=80))
    eu_index_chart = west_summary.iloc[:, :2]
    eu_index_chart.dropna(inplace=True)
    eu_index_chart = eu_index_chart.loc[eu_index_chart.index >= sdate_chart, :]
    eu_fig = chart.line_chart(df=eu_index_chart[[eu_index_chart.columns[0]]], data_ply2=eu_index_chart[[eu_index_chart.columns[1]]],
                              secondary_y=True, title='West index vs EBOB 2-6 spread', y_axis_title='Index', ply2_axis_title='Spread')
    eu_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_gasoline_swaps_fig.json"))
    figs.append(eu_fig)
    figs.append('<br>')
    figs.append(table.table_with_link(data=gdo, name='TA Arb', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=aeo_sprd, name='EBOB', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=wnu, name='TC2 $/mt', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=teu, name='Gas/Nap', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    figs.append('<br>')
    figs.append(table.table_with_link(data=nec_sprd, name='Naphtha', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=rvo, name='RVO Arb', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=ta_arb_rin, name='TA Arb Rin adj', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('411'), width1=100, width2=80))
    figs.append('<br>')
    figs.append(_missing_photo_text('416', "<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Gasoli"))
    figs.append("<p style='font-size: 16px; text-align:left; font-family:Calibri'>East Index = East/West Gasoline * 0.1 + "
                "Singapore Gasoline swaps * 0.4 + RON spread * 0.3 + MOPJ Naphtha * 0.1 + Pro/Nap East * 0.1</p>")
    gdk = get_price_table('GDK', roll_day=roll_day)
    smt = get_price_table('SMT', num=6, roll_day=roll_day)
    smd = get_price_table('SMD', roll_day=roll_day)
    joe = get_price_table('JOE', roll_day=roll_day)
    njc = get_price_table('NJC', num=5, roll_day=roll_day)
    arr = get_price_table('ARR', roll_day=roll_day)
    smt_sprd = get_spread(smt).iloc[:, :4]
    smt_sprd1 = smt.iloc[:, 1] - smt.iloc[:, 5]
    njc_sprd = get_spread(njc)
    east_index_1 = gdk * 0.1 + smt_sprd * 0.4 + smd * 0.3 + njc_sprd * 0.1 + arr * 0.1
    east_summary = pd.concat([weighted_index(east_index_1), smt_sprd1.reindex(east_index_1.index), weighted_index(gdk),
                              weighted_index(smt_sprd), weighted_index(smd), weighted_index(joe),
                              weighted_index(njc_sprd), weighted_index(arr)], axis=1)
    east_summary.columns = ['MOGAS-S-A', f"Sing Mogas {smt.columns[1][:3]}-{smt.columns[5][:3]}", 'East/West Gasoline',
                            'Singapore Gasoline swaps', 'RON spread', 'East/West Naphtha', 'MOPJ Naphtha', 'Pro/Nap East']
    east_summary.fillna(method="ffill", inplace=True)
    east_summary.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\asia_gasoline_swap_detail.csv"))
    existing_cols = east_index_1.columns.to_list()
    east_index = pd.concat([smt_sprd1.reindex(east_index_1.index), east_index_1], axis=1)
    east_index.columns = [f"Sing Mogas {smt.columns[1][:3]}-{smt.columns[5][:3]}"] + existing_cols
    east_index.fillna(method="ffill", inplace=True)
    figs.append(table.table_with_link(data=east_index, name='Gasoline East Index', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('449'), width1=100, width2=80))
    asia_index_chart = east_summary.iloc[:, :2]
    asia_index_chart.dropna(inplace=True)
    asia_fig = chart.line_chart(df=asia_index_chart.loc[asia_index_chart.index >= sdate_chart, [asia_index_chart.columns[0]]],
                                data_ply2=asia_index_chart.loc[asia_index_chart.index >= sdate_chart, [asia_index_chart.columns[1]]],
                                secondary_y=True, title='East index vs Sing Mogas 2-6 spread', y_axis_title='Index', ply2_axis_title='Spread')
    asia_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_gasoline_swaps_fig.json"))
    figs.append(asia_fig)
    figs.append('<br>')
    figs.append(table.table_with_link(data=gdk, name='East/West Gasoline', folder=outputs_html_oil_link,
                                      inline=_missing_photo_text('468'), width1=100, width2=80))
    figs.append(table.table_with_link(data=smt_sprd, name='Singapore Gasoline swaps', folder=outputs_html_oil_link,
                                      width1=100, width2=80, **_missing_photo_text('471')))
    figs.append(table.table_with_link(data=smd, name='RON spread', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    figs.append('<br>')
    figs.append(table.table_with_link(data=joe, name='East/West Naphtha', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=njc_sprd, name='MOPJ Naphtha', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs.append(table.table_with_link(data=arr, name='Pro/Nap East', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    figs.append('<br>')
    global_index = east_index_1 * 0.2 + west_index_1 / 8.33 * 0.8
    blend = (east_summary.iloc[:, 1] + west_summary.iloc[:, 1] / 8.33) / 2  # convert to $/bbl
    existing_cols = global_index.columns.to_list()
    global_index_ = pd.concat([blend.reindex(global_index.index), global_index], axis=1)
    global_index_.columns = ["Blend 2-6 Gasoline Spread"] + existing_cols
    global_index_.fillna(method="ffill", inplace=True)
    figs.insert(3, table.table_with_link(data=global_index_, name='Gasoline Index', folder=outputs_html_oil_link,
                                        inline=False, width1=100, width2=80))
    global_index_chart = pd.concat([weighted_index(global_index), blend], axis=1)
    global_index_chart.columns = ['MOGAS-S-Global', "Blend Gasoline 2-6 Spread"]
    global_index_chart.dropna(inplace=True)
    global_fig = chart.line_chart(df=global_index_chart.loc[global_index_chart.index >= sdate_chart, [global_index_chart.columns[0]]],
                                  data_ply2=global_index_chart.loc[global_index_chart.index >= sdate_chart, [global_index_chart.columns[1]]],
                                  secondary_y=True, title='Global swap index vs blend 2-6 spread',
                                  y_axis_title='Index', ply2_axis_title='Spread', width=750, height=500)
    global_fig.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_gasoline_swaps_fig.json"))
    figs.insert(4, global_fig)
    figs.append('<br>')
    global_index_chart = pd.concat([global_index_chart, west_summary[["MOGAS-S-EU"]] / 8.33, east_summary[["MOGAS-S-A"]]], axis=1)
    global_index_chart.fillna(method="ffill", inplace=True)
    global_index_chart.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_gasoline_swap_detail.csv"))
    figs_crack = []
    figs_crack.append("<div style='font-family:Calibri;' >")
    figs_crack.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU Cracks vs Brent</p>")
    tep = get_price_table('TEP', roll_day=roll_day)
    eob = get_price_table('EOB', roll_day=roll_day)
    jnb = get_price_table('JNB', roll_day=roll_day)
    teo = get_price_table('TEO', roll_day=roll_day)
    nob = get_price_table('NOB', roll_day=roll_day)
    boa = get_price_table('BOA', roll_day=roll_day)
    figs_crack.append(table.table_with_link(data=tep, name='ULSD brg Crack', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs_crack.append(table.table_with_link(data=eob, name='EBOB Crack', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs_crack.append(table.table_with_link(data=jnb, name='Jet Crack', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    figs_crack.append('<br>')
    figs_crack.append(table.table_with_link(data=teo, name='0.5 Marine Crack', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs_crack.append(table.table_with_link(data=nob, name='Nap Crack', folder=outputs_html_oil_link, inline=True, width1=100, width2=80))
    figs_crack.append(table.table_with_link(data=boa, name='3.5 Crack', folder=outputs_html_oil_link, inline=False, width1=100, width2=80))
    figs_crack.append('<br>')
    figs_crack.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(figs_crack, f"{html_path}\\oil\\eu_swap_cracks.html", task_name=report_name)
    figs.append('<br>')
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text('Gasoline Swaps Page', style='font-family:Calibri;', tag='h1')] + figs,
                         f"{html_path}\\oil\\gasoline_swaps_page.html", task_name=report_name)


def update_physical_and_swap():
    sdate_chart = today() - BDay(260)
    eu_physical = ts.read_csv(f"{outputs_csv_oil}\\eu_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    us_physical = ts.read_csv(f"{outputs_csv_oil}\\us_physical_gasoline_detail.csv", index_name='date')
    asia_physical = ts.read_csv(f"{outputs_csv_oil}\\asia_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    global_physical = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    eu_swap = ts.read_csv(f"{outputs_csv_oil}\\eu_gasoline_swap_detail.csv", index_name='TRADE_DATE')
    asia_swap = ts.read_csv(f"{outputs_csv_oil}\\asia_gasoline_swap_detail.csv", index_name='TRADE_DATE')
    global_swap = ts.read_csv(f"{outputs_csv_oil}\\global_gasoline_swap_detail.csv", index_name='TRADE_DATE')
    figs = []
    table_row = []
    table_row1 = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append([_missing_photo_text('583', '<a href="https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774687323/Gasoil+pa'),
                 '&emsp;', u'<a href="{}\\oil\\physical_gasoline_page.html">Physical</a>'.format(html_path),
                 '&emsp;', u'<a href="{}\\oil\\gasoline_swaps_page.html">Swaps</a>'.format(html_path),
                 '&emsp;', u'<a href="{}\\oil\\global_freight_page.html">Freight</a>'.format(html_path)])
    figs.append('<br>')
    global_figs = []
    global_figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global</p>")
    table_row.append(table.table_with_link(data=global_physical, name='Global Phys Gasoline', folder=outputs_html_oil_link,
                                           inline=True, width1=100, width2=100))
    table_row1.append(table.table_with_link(data=global_swap, name='Global Gasoline Swap', folder=outputs_html_oil_link,
                                            inline=_missing_photo_text('600'), width1=100, width2=100))
    total_freight = ts.read_csv(f"{outputs_csv_oil}\\global_clean_freight.csv", index_name='TRADE_DATE')
    total_freight = total_freight.loc[total_freight.index >= sdate_chart, :]
    table_row.append(table.table_with_link(data=total_freight, name='Clean Freight BOM', folder=outputs_html_oil_link,
                                           inline=False, width1=100, width2=80))
    total_freight = ts.read_csv(f"{outputs_csv_oil}\\global_clean_freight_swap.csv", index_name='TRADE_DATE')
    total_freight = total_freight.loc[total_freight.index >= sdate_chart, :]
    table_row1.append(table.table_with_link(data=total_freight, name='Clean Freight Swap', folder=outputs_html_oil_link,
                                            inline=False, width1=100, width2=80))
    fig_charts = [py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoline_fig.json")),
                  py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_clean_freight_fig.json"))]
    fig_charts1 = [py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_gasoline_swaps_fig.json")),
                   py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\clean_freight_swap_fig.json"))]
    figs.append(table.figs_to_grid(table_row + fig_charts, columns=2))
    figs.append(table.figs_to_grid(table_row1 + fig_charts1, columns=2))
    figs.append('</div>')
    eu_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>EU</p>")
    eu_figs.append(table.table_with_link(data=eu_physical, name='EU Phys Gasoline', folder=outputs_html_oil_link,
                                        inline=_missing_photo_text('644'), width1=100, width2=80))
    eu_figs.append(table.table_with_link(data=eu_swap, name='EU Gasoline Swap', folder=outputs_html_oil_link,
                                        width1=100, width2=80, **_missing_photo_text('646')))
    eu_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_physical_gasoline_fig.json")))
    eu_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\eu_gasoline_swaps_fig.json")))
    figs.append(table.figs_to_grid(eu_figs, columns=2))
    us_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>US</p>")
    us_figs.append(table.table_with_link(data=us_physical, name='US Phys Gasoline', folder=outputs_html_oil_link,
                                        inline=_missing_photo_text('655'), width1=100, width2=80))
    us_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\us_physical_gasoline_fig.json")))
    figs.append(table.figs_to_grid(us_figs, columns=1))
    asia_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Asia</p>")
    asia_figs.append(table.table_with_link(data=asia_physical, name='Asia Phys Gasoline', folder=outputs_html_oil_link,
                                          inline=_missing_photo_text('664'), width1=100, width2=80))
    asia_figs.append(table.table_with_link(data=asia_swap, name='Asia Gasoline Swap', folder=outputs_html_oil_link,
                                          inline=_missing_photo_text('667'), width1=100, width2=80))
    asia_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_physical_gasoline_fig.json")))
    asia_figs.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\asia_gasoline_swaps_fig.json")))
    figs.append(table.figs_to_grid(asia_figs, columns=2))
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html([table.html_text('Physical Gasoline and Swaps Page', style='font-family:Calibri;', tag='h1')] + figs,
                  f"{html_path}\\oil\\physical_gasoline_and_swaps_page.html", task_name=report_name)


def update():
    update_physical()
    update_swap()
    update_physical_and_swap()


if __name__ == '__main__':
    update()
