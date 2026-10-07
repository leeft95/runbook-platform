import pandas as pd
import numpy as np
import datetime as dt
import plotly as py
import sys
import statsmodels.api as sm
from pandas.tseries.offsets import BDay
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today
import ecm.cmds.pyg as pyg
from dateutil.relativedelta import relativedelta
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from functools import partial
import ecm.cmds.bbg as bbg
import ecm.cmds.data as dv
from pyg_mongo import *
from ecm.cmds.config import url, root_path, html_path, oil_group
from ecm.cmds._email import send_email

send_to = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "China Refinery Runs"
file_name = "china_oil_demand"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in china_oil_demand.py, photographed lines {lines}")


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


def china_refinery(sdate=dt.datetime(2023, 11, 1)):
    official_bbg = bbg.bdh("CHENRCOL Index", ["PX_LAST"], dt.datetime(2010, 1, 1), today())
    official_cum = bbg.bdh("CHXCPOIL Index", ["PX_LAST"], dt.datetime(2010, 1, 1), today())
    official_cum = official_cum.loc[official_cum.index.month == 2, :] / 2 * 1000
    official_cum = official_cum.loc[official_cum.index > dt.datetime(2016, 1, 1)]
    official_cum_1 = pd.DataFrame(official_cum.values,
        index=[x - relativedelta(months=1) + relativedelta(day=31) for x in official_cum.index], columns=["PX_LAST"])
    official_bbg = pd.concat([official_bbg, official_cum_1, official_cum], axis=0)
    official_bbg.sort_index(inplace=True)
    official_bbg["days"] = official_bbg.index.days_in_month
    official_bbg["PX_LAST"] = official_bbg["PX_LAST"] / official_bbg["days"] * 7.5 / 1000
    official_bbg.index = [dt.datetime(x.year, x.month, 1) for x in official_bbg.index]
    official = official_bbg.copy()
    soe_rate = bbg.bdh("CRCRSOER Index", ["PX_LAST"], dt.datetime(2010, 1, 1), today())
    soe_rate_m = soe_rate.resample("MS").mean()
    forecast_dts = pd.date_range(sdate, soe_rate.index[-1], freq="W-THU")
    refinery = pd.DataFrame(np.nan, index=forecast_dts, columns=["Official_BBG", "Implied by SOE run rate"])
    for d in forecast_dts:
        if d == dt.datetime(2025, 2, 6):
            print(d)
        try:
            sloc = official.index.get_loc(dt.datetime(d.year, d.month, 1))
            y = official.iloc[sloc - 60:sloc, 0]
        except:
            y = official.iloc[-60:, 0]
        sdate_ = np.max([y.index[0], soe_rate.index[0]])
        idx = y.loc[y.index >= sdate_].index
        dts = pd.date_range(y.index[0], y.index[-1], freq="MS")
        y1 = y.reindex(dts)
        y1.fillna(method="ffill", inplace=True)
        y1_ = y1.copy()
        y1 = y1 - y1[0]
        x1 = list(range(1, len(y1) + 1))
        x1 = pd.Series(x1, index=y1.index)
        ols1 = sm.OLS(y1, x1)
        ols_result1 = ols1.fit()
        y1_adj = y1 - ols_result1.params[0] * (x1 - np.mean(x1)) + y[0]
        y1_adj = y1_.reindex(idx)
        x = soe_rate_m.loc[:d, "PX_LAST"]
        x_weekly = soe_rate.loc[:d, "PX_LAST"]
        x_adj = sm.add_constant(x.reindex(idx))
        ols = sm.OLS(y1_adj, x_adj)
        ols_result = ols.fit()
        x1_adj = x1.reindex(x.index)
        daily_dts = pd.date_range(x_weekly.index[0], x_weekly.index[-1], freq="D")
        x1_adj_daily = x1_adj.reindex(daily_dts)
        x1_adj_daily.fillna(method="ffill", inplace=True)
        x1_adj_weekly = x1_adj_daily.reindex(x_weekly.index)
        for idx, i in x1_adj.items():
            if np.isnan(i):
                x1_adj.loc[idx] = i_ + 1
            else:
                i_ = x1_adj.loc[idx]
        fitted_runs = x_weekly * ols_result.params[1] + ols_result.params[0]
        if d + relativedelta(day=1) <= official_bbg.index[-1]:
            try:
                sloc_bbg = official_bbg.index.get_loc(dt.datetime(d.year, d.month, 1))
                refinery.loc[d, "Official_BBG"] = official_bbg.iloc[sloc_bbg, 0]
            except:
                try:
                    refinery.loc[d, "Official_BBG"] = refinery.loc[_missing_photo_text("120: d if d == dt.datetime(2025,1,2) else d -...")]
                except:
                    refinery.loc[d, "Official_BBG"] = np.nan
        try:
            refinery.loc[d, "Implied by SOE run rate"] = fitted_runs.loc[d]
        except:
            refinery.loc[d, "Implied by SOE run rate"] = np.nan
    release_dts = dv.ea_release_dates(dataset_id="1655", monthly=False)
    release_dt = pd.DatetimeIndex([dt.datetime.strptime(x, "%Y-%m-%dT23:55:00") for x in release_dts])
    anchor_date = release_dts[np.where(release_dt < dt.datetime(today().year, 1, 1))[0][-1]]
    quarter_date = release_dts[np.where(release_dt < today() - pd.offsets.QuarterBegin(n=1, startingMonth=3))[0][-1]]
    anchor_data = dv.energy_aspects(dataset_id="1655", start="2018-01-01", release_date=anchor_date)
    anchor_data.set_index("Date", inplace=True)
    anchor_data.index = pd.to_datetime(anchor_data.index)
    quarter_data = dv.energy_aspects(dataset_id="1655", start="2018-01-01", release_date=quarter_date)
    quarter_data.set_index("Date", inplace=True)
    quarter_data.index = pd.to_datetime(quarter_data.index)
    ea_forecast = pd.concat([anchor_data, quarter_data], axis=1)
    ea_forecast.columns = ["EA-Anchor", "EA-Last Quarter"]
    ea_forecast_weekly = ea_forecast.reindex(pd.date_range(ea_forecast.index[0],
        ea_forecast.index[-1] + _missing_photo_text("149: relativedelta...")))
    ea_forecast_weekly.fillna(method="ffill", inplace=True)
    ea_forecast_weekly = ea_forecast_weekly.resample("W-THU").last()
    ea_forecast_weekly = ea_forecast_weekly.loc[ea_forecast_weekly.index >= refinery.index[0], :]
    refinery_comb = pd.concat([refinery, ea_forecast_weekly / 1000], axis=1)
    refinery_comb.loc[refinery_comb.index <= today(), "Implied by SOE run rate"] = _missing_photo_text("154: refinery_comb.loc[refiner...")
    return refinery_comb


