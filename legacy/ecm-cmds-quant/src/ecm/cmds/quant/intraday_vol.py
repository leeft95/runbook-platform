import datetime as dt

import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
import numpy as np
import pandas as pd
from ecm.cmds.cdr import today
from ecm.cmds.core.schema.intraday_vol import _gen_uid_intraday_vol
from ecm.cmds.core.schema.intraday_vol import IntradayVolTickerConfig
from ecm.cmds.core.schema.intraday_vol import IntradayVolWatchlistLive
from ecm.cmds.core.sql import L025DB
from ecm.cmds.core.utils import get_rows_to_upsert
from loguru import logger as log
from pandas.tseries.offsets import BDay

ins_dict = {
    "COA Comdty": ["OIL", [22, 23]],
    "CLA Comdty": ["OIL", [22, 23]],
    "XBA Comdty": ["OIL", [22, 23]],
    "HOA Comdty": ["OIL", [22, 23]],
    "QSA Comdty": ["OIL", [22, 23]],
    "NGA Comdty": ["GAS", [22, 23]],
    "NGVF Comdty": ["GAS", [22, 23]],
    "NGHJ Comdty": ["GAS", [22, 23]],
    "NGJV Comdty": ["GAS", [22, 23]],
    "TZTA Comdty": ["GAS", [17, 7]],
    "TZTVF Comdty": ["GAS", [17, 7]],
    "TZTHJ Comdty": ["GAS", [17, 7]],
    "TZTJV Comdty": ["GAS", [17, 7]],
    "QQT1 Comdty": ["GAS", [17, 7]],
    "QQT2 Comdty": ["GAS", [17, 7]],
    "QTTF6 Comdty": ["GAS", [17, 7]],
    "QZT1 Comdty": ["GAS", [17, 7]],
    "QZT2 Comdty": ["GAS", [17, 7]],
    "QTT2 Comdty": ["GAS", [17, 7]],
    "QTT3 Comdty": ["GAS", [17, 7]],
    "MOA Comdty": ["GAS", [17, 7]],
    "JXY1 Comdty": ["GAS", [17, 7]],
    "JXY2 Comdty": ["GAS", [17, 7]],
    "XE1 Comdty": ["GAS", [17, 7]],
    "XE2 Comdty": ["GAS", [17, 7]],
    "TM1 Comdty": ["GAS", [17, 7]],
    "XA1 Comdty": ["GAS", [17, 7]],
    "GCA Comdty": ["PM", [22, 23]],
    "SIA Comdty": ["PM", [22, 23]],
    "PLA Comdty": ["PM", [22, 23]],
    "PAA Comdty": ["PM", [22, 23]],
    "BTCA Curncy": ["MC", [22, 23]],
    "DCRA Curncy": ["MC", [22, 23]],
    "HGA Comdty": ["BM", [22, 23]],
    "LMCADS03 Comdty": ["BM", [22, 23]],
    "LMAHDS03 Comdty": ["BM", [22, 23]],
    "LMZSDS03 Comdty": ["BM", [22, 23]],
    "LMNIDS03 Comdty": ["BM", [22, 23]],
    "CUA Comdty": ["BM", [22, 23]],
    "AAA Comdty": ["BM", [22, 23]],
    "ZNAA Comdty": ["BM", [22, 23]],
    "ESA Index": ["MC", [22, 23]],
    "NQA Index": ["MC", [22, 23]],
    "NHA Index": ["MC", [22, 23]],
    "HIA Index": ["MC", [22, 23]],
    "XUA Index": ["MC", [22, 23]],
    "TYA Comdty": ["MC", [22, 23]],
    "EAA Curncy": ["MC", [22, 23]],
    "BPA Curncy": ["MC", [22, 23]],
    "ADA Curncy": ["MC", [22, 23]],
    "JYA Curncy": ["MC", [22, 23]],
    "CDA Curncy": ["MC", [22, 23]],
    "S:COCO 1-2 Comdty": ["OIL", [22, 1]],
    "S:COCO 2-3 Comdty": ["OIL", [22, 1]],
    "S:COCO 3-4 Comdty": ["OIL", [22, 1]],
    "S:COCO Jun-Dec Comdty": ["OIL", [22, 1]],
    "S:COCO Dec-Dec Comdty": ["OIL", [22, 1]],
    "S:CLCL 1-2 Comdty": ["OIL", [22, 23]],
    "S:CLCL 2-3 Comdty": ["OIL", [22, 23]],
    "S:CLCL 3-4 Comdty": ["OIL", [22, 23]],
    "S:CLCL Jun-Dec Comdty": ["OIL", [22, 23]],
    "S:CLCL Dec-Dec Comdty": ["OIL", [22, 23]],
    "S:XBXB 1-2 Comdty": ["OIL", [22, 23]],
    "S:XBXB 2-3 Comdty": ["OIL", [22, 23]],
    "S:HOHO 1-2 Comdty": ["OIL", [22, 23]],
    "S:HOHO 2-3 Comdty": ["OIL", [22, 23]],
    "S:TZTTZT 1-2 Comdty": ["GAS", [22, 23]],
    "S:TZTTZT 2-3 Comdty": ["GAS", [22, 23]],
    "S:NGNG 1-2 Comdty": ["GAS", [22, 23]],
    "S:NGNG 2-3 Comdty": ["GAS", [22, 23]],
    "S:QQTQQT 1-2 Comdty": ["GAS", [22, 23]],
    "S:QQTQQT 2-3 Comdty": ["GAS", [22, 23]],
    "S:QZTQZT 1-2 Comdty": ["GAS", [22, 23]],
    "S:QZTQZT 2-3 Comdty": ["GAS", [22, 23]],
    "S:QZTQZT 3-4 Comdty": ["GAS", [22, 23]],
    "S:QSQS 1-2 Comdty": ["OIL", [22, 23]],
    "S:QSQS 2-3 Comdty": ["OIL", [22, 23]],
    "S:QSQS 3-4 Comdty": ["OIL", [22, 23]],
    "S:QSQS Jun-Dec Comdty": ["OIL", [22, 23]],
    "S:QSQS Dec-Dec Comdty": ["OIL", [22, 23]],
    "S:DATDAT 2-3 Comdty": ["OIL", [22, 23]],
    "S:DATDAT 3-4 Comdty": ["OIL", [22, 23]],
}

