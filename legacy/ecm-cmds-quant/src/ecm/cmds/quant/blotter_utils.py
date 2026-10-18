import datetime as dtm

import pandas as pd
from ecm.atom.schema import ECMSchema
from ecm.atom.schema import field
from ecm.cmds.core.bbg import bdh
from ecm.cmds.core.pyg import get_data
from ecm.cmds.core.sql import L025DB
from ecm.cmds.core.ticker import as_active
from ecm.cmds.core.ticker import as_generic
from ecm.cmds.core.ticker import spread_to_flat
from loguru import logger as log


class BoltterFuturesTradeCost(ECMSchema):
    Market: str = field(index=0)
    TradeType: str = field(index=1)
    Unit: str = field()
    Value: float = field()


def get_futures_trade_cost(market: str, spread: bool = False, env: str = "dev"):
    cursor = L025DB(env)
    schema = BoltterFuturesTradeCost
    data = schema.load_sql(source=cursor, nullable=False).applymap(lambda x: x.strip() if isinstance(x, str) else x)
    trade_type = "Spread" if spread else "Outright"
    try:
        mkt_data = data.loc[(market, trade_type)].to_dict()
    except KeyError:
        log.warning(f"Market: {market}|{trade_type} is not in BlotterFuturesCostDB inserting defaults")
        insert_futures_trade_cost(market=market, spread=spread, env=env)
        mkt_data = get_futures_trade_cost(market=market, spread=spread)
    return mkt_data


def insert_futures_trade_cost(market: str, cost: float | None = None, spread: bool = False, env: str = "dev"):
    cursor = L025DB(env)
    unit = "tk" if spread else "bps"
    trade_type = "Spread" if spread else "Outright"
    if cost is None:
        if spread:
            cost = 0.5
        else:
            cost = 5
    df = pd.DataFrame(dict(Market=market, TradeType=trade_type, Unit=unit, Value=cost), index=[0]).set_index(["Market", "TradeType"])
    schema = BoltterFuturesTradeCost(df)
    schema.dump_sql(db=cursor)


def _get_settle_px(ticker: str, date: dtm.datetime):
    px = bdh(ticker, fields=["PX_SETTLE"], sdate=date, edate=date)
    if px.empty:
        return 0
    else:
        return px.iloc[0, 0]


def _trade_row_to_blotter_row(
    row: pd.Series,
    static_data: dict,
    spread: bool = False,
    env: str = "dev",
    counterparty: str = "AMT",
):
    bookings = []
    ticker, pos_date = row.name
    pos_date = pd.to_datetime(pos_date)
    generic_ticker = as_generic(ticker) if not spread else as_generic(spread_to_flat(ticker)[0])
    cost_unit, cost = get_futures_trade_cost(generic_ticker, spread=spread, env=env).values()
    settle_px = _get_settle_px(ticker, pos_date)
    if cost_unit == "bps":
        scaled_cost = cost * 0.0001 * settle_px
    elif cost_unit == "tk":
        tick_value = get_data("contracts", active=as_active(ticker), item="ref").get("FUT_TICK_SIZE", None)
        if not tick_value:
            raise ValueError(f"Tick Value for {ticker} is missing")
        scaled_cost = cost * tick_value
    else:
        log.warning(f"Could not scale the price appropriately for {ticker}|{pos_date}" f" as cost_unit is {cost_unit}")
        scaled_cost = 0
    scaled_cost = -1 * scaled_cost if row.sum() < 0 else scaled_cost
    price = settle_px + scaled_cost
    row = row[row != 0]
    for k, v in row.items():
        booking = dict.fromkeys(["BS", "Notional", "Counterparty", "Product", "SubStrategy", "Price"], None)
        booking.update(Product=ticker, SubStrategy=k, Price=price)
        if k == row.keys()[-1]:
            num = row.sum()
            booking.update(Counterparty=counterparty, Notional=abs(num))
            if num > 0:
                log.debug(f"Is Buy {num} | {k} | AMT")
                booking.update(BS="Buy")
            elif num < 0:
                log.debug(f"Is Sell {num} | {k} | AMT")
                booking.update(BS="Sell")
            else:
                raise ValueError(f"Could not determine side for {k}")
        else:
            booking.update(Counterparty=f"PD,L025,SYS,{k}", Notional=abs(v))
            if v > 0:
                booking.update(BS="Buy")
                log.debug(f"Is Buy {v} | {k} | PD,L025,SYS,{k}")
            elif v < 0:
                booking.update(BS="Sell")
                log.debug(f"Is Sell {v} | {k} | PD,L025,SYS,{k}")
            else:
                continue
        booking.update(**static_data)
        bookings.append(booking)
    return bookings


def convert_trades_to_blotter(send_to_trade: pd.DataFrame, spread: bool = False, env: str = "dev", counterparty: str = "AMT"):
    """Takes an trades positon table of the format as below and generates a blotter compatible table

        BS  Num     Contract PositionDate  DOE-FP  PLATTS-SG  SPRD26
    0 Sell  -18   CLK4 COMDTY   2024-02-21     0.0      -28.0    10.0
    1 Sell  -22   CLM4 COMDTY   2024-02-21   -22.0        0.0     0.0
    2  Buy   17   COK4 COMDTY   2024-02-21     0.0      -32.0    49.0
    3 Sell  -23   COM4 COMDTY   2024-02-21   -23.0        0.0     0.0
    4  Buy   33  NGJ24 COMDTY   2024-02-21    33.0        0.0     0.0

    Args:
        send_to_trade (pd.DataFrame): trade positions table that goes to broker
        spread (bool, optional): If the Trade positions are spreads. Defaults to False.
        env (str, optional): What DB env to use when obtaining the trade cost. Defaults to "dev".

    Returns:
        pd.DataFrame: Blotter Compatible dataframe
    """
    blotter_rows = []
    blotter_columns = [
        "Strategy", "SubStrategy", "BS", "Notional", "CCY", "Trade Type", "Product",
        "CP", "Expiry", "Strike", "Swap Start", "Swap End", "Price", "Counterparty",
        "Comments", "Execution Factor", "Phone",
    ]
    for (ticker, _), row in send_to_trade.drop(columns=["BS", "Num"]).set_index(["Contract", "PositionDate"]).iterrows():
        ticker_meta = get_data("contracts", active=as_active(ticker), item="ref")
        static_data = {
            "CCY": ticker_meta.get("CURRENCY", "USD"),
            "Strategy": "SYS",
            "Trade Type": "Future",
            "Execution Factor": "MOC",
            "Phone": "N",
        }
        booking = _trade_row_to_blotter_row(row, static_data, spread=spread, env=env, counterparty=counterparty)
        blotter_rows.append(pd.DataFrame(booking))
    blotter_df = pd.concat(blotter_rows)
    missing_columns = [x for x in blotter_columns if x not in blotter_df.columns]
    blotter_df[missing_columns] = None
    return blotter_df[blotter_columns].reset_index(drop=True)
