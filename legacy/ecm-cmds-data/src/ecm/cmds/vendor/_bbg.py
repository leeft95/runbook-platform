import getpass
import os
import sys

import pandas as pd
from ecm.cmds.core.bbg_blp import bdh
from ecm.cmds.core.cdr import today
from ecm.cmds.core.config import root_path
from ecm.cmds.core.ticker import convert_ticker
from ecm.cmds.core.ticker import is_future_contract
from ecm.cmds.core.ticker import is_spread
from ecm.cmds.core.utils import convert_path_to_linux
from ecm.cmds.vendor._platts import get_market_data
from ecm.cmds.vendor._rvx import rvx_daily_hapi
from pandas.tseries.offsets import BDay

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"

DREMIO_TOKENS = dict(
    ltrindade=os.environ["DREMIO_TOKEN_LTRINDADE"],
    rzhao=os.environ["DREMIO_TOKEN_RZHAO"],
)
try:
    current_user = os.getlogin()
except OSError:
    current_user = getpass.getuser()

os.environ["DREMIO_ACCESS_TOKEN"] = DREMIO_TOKENS.get(
    current_user, os.environ["DREMIO_TOKEN_RZHAO"]
)


def _bdh_and_internal(ticker, field, sdate, edate):
    """
    Get data from our internal database if exists, otherwise get from bloomberg
    If get from internal, add the latest data from bloomberg
    field can only be string
    """
    if is_future_contract(ticker) or is_spread(ticker):
        rvx_ticker = convert_ticker(ticker, ts=sdate)
    else:
        return bdh(ticker, [field], sdate, edate)
    if is_spread(ticker) and field == "PX_LAST":
        field_rvx = "PX_LAST_PM"
    else:
        field_rvx = field

    data = rvx_daily_hapi(rvx_ticker, [field_rvx], sdate, edate)
    if data is not None and len(data) > 0:
        if data[field_rvx].isnull().any():
            data = data[: data[field_rvx].isnull().idxmax()]
        data = data.rename(columns={field_rvx: field})
        data.dropna(inplace=True)
    if data is None or len(data) == 0:
        if field == "close":
            data = None
        if data is None or len(data) == 0:
            data = bdh(ticker, [field], sdate, edate)
        else:
            data.columns = [field]
            data = data.loc[data.index.dayofweek < 5, :]
    else:
        data = data[[field]]
    if data is None or len(data) == 0:
        data = bdh(ticker, [field], sdate, edate)
        return data
    elif data.index[-1] < edate:
        new_data = bdh(ticker, [field], data.index[-1], edate)
        if len(new_data) > 0:
            if new_data.index[0] > data.index[-1]:
                return pd.concat([data, new_data], axis=0)
            else:
                return pd.concat([data.iloc[:-1, :], new_data], axis=0)
        else:
            return data
    else:
        return data


def bdh_and_internal(ticker, fields, sdate, edate):
    """
    Get data from our internal database if exists, otherwise get from bloomberg
    If get from internal, add the latest data from bloomberg
    fields must be string
    """
    df = pd.DataFrame()
    if edate is None:
        edate = today() + BDay(1)
    for i in fields:
        data = _bdh_and_internal(ticker, i, sdate, edate)
        df = pd.concat([df, data], axis=1)
    return df


def bdh_update(ticker, fields, sdate, edate, data=None, n=1):
    """
    update historical data from bloomberg, start from data.index[-2]
    field must be list
    """
    if data is not None and len(data) > 0 and (edate is not None and data.index[-1] >= edate):
        return data
    elif data is None or len(data) <= n:
        return bdh_and_internal(ticker, fields, sdate, edate)
    else:
        new_data = bdh_and_internal(ticker, fields, data.index[-n], edate)
        if len(new_data) > 0:
            return pd.concat([data.iloc[:-n, :], new_data], axis=0)
        else:
            return data
        return data


