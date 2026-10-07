import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import time
from dateutil.relativedelta import relativedelta
import ecm.cmds.data as dv
from ecm.cmds.vendor._ea import EAClient
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.time_series as ts
from ecm.cmds.cdr import today
from ecm.cmds.config import data_path, html_path, oil_group, csv_path, root_path
from ecm.cmds.utils import convert_path_to_linux
from ecm.atom.clients import retry
from tshistory.api import timeseries
TSA = timeseries('https://lo25.wagyu.elementcapital.corp/tsh/api')

send_to = oil_group
report_name = "US Crude Balance"
file_name = "us_crude_balance"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text in us_crude_balance.py, source lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY, start_datetime=dt.datetime(2023, 7, 1, 13, 35), timezone="Europe/London",
        task_name=report_name, task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True, python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


def ms_balance():
    file_path = latest_file(folder_path=convert_path_to_linux(f"{data_path}\\sell_side_consensus\\MS"))
    df = pd.read_excel(file_path, sheet_name="For machines - crude only", header=0)
    df.set_index("date", inplace=True)
    df.index = pd.to_datetime(df.index)
    return df


def platts_balance():
    file_path = latest_file(folder_path=convert_path_to_linux(f"{data_path}\\sell_side_consensus\\Platts"))
    df = pd.read_excel(file_path, sheet_name="ST crude balance")
    df.dropna(axis=1, how="all", inplace=True)
    df.dropna(axis=0, how="all", inplace=True)
    df.set_index(df.columns[0], inplace=True)
    df.dropna(axis=0, how="all", inplace=True)
    df = df.iloc[[1, 9], 3:].T
    df = df[df[df.columns[0]].apply(lambda x: isinstance(x, dt.datetime))]
    df.set_index(df.columns[0], inplace=True)
    return df.iloc[:, 0].sort_index()


def latest_file(folder_path, suffix="xlsx"):
    onlyfiles = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    str_dt = [s.split(".")[0][-8:] for s in onlyfiles]
    dts = [dt.datetime.strptime(date, "%Y%m%d") for date in str_dt]
    if sys.platform.startswith("win"):
        path = f"{folder_path}\\{onlyfiles[0].split('.')[0][:-8]}{max(dts).strftime('%Y%m%d')}.{suffix}"
    elif sys.platform.startswith("linux"):
        path = f"{folder_path}/{onlyfiles[0].split('.')[0][:-8]}{max(dts).strftime('%Y%m%d')}.{suffix}"
    else:
        raise NotImplementedError("Unsupported operating system")
    return path


