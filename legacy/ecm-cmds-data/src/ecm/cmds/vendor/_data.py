import base64
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor as tp_exec
from gzip import BadGzipFile
from io import BytesIO
from io import StringIO

import numpy as np
import pandas as pd
import requests
import urllib3
from dateutil.relativedelta import relativedelta
from ecm.atom.clients import retry
from ecm.cmds.core.cdr import today
from ecm.cmds.core.config import csv_path
from ecm.cmds.core.config import data_path
from ecm.cmds.core.sql import LO25DB
from ecm.cmds.core.sql import read_sql
from ecm.cmds.core.sql import to_sql
from ecm.cmds.core.utils import convert_path_to_linux
from loguru import logger as log

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"


if sys.platform == "win32":
    from win32com.client import Dispatch

from ecm.cmds.vendor._CEtools import CElink
from ecm.cmds.core.schema import CMEBlockTrades

urllib3.disable_warnings()

celink = CElink(os.environ["CE_USERNAME"], os.environ["CE_PASSWORD"])
eia_api_key = os.environ["EIA_API_KEY"]
ea_api_key = os.environ["EA_API_KEY"]

ice_user = os.environ["ICE_USERNAME"]
ice_password = os.environ["ICE_PASSWORD"]

iir_user = os.environ["IIR_USERNAME"]
iir_pwd = os.environ["IIR_PASSWORD"]


def gen_new_iir_token() -> str:
    req_url = (
        r"https://api.industrialinfo.com"
        rf"/idb/v2.3/token?username={iir_user}&password={iir_pwd}&tokenLifeTime=30"
    )
    resp = requests.post(req_url, verify=False)
    token = resp.headers["authorization"]
    return token


def ce_eugasopdata(assets, variable, dateFrom, unit, **kwargs):
    """
    download data from commodity essentials
    assets: str, e.g. '1836,185,188,192,54,83'
    variable: str, e.g. 'netFlow,withdrawal'
    start_date: str, e.g. 01_Jan_2010
    unit: str, e.g. 'mcm'
    """
    date_excel = kwargs.get("date_excel", False)
    data = celink.eugasopdata(assets=assets, variable=variable, dateFrom=dateFrom, unit=unit)
    data_meta = celink.eugasopdata(assets=assets, variable=variable, dateFrom=dateFrom, meta="True")
    data_meta = data_meta.loc[0, :]
    cols = ["DateExcel", "Date"] + [
        data_meta[x] for x in data.columns if x not in ["DateExcel", "Date"]
    ]
    data.columns = cols
    if date_excel is False:
        data.drop(["DateExcel"], axis=1, inplace=True)
    data["Date"] = pd.to_datetime(data["Date"])
    data.set_index("Date", inplace=True)
    data.index.names = ["Date"]
    return data


def ce_eugasout(assets, variable, dateFrom, dateAt=None, **kwargs):
    """
    download data from commodity essentials
    assets: str, e.g. '1836,185,188,192,54,83'
    variable: str, e.g. 'netFlow,withdrawal'
    start_date: str, e.g. 01_Jan_2010
    unit: str, e.g. 'mcm'
    """
    columns = kwargs.get("columns", None)
    if dateAt is None:
        dateAt = ""
    data = celink.eugasout(assets=assets, variable=variable, dateFrom=dateFrom, dateAt=dateAt)
    data["Date"] = pd.to_datetime(data["Date"])
    data.set_index("Date", inplace=True)
    data.index.names = ["Date"]
    if columns is not None:
        return data[columns]
    else:
        return data


def ce_price(id, nd, date_excel=False):
    """
    download price data from commodity essentials
    id: str, e.g. 'DeSparkBase_Jun.23,DeSparkBase_Jul.23,DeSparkBase_Aug.23'
    nd: int, e.g. 364
    """
    data = celink.pmcontract(id=id, nd=nd)
    data.set_index("Date", inplace=True)
    data.index = pd.to_datetime(data.index)
    if date_excel is False:
        data.drop("DateExcel", inplace=True, axis=1)
    return data


