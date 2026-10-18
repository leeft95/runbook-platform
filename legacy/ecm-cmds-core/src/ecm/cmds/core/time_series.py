import datetime as dt
import os
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from ecm.cmds.core.utils import convert_path_to_linux
from isoweek import Week
from pyg_base import dt as pygdt


def historical_data_on_date(df, date):
    """
    Calculate historical data on input date
    """
    df_alldays = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="D"))
    df_alldays.fillna(method="ffill", inplace=True)
    if date.month == 2 and date.day == 29:
        data_by_yr = df_alldays.loc[(df_alldays.index.month == 2) & (df_alldays.index.day == 28), :]
    else:
        data_by_yr = df_alldays.loc[(df_alldays.index.month == date.month) & (df_alldays.index.day == date.day), :]
    return data_by_yr


def data_by_year(df, freq="D", start_day=None, start_month=None, end_day=None, end_month=None,
                 column=None, start=None, ytd=False, over_year=False):
    if column is not None:
        df_ = df[column]
    else:
        df_ = df.copy()
    if start is not None:
        df_ = df_.loc[df_.index >= start]
    start_year = df_.index[0].year
    if start_day is None:
        start_day = df_.index[0].day
    if start_month is None:
        start_month = df_.index[0].month
    end_year = df_.index[-1].year
    if over_year:
        last_date = df_.index[-1]
        if last_date.month < start_month:
            end_year = end_year - 1
    if freq == "W":
        idx_diff = (df.index.to_series().diff()).dt.days
        idx_diff_cum = idx_diff.rolling(2).sum().shift(-1)
        if any(idx_diff_cum <= 7):
            df_.drop(idx_diff_cum[idx_diff_cum <= 7].index, inplace=True)
        dby = pd.DataFrame(np.nan, index=range(0, 53), columns=range(start_year, end_year + 1))
    elif freq in ["M", "MS", "ME"]:
        dby = pd.DataFrame(np.nan, index=range(0, 12), columns=range(start_year, end_year + 1))
    elif freq == "D":
        dby = pd.DataFrame(np.nan, index=range(0, 366), columns=range(start_year, end_year + 1))
    elif freq == "B":
        dby = pd.DataFrame(np.nan, index=range(0, 262), columns=range(start_year, end_year + 1))
    for yr in range(start_year, end_year + 1):
        if over_year:
            raise NotImplementedError("Photographed time_series.py line 73 has a clipped date boundary")
        else:
            raise NotImplementedError("Photographed time_series.py line 75 has a clipped date boundary")
        if len(data_yr) == 0:
            data_yr = df_.loc[str(yr)]
        if len(dby) < len(data_yr):
            dby.loc[:len(data_yr)-1, yr] = data_yr.values[:len(dby)-len(data_yr)]
        elif yr == start_year and yr != end_year:
            if df_.index[0] > dt.datetime(start_year, start_month, start_day):
                sloc = len(dby) - len(data_yr)
                dby.loc[sloc:, yr] = data_yr.values
            else:
                lloc = len(data_yr) - 1
                dby.loc[:lloc, yr] = data_yr.values
        else:
            raise NotImplementedError("Photographed time_series.py line 89 has a clipped date boundary")
            if ...:  # unavailable condition; retained body below
                dby.drop(end_year, axis=1, inplace=True)
            else:
                dby.loc[:len(data_yr)-1, yr] = data_yr.values
    if ytd:
        return dby - dby.iloc[0, :]
    else:
        return dby


