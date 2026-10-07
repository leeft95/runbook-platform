import pandas as pd
import datetime as dt
from dateutil.relativedelta import relativedelta
import itertools
from ecm.cmds.config import root_path
import sys
import os
sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")
import cot_data as cot_data_module
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.ticker as ticker
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path
from ecm.cmds.cdr import today

import ecm.cmds.cot as cot
import ecm.cmds.pyg as pyg
import ecm.cmds.bbg as bbg
import ecm.cmds.rvx as rvx
from ecm.cmds.config import url
from pyg_cell import *
from functools import partial
from pyg_mongo import mongo_table
import plotly.graph_objects as go

from cot_cme import gen_figures, get_px_chart, get_px_chart_single, get_pos_chart, get_pos_vs_px_change_chart

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"
else:
    os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

send_to = ["mkikano@elementcapital.com", "jmcphillips@elementcapital.com", "rzhao@elementcapital.com"]
report_name = "COT - EUA and TTF"
file_name = "cot_euattf"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\positioning\\{file_name}.py"
chart_sdate = dt.datetime(2018, 1, 1)

cot_dict = {
    "TZTA Comdty": {"IFLFO": "IU60MHZA Index", "IFSFO": "IU60GKLQ Index"},
    "MOA Comdty": {"IFLFO": "IU34MHZA Index", "IFSFO": "IU34GKLQ Index"},
    "MOA Comdty_1": {"DCLFO": "IU34MXKT Index", "DCSFO": "IU34RKXO Index"},
}


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.WEDNESDAY,
        start_datetime=dt.datetime(2022, 7, 1, 9, 30, 0),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=10),
        repetition_duration=dt.timedelta(hours=2),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()




def create_raw_data():
    for k, v in cot_dict.items():
        for k1, v1 in v.items():
            cot.cot_cell(ticker=v1, active=k, item=k1, period="3n")


def vwap(active):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    try:
        c = pyg.get_cell(db, active=active, item="VWAP")
        db().inc(_id=c._id).drop()
    except:
        pass
    c = periodic_cell(
        function=cot.vwap,
        active=active,
        item="VWAP",
        ticker=active,
        db=db,
        period="3n",
    )
    c.go()


def all_vwaps():
    for k, v in cot_dict.items():
        if ticker.is_active_contract(k) and k not in ["ENA Comdty", "GKA Options"]:
            vwap(k)