NO_ROLL_TICKERS = {
    "LMCADS03 Comdty",
    "LMAHDS03 Comdty",
    "LMZSDS03 Comdty",
    "LMNIDS03 Comdty",
}


def get_gen_month(ticker):
    ticker_dict = tk.decompose_ticker(ticker)
    if ticker_dict["active"] in ["SMA Comdty", "BOA Comdty"]:
        return "FHKNZ"
    elif ticker_dict["active"] in ["S A Comdty"]:
        return "FHKNX"
    elif ticker_dict["active"] in ["GCA Comdty"]:
        return "GJMQZ"
    elif ticker_dict["active"] in ["SIA Comdty"]:
        return "HKNUZ"
    else:
        ret = bbg.bref(ticker, ["FUT_GEN_MONTH"])  # .iloc[0, 0]
        if isinstance(ret.columns, pd.MultiIndex):
            ret = ret.iloc[0, 1]
        else:
            ret = ret.iloc[0, 0]
        return ret


def get_ticker(ticker):
    active_contract = None
    last_contract = None
    roll_date = None
    if ticker in NO_ROLL_TICKERS:
        return ticker, None, None
    if ticker[:2] == "S:":
        if ticker in ["S:COCO Jun-Dec Comdty", "S:CLCL Jun-Dec Comdty", "S:QSQS Jun-Dec Comdty"]:
            base_ticker = ticker[2:4]
            ticker1 = bbg.bref(f"{base_ticker}JUN1 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(ticker1.columns, pd.MultiIndex):
                ticker1 = ticker1.iloc[0, 1]
                expiry1 = bbg.bref(ticker1 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = pd.to_datetime(expiry1.iloc[0, 1])
            else:
                ticker1 = ticker1.iloc[0, 0]
                expiry1 = bbg.bref(ticker1 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = expiry1.iloc[0, 0]
            ticker2 = bbg.bref(f"{base_ticker}DEC1 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(ticker2.columns, pd.MultiIndex):
                ticker2 = ticker2.iloc[0, 1]
                expiry2 = bbg.bref(ticker2 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry2 = pd.to_datetime(expiry2.iloc[0, 1])
            else:
                ticker2 = ticker2.iloc[0, 0]
                expiry2 = bbg.bref(ticker2 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry2 = expiry2.iloc[0, 0]
            if isinstance(expiry1, str):
                expiry1 = pd.to_datetime(expiry1)
            if isinstance(expiry2, str):
                expiry2 = pd.to_datetime(expiry2)
            if expiry1 < expiry2 and expiry1 - BDay(10) > today():
                active_contract = ticker1 + ticker2 + " Comdty"
            elif expiry1 < expiry2 and expiry1 - BDay(10) <= today():
                active_contract = f"{ticker2}{ticker1[:-1]}{int(ticker1[-1]) + 1} Comdty"
            elif expiry1 > expiry2:
                active_contract = ticker2 + ticker1 + " Comdty"
            else:
                active_contract = ticker2
        elif ticker in ["S:COCO Dec-Dec Comdty", "S:CLCL Dec-Dec Comdty", "S:QSQS Dec-Dec Comdty", "S:QQTQQT Dec-Dec Comdty"]:
            base_ticker = ticker[2:4]
            ticker1 = f"{base_ticker}DEC1 Comdty"
            sprd1 = bbg.bref(ticker1, ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(sprd1.columns, pd.MultiIndex):
                sprd1 = sprd1.iloc[0, 1]
                expiry1 = bbg.bref(sprd1 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = pd.to_datetime(expiry1.iloc[0, 1])
            else:
                sprd1 = sprd1.iloc[0, 0]
                expiry1 = bbg.bref(sprd1 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = expiry1.iloc[0, 0]
            if isinstance(expiry1, str):
                expiry1 = pd.to_datetime(expiry1)
            ticker2 = f"{base_ticker}DEC2 Comdty"
            sprd2 = bbg.bref(ticker2, ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(sprd2.columns, pd.MultiIndex):
                sprd2 = sprd2.iloc[0, 1]
            else:
                sprd2 = sprd2.iloc[0, 0]
            ticker3 = f"{base_ticker}DEC3 Comdty"
            sprd3 = bbg.bref(ticker3, ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(sprd3.columns, pd.MultiIndex):
                sprd3 = sprd3.iloc[0, 1]
            else:
                sprd3 = sprd3.iloc[0, 0]
            if expiry1 - BDay(10) <= today():
                active_contract = f"{sprd2}{sprd3} Comdty"
            else:
                active_contract = f"{sprd1}{sprd2} Comdty"
        elif ticker in ["S:COCO Dec2-Dec3 Comdty", "S:CLCL Dec2-Dec3 Comdty", "S:QSQS Dec2-Dec3 Comdty"]:
            base_ticker = ticker[2:4]
            ticker1 = f"{base_ticker}DEC2 Comdty"
            sprd1 = bbg.bref(ticker1, ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(sprd1.columns, pd.MultiIndex):
                sprd1 = sprd1.iloc[0, 1]
                expiry1 = bbg.bref(sprd1 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = pd.to_datetime(expiry1.iloc[0, 1])
            else:
                sprd1 = sprd1.iloc[0, 0]
                expiry1 = bbg.bref(sprd1 + " Comdty", ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = expiry1.iloc[0, 0]
            if isinstance(expiry1, str):
                expiry1 = pd.to_datetime(expiry1)
            ticker2 = f"{base_ticker}DEC3 Comdty"
            sprd2 = bbg.bref(ticker2, ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(sprd2.columns, pd.MultiIndex):
                sprd2 = sprd2.iloc[0, 1]
            else:
                sprd2 = sprd2.iloc[0, 0]
            ticker3 = f"{base_ticker}DEC4 Comdty"
            sprd3 = bbg.bref(ticker3, ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0]
            if isinstance(sprd3.columns, pd.MultiIndex):
                sprd3 = sprd3.iloc[0, 1]
            else:
                sprd3 = sprd3.iloc[0, 0]
            if expiry1 - BDay(10) <= today():
                active_contract = f"{sprd2}{sprd3} Comdty"
            else:
                active_contract = f"{sprd1}{sprd2} Comdty"
        elif ticker in [
            "S:QZTQZT 1-2 Comdty",
            "S:QZTQZT 2-3 Comdty",
            "S:QZTQZT 3-4 Comdty",
            "S:QQTQQT 1-2 Comdty",
            "S:QQTQQT 2-3 Comdty",
            "S:TZTTZT 1-2 Comdty",
            "S:QQTQQT Jun-Dec Comdty",
            "S:QQTQQT Dec-Dec Comdty",
        ]:
            ticker_parts = ticker.split(" ")
            base_ticker = ticker_parts[0][-int(len(ticker_parts[0][2:]) / 2) :]
            gen_sprd = bbg.bref(ticker, ["GENERIC_SPREAD_TICKER_EXTENSION"])
            if isinstance(gen_sprd.columns, pd.MultiIndex):
                month_list = gen_sprd.iloc[0, 1].split("-")
            else:
                month_list = gen_sprd.iloc[0, 0].split("-")
            active_contract = base_ticker + month_list[0][0] + month_list[0][-1] + month_list[1][0] + month_list[1][-1] + " Comdty"
        else:
            raise NotImplementedError("Unrecoverable spread classification lists: IMG_5490 lines 190, 220")
            sprd_ticker = bbg.bref(ticker, ["GENERIC_SPREAD_TICKER_EXTENSION"])  # .iloc[0, 0]
            if isinstance(sprd_ticker.columns, pd.MultiIndex):
                sprd_ticker = sprd_ticker.iloc[0, 1]
            else:
                sprd_ticker = sprd_ticker.iloc[0, 0]
            sprd_ticker = f"{ticker.split(' ')[0]} {sprd_ticker} {ticker.split(' ')[-1]}"
            expiry = bbg.bref(sprd_ticker, ["LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST"])
            expiry = expiry.min(axis=1).values[0]
            if isinstance(expiry, str):
                expiry = pd.to_datetime(expiry)
            if not isinstance(expiry, dt.date) and not isinstance(expiry, np.datetime64):
                expiry = dt.datetime(2023, 1, 1)
            if expiry - BDay(3) <= today():
                next_ticker = f"{ticker.split(' ')[0]} 2-3 {ticker.split(' ')[-1]}"
                next_sprd = bbg.bref(next_ticker, ["GENERIC_SPREAD_TICKER_EXTENSION"])  # .iloc[0, 0]
                if isinstance(next_sprd.columns, pd.MultiIndex):
                    next_sprd = next_sprd.iloc[0, 1]
                else:
                    next_sprd = next_sprd.iloc[0, 0]
                active_contract = f"{ticker.split(' ')[0]} {next_sprd} {ticker.split(' ')[-1]}"
                last_contract = sprd_ticker
                roll_date = expiry - BDay(3)
            else:
                active_contract = sprd_ticker
                sprd1 = tk.spread_base_ticker(sprd_ticker)[0]
                gen_month = get_gen_month(sprd1)
                sprd0 = tk.last_ticker(sprd1, gen_month)
                if sprd1[:2] in ["NG", "MO"]:
                    last_contract = f"{sprd0[:3]}{sprd0[4]}{sprd1[:3]}{sprd1[4]} Comdty"
                else:
                    last_contract = f"{sprd0.split(' ')[0]}{sprd1}"
                expiry = bbg.bref(sprd0, ["LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST"])
                expiry = expiry.min(axis=1).values[0]
                if isinstance(expiry, str):
                    expiry = pd.to_datetime(expiry)
                roll_date = expiry - BDay(3)
            active_contract = tk.convert_spread_ticker(active_contract, live=True)
    else:
        if ticker in ["NGVF Comdty", "NGHJ Comdty", "NGJV Comdty"]:
            m1 = dt.datetime(2024, tk.month_str2int[ticker[2]], 1).strftime("%b").upper()
            m2 = dt.datetime(2024, tk.month_str2int[ticker[3]], 1).strftime("%b").upper()
            ticker1 = bbg.bref(f"NG{m1}1 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            ticker1_ = bbg.bref(f"NG{m1}2 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            if isinstance(ticker1.columns, pd.MultiIndex):
                ticker1 = ticker1.iloc[0, 1] + " Comdty"
                ticker1_ = ticker1_.iloc[0, 1] + " Comdty"
                expiry1 = bbg.bref(ticker1, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = pd.to_datetime(expiry1.iloc[0, 1])
            else:
                ticker1 = ticker1.iloc[0, 0] + " Comdty"
                ticker1_ = ticker1_.iloc[0, 0] + " Comdty"
                expiry1 = bbg.bref(ticker1, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = expiry1.iloc[0, 0]

            ticker2 = bbg.bref(f"NG{m2}1 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            ticker2_ = bbg.bref(f"NG{m2}2 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            if isinstance(ticker2.columns, pd.MultiIndex):
                ticker2 = ticker2.iloc[0, 1] + " Comdty"
                ticker2_ = ticker2_.iloc[0, 1] + " Comdty"
                expiry2 = bbg.bref(ticker2, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry2 = pd.to_datetime(expiry2.iloc[0, 1])
            else:
                ticker2 = ticker2.iloc[0, 0] + " Comdty"
                ticker2_ = ticker2_.iloc[0, 0] + " Comdty"
                expiry2 = bbg.bref(ticker2, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry2 = expiry2.iloc[0, 0]
            if isinstance(expiry1, str):
                expiry1 = pd.to_datetime(expiry1)
            if isinstance(expiry2, str):
                expiry2 = pd.to_datetime(expiry2)
            if expiry1 < expiry2 and expiry1 - BDay(3) > today():
                active_contract = tk.flat_to_spread(ticker1, ticker2)
            elif expiry1 < expiry2 and expiry1 - BDay(3) <= today():
                active_contract = tk.flat_to_spread(ticker1_, ticker2_)
            else:
                active_contract = tk.flat_to_spread(ticker1, ticker2_)
        elif ticker in ["TZTVF Comdty", "TZTHJ Comdty", "TZTJV Comdty"]:
            m1 = dt.datetime(2024, tk.month_str2int[ticker[3]], 1).strftime("%b").upper()
            m2 = dt.datetime(2024, tk.month_str2int[ticker[4]], 1).strftime("%b").upper()
            ticker1 = bbg.bref(f"TZT{m1}1 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            ticker1_ = bbg.bref(f"TZT{m1}2 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            if isinstance(ticker1.columns, pd.MultiIndex):
                ticker1 = ticker1.iloc[0, 1] + " Comdty"
                ticker1_ = ticker1_.iloc[0, 1] + " Comdty"
                expiry1 = bbg.bref(ticker1, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = pd.to_datetime(expiry1.iloc[0, 1])
            else:
                ticker1 = ticker1.iloc[0, 0] + " Comdty"
                ticker1_ = ticker1_.iloc[0, 0] + " Comdty"
                expiry1 = bbg.bref(ticker1, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry1 = expiry1.iloc[0, 0]

            ticker2 = bbg.bref(f"TZT{m2}1 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            ticker2_ = bbg.bref(f"TZT{m2}2 Comdty", ["FUT_CUR_GEN_TICKER"])  # .iloc[0, 0] + ' Comdty'
            if isinstance(ticker2.columns, pd.MultiIndex):
                ticker2 = ticker2.iloc[0, 1] + " Comdty"
                ticker2_ = ticker2_.iloc[0, 1] + " Comdty"
                expiry2 = bbg.bref(ticker2, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry2 = pd.to_datetime(expiry2.iloc[0, 1])
            else:
                ticker2 = ticker2.iloc[0, 0] + " Comdty"
                ticker2_ = ticker2_.iloc[0, 0] + " Comdty"
                expiry2 = bbg.bref(ticker2, ["LAST_TRADEABLE_DT"])  # .iloc[0, 0]
                expiry2 = expiry2.iloc[0, 0]
            if isinstance(expiry1, str):
                expiry1 = pd.to_datetime(expiry1)
            if isinstance(expiry2, str):
                expiry2 = pd.to_datetime(expiry2)
            if expiry1 < expiry2 and expiry1 - BDay(3) > today():
                active_contract = tk.flat_to_spread(ticker1, ticker2)
            elif expiry1 < expiry2 and expiry1 - BDay(3) <= today():
                active_contract = tk.flat_to_spread(ticker1_, ticker2_)
            else:
                active_contract = tk.flat_to_spread(ticker1, ticker2_)
        elif ticker == "QTTF6 Comdty":
            active_contract = ticker
        else:
            if ticker[:3] in ["QQT", "QZT", "QTT", "JXY"] or ticker[:2] in ["XE", "XA"]:
                flat_ticker = bbg.bref(ticker, ["FUT_CUR_GEN_TICKER"])
            else:
                flat_ticker = bbg.bref(ticker, ["TICKER"])
            if isinstance(flat_ticker.columns, pd.MultiIndex):
                flat_ticker = flat_ticker.iloc[0, 1] + " " + ticker.rpartition(" ")[-1]
            else:
                flat_ticker = flat_ticker.iloc[0, 0] + " " + ticker.rpartition(" ")[-1]
            expiry = bbg.bref(flat_ticker, ["LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST"])
            expiry = expiry.min(axis=1).values[0]
            if isinstance(expiry, str):
                expiry = pd.to_datetime(expiry)
            if expiry - BDay(3) <= today():
                gen_month = get_gen_month(flat_ticker)
                active_contract = tk.next_ticker(flat_ticker, gen_month)
                last_contract = flat_ticker
                roll_date = expiry - BDay(3)
            else:
                active_contract = flat_ticker
                if flat_ticker[:2] in ["MO", "TM", "XA"]:
                    last_contract = None
                    roll_date = None
                else:
                    gen_month = get_gen_month(flat_ticker)
                    last_contract = tk.last_ticker(flat_ticker, gen_month)
                    expiry = bbg.bref(last_contract, ["LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST"])
                    expiry = expiry.min(axis=1).values[0]
                    if isinstance(expiry, str):
                        expiry = pd.to_datetime(expiry)
                    roll_date = expiry - BDay(3)
    log.info(f"Resolved {ticker}: {active_contract}, last: {last_contract}, roll: {roll_date}")
    return active_contract, last_contract, roll_date


def _build_base_config_frame(source_dict: dict) -> pd.DataFrame:
    """Create a DataFrame suitable for IntradayVolTickerConfig from raw ins_dict-like mapping.

    source_dict structure: { generic_ticker: [asset_class, [h1, h2]] }
    hidden_hours stored as 'HH-HH'. enabled/use_bbg default values.
    """
    rows = []
    for generic_ticker, (asset_class, hours) in source_dict.items():
        if not isinstance(hours, (list, tuple)) or len(hours) != 2:
            log.warning(f"Invalid hours for {generic_ticker}: {hours}; skipping")
            continue
        hidden_hours = f"{int(hours[0]):02d}-{int(hours[1]):02d}"
        uid = _gen_uid_intraday_vol(generic_ticker, asset_class)
        rows.append(
            dict(
                uid=uid,
                generic_ticker=generic_ticker,
                asset_class=asset_class,
                hidden_hours=hidden_hours,
                enabled=True,
            )
        )
    return pd.DataFrame(rows)


def get_latest_config(ticker_config=None, env: str = "prod", update: bool = False) -> dict:
    """Load latest intraday vol config from DB, optionally seeding/updating from a dict.

    Returns mapping: (asset_class, generic_ticker) -> (asset_class, generic_ticker, [h1, h2])

    Behaviors:
      * If DB is empty OR update=True (with no explicit ticker_config), seed from module ins_dict.
      * If ticker_config is provided (same shape as ins_dict), use it to seed/update DB when update=True.
      * hidden_hours in DB stored as 'HH-HH', converted back to list[int,int].
    """
    schema = IntradayVolTickerConfig
    db = L025DB(env)

    data = schema.load_sql(db, form="db")

    seed_source = None
    if ticker_config is not None:
        seed_source = ticker_config
    elif (data.empty) or update:
        seed_source = ins_dict

    if seed_source is not None:
        frame = _build_base_config_frame(seed_source)
        if not frame.empty:
            log.info("Seeding / updating IntradayVolTickerConfig table")
            schema(frame).dump_sql(db, form="db", mode="update_first")
            data = schema.load_sql(db, form="db")

    if data.empty:
        log.warning("IntradayVolTickerConfig still empty; using in-memory ins_dict only")
        source = ins_dict
        formatted = {}
        for generic_ticker, (asset_class, hours) in source.items():
            formatted[(asset_class, generic_ticker)] = (asset_class, generic_ticker, hours)
        return formatted

    df = data.reset_index()  # ensure columns accessible
    required_cols = {"asset_class", "generic_ticker", "hidden_hours"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"IntradayVolTickerConfig missing expected columns: {missing}")
    config = {}
    for _, row in df.iterrows():
        hh = row.hidden_hours
        try:
            parts = [int(p) for p in str(hh).split("-")[:2]]
            if len(parts) != 2:
                raise ValueError
        except Exception:
            log.warning(f"Bad hidden_hours format '{hh}' for {row.generic_ticker}; defaulting to [22,23]")
            parts = [22, 23]
        config[(row.asset_class, row.generic_ticker)] = (row.asset_class, row.generic_ticker, parts)
    return config


def get_ticker_dict(ticker_config=None, force_update: bool = False, env: str = "prod") -> dict:
    """Build a runtime ticker dictionary including active/last contracts.

    For each generic ticker in the (asset_class, generic_ticker) config, we
    resolve the current active_contract using the bespoke ``get_ticker`` logic
    in this module (which handles spreads, roll windows, seasonal structures,
    etc.).

    Returned dict shape:
        { (asset_class, generic_ticker): {
              'generic_ticker': str,
              'active_contract': str,
              'last_contract': Optional[str],
              'roll_date': Optional[pd.Timestamp],
              'hours': List[int]
          }
        }

    Notes
    -----
    * force_update=True will always resolve tickers from Bloomberg.
    * If force_update=False, checks watchlist update_time and only resolves if last update was not today.
    * roll_date is normalized to pd.Timestamp when available.
    * Any resolution errors are logged and the entry is skipped.
    """
    db = L025DB(env)
    cfg = get_latest_config(ticker_config=ticker_config, env=env, update=force_update)

    needs_ticker_resolution = force_update
    if not force_update:
        try:
            existing_watchlist = IntradayVolWatchlistLive.load_sql(db, form="db", nullable=False)
            if not existing_watchlist.empty and "update_time" in existing_watchlist.columns:
                last_update = pd.to_datetime(existing_watchlist["update_time"].max())
                today_date = pd.Timestamp.now().normalize()
                if last_update >= today_date:
                    log.info(f"Watchlist already updated today ({last_update}), using cached tickers")
                    needs_ticker_resolution = False
                else:
                    log.info(f"Watchlist last updated {last_update}, resolving fresh tickers")
                    needs_ticker_resolution = True
            else:
                log.info("Watchlist empty or missing update_time, resolving fresh tickers")
                needs_ticker_resolution = True
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Failed to check watchlist update time: {exc}, resolving fresh tickers")
            needs_ticker_resolution = True

    ticker_dict = {}

    if needs_ticker_resolution:
        for (asset_class, generic_ticker), (_asset_class, _gen, hours) in cfg.items():
            try:
                active_contract, last_contract, roll_date = get_ticker(generic_ticker)
                if roll_date is not None and not isinstance(roll_date, (pd.Timestamp, dt.datetime)):
                    try:
                        roll_date = pd.to_datetime(roll_date)
                    except Exception:  # noqa: BLE001
                        roll_date = None
                ticker_dict[(asset_class, generic_ticker)] = {
                    "generic_ticker": generic_ticker,
                    "active_contract": active_contract,
                    "last_contract": last_contract,
                    "roll_date": roll_date,
                    "hours": hours,
                }
            except Exception as exc:  # noqa: BLE001
                log.warning(f"Failed to resolve active contract for {generic_ticker}: {exc}")
                continue
        update_watchlist(latest_config=ticker_dict, env=env)
    else:
        try:
            existing_watchlist = IntradayVolWatchlistLive.load_sql(db, form="db", nullable=False)
            if existing_watchlist.empty:
                raise ValueError("Watchlist is empty")
            else:
                log.info("Loading tickers from cached watchlist")
                existing_watchlist = existing_watchlist.reset_index()

            for _, row in existing_watchlist.iterrows():
                asset_class = row["asset_class"]
                generic_ticker = row["generic_ticker"]
                hours = cfg.get((asset_class, generic_ticker), (None, None, [22, 23]))[2]

                last_contract = row.get("last_contract", None) if "last_contract" in row.index else None
                roll_date = row.get("roll_date", None) if "roll_date" in row.index else None

                if roll_date is not None and not pd.isna(roll_date):
                    try:
                        roll_date = pd.to_datetime(roll_date)
                    except Exception:  # noqa: BLE001
                        roll_date = None

                ticker_dict[(asset_class, generic_ticker)] = {
                    "generic_ticker": generic_ticker,
                    "active_contract": row["ticker"],
                    "last_contract": last_contract,
                    "roll_date": roll_date,
                    "hours": hours,
                }
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Failed to load cached watchlist: {exc}, falling back to fresh resolution")
            for (asset_class, generic_ticker), (_asset_class, _gen, hours) in cfg.items():
                try:
                    active_contract, last_contract, roll_date = get_ticker(generic_ticker)
                    if roll_date is not None and not isinstance(roll_date, (pd.Timestamp, dt.datetime)):
                        try:
                            roll_date = pd.to_datetime(roll_date)
                        except Exception:  # noqa: BLE001
                            roll_date = None
                    ticker_dict[(asset_class, generic_ticker)] = {
                        "generic_ticker": generic_ticker,
                        "active_contract": active_contract,
                        "last_contract": last_contract,
                        "roll_date": roll_date,
                        "hours": hours,
                    }
                except Exception as exc_inner:  # noqa: BLE001
                    log.warning(f"Failed to resolve active contract for {generic_ticker}: {exc_inner}")
                    continue
            update_watchlist(latest_config=ticker_dict, env=env)

    return ticker_dict


def update_watchlist(latest_config=None, env="prod"):
    db = L025DB(env)
    config_df = IntradayVolTickerConfig.load_sql(db, form="db", nullable=False)
    config_df = config_df.reset_index().set_index("uid")
    if latest_config is None:
        latest_config = get_ticker_dict(env=env)
    latest_config_df = pd.DataFrame(latest_config).T
    latest_config_df.index.names = ["asset_class", "generic_ticker"]
    latest_config_df = latest_config_df.drop(columns=["generic_ticker"]).reset_index()
    watchlist_row = []
    for _, row in latest_config_df.iterrows():
        now_ts = pd.Timestamp.utcnow().replace(tzinfo=None, microsecond=0).to_pydatetime()
        asset_class = row.asset_class
        generic_ticker = row.generic_ticker
        ticker = row.active_contract
        last_contract = row.get("last_contract", None)
        roll_date = row.get("roll_date", None)

        if roll_date is not None and isinstance(roll_date, pd.Timestamp):
            roll_date = roll_date.to_pydatetime()

        uid = _gen_uid_intraday_vol(generic_ticker, asset_class)
        if isinstance(config_df.loc[uid].enabled, pd.Series):
            enabled = config_df.loc[uid].enabled.drop_duplicates().values[0]
        else:
            enabled = config_df.loc[uid].enabled
        watchlist_row.append(
            dict(
                uid=uid,
                asset_class=asset_class,
                generic_ticker=generic_ticker,
                ticker=ticker,
                last_contract=last_contract,
                roll_date=roll_date,
                enabled=bool(enabled),
                update_time=now_ts,
            )
        )
    update_df = pd.DataFrame(watchlist_row)
    if not update_df.empty:
        update_df["enabled"] = update_df["enabled"].map(bool)
        update_df["update_time"] = update_df["update_time"].apply(lambda x: x.to_pydatetime() if isinstance(x, pd.Timestamp) else x)
        new_df = IntradayVolWatchlistLive(update_df, nullable=False)
        existing_watchlist = IntradayVolWatchlistLive.load_sql(db, form="db", nullable=False)

        existing_watchlist_compare = existing_watchlist.copy()
        new_df_compare = new_df.copy()

        raise NotImplementedError("Missing watchlist comparison arguments: IMG_5498 line 690")
        if not upsert_df.empty:
            updated_rows = upsert_df[upsert_df.update_type == "updated"]
            new_rows = upsert_df[upsert_df.update_type == "new"]
            if not updated_rows.empty:
                log.info(f"Updating {len(updated_rows)} existing rows in IntradayVolWatchlist")
                updated_watchlist = updated_rows.drop(columns="update_type")
                IntradayVolWatchlistLive(updated_watchlist, nullable=False).dump_sql(db, form="db", mode="update_only")
            elif not new_rows.empty:
                log.info(f"Inserting {len(new_rows)} new rows to IntradayVolWatchlist")
                new_watchlist = new_rows.drop(columns="update_type")
                IntradayVolWatchlistLive(new_watchlist, nullable=False).dump_sql(db, form="db", mode="insert_first")
            else:
                log.info("No changes to IntradayVolWatchlist")
        else:
            log.info("No rows to upsert to IntradayVolWatchlist")
    else:
        log.warning("No data to update IntradayVolWatchlist")


if __name__ == "__main__":
    ticker_dict = get_ticker_dict(env="prod", force_update=True)
    print("break")