def kpler(link: str, base_url=None, credentials=None, retries=0):
    """
    download data from Kpler
    link: str, e.g. '/v1/flows?flowDirection=Export&granularity=daily&startDate=2015-01-01&
    endDate=2023-05-05&fromZones=Russian Federation&unit=kbd&withForecast=false&
    split=Origin%20Installations&products=crude%2Fco'
    """
    if base_url is None:
        base_url = "https://api.kpler.com"
    if credentials is None:
        credentials = {"email": os.environ["KPLER_USERNAME"], "password": os.environ["KPLER_PASSWORD"]}
        credential_string = f"{credentials['email']}:{credentials['password']}"
        encoded_string = base64.b64encode(str.encode(credential_string)).decode("ascii")
    else:
        credential_string = f"{credentials['email']}:{credentials['password']}"
        encoded_string = base64.b64encode(str.encode(credential_string)).decode("ascii")
    headers_login = {"Authorization": f"Basic {encoded_string}"}
    headers = headers_login
    raw = requests.get(base_url + link, headers=headers, stream=True, verify=False)
    if raw.status_code != 200:
        if retries != 2:
            kpler(link, base_url=base_url, credentials=credentials, retries=retries + 1)
        else:
            raise RuntimeError(f"Could not download {link} due to \n{raw.text}")
    data = StringIO(str(raw.content, "utf-8"))
    return pd.read_csv(data, sep=";")


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(60))
def download_and_get_frame_ice(url, session, delemiter="|"):
    raw_data = session.get(url, verify=False).text
    if "No files Available" in raw_data:
        log.info(f"Data Not available for {url}")
        return pd.DataFrame()
    df = pd.read_csv(StringIO(raw_data), delimiter=delemiter)
    log.info(f"Downloaded {url} with {len(df)} rows")
    if len(df) == 0 and df.columns[0] not in ["TRADE_DATE", "TRADE DATE"]:
        log.info(f"Downloaded {url} with 0 rows retrying in 60s")
        raise Exception("Rate limited")
    return df


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(60))
def download_ice_data(
    start_date: str,
    end_date: str | None = None,
    market: str = "gas",
    file: str = "icecleared_gas",
    file_extension: str = "dat",
    backfill: bool = False,
    session: requests.Session | None = None,
):
    if session is None:
        s = requests.Session()
        credentials = {"userId": ice_user, "password": ice_password, "appKey": "ICEDOWNLOADS"}
        headers_login = {"Content-Type": "application/json"}

        response = s.post(
            "https://sso.ice.com/api/authenticateTfa",
            data=json.dumps(credentials),
            headers=headers_login,
            verify=False,
        )
        if "error" in response.text.lower():
            raise Exception(f"Failed to authenticate ! {response.text}")
    else:
        s = session

    if backfill:
        dfs = []
        dates = pd.bdate_range(start_date, end_date or dt.date.today() - dt.timedelta(days=1))
        urls = [
            (
                "https://downloads.ice.com/Settlement_Reports_CSV/"
                f"{market.capitalize()}/{file}_{d.strftime('%Y_%m_%d')}.{file_extension}"
            )
            for d in dates
        ]
        for url in urls:
            df = download_and_get_frame_ice(url, s)
            dfs.append(df)
        ret_df = pd.concat(dfs)
    else:
        try:
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date)
            if not isinstance(start_date, dt.datetime):
                raise ValueError("start_date and end_date must be a str or dt.datetime")
            d = start_date.strftime("%Y_%m_%d")
            url = (
                "https://downloads.ice.com/Settlement_Reports_CSV/"
                f"{market.capitalize()}/{file}_{d}.{file_extension}"
            )
            response = s.get(url, verify=False)
            if "no files available" in response.text.lower():
                log.info(f"Data Not available for {url} with extension {file_extension}")
                log.info(f"Retrying with .dat.gz extension")
                url = f"{url}.gz"
                response = s.get(url, verify=False)
                if "no files available" in response.text.lower():
                    return pd.DataFrame()

            data = StringIO(response.text) if not url.endswith("gz") else BytesIO(response.content)
            compression = "gzip" if url.endswith("gz") else None
            try:
                ret_df = pd.read_csv(data, delimiter="|", compression=compression)
            except BadGzipFile as e:
                if str(e).endswith("(b'Yo')"):
                    raise Exception("Bad gzip file")
                elif str(e).endswith("(b'TR')"):
                    log.info("Downloaded a text file not gzip")
                    ret_df = pd.read_csv(data, delimiter="|", compression=None)
                else:
                    raise e
            if len(ret_df) == 0 and ret_df.columns[0] not in [
                "TRADE_DATE", "TRADE DATE", "ADE DATE",
            ]:
                if "limited" in ret_df.columns[0].lower():
                    log.info(f"Downloaded rate limited for {url} retrying in 60s")
                    raise Exception("Rate limited")
                raise Exception("Bad file")

            log.info(f"Downloaded {url} with {len(ret_df)} rows")
        except Exception as e:
            log.info(f"Could not download {file} for {start_date} due to {e} retrying in 60s")
            raise Exception(f"Could not download {file} for {start_date} due to {e}")
    return ret_df


