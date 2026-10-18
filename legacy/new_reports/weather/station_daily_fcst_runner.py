import datetime as dt
from pathlib import Path

import pandas as pd

import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today, now_ldn
from ecm.cmds.config import data_path
from ecm.cmds.utils import convert_path_to_linux, get_rows_to_upsert
from loguru import logger as log
from ecm.atom.schema import ECMSchema, field
import numpy as np

def get_table_name(model):
    if model == "ecmwf-eps":
        return "CWG_StormVista_StationFcst_EC"
    elif model == "gfs":
        return "CWG_StormVista_StationFcst_GFS"
    else:
        raise ValueError("Unsupported model. Use 'ecmwf-eps' or 'gfs'.")


stations_default = ["ZBAA", "RKSS", "RJTT", "VIDP", "HECA", "OMDB", "ZGGG", "ZPPP", "RJFT", "RKSO", "RKTU", ...]

station_tracker_csv = convert_path_to_linux(f"{data_path}/weather/stormvista_station_download_tracker.csv")
db = sql.LO25DB("prod")

class StationFcstSchema(ECMSchema, ecmwf_eps="dbo.CWG_StormVista_StationFcst_EC", gfs="dbo.CWG_StormVista_StationFcst_GFS"):
    date: np.datetime64 = field(
        index=0,
        allow_null=False,
    )
    cycle: str = field(
        allow_null=False,
        index=1,
    )
    station: str = field(
        allow_null=False,
        index=2,
    )
    fcst_date: np.datetime64 = field(
        allow_null=False,
        index=3,
    )
    tmp2m: float = field(allow_null=True)
    tmin2m: float = field(allow_null=True)
    tmax2m: float = field(allow_null=True)
    precip: float = field(allow_null=True)
    dpt2m: float = field(allow_null=True)
    heatindex: float = field(allow_null=True)
    tmp850: float = field(allow_null=True)
    windchill: float = field(allow_null=True)
    windspeed10: float = field(allow_null=True)
    winddirection10: float = field(allow_null=True)
    windspeed80: float = field(allow_null=True)
    snow: float = field(allow_null=True)
    hgt500: float = field(allow_null=True)
    mslp: float = field(allow_null=True)
    cloudtotal: float = field(allow_null=True)
    winddirection80: float = field(allow_null=True)



def update(stations, cycle="00", model="ecmwf-eps"):
    table_name = get_table_name(model)
    tracker_path = Path(station_tracker_csv)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    if tracker_path.exists():
        tracker_df = pd.read_csv(tracker_path, parse_dates=["last_date"])  # type: ignore[arg-type]
    else:
        tracker_df = pd.DataFrame(columns=["station", "last_date", "model", "cycle"])

    today_dt = pd.to_datetime(today()).date()

    for st in stations:
        if st is Ellipsis:
            raise NotImplementedError("Photographed station_daily_fcst_runner.py line25 has a clipped station list")
        mask = (tracker_df["station"] == st) & (tracker_df["model"] == model) & (tracker_df["cycle"] == cycle)
        st_down_info = tracker_df[mask]
        if not st_down_info.empty and pd.notnull(st_down_info.iloc[0]["last_date"]):
            last_date = pd.to_datetime(st_down_info.iloc[0]["last_date"]).date()
        else:
            last_date = None

        try:
            max_date_df = sql.read_sql(
                f"SELECT MAX([date]) AS max_date FROM {table_name} WHERE Cycle='{cycle}' AND station = '{st}'"
            )
        except Exception as e:
            log.info(f"SQL error while checking max date for {st}: {e}")
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
            if last_date == max_date_val:
                log.info(f"Station {st} for model {model} cycle {cycle} is already up to date.")
                continue
            else:
                start_date = max_date_val + dt.timedelta(days=1)
        else:
            start_date = dt.date(2025, 6, 1)

        end_date = today_dt
        wrote_data = []
        if start_date <= end_date:
            date_range = pd.date_range(start=start_date, end=end_date, freq="D")
            to_insert_df = pd.DataFrame()
            for single_date in date_range:
                try:
                    data = sv.get_fcst_data_by_station(model=model, cycle=cycle, station=st, file_date=single_date)
                except Exception as e:
                    log.exception(f"Error fetching data for {st} on {single_date.date()}: {e}")
                    data = pd.DataFrame()
                if not data.empty:
                    data = data.drop(columns=["model"])  # already have these by the table name
                    to_insert_df = pd.concat([to_insert_df, data], ignore_index=True)
            if not to_insert_df.empty:
                try:
                    db_form = model.replace("-", "_")
                    schema_frame = StationFcstSchema(to_insert_df, form=db_form, nullable=False)
                    existing_data = StationFcstSchema.load_sql(db, form=db_form, nullable=False)
                    if existing_data is not None and not existing_data.empty:
                        try:
                            upsert_df = get_rows_to_upsert(schema_frame, existing_data, key_cols=["date", "cycle", "station", "fcst_date"])
                        except Exception as e:
                            print("break")
                        updates_df = upsert_df[upsert_df["update_type"] == "updated"]
                        updates_df = updates_df.drop(columns=["update_type"])
                        if not updates_df.empty:
                            StationFcstSchema(updates_df).dump_sql(db, form=db_form, mode="update_only")
                            log.info(f"Upserted {len(updates_df)} rows to consumption database.")
                        new_df = upsert_df[upsert_df["update_type"] == "new"]
                        new_df = new_df.drop(columns=["update_type"])
                        if not new_df.empty:
                            StationFcstSchema(new_df).dump_sql(db, form=db_form, mode="insert_first")
                            log.info(f"Inserted {len(new_df)} new rows to consumption database.")
                        else:
                            log.info("No new or updated rows to upsert for consumption.")
                    else:
                        log.info("No existing data in database, inserting all rows.")
                        schema_frame.dump_sql(db, form=db_form, mode="insert_first")

                    wrote_data.extend(list(to_insert_df['date'].unique()))
                except Exception as e:
                    log.exception(f"Error writing data for {st} to SQL table {table_name}: {e}")

        if wrote_data:
            log.info(f"Wrote dates {wrote_data} for station {st}, model {model}, cycle {cycle}")
            last_written_date = pd.to_datetime(to_insert_df['date']).dt.date.max()
            if mask.any():
                tracker_df.loc[mask, "last_date"] = pd.to_datetime(last_written_date)
                tracker_df.loc[mask, "model"] = model
                tracker_df.loc[mask, "cycle"] = cycle
            else:
                new_row = {"station": st, "last_date": pd.to_datetime(last_written_date), "model": model, "cycle": cycle}
                tracker_df = pd.concat([tracker_df, pd.DataFrame([new_row])], ignore_index=True)

    tracker_df.to_csv(tracker_path, index=False)
    return


release_times = {
    "00": [dt.time(6, 30), dt.time(8, 30)],
    "06": [dt.time(12, 30), dt.time(14, 30)],
    "12": [dt.time(18, 30), dt.time(20, 30)],
}


def runner():
    current_time = now_ldn().time().replace(microsecond=0)
    for cycle, (start, end) in release_times.items():
        if start <= current_time <= end:
            log.info(f"Running stormvista DailyStationFcst for cycle {cycle}")
            update(stations=stations_default, cycle=cycle)
        else:
            log.info(f"Not time for cycle {cycle} yet. Current time: {current_time}, waiting for window {start} - {end}")


if __name__ == "__main__":
    runner()
