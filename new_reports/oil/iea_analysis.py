import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import calendar
import statsmodels.api as sm
from tshistory.api import timeseries
from dateutil.relativedelta import relativedelta
import ecm.cmds.sql as sql
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.time_series as ts
import ecm.cmds.ticker as tk
import ecm.cmds.vendor._platts as platts
from ecm.cmds.cdr import today
from ecm.cmds.config import data_path, html_path, oil_group, csv_path, json_path, root_path
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux
import getpass
import iea_data as SAVE_IEA_DATA


def _unrecovered(message):
    raise NotImplementedError(message)


user = getpass.getuser()
report_name = "Sell Side Consensus"
iea_folder = f"{data_path}\\IEA"
send_to = [
    "mkikano@elementcapital.com",
    "rzhao@elementcapital.com",
    "ltrindade@elementcapital.com",
    "lballand@elementcapital.com",
]
file_name = "iea_analysis"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"

if sys.platform.startswith("win") and user == "pmlo25_svc":
    os.environ["TSHISTORYCFGPATH"] = r"C:\Users\pmlo25_svc\tshistory.cfg"


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
        start_datetime=dt.datetime(2025, 5, 1, 9, 20),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


release_schedule = [
    "01/14/2025",
    "02/11/2025",
    "03/11/2025",
    "04/08/2025",
    "05/06/2025",
    "06/10/2025",
    "07/08/2025",
    "08/13/2025",
    "09/11/2025",
    "10/14/2025",
    "11/13/2025",
    "12/11/2025",
]

static_opec_columns = {
    1: "Monthly EA forecast for Algeria OPEC crude production in kb/d",
    2: "Monthly EA forecast for crude production (including field condensate) in Angola in kb/d",
    3: "Monthly EA forecast for Congo OPEC crude production in kb/d",
    4: "Monthly EA forecast for Equatorial Guinea OPEC crude production in kb/d",
    5: "Monthly EA forecast for Gabon OPEC crude production in kb/d",
    6: "Monthly EA forecast for Iran OPEC crude production in kb/d",
    7: "Monthly EA forecast for Iraq OPEC crude production in kb/d",
    8: "Monthly EA forecast for Kuwait OPEC crude production in kb/d",
    9: "Monthly EA forecast for Libya OPEC crude production in kb/d",
    10: "Monthly EA forecast for Nigeria OPEC crude production in kb/d",
    11: "Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d",
    12: "Monthly EA forecast for Venezuela OPEC crude production in kb/d",
    13: "Monthly EA forecast for UAE OPEC crude production in kb/d",
    14: "Monthly EA forecast for total OPEC crude production in kb/d",
    15: "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
    16: "Monthly EA forecast for OPEC condensate production in kb/d",
    5242: "Monthly EA forecast for OPEC North America crude production (excluding field condensate) in kb/d",
    5243: "Monthly EA forecast for OPEC Latin America crude production (excluding field condensate) in kb/d",
    5244: "Monthly EA forecast for OPEC FSU crude production (excluding field condensate) in kb/d",
    5245: "Monthly EA forecast for OPEC Europe crude production (excluding field condensate) in kb/d",
    5246: "Monthly EA forecast for OPEC Asia Pacific crude production (excluding field condensate) in kb/d",
    5247: "Monthly EA forecast for OPEC Middle East crude production (excluding field condensate) in kb/d",
    5248: "Monthly EA forecast for OPEC Africa crude production (excluding field condensate) in kb/d",
}

def iea_folder_list():
    all_folders = [x[0] for x in os.walk(convert_path_to_linux(iea_folder)) if x[0][-2:].isdigit()]
    all_folders.sort()
    return all_folders


def kpler_oecd_inventory():
    land_stocks = dv.kpler(
        "/v1/inventories?zones=OECD&startDate=2015-01-01&period=monthly&addCommoditiesOnWater=false&split=" + _unrecovered("IMG_4170 original line115: Kpler split parameter and tail")
    )
    land_stocks = land_stocks[["Date" , "commercial and refinery"]]
    land_stocks.set_index("Date", inplace=True)
    land_stocks.index = pd.to_datetime(land_stocks.index)
    land_stocks.index = [x + relativedelta(day=1) for x in land_stocks.index]
    return land_stocks.iloc[:, 0] / 1000


def product_inventory_old():
    product_stocks = dv.energy_aspects(
        dataset_id=(
            "1530,1531,1532,1533,1534,1535,1536,1537,1538,1539,1540,1541,1542,1543,1544,"
            "1545,1546,1547,1548,1549,1550,1551,1552,1553,1554,1555,1556,1557,1558,1559,1560,1561"
        ),
        start="2017-01-01",
    )

    product_stocks = kpler.convert_to_ts(
        kpler_links=product_stocks,
        columns=None,
        rename=None,
        drop_column=[
            "Weekly diesel inventories in Mexico in kb",
            "Weekly fuel oil inventories in Mexico in kb",
            "Weekly gasoline inventories in Mexico in kb",
            "Weekly jet/kero inventories in Mexico in kb",
        ],
    )
    product_stocks.rename(
        columns={"Weekly total product inventories for Fujairah in Mbbl": "Fujairah"}, inplace=True
    )
    product_stocks["Weekly gasoline inventories in ARA in kt"] = (
        product_stocks["Weekly gasoline inventories in ARA in kt"] * 8.33
    )
    product_stocks["Weekly jet/kero inventories for ARA in kt"]= (
        product_stocks["Weekly jet/kero inventories in ARA in kt"] * 7.878
    )
    product_stocks["Weekly middle distillate inventories in ARA in kt"] = (
        product_stocks["Weekly middle distillate inventories in ARA in kt"] * 7.45
    )
    product_stocks["Weekly fuel oil inventories in ARA in kt"] = (
        product_stocks["Weekly fuel oil inventories in ARA in kt"] * 7.45
    )
    product_stocks["ARA"] = (
        product_stocks["Weekly gasoline inventories in ARA in kt"]
        + product_stocks["Weekly jet/kero inventories in ARA in kt"]
        + product_stocks["Weekly middle distillate inventories in ARA in kt"]
        + product_stocks["Weekly fuel oil inventories in ARA in kt"]
    )
    product_stocks["Weekly fuel oil inventories in Singapore in Mb"] = (
        product_stocks["Weekly fuel oil inventories in Singapore in Mb"] * 1000
    )
    product_stocks["Weekly light distillate inventories in Singapore in Mb"] = (
        product_stocks["Weekly light distillate inventories in Singapore in Mb"] * 1000
    )
    product_stocks["Weekly middle distillates inventories in Singapore in Mb"] = (
        product_stocks["Weekly middle distillates inventories in Singapore in Mb"] * 1000
    )
    product_stocks["Singapore"] = (
        product_stocks["Weekly fuel oil inventories in Singapore in Mb"]
        + product_stocks ["Weekly light distillate inventories in Singapore in Mb"]
        + product_stocks["Weekly middle distillates inventories in Singapore in Mb"]
    )
    product_stocks ["Weekly jet/kero inventories in Japan in kl"] = (
        product_stocks["Weekly jet/kero inventories in Japan in kl"] / 158.987567172247
    )
    product_stocks["Weekly kerosene inventories in Japan in kl"] = (
        product_stocks["Weekly kerosene inventories in Japan in kl"] / 158.987567172247
    )
    product_stocks["Weekly naphtha inventories in Japan in kl"] = (
        product_stocks["Weekly naphtha inventories in Japan in kl"] / 158.987567172247
    )
    product_stocks["Weekly gasoline inventories in Japan in kl"] = (
        product_stocks["Weekly gasoline inventories in Japan in kl"] / 158.987567172247
    )
    product_stocks["Weekly diesel inventories in Japan in kl"] = (
        product_stocks["Weekly diesel inventories in Japan in kl"] / 158.987567172247
    )
    product_stocks["Weekly fuel oil inventories in Japan in mb"] = (
        product_stocks["Weekly fuel oil inventories in Japan in mb"] * 1000
    )
    product_stocks["Japan"] = (
        product_stocks["Weekly jet/kero inventories in Japan in kl"]
        + product_stocks["Weekly kerosene inventories in Japan in kl"]
        + product_stocks["Weekly naphtha inventories in Japan in kl"]
        + product_stocks["Weekly gasoline inventories in Japan in kl"]
        + product_stocks["Weekly diesel inventories in Japan in kl"]
        + product_stocks["Weekly fuel oil inventories in Japan in mb"]
    )
    product_stocks["Fujairah"] = (
        product_stocks["Weekly total product inventories in Fujairah in Mb"] * 1000
    )
    product_stocks["US"] = (
        product_stocks["Weekly diesel inventories in United States in kb"]
        + product_stocks["Weekly gasoline inventories in United States in kb"]
        + product_stocks["Weekly jet/kero inventories in United States in kb"]
        + product_stocks[ "Weekly residual fuel oil inventories in United States in kb"]
    )
    product_stocks["US Other"] = (
        product_stocks["Weekly total product inventories in United States in kb"]
        - product_stocks["Weekly crude oil inventories in United States in kb"]
        - product_stocks["US"]
    )
    product_by_loc = product_stocks[["US", "US Other", "ARA", "Japan", "Singapore", "Fujairah"]]

    product_stocks_fill = product_stocks.copy()
    product_stocks_fill = product_stocks_fill.reindex(
        pd.date_range(product_stocks_fill.index[0], product_stocks_fill.index[-1])
    )
    product_stocks_fill.fillna(method="ffill", inplace=True)
    product_stocks_fill["Distillate"] = (
        product_stocks_fill["Weekly middle distillate inventories in ARA in kt"]
        + product_stocks_fill["Weekly jet/kero inventories in ARA in kt"]
        + product_stocks_fill["Weekly middle distillates inventories in Singapore in Mb"]
        * product_stocks_fill["Weekly middle distillates inventories in Singapore in Mb"]
        + product_stocks_fill["Weekly jet/kero inventories in Japan in kl"]
        + product_stocks_fill["Weekly kerosene inventories in Japan in kl"]
        + product_stocks_fill["Weekly diesel inventories in Japan in kl"]
        + product_stocks_fill["Weekly middle distillate inventories in Fujairah in Mb"] * 1000
        + product_stocks_fill["Weekly diesel inventories in United States in kb"]
    )
    product_stocks_fill["Light Ends"] = (
        product_stocks_fill["Weekly naphtha inventories in ARA in kt"]
        + product_stocks_fill["Weekly gasoline inventories in ARA in kt"]
        + product_stocks_fill["Weekly naphtha inventories in Japan in kl"]
        + product_stocks_fill["Weekly gasoline inventories in Japan in kl"]
        + product_stocks_fill["Weekly light distillate inventories in Singapore in Mb"]
        + product_stocks_fill["Weekly light distillates inventories in Fujairah in Mb"] * 1000
        + product_stocks_fill["Weekly gasoline inventories in United States in kb"]
    )
    product_stocks_fill["Fuel Oil"] = (
        product_stocks_fill["Weekly fuel oil inventories in ARA in kt"]
        + product_stocks_fill["Weekly fuel oil inventories in Singapore in Mb"]
        + product_stocks_fill["Weekly fuel oil inventories in Japan in mb"]
        + product_stocks_fill["Weekly residual and heavy distillates inventories in Fujairah in Mb"]
        * 1000
        + product_stocks_fill["Weekly residual fuel oil inventories in United States in kb"]
    )
    return product_by_loc, product_stocks_fill[["Distillate", "Light Ends", "Fuel Oil"]]


def get_platts(ticker, sdate, edate):
    df = platts.get_market_data(ticker, start_date=sdate, end_date=edate)
    df = df[["assessDate", "value"]]
    df.set_index("assessDate", inplace=True)
    df.index = pd.to_datetime(df.index)
    df.columns = ["PX_LAST"]
    return df


def product_inventory():
    product_stocks_ara = bbg.bdh(
        ["ARASGSLN Index", "ARASGO Index", "ARASKERO Index", "ARASNPHT Index", "ARASFO Index"],
        ["PX_LAST"],
        sdate=dt.datetime(2017, 1, 1),
        edate=today(),
    )
    product_stocks_sing = bbg.bdh(
        ["SPIVLDIS Index", "SPIVMDIS Index", "SPIVRESD Index"],
        ["PX_LAST"],
        sdate=dt.datetime(2017, 1, 1),
        edate=today(),
    )
    product_stocks_us = bbg.bdh(
        [
            "DOESTMGS Index",
            "DOESDIST Index",
            "DOESJETK Index",
            "DOESRESD Index",
            "DOESESPR Index",
            "DOESCRUD Index",
        ],
        ["PX_LAST"],
        sdate=dt.datetime(2017, 1, 1),
        edate=today(),
    )

    jp_gasoline = get_platts("AALNX00", sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_naphtha = pd.DataFrame(0.0, index=jp_gasoline.index, columns=["PX_LAST"])
    jp_jet = get_platts("AALQU00", sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_diesel = get_platts("AALNZ00", **_unrecovered("IMG_4173 original line296: remaining get_platts arguments"))
    jp_kero = jp_fo = fuj_light = fuj_middle = _unrecovered("IMG_4173/4174 original lines297-299: not photographed between page edges")


    fuj_res = get_platts("FUJHD04" , sdate=dt.datetime(2017, 1, 1), edate=today())

    product_stocks_ara["ARASNPHT Index"] = product_stocks_ara["ARASNPHT Index"] * 8.9
    product_stocks_ara["ARASGSLN Index"] = product_stocks_ara["ARASGSLN Index"] * 8.33
    product_stocks_ara["ARASKERO Index"] = product_stocks_ara["ARASKERO Index"] * 7.878
    product_stocks_ara["ARASGO Index"] = product_stocks_ara["ARASGO Index"] * 7.45
    product_stocks_ara["ARASFO Index"] = product_stocks_ara["ARASFO Index"] * 7.45
    jp_gasoline /= 1000
    jp_naphtha /= 1000
    jp_jet /= 1000
    jp_diesel /= 1000
    jp_kero /= 1000
    jp_fo /= 1000

    product_ara = product_stocks_ara[
        ["ARASGSLN Index", "ARASGO Index", "ARASKERO Index", "ARASFO Index"]
    ].sum(axis=1)
    product_sing = product_stocks_sing.sum(axis=1)
    product_fuj = fuj_light + fuj_middle + fuj_res
    product_jp = jp_gasoline + jp_naphtha + jp_jet + jp_diesel + jp_kero + jp_fo
    product_us = product_stocks_us[
        ["DOESTMGS Index", "DOESDIST Index", "DOESJETK Index", "DOESRESD Index"]
    ].sum(axis=1)
    product_us_other = (
        product_stocks_us["DOESESPR Index"] - product_stocks_us[ "DOESCRUD Index"] - product_us
    )
    product_by_loc = pd.concat(
        [product_us, product_us_other, product_ara, product_jP, product_sing, product_fuj], axis=1
    )
    product_by_loc.columns = ["US", "US Other", "ARA", "Japan", "Singapore", "Fujairah"]

    dts = pd.date_range(dt.datetime(2017, 1, 1), today() - dt.timedelta(1))
    product_light = pd.concat(
        [
            product_stocks_ara[["ARASGSLN Index", "ARASNPHT Index"]].sum(axis=1),
            jp_gasoline,
            jp_naphtha,
            fuj_light,
            product_stocks_sing["SPIVLDIS Index"],
            product_stocks_us["DOESTMGS Index"],
        ],
        axis=1,
    )
    product_light = product_light.reindex(dts). fillna(method="ffill"). sum(axis=1)
    product_middle = pd.concat(
        [
            product_stocks_ara[["ARASGO Index", "ARASKERO Index"]].sum(axis=1),
            jp_diesel,
            jp_jet,
            jp_kero,
            fuj_middle,
            product_stocks_sing["SPIVMDIS Index"],
            product_stocks_us[["DOESDIST Index", "DOESJETK Index"]].sum(axis=1),
        ],
        axis=1,
    )
    product_middle = product_middle.reindex(dts).fillna(method="ffill").sum(axis=1)
    product_fo = pd.concat(
        [
            product_stocks_ara["ARASFO Index"],
            jp_fo,
            fuj_res,
            product_stocks_sing["SPIVRESD Index"],
            product_stocks_us["DOESRESD Index"],
        ],
        axis=1,
    )
    product_fo = product_fo.reindex(dts).fillna(method="ffill").sum(axis=1)
    product_by_type = pd.concat([product_light, product_middle, product_fo], axis=1)
    product_by_type.columns = ["Distillate", "Light Ends", "Fuel Oil"]
    return product_by_loc.reindex(dts), product_by_type


def iea_summary(issue=-1):
    latest_iea = iea_folder_list()[issue]
    df = pd.read_csv(convert_path_to_linux(f"{latest_iea}\\SUMMARY.TXT"), header=None, sep="\s+")
    df.columns = ["Region", "Observation", "Date", "Value"]
    try:
        df.drop(df.loc[df["Value"].str.contains("x"), :].index, axis=0, inplace=True)
        df["Value"] = df["Value"].astype(np.float64)
    except:
        pass
    dfq = df.loc[df["Date"].str.contains("Q"), :]
    dfy = df.loc[~df.index.isin(dfq.index), :]
    dfq["Date"] = pd.to_datetime(dfq["Date"])
    return dfq, dfy


def iea_oecd_demand(issue=-1):
    latest_iea = iea_folder_list()[issue]
    df = pd.read_csv(convert_path_to_linux(f"{latest_iea}\\OECDDE.TXT"), header=None, sep="\s+")
    df.columns = ["Region", "Product", "Date", "Value"]
    try:
        df.drop(df.loc[df["Value"].str.contains("x"), :].index, axis=0, inplace=True)
        df["Value"] = df["Value"].astype(np.float64)
    except:
        pass
    dfm = df.loc[df["Date"].str.contains(r"[A-Z]{3}[0-9]{4}", regex=True), :]
    dfq = df.loc[df["Date"].str.contains(r"[1-4]Q", regex=True), :]
    dfy = df.loc[df["Date"].str.isdigit(), :]
    dfq["Date"] = pd.to_datetime(dfq["Date"])
    return dfm, dfq, dfy


def iea_nonoecd_demand(issue=-1):
    latest_iea = iea_folder_list()[issue]
    df = pd.read_csv(convert_path_to_linux(f"{latest_iea}\\NOECDDE.TXT"), header=None, sep="\s+")
    df.columns = ["Region", "Date", "Value"]
    try:
        df.drop(df.loc[df["Value"].str.contains("x"), :].index, axis=0, inplace=True)
        df["Value"] = df["Value"].astype(np.float64)
    except:
        pass
    dfq = df.loc[df["Date"].str.contains(r"[1-4]Q", regex=True), :]
    dfy = df.loc[df["Date"].str.isdigit(), :]
    dfq["Date"] = pd.to_datetime(dfq["Date"])
    return dfq, dfy


def iea_supply(issue=-1):
    latest_iea = iea_folder_list()[issue]
    df = pd.read_csv(convert_path_to_linux(f"{latest_iea}\\SUPPLY.TXT"), header=None, sep="\s+")
    df.columns = ["Region", "Product", "Date", "Value"]
    try:
        df.drop(df.loc[df["Value"].str.contains("x"), :].index, axis=0, inplace=True)
        df["Value"] = df["Value"].astype(np.float64)
    except:
        pass
    dfm = df.loc[df["Date"].str.contains(r"[A-Z]{3}[0-9]{4}", regex=True), :]
    dfq = df.loc[df["Date"].str.contains(r"[1-4]Q", regex=True), :]
    dfy = df.loc[df["Date"].str.isdigit(), :]
    dfq["Date"] = pd.to_datetime(dfq["Date"])
    return dfm, dfq, dfy


def iea_fbf(issue=-1):
    latest_iea = iea_folder_list()[issue]
    df = pd.read_csv(convert_path_to_linux(f"{latest_iea}\\field_by_field.csv"))
    df.rename(columns={"TIME": "Date", "VALUE": "Value"}, inplace=True)
    try:
        df.drop(df.loc[df["Value"].str.contains("x"), :].index, axis=0, inplace=True)
        df["Value"] = df["Value"].astype(np.float64)
    except:
        pass
    dfm = df.loc[df["Date"].str.contains(r"[A-Z]{3}[0-9]{4}", regex=True, na=False), :]
    dfq = df.loc[df["Date"].str.contains(r"[1-4]Q", regex=True, na=False), :]
    dfy = df.loc[df["Date"].str.contains(r"^[0-9]{4}", regex=True, na=False), :]
    dfq["Date"] = pd.to_datetime(dfq["Date"])
    return dfm, dfq, dfy


def iea_stock(issue=-1):
    latest_iea = iea_folder_list()[issue]
    df = pd.read_csv(convert_path_to_linux(f"{latest_iea}\\stockdat.TXT"), header=None, sep="\s+")
    df.columns = ["Govt_Industrial", "Country", "Product", "Date", "Value"]
    df["Value"] = df["Value"].astype(np.float64)
    df["Value"] = df["Value"] / 1000
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def filter(df, region, product=None):
    if product is None:
        df_ = df.loc[df["Region"] == region.upper(), :]
    else:
        df_ = df.loc[(df["Region"] == region.upper()) & (df["Product"] == product.upper()), :]
    df_ = df_[["Date", "Value"]]
    df_ = df_.set_index("Date")
    df_ = df_.drop(df_.loc[df_.iloc[:, 0] == 0, :].index, axis=0)
    return df_.iloc[:, 0]


def stock_filter(df, govt_industrial, country, product):
    df_ = df.loc[
        (df["Govt_Industrial"] == govt_industrial)
        & (df["Country"] == country)
        & (df["Product"] == product),
        ["Date", "Value"],
    ]
    df_["Date"] = pd.to_datetime(df_["Date"])
    df_ = (df_.set_index("Date")).sort_index()
    return df_.iloc[:, 0]


def create_table(total_table, table_name, **kwargs):
    combine_table = kwargs.get("combine_table", None)
    format_row = kwargs.get("format_row", None)
    start_date = kwargs.get("start_date", None)
    name_align = kwargs.get("name_align", "center")
    precision = kwargs.get("precision", 0)
    if start_date is not None:
        total_table = total_table.loc[total_table.index >= start_date, :]
        combine_table = combine_table.loc[combine_table.index >= str(start_date.year), :]
    try:
        total_table.index = total_table.index.to_period("Q")
    except:
        pass
    total_table = (total_table.T).reset_index()
    total_table.rename(columns={"index": table_name}, inplace=True)
    if combine_table is not None:
        comb = (combine_table.T).reset_index()
        total_table = pd.concat([total_table, comb.iloc[:, 1:]], axis=1)
    return table.html_format(
        df=total_table,
        precision=precision,
        format_column={
            total_table.columns[0]: {"width": "120px", "text-align": f"{name_align}"},
            tuple(total_table.columns[1:]): {"width": "80px", "text-align": "center"},
        },
        format_row=format_row,
    )


def stocks_to_quarterly_bpd_change(df):
    if isinstance(df, pd.Series):
        df = df.to_frame("PX_LAST")
    stocks_d = df.reindex(pd.date_range(df.index[0], df.index[-1]))
    stocks_d.fillna(method="ffill", inplace=True)
    stocks_m = stocks_d.resample("M").last()
    stocks_m["days"] = [calendar.monthrange(x.year, x.month)[1] for x in stocks_m.index]
    stocks_chg = stocks_m.iloc[:, 0].diff() / 1000 / stocks_m["days"]
    stocks_chg_q = stocks_chg.resample("Q").mean()
    stocks_chg_q.index = [
        x + relativedelta(days=1) - relativedelta(months=3) for x in stocks_chg_q.index
    ]
    return stocks_chg_q, stocks_chg


def ea_release_dates(dataset_id):
    response = pd.read_json(
        f"https://api.energyaspects.com/data/datasets/timeseries/{dataset_id}?api_key={dv.ea_api_key}"
    )
    release_dts = response.metadata.release_dates[-80:]
    return _unrecovered("IMG_4177/4178 original lines535-539: release-date filtering and return not photographed")


def ea_opec_crude_quarterly(issue=None):
    if issue is not None:
        if isinstance(issue, int):
            release_dts = ea_release_dates(dataset_id=5214)
            release_date = release_dts[issue]
        else:
            release_date = issue
        monthly_release_dts = ea_release_dates(dataset_id=14)
        opec_ea = dv.energy_aspects(
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242",
            start="2010-01-01",
            release_date=release_date,
        )
    else:
        opec_ea = dv.energy_aspects(
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242",
            start="2010-01-01",
        )
    opec_ea.set_index("Date", inplace=True)
    opec_ea.index = pd.to_datetime(opec_ea.index)
    opec_ea_q = opec_ea.resample("Q").mean()
    opec_ea_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in opec_ea_q.index]
    opec_columns = dv.ea_dataset(dataset_id="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242")
    for idx, row in opec_columns.iterrows():
        opec_columns.loc[idx, "metadata"] = row["metadata"]["description"]
    opec_columns.drop("additional_fields", axis=1, inplace=True)
    opec_ea_q = opec_ea_q[opec_columns["metadata"]]
    opec_ea_q.columns = opec_columns["dataset_id"]
    opec_ea_q.columns = [static_opec_columns[x] for x in opec_ea_q.columns]
    return opec_ea_q


def ea_opec_crude_monthly(issue=None):
    if issue is not None:
        if isinstance(issue, int):
            release_dts = ea_release_dates(dataset_id=5214)
            release_date = release_dts[issue]
        else:
            release_date = issue
        monthly_release_dts = ea_release_dates(dataset_id=14)
        opec_ea = dv.energy_aspects(
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242",
            start="2010-01-01",
            release_date=release_date,
        )
    else:
        opec_ea = dv.energy_aspects(
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242",
            start="2010-01-01",
        )
    opec_ea.set_index("Date", inplace=True)
    opec_ea.index = pd.to_datetime(opec_ea.index)
    opec_columns = dv.ea_dataset(dataset_id="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242")
    for idx, row in opec_columns.iterrows():
        opec_columns.loc[idx, "metadata"] = row["metadata"]["description"]
    opec_columns.drop("additional_fields", axis=1, inplace=True)
    opec_ea = opec_ea[opec_columns["metadata"]]
    opec_ea.columns = opec_columns["dataset_id"]
    opec_ea.columns = [static_opec_columns[x] for x in opec_ea.columns]
    return opec_ea


def ea_quarterly_balance(issue=None):
    if issue is not None:
        if isinstance(issue, int):
            release_dts = ea_release_dates(dataset_id=5214)
            release_date = release_dts[issue]
        else:
            release_date = issue
        demand = dv.energy_aspects(
            dataset_id=(
                "818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,834,835,"
                "836,837,838,839,840,841,842,843,844,845,846,847,848,849,5214,5215,5216,57,"
                "58,59,60,61,62,63,64,65,66,67,68,6471"
            ),
            start="2010-01-01",
            release_date=release_date,
        )
        crude = dv.energy_aspects(
            dataset_id=(
                "1064,1065,1066,1067,1068,1069,1070,1071,1072,1073,1074,1075,1076,1077,1078,1079,1080,1081,"
                "1082,1083,1084,1085,1086,1087,1088,1089,1090,1091,1092,1093,1094,1095,1096,1097,1098,1099,"
                "1100,1101,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111,1112,1113,1114,1115,1116,1117,"
                "1118,1119,1120,1121,1122,1123,1124,1125,1126,1127,1128,1129,1130,1131,1132,1133,1134,1135,"
                "1136,1137,1138,1139,1140,1141,1142,1143,1144,1145,1146,1147,1148,1149,1150,1151,1152,1153,"
                "1154,1155,1156,1157,1158,1159,1160,1161,1162,1163,1164,1165,1166,1167,1168,1169,1170,1171,"
                "1172,1173,1174,1175,1176,1177,1178,1179,1180,1181,1182,1183,1184,1185,1186,1187,1188,1189,"
                "1190,1191,1192,1193,1194,1195,1196,1197,1198,1199,1200,1201,1202,1203,1204,1205,1206,1207,"
                "1208,1209,1210,1211,1212,1213,1214,1215,1216,1217,1218,1219,1220,1221,1222,1223,1224,1225,"
                "1226,1227,1228,1229,1230,1231,1232,1233,1234,1235,1236,1237,1238,1239,1240,1241,1242,1243,"
                "1244,1245,1246,1247,1248,1249,1250,1251,1252,1253,1254,1255,1256,1257,1258,1259,1260,1261,"
                "1262,1263,1264,1265,1266,1267,1268,1269,1270,1271,1272,1273,1274"
            ),
            start="2010-01-01",
            release_date=release_date,
        )
        supply = dv.energy_aspects(
            dataset_id=(
                "850,851,852,853,854,855,856,857,858,859,860,861,862,863,864,865,866,867,"
                "868,869,870,871,872,873,874,875,876,877,878,879,880,881,882,883,884,885,"
                "886,887,888,889,890,891,892,893,894,895,896,897,898,899,900,901,902,903,"
                "904,905,906,907,908,909,910,911,912,913,914,915,916,917,918,919,920,921,"
                "922,923,924,925,926,927,928,929,930,931,932,933,934,935,936,937,938,939,"
                "940,941,942,943,944,945,946,947,948,949,950,951,952,953,954,955,956,957,"
                "958,959,960,961,962,963,964,965,966,967,968,969,970,971,972,973,974,975,"
                "976,977,978,979,980,981,982,983,984,985,986,987,988,989,990,991,992,993,"
                "994,995,996,997,998,999,1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,"
                "1012,1013,1014,1015,1016,1017,1018,1019,1020,1021,1022,1023,1024,1025,1026,1027,1028,1029,"
                "1030,1031,1032,1033,1034,1035,1036,1037,1038,1039,1040,1041,1042,1043,1044,1045,1046,1047,"
                "1048,1049,1050,1051,1052,1053,1054,1055,1056,1057,1058,1059,1060,1061,1062,1063"
            ),
            start="2010-01-01",
            release_date=release_date,
        )
    else:
        demand = dv.energy_aspects(
            dataset_id=(
                "818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,834,835,"
                "836,837,838,839,840,841,842,843,844,845,846,847,848,849,5214,5215,5216,57,"
                "58,59,60,61,62,63,64,65,66,67,68,6471"
            ),
            start="2010-01-01",
        )
        crude = dv.energy_aspects(
            dataset_id=(
                "1064,1065,1066,1067,1068,1069,1070,1071,1072,1073,1074,1075,1076,1077,1078,1079,1080,1081,"
                "1082,1083,1084,1085,1086,1087,1088,1089,1090,1091,1092,1093,1094,1095,1096,1097,1098,1099,"
                "1100,1101,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111,1112,1113,1114,1115,1116,1117,"
                "1118,1119,1120,1121,1122,1123,1124,1125,1126,1127,1128,1129,1130,1131,1132,1133,1134,1135,"
                "1136,1137,1138,1139,1140,1141,1142,1143,1144,1145,1146,1147,1148,1149,1150,1151,1152,1153,"
                "1154,1155,1156,1157,1158,1159,1160,1161,1162,1163,1164,1165,1166,1167,1168,1169,1170,1171,"
                "1172,1173,1174,1175,1176,1177,1178,1179,1180,1181,1182,1183,1184,1185,1186,1187,1188,1189,"
                "1190,1191,1192,1193,1194,1195,1196,1197,1198,1199,1200,1201,1202,1203,1204,1205,1206,1207,"
                "1208,1209,1210,1211,1212,1213,1214,1215,1216,1217,1218,1219,1220,1221,1222,1223,1224,1225,"
                "1226,1227,1228,1229,1230,1231,1232,1233,1234,1235,1236,1237,1238,1239,1240,1241,1242,1243,"
                "1244,1245,1246,1247,1248,1249,1250,1251,1252,1253,1254,1255,1256,1257,1258,1259,1260,1261,"
                "1262,1263,1264,1265,1266,1267,1268,1269,1270,1271,1272,1273,1274"
            ),
            start="2010-01-01",
        )
        supply = dv.energy_aspects(
            dataset_id=(
                "850,851,852,853,854,855,856,857,858,859,860,861,862,863,864,865,866,867,"
                "868,869,870,871,872,873,874,875,876,877,878,879,880,881,882,883,884,885,"
                "886,887,888,889,890,891,892,893,894,895,896,897,898,899,900,901,902,903,"
                "904,905,906,907,908,909,910,911,912,913,914,915,916,917,918,919,920,921,"
                "922,923,924,925,926,927,928,929,930,931,932,933,934,935,936,937,938,939,"
                "940,941,942,943,944,945,946,947,948,949,950,951,952,953,954,955,956,957,"
                "958,959,960,961,962,963,964,965,966,967,968,969,970,971,972,973,974,975,"
                "976,977,978,979,980,981,982,983,984,985,986,987,988,989,990,991,992,993,"
                "994,995,996,997,998,999,1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,"
                "1012,1013,1014,1015,1016,1017,1018,1019,1020,1021,1022,1023,1024,1025,1026,1027,1028,1029,"
                "1030,1031,1032,1033,1034,1035,1036,1037,1038,1039,1040,1041,1042,1043,1044,1045,1046,1047,"
                "1048,1049,1050,1051,1052,1053,1054,1055,1056,1057,1058,1059,1060,1061,1062,1063"
            ),
            start="2010-01-01",
        )
    demand.set_index("Date", inplace=True)
    demand.index = pd.to_datetime(demand.index)
    crude.set_index("Date", inplace=True)
    crude.index = pd.to_datetime(crude.index)
    supply.set_index("Date", inplace=True)
    supply.index = pd.to_datetime(supply.index)
    demand_q = demand.resample("Q").mean()
    demand_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in demand_q.index]
    crude_q = crude.resample("Q").mean()
    crude_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in crude_q.index]
    supply_q = supply.resample("Q").mean()
    supply_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in supply_q.index]
    ea_data = pd.concat([demand_q, supply_q, crude_q], axis=1)
    return ea_data


