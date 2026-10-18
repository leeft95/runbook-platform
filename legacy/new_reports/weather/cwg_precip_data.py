import ecm.cmds.stormvista as sv
import datetime as dt
import pandas as pd
import numpy as np
import ecm.cmds.sql as sql
from loguru import logger as log
from ecm.atom.schema import ECMSchema, field


default_station_list = ["ZBAA", "RKSS", "RJTT", "VIDD", "HECA", "OMDB", "ZGGC", "ZPPP", "RJFT", "RKSO", ...]
table_name = "CWG_Precipitation"


class CWGPrecipSchema(ECMSchema, db="dbo.CWG_Precipitation"):
    date: np.datetime64 = field(
        index=0,
        allow_null=False,
    )
    station: str = field(
        allow_null=False,
        index=1,
    )
    precip: float = field(allow_null=True)


def get_cwg_precipitation(date: dt.datetime, region: str = "asia", stations: list = None) -> pd.DataFrame:
    data_for_date = pd.DataFrame()
    if stations is None:
        raise NotImplementedError("Photographed cwg_precip_data.py line 10 has a clipped default station list")
        stations = default_station_list
    try:
        df = sv.get_cwg_precipitation(date, region=region)
        filtered_df = df[df.station.isin(stations)]
        data_for_date = pd.concat([data_for_date, filtered_df], ignore_index=True)
    except Exception as e:
        log.error(f"Error getting CWG precipitation data for {date} {region}: {e}")
    data_for_date = data_for_date.drop(columns=["precip(in)"]).rename(columns={"precip(mm)": "precip"})
    return data_for_date


def update(stations, region="asia"):
    table_name = table_name
    today_dt = dt.date.today()

    try:
        max_date_df = sql.read_sql(
            f"SELECT MAX([date]) AS max_date FROM {table_name}"
        )
    except Exception as e:
        log.info(f"SQL error while checking max date f: {e}")
        max_date_df = pd.DataFrame()

    max_date_val = None
    if not max_date_df.empty:
        scalar = None
        if "max_date" in max_date_df.columns:
            scalar = max_date_df.at[0, "max_date"]
        else:
            scalar = max_date_df.iloc[0, 0]
        if pd.notnull(scalar):
            max_date_val = pd.to_datetime(scalar).date()
    if max_date_val is not None:
        if today_dt == max_date_val:
            log.info(f"Data is already up to date.")
            return
        else:
            start_date = max_date_val + dt.timedelta(days=1)
    else:
        start_date = dt.date(2015, 1, 1)

    end_date = today_dt
    wrote_data = []
    to_insert_df = pd.DataFrame()
    if start_date <= end_date:
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        for single_date in date_range:
            try:
                insert_df = get_cwg_precipitation(date=start_date, region=region, stations=stations)
            except Exception as e:
                log.exception(f"Error fetching data for {single_date.date()}: {e}")
                insert_df = pd.DataFrame()
            if not insert_df.empty:
                to_insert_df = pd.concat([to_insert_df, insert_df], ignore_index=True)
                wrote_data.append(single_date.date())
        if not to_insert_df.empty:
            db_form = "db"
            db = sql.LO25DB("prod")
            schema_frame = CWGPrecipSchema(to_insert_df, form=db_form, nullable=False)
            existing_data = CWGPrecipSchema.load_sql(db, form=db_form, nullable=False)
            if existing_data is not None and not existing_data.empty:
                try:
                    upsert_df = get_rows_to_upsert(schema_frame, existing_data, key_cols=["date", "station"])
                except Exception as e:
                    raise e
                updates_df = upsert_df[upsert_df["update_type"] == "updated"]
                inserts_df = upsert_df[upsert_df["update_type"] == "new"]
                if not updates_df.empty:
                    log.info(f"Updating {len(updates_df)} rows in {table_name}")
                    raise NotImplementedError("Photographed cwg_precip_data.py line 99 has clipped save_sql arguments")
                if not inserts_df.empty:
                    log.info(f"Inserting {len(inserts_df)} rows in {table_name}")
                    raise NotImplementedError("Photographed cwg_precip_data.py line 102 has clipped save_sql arguments")