def _merge_df(dfs, keep=0, on=None):
    """
    dfs is dictionary or list of dataframes
    keep: 'add' or 0 - Add the same columns in all dfs (default);
        'append' or 1 - append the same columns in all dfs
    Append different columns
    """
    merged_df = pd.DataFrame()
    if isinstance(dfs, dict):
        dfs_ = list(dfs.items())
    elif isinstance(dfs, list):
        dfs_ = dfs
    if keep == 0 or keep.lower() == "add":
        for df in dfs_:
            common_columns = set(merged_df.columns) & set(df.columns)
            for col in common_columns:
                merged_df[col] += df[col]
            new_columns = set(df.columns) - set(merged_df.columns)
            for col in new_columns:
                merged_df[col] = df[col]
    elif keep == 1 or keep.lower() == "append":
        for df in dfs_:
            merged_df = pd.concat([merged_df, df], axis=1)
    elif (keep == 2 or keep.lower() == "merge") and on is not None:
        merged_df = dfs_[0].copy()
        for df in dfs_[1:]:
            merged_df = pd.merge(merged_df, df, on=on)
    else:
        pass
    return merged_df


def concat(dfs, axis=0, ignore_index=True, columns=None, df_index=None, method="ffill"):
    """
    dfs is list of dataframes
    columns: rename all columns
    df_index: use this df.index as output df index
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        import ecm.cmds.core.pyg as pyg
        from ecm.cmds.core.config import url
        db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
        c1 = pyg.get_cell(db, active="QSA Comdty", item="MMLF")
        c2 = pyg.get_cell(db, active="XBA Comdty", item="MMLF")
        c3 = pyg.get_cell(db, active="HOA Comdty", item="MMLF")
        df = concat(dfs=[c1.data, c2.data, c3.data], axis=1, df_index=c1.data)
        print(df)
    """
    if df_index is not None:
        if isinstance(df_index, pd.DataFrame) or isinstance(df_index, pd.Series):
            days = pd.date_range(df_index.index[0], df_index.index[-1], freq="D")
            df_index_ = df_index.index
        else:
            days = pd.date_range(df_index[0], df_index[-1], freq="D")
            df_index_ = df_index.copy()
        dfs_ = []
        for i in dfs:
            i_ = i.reindex(days, method=method)
            dfs_.append(i_.reindex(df_index_))
    else:
        dfs_ = dfs.copy()
    res = pd.concat(dfs_, axis=axis, ignore_index=ignore_index)
    if columns is not None:
        res.columns = columns
    return res


def sum_dfs(dfs):
    """
    dfs is dictionary or list of dataframes
    Add the same columns in all dfs;
    Append different columns
    """
    merged_df = pd.DataFrame()
    if isinstance(dfs, dict):
        dfs_ = list(dfs.values())
    elif isinstance(dfs, list):
        dfs_ = dfs
    for df in dfs_:
        common_columns = set(merged_df.columns) & set(df.columns)
        for col in common_columns:
            merged_df[col] += df[col]
        new_columns = set(df.columns) - set(merged_df.columns)
        for col in new_columns:
            merged_df[col] = df[col]
    return merged_df


def sumproduct(dfs, w, method="sum"):
    """
    dfs is dictionary or list of dataframes
    that have the same columns in the same order
    return dfs * w
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        import ecm.cmds.core.pyg as pyg
        from ecm.cmds.core.config import url
        db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
        c1 = pyg.get_cell(db, active="QSA Comdty", item="MMLF")
        c2 = pyg.get_cell(db, active="XBA Comdty", item="MMLF")
        c3 = pyg.get_cell(db, active="HOA Comdty", item="MMLF")
        df = sumproduct(dfs=[c1.data, c2.data, c3.data], w=[1, 1, 0.853])
        print(df)
    """
    merged_df = pd.DataFrame()
    if isinstance(dfs, dict):
        dfs_ = list(dfs.values())
    elif isinstance(dfs, list):
        dfs_ = dfs
    cols = dfs_[0].columns
    for idx, df in enumerate(dfs_):
        if isinstance(df, pd.Series):
            df = df.to_frame(cols[0])
        elif isinstance(df, pd.DataFrame):
            df.columns = cols
        if len(merged_df) == 0:
            merged_df = df * w[idx]
        else:
            merged_df += df * w[idx]
    if method == "mean":
        merged_df = merged_df / len(w)
    return merged_df


