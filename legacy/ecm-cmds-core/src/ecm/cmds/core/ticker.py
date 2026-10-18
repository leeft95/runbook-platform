import datetime as dt
import re

import numpy as np
import pandas as pd
from ecm.atom.parse import FutureTicker
from ecm.cmds.core.fx import is_fx
from ecm.cmds.core.pyg import get_data
from ecm.cmds.core.time_series import sum_dfs
from ecm.cmds.core.utils import bbgcase
from loguru import logger as log
from pyg_base import is_arr

MON = "F|G|H|J|K|M|N|Q|U|V|X|Z"
raise NotImplementedError("Clipped BASELESS_CONTRACT expression in IMG_5780")
ACTIVE = re.compile("^[(0-9| |A-Z)]{2,3}A (Comdty|Curncy|Index)$")
CONTRACT = re.compile("^[0-9|A-Z][(0-9| |A-Z)]{1,2}(F|G|H|J|K|M|N|Q|U|V|X|Z)[0-9]{1,2} (Comdty|Curncy|Index)$")
FUTC1 = re.compile("^[0-9|A-Z][(0-9| |A-Z)]{1,2} (Comdty|Curncy|Index) [0-9]{1,2}$")
FUT1C = re.compile("^[0-9|A-Z][(0-9| |A-Z)]{1,2}[0-9]{1} (Comdty|Curncy|Index)$")
FUT0C = re.compile("^[0-9|A-Z][(0-9| |A-Z)]{1}[A-Z]{1}[1-9]{1} (Comdty|Curncy|Index)$")

month_str2int = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}


month_int2str = {v: k for k, v in month_str2int.items()}


def yy2year(yy, century=1950):
    """
    estimate contract year from two digits, the cutoff to a century happens at 1950,
    so 51 goes to 1951 while 49 goes to 2049

    assert yy2year(8) == 2008
    assert yy2year(9) == 2009
    assert yy2year(0) == 2000
    assert yy2year(89) == 1989
    """
    cutoff = century % 100
    offset = century - cutoff
    rtn = yy + offset + (100 if yy < cutoff else 0)
    return rtn


def y2year(y, decade=None):
    """
    estimate contract year from one number :-(

    assert y2year(8) == 2018
    assert y2year(9) == 2019
    assert y2year(0) == 2020
    assert y2year(5) == 2025
    """
    if decade is None:
        decade = dt.datetime.now().year - 2
    cutoff = decade % 10
    offset = decade - cutoff
    return y + offset + (10 if y < cutoff else 0)


def contract2active_y_m(ticker):
    """
    convert ticker to active, m, y
    return dict
    """
    ending = BASELESS_CONTRACT.search(ticker).group(0)
    m = ending[0]
    ystr = ending[1:].split(" ")[0]
    if len(ystr) == 4:
        y = int(ystr)
    elif len(ystr) == 2:
        y = yy2year(int(ystr))
    elif len(ystr) == 1:
        y = y2year(int(ystr))
    else:
        raise ValueError("could not resolve year %s" % ystr)
    return dict(active=ticker[: -len(ending)] + "A " + ending.split(" ")[-1], y=y, m=m)


def decompose_ticker(ticker):
    ticker_dict = contract2active_y_m(ticker)
    ending = BASELESS_CONTRACT.search(ticker).group(0)
    ticker_dict["base_ticker"] = ticker[: -len(ending)]
    ticker_dict["asset_class"] = ending.split(" ")[-1]
    return ticker_dict


def expiry_to_first_of_month(month, year):
    if len(str(year)) == 1:
        int_year = y2year(year)
    elif len(str(year)) == 2:
        int_year = yy2year(year)
    elif len(str(year)) == 4:
        int_year = year
    else:
        raise ValueError(f"{year} is not valid")

    int_month = month_str2int.get(month.upper())
    if int_month is None:
        raise ValueError(f"{month} is not a valid contract month")

    first_of_month = dt.datetime(int_year, int_month, 1)
    return first_of_month


def is_spread(ticker):
    """
    whether a ticker is spread or not
    return boolean
    """
    if ticker[:2] == "S:":
        return True
    elif (
        re.search(
            f"({MON})[0-9]({MON})[0-9] (Comdty|Curncy|Index)$",
            ticker,
        )
        is not None
    ):
        return True
    elif (
        re.search(
            f"..({MON})[0-9]..({MON})[0-9] (Comdty|Curncy|Index)$",
            ticker,
        )
        is not None
    ):
        return True
    else:
        return False