def ea_monthly_balance(issue=None):
    if issue is not None:
        if isinstance(issue, int):
            release_dts = ea_release_dates(dataset_id=5214)
            release_date = release_dts[issue]
        else:
            release_date = issue
        demand = dv.energy_aspects(
            dataset_id=(
                "818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,834,835,"
                "836,837,838,839,840,841,842,843,844,845,846,847,848,849,5214,5215,5216,57,"
                "58,59,60,61,62,63,64,65,66,67,68,6471"
            ),
            start="2010-01-01",
            release_date=release_date,
        )
        crude = dv.energy_aspects(
            dataset_id=(
                "1064,1065,1066,1067,1068,1069,1070,1071,1072,1073,1074,1075,1076,1077,1078,1079,1080,1081,"
                "1082,1083,1084,1085,1086,1087,1088,1089,1090,1091,1092,1093,1094,1095,1096,1097,1098,1099,"
                "1100,1101,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111,1112,1113,1114,1115,1116,1117,"
                "1118,1119,1120,1121,1122,1123,1124,1125,1126,1127,1128,1129,1130,1131,1132,1133,1134,1135,"
                "1136,1137,1138,1139,1140,1141,1142,1143,1144,1145,1146,1147,1148,1149,1150,1151,1152,1153,"
                "1154,1155,1156,1157,1158,1159,1160,1161,1162,1163,1164,1165,1166,1167,1168,1169,1170,1171,"
                "1172,1173,1174,1175,1176,1177,1178,1179,1180,1181,1182,1183,1184,1185,1186,1187,1188,1189,"
                "1190,1191,1192,1193,1194,1195,1196,1197,1198,1199,1200,1201,1202,1203,1204,1205,1206,1207,"
                "1208,1209,1210,1211,1212,1213,1214,1215,1216,1217,1218,1219,1220,1221,1222,1223,1224,1225,"
                "1226,1227,1228,1229,1230,1231,1232,1233,1234,1235,1236,1237,1238,1239,1240,1241,1242,1243,"
                "1244,1245,1246,1247,1248,1249,1250,1251,1252,1253,1254,1255,1256,1257,1258,1259,1260,1261,"
                "1262,1263,1264,1265,1266,1267,1268,1269,1270,1271,1272,1273,1274"
            ),
            start="2010-01-01",
            release_date=release_date,
        )
        supply = dv.energy_aspects(
            dataset_id=(
                "850,851,852,853,854,855,856,857,858,859,860,861,862,863,864,865,866,867,"
                "868,869,870,871,872,873,874,875,876,877,878,879,880,881,882,883,884,885,"
                "886,887,888,889,890,891,892,893,894,895,896,897,898,899,900,901,902,903,"
                "904,905,906,907,908,909,910,911,912,913,914,915,916,917,918,919,920,921,"
                "922,923,924,925,926,927,928,929,930,931,932,933,934,935,936,937,938,939,"
                "940,941,942,943,944,945,946,947,948,949,950,951,952,953,954,955,956,957,"
                "958,959,960,961,962,963,964,965,966,967,968,969,970,971,972,973,974,975,"
                "976,977,978,979,980,981,982,983,984,985,986,987,988,989,990,991,992,993,"
                "994,995,996,997,998,999,1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,"
                "1012,1013,1014,1015,1016,1017,1018,1019,1020,1021,1022,1023,1024,1025,1026,1027,1028,1029,"
                "1030,1031,1032,1033,1034,1035,1036,1037,1038,1039,1040,1041,1042,1043,1044,1045,1046,1047,"
                "1048,1049,1050,1051,1052,1053,1054,1055,1056,1057,1058,1059,1060,1061,1062,1063"
            ),
            start="2010-01-01",
            release_date=release_date,
        )
    else:
        demand = dv.energy_aspects(
            dataset_id=(
                "818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,834,835,"
                "836,837,838,839,840,841,842,843,844,845,846,847,848,849,5214,5215,5216,57,"
                "58,59,60,61,62,63,64,65,66,67,68,6471"
            ),
            start="2010-01-01",
        )
        crude = dv.energy_aspects(
            dataset_id=(
                "1064,1065,1066,1067,1068,1069,1070,1071,1072,1073,1074,1075,1076,1077,1078,1079,1080,1081,"
                "1082,1083,1084,1085,1086,1087,1088,1089,1090,1091,1092,1093,1094,1095,1096,1097,1098,1099,"
                "1100,1101,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111,1112,1113,1114,1115,1116,1117,"
                "1118,1119,1120,1121,1122,1123,1124,1125,1126,1127,1128,1129,1130,1131,1132,1133,1134,1135,"
                "1136,1137,1138,1139,1140,1141,1142,1143,1144,1145,1146,1147,1148,1149,1150,1151,1152,1153,"
                "1154,1155,1156,1157,1158,1159,1160,1161,1162,1163,1164,1165,1166,1167,1168,1169,1170,1171,"
                "1172,1173,1174,1175,1176,1177,1178,1179,1180,1181,1182,1183,1184,1185,1186,1187,1188,1189,"
                "1190,1191,1192,1193,1194,1195,1196,1197,1198,1199,1200,1201,1202,1203,1204,1205,1206,1207,"
                "1208,1209,1210,1211,1212,1213,1214,1215,1216,1217,1218,1219,1220,1221,1222,1223,1224,1225,"
                "1226,1227,1228,1229,1230,1231,1232,1233,1234,1235,1236,1237,1238,1239,1240,1241,1242,1243,"
                "1244,1245,1246,1247,1248,1249,1250,1251,1252,1253,1254,1255,1256,1257,1258,1259,1260,1261,"
                "1262,1263,1264,1265,1266,1267,1268,1269,1270,1271,1272,1273,1274"
            ),
            start="2010-01-01",
        )
        supply = dv.energy_aspects(
            dataset_id=(
                "850,851,852,853,854,855,856,857,858,859,860,861,862,863,864,865,866,867,"
                "868,869,870,871,872,873,874,875,876,877,878,879,880,881,882,883,884,885,"
                "886,887,888,889,890,891,892,893,894,895,896,897,898,899,900,901,902,903,"
                "904,905,906,907,908,909,910,911,912,913,914,915,916,917,918,919,920,921,"
                "922,923,924,925,926,927,928,929,930,931,932,933,934,935,936,937,938,939,"
                "940,941,942,943,944,945,946,947,948,949,950,951,952,953,954,955,956,957,"
                "958,959,960,961,962,963,964,965,966,967,968,969,970,971,972,973,974,975,"
                "976,977,978,979,980,981,982,983,984,985,986,987,988,989,990,991,992,993,"
                "994,995,996,997,998,999,1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,"
                "1012,1013,1014,1015,1016,1017,1018,1019,1020,1021,1022,1023,1024,1025,1026,1027,1028,1029,"
                "1030,1031,1032,1033,1034,1035,1036,1037,1038,1039,1040,1041,1042,1043,1044,1045,1046,1047,"
                "1048,1049,1050,1051,1052,1053,1054,1055,1056,1057,1058,1059,1060,1061,1062,1063"
            ),
            start="2010-01-01",
        )
    demand.set_index("Date", inplace=True)
    demand.index = pd.to_datetime(demand.index)
    crude.set_index("Date", inplace=True)
    crude.index = pd.to_datetime(crude.index)
    supply.set_index("Date", inplace=True)
    supply.index = pd.to_datetime(supply.index)
    ea_data = pd.concat([demand, supply, crude], axis=1)
    return ea_data


def steo_release(mon, yr):
    pre_df = pd.read_excel(
        f"https://www.eia.gov/outlooks/steo/archives/{mon.lower()}{yr}_base.xlsx",
        sheet_name="4atab",
    )
    pre_prod = pre_df.iloc[[1, 2, 5], 2:].T
    pre_prod.fillna(method="ffill", inplace=True)
    pre_prod["date"] = [
        dt.datetime.strptime(f"{pre_prod.iloc[x, 0]}-{pre_prod.iloc[x, 1]}-1", "%Y-%b-%d")
        for x in range(0, len(pre_prod))
    ]
    pre_prod = pre_prod[["date", 5]]
    pre_prod.columns = ["date", f"{mon}-{yr}"]
    pre_prod.set_index("date", inplace=True)
    return pre_prod * 1000


def update_iea_stocks_old():
    df = iea_stock(issue=-1)

    oecd_total = stock_filter(df, "INDUSTRY", "OECDTOT", "TOTALOIL")
    nam_total = stock_filter(df, "INDUSTRY", "OECDAME", "TOTALOIL")
    eu_total = stock_filter(df, "INDUSTRY", "OECDEUR", "TOTALOIL")

    oecd_crude = stock_filter(df, "INDUSTRY", "OECDTOT", "CRUDEOIL")
    nam_crude = stock_filter(df, "INDUSTRY", "OECDAME", "CRUDEOIL")
    eu_crude = stock_filter(df, "INDUSTRY", "OECDEUR", "CRUDEOIL")

    oecd_mogas = stock_filter(df, "INDUSTRY", "OECDTOT", "MOTORGAS")
    nam_mogas = stock_filter(df, "INDUSTRY", "OECDAME", "MOTORGAS")
    eu_mogas = stock_filter(df, "INDUSTRY", "OECDEUR", "MOTORGAS")

    oecd_disty = stock_filter(df, "INDUSTRY", "OECDTOT", "MIDDIST")
    nam_disty = stock_filter(df, "INDUSTRY", "OECDAME", "MIDDIST")
    eu_disty = stock_filter(df, "INDUSTRY", "OECDEUR", "MIDDIST")

    oecd_kpler = kpler_oecd_inventory()
    iea_kpler = pd.concat([oecd_crude, oecd_kpler], axis=1)
    iea_kpler.columns = ["IEA", "Kpler"]
    iea_kpler = iea_kpler.loc[iea_kpler.index >= dt.datetime(2018, 1, 1), :]
    last_valid = iea_kpler["IEA"].last_valid_index()
    lm = sm.OLS(iea_kpler.loc[:last_valid, "IEA"].values, iea_kpler.loc[:last_valid, "Kpler"]).fit()
    iea_kpler["Kpler Forecast"] = iea_kpler["Kpler"] * lm.params.values[0]
    fcst = iea_kpler["Kpler Forecast"].iloc[iea_kpler.index.get_loc(last_valid) + 1 :]

    def create_stock_table(oecd, nam, eu, table_name, period=None):
        total = pd.concat([oecd, nam, eu], axis=1)
        total.columns = ["OECD", "NAM", "EU"]
        if period is not None:
            total = total.diff(periods=period)
        total_table = total.iloc[-10:, :]
        total_table.index = [x.strftime("%#d-%b-%y") for x in total_table.index]
        total_table = (total_table.T).reset_index()
        total_table.rename(columns={"index": table_name}, inplace=True)
        return table.html_format(
            df=total_table,
            precision=0,
            format_column={tuple(total_table.columns): {"width": "80px", "text-align": "center"}},
        )

    def seasonal_chart_min_max_avg(
        df, title, y_axis_title=None, y_range=None, ytd=False, width=750, height=500, fcst=None
    ):
        df = df.loc[df.index >= dt.datetime(2016, 1, 1)]
        demand_by_year = ts.data_by_year(df, freq="M")
        demand_by_year.index = [dt.datetime(today().year, x + 1, 1) for x in demand_by_year.index]
        if ytd:
            demand_by_year = demand_by_year.cumsum(axis=0)
        demand_by_year["Max"] = demand_by_year.iloc[:, :4].max(axis=1)
        demand_by_year["Min"] = demand_by_year.iloc[:, :4].min(axis=1)
        demand_by_year["2016-2021 Avg"] = demand_by_year.iloc[:, :4].mean(axis=1)
        demand_by_year = demand_by_year.iloc[:, -6:]
        if fcst is None:
            return chart.line_chart(
                df=demand_by_year,
                title=title,
                y_axis_title=y_axis_title,
                highlight_dict={
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2016-2019 Avg": {"color": "black", "width": 2, "dash": "dash"},
                },
                tickformat=None,
                y_range=y_range,
                width=width,
                height=height,
            )
        else:
            last_idx = demand_by_year.iloc[:, 2].last_valid_index()
            last_loc = demand_by_year.index.get_loc(last_idx)
            demand_by_year["forecast"] = np.nan
            if last_loc < demand_by_year.shape[0] - len(fcst):
                demand_by_year.loc[last_idx, "forecast"] = demand_by_year.iloc[last_loc, 2]
                demand_by_year.loc[
                    demand_by_year.index[last_loc + 1 : last_loc + len(fcst) + 1], "forecast"
                ] = fcst.values
            elif last_loc == demand_by_year.shape[0] - 1:
                demand_by_year.loc[demand_by_year.index[:len(fcst)], "forecast"] = fcst.values
            else:
                demand_by_year["forecast next year"] = np.nan
                demand_by_year.loc[last_idx, "forecast"] = demand_by_year.iloc[last_loc, 2]
                demand_by_year.loc[demand_by_year.index[last_loc + 1 :], "forecast"] = fcst.values[
                    : demand_by_year.shape[0] - last_loc - 1
                ]
                demand_by_year.loc[
                    demand_by_year.index[: len(fcst) - (demand_by_year.shape[0] - last_loc - 1)],
                    "forecast next year",
                ] = fcst.values[demand_by_year.shape[0] - last_loc - 1 :]
            if "forecast next year" in demand_by_year.columns:
                highlight_dict = {
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2016-2019 Avg": {"color": "black", "width": 2, "dash": "dash"},
                    demand_by_year.columns[-2]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-1]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                }
            else:
                highlight_dict = {
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2016-2019 Avg": {"color": "black", "width": 2, "dash": "dash"},
                    demand_by_year.columns[-1]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                }
            return chart.line_chart(
                df=demand_by_year,
                title=title,
                y_axis_title=y_axis_title,
                highlight_dict=highlight_dict,
                tickformat=None,
                y_range=y_range,
                width=width,
                height=height,
            )

    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("<b>OECD oil inventory level (mbl)<b>")
    figs.append(create_stock_table(oecd_total, nam_total, eu_total, "TOTAL"))
    figs.append(create_stock_table(oecd_crude, nam_crude, eu_crude, "CRUDE"))
    figs.append(create_stock_table(oecd_mogas, nam_mogas, eu_mogas, "MOTORGAS"))
    figs.append(create_stock_table(oecd_disty, nam_disty, eu_disty, "DISTY"))
    figs.append(
        seasonal_chart_min_max_avg(
            df=oecd_total,
            title="Total OECD Liquids (mb) Commercial only",
            y_axis_title=None,
            y_range=None,
            ytd=False,
            width=750,
            height=500,
        )
    )
    figs.append(
        seasonal_chart_min_max_avg(
            df=oecd_crude,
            title="Total OECD Crude (mb) Commercial only",
            y_axis_title=None,
            y_range=None,
            ytd=False,
            width=750,
            height=500,
            fcst=fcst,
        )
    )
    figs.append(
        seasonal_chart_min_max_avg(
            df=oecd_disty,
            title="Total OECD Disty (mb) Commercial only",
            y_axis_title=None,
            y_range=None,
            ytd=False,
            width=750,
            height=500,
        )
    )
    figs.append(
        seasonal_chart_min_max_avg(
            df=eu_disty,
            title="Total EU Disty (mb) Commercial only",
            y_axis_title=None,
            y_range=None,
            ytd=False,
            width=750,
            height=500,
        )
    )
    figs.append("<b>OECD oil inventory mom change (mbl)<b>")
    figs.append(create_stock_table(oecd_total, nam_total, eu_total, "TOTAL", period=1))
    figs.append(create_stock_table(oecd_crude, nam_crude, eu_crude, "CRUDE", period=1))
    figs.append(create_stock_table(oecd_mogas, nam_mogas, eu_mogas, "MOTORGAS", period=1))
    figs.append(create_stock_table(oecd_disty, nam_disty, eu_disty, "DISTY", period=1))
    figs.append(
        seasonal_chart_min_max_avg(
            df=oecd_total.diff(),
            title="Total OECD Liquids (mb) Commercial only - MOM",
            y_axis_title=None,
            y_range=None,
            ytd=False,
            width=750,
            height=500,
        )
    )
    figs.append("<b>OECD oil inventory yoy change (mbl)<b>")
    figs.append(create_stock_table(oecd_total, nam_total, eu_total, "TOTAL", period=12))
    figs.append(create_stock_table(oecd_crude, nam_crude, eu_crude, "CRUDE", period=12))
    figs.append(create_stock_table(oecd_mogas, nam_mogas, eu_mogas, "MOTORGAS", period=12))
    figs.append(create_stock_table(oecd_disty, nam_disty, eu_disty, "DISTY", period=12))
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text("IEA Stocks", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\iea_stocks.html",
        task_name=report_name,
    )
    send_email(
        send_to=send_to,
        subject="IEA Stocks",
        body=figs,
        html_path=f"{html_path}\\oil\\iea_stocks.html",
    )


