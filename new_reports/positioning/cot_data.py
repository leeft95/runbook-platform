import numpy as np
import pandas as pd
import datetime as dt
from pandas.tseries.offsets import BDay
import urllib.request
import requests
import io
import os
import sys
from bs4 import BeautifulSoup
import ecm.cmds.pyg as pyg
from ecm.cmds.config import url
from pyg_cell import *
from functools import partial
from pyg_mongo import mongo_table
from ecm.cmds.config import data_path
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"
else:
    os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"
cot_path = f"{data_path}\\cot"

ice_dict = {
    "COA Comdty": "B",
    "QSA Comdty": "G",
}

lme_dict = {
    "LPA Comdty": ["CA", "copper"],
    "LAA Comdty": ["AH", "aluminium"],
    "LXA Comdty": ["ZS", "Zinc"],
    "LLA Comdty": ["PB", "Lead"],
    "LNA Comdty": ["NI", "Nickel"],
    "LTA Comdty": ["SN", "Tin"],
}

active_dict = {
    "CLA Comdty": "067651",
    "ENA Comdty": "067411",
    "NYMEX Brent": "06765T",
    "XBA Comdty": "111659",
    "HOA Comdty": "022651",
    "NGA Comdty": "023651",
    "NG NYMEX Swap": "03565B",
    "NG NYMEX Penultimate": "03565C",
    "NG ICE Henry Hub": "023391",
    "GKA Options": "02365U",
    "GCA Comdty": "088691",
    "SIA Comdty": "084691",
    "PLA Comdty": "076651",
    "PAA Comdty": "075651",
    'HGA Comdty': "085692",
    'S A Comdty': "005602",
    'SMA Comdty': "026603",
    'BOA Comdty': "007601",
    'C A Comdty': "002602",
    'W A Comdty': "001602",
    'SBA Comdty': "080732",
    'CTA Comdty': "033661",
    'KCA Comdty': "083731",
    'CCA Comdty': "073732",
}

field_dict = {
    "MMLF": "M_Money_Positions_Long_All",
    "MMSF": "M_Money_Positions_Short_All",
    "OIF": "Open_Interest_All",
    "NCLF": "Noncommercial Positions-Long (All)",
    "NCSF": "Noncommercial Positions-Short (All)",
    "MMLFO": "M_Money_Positions_Long_All",
    "MMSFO": "M_Money_Positions_Short_All",
    "OIFO": "Open_Interest_All",
    "NCLFO": "Noncommercial Positions-Long (All)",
    "NCSFO": "Noncommercial Positions-Short (All)",
    "SDLF": "Swap_Positions_Long_All",
    "SDSF": "Swap_Positions_Short_All",
    "SDLFO": "Swap_Positions_Long_All",
    "SDSFO": "Swap_Positions_Short_All",
}


def save_file(link, file_name, cur_dt=None):
    class AppURLopener(urllib.request.FancyURLopener):
        version = "Mozilla/5.0"

    opener = AppURLopener()
    resp = requests.get(link, verify=False)
    data = resp.text

    if cur_dt is None:
        cur_dt = dt.datetime.strptime(data.split(",")[1], "%y%m%d").strftime("%Y%m%d")
    file_path = convert_path_to_linux(f'{cot_path}\\{file_name}_{cur_dt}.txt')
    with open(file_path, 'w+') as f:
        f.write(data)
    return file_path


def read_xls(link, sheet_name, header=0):
    req = urllib.request.Request(url=link, headers={'User-Agent': 'Mozilla/5.0'})
    webpage = urllib.request.urlopen(req, context=ctx).read()
    if "Sorry..." in str(webpage):
        raise Exception("file not found")
    df = pd.io.excel.read_excel(webpage, sheet_name=sheet_name, header=header)
    return df


def report_fields(link):
    field_list = []
    page = requests.get(link, verify=False)
    soup = BeautifulSoup(page.content, "html.parser")
    lst = soup.find_all("tbody")
    fields = lst[0].find_all("p")
    for idx, i in enumerate(fields):
        if idx > 0 and i.text.partition(' ')[-1] != '':
            field_list.append(i.text.partition(' ')[-1])
    return field_list


