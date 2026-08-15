from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import runbook.core.timeseries.forecasting as forecasting


def test_normalize_prophet_holidays_uses_datetime_index_and_default_name() -> None:
    raw = pd.DataFrame(index=pd.to_datetime(["2025-01-01", "2025-12-25"]))
    out = forecasting._normalize_prophet_holidays(raw)

    assert out is not None
    assert list(out.columns) == ["holiday", "ds"]
    assert out["holiday"].tolist() == ["holiday", "holiday"]
    assert pd.api.types.is_datetime64_any_dtype(out["ds"])


def test_normalize_prophet_holidays_fills_missing_window_pair() -> None:
    raw = pd.DataFrame(
        {
            "ds": ["2025-01-01"],
            "holiday": ["new_year"],
            "upper_window": [2],
        }
    )
    out = forecasting._normalize_prophet_holidays(raw)

    assert out is not None
    assert out.loc[0, "lower_window"] == 0
    assert out.loc[0, "upper_window"] == 2


def test_normalize_prophet_holidays_rejects_invalid_lower_window() -> None:
    raw = pd.DataFrame({"ds": ["2025-01-01"], "holiday": ["bad"], "lower_window": [1], "upper_window": [2]})
    with pytest.raises(ValueError, match="lower_window"):
        forecasting._normalize_prophet_holidays(raw)


def test_forecast_ts_normalizes_inputs_before_prophet(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyProphet:
        last_instance: "DummyProphet | None" = None

        def __init__(self, holidays: pd.DataFrame | None = None):
            self.holidays = holidays
            self.history: pd.DataFrame | None = None
            DummyProphet.last_instance = self

        def fit(self, history: pd.DataFrame):
            self.history = history.copy()
            return self

        def make_future_dataframe(self, periods: int):
            assert self.history is not None
            last_ds = pd.Timestamp(self.history["ds"].iloc[-1])
            return pd.DataFrame({"ds": pd.date_range(start=last_ds, periods=periods + 1, freq="D")})

        def predict(self, future: pd.DataFrame):
            out = future.copy()
            out["yhat"] = np.arange(len(out), dtype=float)
            return out

    monkeypatch.setattr(forecasting, "Prophet", DummyProphet)

    history = pd.DataFrame({"value": [2.0, 1.0]}, index=pd.to_datetime(["2025-01-02", "2025-01-01"]))
    holidays = pd.DataFrame({"date": ["2025-01-20"], "holiday": ["mlk"]})

    out = forecasting.forecast_ts(history, holidays=holidays, forecasting_periods=2)
    model = DummyProphet.last_instance
    assert model is not None
    assert model.history is not None
    assert list(model.history.columns) == ["ds", "y"]
    assert model.history["ds"].is_monotonic_increasing

    assert model.holidays is not None
    assert list(model.holidays.columns) == ["holiday", "ds"]
    assert model.holidays.loc[0, "holiday"] == "mlk"

    assert "yhat" in out.columns
    assert len(out) == 3


def test_forecast_ts_with_regression_requires_future_regressor_for_future_periods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyProphet:
        def __init__(self, holidays: pd.DataFrame | None = None):
            self.holidays = holidays

        def add_regressor(self, _: str):
            return self

        def fit(self, _: pd.DataFrame):
            return self

        def make_future_dataframe(self, periods: int):
            return pd.DataFrame({"ds": pd.date_range("2025-01-01", periods=periods + 2, freq="D")})

        def predict(self, future: pd.DataFrame):
            return future

    monkeypatch.setattr(forecasting, "Prophet", DummyProphet)
    history = pd.DataFrame({"y": [1.0, 2.0], "x": [10.0, 11.0]}, index=pd.to_datetime(["2025-01-01", "2025-01-02"]))

    with pytest.raises(ValueError, match="forecast_x is required"):
        forecasting.forecast_ts_with_regression(history, forecasting_periods=1)


def test_forecast_ts_with_regression_uses_history_and_future_regressor_values(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyProphet:
        last_instance: "DummyProphet | None" = None

        def __init__(self, holidays: pd.DataFrame | None = None):
            self.holidays = holidays
            self.history: pd.DataFrame | None = None
            self.future: pd.DataFrame | None = None
            self.regressor_name: str | None = None
            DummyProphet.last_instance = self

        def add_regressor(self, name: str):
            self.regressor_name = name
            return self

        def fit(self, history: pd.DataFrame):
            self.history = history.copy()
            return self

        def make_future_dataframe(self, periods: int):
            assert self.history is not None
            first = pd.Timestamp(self.history["ds"].iloc[0])
            return pd.DataFrame({"ds": pd.date_range(start=first, periods=len(self.history) + periods, freq="D")})

        def predict(self, future: pd.DataFrame):
            self.future = future.copy()
            out = future.copy()
            out["yhat"] = np.arange(len(out), dtype=float)
            return out

    monkeypatch.setattr(forecasting, "Prophet", DummyProphet)

    history = pd.DataFrame(
        {"y": [1.0, 2.0], "x": [10.0, 11.0]},
        index=pd.to_datetime(["2025-01-01", "2025-01-02"]),
    )
    forecast_x = pd.DataFrame({"ds": ["2025-01-03", "2025-01-04"], "x": [12.0, 13.0]})

    out = forecasting.forecast_ts_with_regression(
        history,
        forecasting_periods=2,
        forecast_x=forecast_x,
        start="2025-01-02",
    )
    model = DummyProphet.last_instance
    assert model is not None
    assert model.regressor_name == "x"
    assert model.history is not None
    assert list(model.history.columns) == ["ds", "y", "x"]
    assert model.future is not None
    assert model.future["x"].tolist() == [10.0, 11.0, 12.0, 13.0]
    assert out.index.min() == pd.Timestamp("2025-01-02")
