import datetime as dt
import os
import ssl
import time
import urllib
from io import StringIO
from urllib.error import HTTPError

import ecm.cmds.core.sql as sql
import numpy as np
import pandas as pd
from ecm.atom.clients import retry
from ecm.cmds.core.cdr import today
from ecm.cmds.core.schema import StormVistaGlobalActuals

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

apikey = os.environ["STORMVISTA_API_KEY"]
baseURL = "https://api.stormvistawxmodels.com/v1/model-data/"


def load_into_global_acutals_db(df: pd.DataFrame):
    sh = StormVistaGlobalActuals
    df = df.set_index(["Date", "Field", "Region"])
    schema_frame = sh.load(df)
    schema_frame.dump_sql(db=sql.LO25DB("prod"), form="db", mode="update_first")


def read_from_global_actuals_db():
    sh = StormVistaGlobalActuals
    df = sh.load_sql(sql.LO25DB("prod"), form="db", nullable=False)
    return df.reset_index()


@retry(max_tries=3, exceptions=[Exception], before_retry=lambda **_: time.sleep(10))
def downloadFile(url, backfill=False):
    downloaded = False
    cnt = 0 if not backfill else 1
    while not downloaded and cnt < 2:
        try:
            resp = urllib.request.urlopen(url, context=ctx)
        except HTTPError as he:
            print(he)
            if he.code == 404:
                print("File not found...Waiting for {url}".format(url=url))
                time.sleep(1)
                cnt += 1
            elif he.code == 429:
                print("Rate Limited Retrying in 10")
                raise Exception("Rate limited", 10)
        else:
            print("Downloaded {url}".format(url=url))
            downloaded = True
    try:
        return resp.read()
    except Exception:
        return 0


def us_wdd(file_date, field="ew_cdd", cycle="00", model="ecmwf-eps"):
    """
    model: ecmwf-eps or gfs-ens
    """
    file_name = (
        f'{model}/{file_date.strftime("%Y%m%d")}/{cycle}z/wdd/{field}-daily.csv?apikey={apikey}'
    )
    model_data = downloadFile(f"{baseURL}{file_name}")
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def us_wdd_regional(file_date, field="ew_cdd", cycle="00", model="ecmwf-eps"):
    """
    model: ecmwf-eps or gfs-ens
    """
    file_name = (
        f'{model}/{file_date.strftime("%Y%m%d")}/{cycle}z/wdd/{field}_reg5.csv?apikey={apikey}'
    )
    model_data = downloadFile(f"{baseURL}{file_name}")
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def global_wdd(file_date, area="europe", cycle="00", model="ecmwf-eps"):
    """
    model: ecmwf-eps or gfs-ens
    """
    file_name = f'{model}/{file_date.strftime("%Y%m%d")}/{cycle}z/wdd/{area}.csv?apikey={apikey}'
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def teleconnections(file_date, ind, cycle, model, backfill=False):
    """
    City Extraction North America Daily Max/Min for ECMWF-EPS
    """
    file_name = (
        f'{model}/{file_date.strftime("%Y%m%d")}/{cycle}z/teleconnection/'
        f"{ind}-forecast.csv?apikey={apikey}"
    )
    model_data = downloadFile(
        "{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name), backfill
    )
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def teleconnections_hist(ind):
    """
    Teleconnection full history
    """
    file_name = f"history/{ind}-full-history.csv?apikey={apikey}"
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def us_wdd_national_climo(field="ew_cdd"):
    file_name = f"history/wdd/climo/{field}_climo10yr.csv?apikey={apikey}"
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def us_wdd_regional_climo(field="ew_cdd"):
    file_name = f"history/wdd/climo/{field}_reg5_climo10yr.csv?apikey={apikey}"
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def global_wdd_climo(field="ew_cdd", area="asia"):
    file_name = f"history/wdd/climo/{field}_intl-{area}_climo10yr.csv?apikey={apikey}"
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def us_wdd_national_actual(field="ew_cdd"):
    file_name = f"history/wdd/{field}.csv?apikey={apikey}"
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def us_wdd_regional_actual(field="ew_cdd"):
    file_name = f"history/wdd/{field}_reg5.csv?apikey={apikey}"
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def global_wdd_actual(field="ew_cdd", area="asia", two_week=False):
    file_name = "history/wdd/{field}_intl-{area}.csv?apikey={apikey}".format(
        field=field, area=area, apikey=apikey
    )
    model_data = downloadFile("{baseURL}{fileName}".format(baseURL=baseURL, fileName=file_name))
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")), names=["Date", "Value"], header=0)
        df["Date"] = pd.to_datetime(df["Date"])
        df["Region"] = area
        df["Field"] = field
        load_into_global_acutals_db(df)
    ret_frame = read_from_global_actuals_db()
    ret_frame = ret_frame[(ret_frame.Field == field) & (ret_frame.Region == area)]
    if two_week:
        ret_frame = ret_frame[ret_frame.Date >= today() - dt.timedelta(days=14)]
    return ret_frame[["Date", "Value"]]


