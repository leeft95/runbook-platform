import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
import pandas as pd
import json

historical_tickers = [
    "CWRA Comdty", "AGOA Comdty", "JWLA Comdty", "QIAA Comdty", "ANDA Comdty",
    "ABYA Comdty", "AJPA Comdty", "ALYA Comdty", "WATA Comdty", "ATDA Comdty",
    "AMYA Comdty", "QJBA Comdty", "ANPA Comdty", "CJLA Comdty", "WHCA Comdty",
    "HRTA Comdty", "UDSA Comdty", "WUA Comdty", "YVAA Comdty", "TUSA Comdty",
    "WRA Comdty", "VPA Comdty", "OOPA Comdty", "OYA Comdty", "HOBA Comdty",
    "BTWA Comdty", "MKEA Comdty", "ACEA Comdty",
]
daily_tickers = [
    'HPYA Comdty', 'ASYA Comdty', 'BOPA Comdty', 'CAAA Comdty', 'AQBA Comdty', 'BOPA Comdty',
    'SMOA Comdty', 'CAEA Comdty', 'HXYA Comdty', 'CWBA Comdty', 'AAWA Comdty', 'SDEA Comdty', 'JCWA Comdty',
    'WAYA Comdty', 'HPWA Comdty', 'ATEA Comdty', 'HYIA Comdty', 'BOAA Comdty', 'ATCA Comdty', 'WWDA Comdty',
    'WKRA Comdty', 'ATOA Comdty', 'AWBA Comdty', 'AGDA Comdty', 'CCOA Comdty', 'MCTA Comdty', 'AKCA Comdty',
    'CXEA Comdty', 'PGA Comdty', 'AFYA Comdty', 'BGLA Comdty', 'AWOA Comdty', 'AZBA Comdty', 'PTLA Comdty',
]

all_daily_tickers = historical_tickers + daily_tickers


def generate():
    full_tickers_historical = pd.read_csv(r"c:\dev\L025\TEMP\loic_backfill_tickers.csv").ticker
    fields = ["PX_LAST"]
    out_list = []
    for ticker in full_tickers_historical:
        d = {"ticker": ticker, "history_fields": fields}
        out_list.append(d)
    with open(r"c:\dev\L025\TEMP\loic_backfill_tickers.txt", "w+") as f:
        json.dump(out_list, f)
    print("break")


if __name__ == "__main__":
    generate()