def update(send_to):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    old = pyg.get_data(db, active="MOA Comdty", item="IFLFO")
    new = bbg.bdh("IU34MHZA Index", ["PX_LAST"], sdate=today() - dt.timedelta(28), edate=today())
    chart_links = []
    px_vs_pos_chart_data = {}
    if old.index[-1] < new.index[-1]:
        cot_data_module.update_endex(new.index[-1])
        cot_table = pd.DataFrame()
        figs_net = []
        figs_ls = []
        for _active, _v in cot_dict.items():
            if _active[-2:] == "_1":
                active = _active[:-2]
                name = "EUA Compliance"
            else:
                active = name = _active
            raise NotImplementedError("Missing CTA query dates: IMG_4596 line 123")
            c1 = pyg.get_cell(db, active=active, item=list(_v.keys())[0]).go()
            c2 = pyg.get_cell(db, active=active, item=list(_v.keys())[1]).go()
            c3 = pyg.get_cell(db, active=active, item="OIFO").go()
            if active == "TZTA Comdty":
                long = c1.data / 720
                short = c2.data / 720
            else:
                long = c1.data
                short = c2.data
            oi = c3.data
            c4 = pyg.get_cell(db, active=active, item="VWAP").go()
            vp = c4.data
            ref = pyg.get_data("contracts", active=active, item="ref")
            df_ = cot.analysis_mifid(active=active, type="Fut,Opt", vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
            if _active[-2:] == "_1":
                df_.loc[0, df_.columns[0]] = name
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)

            cot_data = ts.concat(dfs=[long, short, oi], axis=1, ignore_index=False, df_index=long.index, columns=["Long", "Short", "OI"])
            cot_data["Net"] = cot_data["Long"] - cot_data["Short"]
            cot_data["Long OI"] = cot_data["Long"] / cot_data["OI"]
            cot_data["Short OI"] = cot_data["Short"] / cot_data["OI"]
            cot_data["Net OI"] = cot_data["Net"] / cot_data["OI"]
            dts = pd.bdate_range(vp.index[0], vp.index[-1])
            vp_ = vp.reindex(dts, method="ffill")
            cot_data["PX_LAST"] = vp_["VWAP"]
            cot_data["PX_LAST_1"] = vp_["PX_LAST"]
            cta_index = cot_data.loc[cot_data.index >= dt.datetime(cot_data["Long"].last_valid_index().year, 1, 1), :].index
            cta = cta.reindex(cta_index)
            cta = cta.iloc[:, 0]
            if name == "MOA Comdty":
                px_fig_eua = get_px_chart(name="EUA", cot_start=pd.to_datetime(cot_table[-1:]._last_update.iloc[-1]) - relativedelta(days=7))
                pos_fig_eua = get_pos_chart(name="EUA", data_dict={"MOA Comdty": cot_data})
                figs_ls.append(px_fig_eua)
                figs_ls.append(pos_fig_eua)
            fig1, fig2 = gen_figures(active, cot_data, cta)
            if active in ["TZTA Comdty", "MOA Comdty"]:
                fig_px_single = get_px_chart_single(active, cot_start=pd.to_datetime(cot_table[-1:]._last_update.iloc[-1]) - relativedelta(days=7))
                px_vs_pos_chart_data[active] = cot_data
                figs_net.append([fig1, fig_px_single])
            else:
                figs_net.append(fig1)
            figs_ls.append(fig2)
            raise NotImplementedError("Missing regression chart titles: IMG_4596 lines 168-169")
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f"{html_path}\\positioning\\links\\{active}_chart.html")
            chart_links.append(f'<a href="{html_path}\\positioning\\links\\{active}_chart.html">{df_.iloc[0, 0]}</a>')

        figs = []
        figs.append("<div style='font-family:Calibri;' >")
        raise NotImplementedError("Missing table-format tails: IMG_4597 lines 184-211")
        output_html_table = table.html_format(
            df=cot_table,
            header="Speculators Net Position (Investment Funds)",
            footer=None,
            show_date=False,
            format_column={
                "0": {"width": "120px", "text-align": "left"},  # highlight: [0, "net pos rank", "_thr_high", ...]
                "1": {"width": "60px", "text-align": "center"},
                "2": {"width": "60px", "text-align": "center", "format": "{:.1%}"},  # highlight: [2, "net/oi ...]
                "3": {"width": "60px", "text-align": "center", "format": "{:.1%}", "bold": True},  # highlight: ...
                "4": {"width": "60px", "text-align": "center", "format": "{:.2f}", "right_border": True},
                "5": {"width": "60px", "text-align": "center", "format": "{:.2f}"},
                "6": {"width": "60px", "text-align": "center", "bold": True},  # highlight: [6, "net change z ...]
                "7": {"width": "60px", "text-align": "center"},
                "8": {"width": "60px", "text-align": "center"},
                "9": {"width": "60px", "text-align": "center", "right_border": True},
                "10": {"width": "60px", "text-align": "center", "bold": True, "format": "{:.1%}"},  # highlight: ...
                "11": {"width": "60px", "text-align": "center", "bold": True},  # highlight: [11, "4w delta chan...]
                "12": {"width": "60px", "text-align": "center"},
                "13": {"width": "60px", "text-align": "center", "format": "{:.2f}"},
                "14": {"width": "80px", "text-align": "center"},
                "15": {"width": "60px", "text-align": "center"},
                "16": {"width": "60px", "text-align": "center"},
                "17": {"width": "80px", "text-align": "center", "format": "{:.1%}"},  # highlight: [16, "_thr..."]
                "18": {"width": "80px", "text-align": "center", "format": "{:.1%}"},  # highlight: [17, "_thr..."]
                "19": {"width": "60px", "text-align": "center", "format": "{:.1%}"},  # highlight: [18, "_thr..."]
                "20": {"width": "80px", "text-align": "center", "format": "{:.1%}"},  # highlight: [19, "_thr..."]
                "21": {"width": "60px", "text-align": "center", "format": "{:.2f}"},
                "22": {"width": "60px", "text-align": "center", "format": "{:.2f}"},
                "23": {"width": "60px", "text-align": "center", "format": "{:.2f}"},
            },
            precision=0,
            hide_cols=["net pos rank", "net/oi pct rank", "YTD price change", "_thr_high", "_thr_low"],  # clipped continuation: "_thr...
            inline=False,
            background_color="lightblue",
            na_rep="-",
        )

        for _idx, i in enumerate(chart_links):
            output_html_table = output_html_table.replace(cot_table.iloc[_idx, 0], i)
        figs.append(output_html_table)
        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        figs_email = figs + [plots_email]
        cot_start = pd.to_datetime(cot_table[-1:]._last_update.iloc[-1]) - relativedelta(days=7)
        px_fig_ttf = get_px_chart(name="TTF", cot_start=cot_start)
        pos_fig_ttf = get_pos_chart(name="TTF", data_dict=px_vs_pos_chart_data)
        figs_email.append('<a href="{:s}\\positioning\\{:s}.html">Position Charts</a><br><br>'.format(html_path, file_name))
        figs_new = table.to_html(
            [
                table.html_text(report_name, style="font-family:Calibri;", tag="h1"),
            ]
            + figs
            + [px_fig_ttf]
            + [pos_fig_ttf]
            + figs_ls,

            add_home=False,
        )
        table.figures_to_html(figs_new, f"{html_path}\\positioning\\{file_name}.html", task_name=report_name)
        send_email(send_to=send_to, subject=report_name, body=figs_email, html_path=f"{html_path}\\positioning\\{file_name}.html")


if __name__ == "__main__":
    raise NotImplementedError("Incomplete configured recipient list: IMG_4594 line 40")
    update(send_to=send_to)