def rolling(df, columns=None, rename=None, method="mean", window=20, start=None):
    """
    Transform df in a rolling way
    df: dataframe or series
    columns: keep these columns
    rename: dict, e.g. {old column: new column}
    method: mean, sum or diff
    return: dataframe or series
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        import ecm.cmds.core.pyg as pyg
        from ecm.cmds.core.config import url
        db = partial(mongo_table, table="data",
                 pk=["name", "sector", "market", "category", "region", "country", "source"],
                 db="reports", url=url)
        c = pyg.get_cell(db, name="kpler_implied_demand_exporter")
        df = rolling(c.data, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    """
    df_ = df.copy()
    if rename is not None:
        df_.rename(columns=rename, inplace=True)
    if columns is not None:
        df_ = df_[columns]
    if method is None:
        pass
    elif method.lower() in ["change", "diff", "chg"]:
        df_ = df_.diff(periods=window)
    elif method.lower() == "sum":
        df_ = df_.rolling(window).sum()
    elif method.lower() in ["ma", "mean"]:
        df_ = df_.rolling(window).mean()
    if start is not None:
        if isinstance(start, str):
            start = pygdt(start)
        if isinstance(df_, pd.DataFrame):
            df_ = df_.loc[df_.index >= start, :]
        elif isinstance(df_, pd.Series):
            df_ = df_.loc[df_.index >= start]
    return df_


