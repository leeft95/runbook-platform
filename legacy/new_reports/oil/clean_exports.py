import pandas as pd
import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.cdr import today
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path

send_to = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "Clean Exports"
file_name = "clean_exports"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
chart_sdate = dt.datetime(2018, 1, 1)

zone_list = ['China', 'Primorsk', 'Novorossiysk', 'Tuapse']
dates = ['30-Nov-22', '31-Dec-22', '31-Jan-23', '28-Feb-23', '31-Mar-23', '30-Apr-23', '31-May-23', '30-Jun-23',
         '31-Jul-23', '31-Aug-23']
china = [2690, 2760, 1508, 2200, 550, 484, 484, 560, 825, 825]
primorsk = [1467, 1753, 1839, 1882, 1900, 1599, 1081, 1081, 1605, 1605]
novo = [670, 905, 546, 591, 579, 579, 364, 364, 563, 563]
tuapse = [484, 528, 522, 589, 591, 591, 591, 591, 586.5, 586.5]
allocation = pd.DataFrame([china, primorsk, novo, tuapse], columns=dates, index=zone_list).T


def _missing_photo_text(lines):
    """Transcription marker for text clipped from all available photographs."""
    raise NotImplementedError(f"Missing photographed text: clean_exports.py source lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 9, 26),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def actual_export_vs_allocation():
    figs = []
    allocation.index = pd.to_datetime(allocation.index)
    for i in zone_list:
        actual = dv.kpler(link=(
            f"/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&products=diesel,g"
            + _missing_photo_text("60")
            + f"unit=kt&withForecast=false&onlyRealized=true&split=Total&withIntraCountry=false&fromZon"
            + _missing_photo_text("61")
        ))
        actual = kpler.convert_to_ts(kpler_links=actual, end_dt="-1d")
        actual_ma = ts.rolling(df=actual, method="mean", window=10, start=chart_sdate)

        allocation_by_month = ts.cumsum_by_month(allocation, column=i, n=2, label="allocation", method="bfill",
                                                 convert_to_daily=True)
        export_by_month = ts.cumsum_by_month(actual, column="Total", n=2, label="actual", method="ffill",
                                             convert_to_daily=False)
        actual_vs_allocation = pd.concat([export_by_month, allocation_by_month], axis=1)
        figs.append(chart.seasonal_chart_2col(
            df=actual_ma,
            df1=actual_vs_allocation,
            title=f"{i} Gasoil exports",
            vs_avg=True,
            ytd=False,
            freq="D",
            highlight_dict_c2={
                "0": {"color": "blue", "width": 2},
                "1": {"color": "red", "width": 2},
                "2": {"color": "blue", "dash": "dash", "width": 2},
                "3": {"color": "red", "dash": "dash", "width": 2},
            },
            switch=True,
            show_grid_c1=False,
            show_grid_c2=True,
            column_titles=["Actual vs Allocation", "Seasonal Export"],
            x_axis_title="Date",
            y_axis_title="kbd",
            y1_axis_title="kbd",
            y2_axis_title=None
        ))
    return figs


def clean_update():
    clean = dv.kpler(link=(
        "/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&"
        "fromZones=Saudi%20Arabia,United%20Arab%20Emirates,Kuwait,India,China,Korea,US,Russian%20Feder"
        + _missing_photo_text("99")
        + "unit=kbd&withForecast=false&onlyRealized=true&split=Origin%20Countries&products=Clean%20Produ"
        + _missing_photo_text("100")
    ))
    clean = kpler.convert_to_ts(kpler_links=clean, end_dt="-1d")

    clean['Total'] = clean.sum(axis=1)
    clean['Persian Group'] = clean[['Saudi Arabia', 'United Arab Emirates', 'Kuwait']].sum(axis=1)
    clean = clean[['Total', 'United States', 'Russian Federation', 'South Korea', 'India',
                   'Saudi Arabia', 'United Arab Emirates', 'China', 'Kuwait', 'Persian Group']]

    figs = []
    table_clean = table.table_format2_vs_month(
        df=clean,
        rows=['Total', 'Saudi Arabia', 'United Arab Emirates', 'Kuwait',
              'India', 'China', 'South Korea', 'United States', 'Russian Federation'],
        highlight={"window": 92},
        agg_by="mean",
        agg_by_column=None,
        **_missing_photo_text("118"),
        window1=20,
        benchmark_quarter=f"{today().year - 1}-Q4",
        table_head="Clean export"
    )
    figs.append(table.html_format(
        df=table_clean,
        header="Clean export (kbd)",
        footer=None,
        show_date=False,
        format_column={"0": {"width": "120px", "text-align": "left"},
                       "1": {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
                       "2": {"width": "80px", "text-align": "center", "highlight_z": [2, "_mean1", "_std1"]},
                       "3": {"width": "80px", "text-align": "center"},
                       "4": {"width": "80px", "text-align": "center"},
                       "5": {"width": "80px", "text-align": "center"},
                       "6": {"width": "80px", "text-align": "center"},
                       "7": {"width": "80px", "text-align": "center"},
                       "8": {"width": "80px", "text-align": "center"},
                       },
        format_row={"0": {"bottom_border": True, "bold": True}},
        precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"],
    ))

    clean_ma = ts.rolling(df=clean, method="mean", window=10, start=chart_sdate)
    for i in ["Total", "Persian Group", "China", "India", "United States", "Russian Federation"]:
        figs.append(chart.seasonal_chart(
            df=clean_ma,
            column=i,
            title=f"{i} clean exports - 10d mva",
            vs_avg=True,
            ytd=False,
            freq="D",
            x_axis_title="Date",
            y_axis_title="kbd",
            y1_axis_title="kbd",
            y2_axis_title=None,
            ytd_cum_sum=True
        ))
    return figs


def update(send_to):
    figs = clean_update()
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri", tag='h1')] + figs,
        f"{html_path}\\oil\\{file_name}.html", task_name=report_name)


if __name__ == "__main__":
    update(send_to=send_to)
