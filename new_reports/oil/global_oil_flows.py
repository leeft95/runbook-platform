import pandas as pd
import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path, json_path, html_path, data_path
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux
import ecm.cmds.custom as custom

send_to = None
report_name = "Global Oil Flows"
file_name = "global_oil_flows"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in global_oil_flows.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2022, 7, 1, 9, 36), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


def update(send_to):
    save_folder = f"{html_path}\\oil\\global_oil_flows"
    opec_crude = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Opec&unit=kbd&withForecast=false&split=Origin%20Countries&products=crude%2fco"))
    opec_clean = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Opec&unit=kbd&withForecast=false&split=Origin%20Countries&products=Clean%20Products"))
    nonopec_crude = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Non-Opec&unit=kbd&withForecast=false&split=Origin%20Countries&products=crude%2fco"))
    nonopec_clean = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Non-Opec&unit=kbd&withForecast=false&split=Origin%20Countries&products=Clean%20Products"))
    iraq = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Iraq,Turkey&unit=kbd&withForecast=false&split=Grades&products=crude%2fco"))
    non_opec = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Brazil,Mexico&unit=kbd&withForecast=false&split=Origin%20Countries&products=crude%2fco"))
    russia = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Russian%20Federation&unit=kbd&split=Origin%20Installations&products=crude%2fco"))
    clean = dv.kpler(
        link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&onlyRealized=true&"
              "fromZones=Saudi%20Arabia,United%20Arab%20Emirates,Kuwait,India,China,Korea,US,Russian%20Fe"
              + _missing_photo_text("69") + "split=Origin%20Countries&products=Clean%20Products"))
    opec_crude = kpler.convert_to_ts(kpler_links=opec_crude, end_dt="-1d")
    opec_clean = kpler.convert_to_ts(kpler_links=opec_clean, end_dt="-1d")
    nonopec_crude = kpler.convert_to_ts(kpler_links=nonopec_crude, end_dt="-1d")
    nonopec_clean = kpler.convert_to_ts(kpler_links=nonopec_clean, end_dt="-1d")
    iraq = kpler.convert_to_ts(kpler_links=iraq, end_dt="-1d")
    non_opec = kpler.convert_to_ts(kpler_links=non_opec, end_dt="-1d")
    russia = kpler.convert_to_ts(kpler_links=russia, end_dt="-1d")
    clean = kpler.convert_to_ts(kpler_links=clean, end_dt="-1d")
    opec_crude["Iraq"] = opec_crude["Iraq"] + iraq["Kirkuk"]
    opec_crude["Total"] = opec_crude.sum(axis=1)
    opec_clean["United Arab Emirates"] = clean["United Arab Emirates"]
    opec_clean["Total"] = opec_clean.sum(axis=1)
    opec_clean["Saudi-Kuwaiti Neutral Zone"] = 0
    opec_clean = opec_clean[opec_crude.columns]
    opec_liquid = opec_crude + opec_clean
    nonopec_crude["Total"] = nonopec_crude.sum(axis=1)
    nonopec_clean["Total"] = nonopec_clean.sum(axis=1)
    nonopec_crude["Other"] = nonopec_crude["Total"] - _missing_photo_text("94")
    nonopec_clean["Other"] = nonopec_clean["Total"] - _missing_photo_text("95")
    nonopec_crude.to_csv(_missing_photo_text("96: {data_path}\\kpler\\global oil flow\\nonopec_crude_{dt.datetime.now().strftime..."))
    nonopec_clean.to_csv(_missing_photo_text("97: {data_path}\\kpler\\global oil flow\\nonopec_clean_{dt.datetime.now().strftime..."))
    opec_crude.to_csv(_missing_photo_text("98: {data_path}\\kpler\\global oil flow\\opec_crude_{dt.datetime.now().strftime..."))
    opec_clean.to_csv(_missing_photo_text("99: {data_path}\\kpler\\global oil flow\\opec_clean_{dt.datetime.now().strftime..."))
    russia.rename(columns={"CPC Terminal": "Kazakh"}, inplace=True)
    russia["Russia"] = russia.sum(axis=1) - russia["Kazakh"]
    russia.to_csv(_missing_photo_text("102: {data_path}\\kpler\\global oil flow\\russia_crude_{dt.datetime.now().strftime..."))
    nonopec_crude = pd.concat([russia[["Kazakh", "Russia"]], nonopec_crude], axis=1)
    nonopec_crude.drop("Russian Federation", axis=1, inplace=True)
    nonopec_crude = nonopec_crude[_missing_photo_text("105")]
    nonopec_crude_new = nonopec_crude.copy()
    nonopec_crude_new["Other"] = nonopec_crude_new["Total"] - _missing_photo_text("107: nonopec_crude_new[[United States, Russia...")
    nonopec_crude_new = nonopec_crude_new[_missing_photo_text("108: United States, Russia, Kazakh, Canada, Brazil, Mexico...")]
    nonopec_clean.rename(columns={"Russian Federation": "Russia"}, inplace=True)
    nonopec_clean["Kazakh"] = 0
    nonopec_clean = nonopec_clean[nonopec_crude.columns]
    nonopec_liquid = nonopec_crude + nonopec_clean
    nonopec_clean_new = nonopec_clean.copy()
    nonopec_clean_new["Other"] = nonopec_clean_new["Total"] - _missing_photo_text("114: nonopec_clean_new[[Russia, United States...")
    _missing_photo_text("115-118: between photo bottoms and sticky header")
    total_export = pd.concat([opec_liquid["Total"], nonopec_liquid["Total"]], axis=1)
    total_export.columns = ["OPEC", "Non OPEC"]
    total_export["Total"] = total_export.sum(axis=1)
    total_crude = pd.concat([opec_crude["Total"], nonopec_crude["Total"]], axis=1)
    total_crude.columns = ["OPEC", "Non OPEC"]
    total_crude["Total"] = total_crude.sum(axis=1)
    total_clean = pd.concat([opec_clean["Total"], nonopec_clean["Total"]], axis=1)
    total_clean.columns = ["OPEC", "Non OPEC"]
    total_clean["Total"] = total_clean.sum(axis=1)
    def table_format3(df, header, file_path):
        return custom.Oil.table_format2_vs_month(data=df, table_head="Country", header=header, file_path=file_path)
    html_total = table_format3(df=total_export, header="Total liquids export (kbd)", file_path=_missing_photo_text("133: {save_folder}..."))
    html_opec = table_format3(df=opec_liquid, header="Opec liquids export (kbd)", file_path=_missing_photo_text("134: {save_folder}..."))
    html_nonopec = table_format3(df=nonopec_liquid, header="Non-Opec liquids export (kbd)", file_path=_missing_photo_text("135: {save_folder}..."))
    html_total_crude = table_format3(df=total_crude, header="Total crude export (kbd)", file_path=_missing_photo_text("136: {save_folder}..."))
    html_opec_crude = table_format3(df=opec_crude, header="Opec crude export (kbd)", file_path=_missing_photo_text("137: {save_folder}..."))
    html_nonopec_crude = table_format3(df=nonopec_crude_new, header="Non-Opec crude export (kbd)", file_path=_missing_photo_text("138: {save_folder}..."))
    html_total_clean = table_format3(df=total_clean, header="Total products export (kbd)", file_path=_missing_photo_text("139: {save_folder}..."))
    html_opec_clean = table_format3(df=opec_clean, header="Opec products export (kbd)", file_path=_missing_photo_text("140: {save_folder}..."))
    html_nonopec_clean = table_format3(df=nonopec_clean_new, header="Non-Opec products export (kbd)", file_path=_missing_photo_text("141: {save_folder}..."))
    chart_sdate = dt.datetime(2018, 1, 1)
    total_ma = ts.rolling(total_export[["Total"]], method="mean", window=10, start=chart_sdate)
    opec_ma = ts.rolling(opec_liquid, method="mean", window=10, start=chart_sdate)
    nonopec_ma = ts.rolling(nonopec_liquid, method="mean", window=10, start=chart_sdate)
    total_crude_ma = ts.rolling(total_crude[["Total"]], method="mean", window=10, start=chart_sdate)
    opec_crude_ma = ts.rolling(opec_crude, method="mean", window=10, start=chart_sdate)
    nonopec_crude_ma = ts.rolling(nonopec_crude, method="mean", window=10, start=chart_sdate)
    total_clean_ma = ts.rolling(total_clean[["Total"]], method="mean", window=10, start=chart_sdate)
    opec_clean_ma = ts.rolling(opec_clean, method="mean", window=10, start=chart_sdate)
    nonopec_clean_ma = ts.rolling(nonopec_clean, method="mean", window=10, start=chart_sdate)
    def seasonal_chart(df, column, title):
        return chart.seasonal_chart(
            df=df, column=column, title=title, vs_avg=True, ytd=False, freq="D",
            x_axis_title="Date", y_axis_title="kbd", y1_axis_title="kbd", y2_axis_title=None,
            ytd_cum_sum=True)
    chart_total = seasonal_chart(df=total_ma, column="Total", title="Total liquids exports - 10d mva")
    chart_total.write_json(convert_path_to_linux(f"{json_path}\\oil\\total_liquids_export.json"))
    chart_opec = seasonal_chart(df=opec_ma, column="Total", title="Opec liquids exports - 10d mva")
    chart_nonopec = seasonal_chart(df=nonopec_ma, column="Total", title="Non Opec liquids exports - 10d mva")
    chart_total_crude = seasonal_chart(df=total_crude_ma, column="Total", title="Total crude exports - 10d mva")
    chart_opec_crude = seasonal_chart(df=opec_crude_ma, column="Total", title="Opec crude exports - 10d mva")
    chart_nonopec_crude = seasonal_chart(df=nonopec_crude_ma, column="Total", title="Non Opec crude exports - 10d mva")
    chart_total_clean = seasonal_chart(df=total_clean_ma, column="Total", title="Total products exports - 10d mva")
    chart_opec_clean = seasonal_chart(df=opec_clean_ma, column="Total", title="Opec products exports - 10d mva")
    chart_nonopec_clean = seasonal_chart(df=nonopec_clean_ma, column="Total", title="Non Opec products exports - 10d mva")
    figs = []
    figs.append(table.html_text(_missing_photo_text("185: Last date of Kpler data {total_export.index[-1].strftime('%Y-%m-%d')}...")))
    figs.append(html_total)
    figs.append(html_opec)
    figs.append(html_nonopec)
    figs.append(html_total_crude)
    figs.append(html_opec_crude)
    figs.append(html_nonopec_crude)
    figs.append(html_total_clean)
    figs.append(html_opec_clean)
    figs.append(html_nonopec_clean)
    figs.append(chart_total)
    figs.append(chart_opec)
    figs.append(chart_nonopec)
    figs.append(chart_total_crude)
    figs.append(chart_opec_crude)
    figs.append(chart_nonopec_crude)
    figs.append(chart_total_clean)
    figs.append(chart_opec_clean)
    figs.append(chart_nonopec_clean)
    table.to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                  f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    if today().weekday() in [1, 3]:
        send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    update(send_to=send_to)
