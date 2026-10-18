import datetime as dt
import pandas as pd
import numpy as np
from loguru import logger as log
from ecm.cmds.cdr import today, now_ldn
from ecm.cmds.vendor._open_meteo import OpenMeteoClient
from ecm.atom.schema import ECMSchema, field
from ecm.cmds.utils import get_rows_to_upsert
import ecm.cmds.sql as sql
import time

stations_default = ["ZBAA", "RKSS", "RJTT", "VIDP", "HECA", "OMDB", "ZGGG", "ZPPP",
                    "RJFT", "RKSO", "RKTU", "RKNW", "RKTI", "RKNC", "RKTT"]
lat_long_for_sation = {"RKTT": [35.89, 128.62]}


def get_data_daily(icao: str, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    if icao in lat_long_for_sation:
        lat, long = lat_long_for_sation[icao]
        client = OpenMeteoClient(
            icao=icao,
            lat=lat,
            lng=long,
            start_date=start,
            end_date=end,
            timezone="UTC",
            returns="daily"
        )
    else:
        client = OpenMeteoClient(
            icao=icao,
            start_date=start,
            end_date=end,
            timezone="UTC",
            returns="daily"
        )
    data = client.fetch_weather_data()
    if data is None or data.empty:
        log.warning(f"No weather data found for {icao} between {start} and {end}")
        return pd.DataFrame()
    return data


def get_data_fcst(icao: str, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    if icao in lat_long_for_sation:
        lat, long = lat_long_for_sation[icao]
        client = OpenMeteoClient(
            lat=lat,
            lng=long,
            start_date=start,
            end_date=end,
            historical=False,
            timezone="UTC",
            returns="daily",
            run="00z"
        )
    else:
        client = OpenMeteoClient(
            icao=icao,
            start_date=start,
            end_date=end,
            historical=False,
            timezone="UTC",
            returns="daily",
            run="00z"
        )
    data = client.fetch_weather_data()
    if data is None or data.empty:
        log.warning(f"No weather forecast data found for {icao} between {start} and {end}")
        return pd.DataFrame()
    return data


def noramlise_col_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={
        "precipitation": "precip",
        "temperature_2m": "tmp2m",
        "dew_point_2m": "dpt2m"
    })
    df.index.name = "date"
    return df


class StationDailySchema(ECMSchema, db="dbo.OpenMeteo_Station_Daily"):
    date: np.datetime64 = field(
        index=0,
        allow_null=False,
    )
    station: str = field(
        allow_null=False,
        index=1,
    )
    tmp2m: float = field(allow_null=True)
    precip: float = field(allow_null=True)
    dpt2m: float = field(allow_null=True)


class StationDailyFcstSchema(ECMSchema, db="dbo.OpenMeteo_Station_DailyFcst"):
    date: np.datetime64 = field(
        index=0,
        allow_null=False,
    )
    fcst_date: np.datetime64 = field(
        index=1,
        allow_null=False,
    )
    station: str = field(
        allow_null=False,
        index=3,
    )
    tmp2m: float = field(allow_null=True)
    precip: float = field(allow_null=True)
    dpt2m: float = field(allow_null=True)


def update_daliy(backfill: bool = False,):
    if backfill:
        end_date = today()
        start_date = dt.datetime(2015, 1, 1)
    else:
        end_date = today()
        start_date = end_date - dt.timedelta(days=1)
    all_raw_data = pd.DataFrame()
    for station in stations_default:
        log.info(f"Fetching data for station {station} from {start_date} to {end_date}")
        raw_data = get_data_daily(station, start_date, end_date)
        if raw_data is not None and not raw_data.empty:
            log.info(f"Fetched {len(raw_data)} rows for station {station}")
        else:
            log.info(f"No data fetched for station {station}")
            continue
        raw_data["station"] = station
        all_raw_data = pd.concat([all_raw_data, raw_data])
        time.sleep(5)  # to avoid hitting API rate limits
    if not all_raw_data.empty:
        normalised_df = noramlise_col_names(all_raw_data)
        clean_df = normalised_df.dropna(subset=["tmp2m", "dpt2m"], how="all", axis=0)

        db = sql.LO25DB("prod")
        schema_frame = StationDailySchema(clean_df, nullable=False)
        existing_df = StationDailySchema.load_sql(db, form="db", nullable=False)
        upsert_df = get_rows_to_upsert(schema_frame, existing_df, key_cols=["date", "station"])
        if not upsert_df.empty:
            df_to_upsert = upsert_df[upsert_df["update_type"] == "updated"].drop(columns=["update_type"])
            df_to_insert = upsert_df[upsert_df["update_type"] == "new"].drop(columns=["update_type"])
            if not df_to_upsert.empty:
                StationDailySchema(df_to_upsert).dump_sql(db, form="db", mode="update_first")
                log.info(f"Updated {len(df_to_upsert)} rows to OpenMeteo_Station_Daily table.")
            if not df_to_insert.empty:
                StationDailySchema(df_to_insert).dump_sql(db, form="db", mode="insert_first")
                log.info(f"Inserted {len(df_to_insert)} new rows to OpenMeteo_Station_Daily table.")
        else:
            log.info("No new or updated rows to upsert for OpenMeteo_Station_Daily table.")


def update_fcst(backfill: bool = False):
    if backfill:
        end_date = today() + dt.timedelta(days=14)
        start_date = dt.datetime(2023, 10, 1)
    else:
        end_date = today() + dt.timedelta(days=14)
        start_date = today()
    all_raw_data = pd.DataFrame()
    for station in stations_default:
        log.info(f"Fetching forecast data for station {station} from {start_date} to {end_date}")
        raw_data = get_data_fcst(station, start_date, end_date)
        if raw_data is not None and not raw_data.empty:
            log.info(f"Fetched {len(raw_data)} rows for station {station}")
        else:
            log.info(f"No data fetched for station {station}")
            continue
        raw_data = raw_data.reset_index().rename(columns={"run_date": "date"}).set_index("date")
        raw_data["station"] = station
        all_raw_data = pd.concat([all_raw_data, raw_data])
        time.sleep(5)  # to avoid hitting API rate limits
    if not all_raw_data.empty:
        normalised_df = noramlise_col_names(all_raw_data)
        clean_df = normalised_df.dropna(subset=["tmp2m", "dpt2m"], how="all", axis=0)

        db = sql.LO25DB("prod")
        schema_frame = StationDailyFcstSchema(clean_df, nullable=False)
        existing_df = StationDailyFcstSchema.load_sql(db, form="db", nullable=False)
        upsert_df = get_rows_to_upsert(schema_frame, existing_df, key_cols=["date", "fcst_date", "station"])
        if not upsert_df.empty:
            df_to_upsert = upsert_df[upsert_df["update_type"] == "updated"].drop(columns=["update_type"])
            df_to_insert = upsert_df[upsert_df["update_type"] == "new"].drop(columns=["update_type"])
            if not df_to_upsert.empty:
                StationDailyFcstSchema(df_to_upsert).dump_sql(db, form="db", mode="update_first")
                log.info(f"Updated {len(df_to_upsert)} rows to OpenMeteo_Station_Daily_Fcst table.")
            if not df_to_insert.empty:
                StationDailyFcstSchema(df_to_insert).dump_sql(db, form="db", mode="insert_first")
                log.info(f"Inserted {len(df_to_insert)} new rows to OpenMeteo_Station_Daily_Fcst table.")
        else:
            log.info("No new or updated rows to upsert for OpenMeteo_Station_Daily_Fcst table.")


def update_fcst_backfill():
    run_start = dt.datetime(2023, 10, 1)
    run_end = today()
    all_raw_data = pd.DataFrame()
    for station in stations_default:
        log.info(f"Backfill previous runs for {station} from {run_start.date()} to {run_end.date()}")
        try:
            client = OpenMeteoClient(icao=station, historical=False, returns="daily", run="00z", model="ecmwf_ifs")
            prev_df = client.fetch_previous_runs_00z(
                start_date=run_start.strftime("%Y-%m-%d"),
                end_date=run_end.strftime("%Y-%m-%d"),
                days_back=7,
                is_backfill=True
            )
        except Exception as e:
            log.exception(f"Previous runs fetch failed for {station}: {e}")
            continue
        if prev_df.empty:
            log.info(f"No previous run data for {station}")
            continue
        prev_df = prev_df.reset_index()  # run_date index
        prev_df["station"] = station
        tmp_cols = {c: c.split(" ")[0] for c in prev_df.columns}
        prev_df = prev_df.rename(columns=tmp_cols)
        prev_df = prev_df.rename(columns={
            "temperature_2m": "tmp2m",
            "precipitation": "precip",
            "dew_point_2m": "dpt2m",
            "fcst_date": "fcst_date"
        })
        keep = ["run_date", "fcst_date", "station", "tmp2m", "precip", "dpt2m"]
        prev_df = prev_df[keep]
        all_raw_data = pd.concat([all_raw_data, prev_df], axis=0)
        time.sleep(2)
    if all_raw_data.empty:
        log.info("No backfill forecast data collected.")
        return
    all_raw_data = all_raw_data.rename(columns={"run_date": "date"})
    db = sql.LO25DB("prod")
    schema_frame = StationDailyFcstSchema(all_raw_data, nullable=False)
    existing_df = StationDailyFcstSchema.load_sql(db, form="db", nullable=False)
    upsert_df = get_rows_to_upsert(schema_frame, existing_df, key_cols=["date", "fcst_date", "station"])
    if upsert_df.empty:
        log.info("No new/updated rows for backfill forecast.")
        return
    to_update = upsert_df[upsert_df["update_type"] == "updated"].drop(columns=["update_type"])
    to_insert = upsert_df[upsert_df["update_type"] == "new"].drop(columns=["update_type"])
    if not to_update.empty:
        StationDailyFcstSchema(to_update).dump_sql(db, form="db", mode="update_first")
        log.info(f"Updated {len(to_update)} rows (backfill forecasts).")
    if not to_insert.empty:
        StationDailyFcstSchema(to_insert).dump_sql(db, form="db", mode="insert_first")
        log.info(f"Inserted {len(to_insert)} rows (backfill forecasts).")
    return


release_times = {
    "00": [dt.time(6, 30), dt.time(10, 30)],
}


def runner():
    current_time = now_ldn().time().replace(microsecond=0)
    for cycle, (start, end) in release_times.items():
        if start <= current_time <= end:
            log.info(f"Running open_meto_percip for cycle {cycle}")
            try:
                update_fcst(backfill=False)
            except Exception as e:
                log.exception(f"Error running open_meteo_percip forecast update: {e}")
                return
        else:
            log.info(f"{cycle}: Not running open_meto_percip, current time {current_time} not in window {start} - {end}")


if __name__ == "__main__":
    update_daliy(backfill=True)