def add_new_data(cot, type, fo):
    """
    cot: the latest cot dataframe
    type: disaggregated or legacy
    fo: F - futures or FO - futures and options
    """
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    if type.lower() in ["disaggregated", "d"]:
        code_field = "CFTC_Contract_Market_Code"
        date_field = "As_of_Date_Form_YYYY-MM-DD"
        if fo.lower() in ["f"]:
            fields = ["MMLF", "MMSF", "OIF", "SDLF", "SDSF"]
        elif fo.lower() in ["fo"]:
            fields = ["MMLFO", "MMSFO", "OIFO", "SDLFO", "SDSFO"]
    elif type.lower() in ["legacy", "l"]:
        code_field = "CFTC Contract Market Code"
        date_field = "As of Date in Form YYYY-MM-DD"
        if fo.lower() in ["f"]:
            fields = ["NCLF", "NCSF"]
        elif fo.lower() in ["fo"]:
            fields = ["NCLFO", "NCSFO"]
    for key, val in active_dict.items():
        if fo.lower() in ["f"] and key == "GKA Options":
            print(key)
            pass
        else:
            for i in fields:
                if i in ["OIFO", "NCLFO", "NCSFO"] and key == "GKA Options":
                    pass
                else:
                    try:
                        c = pyg.get_cell(db, active=key, item=i)
                        new_data = cot.loc[cot[code_field] == val, [date_field, field_dict[i]]]
                        new_data.columns = ["date", "PX_LAST"]
                        new_data.set_index("date", inplace=True)
                        new_data.index = pd.to_datetime(new_data.index)
                        new_data["PX_LAST"] = new_data["PX_LAST"].astype(np.float64)
                        if c.data.index[-1] < new_data.index[-1]:
                            data = pd.concat([c.data, new_data], axis=0)
                            c.data = data
                            c.period = "10y"
                            c.save()
                    except Exception as e:
                        print(f"error:>>{e}")


def add_new_data_ice(cot, fo):
    """
    cot: the latest ice dataframe
    fo: F - futures or FO - futures and options
    """
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    code_field = "CFTC_Commodity_Code"
    date_field = "As_of_Date_Form_MM/DD/YYYY"
    if fo.lower() in ["f"]:
        fields = ["MMLF", "MMSF", "OIF", "SDLF", "SDSF"]
    elif fo.lower() in ["fo"]:
        fields = ["MMLFO", "MMSFO", "OIFO", "SDLFO", "SDSFO"]
    for key, val in ice_dict.items():
        for i in fields:
            try:
                c = pyg.get_cell(db, active=key, item=i)
                new_data = cot.loc[cot[code_field] == val, [date_field, field_dict[i]]]
                new_data.columns = ["date", "PX_LAST"]
                new_data.set_index("date", inplace=True)
                new_data.index = pd.to_datetime(new_data.index)
                new_data["PX_LAST"] = new_data["PX_LAST"].astype(np.float64)
                if c.data.index[-1] < new_data.index[-1]:
                    data = pd.concat([c.data, new_data], axis=0)
                    c.data = data
                    c.period = "10y"
                    c.save()
            except:
                print("error")


def update_cme():
    disagg_fields = report_fields(
        link="https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/CFTC_023168.html")
    disagg_f_path = save_file(link="https://www.cftc.gov/dea/newcot/f_disagg.txt", file_name="disaggregated_futures")
    disagg_f_data = pd.read_csv(disagg_f_path, names=disagg_fields, header=None)
    if "Swap__Positions_Short_All" in disagg_f_data.columns:
        disagg_f_data.rename(columns={"Swap__Positions_Short_All": "Swap_Positions_Short_All"}, inplace=True)
    if "Swap__Positions_Long_All" in disagg_f_data.columns:
        disagg_f_data.rename(columns={"Swap__Positions_Long_All": "Swap_Positions_Long_All"}, inplace=True)
    add_new_data(cot=disagg_f_data, type="disaggregated", fo="f")

    disagg_c_path = save_file(link="https://www.cftc.gov/dea/newcot/c_disagg.txt",
                              file_name="disaggregated_futures_options")
    disagg_c_data = pd.read_csv(disagg_c_path, names=disagg_fields, header=None)
    if "Swap__Positions_Short_All" in disagg_c_data.columns:
        disagg_c_data.rename(columns={"Swap__Positions_Short_All": "Swap_Positions_Short_All"}, inplace=True)
        if "Swap__Positions_Long_All" in disagg_f_data.columns:
            disagg_f_data.rename(columns={"Swap__Positions_Long_All": "Swap_Positions_Long_All"}, inplace=True)
    add_new_data(cot=disagg_c_data, type="disaggregated", fo="fo")

    legacy_fields = report_fields(
        link="https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/cotvariableslegacy.html")
    legacy_f_path = save_file(link="https://www.cftc.gov/dea/newcot/deafut.txt", file_name="legacy_futures")
    legacy_f_data = pd.read_csv(legacy_f_path, names=legacy_fields, header=None)
    add_new_data(cot=legacy_f_data, type="legacy", fo="f")

    legacy_c_path = save_file(link="https://www.cftc.gov/dea/newcot/deacom.txt", file_name="legacy_futures_options")
    legacy_c_data = pd.read_csv(legacy_c_path, names=legacy_fields, header=None)
    add_new_data(cot=legacy_c_data, type="legacy", fo="fo")