def adjust(df, adjustment, columns=None, rename=None, fill_na=None, start=None):
    """
    df: dataframe to be transformed
    adjustment:{column or list of columns: {
        add: column or list of columns + add value
        subtract: column or list of columns - subtract value
        multiply: column or list of columns * multiply value
        divide: column or list of columns / divide value
        }
    }
    columns: columns to keep
    rename: dict, e.g. {old column: new column}
    fill_na: if not none, it is fillna method, e.g. 'ffill'
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        from ecm.cmds.core.config import url
        import ecm.cmds.core.pyg as pyg

        db = partial(mongo_table, table="data", pk=["name", "sector", "market",
                                                 "category", "region", "country", "source"],
                     db="reports", url=url)
        c = pyg.get_cell(db, name="kpler_implied_demand_exporter")
        df = adjust(c.data, adjustment={"Total": {"add": ['Saudi Arabia', 'Kuwait',
                                                       'United Arab Emirates', 'China', 'India',
                                                       'South Korea']},
                                       ('Saudi Arabia', 'Kuwait'): {"sub":
                                                                  'United Arab Emirates'},
                                       "China": {"mul": 2},
                                       "India": {"diff": 1}})
        print(df)
    """
    df_ = df.copy()
    if start is not None:
        if isinstance(start, str):
            start = pygdt(start)
        if isinstance(df_, pd.DataFrame):
            df_ = df_.loc[df_.index >= start, :]
        elif isinstance(df_, pd.Series):
            df_ = df_.loc[df_.index >= start]
    if fill_na is not None:
        df_.fillna(method=fill_na, inplace=True)
    if rename is not None:
        df_.rename(columns=rename, inplace=True)
    if adjustment is None or len(adjustment) < 1:
        if columns is not None:
            df_ = df[columns]
        return df_
    for k, v in adjustment.items():
        if isinstance(k, tuple):
            k = list(k)
            for i in k:
                if i not in df_.columns:
                    df_[i] = 0.0
        else:
            if k not in df_.columns:
                df_[k] = 0.0
        for k1, v1 in v.items():
            if k1.lower() in ["add", "sum"]:
                if isinstance(v1, list):
                    for i in v1:
                        if i in df_.columns:
                            df_[k] = df_[k] + df_[i]
                        elif isinstance(i, float) or isinstance(i, int) or isinstance(i, pd.Series):
                            df_[k] = df_[k] + i
                        elif isinstance(i, pd.DataFrame):
                            df_[k] = df_[k] + i.iloc[:, 0]
                else:
                    if isinstance(v1, str) and v1 in df_.columns:
                        df_[k] = df_[k].add(df_[v1], axis=0)
                    elif isinstance(v1, float) or isinstance(v1, int):
                        df_[k] = df_[k] + v1
                    elif isinstance(v1, pd.Series):
                        df_[k] = df_[k].add(v1, axis=0)
                    elif isinstance(v1, pd.DataFrame):
                        df_[k] = df_[k].add(v1.iloc[:, 0], axis=0)
            elif k1.lower() in ["subtract", "sub"]:
                if isinstance(v1, list):
                    for i in v1:
                        if i in df_.columns:
                            df_[k] = df_[k] - df_[i]
                        elif isinstance(i, float) or isinstance(i, int) or isinstance(i, pd.Series):
                            df_[k] = df_[k] - i
                        elif isinstance(i, pd.DataFrame):
                            df_[k] = df_[k] + i.iloc[:, 0]
                else:
                    if isinstance(v1, str) and v1 in df_.columns:
                        df_[k] = df_[k].sub(df_[v1], axis=0)
                    elif isinstance(v1, float) or isinstance(v1, int):
                        df_[k] = df_[k] - v1
                    elif isinstance(v1, pd.Series):
                        df_[k] = df_[k].sub(v1, axis=0)
                    elif isinstance(v1, pd.DataFrame):
                        df_[k] = df_[k].sub(v1.iloc[:, 0], axis=0)
            elif k1.lower() in ["multiply", "mul"]:
                if isinstance(v1, list):
                    for i in v1:
                        if i in df_.columns:
                            df_[k] = df_[k] * df_[i]
                        elif isinstance(i, float) or isinstance(i, int) or isinstance(i, pd.Series):
                            df_[k] = df_[k] * i
                        elif isinstance(i, pd.DataFrame):
                            df_[k] = df_[k] + i.iloc[:, 0]
                else:
                    if isinstance(v1, str) and v1 in df_.columns:
                        df_[k] = df_[k].mul(df_[v1], axis=0)
                    elif isinstance(v1, float) or isinstance(v1, int):
                        df_[k] = df_[k] * v1
                    elif isinstance(v1, pd.Series):
                        df_[k] = df_[k].mul(v1, axis=0)
                    elif isinstance(v1, pd.DataFrame):
                        df_[k] = df_[k].mul(v1.iloc[:, 0], axis=0)
            elif k1.lower() in ["divide", "div"]:
                if isinstance(v1, list):
                    for i in v1:
                        if i in df_.columns:
                            df_[k] = df_[k] / df_[i]
                        elif isinstance(i, float) or isinstance(i, int) or isinstance(i, pd.Series):
                            df_[k] = df_[k] / i
                        elif isinstance(i, pd.DataFrame):
                            df_[k] = df_[k] + i.iloc[:, 0]
                else:
                    if isinstance(v1, str) and v1 in df_.columns:
                        df_[k] = df_[k].div(df_[v1], axis=0)
                    elif isinstance(v1, float) or isinstance(v1, int):
                        df_[k] = df_[k] / v1
                    elif isinstance(v1, pd.Series):
                        df_[k] = df_[k].div(v1, axis=0)
                    elif isinstance(v1, pd.DataFrame):
                        df_[k] = df_[k].div(v1.iloc[:, 0], axis=0)
            elif k1.lower() in ["diff"]:
                df_[k] = df_[k].diff(periods=v1)
    if columns is not None:
        df_ = df_[columns]
    return df_


