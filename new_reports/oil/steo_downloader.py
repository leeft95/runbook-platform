import pandas as pd
import datetime as dt
from ecm.atom.clients import retry
import requests
import os
import sys
import time
from ecm.cmds.utils import convert_path_to_linux
if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"
root_path = "\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\CODE\\data\\eia\\steo"


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(20))
def get_release(date=None, save=False):
    if date is None:
        date = dt.datetime.today()
    mon = date.strftime("%b")
    yr = str(date.year)[-2:]
    print(f"Getting release data {mon} {yr}")

    if date > dt.datetime(2013, 7, 1):
        if save:
            try:
                link = f"https://www.eia.gov/outlooks/steo/archives/{mon.lower()}{yr}_base.xlsx"
                print(link)
                raw_bytes = requests.get(link).content
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
            pre_prod["date"] = [dt.datetime.strptime(f"{pre_prod.iloc[x, 0]}-{pre_prod.iloc[x, 1]}-1", "%Y-%m-%d")
                                for x in range(0, len(pre_prod))]
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
                pre_prod["date"] = [dt.datetime.strptime(f"{pre_prod.iloc[x, 0]}-{pre_prod.iloc[x, 1]}-1", "%Y-%m-%d")
                                    for x in range(0, len(pre_prod))]
                pre_prod = pre_prod[["date", col]]
                pre_prod.columns = ["date", f"{mon}-{yr}"]
                pre_prod.set_index("date", inplace=True)
                return pre_prod * 1000
    return pre_df


if __name__ == "__main__":
    releases = get_release(dt.datetime(2008, 7, 1), save=False)