def update_iea_stocks():
    df = iea_stock(issue=-1)

    oecd_total = stock_filter(df, "INDUSTRY", "OECDTOT", "TOTALOIL")
    nam_total = stock_filter(df, "INDUSTRY", "OECDAME", "TOTALOIL")
    eu_total = stock_filter(df, "INDUSTRY", "OECDEUR", "TOTALOIL")

    oecd_crude = stock_filter(df, "INDUSTRY", "OECDTOT", "CRUDEOIL")
    nam_crude = stock_filter(df, "INDUSTRY", "OECDAME", "CRUDEOIL")
    eu_crude = stock_filter(df, "INDUSTRY", "OECDEUR", "CRUDEOIL")

    oecd_mogas = stock_filter(df, "INDUSTRY", "OECDTOT", "MOTORGAS")
    nam_mogas = stock_filter(df, "INDUSTRY", "OECDAME", "MOTORGAS")
    eu_mogas = stock_filter(df, "INDUSTRY", "OECDEUR", "MOTORGAS")

    oecd_disty = stock_filter(df, "INDUSTRY", "OECDTOT", "MIDDIST")
    nam_disty = stock_filter(df, "INDUSTRY", "OECDAME", "MIDDIST")
    eu_disty = stock_filter(df, "INDUSTRY", "OECDEUR", "MIDDIST")

    oecd_kpler = kpler_oecd_inventory()
    iea_kpler = pd.concat([oecd_crude, oecd_kpler], axis=1)
    iea_kpler.columns = ["IEA", "Kpler"]
    iea_kpler = iea_kpler.loc[iea_kpler.index >= dt.datetime(2018, 1, 1), :]
    last_valid = iea_kpler["IEA"].last_valid_index()
    iea_kpler["Kpler"] = iea_kpler["Kpler"].diff()
    fcst = (
        iea_kpler["Kpler"].iloc[iea_kpler.index.get_loc(last_valid) + 1 :].cumsum()
        + iea_kpler.loc[last_valid, "IEA"]
    )
    fcst_chg = iea_kpler["Kpler"].iloc[iea_kpler.index.get_loc(last_valid) + 1 :]
    inv = dv.GS(issue=[-1, -2]).monthly_data(item="OECD commercial stocks")
    inv["days"] = inv.index.days_in_month
    inv.loc[:, inv.columns[:-1]] = inv.loc[:, inv.columns[:-1]].apply(
        lambda x: x * inv["days"] / 1000
    )
    inv.drop("days", axis=1, inplace=True)
    inv.columns = ["GS_" + str(x) for x in inv.columns]
    if oecd_total.index[-1].year < today().year:
        inv_last_yr = oecd_total.iloc[-1]
        inv = inv.loc[
            (inv.index > dt.datetime(oecd_total.index[-1].year, 12, 1))
            & (inv.index <= dt.datetime(oecd_total.index[-1].year + 1, 12, 1)),
            :,
        ]
    else:
        inv_last_yr = oecd_total.loc[dt.datetime(oecd_total.index[-1].year - 1, 12, 1)]
        inv = inv.loc[
            (inv.index > dt.datetime(oecd_total.index[-1].year - 1, 12, 1))
            & (inv.index <= dt.datetime(oecd_total.index[-1].year, 12, 1)),
            :,
        ]
    inv_cum = inv.cumsum() + inv_last_yr
    product_land, product_by_type = product_inventory()
    dts = pd.date_range(oecd_total.index[0], product_land.index[-1])
    product_land = product_land.reindex(dts)
    product_land.fillna(method="ffill", inplace=True)
    product_land["Total"] = product_land[["US", "US Other", "ARA", "Japan", "Singapore"]].sum(
        axis=1
    )
    product_land["Year"] = product_land.index.year
    product_land["Month"] = product_land.index.month
    product_land_m = product_land.groupby(["Year", "Month"])["Total"].last()
    product_land_m.index = [dt.datetime(x[0], x[1], 1) for x in product_land_m.index]
    total_prod = (
        product_land_m / 1000 * 1.2 + oecd_kpler
    )  # US, ARA, Japan, Singapore product is less than IEA data, scale up by 1.2x
    iea_prod = pd.concat([oecd_total, total_prod], axis=1)
    iea_prod.columns = ["IEA", "Kpler+Agency"]
    iea_prod = iea_prod.loc[iea_prod.index >= dt.datetime(2018, 1, 1), :]
    last_valid = iea_prod["IEA"].last_valid_index()
    iea_prod["Kpler+Agency"] = iea_prod["Kpler+Agency"].diff()
    fcst_prod = (
        iea_prod["Kpler+Agency"].iloc[iea_prod.index.get_loc(last_valid) + 1 :].cumsum()
        + iea_prod.loc[last_valid, "IEA"]
    )
    fcst_chg_prod = iea_prod["Kpler+Agency"].iloc[iea_prod.index.get_loc(last_valid) + 1 :]

    def create_stock_table(oecd, nam, eu, table_name, period=None):
        total = pd.concat([oecd, nam, eu], axis=1)
        total.columns = ["OECD", "NAM", "EU"]
        if period is not None:
            total = total.diff(periods=period)
        total_table = total.iloc[-10:, :]
        total_table.index = [x.strftime("%#d-%b-%y") for x in total_table.index]
        total_table = (total_table.T).reset_index()
        total_table.rename(columns={"index": table_name}, inplace=True)
        return table.html_format(
            df=total_table,
            precision=0,
            format_column={tuple(total_table.columns): {"width": "80px", "text-align": "center"}},
        )


    def seasonal_chart_min_max_avg(
        df, title, y_axis_title=None, y_range=None, ytd=False, width=750, height=500, fcst=None, ltfcst=None
    ):
        df = df.loc[df.index >= dt.datetime(2017, 1, 1)]
        demand_by_year = ts.data_by_year(df, freq="M")
        demand_by_year.index = [dt.datetime(today().year, x + 1, 1) for x in demand_by_year.index]
        if ytd:
            demand_by_year = demand_by_year.cumsum(axis=0)
        demand_by_year = demand_by_year.drop(columns=[2020])
        demand_by_year["Max"] = demand_by_year.iloc[:, :5].max(axis=1)
        demand_by_year["Min"] = demand_by_year.iloc[:, :5].min(axis=1)
        demand_by_year["2017-2022 Avg"] = demand_by_year.iloc[:, :5].mean(axis=1)
        demand_by_year = demand_by_year.iloc[:, -6:]
        if fcst is None and ltfcst is None:
            return chart.line_chart(
                df=demand_by_year,
                title=title,
                y_axis_title=y_axis_title,
                highlight_dict={
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2017-2022 Avg": {"color": "black", "width": 2, "dash": "dash"},
                },
                tickformat=None,
                y_range=y_range,
                width=width,
                height=height,
            )
        elif fcst is not None and ltfcst is None:
            last_idx = demand_by_year.iloc[:, 2].last_valid_index()
            last_loc = demand_by_year.index.get_loc(last_idx)
            demand_by_year["forecast"] = np.nan
            if last_loc < demand_by_year.shape[0] - len(fcst):
                demand_by_year.loc[last_idx, "forecast"] = demand_by_year.iloc[last_loc, 2]
                demand_by_year.loc[
                    demand_by_year.index[last_loc + 1 : last_loc + len(fcst) + 1], "forecast"
                ] = fcst.values
            elif last_loc == demand_by_year.shape[0] - 1:
                demand_by_year.loc[demand_by_year.index[:len(fcst)], "forecast"] = fcst.values
            else:
                demand_by_year["forecast next year"] = np.nan
                demand_by_year.loc[last_idx, "forecast"] = demand_by_year.iloc[last_loc, 2]
                demand_by_year.loc[demand_by_year.index[last_loc + 1 :], "forecast"] = fcst.values[
                    : demand_by_year.shape[0] - last_loc - 1
                ]
                demand_by_year.loc[
                    demand_by_year.index[: len(fcst) - (demand_by_year.shape[0] - last_loc - 1)],
                    "forecast next year",
                ] = fcst.values[demand_by_year.shape[0] - last_loc - 1 :]
            if "forecast next year" in demand_by_year.columns:
                highlight_dict = {
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2017-2022 Avg": {"color": "black", "width": 2, "dash": "dash"},
                    demand_by_year.columns[-2]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-1]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                }
            else:
                highlight_dict = {
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2017-2022 Avg": {"color": "black", "width": 2, "dash": "dash"},
                    demand_by_year.columns[-1]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                }
            return chart.line_chart(
                df=demand_by_year,
                title=title,
                y_axis_title=y_axis_title,
                highlight_dict=highlight_dict,
                tickformat=None,
                y_range=y_range,
                width=width,
                height=height,
            )
        elif fcst is None and ltfcst is not None:
            demand_by_year = pd.concat([demand_by_year, ltfcst], axis=1)
            highlight_dict = {
                demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                "Max": {"color": "lightgrey", "width": 0},
                "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                "2017-2022 Avg": {"color": "black", "width": 2, "dash": "dash"},
                demand_by_year.columns[-2]: {"color": "orange", "width": 2, "mode": "markers+lines", "dash": "dash"},
                demand_by_year.columns[-1]: {"color": "blue", "width": 1, "mode": "markers+lines", "dash": "dash"},
            }
            return chart.line_chart(
                df=demand_by_year,
                title=title,
                y_axis_title=y_axis_title,
                highlight_dict=highlight_dict,
                tickformat=None,
                y_range=y_range,
                width=width,
                height=height,
            )
        else:
            last_idx = demand_by_year.iloc[:, 2].last_valid_index()
            last_loc = demand_by_year.index.get_loc(last_idx)
            demand_by_year["forecast"] = np.nan
            if last_loc < demand_by_year.shape[0] - len(fcst):
                demand_by_year.loc[last_idx, "forecast"] = demand_by_year.iloc[last_loc, 2]
                demand_by_year.loc[
                    demand_by_year.index[last_loc + 1 : last_loc + len(fcst) + 1], "forecast"
                ] = fcst.values
            elif last_loc == demand_by_year.shape[0] - 1:
                demand_by_year.loc[demand_by_year.index[:len(fcst)], "forecast"] = fcst.values
            else:
                demand_by_year["forecast next year"] = np.nan
                demand_by_year.loc[last_idx, "forecast"] = demand_by_year.iloc[last_loc, 2]
                demand_by_year.loc[demand_by_year.index[last_loc + 1 :], "forecast"] = fcst.values[
                    : demand_by_year.shape[0] - last_loc - 1
                ]
                demand_by_year.loc[
                    demand_by_year.index[: len(fcst) - (demand_by_year.shape[0] - last_loc - 1)],
                    "forecast next year",
                ] = fcst.values[demand_by_year.shape[0] - last_loc - 1 :]
            demand_by_year = pd.concat([demand_by_year, ltfcst], axis=1)
            if "forecast next year" in demand_by_year.columns:
                highlight_dict = {
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2017-2022 Avg": {"color": "black", "width": 2, "dash": "dash"},
                    demand_by_year.columns[-4]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-3]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-2]: {"color": "orange", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-1]: {"color": "blue", "width": 1, "mode": "markers+lines", "dash": "dash"},
                }
            else:
                highlight_dict = {
                    demand_by_year.columns[0]: {"color": "#17becf", "width": 2},
                    demand_by_year.columns[1]: {"color": "#e377c2", "width": 2},
                    demand_by_year.columns[2]: {"color": "red", "width": 2, "mode": "markers+lines"},
                    "Max": {"color": "lightgrey", "width": 0},
                    "Min": {"color": "lightgrey", "width": 0, "fill": "tonexty", "fillcolor": "rgba(0,0,0,0.1)"},
                    "2017-2022 Avg": {"color": "black", "width": 2, "dash": "dash"},
                    demand_by_year.columns[-3]: {"color": "red", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-2]: {"color": "orange", "width": 2, "mode": "markers+lines", "dash": "dash"},
                    demand_by_year.columns[-1]: {"color": "blue", "width": 1, "mode": "markers+lines", "dash": "dash"},
                }
            return chart.line_chart(
                df=demand_by_year,
                title=title,
                y_axis_title=y_axis_title,
                highlight_dict=highlight_dict,
                tickformat=None,
                y_range=y_range,
                width=width,
                height=height,
            )


    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    fig_oecd_total = seasonal_chart_min_max_avg(
        df=oecd_total,
        title="Total OECD Liquids (mb) Commercial only",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
        ltfcst=inv_cum,
        fcst=fcst_prod,
    )
    fig_oecd_total.write_json(
        convert_path_to_linux(f"{json_path}\\oil\\oecd_liquids_stocks_fig.json")
    )
    fig_oecd_total_mom = seasonal_chart_min_max_avg(
        df=oecd_total.diff(),
        title="Total OECD Liquids (mb) Commercial only - MOM",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
        ltfcst=inv,
        fcst=fcst_chg_prod,
    )
    figs.append([fig_oecd_total, fig_oecd_total_mom])
    fig_oecd_crude = seasonal_chart_min_max_avg(
        df=oecd_crude,
        title="Total OECD Crude (mb) Commercial only",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
        fcst=fcst,
    )
    fig_oecd_crude.write_json(
        _unrecovered("IMG_4194/4195 original line1557: crude chart JSON path not photographed")
    )
    fig_oecd_crude_mom = seasonal_chart_min_max_avg(
        df=oecd_crude.diff(),
        title="Total OECD Crude (mb) Commercial only - MOM",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
        fcst=fcst_chg,
    )
    figs.append([fig_oecd_crude, fig_oecd_crude_mom])
    fig_oecd_disty = seasonal_chart_min_max_avg(
        df=oecd_disty,
        title="Total OECD Disty (mb) Commercial only",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
    )
    fig_oecd_mogas = seasonal_chart_min_max_avg(
        df=oecd_mogas,
        title="Total OECD Mogas (mb) Commercial only",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
    )
    figs.append([fig_oecd_disty, fig_oecd_mogas])
    fig_eu_disty = seasonal_chart_min_max_avg(
        df=eu_disty,
        title="Total EU Disty (mb) Commercial only",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
    )
    fig_eu_mogas = seasonal_chart_min_max_avg(
        df=eu_mogas,
        title="Total EU Mogas (mb) Commercial only",
        y_axis_title=None,
        y_range=None,
        ytd=False,
        width=750,
        height=500,
    )
    figs.append([fig_eu_disty, fig_eu_mogas])
    figs.append("<b>OECD oil inventory level (mbl)<b>")
    figs.append(create_stock_table(oecd_total, nam_total, eu_total, "TOTAL"))
    figs.append(create_stock_table(oecd_crude, nam_crude, eu_crude, "CRUDE"))
    figs.append(create_stock_table(oecd_mogas, nam_mogas, eu_mogas, "MOTORGAS"))
    figs.append(create_stock_table(oecd_disty, nam_disty, eu_disty, "DISTY"))
    figs.append("<b>OECD oil inventory mom change (mbl)<b>")
    figs.append(create_stock_table(oecd_total, nam_total, eu_total, "TOTAL", period=1))
    figs.append(create_stock_table(oecd_crude, nam_crude, eu_crude, "CRUDE", period=1))
    figs.append(create_stock_table(oecd_mogas, nam_mogas, eu_mogas, "MOTORGAS", period=1))
    figs.append(create_stock_table(oecd_disty, nam_disty, eu_disty, "DISTY", period=1))
    figs.append("<b>OECD oil inventory yoy change (mbl)<b>")
    figs.append(create_stock_table(oecd_total, nam_total, eu_total, "TOTAL", period=12))
    figs.append(create_stock_table(oecd_crude, nam_crude, eu_crude, "CRUDE", period=12))
    figs.append(create_stock_table(oecd_mogas, nam_mogas, eu_mogas, "MOTORGAS", period=12))
    figs.append(create_stock_table(oecd_disty, nam_disty, eu_disty, "DISTY", period=12))
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html(
        [table.html_text("IEA Stocks", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\iea_stocks.html",
        task_name=report_name,
    )
    return [table.html_text("IEA Stocks", style="font-family:Calibri;", tag="h1")] + figs


def update_iea_demand_supply():
    dfq, dfy = iea_summary(issue=-1)
    dfq1, dfy1 = iea_summary(issue=-2)
    anchor = -int(iea_folder_list()[-1][-2:]) - 1
    dfq_anchor, dfy_anchor = iea_summary(issue=anchor)

    def stats(df, df1, df_anchor, region, name):
        start_date = dt.datetime((today() - relativedelta(months=6)).year, 1, 1)
        df_ = filter(df, region)
        df1_ = filter(df1, region)
        df1_anchor_ = filter(df_anchor, region)
        chg = df_ - df1_
        chg_anchor = df_ - df1_anchor_
        total = pd.concat([df_, chg, chg_anchor], axis=1)
        total.columns = [f"{name} Latest", "Change vs Piror", "YTD change"]
        try:
            return total.loc[total.index >= start_date]
        except:
            return total.loc[total.index >= str(start_date.year)]

    def yoy(df, df1, df_anchor, region, name):
        df_ = filter(df, region)
        df_ = df_.diff()
        df1_ = filter(df1, region)
        df1_ = df1_.diff()
        df1_anchor_ = filter(df_anchor, region)
        df1_anchor_ = df1_anchor_.diff()
        chg = df_ - df1_
        chg_anchor = df_ - df1_anchor_
        total = pd.concat([df_, chg, chg_anchor], axis=1)
        total.columns = [f"{name} Latest", "Change vs Piror", "YTD change"]
        return total.loc[total.index >= "2018"]

    demand_dict = {
        "TOTAL": "TOTALDEM",
        "OECD": "OECDDEM",
        "Non-OECD": "NOECDDEM",
        "American": "AMEDEM",
        "Europe": "EURODEM",
        "CHINA": "CHINADEM",
    }
    demq = {}
    demy = {}
    demyoy = {}
    for k, v in demand_dict.items():
        demq[k] = stats(dfq, dfq1, dfq_anchor, v, k)
        demy[k] = stats(dfy, dfy1, dfy_anchor, v, k)
        demyoy[k] = yoy(dfy, dfy1, dfy_anchor, v, k)
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append(f"<b>Oil Demand YOY change (kb)<b>")
    for k in demand_dict.keys():
        figs.append(create_table(demyoy[k], k))
    figs.append(f"<b>Oil Demand (kb)<b>")
    for k in demand_dict.keys():
        figs.append(create_table(demq[k], k, combine_table=demy[k]))
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(f"IEA Demand", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\iea_demand.html",
        task_name=report_name,
    )
    send_email(
        send_to=send_to,
        subject="IEA Demand",
        body=[f"Last Update {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"] + figs,
        html_path=f"{html_path}\\oil\\iea_demand.html",
    )
    supply_dict = {
        "TOTAL": "TOTALSUP",
        "OECD": "OECDSUP",
        "American": "AMESUP",
        "Non-OECD": "NOECDSUP",
        "Call on OPEC": "CALLOPECCU",
    }
    supq = {}
    supy = {}
    supyoy = {}
    anchor_date = f"{today().year-1}12"
    for k, v in supply_dict.items():
        if k == "TOTAL":
            onlyfiles = [
                f
                for f in os.listdir(convert_path_to_linux(f"{csv_path}\\oil\\iea"))
                if os.path.isfile(convert_path_to_linux(os.path.join(f"{csv_path}\\oil\\iea", f)))
            ]
            quarterly = [s for s in onlyfiles if "quarter_" in s]
            quarterly.sort()
            this_quarter = ts.read_csv(
                f"{csv_path}\\oil\\iea\\{quarterly[-1]}", index_name="Unnamed: 0"
            )
            last_quarter = ts.read_csv(
                f"{csv_path}\\oil\\iea\\{quarterly[-2]}", index_name="Unnamed: 0"
            )
            anchor_quarter = ts.read_csv(
                f"{csv_path}\\oil\\iea\\IEA_supply_quarter_{anchor_date}.csv",
                index_name="Unnamed: 0",
            )
            start_date = dt.datetime((today() - relativedelta(months=6)).year, 1, 1)
            chg = this_quarter["Total Supply"] - last_quarter["Total Supply"]
            chg_ytd = this_quarter["Total Supply"] - anchor_quarter["Total Supply"]
            total = pd.concat([this_quarter["Total Supply"], chg, chg_ytd], axis=1)
            total.columns = [f"TOTAL Latest", "Change vs Piror", "YTD Change"]
            supq[k] = total.loc[total.index >= start_date, :]
            annual = [s for s in onlyfiles if "annual_" in s]
            annual.sort()
            this_annual = pd.read_csv(convert_path_to_linux(f"{csv_path}\\oil\\iea\\{annual[-1]}"))
            this_annual.set_index("Unnamed: 0", inplace=True)
            last_annual = pd.read_csv(convert_path_to_linux(f"{csv_path}\\oil\\iea\\{annual[-2]}"))
            last_annual.set_index("Unnamed: 0", inplace=True)
            anchor_annual = pd.read_csv(
                convert_path_to_linux(f"{csv_path}\\oil\\iea\\IEA_supply_annual_{anchor_date}.csv")
            )
            anchor_annual.set_index("Unnamed: 0", inplace=True)
            chg = this_annual["Total Supply"] - last_annual["Total Supply"]
            chg_ytd = this_annual["Total Supply"] - anchor_annual["Total Supply"]
            total_yoy = pd.concat([this_annual["Total Supply"], chg, chg_ytd], axis=1)
            total_yoy.columns = [f"TOTAL Latest", "Change vs Piror", "YTD Change"]
            supyoy[k] = total_yoy.loc[total_yoy.index >= 2018, :]
            supy[k] = total_yoy.loc[total_yoy.index >= start_date.year, :]
        else:
            supq[k] = stats(dfq, dfq1, dfq_anchor, v, k)
            supy[k] = stats(dfy, dfy1, dfy_anchor, v, k)
            supyoy[k] = yoy(dfy, dfy1, dfy_anchor, v, k)
    figs_sup = []
    figs_sup.append("<div style='font-family:Calibri;' >")
    figs_sup.append(f"<b>Oil Supply YOY change (kb)<b>")
    for k in supply_dict.keys():
        figs_sup.append(create_table(supyoy[k], k))
    figs_sup.append(f"<b>Oil Supply (kb)<b>")
    for k in supply_dict.keys():
        figs_sup.append(create_table(supq[k], k, combine_table=supy[k]))
    figs_sup.append(
        table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    )
    table.figures_to_html(
        [table.html_text(f"IEA Supply", style="font-family:Calibri;", tag="h1")] + figs_sup,
        f"{html_path}\\oil\\iea_supply.html",
        task_name=report_name,
    )
    send_email(
        send_to=send_to,
        subject="IEA Supply",
        body=[f"Last Update {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"] + figs_sup,
        html_path=f"{html_path}\\oil\\iea_supply.html",
    )


def update_iea_balance(issue=-1):
    latest_iea_date = iea_folder_list()[issue][-6:]
    start_date = dt.datetime((today() - relativedelta(months=6)).year, 1, 1)
    summary_q, summary_y = iea_summary(issue=issue)
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    latest_iea = iea_folder_list()[issue]
    figs.append(f"IEA Release - {pd.to_datetime(latest_iea[-6:] + '01').strftime('%b %Y')}")
    oecd_dem_m, oecd_dem_q, oecd_dem_y = iea_oecd_demand(issue=issue)
    noecd_dem_q, noecd_dem_y = iea_nonoecd_demand(issue=issue)
    summary_dict = {
        'Total Demand': 'TOTALDEM',
        'OECD': 'OECDDEM',
        'Non-OECD': 'NOECDDEM',
        'CHINA': 'CHINADEM',
        'Other Asia': 'OTHASIADEM',
        'Other Latam': 'LATAMDEM',
        'FSU': 'FSUDEM',
        'Europe': 'EASTEURDEM',
    }
    oecd_dict = {
        'United States': 'USA',
        'Canada': 'CANADA',
        'Mexico': 'MEXICO',
        'OECD Europe': 'OECDEUR',
        'Japan': 'JAPAN',
        'South Korea': 'KOREA',
        'Australia': 'AUSTRALI',
        'New Zealand': 'NZ',
        'Other OECD': '-',
    }
    noecd_dict = {
        'India': 'INDIA',
        'Brazil': 'BRAZIL',
        'Middle East': 'MIDDLEEAST',
        'Africa': 'AFRICA',
        'Russia': 'RUSSIA',
    }
    summary = {}
    summary_a = {}
    oecd = {}
    oecd_a = {}
    noecd = {}
    noecd_a = {}
    for k, v in summary_dict.items():
        summary[k] = filter(summary_q, v)
        summary_a[k] = filter(summary_y, v)
    for k, v in oecd_dict.items():
        if k == "Other OECD":
            _oecd = pd.DataFrame.from_dict(oecd, orient="index").T
            oecd[k] = summary["OECD"] - _oecd.sum(axis=1)
            _oecd_a = pd.DataFrame.from_dict(oecd_a, orient="index").T
            oecd_a[k] = summary_a["OECD"] - _oecd_a.sum(axis=1)
        else:
            oecd[k] = filter(oecd_dem_q, v)
            oecd_a[k] = filter(oecd_dem_y, v)
    for k, v in noecd_dict.items():
        noecd[k] = filter(noecd_dem_q, v)
        noecd_a[k] = filter(noecd_dem_y, v)
    summary_df = pd.DataFrame.from_dict(summary, orient="index").T
    oecd_df = pd.DataFrame.from_dict(oecd, orient="index").T
    noecd_df = pd.DataFrame.from_dict(noecd, orient="index").T
    demand = pd.concat(
        [
            oecd_df,
            summary_df[["OECD"]],
            summary_df[["CHINA"]],
            noecd_df[["India"]],
            summary_df[["Other Asia"]],
            noecd_df[["Brazil"]],
            summary_df[["Other Latam"]],
            noecd_df[["Middle East"]],
            noecd_df[["Africa"]],
            noecd_df[["Russia"]],
            summary_df[["FSU"]],
            summary_df[["Europe"]],
            summary_df[["Non-OECD"]],
            summary_df[["Total Demand"]],
        ],
        axis=1,
    )
    summary_a_df = pd.DataFrame.from_dict(summary_a, orient="index").T
    oecd_a_df = pd.DataFrame.from_dict(oecd_a, orient="index").T
    noecd_a_df = pd.DataFrame.from_dict(noecd_a, orient="index").T
    demand_a = pd.concat(
        [
            oecd_a_df,
            summary_a_df[["OECD"]],
            summary_a_df[["CHINA"]],
            noecd_a_df[["India"]],
            summary_a_df[["Other Asia"]],
            noecd_a_df[["Brazil"]],
            summary_a_df[["Other Latam"]],
            noecd_a_df[["Middle East"]],
            noecd_a_df[["Africa"]],
            noecd_a_df[["Russia"]],
            summary_a_df[["FSU"]],
            summary_a_df[["Europe"]],
            summary_a_df[["Non-OECD"]],
            summary_a_df[["Total Demand"]],
        ],
        axis=1,
    )
    if "Australia" in demand.columns:
        demand.drop(["Australia"], axis=1, inplace=True)
    if "New Zealand" in demand.columns:
        demand.drop(["New Zealand"], axis=1, inplace=True)
    figs.append(
        create_table(
            total_table=demand,
            table_name="Demand",
            combine_table=demand_a,
            start_date=start_date,
            name_align="right",
            format_row={
                tuple([6, 17]): {"bottom_border": True},
                tuple([8, 19]): {"bold": True},
                tuple([7, 18]): {"bottom_border": True, "bold": True},
            },
        )
    )
    sup_m, sup_q, sup_a = iea_supply(issue=issue)
    summary_sup_dict = {
        "TOTAL": "TOTALSUP",
        "OECD": "OECDSUP",
        "Non-OECD": "NOECDSUP",
        "North America": "AMESUP",
        "Non-OPEC Asia": _unrecovered("IMG_4200/4201 original1919: supply region code not photographed"),
        "Non-OPEC Latam": "LATAMSUP",
        "Non-OPEC Mid East": "MIDEASTSUP",
        "Non-OPEC Africa": "AFRICASUP",
        "Total FSU": "FSUSUP",
        "Total Europe": "EUROSUP",
        "Processing Gains": "PROCGAIN",
        "Global Biofuels": "GLOBIOTOT",
    }
    sup_dict = {
        'US Crude': ['USA', 'CRUDE'],
        'US NGL': ['USA', 'NGLS'],
        'Canada': ['CANADA', 'TOTAL'],
        'Mexico': ['MEXICO', 'TOTAL'],
        'Chile': ['CHILE', 'TOTAL'],
        'Argentina': ['ARGENTINA', 'TOTAL'],
        'Brazil': ['BRAZIL', 'TOTAL'],
        'Colombia': ['COLOMBIA', 'TOTAL'],
        'Guyana': ['GUYANA', 'TOTAL'],
        'Norway': ['NORWAY', 'TOTAL'],
        'UK': ['UK', 'TOTAL'],
        'Russia Crude': ['RUSSIA', 'CRUDE'],
        'Russia NGL': ['RUSSIA', 'NGLS'],
        'China': ['CHINA', 'TOTAL'],
        'India': ['INDIA', 'TOTAL'],
        'Indonesia': ['INDONESIA', 'TOTAL'],
        'Malaysia': ['MALAYSIA', 'TOTAL'],
    }
    opec_dict = {
        'Algeria': ['Algeria', 'Monthly EA forecast for Algeria OPEC crude production in kb/d'],
        'CONGO': ['CONGO', 'Monthly EA forecast for Congo OPEC crude production in kb/d'],
        'EQUATORIAL': ['EQUATORIAL', 'Monthly EA forecast for Equatorial Guinea OPEC crude production in kb/d'],
        'GABON': ['GABON', 'Monthly EA forecast for Gabon OPEC crude production in kb/d'],
        'Iran': ['Iran', 'Monthly EA forecast for Iran OPEC crude production in kb/d'],
        'Iraq': ['Iraq', 'Monthly EA forecast for Iraq OPEC crude production in kb/d'],
        'Kuwait': ['Kuwait', 'Monthly EA forecast for Kuwait OPEC crude production in kb/d'],
        'Libya': ['Libya', 'Monthly EA forecast for Libya OPEC crude production in kb/d'],
        'Nigeria': ['Nigeria', 'Monthly EA forecast for Nigeria OPEC crude production in kb/d'],
        'Saudi': ['SAUDIARABI', 'Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d'],
        'UAE': ['UAE', 'Monthly EA forecast for UAE OPEC crude production in kb/d'],
        'Venezuela': ['Venezuela', 'Monthly EA forecast for Venezuela OPEC crude production in kb/d'],
    }
    summary_sup = {}
    summary_sup_a = {}
    nopec_sup = {}
    nopec_sup_a = {}
    opec = {}
    opec_a = {}
    for k, v in summary_sup_dict.items():
        summary_sup[k] = filter(summary_q, v)
        summary_sup_a[k] = filter(summary_y, v)
    for k, v in sup_dict.items():
        nopec_sup[k] = filter(sup_q, v[0], v[1])
        nopec_sup_a[k] = filter(sup_a, v[0], v[1])
    if issue == -1:
        opec_ea = dv.energy_aspects(
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242",
            start="2010-01-01",
        )
    else:
        release_date = dt.datetime(int(latest_iea_date[:4]), int(latest_iea_date[-2:]), 1)
        opec_ea = dv.energy_aspects(
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,5248,5247,5246,5245,5244,5243,5242",
            start="2010-01-01",
            release_date=release_date.strftime("%Y-%m-%d"),
        )
    opec_ea.set_index("Date", inplace=True)
    opec_ea.index = pd.to_datetime(opec_ea.index)
    opec_ea_q = opec_ea.resample("Q").mean()
    opec_ea_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in opec_ea_q.index]
    opec_ea_a = opec_ea.resample("A").mean()
    opec_ea_a.index = [str(x.year) for x in opec_ea_a.index]
    for k, v in opec_dict.items():
        print(k)
        opec[k] = filter(sup_q, v[0], "CRUDE")
        opec[k] = opec[k].drop(opec[k].loc[opec[k] == 0].index, axis=0)
        opec[k] = pd.concat(
            [opec[k], opec_ea_q.loc[opec[k].index[-1] + relativedelta(months=3) :, v[1]]], axis=0
        )
        opec_a[k] = filter(sup_a, v[0], "CRUDE")
        opec_a[k] = pd.concat(
            [opec_a[k], opec_ea_a.loc[str(int(opec_a[k].index[-1]) + 1) :, v[1]]], axis=0
        )
    opec_ngl = filter(summary_q, "OPECNGLS")
    opec_a_ngl = filter(summary_y, "OPECNGLS")
    sup_df = pd.DataFrame.from_dict(summary_sup)
    nopec_df = pd.DataFrame.from_dict(nopec_sup)
    opec_df = pd.DataFrame.from_dict(opec)
    supply = pd.concat(
        [
            sup_df[["OECD"]],
            sup_df[["Non-OECD"]],
            nopec_df[["US Crude"]],
            nopec_df[["US NGL"]],
            (nopec_df["US Crude"] + nopec_df["US NGL"]).to_frame("US Supply"),
            nopec_df[["Canada"]],
            nopec_df[["Mexico"]],
            nopec_df[["Chile"]],
            sup_df[["North America"]],
            nopec_df[["Argentina"]],
            nopec_df[["Brazil"]],
            nopec_df[["Colombia"]],
            nopec_df[["Guyana"]],
            sup_df[["Non-OPEC Latam"]],
            nopec_df[["Norway"]],
            nopec_df[["UK"]],
            sup_df[["Total Europe"]],
            nopec_df[["Russia Crude"]],
            nopec_df[["Russia NGL"]],
            sup_df[["Total FSU"]],
            nopec_df[["China"]],
            nopec_df[["India"]],
            nopec_df[["Indonesia"]],
            nopec_df[["Malaysia"]],
            sup_df[["Non-OPEC Asia"]],
            sup_df[["Non-OPEC Mid East"]],
            sup_df[["Non-OPEC Africa"]],
            sup_df[["Processing Gains"]],
            sup_df[["Global Biofuels"]],
            (sup_df["OECD"] + sup_df["Non-OECD"] + sup_df["Processing Gains"] + sup_df["Global Biofuels"]).to_frame("Non OPEC Supply"),
            opec_df,
            (opec_df.sum(axis=1)).to_frame("OPEC Crude"),
            opec_ngl.to_frame("OPEC NGL"),
            (opec_df.sum(axis=1) + opec_ngl).to_frame("OPEC Supply"),
            (sup_df["OECD"] + sup_df["Non-OECD"] + sup_df["Processing Gains"] + sup_df["Global Biofuels"] + opec_df.sum(axis=1) + opec_ngl).to_frame("Total Supply"),
        ],
        axis=1,
    )
    supply.to_csv(
        convert_path_to_linux(f"{csv_path}\\oil\\iea\\IEA_supply_quarter_{latest_iea_date}.csv")
    )
    sup_a_df = pd.DataFrame.from_dict(summary_sup_a)
    nopec_a_df = pd.DataFrame.from_dict(nopec_sup_a)
    opec_a_df = pd.DataFrame.from_dict(opec_a)
    supply_a = pd.concat(
        [
            sup_a_df[["OECD"]],
            sup_a_df[["Non-OECD"]],
            nopec_a_df[["US Crude"]],
            nopec_a_df[["US NGL"]],
            (nopec_a_df["US Crude"] + nopec_a_df["US NGL"]).to_frame("US Supply"),
            nopec_a_df[["Canada"]],
            nopec_a_df[["Mexico"]],
            nopec_a_df[["Chile"]],
            sup_a_df[["North America"]],
            nopec_a_df[["Argentina"]],
            nopec_a_df[["Brazil"]],
            nopec_a_df[["Colombia"]],
            nopec_a_df[["Guyana"]],
            sup_a_df[["Non-OPEC Latam"]],
            nopec_a_df[["Norway"]],
            nopec_a_df[["UK"]],
            sup_a_df[["Total Europe"]],
            nopec_a_df[["Russia Crude"]],
            nopec_a_df[["Russia NGL"]],
            sup_a_df[["Total FSU"]],
            nopec_a_df[["China"]],
            nopec_a_df[["India"]],
            nopec_a_df[["Indonesia"]],
            nopec_a_df[["Malaysia"]],
            sup_a_df[["Non-OPEC Asia"]],
            sup_a_df[["Non-OPEC Mid East"]],
            sup_a_df[["Non-OPEC Africa"]],
            sup_a_df[["Processing Gains"]],
            sup_a_df[["Global Biofuels"]],
            (sup_a_df["OECD"] + sup_a_df["Non-OECD"] + sup_a_df["Processing Gains"] + sup_a_df["Global Biofuels"]).to_frame("Non OPEC Supply"),
            opec_a_df,
            (opec_a_df.sum(axis=1)).to_frame("OPEC Crude"),
            opec_a_ngl.to_frame("OPEC NGL"),
            (opec_a_df.sum(axis=1) + opec_a_ngl).to_frame("OPEC Supply"),
            (sup_a_df["OECD"] + sup_a_df["Non-OECD"] + sup_a_df["Processing Gains"] + sup_a_df["Global Biofuels"] + opec_a_df.sum(axis=1) + opec_a_ngl).to_frame("Total Supply"),
        ],
        axis=1,
    )
    supply_a.to_csv(
        convert_path_to_linux(f"{csv_path}\\oil\\iea\\IEA_supply_annual_{latest_iea_date}.csv")
    )
    figs.append(
        create_table(
            total_table=supply,
            table_name="Supply",
            combine_table=supply_a,
            start_date=start_date,
            name_align="right",
            format_row={
                tuple([7, 12, 15, 18, 23, 28, 41]): {"bottom_border": True},
                tuple([0, 2, 4, 17, 24, 25, 26, 42, 45]): {"bold": True},
                tuple([1, 8, 13, 16, 19, 29, 44]): {"bottom_border": True, "bold": True},
            },
        )
    )
    inbalance_q = (sup_df["OECD"] + sup_df["Non-OECD"] + sup_df["Processing Gains"] + sup_df["Global Biofuels"] + opec_df.sum(axis=1) + opec_ngl) - summary_df["Total Demand"]
    inbalance_a = (sup_a_df["OECD"] + sup_a_df["Non-OECD"] + sup_a_df["Processing Gains"] + sup_a_df["Global Biofuels"] + opec_a_df.sum(axis=1) + opec_a_ngl) - summary_a_df["Total Demand"]
    balance = pd.concat(
        [
            summary_df[["OECD"]],
            summary_df[["Non-OECD"]],
            summary_df[["Total Demand"]],
            nopec_df[["US Crude"]],
            nopec_df[["Russia Crude"]],
            nopec_df[["Norway"]],
            nopec_df[["Brazil"]],
            (sup_df["OECD"] + sup_df["Non-OECD"] + sup_df["Processing Gains"] + sup_df["Global Biofuels"]).to_frame("Non OPEC Supply"),
            opec_df[["Saudi"]],
            (opec_df.sum(axis=1) - opec_df["Saudi"]).to_frame("OPEC ex Saudi"),
            (opec_df.sum(axis=1)).to_frame("OPEC Crude"),
            opec_ngl.to_frame("OPEC NGL"),
            (opec_df.sum(axis=1) + opec_ngl).to_frame("OPEC Supply"),
            (filter(summary_q, "CALLOPECCU") + opec_ngl).to_frame("Cal on OPEC"),
            (sup_df["OECD"] + sup_df["Non-OECD"] + sup_df["Processing Gains"] + sup_df["Global Biofuels"] + opec_df.sum(axis=1) + opec_ngl).to_frame("Total Supply"),
            inbalance_q.to_frame("Imbalance"),
        ],
        axis=1,
    )
    balance_a = pd.concat(
        [
            summary_a_df[["OECD"]],
            summary_a_df[["Non-OECD"]],
            summary_a_df[["Total Demand"]],
            nopec_a_df[["US Crude"]],
            nopec_a_df[["Russia Crude"]],
            nopec_a_df[["Norway"]],
            nopec_a_df[["Brazil"]],
            (sup_a_df["OECD"] + sup_a_df["Non-OECD"] + sup_a_df["Processing Gains"] + sup_a_df["Global Biofuels"]).to_frame("Non OPEC Supply"),
            opec_a_df[["Saudi"]],
            (opec_a_df.sum(axis=1) - opec_a_df["Saudi"]).to_frame("OPEC ex Saudi"),
            (opec_a_df.sum(axis=1)).to_frame("OPEC Crude"),
            opec_a_ngl.to_frame("OPEC NGL"),
            (opec_a_df.sum(axis=1) + opec_a_ngl).to_frame("OPEC Supply"),
            (filter(summary_y, "CALLOPECCU") + opec_a_ngl).to_frame("Cal on OPEC"),
            (sup_a_df["OECD"] + sup_a_df["Non-OECD"] + sup_a_df["Processing Gains"] + sup_a_df["Global Biofuels"] + opec_a_df.sum(axis=1) + opec_a_ngl).to_frame("Total Supply"),
            inbalance_a.to_frame("Imbalance"),
        ],
        axis=1,
    )
    figs.insert(
        2,
        create_table(
            total_table=balance,
            table_name="Balance",
            combine_table=balance_a,
            start_date=start_date,
            name_align="right",
            format_row={
                tuple([1, 6, 9, 11]): {"bottom_border": True},
                tuple([2, 7, 12, 14, 15]): {"bottom_border": True, "bold": True},
            },
        ),
    )
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(f"IEA Balance", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\iea_balance.html",
        task_name=report_name,
    )


def iea_quarterly_balance(issue=-1, ea_issue=None):
    if ea_issue is None:
        ea_issue = issue
    summary_q, summary_y = iea_summary(issue=issue)
    summary_sup_dict = {
        'Total Demand': 'TOTALDEM',
        'OECD Demand': 'OECDDEM',
        'Non-OECD Demand': 'NOECDDEM',
        'American Demand': 'AMEDEM',
        'Europe Demand': 'EURODEM',
        'China Demand': 'CHINADEM',
        'OECD Supply': 'OECDSUP',
        'Non-OECD Supply': 'NOECDSUP',
        'American Supply': 'AMESUP',
        'Processing Gains': 'PROCGAIN',
        'Global Biofuels': 'GLOBIOTOT',
        'Stock Change': 'STCHOECD',
        'OPEC NGLS': 'OPECNGLS',
    }
    summary_sup = {}
    for k, v in summary_sup_dict.items():
        summary_sup[k] = filter(summary_q, v)
    sup_df = pd.DataFrame.from_dict(summary_sup)
    sup_m, sup_q, sup_a = iea_supply(issue=issue)
    opec_ea_q = ea_opec_crude_quarterly(issue=ea_issue)
    opec_dict = {
        'Algeria': ['Algeria', 'Monthly EA forecast for Algeria OPEC crude production in kb/d'],
        'CONGO': ['CONGO', 'Monthly EA forecast for Congo OPEC crude production in kb/d'],
        'EQUATORIAL': ['EQUATORIAL', 'Monthly EA forecast for Equatorial Guinea OPEC crude production in kb/d'],
        'GABON': ['GABON', 'Monthly EA forecast for Gabon OPEC crude production in kb/d'],
        'Iran': ['Iran', 'Monthly EA forecast for Iran OPEC crude production in kb/d'],
        'Iraq': ['Iraq', 'Monthly EA forecast for Iraq OPEC crude production in kb/d'],
        'Kuwait': ['Kuwait', 'Monthly EA forecast for Kuwait OPEC crude production in kb/d'],
        'Libya': ['Libya', 'Monthly EA forecast for Libya OPEC crude production in kb/d'],
        'Nigeria': ['Nigeria', 'Monthly EA forecast for Nigeria OPEC crude production in kb/d'],
        'Saudi': ['SAUDIARABI', 'Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d'],
        'UAE': ['UAE', 'Monthly EA forecast for UAE OPEC crude production in kb/d'],
        'Venezuela': ['Venezuela', 'Monthly EA forecast for Venezuela OPEC crude production in kb/d'],
    }
    opec = {}
    for k, v in opec_dict.items():
        opec[k] = filter(sup_q, v[0], "CRUDE")
        opec[k] = opec[k].drop(opec[k].loc[opec[k] == 0].index, axis=0)
        try:
            opec[k] = pd.concat(
                [opec[k], opec_ea_q.loc[opec[k].index[-1] + relativedelta(months=3) :, v[1]]],
                axis=0,
            )
        except:
            pass
    opec_df = pd.DataFrame.from_dict(opec)
    opec_ngl = filter(summary_q, "OPECNGLS")
    iea_inbalance_q = (
        sup_df["OECD Supply"]
        + sup_df["Non-OECD Supply"]
        + sup_df["Processing Gains"]
        + sup_df["Global Biofuels"]
        + opec_df.sum(axis=1)
        + opec_ngl
    ) - sup_df["Total Demand"]
    sup_dict = {
        'US Crude Supply': ['USA', 'CRUDE'],
        'US NGL Supply': ['USA', 'NGLS'],
        'Canada Supply': ['CANADA', 'TOTAL'],
        'Mexico Supply': ['MEXICO', 'TOTAL'],
        'Chile Supply': ['CHILE', 'TOTAL'],
        'Argentina Supply': ['ARGENTINA', 'TOTAL'],
        'Brazil Supply': ['BRAZIL', 'TOTAL'],
        'Colombia Supply': ['COLOMBIA', 'TOTAL'],
        'Guyana Supply': ['GUYANA', 'TOTAL'],
        'Norway Supply': ['NORWAY', 'TOTAL'],
        'UK Supply': ['UK', 'TOTAL'],
        'Russia Crude Supply': ['RUSSIA', 'CRUDE'],
        'Russia NGL Supply': ['RUSSIA', 'NGLS'],
        'China Supply': ['CHINA', 'TOTAL'],
        'India Supply': ['INDIA', 'TOTAL'],
        'Indonesia Supply': ['INDONESIA', 'TOTAL'],
        'Malaysia Supply': ['MALAYSIA', 'TOTAL'],
    }
    nopec_sup = {}
    for k, v in sup_dict.items():
        nopec_sup[k] = filter(sup_q, v[0], v[1])
    nopec_df = pd.DataFrame.from_dict(nopec_sup)
    noecd_dem_q, noecd_dem_y = iea_nonoecd_demand(issue=issue)
    noecd_dict = {
        'India Demand': 'INDIA',
        'Brazil Demand': 'BRAZIL',
        'Middle East Demand': 'MIDDLEEAST',
        'Africa Demand': 'AFRICA',
        'Russia Demand': 'RUSSIA',
    }
    noecd_dem = {}
    for k, v in noecd_dict.items():
        noecd_dem[k] = filter(noecd_dem_q, v)
    noecd_df = pd.DataFrame.from_dict(noecd_dem)
    out_df = pd.concat(
        [
            sup_df[["Total Demand", "OECD Demand", "Non-OECD Demand", "American Demand", "Europe Demand", "China Demand"]],
            sup_df[["OECD Supply", "Non-OECD Supply", "American Supply", "OPEC NGLS", "Processing Gains", "Global Biofuels"]],
            iea_inbalance_q.to_frame("IEA Balance"),
            nopec_df,
            noecd_df,
        ],
        axis=1,
    )
    out_df["Non-OPEC Supply"] = out_df["OECD Supply"] + out_df["Non-OECD Supply"]
    return out_df


def update_observed_vs_forecast_balance():
    summary_q, summary_y = iea_summary(issue=-1)
    summary_sup_dict = {
        'Total Demand': 'TOTALDEM',
        'OECD': 'OECDSUP',
        'Non-OECD': 'NOECDSUP',
        'Processing Gains': 'PROCGAIN',
        'Global Biofuels': 'GLOBIOTOT',
        'Stock Change': 'STCHOECD',
    }
    summary_sup = {}
    for k, v in summary_sup_dict.items():
        summary_sup[k] = filter(summary_q, v)
    sup_df = pd.DataFrame.from_dict(summary_sup)
    sup_m, sup_q, sup_a = iea_supply(issue=-1)
    opec_ea_q = ea_opec_crude_quarterly()
    opec_ea_m = ea_opec_crude_monthly()
    opec_dict = {
        'Algeria': ['Algeria', 'Monthly EA forecast for Algeria OPEC crude production in kb/d'],
        'CONGO': ['CONGO', 'Monthly EA forecast for Congo OPEC crude production in kb/d'],
        'EQUATORIAL': ['EQUATORIAL', 'Monthly EA forecast for Equatorial Guinea OPEC crude production in kb/d'],
        'GABON': ['GABON', 'Monthly EA forecast for Gabon OPEC crude production in kb/d'],
        'Iran': ['Iran', 'Monthly EA forecast for Iran OPEC crude production in kb/d'],
        'Iraq': ['Iraq', 'Monthly EA forecast for Iraq OPEC crude production in kb/d'],
        'Kuwait': ['Kuwait', 'Monthly EA forecast for Kuwait OPEC crude production in kb/d'],
        'Libya': ['Libya', 'Monthly EA forecast for Libya OPEC crude production in kb/d'],
        'Nigeria': ['Nigeria', 'Monthly EA forecast for Nigeria OPEC crude production in kb/d'],
        'Saudi': ['SAUDIARABI', 'Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d'],
        'UAE': ['UAE', 'Monthly EA forecast for UAE OPEC crude production in kb/d'],
        'Venezuela': ['Venezuela', 'Monthly EA forecast for Venezuela OPEC crude production in kb/d'],
    }
    opec = {}
    for k, v in opec_dict.items():
        opec[k] = filter(sup_q, v[0], "CRUDE")
        opec[k] = opec[k].drop(opec[k].loc[opec[k] == 0].index, axis=0)
        opec[k] = pd.concat(
            [opec[k], opec_ea_q.loc[opec[k].index[-1] + relativedelta(months=3) :, v[1]]], axis=0
        )
    opec_df = pd.DataFrame.from_dict(opec)
    opec_ngl = filter(summary_q, "OPECNGLS")
    iea_inbalance_q = (
        sup_df["OECD"]
        + sup_df["Non-OECD"]
        + sup_df["Processing Gains"]
        + sup_df["Global Biofuels"]
        + opec_df.sum(axis=1)
        + opec_ngl
    ) - sup_df["Total Demand"]


    oecd_stock_chg = sup_df["Stock Change"]
    us_stocks = bbg.bdh("DOESESPR Index", ["PX_LAST"], dt.datetime(2005, 1, 1), today())
    us_q, us_m = stocks_to_quarterly_bpd_change(us_stocks)
    ara_stocks = bbg.bdh(".ARAPROD2 Index", ["PX_LAST"], dt.datetime(2005, 1, 1), today())
    ara_q, ara_m = stocks_to_quarterly_bpd_change(ara_stocks)
    sing_stocks = bbg.bdh("SPIVTOTL Index", ["PX_LAST"], dt.datetime(2005, 1, 1), today())
    sing_q, sing_m = stocks_to_quarterly_bpd_change(sing_stocks)
    crude_water = dv.kpler(
        (
            "/v1/fleet-metrics?metric=loaded_vessels&period=daily&startDate=2016-01-01&"
            "unit=kb&split=Total&products=crude%2fco"
        )
    )
    crude_water = kpler.convert_to_ts(crude_water)
    crude_water_q, crude_water_m = stocks_to_quarterly_bpd_change(crude_water)
    clean_water = dv.kpler(
        (
            "/v1/fleet-metrics?metric=loaded_vessels&period=daily&startDate=2016-01-01&"
            "unit=kb&split=Total&products=Clean%20Products"
        )
    )
    clean_water = kpler.convert_to_ts(clean_water)
    clean_water_q, clean_water_m = stocks_to_quarterly_bpd_change(clean_water)
    kpler_inv = dv.kpler("/v1/inventories?period=monthly&startDate=2016-01-01&split=byCountry")
    kpler_inv = kpler.convert_to_ts(kpler_inv)
    kpler_inv_ex_us = kpler_inv["Level (kb)"] - kpler_inv["United States"]
    kpler_inv_ex_us_q, kpler_inv_ex_us_m = stocks_to_quarterly_bpd_change(kpler_inv_ex_us)
    kpler_inv_china = kpler_inv["China"]
    kpler_inv_china_q, kpler_inv_china_m = stocks_to_quarterly_bpd_change(kpler_inv_china)
    obs = us_q + ara_q + sing_q + crude_water_q + clean_water_q
    obs_m = us_m + ara_m + sing_m + crude_water_m + clean_water_m
    ea_dem = dv.energy_aspects(
        dataset_id=(
            "818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,834,"
            "835,836,837,838,839,840,841,842,843,844,845,846,847,848,849,"
            "5214,5215,5216,57,58,59,60,61,62,63,64,65,66,67,68"
        ),
        start="2010-01-01",
    )
    ea_dem = kpler.convert_to_ts(
        ea_dem, columns=["Monthly EA forecast for liquids demand in World in kb/d"], forecast=True
    )
    ea_dem_q = ea_dem.resample("Q").mean()
    ea_dem_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in ea_dem_q.index]


    ea_sup = dv.energy_aspects(
        dataset_id=(
            "850,851,852,853,854,855,856,857,858,859,860,861,862,863,864,865,"
            "866,867,868,869,870,871,872,873,874,875,876,877,878,879,880,881,"
            "882,883,884,885,886,887,888,889,890,891,892,893,894,895,896,897,"
            "898,899,900,901,902,903,904,905,906,907,908,909,910,911,912,913,"
            "914,915,916,917,918,919,920,921,922,923,924,925,926,927,928,929,"
            "930,931,932,933,934,935,936,937,938,939,940,941,942,943,944,945,"
            "946,947,948,949,950,951,952,953,954,955,956,957,958,959,960,961,"
            "962,963,964,965,966,967,968,969,970,971,972,973,974,975,976,977,"
            "978,979,980,981,982,983,984,985,986,987,988,989,990,991,992,993,"
            "994,995,996,997,998,999,1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,"
            "1010,1011,1012,1013,1014,1015,1016,1017,1018,1019,1020,1021,1022,1023,1024,1025,"
            "1026,1027,1028,1029,1030,1031,1032,1033,1034,1035,1036,1037,1038,1039,1040,1041,"
            "1042,1043,1044,1045,1046,1047,1048,1049,1050,1051,1052,1053,1054,1055,1056,1057,"
            "1058,1059,1060,1061,1062,1063"
        ),
        start="2010-01-01",
    )
    ea_sup = kpler.convert_to_ts(
        ea_sup,
        columns=[
            "Monthly EA forecast for liquids production, including biofuels and processing gains, in total"
            + _unrecovered("IMG_4211 original2537: production series description clipped on right")
        ],
        forecast=True,
    )
    ea_sup_q = ea_sup.resample("Q").mean()
    ea_sup_q.index = [x + relativedelta(days=1) - relativedelta(months=3) for x in ea_sup_q.index]
    ea_balance = (
        opec_ea_q["Monthly EA forecast for total OPEC crude production in kb/d"]
        + opec_ea_q["Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d"]
        + ea_sup_q.iloc[:, 0]
    ) - ea_dem_q.iloc[:, 0]
    ea_balance_m = (
        opec_ea_m["Monthly EA forecast for total OPEC crude production in kb/d"]
        + opec_ea_m["Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d"]
        + ea_sup.iloc[:, 0]
    ) - ea_dem.iloc[:, 0]
    steo_dict = {
        "Non Opec Crude": "steo.PAPR_NONOPEC",
        "Opec NGL": "steo.OPEC_NC",
        "Steo Demand": "steo.PATC_WORLD",
        "Opec Crude": "steo.COPR_OPEC",
        "Stock Change": "steo.T3_STCHANGE_WORLD",
        "Stock Change US": "steo.T3_STCHANGE_US",
        "Stock Change Other OECD": "steo.T3_STCHANGE_OOECD",
    }
    steo = {}
    for k, v in steo_dict.items():
        print(k)
        steo[k] = dv.eia(v, freq="quarterly", facets="seriesId")
    dict_ecm = timeseries().history("element.liquid.global.balance.kbd.monthly.forecast")
    ecm_date = max(list(dict_ecm.keys()))
    ecm_snd = dict_ecm[ecm_date].resample("QS").mean()
    total_stocks = pd.concat(
        [
            iea_inbalance_q / 1000,
            oecd_stock_chg / 1000,
            ecm_snd / 1000,
            us_q,
            ara_q,
            sing_q,
            crude_water_q,
            clean_water_q,
            kpler_inv_ex_us_q,
            obs,
            ea_balance / 1000,
            steo["Stock Change"]["value"].astype(float) * -1,
        ],
        axis=1,
    )
    total_stocks.columns = [
        "IEA Imbalance", "OECD observed", "ECM", "US observed", "ARA observed", "Sing observed",
        "Dirty OOW", "Clean OOW", "Kpler Land Ex US", "Observed", "Aspects", "EIA",
    ]
    total_stocks = total_stocks[
        [
            "IEA Imbalance", "Aspects", "ECM", "OECD observed", "Observed", "US observed",
            "ARA observed", "Sing observed", "Dirty OOW", "Clean OOW", "Kpler Land Ex US",
        ]
    ]
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("Observed: US + ARA + Sing + Crude OOW + Clean OOW")
    total_stocks_ = total_stocks.loc[total_stocks.index >= dt.datetime(2023, 1, 1), :]
    figs.append(
        create_table(
            total_table=total_stocks_,
            precision=2,
            table_name="Imbalance",
            format_row={
                tuple([0, 3]): {"bold": True},
            },
        )
    )
    total_stocks_chart = total_stocks.loc[
        total_stocks.index >= dt.datetime(2021, 1, 1),
        ["IEA Imbalance", "Aspects", "OECD observed", "Observed"],
    ]
    figs.append(
        chart.line_chart(
            df=total_stocks_chart,
            title="Inventory vs balance",
            highlight_dict={
                "IEA Imbalance": {"color": "red", "width": 2, "mode": "markers+lines"},
                "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                "OECD observed": {"color": "black", "dash": "dash"},
            },
            tickformat=False,
        )
    )
    obs_m.index = [x + relativedelta(day=1) for x in obs_m.index]
    monthly_chart_data = pd.concat(
        [
            obs_m.iloc[-12:],
            ea_balance_m.loc[ea_balance_m.index >= obs_m.index[-12]].iloc[:18] / 1000,
        ],
        axis=1,
    )
    monthly_chart_data.columns = ["Observed", "EA forecast"]
    figs.append(
        chart.line_chart(
            df=monthly_chart_data,
            title="Observed inventory change + EA forecast",
            highlight_dict={
                "Observed": {"color": "red", "width": 2, "mode": "markers+lines"},
                "EA forecast": {"color": "blue", "width": 2, "mode": "markers+lines"},
            },
            tickformat=False,
        )
    )
    figs_stocks = update_iea_stocks()
    figs = figs + figs_stocks
    table.to_html(
        [table.html_text(f"IEA - Inventory vs Balances", style="font-family:Calibri;", tag="h1")]
        + figs,
        f"{html_path}\\oil\\inventory_vs_balances.html",
        task_name=report_name,
    )
    send_email(
        send_to=send_to,
        subject="IEA - Inventory vs Balances",
        body=[f"Last Update {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"] + figs,
        html_path=f"{html_path}\\oil\\inventory_vs_balances.html",
    )