def save_ice_to_datebase_backfill(
    start_date: str, end_date: str | None = None, market: str = "gas"
):
    """Downloads and backfills ice gas data

    Args:
        start_date (str): date to download data from
        end_date (str | None, optional): end date of backfill.
            Defaults to None which will be T-1 from today.
    """

    def insert_into_sql(df, table):
        log.info(f"inserting {df.TRADE_DATE.dt.date.unique()[0]}")
        to_sql(df, table, index=False)

    if market == "gas":
        hubs = [
            "Waha", "CG-Mainline", "HSC", "Michcon", "Chicago", "Algonquin",
            "Eastern Gas-South", "TETCO-M3", "Socal-Citygate", "Henry", "Transco-85",
            "Transco-Z5 South", "Transco-Z6 (non-NY)", "AB-NIT",
        ]
        table = "ICE_GAS"
        filename = "icecleared_gas"
        reorder_columns = [
            "TRADE DATE", "HUB", "PRODUCT", "STRIP", "CONTRACT", "CONTRACT TYPE",
            "SETTLEMENT PRICE", "NET CHANGE", "EXPIRATION DATE", "PRODUCT_ID",
        ]
        columns = [
            "TRADE_DATE", "HUB", "PRODUCT", "STRIP", "CONTRACT", "CONTRACT_TYPE",
            "SETTLEMENT_PRICE", "NET_CHANGE", "EXPIRATION_DATE", "PRODUCT_ID",
        ]
    elif market == "oil":
        hubs = None
        table = "ICE_OIL"
        filename = "icecleared_oil"
        reorder_columns = [
            "TRADE DATE", "HUB", "PRODUCT", "STRIP", "CONTRACT", "CONTRACT TYPE",
            "SETTLEMENT PRICE", "NET CHANGE", "EXPIRATION DATE", "PRODUCT_ID",
        ]
        columns = [
            "TRADE_DATE", "HUB", "PRODUCT", "STRIP", "CONTRACT", "CONTRACT_TYPE",
            "SETTLEMENT_PRICE", "NET_CHANGE", "EXPIRATION_DATE", "PRODUCT_ID",
        ]
    elif market == "power":
        hubs = None
        table = "ICE_POWER"
        filename = "icecleared_power"
        reorder_columns = [
            "TRADE DATE", "HUB", "PRODUCT", "STRIP", "CONTRACT", "CONTRACT TYPE",
            "STRIKE", "SETTLEMENT PRICE", "NET CHANGE", "EXPIRATION DATE", "PRODUCT_ID",
        ]
        columns = [
            "TRADE_DATE", "HUB", "PRODUCT", "STRIP", "CONTRACT", "CONTRACT_TYPE",
            "STRIKE", "SETTLEMENT_PRICE", "NET_CHANGE", "EXPIRATION_DATE", "PRODUCT_ID",
        ]
    else:
        raise ValueError(f"{market} is not known only oil and gas is known")

    existing_dates = read_sql(f"Select Distinct TRADE_DATE from {table}").TRADE_DATE.values
    edate = end_date or dt.date.today() - dt.timedelta(days=1)
    dates = pd.bdate_range(start_date, edate)
    dates = [x for x in dates if x not in existing_dates]
    date_chunks = [dates[i : i + 15] for i in range(0, len(dates), 15)]  # noqa: E203
    s = requests.Session()
    credentials = {"userId": ice_user, "password": ice_password, "appKey": "ICEDOWNLOADS"}
    headers_login = {"Content-Type": "application/json"}

    response = s.post(
        "https://sso.ice.com/api/authenticateTfa",
        data=json.dumps(credentials),
        headers=headers_login,
        verify=False,
    )
    if "error" in response.text.lower():
        raise Exception(f"Failed to authenticate ! {response.text}")
    if len(date_chunks) == 0:
        log.info("Not Dates to process")
    for date_list in date_chunks:
        raw_data_to_insert = []
        for date in date_list:
            if market == "oil" and date.year == 2004 and date.month in [11, 12]:
                extension = "dat"
            elif date.year < 2006 and market == "oil":
                extension = "dat.gz"
            else:
                extension = "dat"
            try:
                raw_data = download_ice_data(
                    date, session=s, market=market, file=filename, file_extension=extension
                )
            except Exception as e:
                log.info(e)
                raw_data = pd.DataFrame()
            if not raw_data.empty:
                if "NET_CHANGE" in raw_data.columns:
                    raw_data = raw_data.rename(columns={"NET_CHANGE": "NET CHANGE"})
                if "EXPRIRATION DATE" in raw_data.columns:
                    raw_data = raw_data.rename(columns={"EXPRIRATION DATE": "EXPIRATION DATE"})
                if "PRODUCT_ID" not in raw_data.columns:
                    raw_data["PRODUCT_ID"] = None
                if "ADE DATE" in raw_data.columns:
                    raw_data = raw_data.rename(columns={"ADE DATE": "TRADE DATE"})
                raw_data = raw_data[reorder_columns]
                raw_data.columns = columns
                raw_data["TRADE_DATE"] = pd.to_datetime(raw_data["TRADE_DATE"])
                raw_data["EXPIRATION_DATE"] = pd.to_datetime(raw_data["EXPIRATION_DATE"])
                if hubs:
                    process_raw_data = raw_data.loc[raw_data["HUB"].isin(hubs), :]
                else:
                    process_raw_data = raw_data
                raw_data_to_insert.append(process_raw_data)
                time.sleep(2)  # to avoid rate limiting
        if len(raw_data_to_insert) > 0:
            to_insert = pd.concat(raw_data_to_insert)
            existing_dates = read_sql(f"Select Distinct TRADE_DATE from {table}").TRADE_DATE.values
            args = [
                (gdf, table)
                for d, gdf in to_insert.groupby("TRADE_DATE")
                if d not in existing_dates
            ]
            with tp_exec(20) as pool:
                pool.map(insert_into_sql, *zip(*args))


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(60))
def get_dataset_meta(dataset_id=None, licensed=True):
    lice = 1 if licensed else 0
    dataset_filter = f"&dataset_id={dataset_id}" if dataset_id else ""
    url = (
        "https://api.energyaspects.com/data/datasets/timeseries?"
        f"api_key={ea_api_key}{dataset_filter}&licensed={lice}"
    )
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        if dataset_id:
            if len(response.json()) == 0:
                log.warning(f"Dataset {dataset_id} not found")
                return pd.DataFrame()
            ret = pd.DataFrame(response.json()[0]["metadata"])
            ret = ret.drop(columns=["release_dates"])
            ret.drop_duplicates(inplace=True)
        else:
            log.info("break")
    else:
        log.info(f"Could not download {url} due to {response.status_code} retrying in 60s")
        raise Exception(f"Could not download {url} due to {response.status_code}")
    return ret


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(60))
def get_available_ea_datasets(group=None, only_licensed=True):
    url = f"https://api.energyaspects.com/data/dataset_mappings?api_key={ea_api_key}"
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        resp = response.json()
        all_datasets = pd.concat([pd.DataFrame(y, index=[x] * len(y)) for x, y in resp.items()])
        all_datasets.index.name = "dataset_group"
        if only_licensed:
            all_datasets = all_datasets[all_datasets["licensed"] == "yes"]
    else:
        Exception(f"Could not download {url} due to {response.status_code} retrying in 60s")
    if group is not None:
        all_datasets = all_datasets.loc[group.lower()]
        all_datasets = all_datasets.explode("dataset_ids").reset_index().set_index("dataset_ids")
        for i in all_datasets.index:
            meta_data = get_dataset_meta(i, licensed=only_licensed)  # noqa: F841
            log.info("break")

    return all_datasets


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(60))
def energy_aspects(dataset_id: str, start: str, release_date=None):
    """
    download energy aspects data
    dataset_id: str, e.g. '1064,1065,1066,1067,1068,1069,1070,1071,1072,1073,1074,1075,1076,
    1077,1078,1079,1080,1081,1082,1083,1084,1085,1086,1087,1088,1089,1090,1091,1092,1093,1094,
    1095,1096,1097,1098,1099,1100,1101,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111,1112,
    1113,1114,1115,1116,1117,1118,1119,1120,1121,1122,1123,1124,1125,1126,1127,1128,1129,1130,
    1131,1132,1133,1134,1135,1136,1137,1138,1139,1140,1141,1142,1143,1144,1145,1146,1147,1148,
    1149,1150,1151,1152,1153,1154,1155,1156,1157,1158,1159,1160,1161,1162,1163,1164,1165,1166,
    1167,1168,1169,1170,1171,1172,1173,1174,1175,1176,1177,1178,1179,1180,1181,1182,1183,1184,
    1185,1186,1187,1188,1189,1190,1191,1192,1193,1194,1195,1196,1197,1198,1199,1200,1201,1202,
    1203,1204,1205,1206,1207,1208,1209,1210,1211,1212,1213,1214,1215,1216,1217,1218,1219,1220,
    1221,1222,1223,1224,1225,1226,1227,1228,1229,1230,1231,1232,1233,1234,1235,1236,1237,1238,
    1239,1240,1241,1242,1243,1244,1245,1246,1247,1248,1249,1250,1251,1252,1253,1254,1255,1256,
    1257,1258,1259,1260,1261,1262,1263,1264,1265,1266,1267,1268,1269,1270,1271,1272,1273,1274'
    start: str, e.g. '2020-01-01'
    release_date: str, e.g. '2023-07-10T11:45:00'
    Example:
        data = energy_aspects(
        dataset_id="818,819,820,821,822,823,824,825,826,827,828,829,830,831,832,833,"
        "834,835,836,837,838,839,840,841,842,843,844,845,846,847,848,849,"
        "5214,5215,5216,57,58,59,60,61,62,63,64,65,66,67,68",
        start="2010-01-01",
        release_date="2023-07-10T11:45:00",
    )
    """
    if release_date is None:
        data_url = (
            f"https://api.energyaspects.com/data/timeseries/csv?"
            f"api_key={ea_api_key}&date_from={start}"
        )
        request_string = data_url + "&dataset_id=" + dataset_id
        resp = requests.get(request_string, verify=False)
        if resp.status_code == 200:
            data = pd.read_csv(StringIO(resp.text))
        else:
            raise Exception(
                f"Could not download {request_string} due to {resp.status_code} >>\n{resp.text}"
            )
    else:
        part1 = "https://api.energyaspects.com/data/timeseries/"
        data_url = "{}csv?api_key={}&release_date={}&date_from={}".format(
            part1, ea_api_key, release_date, start
        )
        request_string = data_url + "&dataset_id=" + dataset_id
        resp = requests.get(request_string, verify=False)
        if resp.status_code == 200:
            data = pd.read_csv(StringIO(resp.text))
        else:
            raise Exception(
                f"Could not download {request_string} due to {resp.status_code} >>\n{resp.text}"
            )
        try:
            data = pd.read_csv(request_string)
        except Exception:
            resp = requests.get(request_string, verify=False)
            if resp.status_code == 200:
                data = pd.read_csv(StringIO(resp.text))
            else:
                raise Exception(f"Could not download {request_string} due to error in data")
    if isinstance(data, pd.DataFrame) and "error" in data.columns[0]:
        raise Exception(f"Could not download {request_string} due to error in data")
    return data