def bdh_platts(ticker, platts_ticker, sdate, edate=None, data=None, csv_file=None):
    """
    update platts price. First try bloomberg, if fails, try csv
    Example:
        data = pd.read_csv(("\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\"
                           "Data\\market_scan\\price_spot\\PCRUFRT2 Index.csv"))
        data.set_index("date", inplace=True)
        data.index = pd.to_datetime(data.index)
        data.columns = ["PX_LAST"]
        c = bdh_platts(
            ticker='PCRUFRT2 Index',
            platts_ticker='AAGWZ00',
            sdate=dt.datetime(2010,1,1),
            edate=None,
            data=data,
            csv_file=f"{root_path}\\data\\platts\\platts_price.csv")
        print(c)
    """
    if edate is None:
        edate = today() + BDay(1)
    if data is None:
        try:
            data_ = bdh(ticker, ["PX_LAST"], sdate, edate)
        except Exception:
            data_ = pd.DataFrame()
        if len(data_) < 1:
            all_data = pd.read_csv(convert_path_to_linux(csv_file))
            all_data.set_index("date", inplace=True)
            all_data.index = pd.to_datetime(all_data.index)
            data_ = all_data[platts_ticker].to_frame("PX_LAST")
        return data_
    else:
        sdate = data.index[-1]
        try:
            data_ = bdh(ticker, ["PX_LAST"], sdate, edate)
        except Exception:
            data_ = pd.DataFrame()
        if data_.empty or len(data_) < 1:
            all_data = pd.read_csv(convert_path_to_linux(csv_file))
            all_data.set_index("date", inplace=True)
            all_data.index = pd.to_datetime(all_data.index)
            data_ = all_data[platts_ticker].to_frame("PX_LAST")
        data_ = pd.concat([data.iloc[:-1, :], data_.loc[sdate:, :]], axis=0)
        return data_


def get_platts(platts_ticker, sdate, edate=None, data=None, csv_file=None):
    """
    update platts price. First try platts api, if fails, try csv
    Example:
        data = pd.read_csv(("\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\"
                           "Data\\market_scan\\price_spot\\PCRUFRT2 Index.csv"))
        data.set_index("date", inplace=True)
        data.index = pd.to_datetime(data.index)
        data.columns = ["PX_LAST"]
        c = bdh_platts(
            ticker='PCRUFRT2 Index',
            platts_ticker='AAGWZ00',
            sdate=dt.datetime(2010,1,1),
            edate=None,
            data=data,
            csv_file=f"{root_path}\\data\\platts\\platts_price.csv")
        print(c)
    """
    if edate is None:
        edate = today() + BDay(1)
    if csv_file is None:
        csv_file = convert_path_to_linux(f"{root_path}\\data\\platts\\platts_price.csv")
    if data is None:
        try:
            data_ = get_market_data(platts_ticker, ["c"], sdate, edate)
            data_ = data_.rename(columns={"value": platts_ticker, "assessDate": "date"})[
                ["date", platts_ticker]
            ].set_index("date")
            if csv_file is not None:
                data_.to_csv = convert_path_to_linux(csv_file)
            data_ = data_[platts_ticker].to_frame("PX_LAST")
        except Exception as e:
            print(e)
            data_ = pd.DataFrame()
        if len(data_) < 1:
            all_data = pd.read_csv(convert_path_to_linux(csv_file))
            all_data.set_index("date", inplace=True)
            all_data.index = pd.to_datetime(all_data.index)
            data_ = all_data[platts_ticker].to_frame("PX_LAST")
        return data_
    else:
        sdate = data.index[-1]
        try:
            data_ = get_market_data(platts_ticker, ["c"], sdate, edate)
            data_ = data_.rename(columns={"value": platts_ticker, "assessDate": "date"})[
                ["date", platts_ticker]
            ].set_index("date")
            if csv_file is not None:
                data_.to_csv = convert_path_to_linux(csv_file)
            data_ = data_[platts_ticker].to_frame("PX_LAST")
        except Exception:
            data_ = pd.DataFrame()
        if len(data_) < 1:
            all_data = pd.read_csv(convert_path_to_linux(csv_file))
            all_data.set_index("date", inplace=True)
            all_data.index = pd.to_datetime(all_data.index)
            data_ = all_data[platts_ticker].to_frame("PX_LAST")
        data_ = pd.concat([data.iloc[:-1, :], data_.loc[sdate:, :]], axis=0)
        return data_


if __name__ == "__main__":
    ticker = "PCRUFRT2 Index"
    platts_ticker = "AAGWZ00"

    x = get_platts(
        platts_ticker=ticker,
        sdate=pd.to_datetime("2025-04-04"),
        edate=pd.to_datetime("2025-04-10"),
    )
    print(x)