def update_comparison():
    issues = 12
    ea_data = {}
    ea_data = {}
    iea_dt_list = []
    for i in range(0, -issues, -1):
        iea_dt_list.append(
            dt.datetime(int(iea_folder_list()[i - 1][-6:-2]), int(iea_folder_list()[i - 1][-2:]), 1)
        )
        iea_data[i] = iea_quarterly_balance(issue=i - 1)
        ea = ea_quarterly_balance(issue=i - 1)
        ea_opec = ea_opec_crude_quarterly(issue=i - 1)
        try:
            ea_bal = (
                ea[
                    "Monthly EA forecast for liquids production, including biofuels and processing gains, i"
                    + _unrecovered("IMG_4214 original2712: supply series suffix clipped")
                ]
                + ea_opec[
                    [
                        "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
                        "Monthly EA forecast for total OPEC crude production in kb/d",
                    ]
                ].sum(axis=1)
                - ea["Monthly EA forecast for liquids demand in World in kb/d"]
            )
        except:
            try:
                ea_bal = (
                    ea["Monthly total non-OPEC liquids production, including biofuels and processing gains, in kb/d"]
                    + ea_opec[
                        [
                            "Total OPEC NGL production, including condensate, EA forecast, kb/d",
                            "Monthly EA forecast for total OPEC crude production in kb/d",
                        ]
                    ].sum(axis=1)
                    - ea["Monthly EA forecast for liquids demand in World in kb/d"]
                )
            except:
                print("error")
        ea_data[i] = pd.concat([ea, ea_opec, ea_bal.to_frame("EA Balance")], axis=1)
    display_section = "Balance"
    compare_list = [
        ['IEA Balance', 'EA Balance', 'Q', 'Balance', 'steo.T3_STCHANGE_WORLD'],
        ['Total Demand', 'Monthly EA forecast for liquids demand in World in kb/d', 'Y', 'Total Demand yoy', 'steo.PATC_WORLD'],
        ['China Demand', 'Monthly EA forecast for liquids demand in China in kb/d', 'Y', 'China Demand yoy', 'steo.PATC_CH'],
        ['India Demand', 'Monthly EA forecast for liquids demand in India in kb/d', 'Y', 'India Demand yoy', None],
        ['Middle East Demand', 'Monthly EA forecast for liquids demand in Non-OECD Middle East in kb/d', 'Y', 'Middle East Demand yoy', None],
        ['American Demand', 'Monthly EA forecast for liquids demand in North America in kb/d', 'Y', 'North American Demand yoy', ['steo.PATC_US', 'steo.PATC_CA']],
        ['Europe Demand', 'Monthly EA forecast for liquids demand in OECD Europe in kb/d', 'Y', 'Europe Demand yoy', 'steo.PATC_OECD_EUROPE'],
        ['Non-OPEC Supply', "Monthly EA forecast for liquids production, including biofuels and processing gains, in total" + _unrecovered("IMG_4215 original2791: supply series suffix clipped"), 'Y', 'Non-OPEC Supply yoy', None],
        ['US Crude Supply', 'Monthly EA forecast for crude production (including field condensate) in United States in kb/d', 'Y', 'US Crude Supply yoy', None],
        ['Canada Supply', 'Monthly EA forecast for crude production (including field condensate) in Canada in kb/d', 'Y', 'Canada Supply yoy', None],
        ['Brazil Supply', 'Monthly EA forecast for crude production (including field condensate) in Brazil in kb/d', 'Y', 'Brazil Supply yoy', None],
        ['Guyana Supply', 'Monthly EA forecast for crude production (including field condensate) in Guyana in kb/d', 'Y', 'Guyana Supply yoy', None],
        ['Russia Crude Supply', 'Monthly EA forecast for crude production (including field condensate) in Russia in kb/d', 'Y', 'Russia Supply yoy', None],
        [None, 'Monthly EA forecast for total OPEC crude production in kb/d', 'Y', 'OPEC Supply yoy', None],
        [None, 'Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d', 'Y', 'Saudi Arabia Supply yoy', None],
        [None, 'Monthly EA forecast for UAE OPEC crude production in kb/d', 'Y', 'UAE Supply yoy', None],
        [None, 'Monthly EA forecast for Iran OPEC crude production in kb/d', 'Y', 'Iran Supply yoy', None],
        [None, 'Monthly EA forecast for Venezuela OPEC crude production in kb/d', 'Y', 'Venezuela Supply yoy', None],
    ]
    compare_list_old = [
        ['IEA Balance', 'EA Balance', 'Q', 'Balance', 'steo.T3_STCHANGE_WORLD'],
        ['Total Demand', 'Monthly EA forecast for liquids demand in World in kb/d', 'Y', 'Total Demand yoy', 'steo.PATC_WORLD'],
        ['China Demand', 'Monthly EA forecast for liquids demand in China in kb/d', 'Y', 'China Demand yoy', 'steo.PATC_CH'],
        ['India Demand', 'Monthly EA forecast for liquids demand in India in kb/d', 'Y', 'India Demand yoy', None],
        ['Middle East Demand', 'Monthly EA forecast for liquids demand in Non-OECD Middle East in kb/d', 'Y', 'Middle East Demand yoy', None],
        ['American Demand', 'Monthly EA forecast for liquids demand in North America in kb/d', 'Y', 'North American Demand yoy', ['steo.PATC_US', 'steo.PATC_CA']],
        ['Europe Demand', 'Monthly EA forecast for liquids demand in OECD Europe in kb/d', 'Y', 'Europe Demand yoy', 'steo.PATC_OECD_EUROPE'],
        ['Non-OPEC Supply', 'Monthly total non-OPEC liquids production, including biofuels and processing gains, in kb/d', 'Y', 'Non-OPEC Supply yoy', None],
        ['US Crude Supply', 'Monthly United States crude production in kb/d (includes field condensate)', 'Y', 'US Crude Supply yoy', None],
        ['Canada Supply', 'Monthly Canada crude production in kb/d (includes field condensate)', 'Y', 'Canada Supply yoy', None],
        ['Brazil Supply', 'Monthly Brazil crude production in kb/d (includes field condensate)', 'Y', 'Brazil Supply yoy', None],
        ['Guyana Supply', 'Monthly Guyana crude production in kb/d (includes field condensate)', 'Y', 'Guyana Supply yoy', None],
        ['Russia Crude Supply', 'Monthly Russia crude production in kb/d (includes field condensate)', 'Y', 'Russia Supply yoy', None],
        [None, 'Monthly EA forecast for total OPEC crude production in kb/d', 'Y', 'OPEC Supply yoy', None],
        [None, 'Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d', 'Y', 'Saudi Arabia Supply yoy', None],
        [None, 'Monthly EA forecast for UAE OPEC crude production in kb/d', 'Y', 'UAE Supply yoy', None],
        [None, 'Monthly EA forecast for Iran OPEC crude production in kb/d', 'Y', 'Iran Supply yoy', None],
        [None, 'Monthly EA forecast for Venezuela OPEC crude production in kb/d', 'Y', 'Venezuela Supply yoy', None],
    ]
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("<b>Unit: kbd</b><br>")
    release_ea = ea_release_dates(dataset_id=5214)[-1][:10]
    release_iea = iea_folder_list()[-1][-6:]
    figs.append(f"<b>EA release date: {release_ea}</b><br>")
    figs.append(f"<b>IEA release date: {release_iea}</b><br>")
    for _idx, item in enumerate(compare_list):
        iea_balance = pd.DataFrame()
        ea_balance = pd.DataFrame()


        for dt_idx, i in enumerate(range(0, -issues, -1)):
            try:
                ea_balance = pd.concat(
                    [ea_balance, ea_data[i][item[1]].to_frame(iea_dt_list[dt_idx])], axis=1
                )
            except:
                try:
                    ea_balance = pd.concat(
                        [ea_balance, ea_data[i][compare_list_old[_idx][1]].to_frame(iea_dt_list[dt_idx])],
                        axis=1,
                    )
                except:
                    print("error")
            try:
                iea_balance = pd.concat(
                    [iea_balance, iea_data[i][item[0]].to_frame(iea_dt_list[dt_idx])], axis=1
                )
            except:
                iea_balance = ea_balance.copy()
        iea_balance.index = pd.to_datetime(iea_balance.index)
        ea_balance.index = pd.to_datetime(ea_balance.index)
        if item[2] == "Q":
            start_date = dt.datetime(today().year - 1, 1, 1)
            iea_balance_q = iea_balance.loc[iea_balance.index >= start_date, :]
            ea_balance_q = ea_balance.loc[ea_balance.index >= start_date, :]
            table_df = pd.concat([iea_balance_q.iloc[:, 0], ea_balance_q.iloc[:, 0]], axis=1)
            start_date_yoy = dt.datetime(today().year - 2, 1, 1)
            iea_balance_yoy = iea_balance.loc[iea_balance.index >= start_date_yoy, :]
            ea_balance_yoy = ea_balance.loc[ea_balance.index >= start_date_yoy, :]
            iea_balance_yoy = iea_balance_yoy.resample("A").mean().diff()
            ea_balance_yoy = ea_balance_yoy.resample("A").mean().diff()
            table_df_yoy = pd.concat(
                [iea_balance_yoy.iloc[:, 0], ea_balance_yoy.iloc[:, 0]], axis=1
            )
            table_df_yoy = table_df_yoy.loc[table_df_yoy.index >= start_date, :]
        elif item[2] == "Y":
            table_df = pd.concat([iea_balance.iloc[:, 0], ea_balance.iloc[:, 0]], axis=1)
            table_df = table_df.loc[table_df.index >= start_date, :]
            iea_balance = iea_balance.resample("A").mean().diff()
            ea_balance = ea_balance.resample("A").mean().diff()
            start_date = today() - relativedelta(months=6) + relativedelta(day=1)
            iea_balance = iea_balance.loc[iea_balance.index >= start_date, :]
            ea_balance = ea_balance.loc[ea_balance.index >= start_date, :]
        if item[0] == "IEA Balance":
            table_df.columns = ["IEA", "Aspects"]
            table_df_yoy.columns = ["IEA", "Aspects"]
            if item[4] is not None:
                if isinstance(item[4], list):
                    eia = pd.DataFrame()
                    for j in item[4]:
                        eia[j] = dv.eia(j, freq="quarterly", facets="seriesId").value
                    eia = eia.sum(axis=1)
                else:
                    eia = dv.eia(item[4], freq="quarterly", facets="seriesId").value
                eia_yoy = eia.loc[eia.index >= start_date_yoy]
                eia_yoy = eia_yoy.astype(float) * 1000
                eia_yoy = eia_yoy.resample("A").mean().diff()
                eia_yoy = eia_yoy.loc[eia_yoy.index >= start_date]
                if item[4] == "steo.T3_STCHANGE_WORLD":
                    table_df.loc[:, "EIA"] = -eia.reindex(table_df.index).astype(float) * 1000
                    table_df_yoy.loc[:, "EIA"] = -eia_yoy
                else:
                    table_df.loc[:, "EIA"] = eia.reindex(table_df.index).astype(float) * 1000
                    table_df_yoy.loc[:, "EIA"] = eia_yoy
            table_df.index = [str(x.to_period("Q")) for x in table_df.index]
            table_df_yoy.index = ["YoY " + str(x.to_period("Y")) for x in table_df_yoy.index]
            table_df = pd.concat([table_df, table_df_yoy], axis=0)
            table_df = table_df.T
            table_df.index.name = "Source"
            table_df.reset_index(inplace=True)
            figs.append(
                table.html_format(
                    df=table_df,
                    precision=0,
                    header=f"{item[3]}",
                    format_column={tuple(table_df.columns): {"width": "80px", "text-align": "center"}},
                )
            )
        if item[3] == "Balance" or len(iea_balance) == 1:
            byyr_iea = iea_balance.copy()
            byyr_iea["year"] = byyr_iea.index.year
            byyrd_iea = byyr_iea.groupby("year").mean()
            byyr_ea = ea_balance.copy()
            byyr_ea["year"] = byyr_ea.index.year
            byyrd_ea = byyr_ea.groupby("year").mean()
            if byyrd_iea.shape[0] == 1:
                period = str(byyrd_iea.index[0])
                df = pd.concat([byyrd_iea.iloc[i, :].T, byyrd_ea.iloc[i, :].T], axis=1)
                df.columns = ["IEA", "Aspects"]
                figs.append(
                    chart.line_chart(
                        df=df,
                        title=f"{period} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        width=750,
                        height=500,
                    )
                )
            elif byyrd_iea.shape[0] == 2:
                byyrd_iea = byyrd_iea.iloc[-2:, :]
                byyrd_ea = byyrd_ea.iloc[-2:, :]
                period1 = str(byyrd_iea.index[0])
                period2 = str(byyrd_iea.index[1])
                df1 = pd.concat([byyrd_iea.iloc[0, :].T, byyrd_ea.iloc[0, :].T], axis=1)
                df2 = pd.concat([byyrd_iea.iloc[1, :].T, byyrd_ea.iloc[1, :].T], axis=1)
                df1.columns = ["IEA", "Aspects"]
                df2.columns = ["IEA", "Aspects"]
                figs.append(
                    chart.line_chart(
                        df=df1,
                        data_ply1c2=df2,
                        col=2,
                        column_titles=[f"{period1} {item[3]}", f"{period2} {item[3]}"],
                        tickformat=False,
                        highlight_dict={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        highlight_dict_c2={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        width=1200,
                        height=500,
                    )
                )
            elif byyrd_iea.shape[0] == 3:
                byyrd_iea = byyrd_iea.iloc[-3:, :]
                byyrd_ea = byyrd_ea.iloc[-3:, :]
                period1 = str(byyrd_iea.index[0])
                period2 = str(byyrd_iea.index[1])
                period3 = str(byyrd_iea.index[2])
                df1 = pd.concat([byyrd_iea.iloc[0, :].T, byyrd_ea.iloc[0, :].T], axis=1)
                df2 = pd.concat([byyrd_iea.iloc[1, :].T, byyrd_ea.iloc[1, :].T], axis=1)
                df3 = pd.concat([byyrd_iea.iloc[2, :].T, byyrd_ea.iloc[2, :].T], axis=1)
                df1.columns = ["IEA", "Aspects"]
                df2.columns = ["IEA", "Aspects"]
                df3.columns = ["IEA", "Aspects"]
                chart1 = chart.line_chart(
                    df=df1,
                    title=f"{period1} {item[3]}",
                    tickformat=False,
                    highlight_dict={
                        "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                        "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                    },
                    showlegend=False,
                    width=600,
                    height=500,
                )
                chart2 = chart.line_chart(
                    df=df2,
                    title=f"{period2} {item[3]}",
                    tickformat=False,
                    highlight_dict={
                        "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                        "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                    },
                    showlegend=False,
                    width=600,
                    height=500,
                )
                chart3 = chart.line_chart(
                    df=df3,
                    title=f"{period3} {item[3]}",
                    tickformat=False,
                    highlight_dict={
                        "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                        "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                    },
                    width=600,
                    height=500,
                )
                figs.append([chart1, chart2, chart3])
            iea_balance_ = iea_balance.loc[iea_balance.index >= dt.datetime(today().year, 1, 1)]
            ea_balance_ = ea_balance.loc[ea_balance.index >= dt.datetime(today().year, 1, 1)]
            for i in range(0, len(iea_balance_), 2):
                period1 = str(iea_balance_.index[i].to_period(item[2]))
                period2 = str(iea_balance_.index[i + 1].to_period(item[2]))
                df1 = pd.concat([iea_balance_.iloc[i, :].T, ea_balance_.iloc[i, :].T], axis=1)
                df2 = pd.concat(
                    [iea_balance_.iloc[i + 1, :].T, ea_balance_.iloc[i + 1, :].T], axis=1
                )
                df1.columns = ["IEA", "Aspects"]
                df2.columns = ["IEA", "Aspects"]
                figs.append(
                    chart.line_chart(
                        df=df1,
                        data_ply1c2=df2,
                        col=2,
                        column_titles=[f"{period1} {item[3]}", f"{period2} {item[3]}"],
                        tickformat=False,
                        highlight_dict={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        highlight_dict_c2={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        width=1200,
                        height=500,
                    )
                )
        else:
            if item[0] is not None:
                if display_section not in item[3]:
                    display_section = item[0].split(" ")[-1]
                    figs.append(f"<b>{display_section}</b><br>")
                if iea_balance.shape[0] == 2:
                    period1 = str(iea_balance.index[0].to_period(item[2]))
                    period2 = str(iea_balance.index[1].to_period(item[2]))
                    df1 = pd.concat([iea_balance.iloc[0, :].T, ea_balance.iloc[0, :].T], axis=1)
                    df2 = pd.concat([iea_balance.iloc[1, :].T, ea_balance.iloc[1, :].T], axis=1)
                    df1.columns = ["IEA", "Aspects"]
                    df2.columns = ["IEA", "Aspects"]
                    figs.append(
                        chart.line_chart(
                            df=df1,
                            data_ply1c2=df2,
                            col=2,
                            column_titles=[f"{period1} {item[3]}", f"{period2} {item[3]}"],
                            tickformat=False,
                            highlight_dict={
                                "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                                "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                            },
                            highlight_dict_c2={
                                "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                                "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                            },
                            width=1200,
                            height=500,
                        )
                    )
                elif iea_balance.shape[0] == 3:
                    period1 = str(iea_balance.index[0].to_period(item[2]))
                    period2 = str(iea_balance.index[1].to_period(item[2]))
                    period3 = str(iea_balance.index[2].to_period(item[2]))
                    df1 = pd.concat([iea_balance.iloc[0, :].T, ea_balance.iloc[0, :].T], axis=1)
                    df2 = pd.concat([iea_balance.iloc[1, :].T, ea_balance.iloc[1, :].T], axis=1)
                    df3 = pd.concat([iea_balance.iloc[2, :].T, ea_balance.iloc[2, :].T], axis=1)
                    df1.columns = ["IEA", "Aspects"]
                    df2.columns = ["IEA", "Aspects"]
                    df3.columns = ["IEA", "Aspects"]
                    chart1 = chart.line_chart(
                        df=df1,
                        title=f"{period1} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        showlegend=False,
                        width=600,
                        height=500,
                    )
                    chart2 = chart.line_chart(
                        df=df2,
                        title=f"{period2} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        showlegend=False,
                        width=600,
                        height=500,
                    )
                    chart3 = chart.line_chart(
                        df=df3,
                        title=f"{period3} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "IEA": {"color": "red", "width": 2, "mode": "markers+lines"},
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        width=600,
                        height=500,
                    )
                    figs.append([chart1, chart2, chart3])
            else:
                if display_section not in item[3]:
                    _unrecovered("IMG_4223/4224 original3297-3298: section heading update missing")
                if iea_balance.shape[0] == 2:
                    period1 = str(iea_balance.index[0].to_period(item[2]))
                    period2 = str(iea_balance.index[1].to_period(item[2]))
                    df1 = (ea_balance.iloc[0, :].T).to_frame("Aspects")
                    df2 = (ea_balance.iloc[1, :].T).to_frame("Aspects")
                    figs.append(
                        chart.line_chart(
                            df=df1,
                            data_ply1c2=df2,
                            col=2,
                            column_titles=[f"{period1} {item[3]}", f"{period2} {item[3]}"],
                            tickformat=False,
                            highlight_dict={
                                "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                            },
                            highlight_dict_c2={
                                "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                            },
                            width=1200,
                            height=500,
                        )
                    )
                elif iea_balance.shape[0] == 3:
                    period1 = str(iea_balance.index[0].to_period(item[2]))
                    period2 = str(iea_balance.index[1].to_period(item[2]))
                    period3 = str(iea_balance.index[2].to_period(item[2]))
                    df1 = (ea_balance.iloc[0, :].T).to_frame("Aspects")
                    df2 = (ea_balance.iloc[1, :].T).to_frame("Aspects")
                    df3 = (ea_balance.iloc[2, :].T).to_frame("Aspects")
                    chart1 = chart.line_chart(
                        df=df1,
                        title=f"{period1} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        showlegend=False,
                        width=600,
                        height=500,
                    )
                    chart2 = chart.line_chart(
                        df=df2,
                        title=f"{period2} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        showlegend=False,
                        width=600,
                        height=500,
                    )
                    chart3 = chart.line_chart(
                        df=df3,
                        title=f"{period3} {item[3]}",
                        tickformat=False,
                        highlight_dict={
                            "Aspects": {"color": "blue", "width": 2, "mode": "markers+lines"},
                        },
                        width=600,
                        height=500,
                    )
                    figs.append([chart1, chart2, chart3])
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html(
        [table.html_text(f"IEA vs EA", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\balances_evolution.html",
    )
    send_email(
        send_to=send_to,
        subject="IEA vs EA",
        body=[f"Last Update {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"] + figs,
        html_path=f"{html_path}\\oil\\balances_evolution.html",
    )


def sell_side_consensus():
    table_dict = {
        "SND": {
            "GS": "Imbalance", "JP": "", "MS": "Implied stock change",
            "EA": "EA Balance", "IEA": "IEA Balance",
            "ECM": "element.liquid.global.balance.kbd.monthly.forecast",
        },
        "Supply": {
            "GS": "World supply", "JP": "Global", "MS": "Total supply",
            "EA": "Total Supply", "IEA": "Total Supply",
            "ECM": "element.liquids.global.supply.kbd.monthly.forecast",
        },
        "OPEC Supply": {
            "GS": "Total OPEC Crude", "JP": "OPEC-12", "MS": "OPEC crude",
            "EA": "Monthly EA forecast for total OPEC crude production in kb/d", "IEA": "",
            "ECM": "element.crude.opec.supply.kbd.monthly.forecast",
        },
        "Non-OPEC Supply": {
            "GS": "Total non-OPEC supply", "MS": "Non-OPEC supply",
            "EA": "Monthly EA forecast for liquids production, including biofuels and processing gains, " + _unrecovered("IEA analysis 3401: clipped EA column suffix"),
            "IEA": "Non-OPEC", "ECM": "element.liquids_including_bio_misc.opec.supply.kbd.monthly.forecast",
        },
        "Demand": {
            "GS": "World Demand", "JP": "World oil demand", "MS": "Total demand",
            "EA": "Monthly EA forecast for liquids demand in World in kb/d", "IEA": "Total Demand",
            "ECM": "element.liquids.global.demand.kbd.monthly.forecast",
        },
        "China Demand": {
            "GS": ["Global Demand", "China"], "JP": "China", "MS": ["Non-OECD", "China"],
            "EA": "Monthly EA forecast for liquids demand in China in kb/d", "IEA": "China Demand",
            "ECM": "element.liquids.china.demand.kbd.monthly.forecast",
        },
        "Saudi Production": {
            "GS": ["OPEC Supply", "Saudi Arabia"], "JP": "Saudi Arabia", "MS": ["OPEC crude", "Saudi Arabia"],
            "EA": "Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d", "IEA": "",
            "ECM": "element.crude.opec.saudi_arabia.supply.kbd.monthly.forecast",
        },
        "US Crude": {
            "GS": ["Non-OPEC Supply", "US crude"], "JP": "US crude and condensate production (kbd)",
            "MS": ["Non-OPEC crude and cond.", "USA"],
            "EA": "Monthly EA forecast for crude production (including field condensate) in United States in kb/d",
            "IEA": "US Crude Supply", "EIA": "steo.COPRPUS",
            "ECM": "element.crude_condensate.united_states.supply.kbd.monthly.forecast",
        },
        "Russia Crude": {
            "GS": ["Non-OPEC Supply", "Russia"], "JP": "Russia", "MS": ["Non-OPEC crude and cond.", "Russia"],
            "EA": "Monthly EA forecast for crude production (including field condensate) in Russia in kb/d",
            "IEA": "Russia Crude Supply", "ECM": "element.crude_condensate.russia.supply.kbd.monthly.forecast",
        },
        "Iran": {
            "GS": ["OPEC Supply", "Iran"], "JP": "Iran", "MS": ["OPEC crude", "Iran"],
            "EA": "Monthly EA forecast for Iran OPEC crude production in kb/d",
            "ECM": "element.crude.opec.iran.supply.kbd.monthly.forecast",
        },
    }
    ea = ea_quarterly_balance()
    ea_date = pd.to_datetime(ea_release_dates(dataset_id=5214)[-1])
    ea_opec = ea_opec_crude_quarterly()
    ea_sup = ea[
        "Monthly EA forecast for liquids production, including biofuels and processing gains, in total Non-" + _unrecovered("IEA analysis 3464: clipped EA column suffix")
    ] + ea_opec[[
        "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
        "Monthly EA forecast for total OPEC crude production in kb/d",
    ]].sum(axis=1)
    try:
        ea_bal = ea["Monthly EA forecast for liquids implied stock change in World in mb/d"] * 1000
    except:
        ea_bal = (
            ea["Monthly EA forecast for liquids production, including biofuels and processing gains, " + _unrecovered("IEA analysis 3477: clipped EA column suffix")]
            + ea_opec[[
                "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
                "Monthly EA forecast for total OPEC crude production in kb/d",
            ]].sum(axis=1)
            - ea["Monthly EA forecast for liquids demand in World in kb/d"]
        )
    ea_data = pd.concat([ea, ea_opec, ea_bal.to_frame("EA Balance"), ea_sup.to_frame("Total Supply")], axis=1)
    iea_data = iea_quarterly_balance()
    iea_data["Total Supply"] = (
        iea_data["OECD Supply"] + iea_data["Non-OECD Supply"] + iea_data["OPEC NGLS"]
        + iea_data["Processing Gains"] + iea_data["Global Biofuels"]
        + ea_opec["Monthly EA forecast for total OPEC crude production in kb/d"]
    )
    iea_data["Non-OPEC"] = (
        iea_data["OECD Supply"] + iea_data["Non-OECD Supply"]
        + iea_data["Processing Gains"] + iea_data["Global Biofuels"]
    )
    iea_data["Russia"] = iea_data["Russia Crude Supply"] + iea_data["Russia NGL Supply"]
    iea_date = dt.datetime(int(iea_folder_list()[-1][-6:-2]), int(iea_folder_list()[-1][-2:]), 10)
    gs, gs_date = gs_balance()
    jp_dem, jp_sup, jp_opec, jp_crude, jp_us, jp_date = jpm_balance()
    ms, ms_date = ms_balance()
    citi, citi_date = citi_balance()
    schedule_dts = [pd.to_datetime(x) for x in release_schedule]
    eia_date = schedule_dts[np.where(np.array(schedule_dts) <= today() - relativedelta(days=1))[0][-1]]

    def quarterly_data(df, k, release_date=None, factor=1, adjust=0, yoy=True):
        df = df[[x for x in df.columns if "Q" in str(x) and len(x) < 8]]
        df.columns = [pd.to_datetime(x) for x in df.columns]
        df = df + adjust
        df = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 2]]
        df_ = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 1]]
        byyr = df.T
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_.columns = [str(x.to_period("Q")) for x in df_.columns]
        df_ = pd.concat([df_, byyrd], axis=1)
        df_.index = [k]
        df_ = df_ * factor
        if release_date is not None:
            df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    def quarterly_data_T(df, k, release_date, factor=1, adjust=0, yoy=True):
        df = df + adjust
        df = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 2)]
        df_ = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 1)]
        byyr = df.copy().to_frame(k)
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_.index = [str(x.to_period("Q")) for x in df_.index]
        df_ = df_.to_frame(k)
        df_ = df_.T
        df_ = pd.concat([df_, byyrd], axis=1)
        df_ = df_ * factor
        df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    figs = []
    figs.append("<div style='font-family:Calibri;'>")
    figs.append("<b>Unit: kbd<b>")
    for k, v in table_dict.items():
        if k == "SND":
            yoy = False
        else:
            yoy = True
        if k == "OPEC Supply":
            print(k)
        df = pd.DataFrame()
        for k1, v1 in v.items():
            print(k, k1, yoy)
            if k1 == "GS":
                if isinstance(v1, list):
                    gs_data = gs.loc[(gs["Unnamed: 1"] == v1[0]) & (gs["Unnamed: 2"] == v1[1]), :]
                else:
                    gs_data = gs.loc[gs["Unnamed: 2"] == v1, :]
                df = pd.concat([df, quarterly_data(gs_data, k1, gs_date, yoy=yoy)], axis=0)
            elif k1 == "JP":
                if k.lower() in ["demand", "china demand"]:
                    jp_data = jp_dem.loc[jp_dem["Unnamed: 0"] == v1, :]
                elif k.lower() in ["us crude"]:
                    jp_data = jp_us.loc[jp_us["Unnamed: 0"] == v1, :]
                elif k.lower() in ["supply", "non-opec supply"]:
                    jp_data = jp_sup.loc[jp_sup.iloc[:, 0] == v1, :]
                elif k.lower() in ["iran", "saudi production", "opec supply", "russia crude"]:
                    jp_data = jp_opec.loc[jp_opec["Unnamed: 1"] == v1, :]
                    if len(jp_data) > 1:
                        jp_data = jp_data.iloc[[0], :]
                elif k.lower() in ["snd"]:
                    jp_d = jp_dem.loc[jp_dem["Unnamed: 0"] == "World oil demand", :]
                    jp_d = quarterly_data(jp_d, "JP", yoy=yoy)
                    jp_s = jp_sup.loc[jp_sup.iloc[:, 0] == "Total", :]
                    if len(jp_s) == 0:
                        jp_s = jp_sup.loc[jp_sup.iloc[:, 0] == "Global", :]
                    jp_s = quarterly_data(jp_s, "JP", yoy=yoy)
                    jp_data = jp_s - jp_d
                    jp_data = jp_data * 1000
                    jp_data.insert(loc=0, column="Date", value=[jp_date.strftime("%Y-%m-%d")])
                    df = pd.concat([df, jp_data], axis=0)
                if k.lower() not in ["snd", "iran", "saudi production", "us crude", "opec supply", "russia crude"]:
                    df = pd.concat([df, quarterly_data(jp_data, k1, jp_date, factor=1000, yoy=yoy)], axis=0)
                elif k.lower() in ["iran", "saudi production", "us crude", "russia crude"]:
                    df = pd.concat([df, quarterly_data(jp_data, k1, jp_date, yoy=yoy)], axis=0)
                elif k.lower() in ["opec supply"]:
                    df = pd.concat([df, quarterly_data(jp_data, k1, jp_date, adjust=-1100, yoy=yoy)], axis=0)
            elif k1 == "Citi":
                citi_data = citi.loc[citi["Demand"] == v1, :]
                df = pd.concat([df, quarterly_data(citi_data, k1, citi_date, factor=1000, yoy=yoy)], axis=0)
            elif k1 == "MS":
                if isinstance(v1, list):
                    ms_data = ms.loc[(ms["Unnamed: 0"] == v1[0]) & (ms["Unnamed: 1"] == v1[1]), :]
                else:
                    ms_data = ms.loc[ms["Unnamed: 0"] == v1, :]
                    if ms_data.shape[0] > 1:
                        ms_data = ms_data.iloc[[0], :]
                df = pd.concat([df, quarterly_data(ms_data, k1, ms_date, factor=1000, yoy=yoy)], axis=0)
            elif k1 == "EA":
                df = pd.concat([df, quarterly_data_T(ea_data[v1], k1, ea_date, yoy=yoy)])
            elif k1 == "IEA":
                if v1 != "":
                    df = pd.concat([df, quarterly_data_T(iea_data[v1], k1, iea_date, yoy=yoy)])
            elif k1 == "EIA":
                if k == "SND":
                    eia_q = dv.eia(v1, freq="quarterly", facets="seriesId").value
                    eia_q = eia_q.astype(np.float64) * -1
                else:
                    try:
                        eia_q = dv.eia(v1, freq="quarterly", facets="seriesId").value
                        eia_q = eia_q.astype(np.float64)
                    except:
                        print(v1)
                df = pd.concat([df, quarterly_data_T(eia_q, k1, eia_date, factor=1000, yoy=yoy)])
            elif k1 == "ECM":
                dict_ele = timeseries().history(v1)
                ele_date = max(list(dict_ele.keys()))
                df = pd.concat([df, quarterly_data_T(dict_ele[ele_date].resample("Q").mean(), k1, ele_date, factor=1, yoy=yoy)], axis=0)
        df.loc["Average ex JP", :] = np.nan
        df.loc["Average ex JP", df.columns[1:]] = df.iloc[[0, 2, 3, 4, 5], 1:].mean(axis=0)
        df.index.name = "Source"
        df_benchmark = pd.read_csv(convert_path_to_linux(f"{csv_path}\\oil\\consensus_{k}_benchmark_2026.csv"))
        df.loc["2026-Anchor", :] = df_benchmark.iloc[[0, 2, 3, 4, 5], 2:].mean(axis=0, numeric_only=True)
        df.reset_index(inplace=True)
        df.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\consensus_{k}.csv"))
        figs.append(table.html_format(
            df=df, precision=0, header=k,
            format_column={tuple(df.columns): {"width": "100px", "text-align": "center"}},
            format_row={len(df) - 3: {"bottom_border": True}, len(df) - 2: {"bold": True}},
        ))
        if not yoy:
            drop_cols = [x for x in df.columns if "Mean " in x]
        else:
            drop_cols = [x for x in df.columns if "yoy " in x]
        df_chart = df.drop(["Date"] + drop_cols, axis=1)
        df_chart.set_index("Source", inplace=True)
        figure = chart.line_chart(
            df=df_chart.T, title=k, tickformat=False,
            highlight_dict={
                "Average ex JP": {"color": "black", "width": 2, "mode": "markers+lines"},
                "2026-Anchor": {"color": "red", "width": 2, "dash": "dash"},
                "ECM": {"color": "grey", "width": 2, "mode": "markers+lines"},
            }, height=500, width=750,
        )
        current = pd.Timestamp.today()
        current_q = f"{current.year}Q{current.quarter}"
        figure.add_shape(
            type="line",
            yref="y", xref="x", x0=current_q, y0=min(df_chart.min(axis=1)), x1=current_q,
            y1=max(df_chart.max(axis=1)), line=dict(color="black", width=2, dash="dash"),
        )
        next_q = current.to_period("Q") + 1
        next_label = f"{next_q.year}Q{next_q.quarter}"
        figure.add_annotation(x=next_label, y=max(df_chart.max(axis=1)), yref="y", showarrow=False, text=current_q)
        figs.append(figure)
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(f"Sell Side Consensus", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\sell_side_consensus.html",
    )