def historical_mean_std(df, seasonal=5, window=None, ex2020=True, rank_date=None, drop_years=None):
    """
    Calculate historical mean and std for last day
    If seasonal is not None, using the same month and day in past years
    If window is not None, using moving average
    Do not include last day
    return dataframe with df.columns as index and 'mean', 'std' as columns
    """
    if rank_date is None:
        rank_date = df.index[-1]
    df_mean_std = pd.DataFrame(0, index=df.columns, columns=["mean", "std"])
    if seasonal is not None:
        data_by_yr = historical_data_on_date(df, rank_date)
        if ex2020:
            data_by_yr.drop(data_by_yr.loc[data_by_yr.index.year == 2020, :].index, axis=0, inplace=True)
        if drop_years is not None:
            if isinstance(drop_years, int):
                data_by_yr.drop(data_by_yr.loc[data_by_yr.index.year == drop_years, :].index,
                                axis=0, inplace=True)
            elif isinstance(drop_years, list):
                for i in drop_years:
                    data_by_yr.drop(data_by_yr.loc[data_by_yr.index.year == i, :].index, axis=0, inplace=True)
        sloc = -seasonal - 1
        if -sloc > len(data_by_yr.index):
            sloc = 0
        df_mean_std.loc[:, "mean"] = data_by_yr.iloc[sloc:-1].mean(axis=0)
        df_mean_std.loc[:, "std"] = data_by_yr.iloc[sloc:-1].std(axis=0)
    elif isinstance(window, str) and window.upper() in ["FULL", "EXTEND"]:
        df_mean_std.loc[:, "mean"] = df.iloc[:-1, :].mean()
        df_mean_std.loc[:, "std"] = df.iloc[:-1, :].std()
    else:
        df_mean_std.loc[:, "mean"] = df.rolling(window).mean().iloc[-2]
        df_mean_std.loc[:, "std"] = df.rolling(window).std().iloc[-2]
    return df_mean_std


def last_valid_index(df, index_name="Name", column_name="last_valid_index", dt2str=None):
    """
    Find last valid index for each column
    """
    df_ = df.apply(pd.Series.last_valid_index)
    if dt2str is not None:
        df_ = df_.dt.strftime(dt2str)
    df_ = df_.to_frame(column_name)
    df_.index.name = index_name
    return df_.reset_index()


def fillna(df, columns=None, value=0, method=None):
    """
    fillna by columns
    columns: if list, fill the columns with value or method;
            if dict, fill the columns with value or method in dict
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        import ecm.cmds.core.pyg as pyg
        from ecm.cmds.core.config import url
        db = partial(mongo_table, table="data",
                 pk=["name", "sector", "market", "category", "region", "country", "source"],
                 db="reports", url=url)
        from ecm.cmds.core.cdr import today
        c1 = pyg.get_cell(db, name="global_product_stocks_table_with_date")
        df = fillna(c1.data, columns={"Last Update": {"value": "_last_update"}}, value=0, method=None)
        print(df)
    """
    df_ = df.copy()
    if columns is None:
        if method is not None:
            return df.fillna(method=method)
        else:
            return df.fillna(value=value)
    elif isinstance(columns, list):
        if method is not None:
            return df[columns].fillna(method=method)
        else:
            return df[columns].fillna(value=value)
    elif isinstance(columns, dict):
        for k, v in columns.items():
            if "method" in v.keys():
                df_[k].fillna(method=v["method"], inplace=True)
            elif "value" in v.keys():
                if isinstance(v["value"], str) and v["value"] in df.columns:
                    nan_idx = df_.index[df_[k].isna()]
                    df_.loc[nan_idx, k] = df_.loc[nan_idx, v["value"]]
                else:
                    df_[k].fillna(value=v["value"], inplace=True)
        return df_


