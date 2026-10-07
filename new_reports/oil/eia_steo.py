import time
import pandas as pd
import datetime as dt
import os
import sys
from dateutil.relativedelta import relativedelta
import ecm.cmds.chart as chart
import ecm.cmds.table as table
import ecm.cmds.data as dv
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, root_path, oil_group
import requests
from ecm.atom.clients import retry
from ecm.cmds.utils import convert_path_to_linux
from calendar import monthrange

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"

send_to = oil_group
report_name = "STEO Update"
file_name = "eia_steo"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in eia_steo.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2022, 7, 1, 6, 30), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



release_schedule = [
    "01/14/2025", "02/11/2025", "03/11/2025", "04/10/2025",
    "05/06/2025", "06/10/2025", "07/08/2025", "08/12/2025",
    "09/09/2025", "10/07/2025", "11/12/2025", "12/09/2025",
] + _missing_photo_text("64-75: remainder of release_schedule")


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(10))
def get_release_new(date=None, mon=None, yr=None, save=False):
    root_path = "\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\CODE\\data\\eia\\steo"
    if date is None and mon is None and yr is None:
        date = dt.datetime.today()
        mon = date.strftime("%b")
        yr = str(date.year)[-2:]
    elif date is None and mon is not None and yr is not None:
        _date = dt.datetime.strptime(f"{mon} {yr}", "%b %y")
        last_day = monthrange(_date.year, _date.month)[1]
        date = dt.datetime(_date.year, _date.month, last_day)
    else:
        mon = date.strftime("%b")
        yr = str(date.year)[-2:]

    print(f"Getting release data {mon} {yr}")
    if date > dt.datetime(2013, 7, 1):
        if save:
            try:
                link = f"https://www.eia.gov/outlooks/steo/archives/{mon.lower()}{yr}_base.xlsx"
                print(link)
                raw_bytes = requests.get(link).content
                if isinstance(raw_bytes, str) and "File Not Found" in raw_bytes:
                    raise Exception("File Not Found")
                else:
                    with open(convert_path_to_linux(f"{root_path}\\{mon.lower()}{yr}_base.xlsx"), "wb") as f:
                        f.write(raw_bytes)
            except Exception as e:
                print(e)
                raise Exception("Rate limit exceeded")
            pre_df = None
            return pre_df
        else:
            link = convert_path_to_linux(f"{root_path}\\{mon.lower()}{yr}_base.xlsx")
            print(link)
            engine = "openpyxl"
            sheet = "4atab"
            skiprows = None
            pre_df = pd.read_excel(link, sheet_name=sheet, engine=engine, skiprows=skiprows)
            if "U.S. total crude oil production" in pre_df.iloc[4, 1]:
                pre_prod = pre_df.iloc[[1, 2, 4], 2:].T
                col = 4
            else:
                pre_prod = pre_df.iloc[[1, 2, 5], 2:].T
                col = 5
            pre_prod.fillna(method="ffill", inplace=True)
            pre_prod["date"] = [dt.datetime.strptime(f"{pre_prod.iloc[x, 0]}-{pre_prod.iloc[x, 1]}-1", "%Y-%m-%d") for x in
                                range(0, len(pre_prod))]
            pre_prod = pre_prod[["date", col]]
            pre_prod.columns = ["date", f"{mon}-{yr}"]
            pre_prod.set_index("date", inplace=True)
        return pre_prod * 1000
    else:
        if save:
            try:
                link = f"https://www.eia.gov/outlooks/steo/archives/{mon.lower()}{yr}_base.xls"
                print(link)
                raw_bytes = requests.get(link).content
                with open(convert_path_to_linux(f"{root_path}\\{mon.lower()}{yr}_base.xls"), "wb") as f:
                    f.write(raw_bytes)
            except Exception as e:
                print(e)
                raise Exception("Rate limit exceeded")
            pre_df = None
        else:
            link = convert_path_to_linux(f"{root_path}\\{mon.lower()}{yr}_base.xls")
            engine = "xlrd"
            if date < dt.datetime(2005, 8, 1):
                sheet = "Petroleum"
                skiprows = 2
                pre_df = pd.read_excel(link, sheet_name=sheet, engine=engine, skiprows=skiprows)
                pre_df.columns = [x if "Label" not in str(x) else "LABEL" for x in pre_df.columns]
                pre_df = pre_df.set_index(["DATEX", "LABEL"])
                pre_prod = pre_df.loc["COPRPUS"].T
                pre_prod.columns.name = ""
                pre_prod.columns = ["date", f"{mon}-{yr}"]
                pre_prod.index = pd.to_datetime(pre_prod.index, format="%Y%m")
                return pre_prod * 1000
            elif date > dt.datetime(2005, 8, 1) and date < dt.datetime(2007, 10, 1):
                print(date)
                sheet = "Petroleum US"
                skiprows = 2
                pre_df = pd.read_excel(link, sheet_name=sheet, engine=engine, skiprows=skiprows)
                pre_df.columns = [x if "Label" not in str(x) else "LABEL" for x in pre_df.columns]
                pre_df = pre_df.set_index(["DATEX", "Period"])
                pre_prod = pre_df.loc["COPRPUS"].T
                pre_prod.columns.name = ""
                pre_prod.columns = ["date", f"{mon}-{yr}"]
                pre_prod.index = pd.to_datetime(pre_prod.index, format="%Y%m")
                return pre_prod * 1000
            else:
                sheet = "4atab"
                skiprows = None
                pre_df = pd.read_excel(link, sheet_name=sheet, engine=engine, skiprows=skiprows)
                if "U.S. total crude oil production" in pre_df.iloc[4, 1]:
                    pre_prod = pre_df.iloc[[1, 2, 4], 2:].T
                    col = 4
                else:
                    pre_prod = pre_df.iloc[[1, 2, 5], 2:].T
                    col = 5
                pre_prod.fillna(method="ffill", inplace=True)
                pre_prod["date"] = [dt.datetime.strptime(f"{pre_prod.iloc[x, 0]}-{pre_prod.iloc[x, 1]}-1", "%Y-%m-%d") for x in
                                    range(0, len(pre_prod))]
                pre_prod = pre_prod[["date", col]]
                pre_prod.columns = ["date", f"{mon}-{yr}"]
                pre_prod.set_index("date", inplace=True)
                return pre_prod * 1000