def us_crude_bal_ea():
    line_items = {
        'Crude/cond field production': _missing_photo_text('92', 'energy_aspects.crude_oil.na.us.crude_production_including_field_co'),
        'Imports': _missing_photo_text('93', 'energy_aspects.crude_oil.na.us.crude_oil_imports_to_united_states_in_kb_d.kbbl_d.month'),
        'Adjustement': _missing_photo_text('94', 'energy_aspects.crude_oil.na.us.crude_oil_supply_demand_adjustment_in_united_states'),
        'SPR withdrawals': _missing_photo_text('95', 'energy_aspects.crude_oil.na.us.crude_oil_spr_release_in_kb_d.kbbl_d.monthly.fo'),
        'Refinery runs': _missing_photo_text('96', 'energy_aspects.crude_oil.na.us.refinery_runs_in_united_states_in_kb_d.kbbl_d.mon'),
        'EA CDU outages': _missing_photo_text('97', 'energy_aspects.oil_products.na.us.monthly_refinery_total_outages_for_cdu_units_'),
        'IIR CDU outages': 'iir.crude.united_states.total_outage.kbd.monthly',
        'Exports': _missing_photo_text('99', 'energy_aspects.crude_oil.na.us.crude_oil_exports_from_united_states_in_kb_d.kbbl_d.mon'),
        'Balance, kb/d': 'energy_aspects.crude_oil.na.us.implied_balance.kbbl_d.monthly.forecast',
        'Balance, kb': 'energy_aspects.crude_oil.na.us.implied_balance.kbbl.monthly.forecast',
        'Ending stocks': 'energy_aspects.crude_oil.na.us.implied_stocks.kbbl.monthly.forecast',
        'Cushing': 'energy_aspects.crude_oil.na.us.crude_oil_inventories_in_cushing_in_mb.mb.monthly.forecast',
        'PADD 3': 'energy_aspects.crude_oil.na.us.crude_oil_inventories_in_padd_3_in_mb.mbbl.monthly.forecast',
        'EIA last weekly stocks': 'eia.crude_oil.ending_stocks_ex_spr.united_states.kbd.weekly.ms',
    }
    data = pd.concat(map(TSA.get, line_items.values()), axis=1).rename(columns={v: k for k, v in line_items.items()})
    last_update = TSA.insertion_dates(line_items['Refinery runs'])[-1]
    data.to_csv(f"{csv_path}\\oil\\us_crude_balance.csv")
    data_by_yr = ts.data_by_year(data['Balance, kb/d'], freq="M")
    data_by_yr = data_by_yr.drop(2020, axis=1)
    resampled_data = data.copy()['2025':'2026']
    resampled_data.index = resampled_data.index.strftime('%b-%y')
    filtered_resampled_data = resampled_data.T.reset_index()
    filtered_resampled_data.rename(columns={"index": "EA"}, inplace=True)
    five_year = []
    for i in filtered_resampled_data.columns[1:]:
        date_ = dt.datetime.strptime(i, "%b-%y")
        five_year.append(data_by_yr.loc[date_.month - 1, date_.year - 6:date_.year - 1].mean())
    filtered_resampled_data.loc[8.5, :] = ['5y average balance, kb/d'] + five_year
    filtered_resampled_data.sort_index(inplace=True)
    filtered_resampled_data.reset_index(drop=True, inplace=True)
    cur_mon = pd.Period(pd.Timestamp.now(), freq='M').strftime('%b-%y')
    column_format = {
        'EA': {"right_border": True, 'text-align': 'left', 'width': '200px'},
        **{k: {'width': '60px'} for k in filtered_resampled_data.columns if k not in ('EA', cur_mon)},
        cur_mon: {"left_border": True, "right_border": True, 'width': '50px'},
    }
    format_row = {4: {'top_border': True, 'bold': True}, 8: {'top_border': True, 'bold': True}, 9: {'bottom_border': True}, 11: {'bottom_border': True, 'top_border': True, 'bold': True}}
    html_table = table.html_format(
        filtered_resampled_data, header=f'US crude balance (EA), kb/d',
        footer=f"Last updated {last_update:%d-%m %H:%m}", format_column=column_format,
        format_row=format_row, precision=0, show_date=True)
    return html_table


