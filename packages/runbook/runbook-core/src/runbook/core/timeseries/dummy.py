"""Module to generate dummy time series data"""

import datetime as dt
import typing as tp

import pandas as pd
from isoweek import Week
from pandas import DateOffset


def generate_dwmy_ref_df(
    start_date: str | dt.datetime | None,
    end_date: str | dt.datetime | None,
    m1_offset: int | None = None,
    m2_offset: int | None = None,
) -> pd.DataFrame:
    """
    Generate a business-date DataFrame with week, month, and year fields.

    `m1` and `m2` are the months of the index date shifted by
    `m1_offset` and `m2_offset` months. `y1` and `y2` are the
    corresponding years. `week`, `monday`, and `friday` describe the
    index date's ISO week.

    If `start_date` is `None`, defaults to `2010-01-01`.
    If `end_date` is `None`, defaults to `2030-12-31`.
    """

    if start_date is None:
        start_date = dt.datetime(2010, 1, 1)
    if end_date is None:
        end_date = dt.datetime(2030, 12, 31)
    bdates_index = pd.bdate_range(start_date, end_date, freq="B")
    offsets: tp.Dict[str, int] = {"week": 0}
    if m1_offset is not None:
        offsets["m1"] = m1_offset
        offsets["y1"] = m1_offset
    if m2_offset is not None:
        offsets["m2"] = m2_offset
        offsets["y2"] = m2_offset
    data = pd.DataFrame(index=bdates_index)
    data.index.name = "date"
    for k, v in offsets.items():
        if k == "week":
            data[k] = [x.isocalendar().week for x in data.index]
        else:
            vals = pd.DatetimeIndex([x + DateOffset(months=v) for x in data.index])
            data[k] = vals.month if k.startswith("m") else vals.year
    data["monday"] = [Week(x.isocalendar().year, x.isocalendar().week).monday() for x in data.index]
    data["friday"] = [Week(x.isocalendar().year, x.isocalendar().week).friday() for x in data.index]
    return data
