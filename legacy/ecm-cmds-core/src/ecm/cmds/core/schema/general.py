import numpy as np
from ecm.atom.schema import ECMSchema
from ecm.atom.schema import field


class StormVistaGlobalActuals(ECMSchema, db="dbo.CWG_StormVista_Global_Actuals"):  # type: ignore
    Date: np.datetime64 = field(index=0)
    Field: str = field(index=1)
    Region: str = field(index=2)
    Value: float


class CMEBlockTrades(ECMSchema, raw="csv", db="dbo.CME_block_trades"):  # type: ignore
    trade_date: np.datetime64 = field(index=0)
    symbol: str = field(index=1, raw="Sym")
    ticker: str = field(raw="Ticker")
    product: str = field(index=2, raw="Product")
    type: str = field(index=3, raw="Product_Type")
    strike: int = field(index=4)
    call_put_flag: str = field(index=5)
    side: str = field(index=6, raw="Side")
    ratio: int = field(index=7, raw="Ratio")
    price: float = field(index=8, raw="Price")
    net_price: float = field(index=9, raw="Net_Price")
    size: int = field(raw="Size")
    qty: int = field(raw="Qty")


class CMEVendorCodeMapping(ECMSchema, raw="csv", db="dbo.CME_vendor_code_mappings"):  # type: ignore
    product_name: str = field(index=1)
    type: str = field(index=2)
    globex: str
    clearport: str
    bloomberg: str
    refinitv: str
