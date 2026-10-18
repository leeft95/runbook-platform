import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import time
import calendar
import statsmodels.api as sm
from dateutil.relativedelta import relativedelta
import ecm.cmds.sql as sql
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.to_html as to_html

import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.time_series as ts
from ecm.cmds.cdr import today
from ecm.cmds.config import data_path, html_path, oil_group, csv_path, root_path
from ecm.cmds._email import send_email

from ecm.atom.clients import retry

send_to = oil_group
report_name = "EA Forecast Evolution"
file_name = "ea_evolution"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in ea_evolution.py, photographed lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY,
        start_datetime=dt.datetime(2023, 7, 1, 13, 30), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(10))
def ea_tracker_2024(dataset_id, start, length=12):
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
    df = pd.DataFrame()
    for i in range(-1, -length-1, -1):
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
    anchor = dv.energy_aspects(dataset_id=dataset_id_, start=start, release_date="2023-12-20T23:55:00")
    anchor.set_index("Date", inplace=True)
    anchor.index = pd.to_datetime(anchor.index)
    anchor = anchor.sum(axis=1).to_frame("2024 Anchor")
    anchor_2025 = dv.energy_aspects(dataset_id=dataset_id_, start=start, release_date="2024-04-08T23:55:00")
    anchor_2025.set_index("Date", inplace=True)
    anchor_2025.index = pd.to_datetime(anchor_2025.index)
    anchor_2025 = anchor_2025.sum(axis=1).to_frame("2025 Anchor")
    df = pd.concat([anchor, df], axis=1)
    return df



@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(10))
def ea_tracker(dataset_id, start, length=12):
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
    df = pd.DataFrame()
    for i in range(-1, -length-1, -1):
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
    anchor = dv.energy_aspects(dataset_id=dataset_id_, start=start, release_date="2025-12-20T23:55:00")
    anchor.set_index("Date", inplace=True)
    anchor.index = pd.to_datetime(anchor.index)
    anchor = anchor.sum(axis=1).to_frame("2026 Anchor")
    df = pd.concat([anchor, df], axis=1)
    return df



def chart1(data, title, unit):
    yr = data.resample("Y").mean()
    yr.index = yr.index.to_period("Y")
    yr = yr.T
    yr.columns = [str(x) + 'Y' for x in yr.columns]
    qr = data.resample("Q").mean()
    qr.index = qr.index.to_period("Q")
    qr = qr.T
    df = pd.concat([yr, qr], axis=1)
    df.index = [x[:10] for x in df.index]
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    df.columns = [str(x) for x in df.columns]
    cur_y = today().year
    cur_q = int((today().month - 1) / 3 + 1)
    cur_col = df.columns.get_loc(f"{str(cur_y)}Q{cur_q}")
    df = df.iloc[:, [1, 2, cur_col-1, cur_col, cur_col+1, cur_col+2, cur_col+3]]
    if len(yr.columns) == 1:
        return chart.line_chart(df=df, tickformat=False, title=title, y_axis_title=unit,
            x_axis_title="Forecast date",
            highlight_dict={df.columns[0]: {"color": "black", "width": 2, "mode": "markers+lines"}},
            width=750, height=500)
    else:
        return chart.line_chart(df=df, tickformat=False, title=title, y_axis_title=unit,
            x_axis_title="Forecast date",
            highlight_dict={
                df.columns[0]: {"color": "black", "width": 2, "mode": "markers+lines"},
                df.columns[1]: {"color": "red", "width": 2, "mode": "markers+lines"}},
            width=750, height=500)


