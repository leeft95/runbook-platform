from datetime import datetime, timedelta
import pandas as pd
import datetime as dt
import pandas as pd
import numpy as np
from loguru import logger as log
from ecm.cmds.cdr import today, now_ldn
from ecm.cmds.vendor._open_meteo import OpenMeteoClient
from ecm.atom.schema import ECMSchema, field
from ecm.cmds.utils import get_rows_to_upsert
import ecm.cmds.sql as sql


def accurate_forecast_backfill(icao, start_date, end_date, validate=True):
    """
    Accurate backfill with validation and error handling
    """
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    all_forecasts = []
    missing_runs = []

    current_date = start_dt
    while current_date <= end_dt:
        try:
            client = OpenMeteoClient(
                icao=icao,
                historical=False,
                start_date=current_date.strftime("%Y-%m-%d"),
                end_date=(current_date + timedelta(days=14)).strftime("%Y-%m-%d"),
                returns="daily",
                run="00z",
                model="ecmwf_ifs",
                hourly_vars=["temperature_2m", "precipitation", "dew_point_2m"]
            )

            forecast_df = client.fetch_previous_runs_00z(
                start_date=current_date.strftime("%Y-%m-%d"),
                end_date=(current_date + timedelta(days=14)).strftime("%Y-%m-%d"),
                days_back=1,  # Just get this run
                is_backfill=True
            )

            if not forecast_df.empty:
                forecast_df['run_date_explicit'] = current_date.date()
                all_forecasts.append(forecast_df)
                print(f"✓ {current_date.strftime('%Y-%m-%d')}: {len(forecast_df)} forecast days")
            else:
                missing_runs.append(current_date.strftime('%Y-%m-%d'))
                print(f"X {current_date.strftime('%Y-%m-%d')}: No data")

        except Exception as e:
            missing_runs.append(current_date.strftime('%Y-%m-%d'))
            print(f"X {current_date.strftime('%Y-%m-%d')}: Error - {e}")

        current_date += timedelta(days=1)

    if all_forecasts:
        combined_df = pd.concat(all_forecasts, ignore_index=False)

        if validate:
            print(f"\n=== VALIDATION ===")
            print(f"Expected runs: {(end_dt - start_dt).days + 1}")
            print(f"Successful runs: {len(all_forecasts)}")
            print(f"Missing runs: {missing_runs}")
            print(f"Total forecast records: {len(combined_df)}")

            expected_runs = pd.date_range(start_date, end_date, freq='D')
            for run_date in expected_runs:
                run_data = combined_df[combined_df.index.get_level_values(0) == run_date.date()]
                print(f"  {run_date.strftime('%Y-%m-%d')}: {len(run_data)} forecast days")

        return combined_df, missing_runs
    else:
        print("No forecast data retrieved!")
        return pd.DataFrame(), missing_runs