def ea_tracker(dataset_id, start, length=12):
    """
    Download historical releases
    :param dataset_id:
    :param start:
    :return:
    """
    if isinstance(dataset_id, list):
        dataset_id_ = ','.join(dataset_id)
        dataset_id_release = dataset_id[0]
    else:
        dataset_id_ = dataset_id_release = dataset_id
    release_dts = dv.ea_release_dates(dataset_id=dataset_id_release, monthly=True)
    df = pd.DataFrame()
    for i in range(-1, -length-1, -1):
        data = dv.energy_aspects(dataset_id=dataset_id_, start=start, release_date=release_dts[i])
        data.set_index("Date", inplace=True)
        data.index = pd.to_datetime(data.index)
        data = data.sum(axis=1).to_frame(release_dts[i])
        df = pd.concat([df, data], axis=1)
        df.dropna(axis=1, how="all", inplace=True)
    return df


def steo_prod(send_to):
    df = pd.DataFrame()
    for i in range(0, 25):
        m = (today() + relativedelta(day=1) - relativedelta(months=i)).strftime(("%b"))
        y = str((today() + relativedelta(day=1) - relativedelta(months=i)).year)[-2:]
        df = pd.concat([df, get_release_new(mon=m, yr=y)], axis=1)
    ea_prod = dv.energy_aspects(dataset_id="6495", start="2010-01-01")
    ea_prod.set_index('Date', drop=True, inplace=True)
    ea_prod.index = pd.to_datetime(ea_prod.index)
    release_dts = dv.ea_release_dates(dataset_id=6495, monthly=False)
    ea_prod.columns = [f'EA {release_dts[-1][:10]}']
    ea_prod = ea_prod.loc[ea_prod.index >= dt.datetime(2019, 1, 1)]
    df_ = df.iloc[:, [0, 1]]
    df_.columns = ["STEO " + x for x in df_.columns]
    total_df = pd.concat([df_, ea_prod], axis=1)
    df2 = df.iloc[:, -1]
    total_df = total_df.loc[total_df.index >= today() - relativedelta(months=6)]
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    figs.append(chart.line_chart(
        df=total_df, title="Recent STEO: US Crude Production (kbd)", tickformat=False,
        highlight_dict={total_df.columns[0]: {"width": 2, "color": "black"},
                        total_df.columns[1]: {"width": 2, "color": "blue", "dash": "dash"},
                        total_df.columns[2]: {"color": "red", "width": 2}}))
    live_yr = 2025
    df_y1 = (df.loc[df.index.year == live_yr, :].mean(axis=0)).to_frame(live_yr)
    df_y1.index = [f"01-{x}" for x in df_y1.index]
    df_y1.index = pd.to_datetime(df_y1.index)
    df_y1.sort_index(inplace=True)
    if df.index[-1] > dt.datetime(live_yr + 1, 1, 1):
        df_y2 = (df.loc[df.index.year == live_yr + 1, :].mean(axis=0)).to_frame(live_yr + 1)
        df_y2.index = [f"01-{x}" for x in df_y2.index]
        df_y2.index = pd.to_datetime(df_y2.index)
        df_y2.sort_index(inplace=True)
        df_y0 = (df.loc[df.index.year == live_yr - 1, :].mean(axis=0)).to_frame(live_yr - 1)
        df_y0.index = [f"01-{x}" for x in df_y0.index]
        df_y0.index = pd.to_datetime(df_y0.index)
        df_y0.sort_index(inplace=True)
        df_y1y2 = pd.concat([df_y1, df_y2], axis=1)
        df_yoy = pd.concat([df_y1.iloc[:, 0] - df_y0.iloc[:, 0], df_y2.iloc[:, 0] - df_y1.iloc[:, 0]], axis=1)
        df_yoy.columns = [f"{str(df_y1.columns[0])[-2:]}/{str(df_y0.columns[0])[-2:]}",
                          f"{str(df_y2.columns[0])[-2:]}/{str(df_y1.columns[0])[-2:]}"]
    figs.append(chart.line_chart(df=df_y1y2.iloc[-12:, :], title="STEO Production Evolution (kbd)", tickformat=False))
    figs.append(chart.line_chart(df=df_yoy.iloc[-12:, :], title="STEO Production YoY Evolution (kbd)", tickformat=False))

    df_y1 = (df.loc[df.index.year == live_yr, :].iloc[-1, :]).to_frame(live_yr)
    df_y1.index = [f"01-{x}" for x in df_y1.index]
    df_y1.index = pd.to_datetime(df_y1.index)
    df_y1.sort_index(inplace=True)
    if df.index[-1] > dt.datetime(live_yr + 1, 1, 1):
        df_y2 = (df.loc[df.index.year == live_yr + 1, :].iloc[-1, :]).to_frame(live_yr + 1)
        df_y2.index = [f"01-{x}" for x in df_y2.index]
        df_y2.index = pd.to_datetime(df_y2.index)
        df_y2.sort_index(inplace=True)
        df_y0 = (df.loc[df.index.year == live_yr - 1, :].iloc[-1, :]).to_frame(live_yr - 1)
        df_y0.index = [f"01-{x}" for x in df_y0.index]
        df_y0.index = pd.to_datetime(df_y0.index)
        df_y0.sort_index(inplace=True)
        df_y1y2 = pd.concat([df_y1, df_y2], axis=1)
        df_y1y2.columns = [f"Dec{str(df_y1.columns[0])[-2:]}-STEO", f"Dec{str(df_y2.columns[0])[-2:]}-STEO"]
        df_yoy = pd.concat([df_y1.iloc[:, 0] - df_y0.iloc[:, 0], df_y2.iloc[:, 0] - df_y1.iloc[:, 0]], axis=1)
        df_yoy.columns = [f"Dec{str(df_y1.columns[0])[-2:]}/{str(df_y0.columns[0])[-2:]}-STEO",
                          f"Dec{str(df_y2.columns[0])[-2:]}/{str(df_y1.columns[0])[-2:]}-STEO"]
    sdate = dt.datetime(live_yr-1, 12, 1)
    data = ea_tracker(dataset_id="6495", start=sdate.strftime("%Y-%m-%d"), length=12)
    data1 = data.loc[data.index.month == 12, :]
    data2 = data1.copy().loc[data1.index.year.isin([df_y1.columns[0], df_y2.columns[0]]), :]
    data2.columns = [dt.datetime(int(x[:4]), int(x[5:7]), 1) for x in data2.columns]
    data2.index = [f"Dec{str(df_y1.columns[0])[-2:]}-EA", f"Dec{str(df_y2.columns[0])[-2:]}-EA"]
    data2 = data2.T
    df_y1y2 = pd.concat([df_y1y2, data2], axis=1)
    data3 = data1.diff().loc[data1.index.year.isin([df_y1.columns[0], df_y2.columns[0]]), :]
    data3.columns = [dt.datetime(int(x[:4]), int(x[5:7]), 1) for x in data3.columns]
    data3.index = [f"Dec{str(df_y1.columns[0])[-2:]}/{str(df_y0.columns[0])[-2:]}-EA",
                   f"Dec{str(df_y2.columns[0])[-2:]}/{str(df_y1.columns[0])[-2:]}-EA"]
    data3 = data3.T
    df_yoy = pd.concat([df_yoy, data3], axis=1)
    fig1 = chart.line_chart(df=df_y1y2.iloc[-12:, :], title='US Crude Production Evolution (kbd)', tickformat=False,
                             highlight_dict={df_y1y2.columns[0]: {"color": "blue"},
                                             df_y1y2.columns[1]: {"color": "red"},
                                             df_y1y2.columns[2]: {"color": "blue", "dash": "dash"},
                                             df_y1y2.columns[3]: {"color": "red", "dash": "dash"}})
    figs.append(fig1)
    fig2 = chart.line_chart(df=df_yoy.iloc[-12:, :], title='US Crude Production YoY Evolution (kbd)', tickformat=False,
                             highlight_dict={df_yoy.columns[0]: {"color": "blue"},
                                             df_yoy.columns[1]: {"color": "red"},
                                             df_yoy.columns[2]: {"color": "blue", "dash": "dash"},
                                             df_yoy.columns[3]: {"color": "red", "dash": "dash"}})
    figs.append(fig2)
    table.figures_to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


def update():
    string_date = (today()).strftime("%m/%d/%Y")
    if string_date in release_schedule:
        get_release_new(date=pd.to_datetime(string_date), save=True)
        steo_prod(send_to=send_to)


if __name__ == "__main__":
    update()
