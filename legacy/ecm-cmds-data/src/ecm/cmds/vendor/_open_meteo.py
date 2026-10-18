import re
import typing as tp
from io import BytesIO

import airportsdata
import ecm.atom.parse.types as at
import pandas as pd
import requests
from dateutil.tz import gettz as tzinfo
from ecm.cmds.core.cdr import today
from ecm.cmds.vendor._stormvista import _circular_mean_deg
from loguru import logger as log

_AVAILABLE_HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "pressure_msl",
    "surface_pressure",
    "precipitation",
    "rain",
    "snowfall",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "shortwave_radiation",
    "direct_radiation",
    "direct_normal_irradiance",
    "diffuse_radiation",
    "global_tilted_irradiance",
    "sunshine_duration",
    "wind_speed_10m",
    "wind_speed_100m",
    "wind_direction_10m",
    "wind_direction_100m",
    "wind_gusts_10m",
    "et0_fao_evapotranspiration",
    "weather_code",
    "snow_depth",
    "vapour_pressure_deficit",
    "soil_temperature_0_to_7cm",
    "soil_temperature_7_to_28cm",
    "soil_temperature_28_to_100cm",
    "soil_temperature_100_to_255cm",
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm",
    "soil_moisture_100_to_255cm",
]

_AVAILABLE_DAILY_VARS = [
    "weather_code",  # WMO code for dominant condition
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "sunrise",
    "sunset",
    "sunshine_duration",
    "daylight_duration",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
]


