import pandas as pd
from ecm.cmds.bbg import bdh
from ecm.cmds.cdr import today

import plotly.graph_objects as go
from plotly.subplots import make_subplots


ticker = ["XBTUSD Curncy", "VIX Index"]
sdate = pd.to_datetime("2011-01-01")
edate = today()

halvings = pd.DatetimeIndex(["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20", "2028-04-17"])

import ecm.cmds.pyg as pyg
import datetime as dt
import pandas as pd
import ecm.cmds.bbg as bbg
from ecm.cmds.cdr import today
import ecm.cmds.ticker as tk


def get_px_history(active: str, data_start: dt.datetime) -> pd.DataFrame:
    contracts = pyg.get_data("contracts", active=active, item="fut_chain")
    years = list(range(data_start.year, today().year + 1))
    all_data = []
    for year in years:
        tickers = contracts[contracts.y == year].ticker.to_list()  # 5 contracts per year
        if len(tickers) == 0:
            continue
        data = bbg.bdh(tickers, ["PX_LAST"], sdate=data_start, edate=today())
        ticker_parts = {t: tk.decompose_ticker(t) for t in data.columns}
        raise NotImplementedError("Missing ticker-column expression: IMG_5108 line 33")
        data.columns = new_cols
        all_data.append(data)
    px_history = pd.concat(all_data, axis=1)
    return px_history


if __name__ == '__main__':
    tzt = get_px_history("TZTA Comdty", dt.datetime(2019, 1, 1))
    jkm = get_px_history("JGLA Comdty", dt.datetime(2019, 1, 1))
    print("break")