def ea_release_dates(dataset_id=14, monthly=True):
    """
    EA forecast release dates - 14 is OPEC crude production
    """
    request_string = (
        f"https://api.energyaspects.com/data/datasets/timeseries/{dataset_id}?api_key={ea_api_key}"
    )
    res = requests.get(request_string, verify=False)
    response = pd.read_json(StringIO(res.content.decode("utf-8")))
    release_dts = response.metadata.release_dates[-80:]
    release_dts = pd.DatetimeIndex(release_dts)
    if monthly:
        monthly_release_dts = release_dts[~release_dts.to_period("m").duplicated()]
        monthly_release_dts = [x.strftime("%Y-%m-%dT23:55:00") for x in monthly_release_dts]
        return monthly_release_dts
    else:
        weekly_release_dts = release_dts[~release_dts.to_period("d").duplicated(keep="last")]
        weekly_release_dts = [x.strftime("%Y-%m-%dT23:55:00") for x in weekly_release_dts]
        return weekly_release_dts


def ea_dataset(dataset_id=14):
    """
    EA forecast release dates - 14 is OPEC crude production
    """
    request_string = (
        "https://api.energyaspects.com/data/datasets/timeseries?api_key="
        f"{ea_api_key}&dataset_id={dataset_id}"
    )
    res = requests.get(request_string, verify=False)
    response = pd.read_json(StringIO(res.content.decode("utf-8")))
    return response


