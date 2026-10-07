import pandas as pd
import datetime as dt
from ecm.cmds.config import root_path
import sys
import itertools
sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")
import cot_data as cot_data_module
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path
from ecm.cmds.cdr import today

import ecm.cmds.cot as cot
import ecm.cmds.pyg as pyg
import ecm.cmds.rvx as rvx
import ecm.cmds.bbg as bbg
from ecm.cmds.config import url
from pyg_cell import *
from functools import partial
from pyg_mongo import mongo_table
import plotly.graph_objects as go
from cot_cme import gen_figures, get_px_chart, get_px_chart_single, get_pos_chart, get_pos_vs_px_change_chart

send_to = ["mkikano@elementcapital.com", "rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "COT - LME"
file_name = "cot_lme"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\positioning\\{file_name}.py"
chart_sdate = dt.datetime(2018, 1, 1)

cot_dict = {
    'Global Copper': {
        'IFLFO': 'CTCTMHZA Index',
        'IFSFO': 'CTCTGKLQ Index',
        'OFLFO': 'CTCTAEGX Index',
        'OFSFO': 'CTCTSQPV Index',
    },
    'LPA Comdty': {
        'IFLFO': 'CTCTMHZA Index',
        'IFSFO': 'CTCTGKLQ Index',
        'OFLFO': 'CTCTAEGX Index',
        'OFSFO': 'CTCTSQPV Index',
    },
    'HGA Comdty': {
        'MMLF': 'CFFDTMML Index',
        'MMSF': 'CFFDTMMS Index',
        'MMLFO': 'CFCDTMML Index',
        'MMSFO': 'CFCDTMMS Index',
        'OIFO': 'CMXOCOIN Index',
        'OIF': 'CEI1COIN Index',
        'NCLF': 'CEI1CNCL Index',
        'NCSF': 'CEI1CNCS Index',
        'NCLFO': 'CMXOCNCL Index',
        'NCSFO': 'CMXOCNCS Index',
    },
    'LAA Comdty': {
        'IFLFO': 'AHCTMHZA Index',
        'IFSFO': 'AHCTGKLQ Index',
        'OFLFO': 'AHCTAEGX Index',
        'OFSFO': 'AHCTSQPV Index',
    },
    'LNA Comdty': {
        'IFLFO': 'NICTMHZA Index',
        'IFSFO': 'NICTGKLQ Index',
        'OFLFO': 'NICTAEGX Index',
        'OFSFO': 'NICTSQPV Index',
    },
    'LXA Comdty': {
        'IFLFO': 'ZSCTMHZA Index',
        'IFSFO': 'ZSCTGKLQ Index',
        'OFLFO': 'ZSCTAEGX Index',
        'OFSFO': 'ZSCTSQPV Index',
    },
    'LLA Comdty': {
        'IFLFO': 'PBCTMHZA Index',
        'IFSFO': 'PBCTGKLQ Index',
        'OFLFO': 'PBCTAEGX Index',
        'OFSFO': 'PBCTSQPV Index',
    },
    'LTA Comdty': {
        'IFLFO': 'SYCTMHZA Index',
        'IFSFO': 'SYCTGKLQ Index',
        'OFLFO': 'SYCTAEGX Index',
        'OFSFO': 'SYCTSQPV Index',
    },
}

lme_dict = {
    "LPA Comdty": "LMCADS03 LME Comdty",
    "LAA Comdty": "LMAHDS03 LME Comdty",
    "LXA Comdty": "LMZSDS03 LME Comdty",
    "LNA Comdty": "LMNIDS03 LME Comdty",
    "LLA Comdty": "LMPBDS03 LME Comdty",
    "LTA Comdty": "LMSNDS03 LME Comdty",
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
        days=Days.TUESDAY,
        start_datetime=dt.datetime(2022, 7, 1, 11, 15, 0),
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


def vwap_lme(active):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    try:
        c = pyg.get_cell(db, active=active, item="VWAP")
        db().inc(_id=c._id).drop()
    except:
        pass
    c = periodic_cell(
        function=cot.vwap_lme,
        active=active,
        item="VWAP",
        ticker=active,
        db=db,
        period="3n",
    )
    c.go()


def all_vwaps_lme():
    for k, v in lme_dict.items():
        vwap_lme(v)


def update(send_to):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    old = pyg.get_data(db, active="LPA Comdty", item="IFLFO")
    new = bbg.bdh("CTCTMHZA Index", ["PX_LAST"], sdate=today() - dt.timedelta(28), edate=today())
    dts = pd.bdate_range(dt.datetime(2018, 1, 1), today())
    chart_links = []
    px_vs_pos_chart_data = {}
    if old.index[-1] < new.index[-1]:
        cot_data_module.update_lme(latest=new.index[-1])
        cot_table = pd.DataFrame()
        figs_net = []
        figs_ls = []
        for active in cot_dict.keys():
            if active == "Global Copper":
                active_ = "LPA Comdty"
            else:
                active_ = active
            raise NotImplementedError("Missing CTA query dates: IMG_4612 line 168")
            if active == "HGA Comdty":
                c1 = pyg.get_cell(db, active=active_, item="MMLFO")
                c2 = pyg.get_cell(db, active=active_, item="MMSFO")
                c5 = pyg.get_cell(db, active=active_, item="OIFO").go()
                long = c1.data.reindex(dts, method="ffill").reindex(long.index) / 2.2
                short = c2.data.reindex(dts, method="ffill").reindex(short.index) / 2.2
                oi = c5.data.reindex(dts, method="ffill").reindex(oi.index) / 2.2
                long1 = None
                short1 = None
            else:
                c1 = pyg.get_cell(db, active=active_, item="IFLFO")
                c2 = pyg.get_cell(db, active=active_, item="IFSFO")
                c3 = pyg.get_cell(db, active=active_, item="OFLFO")
                c4 = pyg.get_cell(db, active=active_, item="OFSFO")
                c5 = pyg.get_cell(db, active=active_, item="OIFO").go()
                long = c1.data
                short = c2.data
                long1 = c3.data
                short1 = c4.data
                oi = c5.data
            if active == "Global Copper":
                long2 = bbg.bdh("CFCDTMML Index", ["PX_LAST"], dt.datetime(2018, 1, 1), today()) / 2.2
                short2 = bbg.bdh("CFCDTMMS Index", ["PX_LAST"], dt.datetime(2018, 1, 1), today()) / 2.2
                oi2 = bbg.bdh("CMXOCOIN Index", ["PX_LAST"], dt.datetime(2018, 1, 1), today()) / 2.2
                oi2.columns = oi.columns
                long = (long.reindex(dts, method="ffill") + long2.reindex(dts, method="ffill")).reindex(long.index)
                short = (short.reindex(dts, method="ffill") + short2.reindex(dts, method="ffill")).reindex(short.index)
                oi = (oi.reindex(dts, method="ffill") + oi2.reindex(dts, method="ffill")).reindex(oi.index)
            if active == "HGA Comdty":
                c6 = pyg.get_cell(db, active=active_, item="VWAP").go()
            else:
                c6 = pyg.get_cell(db, active=lme_dict[active_], item="VWAP").go()
            vp = c6.data
            ref = pyg.get_data("contracts", active=active_, item="ref")
            df_ = cot.analysis_mifid(active=active, type="Fut,Opt", vwap=vp, ref=ref, long=long, short=short, oi=oi, long1=long1, short1=short1, cta=cta)
            if active == "HGA Comdty":
                df_.columns = [cot_table.columns[0]] + list(df_.columns[1:])
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)

            if long1 is not None:
                long = long + long1
            if short1 is not None:
                short = short + short1
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
            fig1, fig2 = gen_figures(active, cot_data, cta)
            if active not in ["Global Copper"]:
                single_px_fig = get_px_chart_single(active, cot_start=pd.to_datetime(cot_table[-1:]._last_update.iloc[-1]) - pd.DateOffset(days=7))
                px_vs_pos_chart_data[active] = cot_data
                figs_net.append([fig1, single_px_fig])
            else:
                figs_net.append([fig1, ""])
            figs_ls.append(fig2)
            raise NotImplementedError("Missing regression chart arguments: IMG_4613 lines 235-236")
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f"{html_path}\\positioning\\links\\{active}_chart.html")
            chart_links.append(f'<a href="{html_path}\\positioning\\links\\{active}_chart.html">{df_.iloc[0, 0]}</a>')

        figs = []
        figs.append(table.html_text(f'<a href="{html_path}\\positioning\\position_lme.html">Main Page</a>'))
        figs.append(table.html_text(f"CMX is LME Equivalent"))
        raise NotImplementedError("Missing table-format tails: IMG_4614 lines 252-279")
        lme_html_table = table.html_format(
            df=cot_table,
            header="Speculators Net Position (Investment Funds)",
            footer=None,
            show_date=False,
            format_column={
                "0": {"width": "120px", "text-align": "left"},  # highlight: [0, "net pos rank", "_thr_high", ...]
                "1": {"width": "60px", "text-align": "center"},
                "2": {"width": "60px", "text-align": "center", "format": "{:.1%}"},  # highlight: [2, "net/oi ...]
                "3": {"width": "60px", "text-align": "center", "format": "{:.1%}"},  # highlight: ...
                "4": {"width": "60px", "text-align": "center", "format": "{:.2f}", "right_border": True},
                "5": {"width": "60px", "text-align": "center", "format": "{:.2f}"},
                "6": {"width": "60px", "text-align": "center", "bold": True},  # highlight: [6, "net change z ...]
                "7": {"width": "60px", "text-align": "center"},
                "8": {"width": "60px", "text-align": "center"},
                "9": {"width": "60px", "text-align": "center", "right_border": True},
                "10": {"width": "60px", "text-align": "center", "format": "{:.1%}"},  # highlight: ...
                "11": {"width": "60px", "text-align": "center"},  # highlight: [11, "4w delta chan...]
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

        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        cot_start = pd.to_datetime(cot_table[-1:]._last_update.iloc[-1]) - pd.DateOffset(days=7)
        px_chart = get_px_chart(name="BM", cot_start=cot_start)
        pos_chart = get_pos_chart(name="BM", data_dict=px_vs_pos_chart_data)
        for _idx, i in enumerate(chart_links):
            if not pd.isna(cot_table.iloc[_idx, 0]):
                lme_html_table = lme_html_table.replace(cot_table.iloc[_idx, 0], i)
        figs.append(lme_html_table)
        figs_email = figs + [plots_email]
        figs_email.append('<a href="{:s}\\positioning\\position_lme.html">Position Charts</a><br><br>'.format(html_path))
        raise NotImplementedError("Missing HTML output arguments: IMG_4614 lines 295-296")
        send_email(send_to=send_to, subject=report_name, body=figs_email, html_path=f"{html_path}\\positioning\\position_lme.html")


if __name__ == "__main__":
    raise NotImplementedError("Incomplete configured recipient list: IMG_4610 line 26")
    update(send_to=send_to)