def spread_base_ticker(ticker):
    """
    get tickers of two legs from spread ticker
    """
    if ticker[:2] == "S:":
        ticker_parts = ticker.split(" ")
        s1 = -int(len(ticker_parts[0][2:]) / 2)
        base_ticker1 = ticker_parts[0][2:s1]
        base_ticker2 = ticker_parts[0][s1:]
        if len(base_ticker1) == 2 and base_ticker1[-1] == "_":
            base_ticker1 = base_ticker1[0] + " "
        if len(base_ticker2) == 2 and base_ticker2[-1] == "_":
            base_ticker2 = base_ticker2[0] + " "
        m1 = ticker_parts[1].split("-")[0]
        m2 = ticker_parts[1].split("-")[1]
        active1 = f"{base_ticker1}A {ticker_parts[-1]}"
        active2 = f"{base_ticker2}A {ticker_parts[-1]}"
        if active1 == "ENA Comdty":
            contracts1_ = get_data("contracts", active="COA Comdty", item="fut_ref")
            contracts1 = contracts1_.copy()
            contracts1.loc[:, "ticker"] = [f"EN{x[2:]}" for x in contracts1.loc[:, "ticker"]]
        else:
            contracts1 = get_data("contracts", active=active1, item="fut_ref")
        if active2 == "ENA Comdty":
            contracts2_ = get_data("contracts", active="COA Comdty", item="fut_ref")
            contracts2 = contracts2_.copy()
            contracts2.loc[:, "ticker"] = [f"EN{x[2:]}" for x in contracts2.loc[:, "ticker"]]
        else:
            contracts2 = get_data("contracts", active=active2, item="fut_ref")
        mon1 = m1[0]
        yr1 = yy2year(int(m1[-2:]))
        mon2 = m2[0]
        yr2 = yy2year(int(m2[-2:]))
        return (
            contracts1.loc[(contracts1["y"] == yr1) & (contracts1["m"] == mon1), "ticker"].values[0],
            contracts2.loc[(contracts2["y"] == yr2) & (contracts2["m"] == mon2), "ticker"].values[0],
        )
    else:
        if (
            re.search(
                f"({MON})[0-9]({MON})[0-9] (Comdty|Curncy|Index)$",
                ticker,
            )
            is not None
        ):
            ticker_parts = ticker.split(" ")
            return (
                ticker_parts[0][:5] + " " + ticker_parts[-1],
                ticker_parts[0][:3] + ticker_parts[0][5:7] + " " + ticker_parts[-1],
            )
        else:
            ticker_parts = ticker.split(" ")
            s1 = int(len(ticker_parts[0]) / 2)
            return (
                ticker_parts[0][:s1] + " " + ticker_parts[-1],
                ticker_parts[0][s1:] + " " + ticker_parts[-1],
            )


def convert_ticker(ticker, base="bbg", to="rvx", ts=None):
    """
    ticker: string
    convert ticker between bloomberg and rvx
    base: from source
    to: to source
    ts: approximate ticker date to parse the year
    else the current date will be used
    return string
    """

    if base.lower() == "bbg":
        if is_spread(ticker):
            try:
                ft = FutureTicker(ticker, ts)
                return ft.as_ops_code().upper()
            except Exception as e:
                log.warning(e)
                log.warning("Falling Back to old implementation")
                tk1, tk2 = spread_base_ticker(ticker)
                td1 = decompose_ticker(tk1)
                td2 = decompose_ticker(tk2)
                myy1 = td1["m"] + str(td1["y"])[-2:]
                myy2 = td2["m"] + str(td2["y"])[-2:]
                return f"{td1['base_ticker']} {td1['asset_class']} {myy1} {myy2}"
        else:
            try:
                ft = FutureTicker(ticker, ts)
                return ft.as_ops_code().upper()
            except Exception as e:
                log.warning(e)
                log.warning("Falling Back to old implementation")
                td = decompose_ticker(ticker)
                return f"{td['base_ticker']} {td['asset_class']} {td['m']}{str(td['y'])[-2:]}"
    elif base.lower() == "rvx":
        ft = FutureTicker(ticker, ts)
        return ft.as_ticker(format=2).upper()


def is_active_contract(ticker):
    return not is_fx(ticker) and ACTIVE.search(ticker) is not None


def is_future_contract(ticker):
    return not is_fx(ticker) and CONTRACT.search(ticker) is not None


def is_generic_contract(ticker):
    """
    is this a generic contract of the form

    assert is_generic_contract('TY 1 Comdty')
    assert is_generic_contract('TY1 Comdty')
    assert is_generic_contract('TY Comdty')
    assert is_generic_contract('L  Comdty 10')

    assert not is_generic_contract('TYA Comdty')
    assert not is_generic_contract('TY Comdty')
    assert not is_generic_contract('TYZ9 Comdty')
    assert not is_generic_contract('TYZ19 Comdty')
    """

    raise NotImplementedError("Clipped is_generic_contract return in IMG_5784")


