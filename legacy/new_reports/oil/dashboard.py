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
from pyg_mongo import *
from ecm.cmds.config import url, root_path, html_path, json_path
from pyg_base import dt as pygdt
from ecm.cmds.utils import convert_path_to_linux

db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
outputs_json_oil = f"{root_path}\\outputs\\json\\oil"
outputs_html_oil = f"{root_path}\\outputs\\htmls\\oil"
report_name = "Oil Dashboard"
file_name = "dashboard"  # without .py
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
        start_datetime=dt.datetime(2023, 7, 1, 5, 55), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def update():
    start_date = dt.datetime(2018, 1, 1)
    figs = []
    figs.append("<div style='font-family:Calibri; '>")

    liquids_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global Liquids</p>")
    figs.append([
        f'<a href="{outputs_html_oil}\\physical_oil_page.html">Link to Global Liquids Price</a><br>',
        '&emsp;',
        f'<a href="{outputs_html_oil}\\kpler_inventory.html">Link to Global Liquids Inventory</a><br>',
    ])
    liquids = ts.read_csv(f"{outputs_csv_oil}\\global_physical_liquids.csv", index_name='date')
    liquids_price_table = table.table_with_link(
        data=liquids.loc[liquids.index >= start_date, :], header="Liquids Price", name='Global Physical Liquids',
        folder=f"{outputs_html_oil}\\dashboard", inline=False, width1=100, width2=80,
        chart_columns={tuple(liquids.columns): "seasonal"})
    liquids_price_chart = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_liquids_fig.json"))
    global_liquids_table = pd.read_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_liquids_stocks_table.csv"))
    global_liquids_table.set_index("Unnamed: 0", inplace=True)
    format_column = {"0": {"width": "120px", "text-align": "left"},
                     "1": {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"], "right_border": True},
                     "2": {"width": "80px", "text-align": "center"},
                     "3": {"width": "80px", "text-align": "center"},
                     "4": {"width": "80px", "text-align": "center", "right_border": True},
                     "5": {"width": "80px", "text-align": "center"},
                     "6": {"width": "80px", "text-align": "center"},
                     "7": {"width": "80px", "text-align": "center"},
                     "8": {"width": "80px", "text-align": "center", "right_border": True},
                     "9": {"width": "80px", "text-align": "center"},
                     "10": {"width": "80px", "text-align": "center"},
                     "11": {"width": "80px", "text-align": "center"}}
    liquids_stock_table = table.html_format(
        df=global_liquids_table, header='Global Liquids Stocks Change (kb) - 20d Change on 5d MA', footer='Consensus is the latest average sell side quarterly SND', show_date=False,
        format_column=format_column, format_row={'2': {'bottom_border': True}, '3': {'bold': True}}, precision=0,
        hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    global_liquids = ts.read_csv(f"{outputs_csv_oil}\\global_liquids_stocks.csv", index_name="Date")
    df_2y = global_liquids.loc[pygdt("-2y"):, ["Land+Water"]]
    global_liquids_chart = pd.concat(
        [df_2y, (df_2y.rolling(10)).mean().loc[pygdt("-2y"):].iloc[:, 0].to_frame("10d ma")], axis=1)
    liquids_stock_chart = chart.line_chart(
        df=global_liquids_chart, title="Total Liquids Stocks - level", tickformat=None,
        highlight_dict={"Land+Water": {"color": "black"}, "10d ma": {"color": "red", "width": 2}})
    liquids_figs.extend([liquids_price_table, liquids_stock_table])
    liquids_figs.extend([liquids_price_chart, liquids_stock_chart])
    figs.append(table.figs_to_grid(liquids_figs, columns=2))

    crude_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global Crude</p>")
    figs.append([
        f'<a href="{outputs_html_oil}\\physical_crude_and_swaps_page.html">Link to global crude page</a><br>',
        '&emsp;',
        f'<a href="{outputs_html_oil}\\kpler_inventory.html">Link to Global Liquids Inventory</a><br>',
    ])
    crude = ts.read_csv(f"{outputs_csv_oil}\\global_physical_crude_detail.csv", index_name='date')
    crude_price_table = table.table_with_link(
        data=crude.loc[crude.index >= start_date, :], header="Crude Price", name='Global Physical Crude',
        folder=f"{outputs_html_oil}\\dashboard", inline=False, width1=100, width2=80,
        chart_columns={tuple(crude.columns): "seasonal"})
    crude_price_chart = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_crude_fig.json"))
    global_crude_table = pd.read_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_crude_stocks_table.csv"))
    global_crude_table.set_index("Unnamed: 0", inplace=True)
    crude_stock_table = table.html_format(
        df=global_crude_table, header='Crude Stocks Change (kb) - 20d Change on 5d MA', footer='Consensus is EA monthly forecast', show_date=True,
        format_column=format_column, format_row={'1': {'bottom_border': True}, '3': {'bold': True}}, precision=0,
        hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    global_crude = ts.read_csv(f"{outputs_csv_oil}\\global_crude_stocks.csv", index_name="Date")
    df_2y_crude = global_crude.loc[pygdt("-2y"):, ["Total"]]
    global_crude_chart = pd.concat(
        [df_2y_crude, (df_2y_crude.rolling(10)).mean().loc[pygdt("-2y"):].iloc[:, 0].to_frame("10d ma")], axis=1)
    crude_stock_chart = chart.line_chart(
        df=global_crude_chart, title="Total Crude Stocks - level", tickformat=None,
        highlight_dict={"Total": {"color": "black"}, "10d ma": {"color": "red", "width": 2}})
    total_freight = ts.read_csv(f"{outputs_csv_oil}\\global_freight.csv", index_name='TRADE_DATE')
    freight_table = table.table_with_link(
        data=total_freight.tail(364), header="Global Freight", name='Crude Freight',
        folder=f"{outputs_html_oil}\\dashboard", inline=False, width1=100, width2=120)
    freight_chart = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_freight_fig.json"))
    crude_figs.extend([crude_price_table, crude_stock_table, freight_table])
    crude_figs.extend([crude_price_chart, crude_stock_chart, freight_chart])
    figs.append(table.figs_to_grid(crude_figs, columns=3))

    gasoil_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global Gasoil</p>")
    figs.append([
        f'<a href="{outputs_html_oil}\\physical_gasoil_and_swaps_page.html">Link to global gasoil page</a><br>',
        '&emsp;',
        f'<a href="{outputs_html_oil}\\kpler_inventory.html">Link to Global Liquids Inventory</a><br>',
    ])
    gasoil = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoil_detail.csv", index_name='Unnamed: 0')
    gasoil_price_table = table.table_with_link(
        data=gasoil.loc[gasoil.index >= start_date, :], header="Gasoil Price", name='Global Physical Gasoil',
        folder=f"{outputs_html_oil}\\dashboard", inline=True, width1=100, width2=80,
        chart_columns={tuple(gasoil.columns): "seasonal"})
    gasoil_price_chart = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoil_fig.json"))
    global_gasoil_table = pd.read_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_product_by_type_table.csv"))
    global_gasoil_table.set_index("Unnamed: 0", inplace=True)
    global_gasoil_table = global_gasoil_table.iloc[[0], :]
    gasoil_stock_table = table.html_format(
        df=global_gasoil_table, header='Product Stocks Change by Type (kb) - Distillate', footer=None, show_date=False,
        format_column=format_column, format_row=None, precision=0,
        hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    global_gasoil = ts.read_csv(f"{outputs_csv_oil}\\global_product_by_type.csv", index_name="Date")
    df_2y_gasoil = global_gasoil.loc[pygdt("-2y"):, ["Distillate"]]
    global_gasoil_chart = pd.concat(
        [df_2y_gasoil, (df_2y_gasoil.rolling(10)).mean().loc[pygdt("-2y"):].iloc[:, 0].to_frame("10d ma")], axis=1)
    gasoil_stock_chart = chart.line_chart(
        df=global_gasoil_chart, title="Total Distillate Stocks - level", tickformat=None,
        highlight_dict={"Distillate": {"color": "black"}, "10d ma": {"color": "red", "width": 2}})
    clean_freight = ts.read_csv(f"{outputs_csv_oil}\\global_clean_freight.csv", index_name='TRADE_DATE')
    clean_freight_table = table.table_with_link(
        data=clean_freight.tail(364), header="Global Freight", name='Clean Freight',
        folder=f"{outputs_html_oil}\\dashboard", inline=False, width1=100, width2=120)
    clean_freight_chart = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_clean_freight_fig.json"))
    gasoil_figs.extend([gasoil_price_table, gasoil_stock_table, clean_freight_table])
    gasoil_figs.extend([gasoil_price_chart, gasoil_stock_chart, clean_freight_chart])
    figs.append(table.figs_to_grid(gasoil_figs, columns=3))

    gasoline_figs = []
    figs.append("<p style='font-size: 20px; text-align:left; font-family:Calibri; font-weight:bold'>Global Gasoline</p>")
    figs.append([
        f'<a href="{outputs_html_oil}\\physical_gasoline_and_swaps_page.html">Link to global gasoline page</a><br>',
        '&emsp;',
        f'<a href="{outputs_html_oil}\\kpler_inventory.html">Link to Global Liquids Inventory</a><br>',
    ])
    gasoline = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    gasoline_price_table = table.table_with_link(
        data=gasoline.loc[gasoline.index >= start_date, :], header="Gasoline Price", name='Global Physical Gasoline',
        folder=f"{outputs_html_oil}\\dashboard", inline=True, width1=100, width2=80,
        chart_columns={tuple(gasoline.columns): "seasonal"})
    gasoline_price_chart = py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoline_fig.json"))
    global_gasoline_table = pd.read_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_product_by_type_table.csv"))
    global_gasoline_table.set_index("Unnamed: 0", inplace=True)
    global_gasoline_table = global_gasoline_table.iloc[[1], :]
    global_gasoline_table.reset_index(drop=True, inplace=True)
    gasoline_stock_table = table.html_format(
        df=global_gasoline_table, header='Product Stocks Change by Type (kb) - Light Ends', footer=None, show_date=False,
        format_column=format_column, format_row=None, precision=0,
        hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    global_gasoline = ts.read_csv(f"{outputs_csv_oil}\\global_product_by_type.csv", index_name="Date")
    df_2y_gasoline = global_gasoline.loc[pygdt("-2y"):, ["Light Ends"]]
    global_gasoline_chart = pd.concat(
        [df_2y_gasoline, (df_2y_gasoline.rolling(10)).mean().loc[pygdt("-2y"):].iloc[:, 0].to_frame("10d ma")], axis=1)
    gasoline_stock_chart = chart.line_chart(
        df=global_gasoline_chart, title="Total Light Ends Stocks - level", tickformat=None,
        highlight_dict={"Light Ends": {"color": "black"}, "10d ma": {"color": "red", "width": 2}})
    gasoline_figs.extend([gasoline_price_table, gasoline_stock_table, clean_freight_table])
    gasoline_figs.extend([gasoline_price_chart, gasoline_stock_chart, clean_freight_chart])
    figs.append(table.figs_to_grid(gasoline_figs, columns=3))

    table.to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                  f"{html_path}\\oil\\dashboard.html", task_name=report_name)


if __name__ == "__main__":
    update()