def update_ice(latest):
    cur_dt = latest.strftime("%d%m%Y")
    raise NotImplementedError("Missing ICE cache filename: IMG_4592 line 244")
    ice_data = pd.read_csv(ice_path)
    ice_data_f = ice_data.loc[ice_data["FutOnly_or_Combined"] == "FutOnly", :]
    add_new_data_ice(ice_data_f, "f")
    ice_data_fo = ice_data.loc[ice_data["FutOnly_or_Combined"] == "Combined", :]
    add_new_data_ice(ice_data_fo, "fo")


def add_new_data_lme(latest, active):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    cur_dt = latest.strftime("%d%m%Y")
    short_name = lme_dict[active][0]
    long_name = lme_dict[active][1]
    raise NotImplementedError("Missing LME report URL: IMG_4592 line 258")
    df = read_xls(link, short_name)
    report_date = dt.datetime.strptime(df.iloc[1, 0], "%Y-%m-%d")
    srow = 10
    scol = 5
    fields = ["IFLFO", "IFSFO", "OFLFO", "OFSFO"]
    for idx, i in enumerate(fields):
        pos = df.iloc[srow, scol + idx]
        new_data = pd.DataFrame(pos, index=[report_date], columns=["PX_LAST"])
        c = pyg.get_cell(db, active=active, item=i)
        if c.data.index[-1] < new_data.index[-1]:
            data = pd.concat([c.data, new_data], axis=0)
            c.data = data
            c.period = "10y"
            c.save()


def update_lme(latest):
    test_dt = latest
    while test_dt <= today():
        raise NotImplementedError("Missing LME release URL: IMG_4592 line 279")
        try:
            df = read_xls(link, "AH")
            release_dt = test_dt
            break
        except Exception as e:
            print(f"error:>>{e}")
            test_dt += BDay(1)
    for k, v in lme_dict.items():
        try:
            add_new_data_lme(latest=test_dt, active=k)
        except Exception as e:
            print(f"error:>>{k}||{e}")


def update_endex(latest):
    raise NotImplementedError("Missing ENDEX report URL: IMG_4592 line 295")
    req = urllib.request.Request(url=link, headers={'User-Agent': 'Mozilla/5.0'})
    webpage = urllib.request.urlopen(req, context=ctx).read()
    string_data = webpage.decode('cp1252')
    df = pd.read_csv(io.StringIO(string_data))
    df = df.loc[df["Report_Status"] == "NEWT", :]
    name_dict = {"TZTA Comdty": "TFM",
                 "MOA Comdty": "C"
                 }
    field_dict = {"IFLFO": "NOPS_Investment_Funds_Long_Total",
                  "IFSFO": "NOPS_Investment_Funds_Short_Total",
                  "DCLFO": "NOPS_Operators_with_obligations_under_Directive_2003/87/EC_Long_Total",
                  "DCSFO": "NOPS_Operators_with_obligations_under_Directive_2003/87/EC_Short_Total",
                  }
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    for k, v in name_dict.items():
        for k1, v1 in field_dict.items():
            if k not in ["TZTA Comdty"] or k1 not in ["DCLFO", "DCSFO"]:
                c = pyg.get_cell(db, active=k, item=k1)
                pos = df.loc[df["Venue_Product_Code"] == v, v1].values[0]
                new_data = pd.DataFrame(pos, index=[latest], columns=["PX_LAST"])
                if c.data.index[-1] < new_data.index[-1]:
                    data = pd.concat([c.data, new_data], axis=0)
                    c.data = data
                    c.period = "10y"
                    c.save()


def update_ice_swap(latest):
    raise NotImplementedError("Missing ICE MiFID report URL: IMG_4593 line 324")
    req = urllib.request.Request(url=link, headers={'User-Agent': 'Mozilla/5.0'})
    webpage = urllib.request.urlopen(req, context=ctx).read()
    string_data = webpage.decode('cp1252')
    df = pd.read_csv(io.StringIO(string_data))
    df = df.loc[df["Report_Status"] == "NEWT", :]
    name_dict = {"COA Comdty": "B",
                 "QSA Comdty": "G",
                 "ABEA Comdty": "ULD",
                 }
    field_dict = {"IFLFO": "NOPS_Investment_Funds_Long_Total",
                  "IFSFO": "NOPS_Investment_Funds_Short_Total",
                  "CILFO": "NOPS_Investment_Firms_or_Credit_Institutions_Long_Total",
                  "CISFO": "NOPS_Investment_Firms_or_Credit_Institutions_Short_Total",
                  }
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    for k, v in name_dict.items():
        for k1, v1 in field_dict.items():
            c = pyg.get_cell(db, active=k, item=k1)
            pos = df.loc[df["Venue_Product_Code"] == v, v1].values[0]
            new_data = pd.DataFrame(pos, index=[latest], columns=["PX_LAST"])
            if c.data.index[-1] < new_data.index[-1]:
                data = pd.concat([c.data, new_data], axis=0)
                c.data = data
                c.period = "10y"
                c.save()


if __name__ == "__main__":
    update_cme()