def is_future(ticker):
    return is_active_contract(ticker) or is_generic_contract(ticker) or is_future_contract(ticker)


def contract2active(ticker):
    ticker = bbgcase(ticker)
    if not is_future_contract(ticker):
        return ticker
    ending = BASELESS_CONTRACT.search(ticker).group(0)
    return ticker[: -len(ending)] + "A " + ending.split(" ")[-1]


def generic2active(ticker):
    ticker = bbgcase(ticker)
    if FUT1C.search(ticker) is not None or FUT0C.search(ticker) is not None:
        x = ticker.split(" ")
        x[-2] = x[-2][: -len(re.compile("[0-9]{1,2}$").search(x[-2]).group(0))] + "A"
        return " ".join(x)
    elif FUTC1.search(ticker) is not None:
        x = ticker.split(" ")
        x[-3] = x[-3] + "A"
        return " ".join(x[:-1])
    else:
        return ticker


def as_active(ticker):
    ticker = bbgcase(ticker)
    if is_active_contract(ticker):
        return ticker
    elif is_future_contract(ticker):
        return contract2active(ticker)
    elif is_generic_contract(ticker):
        return generic2active(ticker)
    elif is_spread(ticker):
        return as_active(spread_base_ticker(ticker)[0])
    else:
        raise ValueError("%s not a future ticker" % ticker)


def get_active(ticker):
    if is_spread(ticker):
        ticker_parts = ticker.split(" ")
        base_loc = -int(len(ticker_parts[0][2:]) / 2)
        return ticker_parts[0][base_loc:] + "A Comdty"
    else:
        try:
            return as_active(ticker)
        except ValueError:
            return ticker


def as_generic(ticker, contract=None):
    """
    as_generic(active = 'TYA Comdty') == 'TY Comdty'
    as_generic('TYA Comdty', 3.0) == 'TY Comdty 3'
    as_generic('L A Comdty', 2) == 'L  Comdty 2'
    as_generic(active='L A Comdty', contract=[1,2,3]) ==
    ['L  Comdty 1', 'L  Comdty 2', 'L  Comdty 3']
    """
    active = as_active(ticker)
    x = active.split()
    x[-2] = x[-2][:-1]
    if contract is None:
        return " ".join(x)
    elif is_arr(contract):
        return [" ".join(x + ["%i" % i]) for i in contract]
    else:
        return " ".join(x + ["%i" % contract])


def sprd_to_future(df, active):
    """
    convert spreads dataframe to outrights dataframe
    spreads are from the same futures
    """
    outright_dict = {}
    for col in df.columns:
        ticker1, ticker2 = spread_base_ticker(col)
        outright_dict[col] = pd.concat([df[col].to_frame(ticker1), -df[col].to_frame(ticker2)], axis=1)
    outright_df = sum_dfs(outright_dict)
    expiry = get_data("contracts", active=active, item="t")
    expiry = expiry.loc[expiry["ticker"].isin(outright_df.columns), ["ticker", "last_t"]]
    expiry.sort_values("last_t", inplace=True)
    return outright_df[expiry["ticker"]]


def flat_to_spread(ticker1, ticker2, short_ticker=True):
    """
    combine ticker1 and ticker2 to spread ticker
    """
    d1 = decompose_ticker(ticker1)
    d2 = decompose_ticker(ticker2)
    if d1["base_ticker"][-1] == " ":
        base1 = d1["base_ticker"][0] + "_"
    else:
        base1 = d1["base_ticker"]
    if d2["base_ticker"][-1] == " ":
        base2 = d2["base_ticker"][0] + "_"
    else:
        base2 = d2["base_ticker"]
    if short_ticker:
        if len(base1) == 3:
            return f"{base1}{d1['m']}{str(d1['y'])[-1:]}{d2['m']}{str(d2['y'])[-1:]} " f"{d1['asset_class']}"
        else:
            return f"{base1}{d1['m']}{str(d1['y'])[-1:]}{base2}{d2['m']}{str(d2['y'])[-1:]} " f"{d1['asset_class']}"
    else:
        return f"S:{base1}{base2} {d1['m']}{str(d1['y'])[-2:]}-{d2['m']}{str(d2['y'])[-2:]} " f"{d1['asset_class']}"


