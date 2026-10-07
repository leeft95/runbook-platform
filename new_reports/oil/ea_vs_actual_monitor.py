import pandas as pd
import numpy as np
import datetime as dt
import sys
import statsmodels.api as sm
import requests
from dateutil.relativedelta import relativedelta
from pandas.tseries.offsets import BDay
import plotly.graph_objects as go
import plotly.express as px
import ecm.cmds.data as dv
import ecm.cmds.bbg as bbg
import ecm.cmds.chart as chart
import ecm.cmds.table as table
import ecm.cmds.sql as sql
from ecm.cmds.config import root_path, html_path, output_path, oil_group, csv_path
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux

send_to = ["rzhao@elementcapital.com", "ltrindade"]
report_name = "EA vs Actual Monitor"
file_name = "ea_vs_actual_monitor"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    """Transcription marker for text absent from all available photographs."""
    raise NotImplementedError(f"Missing photographed text: ea_vs_actual_monitor.py source lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 12, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def china_refinery(sdate=dt.datetime(2023, 11, 1)):
    official = bbg.bdh("CHENRCOL Index", ["PX_LAST"], dt.datetime(2010, 1, 1), today())
    soe_rate = bbg.bdh("CRCRSOER Index", ["PX_LAST"], dt.datetime(2010, 1, 1), today())
    soe_rate_m = soe_rate.resample("M").mean()
    forecast_dts = pd.date_range(sdate, soe_rate_m.index[-1], freq="M")
    refinery = pd.DataFrame(np.nan, index=forecast_dts, columns=["Official", "Implied by SOE run rate"])
    for d in forecast_dts:
        try:
            sloc = np.where(official.index <= d)[0][-1]
            y = official.iloc[sloc-50:sloc, 0]
        except:
            y = official.iloc[-50:, 0]
        sdate_ = np.max([y.index[0], soe_rate.index[0]])
        idx = y.loc[y.index >= sdate_].index
        dts = pd.date_range(y.index[0], y.index[-1], freq="M")
        y1 = y.reindex(dts)
        y1.fillna(method="ffill", inplace=True)
        y1 = y1 - y1[0]
        x1 = list(range(1, len(y1)+1))
        x1 = pd.Series(x1, index=y1.index)
        ols1 = sm.OLS(y1, x1)
        ols_result1 = ols1.fit()
        y1_adj = y1 - ols_result1.params[0] * (x1 - np.mean(x1)) + y[0]
        y1_adj = y1_adj.reindex(idx)

        x = soe_rate_m.loc[:d, "PX_LAST"]
        x_adj = sm.add_constant(x.reindex(idx))
        ols = sm.OLS(y1_adj, x_adj)
        ols_result = ols.fit()
        x1_adj = x1.reindex(x.index)
        for idx, i in x1_adj.items():
            if np.isnan(i):
                x1_adj.loc[idx] = i_ + 1
            else:
                i_ = x1_adj.loc[idx]
        fitted_runs = x * ols_result.params[1] + ols_result.params[0] + ols_result1.params[0] * (x1_adj - np.mean(x1))
        if d <= official.index[-1]:
            try:
                refinery.loc[d, "Official"] = official.loc[d, "PX_LAST"]
            except:
                refinery.loc[d, "Official"] = official.iloc[sloc, 0]
        refinery.loc[d, "Implied by SOE run rate"] = fitted_runs.loc[d]

    refinery["days"] = refinery.index.days_in_month
    refinery["Official"] = refinery["Official"] / refinery["days"] * 7.46 / 1000
    refinery["Implied by SOE run rate"] = refinery["Implied by SOE run rate"] / refinery["days"] * 7.46 / 1000
    refinery = refinery[["Official", "Implied by SOE run rate"]]

    ea_forecast = pd.DataFrame(
        [15.206, 15.034, 15.405, 15.708, 15.431, 15.717, 15.486, 15.594, 16.024, 15.616, 15.812, 15.628],
        index=pd.date_range("2024-01-31", "2024-12-31", freq="M"),
        columns=["EA"]
    )
    refinery_comb = pd.concat([refinery, ea_forecast], axis=1)
    refinery_comb.index = [dt.datetime(x.year, x.month, 1) for x in refinery_comb.index]
    return refinery_comb


def us_refinery_stocks(sdate=dt.datetime(2023, 11, 1)):
    runs = bbg.bdh("DOEPCRIN Index", ["PX_LAST"], sdate, today())
    runs_m = runs.resample("MS").mean()
    padd2 = bbg.bdh("DOESCRU2 Index", ["PX_LAST"], sdate, today())
    padd2_m = padd2.resample("MS").mean()
    padd3 = bbg.bdh("DOESCRU3 Index", ["PX_LAST"], sdate, today())
    padd3_m = padd3.resample("MS").mean()

    ea = pd.read_excel(
        convert_path_to_linux("\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\CODE\\data\\sell_side_consen"
                              + _missing_photo_text("127")),
        sheet_name="2019 - 2024 Balances"
    )
    total = ea.iloc[2:26, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd1 = ea.iloc[30:53, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd2 = ea.iloc[57:80, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd3 = ea.iloc[84:107, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd4 = ea.iloc[111:134, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])
    padd5 = ea.iloc[138:, 1:].dropna(axis=0, how="all").set_index(ea.columns[1])

    total_runs = total.loc[[total.index[0], "Runs"], :].T
    total_runs.set_index(total_runs.columns[0], inplace=True)
    total_runs.index = pd.to_datetime(total_runs.index)

    padd2_stocks = padd2.loc[[padd2.index[0], "Stocks"], :].T
    padd2_stocks.set_index(padd2_stocks.columns[0], inplace=True)
    padd2_stocks.index = pd.to_datetime(padd2_stocks.index)

    padd3_stocks = padd3.loc[[padd3.index[0], "Stocks"], :].T
    padd3_stocks.set_index(padd3_stocks.columns[0], inplace=True)
    padd3_stocks.index = pd.to_datetime(padd3_stocks.index)

    runs_comb = pd.concat([runs_m / 1000, total_runs / 1000], axis=1)
    runs_comb = runs_comb.loc[runs_comb.index >= sdate, :]
    runs_comb.columns = ["DOE", "EA"]
    padd2_comb = pd.concat([padd2_m / 1000, padd2_stocks], axis=1)
    padd2_comb = padd2_comb.loc[padd2_comb.index >= sdate, :]
    padd2_comb.columns = ["DOE", "EA"]
    padd3_comb = pd.concat([padd3_m / 1000, padd3_stocks], axis=1)
    padd3_comb = padd3_comb.loc[padd3_comb.index >= sdate, :]
    padd3_comb.columns = ["DOE", "EA"]
    return runs_comb, padd2_comb, padd3_comb


def update():
    figs = []
    figs.append("<div style='font-family:Calibri; '>")
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    china_runs = china_refinery(sdate=dt.datetime(2023, 11, 1))
    figs.append(chart.line_chart(df=china_runs, title="China Refinery Monitor", y_axis_title="mbd", tickformat=None))
    us_runs, padd2, padd3 = us_refinery_stocks(sdate=dt.datetime(2023, 11, 1))
    figs.append(chart.line_chart(
        df=us_runs,
        title="US Refinery Monitor",
        y_axis_title="mbd",
        highlight_dict={"DOE": {"mode": "markers+lines"}, "EA": {"mode": "markers+lines"}},
        tickformat=None
    ))
    figs.append(chart.line_chart(df=padd2, title="PADD2 Stocks Monitor", y_axis_title="mb", tickformat=None))
    figs.append(chart.line_chart(df=padd3, title="PADD3 Monitor", y_axis_title="mb", tickformat=None))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri", tag='h1')] + figs,
        f"{html_path}\\oil\\{file_name}.html", task_name=report_name
    )
    send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    raise NotImplementedError("Missing photographed main block: ea_vs_actual_monitor.py after line188")
