import ecm.cmds.stormvista as sv
import datetime as dt
import pandas as pd
import ecm.cmds.sql as sql
from ecm.cmds.core.cdr import today
from ecm.cmds.config import data_path
from ecm.cmds.utils import convert_path_to_linux
from pathlib import Path


def get_table_name(model):
    if model == "ecmwf-eps":
        return "CWG_StormVista_StationFcst_EC"
    elif model == "gfs":
        return "CWG_StormVista_StationFcst_GFS"
    else:
        raise ValueError("Unsupported model. Use 'ecmwf-eps' or 'gfs'.")

stations_default = ['ZBAA', 'RKSS', 'RJTT', 'VIDP', 'HECA', 'OMDB']

station_tracker_csv = convert_path_to_linux(f"{data_path}/weather/stormvista_station_download_tracker.csv")


def update(stations, cycle="00", model="ecmwf-eps"):
    table_name = get_table_name(model)
    tracker_path = Path(station_tracker_csv)
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    if tracker_path.exists():
        tracker_df = pd.read_csv(tracker_path, parse_dates=["last_date"])
    else:
        tracker_df = pd.DataFrame(columns=["station", "last_date", "model", "cycle"])

    today_dt = pd.to_datetime(today()).date()

    for st in stations:
        mask = (tracker_df["station"] == st) & (tracker_df["model"] == model) & (tracker_df["cycle"] == cycle)
        st_down_info = tracker_df[mask]
        if not st_down_info.empty and pd.notnull(st_down_info.iloc[0]["last_date"]):
            last_date = pd.to_datetime(st_down_info.iloc[0]["last_date"]).date()
        else:
            last_date = None

        if last_date == today_dt:
            print(f"Station {st} for model {model} cycle {cycle} is already up to date.")
            continue

        try:
            max_date_df = sql.read_sql(
                f"SELECT MAX([date]) AS max_date FROM {table_name} WHERE Cycle='{cycle}' AND station = '{st}'"
            )
        except Exception as e:
            print(f"SQL error while checking max date for {st}: {e}")
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
            start_date = max_date_val + dt.timedelta(days=1)
        else:
            start_date = dt.date(2024, 8, 17)

        end_date = today_dt

        if start_date <= end_date:
            date_range = pd.date_range(start=start_date, end=end_date, freq="D")
            to_insert_df = pd.DataFrame()
            for single_date in date_range:
                try:
                    data = sv.get_data_by_station(model=model, cycle=cycle, station=st, file_date=single_date)
                except Exception as e:
                    print(f"Error fetching data for {st} on {single_date.date()}: {e}")
                    data = pd.DataFrame()
                if not data.empty:
                    to_insert_df = pd.concat([to_insert_df, data], ignore_index=True)
            if not to_insert_df.empty:
                try:
                    sql.to_sql(to_insert_df, table_name, index=False)
                except Exception as e:
                    print(f"Error writing data for {st} to SQL table {table_name}: {e}")

        if mask.any():
            tracker_df.loc[mask, "last_date"] = pd.to_datetime(today_dt)
            tracker_df.loc[mask, "model"] = model
            tracker_df.loc[mask, "cycle"] = cycle
        else:
            new_row = {"station": st, "last_date": pd.to_datetime(today_dt), "model": model, "cycle": cycle}
            tracker_df = pd.concat([tracker_df, pd.DataFrame([new_row])], ignore_index=True)

    tracker_df.to_csv(tracker_path, index=False)
    return


if __name__ == "__main__":
    update(stations=stations_default)
