import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path

from ecm.cmds.cdr import today

send_to = None  # Unrecovered recipient list.
report_name = "Kpler Implied Demand Monitor"
file_name = "kpler_implied_demand"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    """Transcription marker for text absent from all available photographs."""
    raise NotImplementedError(f"Missing photographed text: kpler_implied_demand.py source lines {lines}")


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
        start_datetime=dt.datetime(2022, 7, 1, 9, 33),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update(send_to):
    net_exports = dv.kpler(
        link=("/v1/flows?fromZones=China,Saudi%20Arabia,United%20Arab%20Emirates&products=Clean%20Products&"
              "flowDirection=NetExport&split=Origin%20Countries&granularity=daily&"
              "onlyRealized=true&startDate=2016-01-01&unit=kb"))
    exports = dv.kpler(
        link=("/v1/flows?fromZones=India,South%20Korea,Kuwait&products=Clean%20Products&"
              "flowDirection=Export&split=Origin%20Countries&granularity=daily&onlyRealized=true&"
              "startDate=2016-01-01&unit=kb"))
    imports = dv.kpler(
        link=("/v1/flows?toZones=Japan,Thailand,Taiwan,Vietnam,Indonesia,Brazil,Chile,Mexico,"
              "Australia,Argentina&products=Clean%20Products&flowDirection=Import&"
              "split=Destination%20Countries&granularity=daily&onlyRealized=true&startDate=2016-01-01&unit=kb"))

    exporter = kpler.convert_to_ts(
        kpler_links=[net_exports, exports],
        columns=['Saudi Arabia', 'Kuwait', 'United Arab Emirates', 'China', 'India', 'South Korea'],
        end_dt="-1d"
    )
    exporter['Total'] = exporter.sum(axis=1)
    importer = kpler.convert_to_ts(
        kpler_links=imports,
        columns=['Japan', 'Thailand', 'Taiwan', 'Vietnam', 'Indonesia', 'Australia', 'Brazil', 'Mexico', 'Chile',
                 'Argentina'],
        end_dt="-1d"
    )
    importer['Asian Imports'] = importer[['Japan', 'Thailand', 'Taiwan', 'Vietnam', 'Indonesia', 'Australia']].sum(
        axis=1)
    importer['Latam Imports'] = importer[['Brazil', 'Mexico', 'Chile', 'Argentina']].sum(axis=1)
    importer['Total'] = importer['Asian Imports'] + importer['Latam Imports']

    table_exporter = table.table_format1(
        df=exporter,
        rows=['Saudi Arabia', 'Kuwait', 'United Arab Emirates', 'China', 'India', 'South Korea', 'Total'],
        highlight={"seasonal": 5}, agg_by="mean", window=20, ex2020=True, table_head="Exporter"
    )
    table_importer = table.table_format1(
        df=importer,
        rows=['Japan', 'Thailand', 'Taiwan', 'Vietnam', 'Indonesia', 'Australia', 'Brazil', 'Mexico', 'Chile',
              'Argentina', 'Asian Imports', 'Latam Imports', 'Total'],
        highlight={"seasonal": 5}, agg_by="mean", window=20, ex2020=True, table_head="Importer"
    )

    html_exporter = table.html_format(
        df=table_exporter,
        header="Export (kbd): Lower exports imply stronger internal demand and/or Tars",
        footer="Saudi/China are net exporters",
        show_date=False,
        format_column={
            table_exporter.columns[0]: {"width": "120px", "text-align": "left"},
            table_exporter.columns[1]: {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
            tuple(table_exporter.columns[2:]): {"width": "80px", "text-align": "center"},
        },
        format_row={5: {"bottom_border": True}, 6: {"bold": True}},
        precision=0,
        hide_cols=["_last_update", "_mean", "_std"],
        inline=False,
        background_color="lightblue",
        na_rep="-"
    )
    html_importer = table.html_format(
        df=table_importer,
        **_missing_photo_text("117-118"),
        show_date=False,
        format_column={
            table_importer.columns[0]: {"width": "120px", "text-align": "left"},
            table_importer.columns[1]: {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
            tuple(table_importer.columns[2:]): {"width": "80px", "text-align": "center"},
        },
        format_row={9: {"bottom_border": True}, 10: {"bold": True}, 11: {"bold": True}, 12: {"bold": True}},
        precision=0,
        hide_cols=["_last_update", "_mean", "_std"],
        inline=False,
        background_color="lightblue",
        na_rep="-"
    )

    exporter_ma = ts.rolling(exporter, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    importer_ma = ts.rolling(importer, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    chart_exporter = chart.seasonal_chart(
        df=exporter_ma, column="Total", title="Total export - 20d MA (Reversed)",
        vs_avg=True, ytd=False, freq="D", x_axis_title="Date", y_axis_title="kb",
        y1_axis_title="kb", y2_axis_title=None, y_axis_reversed=True,
        y1_axis_reversed=True, ytd_cum_sum=True
    )
    chart_importer = chart.seasonal_chart(
        df=importer_ma, column="Total", title="Total import - 20d MA",
        vs_avg=True, ytd=False, freq="D", x_axis_title="Date", y_axis_title="kb",
        y1_axis_title="kb", y2_axis_title=None, ytd_cum_sum=True
    )

    figs = []
    figs.append(html_exporter)
    figs.append(html_importer)
    figs.append(chart_exporter)
    figs.append(chart_importer)
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri", tag='h1')] + figs,
        f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    if today().weekday() in [1, 3]:
        send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    raise NotImplementedError("Missing photographed main block: kpler_implied_demand.py after line186")