def global_crude_bal_ea():
    line_items = {
        'Crude/cond production': _missing_photo_text('149', 'energy_aspects.crude_oil.world.crude_oil_production_including_field_conde'),
        'OPEC crude': 'energy_aspects.crude_oil.opec.total_opec_crude_production_in_kb_d.kbbl_d.monthly.forecast',
        'Saudi Arabia': _missing_photo_text('151', 'energy_aspects.crude_oil.me.saudi_arabia.saudi_arabia_opec_crude_production_in_kb_d'),
        'Non-OPEC': _missing_photo_text('152', 'energy_aspects.crude_oil.non_opec.crude_production_including_field_condensate_in_total_'),
        'World refinery runs': _missing_photo_text('153', 'energy_aspects.crude_oil.world.refinery_runs_in_world_in_kb_d.kbbl_d.monthl'),
        'World burn': 'element.crude_oil.world.burn.kbd.monthly',
        'SPR builds': _missing_photo_text('155', 'energy_aspects.crude_oil.world.crude_oil_implied_spr_stock_change_in_world.kbd.monthl'),
        'Balance, kb': 'energy_aspects.crude_oil.world.implied_balance.kb.monthly.forecast',
        'Balance (Commercial)': 'energy_aspects.crude_oil.world.implied_balance.kbd.monthly.forecast',
        'Kpler builds, kb': 'kpler.crude_oil.world.balance.kb.monthly',
        'Kpler actual, kb/d': 'kpler.crude_oil.world.balance.kbd.monthly',
    }
    data = pd.concat(map(TSA.get, line_items.values()), axis=1).rename(columns={v: k for k, v in line_items.items()})
    last_update = TSA.insertion_dates(line_items['World refinery runs'])[-1]
    data.to_csv(f"{csv_path}\\oil\\global_crude_balance.csv")
    platts = platts_balance()
    data.insert(9, "Platts Balance", platts * 1000)
    data_by_yr = ts.data_by_year(data['Balance (Commercial)'], freq="M")
    data_by_yr = data_by_yr.drop(2020, axis=1)
    resampled_data = data.copy()['2025':'2026']
    resampled_data.index = resampled_data.index.strftime('%b-%y')
    filtered_resampled_data = resampled_data.T.reset_index()
    filtered_resampled_data.rename(columns={"index": "EA"}, inplace=True)
    five_year = []
    for i in filtered_resampled_data.columns[1:]:
        date_ = dt.datetime.strptime(i, "%b-%y")
        five_year.append(data_by_yr.loc[date_.month - 1, date_.year - 6:date_.year - 1].mean())
    filtered_resampled_data.loc[8.5, :] = ['5y average balance'] + five_year
    filtered_resampled_data.sort_index(inplace=True)
    filtered_resampled_data.reset_index(drop=True, inplace=True)
    cur_mon = pd.Period(pd.Timestamp.now(), freq='M').strftime('%b-%y')
    column_format = {
        'EA': {"right_border": True, 'text-align': 'left', 'width': '200px'},
        **{k: {'width': '60px'} for k in filtered_resampled_data.columns if k not in ('EA', cur_mon)},
        cur_mon: {"left_border": True, "right_border": True, 'width': '50px'},
    }
    format_row = {4: {'top_border': True, 'bold': True}, 8: {'top_border': True, 'bold': True}, 10: {'bottom_border': True}, 12: {'bottom_border': True, 'top_border': True, 'bold': True}}
    html_table = table.html_format(
        filtered_resampled_data, header=f'Global crude balance (EA), kb/d',
        footer=f"Last updated {last_update:%d-%m %H:%m}", format_column=column_format,
        format_row=format_row, precision=0, show_date=True)
    return html_table


def global_liquids_bal_ea():
    line_items = {
        'Liquid supply': _missing_photo_text('205', 'energy_aspects.liquids.world.liquids_production_in_world_in_kb_d.kbbl_d.monthly.f'),
        'OPEC crude': 'energy_aspects.crude_oil.opec.total_opec_crude_production_in_kb_d.kbbl_d.monthly.forecast',
        'Non-OPEC crude/cond': _missing_photo_text('207', 'energy_aspects.crude_oil.non_opec.crude_production_including_field_condensa'),
        'OPEC condensates/NGLs': _missing_photo_text('208', 'energy_aspects.ngls.opec.opec_ngl_production_includes_condensate_in_kb_d.'),
        'Non-OPEC NGL/Bio/Proc gains': _missing_photo_text('209', 'energy_aspects.liquids.non_opec.ngls_biofuels_and_processing_gains_'),
        'Liquid demand': 'energy_aspects.liquids.world.liquids_demand_in_world_in_kb_d.kbbl_d.monthly.forecast',
        'World burn': 'element.crude_oil.world.burn.kbd.monthly',
        'Liquid Balance': 'energy_aspects.liquids.world.implied_stock_change.kbbl_d.monthly.forecast',
        'SPR crude': _missing_photo_text('213', 'energy_aspects.crude_oil.world.crude_oil_implied_spr_stock_change_in_world.kbd.monthly'),
        'Commercial crude balance': 'energy_aspects.crude_oil.world.implied_balance.kbd.monthly.forecast',
        'Product balance (liquid - commercial crude - SPR)': _missing_photo_text('215', 'energy_aspects.products.world.implied_stock_ch'),
    }
    data = pd.concat(map(TSA.get, line_items.values()), axis=1).rename(columns={v: k for k, v in line_items.items()})
    last_update = TSA.insertion_dates(line_items['Liquid supply'])[-1]
    data.to_csv(f"{csv_path}\\oil\\global_liquids_balance.csv")
    data_by_yr = ts.data_by_year(data['Liquid Balance'], freq="M")
    data_by_yr = data_by_yr.drop(2020, axis=1)
    resampled_data = data.copy()['2025':'2026']
    resampled_data.index = resampled_data.index.strftime('%b-%y')
    filtered_resampled_data = resampled_data.T.reset_index()
    filtered_resampled_data.rename(columns={"index": "EA"}, inplace=True)
    five_year = []
    for i in filtered_resampled_data.columns[1:]:
        date_ = dt.datetime.strptime(i, "%b-%y")
        five_year.append(data_by_yr.loc[date_.month - 1, date_.year - 6:date_.year - 1].mean())
    filtered_resampled_data.loc[7.5, :] = ['5y average balance'] + five_year
    filtered_resampled_data.sort_index(inplace=True)
    filtered_resampled_data.reset_index(drop=True, inplace=True)
    cur_mon = pd.Period(pd.Timestamp.now(), freq='M').strftime('%b-%y')
    column_format = {
        'EA': {"right_border": True, 'text-align': 'left', 'width': '200px'},
        **{k: {'width': '60px'} for k in filtered_resampled_data.columns if k not in ('EA', cur_mon)},
        cur_mon: {"left_border": True, "right_border": True, 'width': '50px'},
    }
    format_row = {5: {'top_border': True}, 7: {'top_border': True, 'bold': True}, 8: {'bottom_border': True}, 11: {'bottom_border': True, 'top_border': True, 'bold': True}}
    html_table = table.html_format(
        filtered_resampled_data, header=f'Global liquids balance (EA), kb/d',
        footer=f"Last updated {last_update:%d-%m %H:%m}", format_column=column_format,
        format_row=format_row, precision=0, show_date=True)
    return html_table