def sell_side_consensus_monthly():
    table_dict = {
        "SND": {
            "GS": "Imbalance", "JP": "", "MS": "Implied stock change",
            "EA": "EA Balance", "IEA": "IEA Balance",
            "ECM": "element.liquid.global.balance.kbd.monthly.forecast",
        },
        "Supply": {
            "GS": "World supply", "JP": "Global", "MS": "Total supply",
            "EA": "Total Supply", "IEA": "Total Supply",
            "ECM": "element.liquids.global.supply.kbd.monthly.forecast",
        },
        "OPEC Supply": {
            "GS": "Total OPEC Crude", "JP": "OPEC-12", "MS": "OPEC crude",
            "EA": "Monthly EA forecast for total OPEC crude production in kb/d", "IEA": "",
            "ECM": "element.crude.opec.supply.kbd.monthly.forecast",
        },
        "Non-OPEC Supply": {
            "GS": "Total non-OPEC supply", "MS": "Non-OPEC supply",
            "EA": "Monthly EA forecast for liquids production, including biofuels and processing gains, " + _unrecovered("IEA analysis 3766: clipped EA column suffix"),
            "IEA": "Non-OPEC", "ECM": "element.liquids_including_bio_misc.opec.supply.kbd.monthly.forecast",
        },
        "Demand": {
            "GS": "World Demand", "JP": "World oil demand", "MS": "Total demand",
            "EA": "Monthly EA forecast for liquids demand in World in kb/d", "IEA": "Total Demand",
            "ECM": "element.liquids.global.demand.kbd.monthly.forecast",
        },
        "China Demand": {
            "GS": ["Global Demand", "China"], "JP": "China", "MS": ["Non-OECD", "China"],
            "EA": "Monthly EA forecast for liquids demand in China in kb/d", "IEA": "China Demand",
            "ECM": "element.liquids.china.demand.kbd.monthly.forecast",
        },
        "Saudi Production": {
            "GS": ["OPEC Supply", "Saudi Arabia"], "JP": "Saudi Arabia", "MS": ["OPEC crude", "Saudi Arabia"],
            "EA": "Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d", "IEA": "",
            "ECM": "element.crude.opec.saudi_arabia.supply.kbd.monthly.forecast",
        },
        "US Crude": {
            "GS": ["Non-OPEC Supply", "US crude"], "JP": "US crude and condensate production (kbd)",
            "MS": ["Non-OPEC crude and cond.", "USA"],
            "EA": "Monthly EA forecast for crude production (including field condensate) in United States in kb/d",
            "IEA": "US Crude Supply", "EIA": "steo.COPRPUS",
            "ECM": "element.crude_condensate.united_states.supply.kbd.monthly.forecast",
        },
        "Russia Crude": {
            "GS": ["Non-OPEC Supply", "Russia"], "JP": "Russia", "MS": ["Non-OPEC crude and cond.", "Russia"],
            "EA": "Monthly EA forecast for crude production (including field condensate) in Russia in kb/d",
            "IEA": "Russia Crude Supply", "ECM": "element.crude_condensate.russia.supply.kbd.monthly.forecast",
        },
        "Iran": {
            "GS": ["OPEC Supply", "Iran"], "JP": "Iran", "MS": ["OPEC crude", "Iran"],
            "EA": "Monthly EA forecast for Iran OPEC crude production in kb/d",
            "ECM": "element.crude.opec.iran.supply.kbd.monthly.forecast",
        },
    }
    ea = ea_monthly_balance()
    ea_date = pd.to_datetime(ea_release_dates(dataset_id=5214)[-1])
    ea_opec = ea_opec_crude_monthly()
    ea_sup = ea[
        "Monthly EA forecast for liquids production, including biofuels and processing gains, in total Non-" + _unrecovered("IEA analysis 3829: clipped EA column suffix")
    ] + ea_opec[[
        "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
        "Monthly EA forecast for total OPEC crude production in kb/d",
    ]].sum(axis=1)
    try:
        ea_bal = ea["Monthly EA forecast for liquids implied stock change in World in mb/d"] * 1000
    except:
        ea_bal = (
            ea["Monthly EA forecast for liquids production, including biofuels and processing gains, " + _unrecovered("IEA analysis 3843: clipped EA column suffix")]
            + ea_opec[[
                "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
                "Monthly EA forecast for total OPEC crude production in kb/d",
            ]].sum(axis=1)
            - ea["Monthly EA forecast for liquids demand in World in kb/d"]
        )
    ea_data = pd.concat([ea, ea_opec, ea_bal.to_frame("EA Balance"), ea_sup.to_frame("Total Supply")], axis=1)
    iea_data = iea_quarterly_balance()
    iea_data = iea_data.resample("MS").last().fillna(method="ffill")
    iea_data = iea_data.reindex(pd.date_range(iea_data.index[0], dt.datetime(iea_data.index[-1].year, 12, *_unrecovered("IEA analysis 3862: clipped end-date/reindex arguments"))))
    iea_data["Total Supply"] = (
        iea_data["OECD Supply"] + iea_data["Non-OECD Supply"] + iea_data["OPEC NGLS"]
        + iea_data["Processing Gains"] + iea_data["Global Biofuels"]
        + ea_opec["Monthly EA forecast for total OPEC crude production in kb/d"]
    )
    iea_data["Non-OPEC"] = (
        iea_data["OECD Supply"] + iea_data["Non-OECD Supply"]
        + iea_data["Processing Gains"] + iea_data["Global Biofuels"]
    )
    iea_data["Russia"] = iea_data["Russia Crude Supply"] + iea_data["Russia NGL Supply"]
    iea_date = dt.datetime(int(iea_folder_list()[-1][-6:-2]), int(iea_folder_list()[-1][-2:]), 10)
    gs, gs_date = gs_balance()
    jp_dem, jp_sup, jp_opec, jp_crude, jp_us, jp_date = jpm_balance(monthly=True)
    ms, ms_date = ms_balance()
    citi, citi_date = citi_balance()
    schedule_dts = [pd.to_datetime(x) for x in release_schedule]
    eia_date = schedule_dts[np.where(np.array(schedule_dts) <= today() - relativedelta(days=1))[0][-1]]

    def quarterly_data(df, k, release_date=None, factor=1, adjust=0, yoy=True):
        df = df[[x for x in df.columns if "Q" in str(x) and len(x) < 8]]
        df.columns = [pd.to_datetime(x) for x in df.columns]
        df = df + adjust
        df = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 2]]
        df_ = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 1]]
        byyr = df.T
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_.columns = [str(x.to_period("Q")) for x in df_.columns]
        df_ = pd.concat([df_, byyrd], axis=1)
        df_.index = [k]
        df_ = df_ * factor
        if release_date is not None:
            df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    def monthly_data(df, k, release_date=None, factor=1, adjust=0, yoy=True):
        df = df[[x for x in df.columns if isinstance(x, dt.datetime)]]
        df.columns = [pd.to_datetime(x) for x in df.columns]
        df = df + adjust
        df = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 2]]
        df_ = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 1]]
        byyr = df.T
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_ = pd.concat([df_, byyrd], axis=1)
        df_.index = [k]
        df_ = df_ * factor
        if release_date is not None:
            df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    def quarterly_data_T(df, k, release_date, factor=1, adjust=0, yoy=True):
        df = df + adjust
        df = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 2)]
        df_ = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 1)]
        byyr = df.copy().to_frame(k)
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_.index = [str(x.to_period("Q")) for x in df_.index]
        df_ = df_.to_frame(k)
        df_ = df_.T
        df_ = pd.concat([df_, byyrd], axis=1)
        df_ = df_ * factor
        df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    def monthly_data_T(df, k, release_date, factor=1, adjust=0, yoy=True):
        df = df + adjust
        df = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 2)]
        df_ = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 1)]
        byyr = df.copy().to_frame(k)
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_ = df_.to_frame(k)
        df_ = df_.T
        df_ = pd.concat([df_, byyrd], axis=1)
        df_ = df_ * factor
        df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    def quarter_to_date(quarter_str):
        """
        Converts a quarterly string (e.g., '2Q25') to a datetime.date object.
        The date is set to the first day of the specified quarter.
        """
        if quarter_str[1] == "Q":
            quarter = int(quarter_str[0])
            year = int("20" + quarter_str[2:])
        elif quarter_str[4] == "Q":
            quarter = int(quarter_str[-1])
            year = int(quarter_str[:4])
        if quarter == 1:
            month = 1
        elif quarter == 2:
            month = 4
        elif quarter == 3:
            month = 7
        elif quarter == 4:
            month = 10
        else:
            raise ValueError("Invalid quarter number")
        return dt.datetime(year, month, 1)

    figs = []
    figs.append("<div style='font-family:Calibri;'>")
    figs.append("<b>Unit: kbd<b>")
    for k, v in table_dict.items():
        if k == "SND":
            yoy = False
        else:
            yoy = True
        if k == "OPEC Supply":
            print(k)
        df = pd.DataFrame()
        for k1, v1 in v.items():
            print(k, k1, yoy)
            if k1 == "GS":
                if isinstance(v1, list):
                    gs_data = gs.loc[(gs["Unnamed: 1"] == v1[0]) & (gs["Unnamed: 2"] == v1[1]), :]
                else:
                    gs_data = gs.loc[gs["Unnamed: 2"] == v1, :]
                df = pd.concat([df, monthly_data(gs_data, k1, gs_date, yoy=yoy)], axis=0)
            elif k1 == "JP":
                if k.lower() in ["demand", "china demand"]:
                    jp_data = jp_dem.loc[jp_dem["Unnamed: 0"] == v1, :]
                elif k.lower() in ["us crude"]:
                    jp_data = jp_us.loc[jp_us["Unnamed: 0"] == v1, :]
                elif k.lower() in ["supply", "non-opec supply"]:
                    jp_data = jp_sup.loc[jp_sup.iloc[:, 0] == v1, :]
                elif k.lower() in ["iran", "saudi production", "opec supply", "russia crude"]:
                    jp_data = jp_opec.loc[jp_opec["Unnamed: 1"] == v1, :]
                    if len(jp_data) > 1:
                        jp_data = jp_data.iloc[[0], :]
                elif k.lower() in ["snd"]:
                    jp_d = jp_dem.loc[jp_dem["Unnamed: 0"] == "World oil demand", :]
                    jp_d = monthly_data(jp_d, "JP", yoy=yoy)
                    jp_s = jp_sup.loc[jp_sup.iloc[:, 0] == "Total", :]
                    if len(jp_s) == 0:
                        jp_s = jp_sup.loc[jp_sup.iloc[:, 0] == "Global", :]
                    jp_s = monthly_data(jp_s, "JP", yoy=yoy)
                    jp_data = jp_s - jp_d
                    jp_data = jp_data * 1000
                    jp_data.insert(loc=0, column="Date", value=[jp_date.strftime("%Y-%m-%d")])
                    df = pd.concat([df, jp_data], axis=0)
                if k.lower() not in ["snd", "iran", "saudi production", "us crude", "opec supply", "russia crude"]:
                    df = pd.concat([df, monthly_data(jp_data, k1, jp_date, factor=1000, yoy=yoy)], axis=0)
                elif k.lower() in ["iran", "saudi production", "us crude", "russia crude"]:
                    df = pd.concat([df, monthly_data(jp_data, k1, jp_date, yoy=yoy)], axis=0)
                elif k.lower() in ["opec supply"]:
                    df = pd.concat([df, monthly_data(jp_data, k1, jp_date, adjust=-1100, yoy=yoy)], axis=0)
            elif k1 == "Citi":
                citi_data = citi.loc[citi["Demand"] == v1, :]
                df = pd.concat([df, quarterly_data(citi_data, k1, citi_date, factor=1000, yoy=yoy)], axis=0)
            elif k1 == "MS":
                if isinstance(v1, list):
                    ms_data = ms.loc[(ms["Unnamed: 0"] == v1[0]) & (ms["Unnamed: 1"] == v1[1]), :]
                else:
                    ms_data = ms.loc[ms["Unnamed: 0"] == v1, :]
                    if ms_data.shape[0] > 1:
                        ms_data = ms_data.iloc[[0], :]
                ms_data = ms_data[[x for x in ms_data.columns if "Q" in str(x) and len(x) < 8]]
                ms_data.columns = [quarter_to_date(x) for x in ms_data.columns]
                ms_data = ms_data.T.resample("MS").last().reindex(pd.date_range(ms_data.columns[0], *_unrecovered("IEA analysis 4074: clipped monthly reindex expression")))
                df = pd.concat([df, monthly_data(ms_data, k1, ms_date, factor=1000, yoy=yoy)], axis=0)
            elif k1 == "EA":
                df = pd.concat([df, monthly_data_T(ea_data[v1], k1, ea_date, yoy=yoy)])
            elif k1 == "IEA":
                if v1 != "":
                    df = pd.concat([df, monthly_data_T(iea_data[v1], k1, iea_date, yoy=yoy)])
            elif k1 == "EIA":
                if k == "SND":
                    eia_q = dv.eia(v1, freq="quarterly", facets="seriesId").value
                    eia_q = eia_q.astype(np.float64) * -1
                else:
                    try:
                        eia_q = dv.eia(v1, freq="quarterly", facets="seriesId").value
                        eia_q = eia_q.astype(np.float64)
                    except:
                        print(v1)
                df = pd.concat([df, monthly_data_T(eia_q, k1, eia_date, factor=1000, yoy=yoy)])
            elif k1 == "ECM":
                dict_ele = timeseries().history(v1)
                ele_date = max(list(dict_ele.keys()))
                df = pd.concat([df, monthly_data_T(dict_ele[ele_date].resample("MS").mean(), k1, ele_date, factor=1, yoy=yoy)], axis=0)
        df.loc["Average ex JP", :] = np.nan
        df.loc["Average ex JP", df.columns[1:]] = df.iloc[[0, 2, 3, 4, 5], 1:].mean(axis=0)
        df.index.name = "Source"
        df_benchmark = pd.read_csv(convert_path_to_linux(f"{csv_path}\\oil\\consensus_{k}_benchmark_2026.csv"))
        df_bm_data = df_benchmark.iloc[:, 3:]
        df_bm_data = df_bm_data[[x for x in df_bm_data.columns if "Q" in str(x) and len(x) < 8]]
        df_bm_data.columns = [quarter_to_date(x) for x in df_bm_data.columns]
        df_bm_data = df_bm_data.T.resample("MS").fillna(method="ffill").T
        df_bm_data = pd.concat([df_benchmark.iloc[:, :3], df_bm_data], axis=1)
        df.loc["2026-Anchor", :] = df_bm_data.iloc[[0, 2, 3, 4, 5], 2:].mean(axis=0, numeric_only=True)
        df.reset_index(inplace=True)
        df.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\consensus_{k}_monthly.csv"))
        df_m = df[[x for x in df.columns if isinstance(x, dt.datetime)]]
        end_col = df_m.shape[1] + 2
        cur_loc = pd.DatetimeIndex(df_m.columns).get_loc(today() + relativedelta(day=1))
        df_m.columns = [x.strftime("%b-%Y") for x in df_m.columns]
        df_recent = pd.concat([df.iloc[:, :2], df_m.iloc[:, cur_loc-6:cur_loc+7], df.iloc[:, end_col:]], axis=1)
        figs.append(table.html_format(
            df=df_recent, precision=0,
            **_unrecovered("IEA analysis 4138-4139: missing HTML header/column arguments"),
            format_row={len(df_recent)-3: {"bottom_border": True}, len(df_recent)-2: {"bold": True}},
        ))
        df = df_recent.copy()
        if not yoy:
            drop_cols = [x for x in df.columns if "Mean " in x]
        else:
            drop_cols = [x for x in df.columns if "yoy " in x]
        df_chart = df.drop(["Date"] + drop_cols, axis=1)
        df_chart.set_index("Source", inplace=True)
        figure = chart.line_chart(
            df=df_chart.T, title=k, tickformat=False,
            highlight_dict={
                "Average ex JP": {"color": "black", "width": 2, "mode": "markers+lines"},
                "2026-Anchor": {"color": "red", "width": 2, "dash": "dash"},
                "ECM": {"color": "grey", "width": 2, "mode": "markers+lines"},
            }, height=500, width=750,
        )
        current = pd.Timestamp.today()
        current_q = (today() + relativedelta(day=1)).strftime("%b-%Y")
        figure.add_shape(
            type="line",
            yref="y", xref="x", x0=current_q, y0=min(df_chart.min(axis=1)), x1=current_q,
            y1=max(df_chart.max(axis=1)), line=dict(color="black", width=2, dash="dash"),
        )
        next_q = current + relativedelta(months=1) + relativedelta(day=1)
        next_label = next_q.strftime("%b-%Y")
        figure.add_annotation(x=next_label, y=max(df_chart.max(axis=1)), yref="y", showarrow=False, text=current_q)
        figs.append(figure)
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(f"Sell Side Consensus - Monthly", style="font-family:Calibri;", tag="h1")] + figs,
        f"{html_path}\\oil\\sell_side_consensus_month.html",
    )


