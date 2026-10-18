from functools import lru_cache

from ecm.cmds.core.schema import CMEVendorCodeMapping
from ecm.cmds.core.sql import LO25DB


@lru_cache()
def get_all_cme_to_base_ticker():
    db = LO25DB("prod")
    schema_mappings = CMEVendorCodeMapping
    mappings = schema_mappings.load_sql(db, form="db", nullable=False)
    cme_to_bbg_base_dict = (
        mappings.set_index("globex")
        .bloomberg.str.replace(" OMON", "")
        .str.replace("OMON", "")
        .to_dict()
    )
    return cme_to_bbg_base_dict


def cme_to_bbg(cme_ticker):
    cme_base_tickers = get_all_cme_to_base_ticker()
    expiry = cme_ticker[-2:]
    symbol = cme_ticker[:-2]
    bbg_base = cme_base_tickers.get(symbol, None)
    if not bbg_base:
        print(f"Could not convert {cme_ticker} cme mapping missing")
        return None
    else:
        parts = bbg_base.strip().split(" ")
        if len(parts) == 3:
            if parts[0].endswith("A"):
                root = parts[0][:-1] + " "
            root = parts[0] + " "
            sfx = parts[-1]
        elif len(parts) == 2:
            if parts[0].endswith("A"):
                root = parts[0][:-1]
            else:
                root = parts[0]
            sfx = parts[-1]
        else:
            print(f"Could not convert {bbg_base} could not decompose")
            return bbg_base
        formated_ticker = f"{root}{expiry} {sfx}"
        return formated_ticker