def ea_us_oil_weekly(
    folder=f"{csv_path}\\oil\\ea\\US Oil Weekly", issue=-1, sheet_name=None, date_format="%b %y"
):
    r"""
    EA US Oil Weekly pdf is converted to Excel and saved to this location:
    S:\Michel Kikano\CODE\outputs\csvs\oil\ea\US Oil Weekly
    This function reads the table in US Oil weekly on issue date
    Tables available in the Excel file:
        'Fig 1': 'Fig 1 US inventory projections',
        'Fig 2': 'Fig 2 Cushing balances',
        'Fig 3': 'Fig 3 US crude oil balance 2025',
        'Fig 4': 'Fig 4 US crude oil balance 2026',
        'Fig 5': 'Fig 5 US gasoline balance',
        'Fig 6': 'Fig 6 US gasoline balance weekly forecast',
        'Fig 9': 'Fig 9 US distillate balance',
        'Fig 10': 'Fig 10 US distillate balance weekly forecast',
        'Fig 17': 'Fig 17 PADD 1 crude oil balance 2025',
        'Fig 18': 'Fig 18 PADD 1 crude oil balance 2026',
        'Fig 19': 'Fig 19 PADD 2 crude oil balance 2025',
        'Fig 20': 'Fig 20 PADD 2 crude oil balance 2026',
        'Fig 21': 'Fig 21 PADD 3 crude oil balance 2025',
        'Fig 22': 'Fig 22 PADD 3 crude oil balance 2026',
        'Fig 23': 'Fig 23 PADD 4 crude oil balance 2025',
        'Fig 24': 'Fig 24 PADD 4 crude oil balance 2026',
        'Fig 25': 'Fig 25 PADD 5 crude oil balance 2025',
        'Fig 26': 'Fig 26 PADD 5 crude oil balance 2026',
    """
    files = [x for x in os.listdir(convert_path_to_linux(folder))]
    files.sort()
    if not isinstance(issue, int):
        file_dts = [dt.datetime.strptime(x[:8], "%Y%m%d") for x in files]
        last_day = issue
        issue = np.where(np.array(file_dts) <= last_day)[0][-1]
    if sheet_name is None:
        sheet_name = "Fig 2 Cushing balances"
    data = pd.read_excel(convert_path_to_linux(f"{folder}\\{files[issue]}"), sheet_name=sheet_name)
    data.set_index(data.columns[0], inplace=True)
    data = data.T
    last_file_date = dt.datetime.strptime(files[issue][:8], "%Y%m%d")
    if date_format is not None:
        data.index = [dt.datetime.strptime(x, date_format) for x in data.index]
        if "%y" not in date_format.lower():
            year = last_file_date.year
            new_index = []
            for i, date_val in enumerate(data.index):
                if i > 0 and date_val.month < data.index[i - 1].month:
                    year += 1
                new_index.append(date_val.replace(year=year))
            data.index = pd.DatetimeIndex(new_index)
    return data, last_file_date


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(30))
def eia(field="petroleum.stoc.wstk.WCESTUS1", freq="weekly", url=None, facets="series"):
    """
    ticker includes the url part after https://api.eia.gov/v2/ and before /data/?
    separated by '.'
    """
    if url is None:
        ticker_list = field.split(".")
        url_ = "/".join(ticker_list[:-1])
        url = (
            f"https://api.eia.gov/v2/{url_}/data/?api_key={eia_api_key}&frequency={freq}"
            f"&data[0]=value&facets[{facets}][]={ticker_list[-1]}&sort[0][column]=period"
            "&sort[0][direction]=desc"
        )
    commercial = requests.get(url, verify=False)
    json_data = commercial.json()
    if commercial.status_code != 200:
        raise Exception(f"Could not download {url} due to \n{commercial.text}: retrying in 30s")
    df = pd.DataFrame(json_data["response"]["data"])
    df.set_index("period", inplace=True)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def update_cme_block_trades_db(df):
    """Converts input cme_block_trades df to its schema form
    and inserts it to the db
    """
    schema = CMEBlockTrades
    db = LO25DB("prod")
    data = schema(df, form="raw", nullable=False)
    data.dump_sql(db, form="db", mode="update_first")
    return data