def resample(df, freq="M", method="mean", last_window=20, index="first"):
    """
    pandas resample function
    last_window: replace the last value with last_window mean (20d mean)
    index: first - beginning of the freq period; last - end of the freq period
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        import ecm.cmds.core.pyg as pyg
        from ecm.cmds.core.config import url
        db = partial(mongo_table, table="data",
                 pk=["name", "sector", "market", "category", "region", "country", "source"],
                 db="reports", url=url)
        c1 = pyg.get_cell(db, name="apac_daily_imports_total")
        df = resample(df=c1.data, freq="M", method="mean", last_window=20)
        print(df)
    """
    if method == "last":
        df_ = df.resample(freq).last()
    elif method == "sum":
        df_ = df.resample(freq).sum()
        df_.loc[df_.index[-1], :] = (df.rolling(last_window).sum()).iloc[-1, :]
    elif method == "mean":
        df_ = df.resample(freq).mean()
        df_.loc[df_.index[-1], :] = (df.rolling(last_window).mean()).iloc[-1, :]
    if index == "first":
        df_.index = [x - relativedelta(day=1) for x in df_.index]
    return df_


def cumsum_by_month(df, column="Total", n=2, lable=None, method="ffill", convert_to_daily=False):
    """
    df is daily time series
    n is how many months
    return cumsum column, rows are 0-30 (days), columns are months
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        import ecm.cmds.core.pyg as pyg
        from ecm.cmds.core.config import url
        db = partial(mongo_table, table="data",
                 pk=["name", "sector", "market", "category", "region", "country", "source"],
                 db="reports", url=url)
        c1 = pyg.get_cell(db, name="clean_export_allocation")
        df = cumsum_by_month(c1.data, column=c1.data.columns[0], n=2, lable="actual", convert_to_daily=True)
        print(df)
    """
    dts = pd.date_range(df.index[0], df.index[-1])
    df_ = df.copy()
    if convert_to_daily:
        df_ = df_.divide(pd.Series(df.index.daysinmonth, index=df.index), axis=0)
    df_ = df_.reindex(dts, method=method)
    df_["year"] = df_.index.year
    df_["month"] = df_.index.month
    df_["new_col"] = df_.groupby(["year", "month"])[column].cumsum()
    if n is not None or n > 0:
        datatbl = df_.loc[df_.index > pygdt() - relativedelta(months=n) + relativedelta(day=31)]
        datatbl["dm"] = datatbl.index.strftime("%m/%Y")
        pvt2 = pd.pivot_table(datatbl, columns=[datatbl.dm], index=datatbl.index.day, values="new_col")
        if lable is not None:
            pvt2.columns = [dt.datetime(int(x[-4:]), int(x[:2]), 1).strftime(f"%b-%y {lable}") for x in pvt2.columns]
        else:
            pvt2.columns = [dt.datetime(int(x[-4:]), int(x[:2]), 1).strftime("%b-%y") for x in pvt2.columns]
        return pvt2
    else:
        return df_


def read_csv(path, index_name="Unnamed: 0"):
    path = convert_path_to_linux(path)
    if os.path.exists(path):
        df = pd.read_csv(path)
        if index_name is None:
            return df
        else:
            if "Unnamed: 0" in df.columns and index_name != "Unnamed: 0":
                df = df.rename(columns={"Unnamed: 0": index_name})
            df = df.set_index(index_name)
            df.index = pd.to_datetime(df.index)
            return df
    else:
        return pd.DataFrame()


def reindex(df, to_index, method="ffill"):
    """
    change df index to to_index with method
    different from pandas reindex is that
    this first adjust to day frequency before
    fillna
    """
    if isinstance(to_index, pd.DataFrame) or isinstance(to_index, pd.Series):
        to_index_ = to_index.index
    else:
        to_index_ = to_index.copy()
    dts = pd.date_range(np.min([to_index_[0], df.index[0]]), np.max([to_index_[-1], df.index[-1]]))
    df_ = df.reindex(dts)
    df_.fillna(method=method, inplace=True)
    return df_.reindex(to_index_)


