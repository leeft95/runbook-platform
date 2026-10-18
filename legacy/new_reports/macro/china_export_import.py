import pandas as pd
import datetime as dt
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
from ecm.cmds.cdr import today
from ecm.cmds.config import html_path

report_name = "China Export"
file_name = "china_export_import"


def update():
    export_ticker = {
        "Total": "CNFREXP$ Index",
        "Refined crude petroleum products": "CHVEREFO Index",
        "Rare Earth": "CHVERERH Index",
        "Copper": "CHVECOPP Index",
        "Aluminium": "CHVEALUM Index",
        "Batteries and ESS": "CHVEBATT Index",
        "Electric wires and cables": "CHVEWIRE Index",
        "Electric vehicles": "CHVEELVE Index",
    }
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    for k, v in export_ticker.items():
        df = bbg.bdh(v, ["PX_LAST"], dt.datetime(2018, 1, 1), today())
        df_chg = (df - df.shift(12)) / df.shift(12)
        figs.append(chart.seasonal_chart(
            df=df_chg,
            freq="M",
            title=f"China export - {k}",
        ))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\{file_name}.html", task_name=report_name)


if __name__ == "__main__":
    update()
