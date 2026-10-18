import datetime as dt

import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
import numpy as np
import pandas as pd
from ecm.cmds.cdr import today
from ecm.cmds.config import data_path
from fastparquet import ParquetFile
from pandas.tseries.offsets import BDay


def read_parq(file_name):
    pf = ParquetFile(file_name)
    return pf.to_pandas()


def convert_timezone(data, zone_in, zone_out):
    price_intraday = data.copy()
    price_intraday = price_intraday.loc[price_intraday.index.dayofweek != 6, :]
    price_intraday.index = price_intraday.index.tz_localize(zone_in)
    price_intraday.index = price_intraday.index.tz_convert(zone_out)
    price_intraday.index = price_intraday.index.tz_localize(None)
    price_intraday.sort_index(inplace=True)
    price_intraday = price_intraday[~price_intraday.index.duplicated(keep="first")]
    return price_intraday


def normalize_intraday(data, hour, minute):
    dts = data.index.normalize().unique()
    dts = dts[dts.dayofweek != 5]
    dts = dts[dts.dayofweek != 6]
    dts_target = dts + dt.timedelta(hours=hour, minutes=minute)
    if "vwap" in data.columns:
        price = data[["closep", "vwap"]].reindex(dts_target, method="bfill")
    else:
        price = data[["closep"]].reindex(dts_target, method="bfill")
    price.index = price.index.normalize()
    price.dropna(inplace=True)
    return price


def intraday_to_daily(
    ticker, hour, minute, zone, vwap_time=30, use_bbg=False, bbg_factor=1, active=None
):
    """
    Convert intraday price to daily price based on time zone, hour and minute
    Intraday data comes from ECM internal database, generally has 1d lag
    active: the 2 or 3 letters of future ticker. e.g. HO
    use_bbg: use bloomberg to fill the latest data
    bbg_factor: convert bbg price to the same as internal intraday price. e.g. HO and XB
    """
    if active is None:
        tk_dict = tk.decompose_ticker(ticker)
        active = tk_dict["base_ticker"]
    if len(active) <= 3:
        active_ = active
    else:
        active_ = active[:2]
    try:
        price_intraday = read_parq(f"{data_path}\\intraday\\{active_}\\{ticker}.parq")
    except Exception:
        price_intraday = read_parq(
            f"{data_path}\\intraday\\{active_}\\{ticker.split(' ')[0][:-2]}"
            f"{ticker.split(' ')[0][-1]} {ticker.split(' ')[-1]}.parq"
        )
    price_intraday.fillna(method="bfill", inplace=True)
    price_intraday = convert_timezone(data=price_intraday, zone_in="US/Eastern", zone_out=zone)
    if vwap_time is not None:
        price_intraday["vc"] = price_intraday["closep"] * price_intraday["volume"]
        price_intraday["vwap"] = (
            price_intraday["vc"].rolling(vwap_time).sum()
            / price_intraday["volume"].rolling(vwap_time).sum()
        )
        price_intraday["vwap"] = price_intraday["vwap"].shift(-vwap_time + 1)
        price_intraday.replace([np.inf, -np.inf], np.nan, inplace=True)
    price = normalize_intraday(data=price_intraday, hour=hour, minute=minute)
    if use_bbg:
        lastest_price = bbg.bdib(ticker, sdate=price.index[-1], edate=today() + BDay(1))
        lastest_price = convert_timezone(data=lastest_price, zone_in="UTC", zone_out=zone)
        lastest_price = lastest_price[["open", "high", "low", "close", "volume"]]
        lastest_price.columns = ["openp", "highp", "lowp", "closep", "volume"]
        if vwap_time is not None:
            lastest_price["vc"] = lastest_price["closep"] * lastest_price["volume"]
            lastest_price["vwap"] = (
                lastest_price["vc"].rolling(vwap_time).sum()
                / lastest_price["volume"].rolling(vwap_time).sum()
            )
            lastest_price["vwap"] = lastest_price["vwap"].shift(-vwap_time + 1)
            lastest_price.replace([np.inf, -np.inf], np.nan, inplace=True)
        lastest_price = normalize_intraday(data=lastest_price, hour=hour, minute=minute)
        return pd.concat(
            [price, lastest_price.loc[lastest_price.index > price.index[-1], :] * bbg_factor],
            axis=0,
        )
    else:
        return price


if __name__ == "__main__":
    data = intraday_to_daily(
        ticker="HOU5 Comdty",
        hour=16,
        minute=30,
        zone="Europe/London",
        vwap_time=30,
        use_bbg=True,
        bbg_factor=0.01,
    )
    print(data)
