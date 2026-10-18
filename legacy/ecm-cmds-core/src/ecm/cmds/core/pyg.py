from functools import partial

import ecm.cmds.core.config as config
import pyg_cell
from pyg_base import as_list
from pyg_base import Dict
from pyg_mongo import mongo_table

url = config.url


def bbg_db(table=None, url=url):
    """
    This manages explicitly, all the tables in our bbg database in Mongo
    """
    kw = dict(db="bbg", url=url)
    bbg = Dict()
    bbg.cal = partial(mongo_table, table="cal", pk=["code"], **kw)
    bbg.spot = partial(mongo_table, table="spot", pk=["field", "ticker"], **kw)
    bbg.contracts = partial(mongo_table, table="contracts", pk=["active", "item"], **kw)
    bbg.contracts_PX_LAST = partial(mongo_table, table="contracts_PX_LAST", pk=["active", "m", "y"], **kw)
    bbg.contracts_PX_LAST_PM = partial(mongo_table, table="contracts_PX_LAST_PM", pk=["active", "m", "y"], **kw)
    bbg.contracts_PX_OPEN = partial(mongo_table, table="contracts_PX_OPEN", pk=["active", "m", "y"], **kw)
    bbg.contracts_PX_HIGH = partial(mongo_table, table="contracts_PX_HIGH", pk=["active", "m", "y"], **kw)
    bbg.contracts_PX_LOW = partial(mongo_table, table="contracts_PX_LOW", pk=["active", "m", "y"], **kw)
    bbg.contracts_PX_VOLUME = partial(mongo_table, table="contracts_PX_VOLUME", pk=["active", "m", "y"], **kw)
    bbg.contracts_OPEN_INT = partial(mongo_table, table="contracts_OPEN_INT", pk=["active", "m", "y"], **kw)
    bbg.contracts_FAIR_VALUE_SNAPSHOT_AT_1630 = partial(mongo_table, table="contracts_FAIR_VALUE_SNAPSHOT_AT_1630", pk=["active", "m", "y"], **kw)
    bbg.spreads = partial(mongo_table, table="spreads", pk=["active", "item"], **kw)
    bbg.spreads_PX_LAST = partial(mongo_table, table="spreads_PX_LAST", pk=["active", "m", "y", "far_y", "far_m"], **kw)
    bbg.spreads_PX_OPEN = partial(mongo_table, table="spreads_PX_OPEN", pk=["active", "m", "y", "far_y", "far_m"], **kw)
    bbg.spreads_PX_HIGH = partial(mongo_table, table="spreads_PX_HIGH", pk=["active", "m", "y", "far_y", "far_m"], **kw)
    bbg.spreads_PX_LOW = partial(mongo_table, table="spreads_PX_LOW", pk=["active", "m", "y", "far_y", "far_m"], **kw)
    bbg.xspreads_PX_LAST = partial(mongo_table, table="xspreads_PX_LAST", pk=["active", "m", "y"], **kw)
    bbg.xspreads_PX_OPEN = partial(mongo_table, table="xspreads_PX_OPEN", pk=["active", "m", "y"], **kw)
    bbg.xspreads_PX_HIGH = partial(mongo_table, table="xspreads_PX_HIGH", pk=["active", "m", "y"], **kw)
    bbg.xspreads_PX_LOW = partial(mongo_table, table="xspreads_PX_LOW", pk=["active", "m", "y"], **kw)
    if table is None:
        return bbg
    else:
        return bbg[table]


def reports_db(table=None, url=url):
    """
    This manages explicitly, all the tables in reports database in Mongo
    """
    kw = dict(db="reports", url=url)
    reports = Dict()
    reports.table = partial(mongo_table, table="table", pk=["name"], **kw)
    reports.chart = partial(mongo_table, table="chart", pk=["name"], **kw)
    if table is None:
        return reports
    else:
        return reports[table]


def data_db(table=None, url=url):
    """
    This manages explicitly, all the tables in data database in Mongo
    """
    kw = dict(db="data", url=url)
    data = Dict()
    data.kpler = partial(mongo_table, table="kpler", pk=["link"], **kw)
    data.cot = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], **kw)
    data.eia_weekly = partial(mongo_table, table="eia_weekly", pk=["ticker", "name", "field"], **kw)
    data.platts = partial(mongo_table, table="platts", pk=["name", "ticker", "platts_ticker"], **kw)
    data.cfd = partial(mongo_table, table="cfd", pk=["ticker"], **kw)
    if table is None:
        return data
    else:
        return data[table]


def get_cell(table=None, db="bbg", schema=None, url=url, server=None, deleted=False, doc=None, **kwargs):
    return pyg_cell.get_cell(table=table, db=db, schema=schema, url=url, server=server, deleted=deleted, doc=doc, **kwargs)


def get_data(table=None, db="bbg", url=url, schema=None, server=None, deleted=False, doc=None, **kwargs):
    return pyg_cell.get_data(table=table, db=db, url=url, schema=schema, server=server, deleted=deleted, doc=doc, **kwargs)


def db_address(doc):
    """
    if doc is a db_cell, will return its address.
    address is used as the key for in-memory cache as well as for logging

    :Parameters:
    ----------
    doc : db_cell
        document

    :Returns:
    -------
    tuple

    :Example:
    --------
    db = partial(mongo_table, db = 'db', table = 'table', pk = ['key1', 'key2'], writer = True)
    c = db_cell(add_, a = 1, b = 2, db = db, key1 = 'hello', key2 = 'world')
    db_address(c)[1:] == ('db', 'table', ('key1', 'key2'), ('hello', 'world'))
    c = c.call()
    GRAPH[db_address(c)].data == c.a + c.b
    db().raw.drop()

    :Example: 'fake db' for logging
    --------
    c = db_cell(add_, a = 1, b = 2, db = ['key1', 'key2'], key1 = 'hello', key2 = 'world')
    db_address(c) == (None, None, None, ('key1', 'key2'), ('hello', 'world'))
    c.call().data == 3
    2021-04-11 13:41:46.135193 running...  (None, None, None, ('key1', 'key2'), ('hello', 'world'))

    c = db_cell(add_, db = ['key1', 'key2'])
    d = Dict(a = 1, b = 2, key1 = 'hello', key2 = 'world')[c]
    d.key1 == 'hello' and d.a == 1
    """
    partial_db = doc.get("db")
    if partial_db is None:
        return (None,)
    elif isinstance(partial_db, (list, str)):
        keys = tuple(sorted(as_list(partial_db)))
        address = database = collection = None
    else:
        db = partial_db()
        address = db.collection.database.client.address
        database = db.collection.database.name
        collection = db.collection.name
        keys = tuple(sorted(getattr(db, "pk", ("_id"))))
    values = [doc.get(key) for key in keys]
    values = tuple(tuple(v) if isinstance(v, list) else v for v in values)
    return (address, database, collection, keys, values)