class IEA(object):
    """
    Load IEA data from folders
    """

    def __init__(self, issue=-1):
        """
        issue=-1 is the latest data, -2 is the previous issue
        issue="202403" is 2024 Mar release
        return list of IEA folders
        """
        if not isinstance(issue, list):
            _issue = [issue]
        else:
            _issue = issue
        self.folder = []
        folder_list = self.iea_folder_list()
        for i in _issue:
            if isinstance(i, str):
                self.folder.append(convert_path_to_linux(f"{data_path}\\IEA\\{i}"))
            elif isinstance(i, int):
                self.folder.append(folder_list[i])

    @staticmethod
    def iea_folder_list():
        """
        All IEA folders
        """
        all_folders = [x[0] for x in os.walk(convert_path_to_linux(f"{data_path}\\IEA"))]
        all_folders.sort()
        return all_folders

    @staticmethod
    def _load_stocks(folder=None):
        """
        load stocks data from one IEA folder
        convert unit to mb
        """
        if folder is None:
            folder = IEA.iea_folder_list()[-1]
        df = pd.read_csv(
            convert_path_to_linux(f"{folder}\\stockdat.TXT"), header=None, delim_whitespace=True
        )
        df.columns = ["Govt_Industrial", "Country", "Product", "Date", "Value"]
        df["Value"] = df["Value"].astype(np.float64)
        df["Value"] = df["Value"] / 1000
        df["Date"] = pd.to_datetime(df["Date"])
        return df

    @staticmethod
    def stocks_meta():
        data = IEA._load_stocks()
        return {
            "govt_industrial": list(data["Govt_Industrial"].unique()),
            "country": list(data["Country"].unique()),
            "product": list(data["Product"].unique()),
        }

    def stocks(self, country="OECDTOT", product="TOTALOIL", govt_industrial="INDUSTRY"):
        res = pd.DataFrame()
        for i in self.folder:
            data = self._load_stocks(i)
            df = data.loc[
                (data["Govt_Industrial"] == govt_industrial)
                & (data["Country"] == country)
                & (data["Product"] == product),
                ["Date", "Value"],
            ]
            df["Date"] = pd.to_datetime(df["Date"])
            df = (df.set_index("Date")).sort_index()
            df.columns = [i.split("\\")[-1]]
            res = pd.concat([res, df], axis=1)
        return res


