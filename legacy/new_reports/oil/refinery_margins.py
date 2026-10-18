import pandas as pd
import numpy as np
import datetime as dt
import plotly as py
import sys
import plotly.graph_objects as go
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
from pyg_mongo import *
from ecm.cmds.config import url, root_path, html_path
from ecm.cmds.utils import convert_path_to_linux
from loguru import logger as log
import time

db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
outputs_json_oil = f"{root_path}\\outputs\\json\\oil"
outputs_html_oil_link = f"{root_path}\\outputs\\htmls\\oil\\links"
report_name = "Refinery Margins"
file_name = "refinery_margins"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text at source lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 6, 5),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def fv_table(data, key):
    output = pd.DataFrame(0, index=["30d MA", "14d MA", "8d MA", "Margin"], columns=data.columns)
    output.loc["30d MA", :] = data.rolling(30).mean().iloc[-1, :]
    output.loc["14d MA", :] = data.rolling(14).mean().iloc[-1, :]
    output.loc["8d MA", :] = data.rolling(8).mean().iloc[-1, :]
    output.loc["Margin", :] = data.iloc[-1, :]
    output.index.name = key
    output.reset_index(drop=False, inplace=True)
    return table.html_format(df=output)


def eu_margins():
    log.info("=" * 60)
    log.info("Starting EU margins calculation")
    start_time = time.time()
    weight_conversion = {
        "10ppm ULSD": [0.3, 7.45, "FSGOM"],
        "0.1% Gasoil": [0.03, 7.45, "FSB1M"],
        "Jet": [0.06, 7.878, "FSWJM"],
        "Gasoline": [0.38, 8.33, "FSNOM"],
        "Naphtha": [0.04, 8.9, "FSNNM"],
        "Propane": [0.03, 12.11, "FNPAM"],
        "3.5% FO": [0.04, 6.35, "FSROM"],
        "0.5% Marine": [0.12, 6.35, "FLSEM"],
    }
    log.info("Fetching spot price data from Platts...")
    fetch_start = time.time()
    eufo = pyg.get_data(db, platts_ticker="PUABC00")
    eugo = pyg.get_data(db, platts_ticker="AAJUS00")
    eunap = pyg.get_data(db, platts_ticker="PAAAL00")
    ebob = pyg.get_data(db, platts_ticker="AAQZV00")
    eujet = pyg.get_data(db, platts_ticker="PJAAU00")
    eugo01 = pyg.get_data(db, platts_ticker="AAYWT00")
    eufo1 = pyg.get_data(db, platts_ticker="PUMFD00")
    dbrent = pyg.get_data(db, platts_ticker="PCAAS00")
    log.info(f"Spot price data fetched in {time.time() - fetch_start:.2f}s")
    data_dict = {
        "10ppm ULSD": eugo,
        "0.1% Gasoil": eugo01,
        "Jet": eujet,
        "Gasoline": ebob,
        "Naphtha": eunap,
        "Propane": eunap,
        "3.5% FO": eufo,
        "0.5% Marine": eufo1,
    }
    log.info("Calculating spot margins...")
    calc_start = time.time()
    df = pd.DataFrame()
    for key, val in weight_conversion.items():
        df[key] = data_dict[key] / val[1] - dbrent
    df.dropna(inplace=True)
    df_weight = df.copy()
    for key, val in weight_conversion.items():
        df_weight[key] = val[0]
    margins_ind = df * df_weight
    margins = (df * df_weight).sum(axis=1)
    gen_month = list(month_str2int.keys())
    cur_yr = today().year
    next_yr = today().year + 1
    cur_q = int((today().month - 1) / 3 + 1)
    next_q = (cur_q + 1) - 4 if cur_q >= 4 else cur_q + 1
    next_q1 = (next_q + 1) - 4 if next_q >= 4 else next_q + 1
    next_q2 = (next_q1 + 1) - 4 if next_q1 >= 4 else next_q1 + 1
    quarter_dict = {1: "F", 2: "J", 3: "N", 4: "V"}
    df_fv = pd.DataFrame()
    df_fv_7d = pd.DataFrame()
    df_fv_next_yr = pd.DataFrame()
    df_fv_next_yr_daily = pd.DataFrame()
    df_fv_all = {}
    cur_yr_ticker_dated = [f"FSDBM {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
    next_yr_ticker_dated = [f"FSDBM {x}{str(next_yr)[-2:]} Index" for x in gen_month]
    two_yr_ticker_dated = cur_yr_ticker_dated + next_yr_ticker_dated
    next_ticker_month = gen_month[np.mod(today().month, len(gen_month))]
    next_ticker_year = today().year if today().month < len(gen_month) else today().year + 1
    cur_ticker_index = two_yr_ticker_dated.index(f"FSDBM {next_ticker_month}{str(next_ticker_year)[-2:]} Index")
    next_10_ticker_dated = two_yr_ticker_dated[cur_ticker_index:]
    if margins.index[-1].month < 3:
        bbg_sdate = margins.index[-1] - dt.timedelta(60)
    else:
        bbg_sdate = dt.datetime(margins.index[-1].year, 1, 1)
    log.info(f"Spot margins calculated in {time.time() - calc_start:.2f}s")
    log.info("Fetching Bloomberg forward dated Brent data...")
    bbg_start = time.time()
    fv_dated = bbg.bdh(cur_yr_ticker_dated, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_dated_10 = bbg.bdh(next_10_ticker_dated, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_dated_next_yr = bbg.bdh(next_yr_ticker_dated, ["PX_LAST"], bbg_sdate, margins.index[-1])
    log.info(f"Bloomberg Brent data fetched in {time.time() - bbg_start:.2f}s")
    log.info("Calculating forward margins for each product...")
    fv_calc_start = time.time()
    for key, val in weight_conversion.items():
        log.info(f"  Processing {key}...")
        cur_yr_ticker = [f"{val[2]} {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
        next_yr_ticker = [f"{val[2]} {x}{str(next_yr)[-2:]} Index" for x in gen_month]
        two_yr_ticker = cur_yr_ticker + next_yr_ticker
        next_10_ticker = two_yr_ticker[cur_ticker_index:]
        cols = [dt.datetime(cur_yr, x+1, 1) + relativedelta(day=31) for x, _x in enumerate(gen_month)]
        fv_price = bbg.bdh(cur_yr_ticker, ["PX_LAST"], bbg_sdate, margins.index[-1])
        fv_dated_ = fv_dated.copy()
        fv_dated_ = fv_dated_.reindex(fv_price.index)
        fv_dated_.columns = fv_price.columns
        fv_price = fv_price / val[1] - fv_dated_
        fv_price.fillna(method="ffill", inplace=True)
        fv_price_1d = fv_price.iloc[[-1], :]
        if fv_price.shape[0] < 7:
            fv_price_7d = fv_price.iloc[[0], :]
        else:
            fv_price_7d = fv_price.iloc[[-7], :]
        fv_price_1d.columns = cols
        fv_price_7d.columns = cols
        df_fv[key] = fv_price_1d.T.reindex(pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        df_fv_7d[key] = fv_price_7d.T.reindex(pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        fv_price_next_yr_ori = bbg.bdh(next_yr_ticker, ["PX_LAST"], bbg_sdate, margins.index[-1])
        fv_price_next_yr = fv_price_next_yr_ori.copy()
        fv_dated_next_yr_ = fv_dated_next_yr.copy()
        fv_dated_next_yr_ = fv_dated_next_yr_.reindex(fv_price_next_yr.index)
        fv_dated_next_yr_.columns = fv_price_next_yr.columns
        fv_price_next_yr = fv_price_next_yr / val[1] - fv_dated_next_yr_
        fv_price_next_yr.fillna(method="ffill", inplace=True)
        df_fv_next_yr_daily[key] = fv_price_next_yr.mean(axis=1)
        fv_price_next_yr = fv_price_next_yr.iloc[[-1], :]
        fv_price_next_yr.columns = cols
        df_fv_next_yr[key] = fv_price_next_yr.T.reindex(
            pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        fv_price_10 = bbg.bdh(next_10_ticker, ["PX_LAST"], margins.index[-1] - dt.timedelta(364), margins.index[-1])
        fv_dated_1 = fv_dated_10.copy()
        fv_dated_1 = fv_dated_1.reindex(fv_price_10.index)
        fv_dated_1.columns = fv_price_10.columns
        fv_price_10 = fv_price_10 / val[1] - fv_dated_1
        fv_price_10.fillna(method="ffill", inplace=True)
        fv_price_10.columns = [x.split(" ")[1] for x in next_10_ticker]
        nq1 = [x[0] for x in fv_price_10.columns].index(quarter_dict[next_q])
        fv_price_nq1 = fv_price_10.iloc[:, nq1:nq1+3].mean(axis=1)
        fv_price_nq2 = fv_price_10.iloc[:, nq1+3:nq1+6].mean(axis=1)
        fv_price_nq3 = fv_price_10.iloc[:, nq1+6:nq1+9].mean(axis=1)
        fv_price_mqy = pd.concat([fv_price_10.iloc[:, :3], fv_price_nq1, fv_price_nq2, fv_price_nq3,
                                  fv_price_10.iloc[:, -12:].mean(axis=1)], axis=1)
        fv_price_mqy.columns = list(fv_price_10.columns[:3]) + [f"Q{next_q}{fv_price_10.columns[nq1][-2:]}",
            f"Q{next_q1}{fv_price_10.columns[nq1+3][-2:]}", f"Q{next_q2}{fv_price_10.columns[nq1+6][-2:]}", f"{next_yr}"]
        df_fv_all[key] = pd.concat([df[key].to_frame("Spot").reindex(fv_price_10.index).fillna(method="ffill"), fv_price_mqy], axis=1)
    log.info(f"Forward margins calculated in {time.time() - fv_calc_start:.2f}s")
    log.info("Preparing data for charting...")
    chart_prep_start = time.time()
    df_weight_fv = df_fv.copy()
    for key, val in weight_conversion.items():
        df_weight_fv[key] = val[0]
    margins_fv = (df_fv * df_weight_fv).sum(axis=1)
    margins_fv_7d = (df_fv_7d * df_weight_fv).sum(axis=1)
    margins_fv_next_yr = (df_fv_next_yr * df_weight_fv).sum(axis=1)
    margins_fv_next_yr_sep = (df_fv_next_yr_daily * df_weight.reindex(df_fv_next_yr_daily.index, method='ffill'))
    margins_fv_next_yr_sep.fillna(method="ffill", inplace=True)
    sdate = dt.datetime(2019, 1, 1)
    edate = dt.datetime(cur_yr, 12, 31)
    dts = pd.bdate_range(sdate, edate)
    dts_cur_yr = pd.bdate_range(dt.datetime(cur_yr, 1, 1), edate)
    margins = margins.reindex(dts)
    margins.fillna(method="ffill", inplace=True)
    margins.loc[margins.index >= today()] = np.nan
    margins_fv = margins_fv.reindex(dts_cur_yr)
    margins_fv_7d = margins_fv_7d.reindex(dts_cur_yr)
    margins_fv_next_yr = margins_fv_next_yr.reindex(dts_cur_yr)
    log.info(f"Chart data prepared in {time.time() - chart_prep_start:.2f}s")
    log.info("Creating charts...")
    chart_start = time.time()
    fig1 = chart.seasonal(
        df=margins.to_frame("Spot margins"), title="NWE margin not adjusted for natgas",
        highlight_dict={cur_yr: {"mode": "lines+markers", "color": "black", "width": 2}, },
        freq="B", drop_years=[2022], height=500, width=750)
    fig1.add_trace(go.Scatter(name="FWD", x=margins_fv.index, y=margins_fv, showlegend=True, mode="lines",
                             line=dict(color="red")))
    fig1.add_trace(go.Scatter(name="FWD 7d ago", x=margins_fv_7d.index, y=margins_fv_7d, showlegend=True, mode="lines",
                             line=dict(color="blue", dash="dash")))
    fig1.add_trace(go.Scatter(name=f"FWD {next_yr}", x=margins_fv_next_yr.index, y=margins_fv_next_yr, showlegend=True,
                             mode="lines", line=dict(color="red", dash="dash")))
    fig2_x = ["Margin 7d ago"] + list(margins_ind.columns) + ["Margin Today"]
    fig2_data = [margins_ind.sum(axis=1)[-6]] + (margins_ind.iloc[-1, :] - margins_ind.iloc[-6, :]).to_list() + [margins_ind.sum(axis=1)[-1]]
    fig2 = go.Figure(go.Waterfall(
        name="margin", orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "absolute"],
        x=fig2_x, y=fig2_data, width=0.5, textposition="outside", text=["{:.2f}".format(x) for x in fig2_data]))
    fig2.update_layout(
        title={"text": "Cash margin change week over week", "x": 0.5, "xanchor": "center"},
        showlegend=False, width=750, height=510,
        yaxis_range=[int(np.max(fig2_data) / 3 * 2), int(np.max(fig2_data) + 2)])
    fig21_x = ["Margin 7d ago"] + list(margins_fv_next_yr_sep.columns) + ["Margin Today"]
    if margins_fv_next_yr_sep.shape[0] < 7:
        fig21_data = [margins_fv_next_yr_sep.sum(axis=1)[0]] + (
            margins_fv_next_yr_sep.iloc[-1, :] - margins_fv_next_yr_sep.iloc[0, :]).to_list() + [
            margins_fv_next_yr_sep.sum(axis=1)[-1]]
    else:
        fig21_data = [margins_fv_next_yr_sep.sum(axis=1)[-6]] + (
            margins_fv_next_yr_sep.iloc[-1, :] - margins_fv_next_yr_sep.iloc[-6, :]).to_list() + [
            margins_fv_next_yr_sep.sum(axis=1)[-1]]
    fig21 = go.Figure(go.Waterfall(
        name="margin", orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "absolute"],
        x=fig21_x, y=fig21_data, width=0.5, textposition="outside", text=["{:.2f}".format(x) for x in fig21_data]))
    fig21.update_layout(
        title={"text": f"{next_yr} margin change week over week", "x": 0.5, "xanchor": "center"},
        showlegend=False, width=750, height=500,
        yaxis_range=[int(np.max(fig21_data) / 3 * 2), int(np.max(fig21_data) + 2)])
    fv_m2_ticker = {
        "Disti Crack": "FSQCM2 Index",
        "Jet Crack": "FJNBM2 Index",
        "Naptha Crack": "FNNSM2 Index",
        "Gasoline Crack": "FNOSM2 Index",
        "Fuel Crack": "FROSM2 Index",
    }
    fv_m2 = bbg.bdh(list(fv_m2_ticker.values()), ["PX_LAST"], today()-dt.timedelta(364), today())
    fv_m2.columns = fv_m2_ticker.keys()
    fig3 = chart.line_chart(
        df=fv_m2[["Disti Crack", "Jet Crack", "Gasoline Crack"]], secondary_y=True,
        title="Second month NWE cracks", tickformat=False, width=750, height=500)
    fig3.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5, itemwidth=30))
    fig31 = chart.line_chart(
        df=df_fv_next_yr_daily.loc[df_fv_next_yr_daily.index >= fv_m2.index[0], ["10ppm ULSD", "Jet", "Gasoline"]],
        secondary_y=True, title=f"{next_yr} NWE cracks fair value", tickformat=False, width=750, height=500)
    fig31.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5, itemwidth=30))
    co26_ticker = bbg.live_spread_ticker(active='COA Comdty', spread="26")
    co_gen = pyg.get_data("contracts", active="COA Comdty", item="PX_LAST_gen")
    co26_price = (co_gen.iloc[:, 1] - co_gen.iloc[:, 5]).to_frame(co26_ticker)
    fig4 = chart.line_chart(
        df=co26_price.loc[co26_price.index >= today() - dt.timedelta(364), :],
        title="Brent 2-6 spread", tickformat=False, width=750, height=500)
    fig4.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    log.info(f"Charts created in {time.time() - chart_start:.2f}s")
    log.info("Building HTML tables...")
    table_start = time.time()
    tbs = []
    total_fv_10 = pd.DataFrame()
    for key, val in weight_conversion.items():
        if len(total_fv_10) == 0:
            total_fv_10 = df_fv_all[key] * val[0]
        else:
            total_fv_10 += df_fv_all[key] * val[0]
        tbs.append(fv_table(df_fv_all[key], key))
    tbs.insert(0, fv_table(total_fv_10, "Margin"))
    log.info(f"Tables built in {time.time() - table_start:.2f}s")
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_missing_photo_text(379, "Weights: 10ppm ULSD - 30%, 0.1% Gasoil - 3%, Jet - 6%, Gasoline - 38%, Naphtha - 4%, Propa"))
    figs.append([fig1, fig2, fig21])
    figs.append([fig3, fig31, fig4])
    figs = figs + tbs
    log.info("Writing HTML output...")
    html_start = time.time()
    table.to_html(
        [table.html_text("NWE Refinery Margins", style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\refinery_margins_eu.html", task_name=report_name)
    log.info(f"HTML written in {time.time() - html_start:.2f}s")
    log.info(f"EU margins completed in {time.time() - start_time:.2f}s total")
    log.info("=" * 60)


def us_margins():
    weight_conversion = {
        "10ppm ULSD": [0.32, 2.380952, "FSGCM"],
        "Jet": [0.11, 2.380952, "FSGJM"],
        "Gasoline": [0.44, 2.380952, "FSCDM"],
        "Naphtha": [0.09, 0.02380952, "FMBVM"],
        "Propane": [0.02, 0.02380952, "FSM3M"],
        "3.5% FO": [0.02, 1, "FSG3M"],
    }
    usfo = pyg.get_data(db, platts_ticker="PUAFZ00")
    usgo = pyg.get_data(db, platts_ticker="AATGY00")
    usnap = pyg.get_data(db, platts_ticker="AAWUG00") / 100
    gasoline = pyg.get_data(db, platts_ticker="AAELD00")
    usjet = pyg.get_data(db, platts_ticker="AAELU00")
    propane = pyg.get_data(db, platts_ticker="PMAAY00") / 100
    lls = pyg.get_data(db, platts_ticker="PCABN00")
    mars = pyg.get_data(db, platts_ticker="AAPYU00")
    data_dict = {
        "10ppm ULSD": usgo,
        "Jet": usjet,
        "Gasoline": gasoline,
        "Naphtha": usnap,
        "Propane": propane,
        "3.5% FO": usfo,
    }
    df = pd.DataFrame()
    for key, val in weight_conversion.items():
        df[key] = data_dict[key] / val[1] - (lls + mars)/2
    df.dropna(inplace=True)
    df_weight = df.copy()
    for key, val in weight_conversion.items():
        df_weight[key] = val[0]
    margins_ind = df * df_weight
    margins = (df * df_weight).sum(axis=1)
    gen_month = list(month_str2int.keys())
    cur_yr = today().year
    next_yr = today().year + 1
    cur_q = int((today().month - 1) / 3 + 1)
    next_q = (cur_q + 1) - 4 if cur_q >= 4 else cur_q + 1
    next_q1 = (next_q + 1) - 4 if next_q >= 4 else next_q + 1
    next_q2 = (next_q1 + 1) - 4 if next_q1 >= 4 else next_q1 + 1
    quarter_dict = {1: "F", 2: "J", 3: "N", 4: "V"}
    df_fv = pd.DataFrame()
    df_fv_7d = pd.DataFrame()
    df_fv_next_yr = pd.DataFrame()
    df_fv_next_yr_daily = pd.DataFrame()
    df_fv_all = {}
    cur_yr_ticker_lls = [f"FSLDM {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
    cur_yr_ticker_mars = [f"FSMCM {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
    next_yr_ticker_lls = [f"FSLDM {x}{str(next_yr)[-2:]} Index" for x in gen_month]
    next_yr_ticker_mars = [f"FSMCM {x}{str(next_yr)[-2:]} Index" for x in gen_month]
    two_yr_ticker_lls = cur_yr_ticker_lls + next_yr_ticker_lls
    two_yr_ticker_mars = cur_yr_ticker_mars + next_yr_ticker_mars
    next_ticker_month = gen_month[np.mod(today().month, len(gen_month))]
    next_ticker_year = today().year if today().month < len(gen_month) else today().year + 1
    cur_ticker_index = two_yr_ticker_lls.index(f"FSLDM {next_ticker_month}{str(next_ticker_year)[-2:]} Index")
    next_10_ticker_lls = two_yr_ticker_lls[cur_ticker_index:cur_ticker_index+10]
    if margins.index[-1].month < 3:
        bbg_sdate = margins.index[-1] - dt.timedelta(60)
    else:
        bbg_sdate = dt.datetime(margins.index[-1].year, 1, 1)
    fv_lls = bbg.bdh(cur_yr_ticker_lls, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_lls_10 = bbg.bdh(next_10_ticker_lls, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_lls_next_yr = bbg.bdh(next_yr_ticker_lls, ["PX_LAST"], bbg_sdate, margins.index[-1])
    next_10_ticker_mars = two_yr_ticker_mars[cur_ticker_index:cur_ticker_index+10]
    fv_mars = bbg.bdh(cur_yr_ticker_mars, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_mars_10 = bbg.bdh(next_10_ticker_mars, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_mars_next_yr = bbg.bdh(next_yr_ticker_mars, ["PX_LAST"], bbg_sdate, margins.index[-1])
    for key, val in weight_conversion.items():
        cur_yr_ticker = [f"{val[2]} {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
        next_yr_ticker = [f"{val[2]} {x}{str(next_yr)[-2:]} Index" for x in gen_month]
        two_yr_ticker = cur_yr_ticker + next_yr_ticker
        next_10_ticker = two_yr_ticker[cur_ticker_index:cur_ticker_index + 10]
        cols = [dt.datetime(cur_yr, x+1, 1) + relativedelta(day=31) for x, _x in enumerate(gen_month)]
        fv_price = bbg.bdh(cur_yr_ticker, ["PX_LAST"], bbg_sdate, margins.index[-1])
        fv_lls_ = fv_lls.copy()
        fv_lls_ = fv_lls_.reindex(fv_price.index)
        fv_lls_.columns = fv_price.columns
        fv_mars_ = fv_mars.copy()
        fv_mars_ = fv_mars_.reindex(fv_price.index)
        fv_mars_.columns = fv_price.columns
        fv_price = fv_price / val[1] - (fv_lls_ + fv_mars_)/2
        fv_price.fillna(method="ffill", inplace=True)
        fv_price_1d = fv_price.iloc[[-1], :]
        if fv_price.shape[0] < 7:
            fv_price_7d = fv_price.iloc[[0], :]
        else:
            fv_price_7d = fv_price.iloc[[-7], :]
        fv_price_1d.columns = cols
        fv_price_7d.columns = cols
        df_fv[key] = fv_price_1d.T.reindex(pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        df_fv_7d[key] = fv_price_7d.T.reindex(pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        fv_price_next_yr_ori = bbg.bdh(next_yr_ticker, ["PX_LAST"], bbg_sdate, margins.index[-1])
        fv_price_next_yr = fv_price_next_yr_ori.copy()
        fv_lls_next_yr_ = fv_lls_next_yr.copy()
        fv_lls_next_yr_ = fv_lls_next_yr_.reindex(fv_price_next_yr.index)
        fv_lls_next_yr_.columns = fv_price_next_yr.columns
        fv_mars_next_yr_ = fv_mars_next_yr.copy()
        fv_mars_next_yr_ = fv_mars_next_yr_.reindex(fv_price_next_yr.index)
        fv_mars_next_yr_.columns = fv_price_next_yr.columns
        fv_price_next_yr = fv_price_next_yr / val[1] - (fv_lls_next_yr_ + fv_mars_next_yr_)/2
        fv_price_next_yr.fillna(method="ffill", inplace=True)
        df_fv_next_yr_daily[key] = fv_price_next_yr.mean(axis=1)
        fv_price_next_yr = fv_price_next_yr.iloc[[-1], :]
        fv_price_next_yr.columns = cols
        df_fv_next_yr[key] = fv_price_next_yr.T.reindex(
            pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        fv_price_10 = bbg.bdh(next_10_ticker, ["PX_LAST"], margins.index[-1] - dt.timedelta(364), margins.index[-1])
        fv_lls_1 = fv_lls_10.copy()
        fv_lls_1 = fv_lls_1.reindex(fv_price_10.index)
        fv_lls_1.columns = fv_price_10.columns
        fv_mars_1 = fv_mars_10.copy()
        fv_mars_1 = fv_mars_1.reindex(fv_price_10.index)
        fv_mars_1.columns = fv_price_10.columns
        fv_price_10 = fv_price_10 / val[1] - (fv_lls_1 + fv_mars_1)/2
        fv_price_10.fillna(method="ffill", inplace=True)
        fv_price_10.columns = [x.split(" ")[1] for x in next_10_ticker]
        nq1 = [x[0] for x in fv_price_10.columns].index(quarter_dict[next_q])
        fv_price_nq1 = fv_price_10.iloc[:, nq1:nq1+3].mean(axis=1)
        fv_price_nq2 = fv_price_10.iloc[:, nq1+3:nq1+6].mean(axis=1)
        fv_price_nq3 = fv_price_10.iloc[:, nq1+6:nq1+9].mean(axis=1)
        fv_price_mqy = pd.concat([fv_price_10.iloc[:, :3], fv_price_nq1, fv_price_nq2, fv_price_nq3,
                                  fv_price_10.iloc[:, -12:].mean(axis=1)], axis=1)
        fv_price_mqy.columns = list(fv_price_10.columns[:3]) + [f"Q{next_q}{fv_price_10.columns[nq1][-2:]}",
            f"Q{next_q1}{fv_price_10.columns[nq1+3][-2:]}", f"Q{next_q2}{fv_price_10.columns[nq1+6][-2:]}", f"{next_yr}"]
        df_fv_all[key] = pd.concat([df[key].to_frame("Spot").reindex(fv_price_10.index).fillna(method="ffill"), fv_price_mqy], axis=1)
    df_weight_fv = df_fv.copy()
    for key, val in weight_conversion.items():
        df_weight_fv[key] = val[0]
    margins_fv = (df_fv * df_weight_fv).sum(axis=1)
    margins_fv_7d = (df_fv_7d * df_weight_fv).sum(axis=1)
    margins_fv_next_yr = (df_fv_next_yr * df_weight_fv).sum(axis=1)
    margins_fv_next_yr_sep = (df_fv_next_yr_daily * df_weight.reindex(df_fv_next_yr_daily.index, method='ffill'))
    margins_fv_next_yr_sep.fillna(method="ffill", inplace=True)
    sdate = dt.datetime(2018, 1, 1)
    edate = dt.datetime(cur_yr, 12, 31)
    dts = pd.bdate_range(sdate, edate)
    dts_cur_yr = pd.bdate_range(dt.datetime(cur_yr, 1, 1), edate)
    margins = margins.reindex(dts)
    margins.fillna(method="ffill", inplace=True)
    margins.loc[margins.index >= today()] = np.nan
    margins_fv = margins_fv.reindex(dts_cur_yr)
    margins_fv_7d = margins_fv_7d.reindex(dts_cur_yr)
    margins_fv_next_yr = margins_fv_next_yr.reindex(dts_cur_yr)
    fig1 = chart.seasonal(
        df=margins.to_frame("Spot margins"), title="USGC margin not adjusted for natgas",
        highlight_dict={cur_yr: {"mode": "lines+markers", "color": "black", "width": 2}, },
        freq="B", drop_years=[2022], height=500, width=750)
    fig1.add_trace(go.Scatter(name="FWD", x=margins_fv.index, y=margins_fv, showlegend=True, mode="lines",
                             line=dict(color="red")))
    fig1.add_trace(go.Scatter(name="FWD 7d ago", x=margins_fv_7d.index, y=margins_fv_7d, showlegend=True, mode="lines",
                             line=dict(color="blue", dash="dash")))
    fig1.add_trace(go.Scatter(name=f"FWD {next_yr}", x=margins_fv_next_yr.index, y=margins_fv_next_yr, showlegend=True,
                             mode="lines", line=dict(color="red", dash="dash")))
    fig2_x = ["Margin 7d ago"] + list(margins_ind.columns) + ["Margin Today"]
    fig2_data = [margins_ind.sum(axis=1)[-6]] + (margins_ind.iloc[-1, :] - margins_ind.iloc[-6, :]).to_list() + [margins_ind.sum(axis=1)[-1]]
    fig2 = go.Figure(go.Waterfall(
        name="margin", orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "absolute"],
        x=fig2_x, y=fig2_data, width=0.5, textposition="outside", text=["{:.2f}".format(x) for x in fig2_data]))
    fig2.update_layout(
        title={"text": "Cash margin change week over week", "x": 0.5, "xanchor": "center"},
        showlegend=False, width=750, height=510,
        yaxis_range=[int(np.max(fig2_data) / 3 * 2), int(np.max(fig2_data) + 2)])
    fig21_x = ["Margin 7d ago"] + list(margins_fv_next_yr_sep.columns) + ["Margin Today"]
    if margins_fv_next_yr_sep.shape[0] < 7:
        fig21_data = [margins_fv_next_yr_sep.sum(axis=1)[0]] + (
            margins_fv_next_yr_sep.iloc[-1, :] - margins_fv_next_yr_sep.iloc[0, :]).to_list() + [
            margins_fv_next_yr_sep.sum(axis=1)[-1]]
    else:
        fig21_data = [margins_fv_next_yr_sep.sum(axis=1)[-6]] + (
            margins_fv_next_yr_sep.iloc[-1, :] - margins_fv_next_yr_sep.iloc[-6, :]).to_list() + [
            margins_fv_next_yr_sep.sum(axis=1)[-1]]
    fig21 = go.Figure(go.Waterfall(
        name="margin", orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "absolute"],
        x=fig21_x, y=fig21_data, width=0.5, textposition="outside", text=["{:.2f}".format(x) for x in fig21_data]))
    fig21.update_layout(
        title={"text": f"{next_yr} margin change week over week", "x": 0.5, "xanchor": "center"},
        showlegend=False, width=750, height=500,
        yaxis_range=[int(np.max(fig21_data) / 3 * 2), int(np.max(fig21_data) + 2)])
    fv_m2_ticker = {
        "Disti Crack": "FSGCM2 Index",
        "Jet Crack": "FSGJM2 Index",
        "Gasoline Crack": "FSCDM2 Index",
        "Naptha Crack": "FMBVM2 Index",
        "Propane Crack": "FSM3M2 Index",
        "Fuel Crack": "FSG3M2 Index",
    }
    crude_m2_ticker = {"LLS": "FSLDM2 Index", "Mars": "FSMCM2 Index"}
    fv_m2 = bbg.bdh(list(fv_m2_ticker.values()), ["PX_LAST"], today()-dt.timedelta(364), today())
    crude_m2 = bbg.bdh(list(crude_m2_ticker.values()), ["PX_LAST"], today()-dt.timedelta(364), today())
    crude_m2 = crude_m2.mean(axis=1)
    coversion = pd.Series([v[1] for v in weight_conversion.values()], index=fv_m2.columns)
    fv_m2 = (fv_m2 / coversion).sub(crude_m2, axis=0)
    fv_m2.columns = fv_m2_ticker.keys()
    fig3 = chart.line_chart(
        df=fv_m2[["Disti Crack", "Jet Crack", "Gasoline Crack"]], secondary_y=True,
        title="Second month USGC cracks", tickformat=False, width=750, height=500)
    fig3.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    fig31 = chart.line_chart(
        df=df_fv_next_yr_daily.loc[df_fv_next_yr_daily.index >= fv_m2.index[0], ["10ppm ULSD", "Jet", "Gasoline"]],
        secondary_y=True, title=f"{next_yr} USGC cracks fair value", tickformat=False, width=750, height=500)
    fig31.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5, itemwidth=30))
    cl26_ticker = bbg.live_spread_ticker(active='CLA Comdty', spread="26")
    cl_gen = pyg.get_data("contracts", active="CLA Comdty", item="PX_LAST_gen")
    cl26_price = (cl_gen.iloc[:, 1] - cl_gen.iloc[:, 5]).to_frame(cl26_ticker)
    fig4 = chart.line_chart(
        df=cl26_price.loc[cl26_price.index >= today() - dt.timedelta(364), :],
        title="WTI 2-6 spread", tickformat=False, width=750, height=500)
    fig4.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    tbs = []
    total_fv_10 = pd.DataFrame()
    for key, val in weight_conversion.items():
        if len(total_fv_10) == 0:
            total_fv_10 = df_fv_all[key] * val[0]
        else:
            total_fv_10 += df_fv_all[key] * val[0]
        tbs.append(fv_table(df_fv_all[key], key))
    tbs.insert(0, fv_table(total_fv_10, "Margin"))
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_missing_photo_text(699, "Weights: 10ppm ULSD - 32%, Jet - 11%, Gasoline - 44%, Naphtha - 9%, Propane - 2%, 3.5% FO"))
    figs.append([fig1, fig2, fig21])
    figs.append([fig3, fig31, fig4])
    figs = figs + tbs
    table.to_html(
        [table.html_text("USGC Refinery Margins", style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\refinery_margins_us.html")


def asia_margins():
    weight_conversion = {
        "10ppm ULSD": [0.38, 1, "FSG1M"],
        "50ppm Gasoil": [0.02, 1, "FSSGM"],
        "Jet": [0.08, 1, "FSSKM"],
        "Gasoline": [0.35, 1, "FSGAM"],
        "Naphtha": [0.06, 8.9, "FJPNM"],
        "Propane": [0.01, 12.11, "FPFEM"],
        "3.5% FO": [0.1, 6.35, "FSS3M"],
    }
    afo = pyg.get_data(db, platts_ticker="PPXDK00")
    ago = pyg.get_data(db, platts_ticker="AAOVC00")
    anap = pyg.get_data(db, platts_ticker="PAAAP00")
    agas = pyg.get_data(db, platts_ticker="AAXEQ00")
    agas_bbg = bbg.bdh("MOGFM925 Index", ["PX_LAST"], dt.datetime(2024, 7, 17), today()-BDay(1))
    agas = pd.concat([agas.loc[:"2024-07-16", :], agas_bbg-1.5], axis=0)
    ajet = pyg.get_data(db, platts_ticker="PJABF00")
    ago01 = pyg.get_data(db, platts_ticker="AAPPF00")
    dubai = pyg.get_data(db, platts_ticker="PCAAT00")
    data_dict = {
        "10ppm ULSD": ago,
        "50ppm Gasoil": ago01,
        "Jet": ajet,
        "Gasoline": agas,
        "Naphtha": anap * 8.9,
        "Propane": anap * 12.11,
        "3.5% FO": afo,
    }
    df = pd.DataFrame()
    for key, val in weight_conversion.items():
        df[key] = data_dict[key] / val[1] - dubai
    df.dropna(inplace=True)
    df_weight = df.copy()
    for key, val in weight_conversion.items():
        df_weight[key] = val[0]
    margins_ind = df * df_weight
    margins = (df * df_weight).sum(axis=1)
    gen_month = list(month_str2int.keys())
    cur_yr = today().year
    next_yr = today().year + 1
    cur_q = int((today().month - 1) / 3 + 1)
    next_q = (cur_q + 1) - 4 if cur_q >= 4 else cur_q + 1
    next_q1 = (next_q + 1) - 4 if next_q >= 4 else next_q + 1
    next_q2 = (next_q1 + 1) - 4 if next_q1 >= 4 else next_q1 + 1
    quarter_dict = {1: "F", 2: "J", 3: "N", 4: "V"}
    df_fv = pd.DataFrame()
    df_fv_7d = pd.DataFrame()
    df_fv_next_yr = pd.DataFrame()
    df_fv_next_yr_daily = pd.DataFrame()
    df_fv_all = {}
    cur_yr_ticker_dated = [f"FSDUM {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
    next_yr_ticker_dated = [f"FSDUM {x}{str(next_yr)[-2:]} Index" for x in gen_month]
    two_yr_ticker_dated = cur_yr_ticker_dated + next_yr_ticker_dated
    next_ticker_month = gen_month[np.mod(today().month, len(gen_month))]
    next_ticker_year = today().year if today().month < len(gen_month) else today().year + 1
    cur_ticker_index = two_yr_ticker_dated.index(f"FSDUM {next_ticker_month}{str(next_ticker_year)[-2:]} Index")
    next_10_ticker_dated = two_yr_ticker_dated[cur_ticker_index:cur_ticker_index+10]
    if margins.index[-1].month < 3:
        bbg_sdate = margins.index[-1] - dt.timedelta(60)
    else:
        bbg_sdate = dt.datetime(margins.index[-1].year, 1, 1)
    fv_dated = bbg.bdh(cur_yr_ticker_dated, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_dated_10 = bbg.bdh(next_10_ticker_dated, ["PX_LAST"], bbg_sdate, margins.index[-1])
    fv_dated_next_yr = bbg.bdh(next_yr_ticker_dated, ["PX_LAST"], bbg_sdate, margins.index[-1])
    for key, val in weight_conversion.items():
        cur_yr_ticker = [f"{val[2]} {x}{str(cur_yr)[-2:]} Index" for x in gen_month]
        next_yr_ticker = [f"{val[2]} {x}{str(next_yr)[-2:]} Index" for x in gen_month]
        two_yr_ticker = cur_yr_ticker + next_yr_ticker
        next_10_ticker = two_yr_ticker[cur_ticker_index:cur_ticker_index+10]
        cols = [dt.datetime(cur_yr, x+1, 1) + relativedelta(day=31) for x, _x in enumerate(gen_month)]
        fv_price = bbg.bdh(cur_yr_ticker, ["PX_LAST"], bbg_sdate, margins.index[-1])
        fv_dated_ = fv_dated.copy()
        fv_dated_ = fv_dated_.reindex(fv_price.index)
        fv_dated_.columns = fv_price.columns
        fv_price = fv_price / val[1] - fv_dated_
        fv_price.fillna(method="ffill", inplace=True)
        fv_price_1d = fv_price.iloc[[-1], :]
        if fv_price.shape[0] < 7:
            fv_price_7d = fv_price.iloc[[0], :]
        else:
            fv_price_7d = fv_price.iloc[[-7], :]
        fv_price_1d.columns = cols
        fv_price_7d.columns = cols
        df_fv[key] = fv_price_1d.T.reindex(pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        df_fv_7d[key] = fv_price_7d.T.reindex(pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        fv_price_next_yr_ori = bbg.bdh(next_yr_ticker, ["PX_LAST"], bbg_sdate, margins.index[-1])
        fv_price_next_yr = fv_price_next_yr_ori.copy()
        fv_dated_next_yr_ = fv_dated_next_yr.copy()
        fv_dated_next_yr_ = fv_dated_next_yr_.reindex(fv_price_next_yr.index)
        fv_dated_next_yr_.columns = fv_price_next_yr.columns
        fv_price_next_yr = fv_price_next_yr / val[1] - fv_dated_next_yr_
        fv_price_next_yr.fillna(method="ffill", inplace=True)
        df_fv_next_yr_daily[key] = fv_price_next_yr.mean(axis=1)
        fv_price_next_yr = fv_price_next_yr.iloc[[-1], :]
        fv_price_next_yr.columns = cols
        df_fv_next_yr[key] = fv_price_next_yr.T.reindex(
            pd.date_range(dt.datetime(cur_yr, 1, 1), dt.datetime(cur_yr, 12, 31))).fillna(method="bfill")
        fv_price_10 = bbg.bdh(next_10_ticker, ["PX_LAST"], margins.index[-1] - dt.timedelta(364), margins.index[-1])
        fv_dated_1 = fv_dated_10.copy()
        fv_dated_1 = fv_dated_1.reindex(fv_price_10.index)
        fv_dated_1.columns = fv_price_10.columns
        fv_price_10 = fv_price_10 / val[1] - fv_dated_1
        fv_price_10.fillna(method="ffill", inplace=True)
        fv_price_10.columns = [x.split(" ")[1] for x in next_10_ticker]
        nq1 = [x[0] for x in fv_price_10.columns].index(quarter_dict[next_q])
        fv_price_nq1 = fv_price_10.iloc[:, nq1:nq1+3].mean(axis=1)
        fv_price_nq2 = fv_price_10.iloc[:, nq1+3:nq1+6].mean(axis=1)
        fv_price_nq3 = fv_price_10.iloc[:, nq1+6:nq1+9].mean(axis=1)
        fv_price_mqy = pd.concat([fv_price_10.iloc[:, :3], fv_price_nq1, fv_price_nq2, fv_price_nq3,
                                  fv_price_10.iloc[:, -12:].mean(axis=1)], axis=1)
        fv_price_mqy.columns = list(fv_price_10.columns[:3]) + [f"Q{next_q}{fv_price_10.columns[nq1][-2:]}",
            f"Q{next_q1}{fv_price_10.columns[nq1+3][-2:]}", f"Q{next_q2}{fv_price_10.columns[nq1+6][-2:]}", f"{next_yr}"]
        df_fv_all[key] = pd.concat([df[key].to_frame("Spot").reindex(fv_price_10.index).fillna(method="ffill"), fv_price_mqy], axis=1)
    df_weight_fv = df_fv.copy()
    for key, val in weight_conversion.items():
        df_weight_fv[key] = val[0]
    margins_fv = (df_fv * df_weight_fv).sum(axis=1)
    margins_fv_7d = (df_fv_7d * df_weight_fv).sum(axis=1)
    margins_fv_next_yr = (df_fv_next_yr * df_weight_fv).sum(axis=1)
    margins_fv_next_yr_sep = (df_fv_next_yr_daily * df_weight.reindex(df_fv_next_yr_daily.index, method='ffill'))
    margins_fv_next_yr_sep.fillna(method="ffill", inplace=True)
    sdate = dt.datetime(2019, 1, 1)
    edate = dt.datetime(cur_yr, 12, 31)
    dts = pd.bdate_range(sdate, edate)
    dts_cur_yr = pd.bdate_range(dt.datetime(cur_yr, 1, 1), edate)
    margins = margins.reindex(dts)
    margins.fillna(method="ffill", inplace=True)
    margins.loc[margins.index >= today()] = np.nan
    margins_fv = margins_fv.reindex(dts_cur_yr)
    margins_fv_7d = margins_fv_7d.reindex(dts_cur_yr)
    margins_fv_next_yr = margins_fv_next_yr.reindex(dts_cur_yr)
    fig1 = chart.seasonal(
        df=margins.to_frame("Spot margins"), title="Asia margin not adjusted for natgas",
        highlight_dict={cur_yr: {"mode": "lines+markers", "color": "black", "width": 2}, },
        freq="B", drop_years=[2022], height=500, width=750)
    fig1.add_trace(go.Scatter(name="FWD", x=margins_fv.index, y=margins_fv, showlegend=True, mode="lines",
                             line=dict(color="red")))
    fig1.add_trace(go.Scatter(name="FWD 7d ago", x=margins_fv_7d.index, y=margins_fv_7d, showlegend=True, mode="lines",
                             line=dict(color="blue", dash="dash")))
    fig1.add_trace(go.Scatter(name=f"FWD {next_yr}", x=margins_fv_next_yr.index, y=margins_fv_next_yr, showlegend=True,
                             mode="lines", line=dict(color="red", dash="dash")))
    fig2_x = ["Margin 7d ago"] + list(margins_ind.columns) + ["Margin Today"]
    fig2_data = [margins_ind.sum(axis=1)[-6]] + (margins_ind.iloc[-1, :] - margins_ind.iloc[-6, :]).to_list() + [margins_ind.sum(axis=1)[-1]]
    fig2 = go.Figure(go.Waterfall(
        name="margin", orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "absolute"],
        x=fig2_x, y=fig2_data, width=0.5, textposition="outside", text=["{:.2f}".format(x) for x in fig2_data]))
    fig2.update_layout(
        title={"text": "Cash margin change week over week", "x": 0.5, "xanchor": "center"},
        showlegend=False, width=750, height=510,
        yaxis_range=[int(np.max(fig2_data) / 2), int(np.max(fig2_data) + 2)])
    fig21_x = ["Margin 7d ago"] + list(margins_fv_next_yr_sep.columns) + ["Margin Today"]
    if margins_fv_next_yr_sep.shape[0] < 7:
        fig21_data = [margins_fv_next_yr_sep.sum(axis=1)[0]] + (
            margins_fv_next_yr_sep.iloc[-1, :] - margins_fv_next_yr_sep.iloc[0, :]).to_list() + [
            margins_fv_next_yr_sep.sum(axis=1)[-1]]
    else:
        fig21_data = [margins_fv_next_yr_sep.sum(axis=1)[-6]] + (
            margins_fv_next_yr_sep.iloc[-1, :] - margins_fv_next_yr_sep.iloc[-6, :]).to_list() + [
            margins_fv_next_yr_sep.sum(axis=1)[-1]]
    fig21 = go.Figure(go.Waterfall(
        name="margin", orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "absolute"],
        x=fig21_x, y=fig21_data, width=0.5, textposition="outside", text=["{:.2f}".format(x) for x in fig21_data]))
    fig21.update_layout(
        title={"text": f"{next_yr} margin change week over week", "x": 0.5, "xanchor": "center"},
        showlegend=False, width=750, height=500,
        yaxis_range=[int(np.max(fig21_data) / 3 * 2), int(np.max(fig21_data) + 2)])
    fv_m2_ticker = {
        "GO Crack": "FSQCM2 Index",
        "Naptha Crack": "JADCM2 Index",
        "Gasoline Brent Crack": "G92BM2 PVMO Index",
        "Fuel Crack": "F38CM2 Index",
        "Jet regrade": "DRJKM2 PVMO Index",
        "GO E/W": "GOEWM2 PVMO Index",
        "Brent/Dubai": "FDUSM1 Index",
    }
    fv_m2 = bbg.bdh(list(fv_m2_ticker.values()), ["PX_LAST"], today()-dt.timedelta(364), today())
    fv_m2.columns = fv_m2_ticker.keys()
    fv_m2['Disty Crack'] = fv_m2['GO Crack'] + fv_m2["GO E/W"] / 7.45 + fv_m2["Brent/Dubai"]
    fv_m2['Jet Crack'] = fv_m2['Disty Crack'] + fv_m2["Jet regrade"]
    fv_m2['Gasoline Crack'] = fv_m2['Gasoline Brent Crack'] + fv_m2["Brent/Dubai"]
    fig3 = chart.line_chart(
        df=fv_m2[["Disty Crack", "Jet Crack", "Gasoline Crack"]], secondary_y=True,
        title="Second month Asia cracks", tickformat=False, width=750, height=500)
    fig3.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    annual_tickers = []
    for k, v in fv_m2_ticker.items():
        yr = str(today().year + 1)[-2:]
        if k == "Gasoline Brent Crack":
            annual_tickers.append(f"{v.split(' ')[0][:-2]}Y {yr} MRXI Index")
        else:
            annual_tickers.append(f"{v.split(' ')[0][:-2]}Y {yr} {v.partition(' ')[-1]}")
    fv_y2 = _missing_photo_text(958, 'annual_tickers', annual_tickers)
    fv_y2.columns = fv_m2_ticker.keys()
    if dt.datetime(2025, 4, 1) in fv_y2.index:
        fv_y2.loc[dt.datetime(2025, 4, 1), "GO E/W"] = -11.25
    fv_y2['Disty Crack'] = fv_y2['GO Crack'] + fv_y2["GO E/W"] / 7.45 + fv_y2["Brent/Dubai"]
    fv_y2['Jet Crack'] = fv_y2['Disty Crack'] + fv_y2["Jet regrade"]
    fv_y2['Gasoline Crack'] = fv_y2['Gasoline Brent Crack'] + fv_y2["Brent/Dubai"]
    fig31 = chart.line_chart(
        df=fv_y2[["Disty Crack", "Jet Crack", "Gasoline Crack"]], secondary_y=True,
        title=f"{next_yr} Asia cracks fair value", tickformat=False, width=750, height=500)
    fig31.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5, itemwidth=30))
    dat24_ticker = bbg.live_spread_ticker(active='DATA Comdty', spread="24")
    dat24_price = bbg.bdh(dat24_ticker, ["PX_LAST"], today() - dt.timedelta(364), today())
    fig4 = chart.line_chart(
        df=dat24_price, title="Dubai 2-4 spread", tickformat=False, width=750, height=500)
    fig4.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    tbs = []
    total_fv_10 = pd.DataFrame()
    for key, val in weight_conversion.items():
        if len(total_fv_10) == 0:
            total_fv_10 = df_fv_all[key] * val[0]
        else:
            total_fv_10 += df_fv_all[key] * val[0]
        tbs.append(fv_table(df_fv_all[key], key))
    tbs.insert(0, fv_table(total_fv_10, "Margin"))
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(_missing_photo_text(1013, "Weights: 10ppm ULSD - 38%, 50ppm Gasoil - 2%, Jet - 8%, Gasoline - 35%, Naphtha - 6%, Pro"))
    figs.append([fig1, fig2, fig21])
    figs.append([fig3, fig31, fig4])
    figs = figs + tbs
    table.to_html(
        [table.html_text("Asia Refinery Margins", style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\refinery_margins_asia.html", task_name=report_name)


def update():
    log.info("Starting refinery margins report update")
    overall_start = time.time()
    eu_margins()
    log.info(f"EU margins updated in {time.time() - overall_start:.2f}s")
    us_margins()
    log.info(f"US margins updated in {time.time() - overall_start:.2f}s")
    asia_margins()
    log.info(f"Asia margins updated in {time.time() - overall_start:.2f}s")
    log.info(f"Report update completed in {time.time() - overall_start:.2f}s total")


if __name__ == "__main__":
    update()
