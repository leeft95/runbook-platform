import pandas as pd
from ecm.cmds.core.talib import *  # noqa: F403,F401
from prophet import Prophet


def ts_forecast(data, hol=None, forecast_periods=366):
    data_ = data.copy()
    if isinstance(data_, pd.Series):
        data_ = data_.to_frame("y")
        data_.index.name = "ds"
        data_.reset_index(inplace=True)
    elif data_.shape[1] == 1:
        data_.columns = ["y"]
        data_.index.name = "ds"
        data_.reset_index(inplace=True)
    elif data_.shape[1] == 2:
        data_.columns = ["ds", "y"]
    else:
        print("too many columns")
        return pd.DataFrame()
    if hol is not None:
        m = Prophet(holidays=hol)
    else:
        m = Prophet()
    m.fit(data_)
    future = m.make_future_dataframe(periods=forecast_periods)
    forecast = m.predict(future)
    forecast.set_index("ds", inplace=True)
    return forecast


def ts_regression(data, hol=None, start=None, forecast_periods=0, forecast_x=None):
    if hol is None:
        m = Prophet()
    else:
        m = Prophet(holidays=hol)
    m.add_regressor("x")
    m.fit(data)
    future = m.make_future_dataframe(periods=forecast_periods)
    if forecast_x is None:
        if len(future.index) != len(data.index):
            future = future.set_index("ds").reindex(data.set_index("ds").index).reset_index()
        future["x"] = data["x"]
    else:
        future["x"] = pd.concat([data["x"], forecast_x], axis=0).values
    forecast = m.predict(future)
    forecast.set_index("ds", inplace=True)
    if start is None:
        return forecast
    else:
        return forecast.iloc[start:, :]
