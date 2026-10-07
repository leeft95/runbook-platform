import pandas as pd
import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path, data_path
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path

send_to = None
report_name = "OPEC Exports"
file_name = "opec_exports"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in opec_exports.py, photographed lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.TUESDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 9, 31), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def update(send_to):
    opec = dv.kpler(link=("/v1/flows?flowDirection=NetExport&granularity=daily&startDate=2015-01-01&"
        "fromZones=Opec&unit=kbd&withForecast=false&onlyRealized=true&split=Origin%20Countries&product" + _missing_photo_text("47: clipped URL suffix")))
    iraq = dv.kpler(link=("/v1/flows?flowDirection=NetExport&granularity=daily&startDate=2015-01-01&"
        "fromZones=Iraq,Turkey&unit=kbd&withForecast=true&onlyRealized=true&split=Grades&products=crud" + _missing_photo_text("50: clipped URL suffix")))
    non_opec = dv.kpler(link=("/v1/flows?flowDirection=NetExport&granularity=daily&startDate=2015-01-01&"
        "fromZones=Brazil,Mexico&unit=kbd&withForecast=true&onlyRealized=true&split=Origin%20Countries" + _missing_photo_text("53: clipped URL suffix")))
    russia = dv.kpler(link=("/v1/flows?flowDirection=NetExport&granularity=daily&startDate=2015-01-01&"
        "fromZones=Russian%20Federation&unit=kbd&withForecast=true&onlyRealized=true&split=Origin%20In" + _missing_photo_text("56: clipped URL suffix")))
    clean = dv.kpler(link=("/v1/flows?flowDirection=NetExport&granularity=daily&startDate=2017-01-01&"
        "fromZones=Saudi%20Arabia,Iraq,United%20Arab%20Emirates,Kuwait&unit=kbd&withForecast=false&onl" + _missing_photo_text("59: clipped URL suffix") + "split=Origin%20Countries&products=Clean%20Products"))
    non_opec_clean = dv.kpler(link=("/v1/flows?flowDirection=NetExport&granularity=daily&startDate=2015-01-01&"
        "fromZones=Russian%20Federation,Brazil,Mexico&unit=kbd&withForecast=true&onlyRealized=true&spl" + _missing_photo_text("63: clipped URL suffix")))
    opec = kpler.convert_to_ts(kpler_links=opec, end_dt="-1d")
    iraq = kpler.convert_to_ts(kpler_links=iraq, end_dt="-1d")
    non_opec = kpler.convert_to_ts(kpler_links=non_opec, end_dt="-1d")
    russia = kpler.convert_to_ts(kpler_links=russia, end_dt="-1d")
    clean = kpler.convert_to_ts(kpler_links=clean, end_dt="-1d")
    non_opec_clean = kpler.convert_to_ts(kpler_links=non_opec_clean, end_dt="-1d")
    opec.to_csv(_missing_photo_text("73: {data_path}\\kpler\\opec export\\net_opec_crude_{dt.datetime.now().strftime..."))
    clean.to_csv(_missing_photo_text("74: {data_path}\\kpler\\opec export\\net_opec_clean_{dt.datetime.now().strftime..."))
    non_opec.to_csv(_missing_photo_text("75: {data_path}\\kpler\\opec export\\net_nonopec_crude_{dt.datetime.now().strftime..."))
    non_opec_clean.to_csv(_missing_photo_text("76: {data_path}\\kpler\\opec export\\net_nonopec_clean_{dt.datetime.now().strftime..."))

    clean_columns = ["Saudi Arabia", "Iraq", "United Arab Emirates", "Kuwait"]
    clean = clean[clean_columns]
    opec["Iraq"] = opec["Iraq"] + iraq["Kirkuk"]
    opec["Total"] = opec.sum(axis=1)
    russia.rename(columns={"CPC Terminal": "Kazakh"}, inplace=True)
    russia["Russia"] = russia.sum(axis=1) - russia["Kazakh"]
    non_opec = pd.concat([russia[["Kazakh", "Russia"]], non_opec], axis=1)
    non_opec["Total"] = non_opec.sum(axis=1)
    suk_total = opec[clean.columns] + clean
    clean["Total"] = clean.sum(axis=1)
    suk_total["Total"] = suk_total.sum(axis=1)
    non_opec_clean.columns = ["Russia", "Brazil", "Mexico"]
    non_opec_clean["Total"] = non_opec_clean.sum(axis=1)
    suk_total_non_opec = non_opec[non_opec_clean.columns] + non_opec_clean
    suk_total_non_opec["Total"] = suk_total_non_opec.sum(axis=1)
    total_liquids = suk_total + suk_total_non_opec

    def table_format2(df):
        return table.table_format2_vs_month(
            df=df, rows=None, highlight={"window": 92}, agg_by="mean", agg_by_column=None,
            window=10, window1=20, benchmark_quarter=f"{today().year-1}-Q4", table_head="Country")

    table_opec = table_format2(opec)
    table_nonopec = table_format2(non_opec)
    table_clean = table_format2(clean)
    table_total = table_format2(suk_total)
    table_non_opec_clean = table_format2(non_opec_clean)
    table_total_non_opec = table_format2(suk_total_non_opec)
    format_column = {"0": {"width": "120px", "text-align": "left"},
                     "1": {"width": "80px", "text-align": "center", "highlight_z": ["10d MA", "_mean", "_std"]},
                     "2": {"width": "80px", "text-align": "center", "highlight_z": ["20d MA", "_mean1", "_std1"]},
                     "3": {"width": "80px", "text-align": "center"},
                     "4": {"width": "80px", "text-align": "center"},
                     "5": {"width": "80px", "text-align": "center"},
                     "6": {"width": "80px", "text-align": "center"},
                     "7": {"width": "80px", "text-align": "center"},
                     "8": {"width": "80px", "text-align": "center"}}
    html_opec = table.html_format(
        df=table_opec, header="OPEC Crude Net Export (kbd)", footer=None, show_date=False,
        format_column=format_column,
        format_row={"12": {"bottom_border": True}, "13": {"bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])
    html_nonopec = table.html_format(
        df=table_nonopec, header="Non-OPEC Crude Net Export (kbd)", footer=None, show_date=False,
        format_column=format_column,
        format_row={"3": {"bottom_border": True}, "4": {"bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])
    html_clean = table.html_format(
        df=table_clean, header="OPEC Clean Net Export (kbd)", footer=None, show_date=False,
        format_column=format_column,
        format_row={"3": {"bottom_border": True}, "4": {"bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])
    html_total = table.html_format(
        df=table_total, header="OPEC Liquids Net Export (kbd)", footer=None, show_date=False,
        format_column=format_column,
        format_row={"3": {"bottom_border": True}, "4": {"bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])
    html_total_non_opec = table.html_format(
        df=table_total_non_opec, header="Non-OPEC Liquids Net Export (kbd)", footer=None, show_date=False,
        format_column=format_column,
        format_row={"1": {"bottom_border": True}, "2": {"bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])
    html_non_opec_clean = table.html_format(
        df=table_non_opec_clean, header="Non-OPEC Clean Net Export (kbd)", footer=None, show_date=False,
        format_column=format_column,
        format_row={"1": {"bottom_border": True}, "2": {"bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])

    chart_sdate = dt.datetime(2018, 1, 1)
    total = (opec["Total"] + non_opec["Total"]).to_frame("Total")
    total_liquids_ma = ts.rolling(total, method="mean", window=10, start=chart_sdate)
    total_ma = ts.rolling(total_liquids, method="mean", window=10, start=chart_sdate)
    opec_ma = ts.rolling(opec, method="mean", window=10, start=chart_sdate)
    suk_total_ma = ts.rolling(suk_total, method="mean", window=10, start=chart_sdate)

    def seasonal_chart(df, column, title):
        return chart.seasonal_chart(df=df, column=column, title=title, vs_avg=True, ytd=False, freq="D",
                                    x_axis_title="Date", y_axis_title="kbd", y1_axis_title="kbd", y2_axis_title=None)

    chart_total = seasonal_chart(df=total_ma, column="Total", title="Opec and Non-Opec Crude Net Exports - 10d mva")
    chart_total_liquids = seasonal_chart(df=total_liquids_ma, column="Total", title=_missing_photo_text("223: Opec and Non-Opec Liqui..."))
    chart_opec = seasonal_chart(df=opec_ma, column="Total", title="Opec Crude Net Exports - 10d mva")
    chart_saudi = seasonal_chart(df=opec_ma, column="Saudi Arabia", title="Saudi Crude Net Exports - 10d mva")
    chart_uae = seasonal_chart(df=opec_ma, column="United Arab Emirates", title="UAE Crude Net Exports - 10d mva")
    chart_iraq = seasonal_chart(df=opec_ma, column="Iraq", title="Iraq Crude Net Exports - 10d mva")
    chart_iran = seasonal_chart(df=opec_ma, column="Iran", title="Iran Crude Net Exports - 10d mva")
    chart_saudi_liquids = seasonal_chart(df=suk_total_ma, column="Saudi Arabia", title=_missing_photo_text("229: Saudi total liquids..."))
    chart_uae_liquids = seasonal_chart(df=suk_total_ma, column="United Arab Emirates", title=_missing_photo_text("230: UAE total liqui..."))
    chart_opec_liquids = seasonal_chart(df=suk_total_ma, column="Total", title=_missing_photo_text("231: OPEC liquids net exports - 1..."))
    figs = []
    figs.append(html_opec)
    figs.append(html_clean)
    figs.append(html_total)
    figs.append(html_nonopec)
    figs.append(html_non_opec_clean)
    figs.append(html_total_non_opec)
    figs.append([chart_total_liquids, chart_total])
    figs.append([chart_opec_liquids, chart_opec])
    figs.append([chart_saudi_liquids, chart_saudi])
    figs.append([chart_uae_liquids, chart_uae])
    figs.append(chart_iraq)
    figs.append(chart_iran)
    page_title = 'OPEC<span style="font-size:0.9em; vertical-align:super; line-height:0; position:relative;' + _missing_photo_text("248")
    table.to_html([table.html_text(page_title, style="font-family:Calibri;", tag="h1")] + figs,
                  f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    if today().weekday() in [1, 3]:
        send_email(send_to=send_to, subject="OPEC⁺ Net Exports", body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    update(send_to=send_to)
