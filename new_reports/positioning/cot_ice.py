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
import ecm.cmds.ticker as tk
from ecm.cmds.config import url
from pyg_cell import *
from functools import partial
from pyg_mongo import mongo_table
import plotly.graph_objects as go
from cot_cme import gen_figures, get_px_chart, get_px_chart_single, get_pos_chart, get_pos_vs_px_change_chart

send_to = ["mkikano@elementcapital.com", "rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "COT - ICE"
file_name = "cot_ice"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\positioning\\{file_name}.py"
chart_sdate = dt.datetime(2018, 1, 1)

cot_dict = {
    'COA Comdty': {
        'MMLF': 'ICFUBMML Index',
        'MMSF': 'ICFUBMMS Index',
        'MMLFO': 'ICCBBMML Index',
        'MMSFO': 'ICCBBMMS Index',
        'OIFO': 'ICCBBOIN Index',
        'OIF': 'ICFUBOIN Index',
        'SDLF': 'ICFUBSWL Index',
        'SDSF': 'ICFUBSWS Index',
        'SDLFO': 'ICCBBSWL Index',
        'SDSFO': 'ICCBBSWS Index',
    },
    'QSA Comdty': {
        'MMLF': 'ICFUAMML Index',
        'MMSF': 'ICFUAMMS Index',
        'MMLFO': 'ICCBAMML Index',
        'MMSFO': 'ICCBAMMS Index',
        'OIFO': 'ICCBAOIN Index',
        'OIF': 'ICFUAOIN Index',
        'SDLF': 'ICFUASWL Index',
        'SDSF': 'ICFUASWS Index',
        'SDLFO': 'ICCBASWL Index',
        'SDSFO': 'ICCBASWS Index',
    },
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
        days=Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 17, 30, 0),
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


def update(send_to):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    old = pyg.get_data(db, active="COA Comdty", item="MMLFO")
    new = bbg.bdh("ICCBBMML Index", ["PX_LAST"], sdate=today() - dt.timedelta(28), edate=today())
    chart_links = {}
    px_vs_pos_chart_data = {}
    if old.index[-1] < new.index[-1]:
        cot_data_module.update_ice(latest=new.index[-1])
        cot_table = pd.DataFrame()
        figs_net = []
        figs_ls = []
        for active in cot_dict.keys():
            cta = rvx.rvx(
                ticker=f"CTA LN4 CM EN {active.split('A Comdty')[0]}_COMDTY",
                field="SIGNAL",
                sdate=f"2023-01-01",
                edate=today()
            )
            c1 = pyg.get_cell(db, active=active, item="MMLF")
            c2 = pyg.get_cell(db, active=active, item="MMSF")
            c3 = pyg.get_cell(db, active=active, item="OIF")
            c4 = pyg.get_cell(db, active=active, item="MMLFO")
            c5 = pyg.get_cell(db, active=active, item="MMSFO")
            c6 = pyg.get_cell(db, active=active, item="OIFO")
            c7 = pyg.get_cell(db, active=active, item="VWAP").go()
            vp = c7.data
            ref = pyg.get_data("contracts", active=active, item="ref")
            long = c1.data
            short = c2.data
            oi = c3.data
            df_ = cot.analysis(active=active, type="Fut", vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            long = c4.data
            short = c5.data
            oi = c6.data
            df_ = cot.analysis(active=active, type="Fut,Opt", vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
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
            cta_index = cot_data.loc[cot_data.index >= dt.datetime(today().year, 1, 1), :].index
            cta = cta.reindex(cta_index)
            cta = cta.iloc[:, 0]
            fig1, fig2 = gen_figures(active, cot_data, cta)
            single_px_figure = get_px_chart_single(active, cot_start=pd.to_datetime(cot_table.iloc[:, -1].dropna().iloc[-1]))
            px_vs_pos_chart_data[active] = cot_data
            figs_net.append([fig1, single_px_figure])
            figs_ls.append(fig2)
            raise NotImplementedError("Missing regression chart arguments: IMG_4606 lines 150-151")
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f"{html_path}\\positioning\\links\\{active}_chart.html")
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{active}_chart.html">{df_.iloc[0, 0]}</a>'

        figs = []
        figs.append("<div style='font-family:Calibri;' >")
        raise NotImplementedError("Missing table-format tails: IMG_4606/4607 lines 166-189")
        output_html_table = table.html_format(
            df=cot_table,
            header="Speculators Net Position (Managed money)",
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
            hide_cols=["net pos rank", "net/oi pct rank",
                       "YTD price change", "_thr_high", "_thr_low", "_thr_high8", "_thr_low8", "_thr_net",
                       "_z_high", "_z_low", "_price_chg", "_last_update"],
            inline=False,
            background_color="lightblue",
            na_rep="-",
        )

        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        figs.append(output_html_table)
        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        figs_email = figs + [plots_email]
        px_fig = get_px_chart(name="ICE", cot_start=pd.to_datetime(cot_table.iloc[:, -1].dropna().iloc[-1]))
        pos_fig = get_pos_chart(name="ICE", data_dict=px_vs_pos_chart_data)
        figs_email.append(
            u'<a href="{:s}\\positioning\\{:s}.html">Position Charts</a><br><br>'.format(
                html_path, file_name))
        raise NotImplementedError("Missing HTML composition: IMG_4607 line 210")
        table.figures_to_html(figs_new, f"{html_path}\\positioning\\{file_name}.html", task_name=report_name)
        send_email(send_to=send_to, subject=report_name, body=figs_email, html_path=f"{html_path}\\positioning\\{file_name}.html")
        print(f"Updated to {new.index[-1].strftime('%Y-%m-%d')}")
        pyg.get_cell(db, active="COA Comdty", item="MMLFO").go()
    else:
        print(f"No new data. Last release is {new.index[-1].strftime('%Y-%m-%d')}")


def update_dealer(send_to):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    old = pyg.get_data(db, active="COA Comdty", item="SDLFO")
    new = bbg.bdh("ICCBBSWL Index", ["PX_LAST"], sdate=today() - dt.timedelta(28), edate=today())
    chart_links = {}
    if old.index[-1] < new.index[-1]:
        cot_table = pd.DataFrame()
        figs_net = []
        figs_ls = []
        for active in cot_dict.keys():
            c1 = pyg.get_cell(db, active=active, item="SDLF")
            c2 = pyg.get_cell(db, active=active, item="SDSF")
            c3 = pyg.get_cell(db, active=active, item="OIF")
            c4 = pyg.get_cell(db, active=active, item="SDLFO")
            c5 = pyg.get_cell(db, active=active, item="SDSFO")
            c6 = pyg.get_cell(db, active=active, item="OIFO")
            c7 = pyg.get_cell(db, active=active, item="VWAP").go()
            vp = c7.data
            ref = pyg.get_data("contracts", active=active, item="ref")
            long = c1.data
            short = c2.data
            oi = c3.data
            df_ = cot.analysis(active=active, type="Fut", vwap=vp, ref=ref, long=long, short=short, oi=oi)
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            long = c4.data
            short = c5.data
            oi = c6.data
            df_ = cot.analysis(active=active, type="Fut,Opt", vwap=vp, ref=ref, long=long, short=short, oi=oi)
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
            fig1, fig2 = gen_figures(active, cot_data)
            figs_net.append(fig1)
            figs_ls.append(fig2)
            reg_data = pd.DataFrame()
            reg_data["price chg"] = cot_data["PX_LAST_1"].diff() / cot_data["PX_LAST_1"].shift(1)
            reg_data["net chg"] = cot_data["Net"].diff()
            reg_fig, lm = chart.regression_chart(
                data=reg_data.iloc[-104:, :].dropna(),
                title=f"Price vs Net position change - {active}",
                xaxis_title='Net position change',
                yaxis_title='Price change',
            )
            raise NotImplementedError("Missing regression annotation: IMG_4608 line 275")
            reg_data_4w = pd.DataFrame()
            reg_data_4w["price chg"] = (cot_data["PX_LAST_1"] - cot_data["PX_LAST_1"].shift(4)) / cot_data[
                "PX_LAST_1"].shift(4)
            reg_data_4w["net chg"] = cot_data["Net"] - cot_data["Net"].shift(4)
            reg_fig_4w, lm_4w = chart.regression_chart(
                data=reg_data_4w.iloc[-104:, :].dropna(),
                title=f"Price vs Net position 4w change - {active}",
                xaxis_title='Net position change',
                yaxis_title='Price change',
            )
            raise NotImplementedError("Missing regression annotation: IMG_4608 line 286")
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig, reg_fig_4w] + [reg_str, reg_str_4w], columns=2))
            table.to_html(figs_reg, f"{html_path}\\positioning\\links\\{active}_chart_dealers.html")
            chart_links[df_.iloc[0, 0]] = (
                f'<a href="{html_path}\\positioning\\links\\{active}_chart_dealers.html">{df_.iloc[0, 0]}</a>')

        figs = []
        figs.append("<div style='font-family:Calibri;' >")
        raise NotImplementedError("Missing table-format tails: IMG_4609 lines 302-325")
        output_html_table = table.html_format(
            df=cot_table,
            header="Swap Dealers Net Position",
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
            hide_cols=["net pos rank", "net/oi pct rank",
                       "YTD price change", "_thr_high", "_thr_low", "_thr_high8", "_thr_low8", "_thr_net",
                       "_z_high", "_z_low", "_price_chg", "_last_update"],
            inline=False,
            background_color="lightblue",
            na_rep="-",
        )

        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        figs.append(output_html_table)
        figs_email = figs + figs_net
        figs_email.append(
            u'<a href="{:s}\\positioning\\{:s}.html">Position Charts</a><br><br>'.format(
                html_path, file_name))
        figs_new = table.to_html(
            [table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs + figs_ls, add_home=False)
        table.figures_to_html(figs_new, f"{html_path}\\positioning\\{file_name}_dealers.html", task_name=report_name)
        print(f"Updated to {new.index[-1].strftime('%Y-%m-%d')}")
        pyg.get_cell(db, active="COA Comdty", item="SDLFO").go()
    else:
        print(f"No new data. Last release is {new.index[-1].strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    raise NotImplementedError("Incomplete configured recipient list: IMG_4604 line 27")
    update(send_to=send_to)