def sell_side_consensus_benchmark_2026():
    table_dict = {
        "SND": {
            "GS": "Imbalance", "JP": "", "MS": "Implied stock change",
            "EA": "EA Balance", "IEA": "IEA Balance",
            "ECM": "element.liquid.global.balance.kbd.monthly.forecast",
        },
        "Supply": {
            "GS": "World supply", "JP": "Global", "MS": "Total supply",
            "EA": "Total Supply", "IEA": "Total Supply",
            "ECM": "element.liquids.global.supply.kbd.monthly.forecast",
        },
        "OPEC Supply": {
            "GS": "Total OPEC Crude", "JP": "OPEC-12", "MS": "OPEC crude",
            "EA": "Monthly EA forecast for total OPEC crude production in kb/d", "IEA": "",
            "ECM": "element.crude.opec.supply.kbd.monthly.forecast",
        },
        "Non-OPEC Supply": {
            "GS": "Total non-OPEC supply", "MS": "Non-OPEC supply",
            "EA": "Monthly EA forecast for liquids production, including biofuels and processing gains, " + _unrecovered("IEA analysis 4222: clipped EA column suffix"),
            "IEA": "Non-OPEC", "ECM": "element.liquids_including_bio_misc.opec.supply.kbd.monthly.forecast",
        },
        "Demand": {
            "GS": "World Demand", "JP": "World oil demand", "MS": "Total demand",
            "EA": "Monthly EA forecast for liquids demand in World in kb/d", "IEA": "Total Demand",
            "ECM": "element.liquids.global.demand.kbd.monthly.forecast",
        },
        "China Demand": {
            "GS": ["Global Demand", "China"], "JP": "China", "MS": ["Non-OECD", "China"],
            "EA": "Monthly EA forecast for liquids demand in China in kb/d", "IEA": "China Demand",
            "ECM": "element.liquids.china.demand.kbd.monthly.forecast",
        },
        "Saudi Production": {
            "GS": ["OPEC Supply", "Saudi Arabia"], "JP": "Saudi Arabia", "MS": ["OPEC crude", "Saudi Arabia"],
            "EA": "Monthly EA forecast for Saudi Arabia OPEC crude production in kb/d", "IEA": "",
            "ECM": "element.crude.opec.saudi_arabia.supply.kbd.monthly.forecast",
        },
        "US Crude": {
            "GS": ["Non-OPEC Supply", "US crude"], "JP": "US crude and condensate production (kbd)",
            "MS": ["Non-OPEC crude and cond.", "USA"],
            "EA": "Monthly EA forecast for crude production (including field condensate) in United States in kb/d",
            "IEA": "US Crude Supply", "EIA": "steo.COPRPUS",
            "ECM": "element.crude_condensate.united_states.supply.kbd.monthly.forecast",
        },
        "Russia Crude": {
            "GS": ["Non-OPEC Supply", "Russia"], "JP": "Russia", "MS": ["Non-OPEC crude and cond.", "Russia"],
            "EA": "Monthly EA forecast for crude production (including field condensate) in Russia in kb/d",
            "IEA": "Russia Crude Supply", "ECM": "element.crude_condensate.russia.supply.kbd.monthly.forecast",
        },
        "Iran": {
            "GS": ["OPEC Supply", "Iran"], "JP": "Iran", "MS": ["OPEC crude", "Iran"],
            "EA": "Monthly EA forecast for Iran OPEC crude production in kb/d",
            "ECM": "element.crude.opec.iran.supply.kbd.monthly.forecast",
        },
    }
    ea = ea_quarterly_balance(issue="2025-12-20")
    ea_date = dt.datetime(2025, 12, 20)
    ea_opec = ea_opec_crude_quarterly(issue="2025-12-20")
    ea_sup = ea[
        "Monthly EA forecast for liquids production, including biofuels and processing gains, in total Non-" + _unrecovered("IEA analysis 4282: clipped EA column suffix")
    ] + ea_opec[[
        "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
        "Monthly EA forecast for total OPEC crude production in kb/d",
    ]].sum(axis=1)
    try:
        ea_bal = ea["Monthly EA forecast for liquids implied stock change in World in mb/d"] * 1000
    except:
        ea_bal = (
            ea["Monthly EA forecast for liquids production, including biofuels and processing gains, " + _unrecovered("IEA analysis 4296: clipped EA column suffix")]
            + ea_opec[[
                "Monthly EA forecast for OPEC NGL production (including field condensate) in kb/d",
                "Monthly EA forecast for total OPEC crude production in kb/d",
            ]].sum(axis=1)
            - ea["Monthly EA forecast for liquids demand in World in kb/d"]
        )
    ea_data = pd.concat([ea, ea_opec, ea_bal.to_frame("EA Balance"), ea_sup.to_frame("Total Supply")], axis=1)
    iea_bm_issue = iea_folder_list().index(convert_path_to_linux(
        "\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\CODE\\data\\IEA\\2025" + _unrecovered("IEA analysis 4313: clipped benchmark folder suffix")
    ))
    iea_data = iea_quarterly_balance(issue=iea_bm_issue, ea_issue="2025-12-20")
    iea_data["Total Supply"] = (
        iea_data["OECD Supply"] + iea_data["Non-OECD Supply"] + iea_data["OPEC NGLS"]
        + iea_data["Processing Gains"] + iea_data["Global Biofuels"]
        + ea_opec["Monthly EA forecast for total OPEC crude production in kb/d"]
    )
    iea_data["Non-OPEC"] = (
        iea_data["OECD Supply"] + iea_data["Non-OECD Supply"]
        + iea_data["Processing Gains"] + iea_data["Global Biofuels"]
    )
    iea_data["Russia"] = iea_data["Russia Crude Supply"] + iea_data["Russia NGL Supply"]
    iea_date = dt.datetime(int(iea_folder_list()[-1][-6:-2]), int(iea_folder_list()[-1][-2:]), 10)
    gs, gs_date = gs_balance_benchmark()
    jp_dem, jp_sup, jp_opec, jp_crude, jp_us, jp_date = jpm_balance_benchmark()
    ms, ms_date = ms_balance_benchmark()
    citi, citi_date = citi_balance_benchmark()
    schedule_dts = [pd.to_datetime(x) for x in release_schedule]
    eia_date = schedule_dts[np.where(np.array(schedule_dts) <= dt.datetime(2025, 12, 31))[0][-1]]

    def quarterly_data(df, k, release_date=None, factor=1, adjust=0, yoy=True):
        df = df[[x for x in df.columns if "Q" in str(x) and len(x) < 8]]
        df.columns = [pd.to_datetime(x) for x in df.columns]
        df = df + adjust
        df = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 2]]
        df_ = df[[x for x in df.columns if today().year - 1 <= x.year <= today().year + 1]]
        byyr = df.T
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_.columns = [str(x.to_period("Q")) for x in df_.columns]
        df_ = pd.concat([df_, byyrd], axis=1)
        df_.index = [k]
        df_ = df_ * factor
        if release_date is not None:
            df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    def quarterly_data_T(df, k, release_date, factor=1, adjust=0, yoy=True):
        df = df + adjust
        df = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 2)]
        df_ = df[(df.index.year >= today().year - 1) & (df.index.year <= today().year + 1)]
        byyr = df.copy().to_frame(k)
        byyr["year"] = byyr.index.year
        if not yoy:
            byyrd = byyr.groupby("year").mean()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["Mean " + str(x) for x in byyrd.columns]
        else:
            byyrd = (byyr.groupby("year").mean()).diff()
            byyrd = byyrd.dropna().T
            byyrd.columns = ["yoy " + str(x) for x in byyrd.columns]
        df_.index = [str(x.to_period("Q")) for x in df_.index]
        df_ = df_.to_frame(k)
        df_ = df_.T
        df_ = pd.concat([df_, byyrd], axis=1)
        df_ = df_ * factor
        df_.insert(loc=0, column="Date", value=[release_date.strftime("%Y-%m-%d")])
        return df_

    figs = []
    figs.append("<div style='font-family:Calibri;'>")
    figs.append("<b>Unit: kbd<b>")
    for k, v in table_dict.items():
        if k == "SND":
            yoy = False
        else:
            yoy = True
        if k == "OPEC Supply":
            print(k)
        df = pd.DataFrame()
        for k1, v1 in v.items():
            print(k, k1, yoy)
            if k1 == "GS":
                if isinstance(v1, list):
                    gs_data = gs.loc[(gs["Unnamed: 1"] == v1[0]) & (gs["Unnamed: 2"] == v1[1]), :]
                else:
                    gs_data = gs.loc[gs["Unnamed: 2"] == v1, :]
                df = pd.concat([df, quarterly_data(gs_data, k1, gs_date, yoy=yoy)], axis=0)
            elif k1 == "JP":
                if k.lower() in ["demand", "china demand"]:
                    jp_data = jp_dem.loc[jp_dem["Unnamed: 0"] == v1, :]
                elif k.lower() in ["us crude"]:
                    jp_data = jp_us.loc[jp_us["Unnamed: 0"] == v1, :]
                elif k.lower() in ["supply", "non-opec supply"]:
                    jp_data = jp_sup.loc[jp_sup.iloc[:, 0] == v1, :]
                elif k.lower() in ["iran", "saudi production", "opec supply", "russia crude"]:
                    jp_data = jp_opec.loc[jp_opec["Unnamed: 1"] == v1, :]
                    if len(jp_data) > 1:
                        jp_data = jp_data.iloc[[0], :]
                elif k.lower() in ["snd"]:
                    jp_d = jp_dem.loc[jp_dem["Unnamed: 0"] == "World oil demand", :]
                    jp_d = quarterly_data(jp_d, "JP", yoy=yoy)
                    jp_s = jp_sup.loc[jp_sup.iloc[:, 0] == "Total", :]
                    if len(jp_s) == 0:
                        jp_s = jp_sup.loc[jp_sup.iloc[:, 0] == "Global", :]
                    jp_s = quarterly_data(jp_s, "JP", yoy=yoy)
                    jp_data = jp_s - jp_d
                    jp_data = jp_data * 1000
                    jp_data.insert(loc=0, column="Date", value=[jp_date.strftime("%Y-%m-%d")])
                    df = pd.concat([df, jp_data], axis=0)
                if k.lower() not in ["snd", "iran", "saudi production", "us crude", "opec supply", "russia crude"]:
                    df = pd.concat([df, quarterly_data(jp_data, k1, jp_date, factor=1000, yoy=yoy)], axis=0)
                elif k.lower() in ["iran", "saudi production", "us crude", "russia crude"]:
                    df = pd.concat([df, quarterly_data(jp_data, k1, jp_date, yoy=yoy)], axis=0)
                elif k.lower() in ["opec supply"]:
                    df = pd.concat([df, quarterly_data(jp_data, k1, jp_date, adjust=-1100, yoy=yoy)], axis=0)
            elif k1 == "Citi":
                citi_data = citi.loc[citi["Demand"] == v1, :]
                df = pd.concat([df, quarterly_data(citi_data, k1, citi_date, factor=1000, yoy=yoy)], axis=0)
            elif k1 == "MS":
                if isinstance(v1, list):
                    ms_data = ms.loc[(ms["Unnamed: 0"] == v1[0]) & (ms["Unnamed: 1"] == v1[1]), :]
                else:
                    ms_data = ms.loc[ms["Unnamed: 0"] == v1, :]
                    if ms_data.shape[0] > 1:
                        ms_data = ms_data.iloc[[0], :]
                df = pd.concat([df, quarterly_data(ms_data, k1, ms_date, factor=1000, yoy=yoy)], axis=0)
            elif k1 == "EA":
                df = pd.concat([df, quarterly_data_T(ea_data[v1], k1, ea_date, yoy=yoy)])
            elif k1 == "IEA":
                if v1 != "":
                    df = pd.concat([df, quarterly_data_T(iea_data[v1], k1, iea_date, yoy=yoy)])
            elif k1 == "EIA":
                if k == "SND":
                    eia_q = dv.eia(v1, freq="quarterly", facets="seriesId").value
                    eia_q = eia_q.astype(np.float64) * -1
                else:
                    try:
                        eia_q = dv.eia(v1, freq="quarterly", facets="seriesId").value
                        eia_q = eia_q.astype(np.float64)
                    except:
                        print(v1)
                df = pd.concat([df, quarterly_data_T(eia_q, k1, eia_date, factor=1000, yoy=yoy)])
            elif k1 == "ECM":
                dict_ele = timeseries().history(v1)
                ele_date = max(list(dict_ele.keys()))
                df = pd.concat([df, quarterly_data_T(dict_ele[ele_date].resample("Q").mean(), k1, ele_date, factor=1, yoy=yoy)], axis=0)
        df.loc["Average ex JP", :] = np.nan
        df.loc["Average ex JP", df.columns[1:]] = df.iloc[[0, 2, 3, 4, 5], 1:].mean(axis=0)
        df.index.name = "Source"
        df_benchmark = pd.read_csv(convert_path_to_linux(f"{csv_path}\\oil\\consensus_{k}_benchmark_2026.csv"))
        df.loc["2026-Anchor", :] = df_benchmark.iloc[[0, 2, 3, 4, 5], 2:].mean(axis=0, numeric_only=True)
        df.reset_index(inplace=True)
        df.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\consensus_{k}_benchmark_2026.csv"))