class OpenMeteoClient:
    BASE_URL_FCST = "https://api.open-meteo.com/v1/forecast"
    BASE_URL_HIST = "https://archive-api.open-meteo.com/v1/archive"
    PREV_BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
    FCST_META_URL = "https://api.open-meteo.com/data/ecmwf_ifs/static/meta.json"

    _airport_db = airportsdata.load()

    def __init__(
        self,
        icao: str,
        lat: str = None,
        lng: str = None,
        timezone: str = "Europe/London",
        hourly_vars: tp.Optional[tp.List[str]] = None,
        daily_vars: tp.Optional[tp.List[str]] = None,
        historical: bool = True,
        fcst_days: int = 14,
        model: str = "ecmwf_ifs",
        run: str = "00z",
        start_date: str = None,
        end_date: str = None,
        returns: str = "daily",
    ):
        if returns not in ["hourly", "daily"]:
            raise ValueError("returns must be either 'hourly' or 'daily'")
        icao = icao.upper()
        if icao not in self._airport_db and (lat is None or lng is None):
            raise ValueError(
                f"ICAO code {icao} not found in airport database and lat/lng not provided."
            )
        if start_date is None:
            if not historical:
                start_date = today().strftime("%Y-%m-%d")
            else:
                start_date = (
                    pd.Timestamp.now(tz=tzinfo(timezone)) - pd.Timedelta(days=7)
                ).strftime("%Y-%m-%d")
        if end_date is None:
            if historical:
                end_date = pd.Timestamp.now(tz=tzinfo(timezone)).strftime("%Y-%m-%d")
            else:
                end_date = (
                    pd.Timestamp.now(tz=tzinfo(timezone)) + pd.Timedelta(days=fcst_days)
                ).strftime("%Y-%m-%d")
        if fcst_days < 1 or fcst_days > 14:
            raise ValueError("fcst_days must be between 1 and 14 inclusive.")

        self.start_date = self._normalise_datetime(start_date)
        self.end_date = self._normalise_datetime(end_date)
        if icao in self._airport_db:
            airport = self._airport_db[icao]
            self.latitude = airport["lat"]
            self.longitude = airport["lon"]
        else:
            self.latitude = lat
            self.longitude = lng
        if hourly_vars and daily_vars:
            raise ValueError(
                "Cannot pass both hourly_vars and daily_vars. Please pass only one option."
            )
        self.daily = False
        self.hourly = True
        self.model = model
        if hourly_vars:
            self.hourly_vars = hourly_vars
            self.daily = False
        elif daily_vars:
            self.daily_vars = daily_vars
            self.hourly = False
        else:
            self.hourly_vars = ["temperature_2m", "precipitation", "dew_point_2m"]
            self.hourly = True
        self._verify_vars()
        self.historical = historical
        if self.historical:
            self.BASE_URL = self.BASE_URL_HIST
            self.run = None
            self.fcst_days = None
        else:
            self.run = run
            self.fcst_days = fcst_days
            self.BASE_URL = self.BASE_URL_FCST
        self.timezone = timezone
        self.returns = returns

    def _normalise_datetime(self, dt: at.TimestampLike) -> str:
        return pd.to_datetime(dt).strftime("%Y-%m-%d")

    def _ts_or_nat(self, x):
        return pd.to_datetime(x, unit="s", utc=True) if x is not None else pd.NaT

    def _utc_now(self):
        return pd.Timestamp.now(tz="UTC")

    def _utc_today(self):
        return self._utc_now().normalize()

    def _latest_available_fcst_model_run(
        self,
    ) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp, int | None]:
        resp = requests.get(self.FCST_META_URL, verify=False)
        resp.raise_for_status()
        m = resp.json()

        init = self._ts_or_nat(m.get("last_run_initialisation_time"))
        avail = self._ts_or_nat(m.get("last_run_availability_time"))
        mod = self._ts_or_nat(m.get("last_run_modification_time"))
        dend = self._ts_or_nat(m.get("data_end_time"))
        upint = m.get("update_interval_seconds")  # e.g., 21600 (6h)

        log.debug(f"FCST meta: init={init}, avail={avail}, mod={mod}, end={dend}, upint={upint}")
        return init, avail, mod, dend, upint

    def _is_forecast_ready(self) -> bool:
        if self.run is None:
            return False
        now_utc = self._utc_now()
        expected_init = pd.to_datetime(f"{self.start_date}T{self.run}", utc=True)
        target_hour: int = int(self.run[:2])

        if now_utc < expected_init:
            return False

        init, avail, mod, dend, _ = self._latest_available_fcst_model_run()

        if (
            pd.isna(init)
            or init.normalize() != expected_init.normalize()
            or init.hour != target_hour
        ):
            return False

        min_span = pd.Timedelta(hours=6)

        def span_ok():
            return pd.isna(dend) or dend >= init + min_span

        if pd.notna(avail) and avail > init and now_utc >= avail and span_ok():
            return True

        if pd.notna(mod) and mod > init and now_utc >= mod and span_ok():
            return True

        return False

    def _verify_vars(self):
        if self.hourly:
            invalid_vars = [var for var in self.hourly_vars if var not in _AVAILABLE_HOURLY_VARS]
            if invalid_vars:
                avail_vars = "\n" + "\n".join(_AVAILABLE_HOURLY_VARS)
                raise ValueError(
                    f"Invalid hourly variables: {invalid_vars}, available:{avail_vars}"
                )
        if self.daily:
            invalid_vars = [var for var in self.daily_vars if var not in _AVAILABLE_DAILY_VARS]
            if invalid_vars:
                avail_vars = "\n" + "\n".join(_AVAILABLE_DAILY_VARS)
                raise ValueError(f"Invalid daily variables: {invalid_vars},available:{avail_vars}")

    def _norm_om_name(self, name: str) -> str:
        s = str(name)
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
        s = re.sub(r"_previous_(?:day|hour)\d+$", "", s)
        return s

    def fetch_weather_data(self) -> pd.DataFrame:
        if not self.historical:
            if not self._is_forecast_ready():
                raise ValueError("Forecast data is not yet available for the latest model run.")
        log.info(f"Fetching weather data for lat={self.latitude}, lon={self.longitude}")
        if self.historical:
            params = {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "timezone": self.timezone,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "format": "xlsx",
                "hourly"
                if self.hourly
                else "daily": ",".join(self.hourly_vars if self.hourly else self.daily_vars),
            }
            rqst_url = self.BASE_URL
        else:
            params = {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "timezone": self.timezone,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "models": self.model,
                "format": "xlsx",
                "hourly"
                if self.hourly
                else "daily": ",".join(self.hourly_vars if self.hourly else self.daily_vars),
            }
            rqst_url = self.BASE_URL
        response = requests.get(rqst_url, params=params, verify=False)
        response.raise_for_status()
        metadata_dict = pd.read_excel(BytesIO(response.content)).iloc[0:1].to_dict("records")[0]
        self.metadata = metadata_dict
        weather_df_raw = pd.read_excel(BytesIO(response.content), header=3)
        weather_df_raw = weather_df_raw.dropna(how="all", axis=1)
        df = weather_df_raw
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")
        df.columns = [self._norm_om_name(c) for c in df.columns]
        if self.returns == "daily" and not self.daily:
            processed_df = self.process_weather_data(df)
        else:
            processed_df = df
        if not self.historical:
            processed_df["run_date"] = pd.to_datetime(self.start_date, utc=True).date()
            if self.returns == "daily":
                processed_df.index.name = "fcst_date"
                processed_df = processed_df.reset_index().set_index(["run_date", "fcst_date"])
            else:
                processed_df.index.name = "time"
        return processed_df

    def fetch_previous_runs_00z(
        self,
        days_back: int = 7,  # up to 7 per Open-Meteo docs/UI
        vars_override: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        is_backfill: bool = False,
    ) -> pd.DataFrame:
        """
        Build a daily 00Z 'previous runs' panel:
        index: valid_time at 00:00Z
        columns: <var>_previous_day1 .. <var>_previous_dayN (plus <var> Day0 if requested)
        """

        def _parse_prev_col(name: str):
            s = name.split(" ")[0]  # drop units if any
            for tag in ["_previous_day"]:
                if tag in s:
                    var, _, n = s.partition(tag)
                    return var, int(n)
            return s, 0  # no previous_* suffix

        if vars_override:
            vars_base = vars_override
        elif self.hourly:
            vars_base = self.hourly_vars
        else:
            raise ValueError(
                "Use hourly variables for previous-runs (daily vars not supported here)."
            )

        hourly_list = []
        for v in vars_base:
            hourly_list.append(v)  # Day0 (optional if you also want today's forecast)
            hourly_list.extend([f"{v}_previous_day{i}" for i in range(1, days_back + 1)])

        start = pd.to_datetime(start_date or self.start_date).strftime("%Y-%m-%d")
        end = pd.to_datetime(end_date or self.end_date).strftime("%Y-%m-%d")
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": ",".join(hourly_list),
            "timezone": "UTC",
        }
        if not is_backfill:
            params["models"] = self.model
        else:
            params["start_date"] = start
            params["end_date"] = end

        url = self.PREV_BASE_URL
        params["format"] = "xlsx"
        r = requests.get(url, params=params, verify=False)
        r.raise_for_status()
        df = pd.read_excel(BytesIO(r.content), header=3)

        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")

        long_df = {}
        for col in df.columns:
            var, dback = _parse_prev_col(col)
            dt_col = pd.to_datetime(start, utc=True) - pd.Timedelta(days=dback)
            if var is None:
                continue  # skip non-data columns if any
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if s.empty:
                continue
            df_part = pd.DataFrame(columns=["run_date", var], index=pd.to_datetime(s.index))
            df_part.index.name = "fcst_date"
            df_part[var] = s.values
            df_part["run_date"] = dt_col.date()
            df_part = df_part.reset_index().set_index(["fcst_date", "run_date"])
            if var not in long_df:
                long_df[var] = df_part
            else:
                col_frame = long_df[var]
                long_df[var] = pd.concat([col_frame, df_part], axis=0)
        fcst_df = pd.concat([y[x] for x, y in long_df.items()], axis=1)
        fcst_df = fcst_df.reset_index().set_index("fcst_date")
        processed_df = (
            fcst_df.groupby("run_date")
            .apply(self.process_weather_data)
            .reset_index()
            .set_index("run_date")
        )
        processed_df["fcst_date"] = processed_df["fcst_date"].dt.tz_localize(None)
        return processed_df

    def fetch_metadata(self) -> dict:
        if not hasattr(self, "metadata"):
            self.fetch_weather_data()
        return self.metadata

    def _sum_daily(series: pd.Series) -> pd.Series:
        return series.resample("D").sum()

    def _mean_daily(series: pd.Series) -> pd.Series:
        return series.resample("D").mean()

    _processing_map = {
        "wind_direction_10m": _circular_mean_deg,
        "precipitation": _sum_daily,
        "rain": _sum_daily,
        "snowfall": _sum_daily,
        "temperature_2m": _mean_daily,
        "dew_point_2m": _mean_daily,
        "wind_speed_10m": _mean_daily,
    }

    def process_weather_data(self, df: pd.DataFrame) -> pd.DataFrame:
        output_frame = pd.DataFrame()
        for col in df.columns:
            _col = col.split(" ")[0]  # remove units if present
            if _col == "run_date":
                continue
            if _col in self._processing_map:
                func = self._processing_map.get(_col, None)
                if func is not None:
                    output_frame[col] = func(df[col])
                else:
                    log.warning(f"No processing function for {col}, using daily mean")
                    output_frame[col] = df[col].resample("D").mean()
            else:
                log.warning(f"No processing function for {col}, using daily mean")
                output_frame[col] = df[col].resample("D").mean()
        return output_frame


if __name__ == "__main__":
    client_fcst = OpenMeteoClient(
        icao="RJFT",
        historical=False,
        returns="daily",
        run="00z",
        model="ecmwf_ifs",
    )
    prev_df = client_fcst.fetch_previous_runs_00z(
        start_date="2025-10-07", end_date="2025-10-13", days_back=7, is_backfill=True
    )
    print(prev_df.to_string())