def charts_ecm():
    line_items = {
        'Stocks': 'energy_aspects.crude_oil.na.us.implied_stocks.kbbl.monthly.forecast',
        'Refinery runs': _missing_photo_text('260', 'energy_aspects.crude_oil.na.us.refinery_runs_in_united_states_in_kb_d.kbbl_d.month'),
        'Exports': _missing_photo_text('261', 'energy_aspects.crude_oil.na.us.crude_oil_exports_from_united_states_in_kb_d.kbbl_d.month'),
        'Production': _missing_photo_text('262', 'energy_aspects.crude_oil.na.us.crude_production_including_field_condensate_in_united'),
        'Cushing': 'energy_aspects.crude_oil.na.us.crude_oil_inventories_in_cushing_in_mb.mb.monthly.forecast',
        'PADD 3 stocks': 'energy_aspects.crude_oil.na.us.crude_oil_inventories_in_padd_3_in_mb.mbbl.monthly.forecast',
    }
    figs1 = []
    figs2 = []
    for k, v in line_items.items():
        df = pd.DataFrame(TSA.history(line_items[k]))  # cols: vintage date, row: value date
        last_col = df.columns.max()
        figs1.append(chart.seasonal_chart(
            df=df.loc[df.index >= dt.datetime(2018, 1, 1), last_col].to_frame(last_col.strftime("%Y%m%d")),
            title=f"{k} seasonal chart", freq="MS", dash_from=today() + relativedelta(day=1), height=500, width=750))
        if k in ["Stocks", "Production", "Cushing", "PADD 3 stocks"]:
            df1 = df.resample("Q").last()
        else:
            df1 = df.resample("Q").mean()
        next_4q = df1.loc[df1.index > today() + relativedelta(months=2), :].iloc[:4, :].T
        next_4q.index = next_4q.index.normalize()
        next_4q = next_4q.loc[~next_4q.index.duplicated(keep='last'), :]
        if k in ["Stocks", "Production", "Cushing", "PADD 3 stocks"]:
            next_4q.columns = [x.strftime('%b-%y') for x in next_4q.columns]
        else:
            next_4q.columns = [x.to_period("Q").strftime('Q%q-%y') for x in next_4q.columns]
        next_4q.dropna(inplace=True)
        figs2.append(chart.line_chart(
            df=next_4q, title=f"{k} evolution chart",
            highlight_dict={**{k: {"mode": "lines+markers"} for k in next_4q.columns}}, height=500, width=750))
    return list(zip(figs1, figs2))