def gs_balance_benchmark():
    """
    compare update with benchmark
    :return:
    """
    file_path = convert_path_to_linux(
        f"{data_path}\\sell_side_consensus\\GS\\GS Global Oil Supply and Demand Model_20251117.xlsx"
    )
    df = pd.read_excel(file_path, sheet_name="17-Nov-25", header=6)
    df.drop(df.columns[0], axis=1, inplace=True)
    df.loc[:, df.columns[0]].fillna(method="ffill", inplace=True)
    return df, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d")


def gs_balance():
    file_path = latest_file(folder_path=convert_path_to_linux(f"{data_path}\\sell_side_consensus\\GS"))
    excel_file = pd.ExcelFile(file_path)
    sheet_names = excel_file.sheet_names
    sheet_names = [x for x in sheet_names if "Cover" not in x and "Summary" not in x]
    df = pd.read_excel(file_path, sheet_name=sheet_names[0], header=6)
    df.drop(df.columns[0], axis=1, inplace=True)
    df.loc[:, df.columns[0]].fillna(method="ffill", inplace=True)
    return df, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d")


def jpm_balance_benchmark(monthly=False):
    file_path = convert_path_to_linux(f"{data_path}\\sell_side_consensus\\JPM\\JPM Oil S&D_20251124.xlsm")
    demand = pd.read_excel(file_path, sheet_name="Demand country", header=1)
    supply = pd.read_excel(file_path, sheet_name="Global Liquid Supply", header=1)
    opec = pd.read_excel(file_path, sheet_name="OPEC+ Supply", header=2)
    crude = pd.read_excel(file_path, sheet_name="Global crude Supply", header=1)
    us = pd.read_excel(file_path, sheet_name="US Supply", header=0)
    demand.loc[0, :] = demand.loc[0, :].fillna(method="ffill")
    supply.loc[0, :] = supply.loc[0, :].fillna(method="ffill")
    opec.loc[0, :] = opec.loc[0, :].fillna(method="ffill")
    opec.drop(opec.columns[0], axis=1, inplace=True)
    crude.loc[0, :] = crude.loc[0, :].fillna(method="ffill")
    us.loc[0, :] = us.loc[0, :].fillna(method="ffill")
    if isinstance(crude.iloc[0, 0], str):
        pass
    else:
        crude.drop(crude.columns[0], axis=1, inplace=True)
    if isinstance(supply.iloc[0, 0], str):
        pass
    else:
        supply.drop(supply.columns[0], axis=1, inplace=True)

    def columns_name(df):
        cols = []
        for i in df.columns:
            if pd.isnull(df.loc[0, i]) or pd.isnull(df.loc[1, i]):
                cols.append(i)
            else:
                if isinstance(df.loc[0, i], int):
                    cols.append(f"{df.loc[1, i]}{df.loc[0, i]}")
                elif isinstance(df.loc[0, i], float):
                    cols.append(f"{df.loc[1, i]}{int(df.loc[0, i])}")
                else:
                    cols.append(f"{df.loc[1, i]}{df.loc[0, i][:-1]}")
        return cols

    def monthly_cols(df):
        valid_col = []
        for idx, col in enumerate(df.columns):
            try:
                dt.datetime.strptime(col, "%b%Y")
                valid_col.append(col)
            except ValueError:
                pass
        valid_df = df[valid_col]
        valid_df.columns = [dt.datetime.strptime(x, "%b%Y") for x in valid_df.columns]
        valid_df = pd.concat([df.iloc[:, 0], valid_df], axis=1)
        return valid_df

    demand.columns = columns_name(demand)
    demand.loc[:, "Unnamed: 0"] = demand.loc[:, "Unnamed: 0"].str.strip()
    supply.columns = columns_name(supply)
    supply.loc[:, crude.columns[0]] = supply.loc[:, crude.columns[0]].str.strip()
    opec.columns = columns_name(opec)
    crude.columns = columns_name(crude)
    crude.loc[:, crude.columns[0]] = crude.loc[:, crude.columns[0]].str.strip()
    us.columns = columns_name(us)
    if monthly:
        demand = monthly_cols(demand)
        supply = monthly_cols(supply)
        opec = monthly_cols(opec)
        crude = monthly_cols(crude)
        us = monthly_cols(us)
    return (demand, supply, opec, crude, us, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d"))


def jpm_balance(monthly=False):
    file_path = latest_file(folder_path=convert_path_to_linux(f"{data_path}\\sell_side_consensus\\JPM"), suffix="xlsm")
    demand = pd.read_excel(file_path, sheet_name="Demand country", header=1)
    supply = pd.read_excel(file_path, sheet_name="Global Liquid Supply", header=1)
    opec = pd.read_excel(file_path, sheet_name="OPEC+ Supply", header=2)
    crude = pd.read_excel(file_path, sheet_name="Global crude Supply", header=1)
    us = pd.read_excel(file_path, sheet_name="US Supply", header=0)
    demand.loc[0, :] = demand.loc[0, :].fillna(method="ffill")
    supply.loc[0, :] = supply.loc[0, :].fillna(method="ffill")
    opec.loc[0, :] = opec.loc[0, :].fillna(method="ffill")
    opec.drop(opec.columns[0], axis=1, inplace=True)
    crude.loc[0, :] = crude.loc[0, :].fillna(method="ffill")
    us.loc[0, :] = us.loc[0, :].fillna(method="ffill")
    if isinstance(crude.iloc[0, 0], str):
        pass
    else:
        crude.drop(crude.columns[0], axis=1, inplace=True)
    if isinstance(supply.iloc[0, 0], str):
        pass
    else:
        supply.drop(supply.columns[0], axis=1, inplace=True)

    def columns_name(df):
        cols = []
        for i in df.columns:
            if pd.isnull(df.loc[0, i]) or pd.isnull(df.loc[1, i]):
                cols.append(i)
            else:
                if isinstance(df.loc[0, i], int):
                    cols.append(f"{df.loc[1, i]}{df.loc[0, i]}")
                elif isinstance(df.loc[0, i], float):
                    cols.append(f"{df.loc[1, i]}{int(df.loc[0, i])}")
                else:
                    cols.append(f"{df.loc[1, i]}{df.loc[0, i][:-1]}")
        return cols

    def monthly_cols(df):
        valid_col = []
        for idx, col in enumerate(df.columns):
            try:
                dt.datetime.strptime(col, "%b%Y")
                valid_col.append(col)
            except ValueError:
                pass
        valid_df = df[valid_col]
        valid_df.columns = [dt.datetime.strptime(x, "%b%Y") for x in valid_df.columns]
        valid_df = pd.concat([df.iloc[:, 0], valid_df], axis=1)
        return valid_df

    demand.columns = columns_name(demand)
    demand.loc[:, "Unnamed: 0"] = demand.loc[:, "Unnamed: 0"].str.strip()
    supply.columns = columns_name(supply)
    supply.loc[:, crude.columns[0]] = supply.loc[:, crude.columns[0]].str.strip()
    opec.columns = columns_name(opec)
    crude.columns = columns_name(crude)
    crude.loc[:, crude.columns[0]] = crude.loc[:, crude.columns[0]].str.strip()
    us.columns = columns_name(us)
    if monthly:
        demand = monthly_cols(demand)
        supply = monthly_cols(supply)
        opec = monthly_cols(opec)
        crude = monthly_cols(crude)
        us = monthly_cols(us)
    return (demand, supply, opec, crude, us, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d"))


def citi_balance_benchmark():
    file_path = convert_path_to_linux(f"{data_path}\\sell_side_consensus\\Citi\\Citi Global Oil SND_20230923.xlsx")
    df = pd.read_excel(file_path, sheet_name="Sheet1", header=5)
    df.drop(df.columns[[0, 1]], axis=1, inplace=True)
    return df, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d")


def citi_balance():
    file_path = convert_path_to_linux(f"{data_path}\\sell_side_consensus\\Citi\\Citi Global Oil SND_20230923.xlsx")
    df = pd.read_excel(file_path, sheet_name="Sheet1", header=5)
    df.drop(df.columns[[0, 1]], axis=1, inplace=True)
    return df, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d")


def ms_balance_benchmark():
    file_path = convert_path_to_linux(f"{data_path}\\sell_side_consensus\\MS\\MS Global balance_20260104.xlsx")
    df = pd.read_excel(file_path, sheet_name="For humans", header=4)
    df["Unnamed: 0"].fillna(method="ffill", inplace=True)
    new_row = len(df)
    df.loc[new_row, :] = np.nan
    df.loc[new_row, "Unnamed: 0"] = "Total supply"
    cols = df.columns[3:]
    try:
        df.loc[new_row, cols] = (
            df.loc[df["Unnamed: 0"] == "Non-OPEC supply", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC NGLs", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC crude", cols].iloc[0, :]
        )
    except:
        df.loc[new_row, cols] = (
            df.loc[df["Unnamed: 0"] == "Non-OPEC supply", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC Condensate and NGLs", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC crude", cols].iloc[0, :]
        )
    return df, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d")


def ms_balance():
    file_path = latest_file(folder_path=convert_path_to_linux(f"{data_path}\\sell_side_consensus\\MS"))
    df = pd.read_excel(file_path, sheet_name="For humans", header=4)
    df["Unnamed: 0"].fillna(method="ffill", inplace=True)
    new_row = len(df)
    df.loc[new_row, :] = np.nan
    df.loc[new_row, "Unnamed: 0"] = "Total supply"
    cols = df.columns[3:]
    try:
        df.loc[new_row, cols] = (
            df.loc[df["Unnamed: 0"] == "Non-OPEC supply", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC NGLs", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC crude", cols].iloc[0, :]
        )
    except:
        df.loc[new_row, cols] = (
            df.loc[df["Unnamed: 0"] == "Non-OPEC supply", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC Condensate and NGLs", cols].iloc[0, :]
            + df.loc[df["Unnamed: 0"] == "OPEC crude", cols].iloc[0, :]
        )
    return df, dt.datetime.strptime(file_path.split(".")[-2][-8:], "%Y%m%d")


def latest_file(folder_path, suffix="xlsx"):
    onlyfiles = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    str_dt = [s.split(".")[0][-8:] for s in onlyfiles]
    dts = [dt.datetime.strptime(date, "%Y%m%d") for date in str_dt]
    if sys.platform.startswith("win"):
        path = f"{folder_path}\\{onlyfiles[0].split('.')[0][:-8]}{max(dts).strftime('%Y%m%d')}.{suffix}"
    elif sys.platform.startswith("linux"):
        path = f"{folder_path}/{onlyfiles[0].split('.')[0][:-8]}{max(dts).strftime('%Y%m%d')}.{suffix}"
    else:
        raise NotImplementedError("Unsupported operating system")
    return path


def update():
    string_date = today().strftime("%m/%d/%Y")
    if True:
        update_iea_stocks()
        update_iea_balance()
        update_iea_demand_supply()
        update_observed_vs_forecast_balance()
        update_comparison()
        sell_side_consensus()
        sell_side_consensus_monthly()
        SAVE_IEA_DATA.update(run_date=dt.datetime.strptime(string_date, "%m/%d/%Y"))


if __name__ == "__main__":
    update()