def spread_to_flat(ticker, live=True):
    """
    get tickers of two legs from spread ticker
    """
    if ticker[1] == ":":
        ticker_parts = ticker.split(" ")
        sloc = -int(len(ticker_parts[0][2:]) / 2)
        base_ticker = ticker_parts[0][sloc:]
        m1 = ticker_parts[1].split("-")[0]
        m2 = ticker_parts[1].split("-")[1]
        if live and base_ticker not in ["NG", "MO"]:
            m1 = m1[:-2] + m1[-1]
            m2 = m2[:-2] + m2[-1]
        return (
            base_ticker + m1 + " " + ticker_parts[-1],
            base_ticker + m2 + " " + ticker_parts[-1],
        )
    else:
        if ticker[:3] in ["TZT", "DAT", "QZT", "QQT", "QTT"]:
            ticker_parts = ticker.split(" ")
            return (
                ticker_parts[0][:5] + " " + ticker_parts[-1],
                ticker_parts[0][:3] + ticker_parts[0][5:7] + " " + ticker_parts[-1],
            )
        else:
            ticker_parts = ticker.split(" ")
            loc_ = int(len(ticker_parts[0]) / 2)
            return (
                ticker_parts[0][:loc_] + " " + ticker_parts[-1],
                ticker_parts[0][loc_:] + " " + ticker_parts[-1],
            )


def last_ticker(ticker, fut_gen_month="FGHJKMNQUVXZ"):
    ticker_dict = decompose_ticker(ticker)
    month = ticker_dict["m"]
    year = ticker_dict["y"]
    base_ticker = ticker_dict["base_ticker"]
    asset_class = ticker_dict["asset_class"]
    next_ticker_month = fut_gen_month[np.mod(fut_gen_month.index(month) + len(fut_gen_month) - 1, len(fut_gen_month))]
    next_ticker_year = year if fut_gen_month.index(month) - 1 >= 0 else year - 1
    if ticker_dict["base_ticker"] in ["NG", "MO"]:
        return base_ticker + next_ticker_month + str(next_ticker_year)[-2:] + " " + asset_class
    else:
        return base_ticker + next_ticker_month + str(next_ticker_year)[-1] + " " + asset_class


def next_ticker(ticker, fut_gen_month="FGHJKMNQUVXZ"):
    ticker_dict = decompose_ticker(ticker)
    month = ticker_dict["m"]
    year = ticker_dict["y"]
    base_ticker = ticker_dict["base_ticker"]
    asset_class = ticker_dict["asset_class"]
    next_ticker_month = fut_gen_month[np.mod(fut_gen_month.index(month) + 1, len(fut_gen_month))]
    next_ticker_year = year if fut_gen_month.index(month) + 1 < len(fut_gen_month) else year + 1
    if ticker_dict["base_ticker"] in ["NG", "MO", "GK", "TC5FM ", "LP", "LA"]:
        return base_ticker + next_ticker_month + str(next_ticker_year)[-2:] + " " + asset_class
    else:
        return base_ticker + next_ticker_month + str(next_ticker_year)[-1] + " " + asset_class


def convert_spread_ticker(ticker, live=True, long_to_short=True):
    """
    convert ticker format from S:COCO to COXXCOXX
    """
    ticker_parts = ticker.split(" ")
    if long_to_short:
        sloc = int(len(ticker_parts[0][2:]) / 2)
        sloc1 = -sloc * 2
        base_ticker1 = ticker_parts[0][sloc1:-sloc]
        base_ticker2 = ticker_parts[0][-sloc:]
        m1 = ticker_parts[1].split("-")[0]
        m2 = ticker_parts[1].split("-")[1]
        if live:
            m1 = m1[:-2] + m1[-1]
            m2 = m2[:-2] + m2[-1]
        return base_ticker1 + m1 + base_ticker2 + m2 + " " + ticker_parts[-1]
    else:
        sloc = int(len(ticker_parts[0]) / 2)
        ticker1 = f"{ticker_parts[0][:sloc]} {ticker_parts[1]}"
        ticker2 = f"{ticker_parts[0][-sloc:]} {ticker_parts[1]}"
        ticker_dict1 = decompose_ticker(ticker1)
        ticker_dict2 = decompose_ticker(ticker2)
        base_ticker1 = ticker_dict1["base_ticker"]
        base_ticker2 = ticker_dict2["base_ticker"]
        asset_class = ticker_dict1["asset_class"]
        month1 = ticker_dict1["m"]
        month2 = ticker_dict2["m"]
        year1 = ticker_dict1["y"]
        year2 = ticker_dict2["y"]
        return "S:{:s}{:s} {:s}{:s}-{:s}{:s} {:s}".format(
            base_ticker1,
            base_ticker2,
            month1,
            str(year1)[-2:],
            month2,
            str(year2)[-2:],
            asset_class,
        )


if __name__ == "__main__":
    c = convert_ticker("XBZ25HOZ25 Comdty")
    print(c)
    c = convert_ticker("XBZ25HO25 Comdty")

    print(c)

    c = convert_ticker("XB Comdty")

    print(c)