def dwmy(start_date, end_date, m1=2, m2=3, add_week=0):
    """
    Day/Week/Month/Year - Generate dataframe with bdates, week num, month 1/2 and year 1/2
    m1 is current date + m1 months
    m2 is current date + m2 months
    y1 and y2 are calculated from m1 and m2
    """
    if start_date is None:
        start_date = dt.datetime(2009, 1, 1)
    if end_date is None:
        end_date = dt.datetime(2030, 12, 31)
    dts = pd.bdate_range(start_date, end_date, freq="B")
    res = pd.DataFrame(0, index=dts, columns=["value"])
    res["week"] = [(x + relativedelta(weeks=add_week)).isocalendar().week for x in res.index]
    res["m1"] = (res.index + pd.DateOffset(months=m1)).month
    res["m2"] = (res.index + pd.DateOffset(months=m2)).month
    res["y1"] = (res.index + pd.DateOffset(months=m1)).year
    res["y2"] = (res.index + pd.DateOffset(months=m2)).year
    res["monday"] = [Week(x.isocalendar().year, x.isocalendar().week).monday() for x in dts]
    res["friday"] = [Week(x.isocalendar().year, x.isocalendar().week).friday() for x in dts]
    return res.drop(["value"], axis=1)


def pnl_stats(pnl, cumulative=False):
    """
    Calculate annual return, vol, Sharpe Ratio, Max Drawdown and Calmar ratio
    for daily pnl series or dataframe
    """
    if cumulative:
        daily_pnl = pnl.copy().diff()
    else:
        daily_pnl = pnl.copy()
    if isinstance(daily_pnl, pd.Series):
        daily_pnl = daily_pnl.to_frame("Total")
    if len(daily_pnl) < 260:
        ann_rtn = daily_pnl.mean() * len(daily_pnl)
        ann_vol = daily_pnl.std() * np.sqrt(len(daily_pnl))
    else:
        ann_rtn = daily_pnl.mean() * 260
        ann_vol = daily_pnl.std() * np.sqrt(260)
    sharpe = ann_rtn / ann_vol
    cum_rtn = daily_pnl.cumsum()
    dd = cum_rtn - cum_rtn.cummax()
    max_dd = dd.min()
    calmar = ann_rtn / np.abs(max_dd)
    calmar[calmar > 10000] = np.nan
    calmar[calmar < -10000] = np.nan
    stats = pd.concat([ann_rtn, ann_vol, sharpe, max_dd, calmar], axis=1)
    stats.columns = ["Annual Return", "Vol", "Sharpe Ratio", "Max Drawdown", "Calmar Ratio"]
    return stats.transpose()


def convert_monthly(df, to="weekly", sdate=None, edate=None, freq="FRI"):
    if sdate is None:
        sdate = df.index[0] + relativedelta(day=1)
    if edate is None:
        edate = df.index[-1] + relativedelta(day=31)
    dts = pd.date_range(sdate, edate, freq="d")
    df_ = df.reindex(dts).fillna(method="ffill").fillna(method="bfill")
    if isinstance(df_, pd.Series):
        df_ = df.to_frame("0")
    df_["days"] = df_.index.days_in_month
    if to.lower() in ["daily", "day", "d"]:
        ret = df_.iloc[:, 0] / df_["days"]
        return ret.resample(freq).last()
    elif to in ["weekly", "week", "w"]:
        ret = df_.iloc[:, 0] / df_["days"] * 7
        return ret.resample(freq).last()


if __name__ == "__main__":
    from functools import partial
    from pyg_mongo import mongo_table
    import ecm.cmds.core.pyg as pyg
    from ecm.cmds.core.config import url
    db = partial(mongo_table, table="data",
                 pk=["name", "sector", "market", "category", "region", "country", "source"],
                 db="reports", url=url)
    c1 = pyg.get_cell(db, name="clean_export_allocation")
    df = cumsum_by_month(c1.data, column=c1.data.columns[0], n=2, lable="actual", convert_to_daily=True)
    print(df)