def us_crude_charts_ea():
    line_items = {
        'Stocks': '313',
        'Refinery runs': '1679',
        'Exports': '309',
        'Production': '6495',
    }
    figs1 = []
    figs2 = []
    for k, v in line_items.items():
        df = ea_tracker(dataset_id=v, start="2018-01-01", length=12, anchor_date=None)
        last_col = df.columns[0]
        figs1.append(chart.seasonal_chart(
            df=df.loc[df.index >= dt.datetime(2018, 1, 1), last_col].to_frame(last_col[:10]),
            title=f"{k} seasonal chart", freq="MS", dash_from=today() + relativedelta(day=1), height=500, width=750))
        if k in ['Stocks', 'Production']:
            df1 = df.resample("Q").last()
        else:
            df1 = df.resample("Q").mean()
        next_4q = df1.loc[df1.index >= today(), :].T
        next_4q.index = [dt.datetime.strptime(x[:10], "%Y-%m-%d") for x in next_4q.index]
        next_4q = next_4q.sort_index()
        next_4q = next_4q.loc[~next_4q.index.duplicated(keep='last'), :]
        if k in ['Stocks', 'Production']:
            next_4q.columns = [x.strftime('%b-%y') for x in next_4q.columns]
            next_4q = next_4q[["Mar-26", "Jun-26", "Sep-26", "Dec-26"]]
        else:
            next_4q.columns = [x.to_period("Q").strftime('Q%q-%y') for x in next_4q.columns]
            next_4q = next_4q[["Q1-26", "Q2-26", "Q3-26", "Q4-26"]]
        next_4q.dropna(inplace=True)
        figs2.append(chart.line_chart(
            df=next_4q, title=f"{k} evolution chart",
            highlight_dict={**{k: {"mode": "lines+markers"} for k in next_4q.columns}}, height=500, width=750))
    return list(zip(figs1, figs2))


def global_crude_charts_ea():
    line_items = {
        'Balance (with SPR)': '6470',
        'Balance (Commercial)': '11235',
        'Refinery runs': '5239',
        'Non OPEC Production': '1274',
        'OPEC Crude Production': '14',
    }
    figs1 = []
    figs2 = []
    kpler_crude_inv = ts.read_csv(f"{csv_path}\\oil\\global_crude_stocks.csv", index_name="Date")
    kpler_crude_inv = kpler_crude_inv["Total"] / 1000  # convert to mb
    client = EAClient()
    global_crude_bal = client.get_data(dataset_ids="6470", start_date=(kpler_crude_inv.index[-1] - relativedelta(months=1)).strftime("%Y-%m-%d"))
    global_crude_bal.set_index("Date", inplace=True)
    global_crude_bal.index = pd.to_datetime(global_crude_bal.index)
    global_crude_bal = global_crude_bal.iloc[:, 0]
    global_crude_bal = _missing_photo_text('381', "global_crude_bal.reindex(pd.date_range(global_crude_bal.index[0], global_crude_bal.in")
    global_crude_bal = global_crude_bal[global_crude_bal.index > kpler_crude_inv.index[-1]].cumsum() + kpler_crude_inv.iloc[-1]
    crude_inv = pd.concat([kpler_crude_inv, global_crude_bal], axis=0)
    crude_inv = crude_inv[crude_inv.index >= dt.datetime(2018, 1, 1)]
    fig = chart.seasonal_chart(df=crude_inv.to_frame("inv"), title='Kpler Global Crude Stocks + EA Forecast (mb)', freq="D", dash_from=today(), height=500, width=750)
    for k, v in line_items.items():
        df = ea_tracker(dataset_id=v, start="2018-01-01", length=12, anchor_date=None)
        last_col = df.columns[0]
        figs1.append(chart.seasonal_chart(
            df=df.loc[df.index >= dt.datetime(2018, 1, 1), last_col].to_frame(last_col[:10]),
            title=f"{k} seasonal chart", freq="MS", dash_from=today() + relativedelta(day=1), height=500, width=750))
        if k in ['Balance (with SPR)', 'Balance (Commercial)', 'Non OPEC Production', 'OPEC Crude Production']:
            df1 = df.resample("Q").last()
        else:
            df1 = df.resample("Q").mean()
        next_4q = df1.loc[df1.index >= today(), :].T
        next_4q.index = [dt.datetime.strptime(x[:10], "%Y-%m-%d") for x in next_4q.index]
        next_4q = next_4q.sort_index()
        next_4q = next_4q.loc[~next_4q.index.duplicated(keep='last'), :]
        if k in ['Balance (with SPR)', 'Balance (Commercial)', 'Non OPEC Production', 'OPEC Crude Production']:
            next_4q.columns = [x.strftime('%b-%y') for x in next_4q.columns]
            next_4q = next_4q[["Mar-26", "Jun-26", "Sep-26", "Dec-26"]]
        else:
            next_4q.columns = [x.to_period("Q").strftime('Q%q-%y') for x in next_4q.columns]
            next_4q = next_4q[["Q1-26", "Q2-26", "Q3-26", "Q4-26"]]
        next_4q.dropna(inplace=True)
        figs2.append(chart.line_chart(
            df=next_4q, title=f"{k} evolution chart",
            highlight_dict={**{k: {"mode": "lines+markers"} for k in next_4q.columns}}, height=500, width=750))
    return [fig] + list(zip(figs1, figs2))


