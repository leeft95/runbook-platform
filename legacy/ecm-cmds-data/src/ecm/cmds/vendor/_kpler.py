from functools import partial
from functools import reduce

import ecm.cmds.core.cdr as cdr
import ecm.cmds.core.pyg as pyg
import ecm.cmds.vendor._data as data
import pandas as pd
from ecm.cmds.core.config import url
from pyg_base import dt as pygdt
from pyg_cell import periodic_cell
from pyg_mongo import mongo_table


def kpler_cell(link, period="0b"):
    """
    Create cell in mongodb that has raw data from kpler link
    Delete cell if already exists
    Kpler link cannot have space
    """
    db = partial(mongo_table, table="kpler", pk=["link"], db="data", url=url)
    try:
        c = pyg.get_cell(db, link=link)
        db().inc(link=c.link).drop()
    except Exception:
        pass
    periodic_cell(
        function=data.kpler,
        db=db,
        link=link,
        period=period,
    ).go()


def convert_to_ts(
    kpler_links, columns=None, rename=None, drop_column=None, forecast=False, end_dt=None
):
    """
    Convert Kpler raw data to time series
    kpler_links: one cell or list of cells
    columns: columns to keep
    rename: dict, e.g. {old column: new column}
    drop_column: list, columns to drop
    forecast: if False, data is up to today
    Example:
        db = partial(mongo_table, table="kpler", pk=["link"], db="data", url=url)
        c1 = pyg.get_cell(db,
                         link="/v1/flows?fromZones=China,Saudi%20Arabia,United%20Arab%20Emirates
                         &products=Clean%20Products&flowDirection=NetExport&
                         split=Origin%20Countries&granularity=daily&onlyRealized=true&
                         startDate=2016-01-01&unit=kb")
        c2 = pyg.get_cell(db,
                         link="/v1/flows?fromZones=India,South%20Korea,Kuwait&
                         products=Clean%20Products&flowDirection=Export&split=Origin%20Countries&
                         granularity=daily&onlyRealized=true&startDate=2016-01-01&unit=kb")
        df = convert_to_ts([c1.data, c2.data],
                           columns=['Saudi Arabia', 'Kuwait', 'UAE', 'China',
                                    'India', 'South Korea'],
                           rename={'United Arab Emirates': 'UAE'},
                           drop_column=None,
                           end_dt="-1d",
                           forecast=False)
        print(df)
    """

    if isinstance(kpler_links, list):
        for i in kpler_links:
            if " Date" in i.columns or "  Date" in i.columns:
                i.rename(columns={" Date": "Date"}, inplace=True)
        df_ = reduce(lambda x, y: pd.merge(x, y, on=["Date", "Period End Date"]), kpler_links)
    else:
        if " Date" in kpler_links.columns or "  Date" in kpler_links.columns:
            kpler_links.rename(columns={" Date": "Date"}, inplace=True)
        df_ = kpler_links
    df = df_.copy()
    if "error" in df.columns[0]:
        raise ValueError(f"Kepler Service Error:>> {df.columns[0]}")
    df = df.set_index("Date")
    df.index = pd.to_datetime(df.index)
    if not forecast:
        df = df.loc[df.index <= cdr.today(), :]
    if "Period End Date" in df.columns:
        df.drop("Period End Date", axis=1, inplace=True)
    if rename is not None:
        df.rename(columns=rename, inplace=True)
    if drop_column is not None:
        df.drop(drop_column, axis=1, inplace=True)
    if columns is not None:
        df = df[columns]
    if end_dt is not None:
        df = df.loc[df.index <= pygdt(end_dt)]
    return df