def update():
    china_runs = china_refinery(sdate=dt.datetime(2023, 11, 1))
    release = bbg.bbulkref("CHENRCOL Index", ["ECO_FUTURE_RELEASE_DATE_LIST"])
    release = release.iloc[:, 0]
    release_list = pd.DatetimeIndex(pd.to_datetime(release[:-1])).normalize().unique()
    release_list1 = pd.to_datetime(release.iloc[-1].split(" "))
    release_list = release_list.append(release_list1)
    if True:
        figs = []
        figs.append("<div style='font-family:Calibri; '>")
        figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
        highlight_dict = {"EA-Anchor": {"color": "red", "dash": "dash"},
                          "EA-Last Quarter": {"color": "black", "dash": "dash"}}
        figs.append(chart.line_chart(df=china_runs, title="China Refinery Monitor", y_axis_title="mbd",
                                      **_missing_photo_text("175: tickformat=N...")))
        soe_rate = bbg.bdh("CRCRSOER Index", ["PX_LAST"], dt.datetime(2021, 1, 1), today())
        dts1 = pd.date_range(dt.datetime(2021, 1, 1), today(), freq="W-THU")
        soe_rate = soe_rate.reindex(dts1)
        soe_rate.fillna(method="ffill", inplace=True)
        figs.append(chart.seasonal(df=soe_rate, title="China State Owned Refineries Run Rates", freq="W",
                                    **_missing_photo_text("182: wi...")))
        sdi_rate = bbg.bdh("CRCRSDIR Index", ["PX_LAST"], dt.datetime(2021, 1, 1), today())
        dts2 = pd.date_range(dt.datetime(2018, 1, 1), today(), freq="W-FRI")
        sdi_rate = sdi_rate.reindex(dts2)
        sdi_rate.fillna(method="ffill", inplace=True)
        figs.append(chart.seasonal(df=sdi_rate, title="China Shandong Independent Refineries Run Rates",
                                    **_missing_photo_text("188: freq...")))
        ip_refinery = bbg.bdh("CHENRCOL Index", ["PX_LAST"], sdate=dt.datetime(2017, 1, 1), edate=today())
        data_2024_1_2 = pd.DataFrame([197.9 * 31 * 10, 197.9 * 29 * 10],
            index=[dt.datetime(2024, 1, 31), dt.datetime(2024, 2, 29)], columns=["PX_LAST"])
        ip_refinery = pd.concat([ip_refinery, data_2024_1_2], axis=0)
        ip_refinery.sort_index(inplace=True)
        dts = pd.date_range(dt.datetime(2017, 1, 1), today(), freq='M')
        ip_refinery = ip_refinery.reindex(dts)
        ip_refinery["days"] = ip_refinery.index.days_in_month
        ip_refinery["mbd"] = ip_refinery["PX_LAST"] / ip_refinery["days"] * 7.46 / 1000
        ip_refinery = ip_refinery[["mbd"]]
        ip_refinery_yoy = ip_refinery / ip_refinery.shift(12) - 1
        ip_refinery_yoy = ip_refinery_yoy.loc[ip_refinery_yoy.index >= dt.datetime(2018, 1, 1), :]
        figs.append(chart.seasonal_chart(df=ip_refinery, title="China Official Refinery Runs - mbd",
                                         **_missing_photo_text("203: freq=M...")))
        figs.append(chart.seasonal_chart(df=ip_refinery_yoy, title="China Official Refinery Runs - yoy",
                                         **_missing_photo_text("204: freq...")))
        table.figures_to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                              f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
        send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    update()