def station_daily_min_max_gc(file_date, station, model="gfs", cycle="00"):
    file_name = (
        f"{model}/{file_date.strftime('%Y%m%d')}/{cycle}z/"
        f"city-extraction/individual/{station}_max-min-bc.csv?apikey={apikey}"
    )

    model_data = downloadFile(f"{baseURL}{file_name}")
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def region_daily_min_max_gc(file_date, region, model="gfs", cycle="00"):
    file_name = (
        f"{model}/{file_date.strftime('%Y%m%d')}/{cycle}z/"
        f"city-extraction/max-min-bc_{region}.csv?apikey={apikey}"
    )

    model_data = downloadFile(f"{baseURL}{file_name}")
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def omdb_min_max(file_date, model="gfs", cycle="00"):
    """
    Download the min/max data for a specific region, model, and cycle.
    """

    df = station_daily_min_max_gc(file_date, "OMDB", model=model, cycle=cycle)
    return df


def heca_min_max(file_date, model="gfs", cycle="00"):
    """
    Download the min/max data for europe given a model, and cycle.
    """

    df = station_daily_min_max_gc(file_date, "HECA", model=model, cycle=cycle)
    return df


def region_daily_raw_gc(file_date, region, model="gfs", cycle="00"):
    file_name = (
        f"{model}/{file_date.strftime('%Y%m%d')}/{cycle}z/"
        f"city-extraction/all-stations_{region}.csv?apikey={apikey}"
    )

    model_data = downloadFile(f"{baseURL}{file_name}")
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def station_daily_raw_gc(file_date, station, model="gfs", cycle="00"):
    file_name = (
        f"{model}/{file_date.strftime('%Y%m%d')}/{cycle}z/"
        f"city-extraction/individual/{station}_raw.csv?apikey={apikey}"
    )

    model_data = downloadFile(f"{baseURL}{file_name}")
    if model_data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(model_data, "utf-8")))
    return df


def get_data_by_region(
    model="ecmwf-eps", cycle="00", region="europe", file_date=None, station=None
):
    if file_date is None:
        run_date = today()
    else:
        run_date = file_date
    if station is not None:
        if isinstance(station, str):
            station = [station]
    data = region_daily_raw_gc(run_date, region, model=model, cycle=cycle)

    data["fhr"] = data["fhr"].apply(lambda x, base_date=run_date: base_date + dt.timedelta(hours=x))
    ret_data = pd.DataFrame()
    for station_, group in data.groupby("station"):
        group = group.sort_values(by="fhr")
        mean_data = group.drop(columns="station").set_index("fhr").resample("D").mean()
        mean_data["station"] = station_
        ret_data = pd.concat([ret_data, mean_data.reset_index()])
    if ret_data.empty:
        return pd.DataFrame()
    ret_data = ret_data.rename(columns={"fhr": "fcst_date"})
    ret_data["date"] = file_date
    ret_data["cycle"] = cycle
    if station is not None:
        ret_data = ret_data[ret_data.station.isin(station)]
    return ret_data




def get_data_by_station(model="ecmwf-eps", cycle="00", station=None, file_date=None):
    if file_date is None:
        run_date = today()
    else:
        run_date = file_date
    if station is None:
        raise ValueError("station(s) must be provided")
    else:
        if isinstance(station, str):
            station = [station]
    data = pd.DataFrame()
    for st in station:
        st_data = station_daily_raw_gc(run_date, st, model=model, cycle=cycle)
        if st not in st_data.columns:
            print(f"No data for station {st} on {file_date} for model {model} cycle {cycle}")
            continue

        st_data["fhr"] = st_data[st].apply(
            lambda x, base_date=run_date: base_date + dt.timedelta(hours=float(x))
        )
        st_data = st_data.drop(columns=[st])
        st_data["station"] = st
        data = pd.concat([data, st_data])
    if data.empty:
        return pd.DataFrame()
    ret_data = pd.DataFrame()
    for station_, group in data.groupby("station"):
        group = group.sort_values(by="fhr")
        group["fhr"]
        mean_data = group.drop(columns="station").set_index("fhr").resample("D").mean()
        mean_data["station"] = station_
        ret_data = pd.concat([ret_data, mean_data.reset_index()])
    if ret_data.empty:
        return pd.DataFrame()

    ret_data = ret_data.rename(columns={"fhr": "fcst_date"})
    ret_data["date"] = file_date
    ret_data["cycle"] = cycle
    return ret_data