class GS(object):
    """
    GS oil model
    """

    def __init__(self, issue=-1):
        """
        issue=-1 is the latest data, -2 is the previous issue
        return list of gs files
        """
        self.folder = convert_path_to_linux(f"{data_path}\\sell_side_consensus\\GS")
        if not isinstance(issue, list):
            _issue = [issue]
        else:
            _issue = issue
        files = os.listdir(self.folder)
        files.sort()
        self.files = []
        for i in _issue:
            self.files.append(files[i])

    def meta(self):
        """
        snd items
        """
        return [
            "Imbalance", "OECD commercial stocks", "OECD levels (EoM, mb)",
            "World supply", "Total non-OPEC supply", "World Demand", "OPEC Supply_Iran",
            "Global Demand_China", "Non-OPEC Supply_Russia", "Non-OPEC Supply_US crude",
            "OPEC Supply_Saudi Arabia",
        ]

    def _raw_data(self, file, item="Imbalance"):
        df = pd.read_excel(
            convert_path_to_linux(f"{self.folder}\\{file}"),
            sheet_name=dt.datetime.strptime(file.split(".xlsx")[0][-8:], "%Y%m%d").strftime(
                "%d-%b-%y"
            ),
            header=6,
        )
        df.drop(df.columns[0], axis=1, inplace=True)
        df.loc[:, df.columns[0]].fillna(method="ffill", inplace=True)
        if isinstance(item, list):
            return df.loc[(df["Unnamed: 1"] == item[0]) & (df["Unnamed: 2"] == item[1]), :]
        else:
            return df.loc[df["Unnamed: 2"] == item, :]

    def monthly_data(self, item="Imbalance"):
        if "_" in item:
            _item = item.split("_")
        else:
            _item = item
        res = pd.DataFrame()
        for i in self.files:
            date_str = i.split(".xlsx")[0][-8:]
            df = self._raw_data(file=i, item=_item)
            df_ = df[[x for x in df.columns if isinstance(x, dt.datetime)]].T
            df_.index = pd.to_datetime(df_.index)
            df_[df_.columns[0]] = pd.to_numeric(df_[df_.columns[0]], errors="coerce")
            res = pd.concat([res, df_.iloc[:, 0].to_frame(date_str)], axis=1)
        return res

    def quarterly_data(self, item="Imbalance"):
        if "_" in item:
            _item = item.split("_")
        else:
            _item = item
        res = pd.DataFrame()
        for i in self.files:
            date_str = i.split(".xlsx")[0][-8:]
            df = self._raw_data(file=i, item=_item)
            df_ = df[[x for x in df.columns if "Q" in str(x)]].T
            df_.index = pd.to_datetime(df_.index)
            res = pd.concat([res, df_.iloc[:, 0].to_frame(date_str)], axis=1)
        return res


def crude_consensus(end=None):
    """
    end: end_date
    return forecasted monthly change of crude stocks
    """
    consen = read_sql("select * from dbo.Consensus_Balances_CrudeBalance order by AS_of_date, Date")
    consen["AS_of_date"] = pd.to_datetime(consen["AS_of_date"])
    consen = consen.loc[consen["AS_of_date"] == max(consen["AS_of_date"]), :]
    consen["Energy_Aspects"] = consen["Energy_Aspects"].astype(float, errors="raise")
    consen["JPM"] = consen["JPM"].astype(float, errors="raise")
    consen["Consensus"] = consen[["Energy_Aspects", "JPM"]].mean(axis=1, numeric_only=None)
    consen["Date"] = pd.to_datetime(consen["Date"])
    consen = consen.set_index("Date")
    consen.rename(columns={"AS_of_date": "_last_update"}, inplace=True)
    if end is None:
        return consen
    else:
        return consen.loc[consen.index <= end, :]


def save_email_attachment(
    subject: str, attachments: list, to_folder: str, start: dt.datetime, end: dt.datetime
):
    """
    Save email attachment
    :param subject: email subject
    :param attachments: names of attachments
    :param to_folder: save to folder
    :param start: search start date
    :param end: search end date
    :return: None
    """
    if sys.platform == "win32":
        atts = {}
        for i in attachments:
            atts[i] = 0
        outlook = Dispatch("Outlook.Application").GetNamespace("MAPI")
        inbox = outlook.GetDefaultFolder("6")
        all_inbox = inbox.Items
        sub_today = re.compile("{}.*".format(subject))
        if end is None:
            end = today()
        if start is None:
            start = today() - dt.timedelta(2)
        for msg in all_inbox:
            try:
                x = dt.datetime(
                    (msg.CreationTime.year), (msg.CreationTime.month), (msg.CreationTime.day)
                )
            except Exception:
                x = dt.datetime(2010, 1, 1)
            if start <= x <= end:
                if sub_today.search(msg.Subject) is not None:
                    for att in msg.Attachments:
                        if att.FileName in atts.keys() and atts[att.FileName] == 0:
                            att.SaveAsFile(convert_path_to_linux(to_folder + "\\" + att.FileName))
                            atts[att.FileName] = 1
    else:
        raise NotImplementedError(f"Cannot run save email attachement on {sys.platform}")