def update():
    figs1 = []
    figs2 = []
    figs3 = []
    sdate = dt.datetime(today().year, 1, 1) - relativedelta(years=1)
    item_dict = {
        "Global Liquids Balance": "6471",
        "Global Liquids Supply": "6769",
        "Global Liquids Demand": "5214",
        "Global Crude Balance": "6470",
        "Global Refinery Runs": "5239",
        "OPEC Crude Supply": "14",
        "Saudi Crude Supply": "11",
        "Russia, Iran, Venezuela Crude Supply": ["1161", "6", "12"],
        "Non OPEC Crude+Condensate Supply": "1274",
        "US Crude+Condensate production": "1070",
        "Brazil Crude Production": "1079",
        "China demand": "841",
    }
    scol = 1
    table_dict = {}
    raw_tables = {}
    for k, v in item_dict.items():
        print(k)
        data = ea_tracker(dataset_id=v, start=sdate.strftime("%Y-%m-%d"), length=12)
        raw_tables[k] = data
        if k == "Russia, Iran, Venezuela Crude Supply":
            try:
                data = data.drop(columns=["2025-07-09T23:55:00"])  # bad data read for 2026
            except:
                pass
        if k in ["Global Liquids Balance", "Global Crude Balance", "OPEC Crude Supply", "Global Liquids Supply",
                 "Global Liquids Demand", "Non OPEC Crude+Condensate Supply"]:
            if k in ["Global Liquids Balance", "Global Crude Balance"]:
                data_table = data.iloc[:, 1:]
                data_table = data_table.loc[data_table.index.year >= today().year, :]
                df_table = pd.DataFrame(np.nan, index=["Q1", "Q2", "Q3", "Q4", f"{today().year}", f"{today().year + 1}"], columns=data_table.columns)
                df_table.loc["Q1", :] = data_table.iloc[:3, :].mean(axis=0)
                df_table.loc["Q2", :] = data_table.iloc[3:6, :].mean(axis=0)
                df_table.loc["Q3", :] = data_table.iloc[6:9, :].mean(axis=0)
                df_table.loc["Q4", :] = data_table.iloc[9:, :].mean(axis=0)
                df_table.loc[f"{today().year}", :] = data_table.loc[data_table.index.year == today().year, :].mean(axis=0)
                df_table.loc[f"{today().year + 1}", :] = data_table.loc[data_table.index.year == (today().year + 1), :].mean(axis=0)
                df_table = df_table * 1000
            else:
                data_table_y_min_1 = data.iloc[:, 1:]
                data_table = data.iloc[:, 1:]
                data_table = data_table.loc[data_table.index.year >= today().year, :]
                data_table_year_Min_1 = data_table_y_min_1[data_table_y_min_1.index.year == (today().year - 1)]
                df_table = pd.DataFrame(np.nan, index=["Q1", "Q2", "Q3", "Q4", f"{today().year}", f"{today().year + 1}"], columns=data_table.columns)
                data_table_year_min_1_Q1 = data_table_year_Min_1.iloc[:, 0].iloc[:3, ].mean(axis=0)
                data_table_year_min_1_Q2 = data_table_year_Min_1.iloc[:, 0].iloc[3:6, ].mean(axis=0)
                data_table_year_min_1_Q3 = data_table_year_Min_1.iloc[:, 0].iloc[6:9, ].mean(axis=0)
                data_table_year_min_1_Q4 = data_table_year_Min_1.iloc[:, 0].iloc[9:, ].mean(axis=0)
                data_table_year_min_1_mean = data_table_year_Min_1.iloc[:, 0].mean(axis=0)
                df_table.loc["Q1", :] = data_table.iloc[:3, :].mean(axis=0) - data_table_year_min_1_Q1
                df_table.loc["Q2", :] = data_table.iloc[3:6, :].mean(axis=0) - data_table_year_min_1_Q2
                df_table.loc["Q3", :] = data_table.iloc[6:9, :].mean(axis=0) - data_table_year_min_1_Q3
                df_table.loc["Q4", :] = data_table.iloc[9:, :].mean(axis=0) - data_table_year_min_1_Q4
                df_table.loc[f"{today().year}", :] = _missing_photo_text("275: data_table.loc[data_table.index.year == today().year,...")
                df_table.loc[f"{today().year + 1}", :] = _missing_photo_text("276: data_table.loc[data_table.index.year == (today().year...")
                df_table = df_table / 1000
            df_table.columns = [dt.datetime.strptime(x[:10], "%Y-%m-%d").strftime("%b-%d") for x in df_table.columns]
            df_table.index.name = "Date"
            df_table.reset_index(inplace=True)
            if k in ["Global Liquids Balance", "Global Crude Balance"]:
                header = f"{k} in kbd"
            elif k == "Non OPEC Crude+Condensate Supply":
                header = "YoY Non OPEC Crude Supply in mbd"
            else:
                header = f" YoY {k} in mbd"
            table_dict[k] = table.html_format(
                df=df_table, precision=0 if k in ["Global Liquids Balance", "Global Crude Balance"] else 2,
                header=header, format_column={tuple(df_table.columns): {'width': '60px', 'text-align': 'center'}},
                inline=False)
        if k not in ["Global Liquids Balance", "Global Crude Balance"]:
            data = data / 1000
        if k not in ["Asia runs"]:
            figs1.append(chart1(data.iloc[:, scol:], title=k, unit="mbd"))
            col1 = _missing_photo_text("301")
            try:
                col2 = _missing_photo_text("303")
            except:
                col2 = len(data.columns) - 1
        else:
            figs1.append(chart1(data.iloc[:, scol:-2], title=k, unit="mbd"))
            col1 = scol + 1
            col2 = scol + 2
        data = data.loc[data.index < dt.datetime(2026, 1, 1), :]
        data.columns = [x[:10] if "T23:55:00" in x else x for x in data.columns]
        fig2_ = chart.line_chart(
            df=data.iloc[-15:, [0, 1, col1, col2]], title=k, y_axis_title="mbd",
            highlight_dict={
                data.columns[0]: {"color": "red", "width": 2, "dash": "dash"},
                data.columns[1]: {"color": "black", "width": 2, "mode": "markers+lines"}},
            tickformat=None, width=750, height=500)
        line_timestamp = dt.datetime(today().year, today().month, 1).timestamp() * 1000
        label = dt.datetime(today().year, today().month, 1).strftime("%Y-%m")
        fig2_.add_vline(x=line_timestamp, line_width=2, line_dash="dash", line_color="black",
                        **_missing_photo_text("328: annotation_tex..."))
        figs2.append(fig2_)
    tables = [table_dict["Global Liquids Balance"], table_dict["Global Crude Balance"],
              table_dict["Global Liquids Supply"], table_dict["OPEC Crude Supply"],
              table_dict["Global Liquids Demand"], table_dict["Non OPEC Crude+Condensate Supply"]]
    tables_html = to_html._figure_to_html_table(tables, num_columns=2)
    tables_html_email = table.figs_to_grid_email(tables, columns=2, width=1500)
    figs = list(zip(figs1, figs2))
    figs_email = ["<div style='font-family:Calibri; '>"] + [tables_html_email] + figs + [_missing_photo_text("343: prior-year HTML anchor clipped")]
    figs3.append(tables_html)
    figs.insert(0, figs3)
    figs.insert(0, "<div style='font-family:Calibri; '>")
    figs.append(u'<a href="{}\oil\{}_2024_main.html">Y-1 Link</a>'.format(html_path, file_name))
    table.to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                  f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    send_email(send_to=send_to, subject=report_name, body=figs_email, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    update()