ACCUMULATED_VARS = {"precip", "snow"}
ANGLE_VARS = {"winddirection10", "winddirection80"}


def _circular_mean_deg(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return np.nan
    rad = np.deg2rad(vals.to_numpy())
    s, c = np.sin(rad).mean(), np.cos(rad).mean()
    if np.isclose(s, 0.0) and np.isclose(c, 0.0):
        return np.nan
    ang = np.degrees(np.arctan2(s, c))
    return ang % 360.0


def _nearest_value_at_time(series: pd.Series, target_time: pd.Timestamp, tol_hours: float = 1.0):
    """
    series is indexed by datetime (your 'fhr' timestamps).
    Return exact value at target_time, else nearest within ±tol_hours,
    else the last value before target_time (helpful for sparse leads).
    """
    if series.empty:
        return np.nan
    if target_time in series.index:
        return float(series.loc[target_time])

    diffs = (series.index - target_time).to_series().abs()
    nearest_idx = diffs.idxmin()
    if abs((nearest_idx - target_time).total_seconds()) <= tol_hours * 3600:
        return float(series.loc[nearest_idx])

    before = series[series.index <= target_time]
    if not before.empty:
        return float(before.iloc[-1])
    return np.nan


def get_fcst_data_by_station(model="ecmwf-eps", cycle="00", station=None, file_date=None):
    """
    Forecast-daily aggregates per run (file_date).

    Returns columns:
      ["station","run_date","fcst_date","model","cycle", <aggregated fields...>]

    Aggregations:
      - accumulated vars (in ACCUMULATED_VARS or name contains 'precip'/'snow'):
      end - start over [fcst_date, fcst_date+24h]
      - wind direction vars (in ANGLE_VARS or name contains 'wind' & 'direction'):
      circular mean over the window
      - everything else: simple mean over the window
    """
    if file_date is None:
        run_date = today()
    else:
        run_date = file_date

    if station is None:
        raise ValueError("station(s) must be provided")
    if isinstance(station, str):
        station = [station]

    rows = []

    for st in station:
        st_data = station_daily_raw_gc(run_date, st, model=model, cycle=cycle)
        if st_data is None or st_data.empty or st not in st_data.columns:
            print(f"No data for station {st} on {file_date} for model {model} cycle {cycle}")
            continue

        st_df = st_data.copy()

        st_df["fhr"] = st_df[st].apply(
            lambda x, base_date=run_date: base_date + dt.timedelta(hours=float(x))
        )
        st_df = st_df.drop(columns=[st])
        st_df["station"] = st

        st_df = st_df.sort_values("fhr").set_index("fhr")

        max_lead_hours = (st_df.index.max() - run_date).total_seconds() / 3600.0
        n_days = int(np.floor(max_lead_hours / 24.0))
        if n_days <= 0:
            print(f"Insufficient forecast length for station {st} on {file_date}")
            continue

        vars_present = [c for c in st_df.columns if c != "station"]

        for i in range(n_days):
            day_start = (run_date + dt.timedelta(days=i)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            day_end = day_start + dt.timedelta(days=1)

            row = {
                "station": st,
                "run_date": run_date,  # if you prefer 'date' like before, just rename at the end
                "fcst_date": day_start,
                "model": model,
                "cycle": cycle,
            }

            for col in vars_present:
                s_full = pd.to_numeric(st_df[col], errors="coerce")
                s_full.index = st_df.index  # DatetimeIndex
                s_window = s_full.loc[day_start:day_end]

                if (
                    (col in ACCUMULATED_VARS)
                    or ("precip" in col.lower())
                    or ("snow" in col.lower())
                ):
                    v0 = _nearest_value_at_time(s_full, day_start)
                    v24 = _nearest_value_at_time(s_full, day_end)
                    if i == 0 and pd.isna(v0):
                        v0 = 0.0
                    row[col] = (
                        (float(v24) - float(v0)) if (pd.notna(v24) and pd.notna(v0)) else np.nan
                    )

                elif (col in ANGLE_VARS) or ("direction" in col.lower() and "wind" in col.lower()):
                    row[col] = _circular_mean_deg(s_window)

                else:
                    row[col] = float(np.nanmean(s_window.values)) if len(s_window) else np.nan

            rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = (
        pd.DataFrame(rows).sort_values(["station", "run_date", "fcst_date"]).reset_index(drop=True)
    )
    out = out.rename(columns={"run_date": "date"})
    return out


def get_daily_station_data(
    *,
    model="ecmwf",  # or "ecmwf-eps", "gfs-ens-bc", etc.
    cycle="00",  # use 00 for UTC 00Z→00Z
    station=None,  # "ZGGG" or ["ZGGG","VHHH",...]
    start_date=None,  # inclusive
    end_date=None,  # inclusive
    sleep_seconds: float = 0.5,
):
    """
    For each UTC day and station:
      - downloads ONE file (your model/cycle/day)
      - converts lead hours to datetimes with your exact logic
      - filters to that 24h window [00Z, 24Z] and aggregates:
          * totals for accumulated vars (precip/snow): end - start
          * circular mean for wind directions
          * simple mean for everything else
    Returns a tidy DataFrame: ["station","date","model","cycle", ...daily_* columns...]
    """
    if station is None:
        raise ValueError("station must be provided (string or list of strings)")
    stations = station if isinstance(station, (list, tuple, set)) else [station]
    dates = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="D")

    out_rows = []

    for st in stations:
        for file_date in dates:
            st_data = station_daily_raw_gc(file_date, st, model=model, cycle=cycle)
            if st_data is None or st_data.empty or st not in st_data.columns:
                out_rows.append(
                    {"station": st, "date": file_date.normalize(), "model": model, "cycle": cycle}
                )
                time.sleep(sleep_seconds)
                continue

            st_data = st_data.copy()
            st_data["fhr"] = st_data[st].apply(
                lambda x, base_date=file_date: base_date + dt.timedelta(hours=float(x))
            )
            st_data = st_data.drop(columns=[st])  # drop the lead-hour column named by station
            st_data["station"] = st

            day_start = pd.Timestamp(file_date).normalize()
            day_end = day_start + dt.timedelta(days=1)
            day_df = (
                st_data[(st_data["fhr"] >= day_start) & (st_data["fhr"] <= day_end)]
                .sort_values("fhr")
                .set_index("fhr")
            )

            row = {"station": st, "date": day_start, "model": model, "cycle": cycle}

            for col in [c for c in day_df.columns if c != "station"]:
                s = pd.to_numeric(day_df[col], errors="coerce")
                s.index = day_df.index  # DatetimeIndex

                if (
                    (col in ACCUMULATED_VARS)
                    or ("precip" in col.lower())
                    or ("snow" in col.lower())
                ):
                    v0 = _nearest_value_at_time(s, day_start)
                    v24 = _nearest_value_at_time(s, day_end)
                    v0 = 0.0 if pd.isna(v0) else float(v0)  # treat +0 missing as 0
                    row[f"{col}"] = (float(v24) - v0) if pd.notna(v24) else np.nan
                elif (col in ANGLE_VARS) or ("direction" in col.lower() and "wind" in col.lower()):
                    row[f"{col}"] = _circular_mean_deg(s)
                else:
                    row[f"{col}"] = float(np.nanmean(s.values)) if len(s) else np.nan

            out_rows.append(row)
            time.sleep(sleep_seconds)
    if not out_rows:
        return pd.DataFrame()
    out = pd.DataFrame(out_rows).sort_values(["station", "date"]).reset_index(drop=True)
    return out


def cwg_url(endpoint):
    return f"https://api.commoditywx.com/v1/{endpoint}?apikey={os.environ['CWG_API_KEY']}"


def get_cwg_precipitation(date, region="asia"):
    url = cwg_url(f"{region}_fullcitylist_precip_observations_{date.strftime('%Y%m%d')}.csv")
    data = downloadFile(url)
    if data == 0:
        df = pd.DataFrame()
    else:
        df = pd.read_csv(StringIO(str(data, "utf-8")))
    return df


if __name__ == "__main__":
    import pandas as pd



    y = get_data_by_station(
        model="ecmwf-eps", cycle="12", station=["ZPPP"], file_date=dt.datetime(2021, 1, 2)
    )
    z = get_data_by_station(
        model="ecmwf-eps", cycle="00", station=["ZPPP"], file_date=dt.datetime(2021, 1, 2)
    )
    print(y)