def genscape_from_email(to_folder, att_name, subject, start):
    """
    save genscape data from email
    Example:
        save_attachment_to_folder(
        to_folder="S://Michel Kikano//Joseph//US_Gas//Raw_Data//Genscape//Daily_Production",
        att_name="Spring_Rock_Production_Pipe_Flow_Data_",
        subject="Wood Mackenzie Daily Pipe Production Data",
        start=dt.datetime(2023, 7, 5),
        date_format="%Y%m%d",
        file_type="xlsx",
    )
    """
    save_attachment_to_folder(
        to_folder=to_folder,
        att_name=att_name,
        subject=subject,
        start=start,
        date_format="%Y%m%d",
        file_type="xlsx",
    )


def save_attachment_to_folder(
    to_folder, att_name, subject, start, date_format="%Y%m%d", file_type="xlsx"
):
    if len(os.listdir(to_folder)) == 0:
        sdate = start
    else:
        exist_dates = []
        date_length = len(today().strftime(date_format))
        for filename in os.listdir(to_folder):
            if os.path.isfile(convert_path_to_linux(to_folder + "\\" + filename)):
                exist_dates.append(
                    dt.datetime.strptime(filename.split(".")[0][-date_length:], date_format)
                )
        if len(exist_dates) > 0:
            sdate = np.max(exist_dates) + dt.timedelta(days=1)
        else:
            sdate = start
    if sdate <= today():
        atts = []
        for i in pd.bdate_range(sdate, today()):
            atts.append(att_name + i.strftime(date_format) + "." + file_type)
        save_email_attachment(
            subject=subject, attachments=atts, to_folder=to_folder, start=sdate, end=today()
        )


def ice_price_table(contract, num=4, roll_day=10, months_ahead=1, mon_list=None, pdb_spread=True):
    """
    Get next a few contracts from ICE_Oil table
    """

    def get_monthly_contract(num=4, roll_day=10, months_ahead=1):
        mon_list = []
        if today().day > roll_day:
            mon1 = today() + relativedelta(months=months_ahead) + relativedelta(day=1)
        else:
            mon1 = today() + relativedelta(months=months_ahead - 1) + relativedelta(day=1)
        mon_list.append(mon1)
        for i in range(1, num):
            mon_list.append(mon1 + relativedelta(months=i))
        return mon_list

    if mon_list is None:
        mon_list = get_monthly_contract(num=num, roll_day=roll_day, months_ahead=months_ahead)
    mon_str_list = [
        dt.datetime.strftime(x, "%#m/%#d/%Y")
        if sys.platform.startswith("win")
        else dt.datetime.strftime(x, "%-m/%-d/%Y")
        for x in mon_list
    ]
    mon_str_list1 = [dt.datetime.strftime(x, "%b-%Y") for x in mon_list]
    df = pd.DataFrame()
    data = read_sql(
        f"Select * from ICE_OIL where CONTRACT='{contract}' order by TRADE_DATE, EXPIRATION_DATE"
    )
    for idx, i in enumerate(mon_str_list):
        contract_data = data.loc[data["STRIP"] == i, ["TRADE_DATE", "SETTLEMENT_PRICE"]]
        contract_data.drop_duplicates(inplace=True)
        contract_data.set_index("TRADE_DATE", inplace=True)
        contract_data.index = pd.to_datetime(contract_data.index)
        contract_data.columns = [mon_str_list1[idx]]
        df = pd.concat([df, contract_data], axis=1)
    if contract == "PDB":
        dbq = read_sql(
            "Select * from ICE_OIL where CONTRACT='DBQ' order by TRADE_DATE, EXPIRATION_DATE"
        )
        dbq["STRIP"] = pd.to_datetime(dbq["STRIP"])
        for i in df.index:
            if i >= mon_list[0]:
                dbq_day = dbq.loc[
                    (dbq["STRIP"] > i) & (dbq["STRIP"] < mon_list[1]) & (dbq["TRADE_DATE"] == i), :
                ]
                if pdb_spread:
                    df.loc[i, df.columns[0]] = (
                        dbq_day["SETTLEMENT_PRICE"].mean() - df.loc[i, df.columns[1]]
                    )
                else:
                    df.loc[i, df.columns[0]] = dbq_day["SETTLEMENT_PRICE"].mean()
            else:
                if pdb_spread:
                    df.loc[i, df.columns[0]] = df.loc[i, df.columns[0]] - df.loc[i, df.columns[1]]
    return df


if __name__ == "__main__":
    failing_id_list = (
        "1530,1531,1532,1533,1534,1535,1536,1537,1538,1539,1540,1541,1542,1543,1544,"
        "1545,1546,1547,1548,1549,1550,1551,1552,1553,1554,1555,1556,1557,1558,1559,1560,1561"
    )
    x = energy_aspects(dataset_id=failing_id_list, start="2023-01-01", release_date="2025-05-10")
    log.info(x)
