"""Prophet time-series forecasting helpers."""

from __future__ import annotations

import pandas as pd
from prophet import Prophet

_PROPHET_HOLIDAY_COLUMNS = ("holiday", "ds", "lower_window", "upper_window", "prior_scale")


def _normalize_prophet_history(df: pd.DataFrame) -> pd.DataFrame:
    """Return Prophet-ready history with columns ``ds`` and ``y``."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")
    if df.empty:
        raise ValueError("df must not be empty.")

    if {"ds", "y"}.issubset(df.columns):
        history = df.loc[:, ["ds", "y"]].copy()
    elif isinstance(df.index, pd.DatetimeIndex):
        if "y" in df.columns:
            history = pd.DataFrame({"ds": df.index, "y": df["y"]})
        elif len(df.columns) == 1:
            history = pd.DataFrame({"ds": df.index, "y": df.iloc[:, 0]})
        else:
            raise ValueError('df must contain "y" when using a datetime index with multiple columns.')
    else:
        raise ValueError('df must provide either columns {"ds", "y"} or a DatetimeIndex with one value column.')

    history["ds"] = pd.to_datetime(history["ds"], errors="coerce")
    if history["ds"].isna().any():
        raise ValueError('df["ds"] contains invalid timestamps.')
    if isinstance(history["ds"].dtype, pd.DatetimeTZDtype):
        history["ds"] = history["ds"].dt.tz_convert(None)

    history["y"] = pd.to_numeric(history["y"], errors="coerce")
    if history["y"].isna().any():
        raise ValueError('df["y"] contains non-numeric values.')

    history = history.sort_values("ds").reset_index(drop=True)
    if history["ds"].duplicated().any():
        raise ValueError('df["ds"] must be unique.')
    return history


def _normalize_prophet_holidays(holidays: pd.DataFrame | None) -> pd.DataFrame | None:
    """Normalize holiday inputs to Prophet's expected schema."""
    if holidays is None:
        return None
    if not isinstance(holidays, pd.DataFrame):
        raise TypeError("holidays must be a pandas DataFrame or None.")
    if len(holidays.index) == 0:
        return None

    out = holidays.copy()

    if "ds" not in out.columns:
        if isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index().rename(columns={out.index.name or "index": "ds"})
        else:
            aliases = ("date", "datetime", "timestamp", "time")
            alias_col = next((alias for alias in aliases if alias in out.columns), None)
            if alias_col is not None:
                out = out.rename(columns={alias_col: "ds"})
            else:
                non_holiday_cols = [c for c in out.columns if c != "holiday"]
                if len(non_holiday_cols) == 1:
                    out = out.rename(columns={non_holiday_cols[0]: "ds"})
                else:
                    raise ValueError('holidays must contain "ds", a date-like alias, or use a DatetimeIndex.')

    out["ds"] = pd.to_datetime(out["ds"], errors="coerce")
    if out["ds"].isna().any():
        raise ValueError('holidays["ds"] contains invalid timestamps.')
    if isinstance(out["ds"].dtype, pd.DatetimeTZDtype):
        out["ds"] = out["ds"].dt.tz_convert(None)
    out["ds"] = out["ds"].dt.normalize()

    if "holiday" not in out.columns:
        out["holiday"] = "holiday"
    else:
        out["holiday"] = out["holiday"].astype("string").fillna("holiday").str.strip()
        out.loc[out["holiday"] == "", "holiday"] = "holiday"

    has_lower = "lower_window" in out.columns
    has_upper = "upper_window" in out.columns
    if has_lower or has_upper:
        if not has_lower:
            out["lower_window"] = 0
        if not has_upper:
            out["upper_window"] = 0

        for col in ("lower_window", "upper_window"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
            if out[col].isna().any():
                raise ValueError(f'holidays["{col}"] contains non-numeric values.')

        if (out["lower_window"] > 0).any():
            raise ValueError('holidays["lower_window"] must be <= 0.')
        if (out["upper_window"] < 0).any():
            raise ValueError('holidays["upper_window"] must be >= 0.')

        out["lower_window"] = out["lower_window"].astype(int)
        out["upper_window"] = out["upper_window"].astype(int)

    if "prior_scale" in out.columns:
        out["prior_scale"] = pd.to_numeric(out["prior_scale"], errors="coerce")
        if out["prior_scale"].isna().any():
            raise ValueError('holidays["prior_scale"] contains non-numeric values.')
        if (out["prior_scale"] <= 0).any():
            raise ValueError('holidays["prior_scale"] must be > 0.')

    keep_cols = [c for c in _PROPHET_HOLIDAY_COLUMNS if c in out.columns]
    out = out.loc[:, keep_cols].sort_values(["ds", "holiday"]).reset_index(drop=True)
    return out


def _normalize_prophet_history_with_regressor(df: pd.DataFrame, regressor: str = "x") -> pd.DataFrame:
    """Return Prophet-ready history with ``ds``, ``y`` and one numeric regressor."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")
    if df.empty:
        raise ValueError("df must not be empty.")

    if {"ds", "y", regressor}.issubset(df.columns):
        history = df.loc[:, ["ds", "y", regressor]].copy()
    elif isinstance(df.index, pd.DatetimeIndex):
        if regressor not in df.columns:
            raise ValueError(f'df must contain regressor column "{regressor}".')
        if "y" in df.columns:
            y_values = df["y"]
        else:
            value_cols = [c for c in df.columns if c != regressor]
            if len(value_cols) != 1:
                raise ValueError(
                    f'df must contain "y" or exactly one non-regressor value column when regressor="{regressor}".'
                )
            y_values = df[value_cols[0]]
        history = pd.DataFrame({"ds": df.index, "y": y_values, regressor: df[regressor]})
    else:
        raise ValueError(
            f'df must provide columns {{"ds", "y", "{regressor}"}} or a DatetimeIndex with regressor data.'
        )

    history["ds"] = pd.to_datetime(history["ds"], errors="coerce")
    if history["ds"].isna().any():
        raise ValueError('df["ds"] contains invalid timestamps.')
    if isinstance(history["ds"].dtype, pd.DatetimeTZDtype):
        history["ds"] = history["ds"].dt.tz_convert(None)

    history["y"] = pd.to_numeric(history["y"], errors="coerce")
    if history["y"].isna().any():
        raise ValueError('df["y"] contains non-numeric values.')
    history[regressor] = pd.to_numeric(history[regressor], errors="coerce")
    if history[regressor].isna().any():
        raise ValueError(f'df["{regressor}"] contains non-numeric values.')

    history = history.sort_values("ds").reset_index(drop=True)
    if history["ds"].duplicated().any():
        raise ValueError('df["ds"] must be unique.')
    return history


def _normalize_prophet_regressor_forecast(
    forecast_x: pd.DataFrame | pd.Series | None, regressor: str = "x"
) -> pd.DataFrame | None:
    """Normalize future regressor values to a ``ds`` + regressor dataframe."""
    if forecast_x is None:
        return None

    if isinstance(forecast_x, pd.Series):
        if not isinstance(forecast_x.index, pd.DatetimeIndex):
            raise ValueError("forecast_x series must use a DatetimeIndex.")
        out = pd.DataFrame({"ds": forecast_x.index, regressor: forecast_x.values})
    elif isinstance(forecast_x, pd.DataFrame):
        if forecast_x.empty:
            return None
        out = forecast_x.copy()
        if "ds" not in out.columns:
            if isinstance(out.index, pd.DatetimeIndex):
                out = out.reset_index().rename(columns={out.index.name or "index": "ds"})
            else:
                aliases = ("date", "datetime", "timestamp", "time")
                alias_col = next((alias for alias in aliases if alias in out.columns), None)
                if alias_col is not None:
                    out = out.rename(columns={alias_col: "ds"})
                else:
                    raise ValueError('forecast_x must contain "ds", a date-like alias, or use a DatetimeIndex.')

        if regressor not in out.columns:
            non_ds_cols = [c for c in out.columns if c != "ds"]
            if len(non_ds_cols) != 1:
                raise ValueError(
                    f'forecast_x must contain regressor column "{regressor}" or exactly one non-date column.'
                )
            out = out.rename(columns={non_ds_cols[0]: regressor})
        out = out.loc[:, ["ds", regressor]]
    else:
        raise TypeError("forecast_x must be a pandas DataFrame, Series, or None.")

    out["ds"] = pd.to_datetime(out["ds"], errors="coerce")
    if out["ds"].isna().any():
        raise ValueError('forecast_x["ds"] contains invalid timestamps.')
    if isinstance(out["ds"].dtype, pd.DatetimeTZDtype):
        out["ds"] = out["ds"].dt.tz_convert(None)
    out[regressor] = pd.to_numeric(out[regressor], errors="coerce")
    if out[regressor].isna().any():
        raise ValueError(f'forecast_x["{regressor}"] contains non-numeric values.')

    out = out.sort_values("ds").reset_index(drop=True)
    if out["ds"].duplicated().any():
        raise ValueError('forecast_x["ds"] must be unique.')
    return out


def forecast_ts(df: pd.DataFrame, holidays: pd.DataFrame | None = None, forecasting_periods: int = 366) -> pd.DataFrame:
    """Fit Prophet on ``df`` and return the full forecast dataframe."""
    if forecasting_periods < 0:
        raise ValueError("forecasting_periods must be >= 0.")

    history = _normalize_prophet_history(df)
    holidays_normalized = _normalize_prophet_holidays(holidays)

    model = Prophet(holidays=holidays_normalized)
    model.fit(history)
    future = model.make_future_dataframe(periods=int(forecasting_periods))
    prediction = model.predict(future)
    prediction.set_index("ds", inplace=True)
    return prediction


def forecast_ts_with_regression(
    df: pd.DataFrame,
    holidays: pd.DataFrame | None = None,
    start: str | pd.Timestamp | None = None,
    forecasting_periods: int = 0,
    forecast_x: pd.DataFrame | pd.Series | None = None,
    regressor: str = "x",
) -> pd.DataFrame:
    """Fit Prophet with one external regressor and return predictions."""
    if forecasting_periods < 0:
        raise ValueError("forecasting_periods must be >= 0.")

    history = _normalize_prophet_history_with_regressor(df=df, regressor=regressor)
    forecast_reg = _normalize_prophet_regressor_forecast(forecast_x=forecast_x, regressor=regressor)

    if int(forecasting_periods) > 0 and forecast_reg is None:
        raise ValueError("forecast_x is required when forecasting_periods > 0 for regression forecasts.")

    holidays_normalized = _normalize_prophet_holidays(holidays)
    model = Prophet(holidays=holidays_normalized)
    model.add_regressor(regressor)
    model.fit(history)
    future = model.make_future_dataframe(periods=int(forecasting_periods))

    future = future.merge(history[["ds", regressor]], how="left", on="ds")
    if forecast_reg is not None:
        future = future.merge(forecast_reg.rename(columns={regressor: "_forecast_reg"}), how="left", on="ds")
        future[regressor] = future[regressor].fillna(future["_forecast_reg"])
        future = future.drop(columns=["_forecast_reg"])

    missing_mask = future[regressor].isna()
    if missing_mask.any():
        missing_dates = future.loc[missing_mask, "ds"].head(3).dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(f'Missing regressor values for "{regressor}" at dates: {missing_dates}')

    prediction = model.predict(future)
    prediction.set_index("ds", inplace=True)
    if start is not None:
        start_ts = pd.to_datetime(start, errors="coerce")
        if pd.isna(start_ts):
            raise ValueError("start must be parseable as datetime.")
        if isinstance(start_ts, pd.Timestamp) and start_ts.tzinfo is not None:
            start_ts = start_ts.tz_convert(None)
        prediction = prediction.loc[prediction.index >= start_ts]

    return prediction
