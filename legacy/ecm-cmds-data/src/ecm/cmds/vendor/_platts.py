import datetime as dt
import os
import typing as tp

import pandas as pd
import spgci as ci
from ecm.cmds.core.cdr import today

pwrd = os.environ["PLATTS_PASSWORD"]
username = os.environ["PLATTS_USERNAME"]


def get_market_data(
    symbols: tp.List[str],
    fields: tp.List[str] | None = None,
    start_date: dt.datetime | None = None,
    end_date: dt.datetime | None = None,
) -> pd.DataFrame:
    """
    Get historical market data from Platts
    """
    ci.set_credentials(username, pwrd)
    mdd = ci.MarketData()

    x = mdd.get_assessments_by_symbol_historical(
        symbol=symbols, bate=fields, assess_date_gte=start_date, assess_date_lte=end_date
    )
    return x


def get_platts(ticker, start_date, end_date=None):
    """
    Get simple format data from get_market_data
    """
    if end_date is None:
        end_date = today()
    df = get_market_data(ticker, fields=["c"], start_date=start_date, end_date=end_date)
    df = df[["assessDate", "value"]]
    df.set_index("assessDate", inplace=True)
    df.columns = ["PX_LAST"]
    return df


if __name__ == "__main__":
    symbols = ["PCAAS00", "PCAAT00"]
    fields = ["h", "l", "c"]
    start_date = dt.datetime(2025, 4, 1)
    end_date = dt.datetime.today()

    historical_data = get_market_data(symbols, fields, start_date, end_date)
    print(historical_data)