def global_liquids_charts_ea():
    line_items = {
        'Liquid supply': '6769',
        'Non-OPEC crude/cond': '1274',
        'Liquid demand': '5214',
        'Liquid Balance': '6471',
        'SPR crude': '11233',
        'Commercial crude balance': '11235',
        'Product balance (liquid - commercial crude - SPR)': _missing_photo_text('444', 'energy_aspects.products.world.implied_stock_cha'),
    }
    figs1 = []
    figs2 = []
    kpler_liquids_inv = ts.read_csv(f"{csv_path}\\oil\\global_liquids_stocks.csv", index_name="Date")
    kpler_liquids_inv = kpler_liquids_inv["Land+Water"] / 1000  # convert to mb
    client = EAClient()
    global_liquids_bal = client.get_data(dataset_ids="6471", start_date=(kpler_liquids_inv.index[-1] - relativedelta(months=1)).strftime("%Y-%m-%d"))
    global_liquids_bal.set_index("Date", inplace=True)
    global_liquids_bal.index = pd.to_datetime(global_liquids_bal.index)
    global_liquids_bal = global_liquids_bal.iloc[:, 0]
    global_liquids_bal = _missing_photo_text('460', "global_liquids_bal.reindex(pd.date_range(global_liquids_bal.index[0], global_liquids_bal.in")
    global_liquids_bal = global_liquids_bal[global_liquids_bal.index > kpler_liquids_inv.index[-1]].cumsum() + kpler_liquids_inv.iloc[-1]
    liquids_inv = pd.concat([kpler_liquids_inv, global_liquids_bal], axis=0)
    liquids_inv = liquids_inv[liquids_inv.index >= dt.datetime(2018, 1, 1)]
    fig = chart.seasonal_chart(df=liquids_inv.to_frame("inv"), title='Global Lqiuds Stocks + EA Forecast (kb)', freq="D", dash_from=today(), height=500, width=750)
    save_dict = {}
    for k, v in line_items.items():
        if k not in ["Product balance (liquid - commercial crude - SPR)"]:
            df = ea_tracker(dataset_id=v, start="2018-01-01", length=12, anchor_date=None)
            last_col = df.columns[0]
            save_dict[k] = df
        else:
            df = save_dict['Liquid Balance'] - save_dict['SPR crude'] - save_dict['Commercial crude balance']
            last_col = df.columns[0]
        if k not in ['SPR crude', 'Commercial crude balance']:
            figs1.append(chart.seasonal_chart(
                df=df.loc[df.index >= dt.datetime(2018, 1, 1), last_col].to_frame(last_col[:10]),
                title=f"{k} seasonal chart", freq="MS", dash_from=today() + relativedelta(day=1), height=500, width=750))
            if k in ['Liquid Balance', 'SPR crude', 'Commercial crude balance', 'Product balance (liquid - commercial crude - SPR)']:
                df1 = df.resample("Q").last()
            else:
                df1 = df.resample("Q").mean()
            next_4q = df1.loc[df1.index >= today(), :].T
            next_4q.index = [dt.datetime.strptime(x[:10], "%Y-%m-%d") for x in next_4q.index]
            next_4q = next_4q.sort_index()
            next_4q = next_4q.loc[~next_4q.index.duplicated(keep='last'), :]
            if k in ['Liquid Balance', 'SPR crude', 'Commercial crude balance', 'Product balance (liquid - commercial crude - SPR)']:
                next_4q.columns = [x.strftime('%b-%y') for x in next_4q.columns]
                next_4q = next_4q[["Mar-26", "Jun-26", "Sep-26", "Dec-26"]]
            else:
                next_4q.columns = [x.to_period("Q").strftime('Q%q-%y') for x in next_4q.columns]
                next_4q = next_4q[["Q1-26", "Q2-26", "Q3-26", "Q4-26"]]
            next_4q.dropna(inplace=True)
            figs2.append(chart.line_chart(
                df=next_4q, title=f"{k} evolution chart",
                highlight_dict={**{k: {"mode": "lines+markers"} for k in next_4q.columns}}, height=500, width=750))
    return [fig] + list(zip(figs1, figs2))


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(10))
def ea_tracker(dataset_id, start, length=12, anchor_date=None):
    """
    Download historical releases
    :param dataset_id:
    :param start:
    :return:
    """
    if isinstance(dataset_id, list):
        dataset_id_ = ",".join(dataset_id)
        dataset_id_release = dataset_id[0]
    else:
        dataset_id_ = dataset_id_release = dataset_id
    release_dts = dv.ea_release_dates(dataset_id=dataset_id_release, monthly=False)
    convert_dts = [dt.datetime.strptime(x[:10], "%Y-%m-%d") for x in release_dts]
    for idx, i in enumerate(convert_dts):
        if idx > 1:
            if (i - convert_dts[idx - 1]).days < 3:
                if (convert_dts[idx - 1] - convert_dts[idx - 2]).days > 10:
                    convert_dts.remove(convert_dts[idx])
                    release_dts.remove(release_dts[idx])
                else:
                    convert_dts.remove(convert_dts[idx - 1])
                    release_dts.remove(release_dts[idx - 1])
    df = pd.DataFrame()
    for i in range(-1, -length - 1, -1):
        try:
            data = dv.energy_aspects(dataset_id=dataset_id_, start=start, release_date=release_dts[i])
        except Exception as e:
            if str(e) == "HTTP Error 417: Expectation Failed":
                raise Exception((f"Could not download dataset_id={dataset_id_} due to {e}"
                                 " sleeping and retrying in 1s"))
        if data.index.name != "Date":
            data.set_index("Date", inplace=True)
        data.index = pd.to_datetime(data.index)
        data = data.sum(axis=1).to_frame(release_dts[i])
        df = pd.concat([df, data], axis=1)
        df.dropna(axis=1, how="all", inplace=True)
    if anchor_date is not None:
        anchor = dv.energy_aspects(dataset_id=dataset_id_, start=start, release_date=f"{anchor_date}T23:55:00")
        anchor.set_index("Date", inplace=True)
        anchor.index = pd.to_datetime(anchor.index)
        anchor = anchor.sum(axis=1).to_frame("2025 Anchor")
        df = pd.concat([anchor, df], axis=1)
    return df


def update():
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(us_crude_bal_ea())
    figs.append('Data source for the following charts: EA')
    figs += us_crude_charts_ea()
    table.to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                  f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    figs_global = []
    figs_global.append("<div style='font-family:Calibri;' >")
    figs_global.append(global_crude_bal_ea())
    figs_global.append('Data source for the following charts: EA')
    figs_global += global_crude_charts_ea()
    table.to_html([table.html_text("Global Crude Balance", style="font-family:Calibri;", tag='h1')] + figs_global,
                  f"{html_path}\\oil\\global_crude_balance.html", task_name="US Crude Balance")
    figs_liquids = []
    figs_liquids.append("<div style='font-family:Calibri;' >")
    figs_liquids.append(global_liquids_bal_ea())
    figs_liquids.append('Data source for the following charts: EA')
    figs_liquids += global_liquids_charts_ea()
    table.to_html([table.html_text("Global Liquids Balance", style="font-family:Calibri;", tag='h1')] + figs_liquids,
                  f"{html_path}\\oil\\global_liquids_balance.html", task_name="US Crude Balance")


if __name__ == "__main__":
    update()
