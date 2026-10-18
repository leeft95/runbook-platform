from ecm.cmds.cdr import bday_adj
from ecm.cmds.cdr import today
from ecm.cmds.data import CMEBlockTrades
from ecm.cmds.sql import L025DB

ignore_products = [
    "E-mini Nasdaq-100 Options",
    "E-mini Nasdaq-100 Weekly Options - Week 2",
    "E-mini Russell 2000 Options",
    "E-mini S&P 500 EOM Options",
    "E-mini S&P 500 Monday Weekly Options - Week 1",
    "E-mini S&P 500 Monday Weekly Options - Week 2",
    "E-mini S&P 500 Monday Weekly Options - Week 3",
    "E-mini S&P 500 Options",
    "E-mini S&P 500 Thursday Weekly Options - Week 5",
    "E-mini S&P 500 Tuesday Weekly Options - Week 2",
    "E-mini S&P 500 Tuesday Weekly Options - Week 3",
    "E-mini S&P 500 Tuesday Weekly Options - Week 4",
    "E-mini S&P 500 Wednesday Weekly Options - Week 1",
    "E-mini S&P 500 Wednesday Weekly Options - Week 3",
    "E-mini S&P 500 Weekly Options - Week 1",
    "E-mini S&P 500 Weekly Options - Week 2",
    "E-mini S&P 500 Weekly Options - Week 3",
    "E-mini S&P 500 Weekly Options - Week 4",
    "S&P 500 Annual Dividend Options",
    "USD/CNH Monthly Option",
    "AUD/USD Monthly Option",
    "EUR/USD Monthly Option",
    "GBP/USD Monthly Option",
    "JPY/USD Monthly Option",
    "10-Year T-Note Options",
    "Boston CDD Index Options",
    "Options on Three-Month SOFR Futures",
]


def _agg_and_filter_to_cmdty_max(data):
    raise NotImplementedError("Unrecoverable aggregation expression: IMG_5447.JPG line 39")
    df = df.reset_index()
    df = df[~df["product"].isin(ignore_products)].rename(columns={"call_put_flag": "C/P"})
    return df


def get_block_trades(exch: str = "CME", lookback: int = -1):
    if exch == "CME":
        schema = CMEBlockTrades
    else:
        raise NotImplementedError(f"{exch} is not currently mapped")
    db = L025DB("prod")
    df = schema.load_sql(db, form="db", nullable=False)
    if lookback:
        if df.trade_date.max() == today():
            min_date = bday_adj(df.trade_date.max(), lookback - 1)
        else:
            min_date = bday_adj(df.trade_date.max(), lookback)
        df = df[(df.trade_date > min_date) & (df.trade_date < today())]
    df = _agg_and_filter_to_cmdty_max(df)
    df = df[["trade_date", "type", "product", "ticker", "side", "C/P", "strike", "size", "qty"]]
    return df


if __name__ == "__main__":
    data = get_block_trades()
    print("here")
