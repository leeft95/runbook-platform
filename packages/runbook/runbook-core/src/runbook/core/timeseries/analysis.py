"timeseries analysis functions"

import calendar
import datetime as dt
import typing as tp
from enum import Enum
from typing import cast

import numpy as np
import pandas as pd
import statsmodels.api as sm
from loguru import logger as log
from scipy.optimize import minimize
from statsmodels.regression.rolling import RollingOLS

from .transforms import ts_by_year


class MovingAvgModes(str, Enum):
    """Moving average modes."""

    SIMPLE = "simple"
    EXPONENTIAL = "exponential"
    SMOOTHED = "smoothed"

    @classmethod
    def _missing_(cls, value: object) -> "MovingAvgModes | None":
        """Handle missing ."""
        if not isinstance(value, str):
            return None
        aliases = {
            "s": cls.SIMPLE,
            "e": cls.EXPONENTIAL,
            "m": cls.SMOOTHED,
        }
        return aliases.get(value.strip().lower())


class AggregationModes(str, Enum):
    "Agg modes"

    DIFF = "diffenerence"
    SUM = "Sum"
    MA = "MovingAverage"

    @classmethod
    def _missing_(cls, value: object) -> "AggregationModes | None":
        """Handle missing ."""
        if not isinstance(value, str):
            return None
        aliases = {
            "change": cls.DIFF,
            "chg": cls.DIFF,
            "mean": cls.MA,
        }
        return aliases.get(value.strip().lower())


def calculate_moving_average(
    x: pd.Series | np.ndarray | tp.List[float], window: int = 3, kind: MovingAvgModes | str = MovingAvgModes.SIMPLE
) -> pd.Series | np.ndarray | tp.List[float]:
    """Calculate the moving average of a timeseries."""
    # convert everything to numpy and calculate for effienceny
    if isinstance(kind, str):
        try:
            kind = MovingAvgModes(kind)
        except ValueError:
            raise ValueError(f"Unsupported moving average kind: {kind}")
    if isinstance(x, pd.Series):
        x_values = np.asarray(x.values, dtype=np.float64)
    elif isinstance(x, np.ndarray):
        # change to 1d array if it's not already
        if x.ndim > 1:
            x_values = np.asarray(x.flatten(), dtype=np.float64)
        else:
            x_values = np.asarray(x, dtype=np.float64)
    else:
        x_values = np.asarray(x, dtype=np.float64)
    if kind == MovingAvgModes.SIMPLE:
        weights = np.ones(window) / window
    elif kind == MovingAvgModes.EXPONENTIAL:
        weights = np.exp(np.linspace(-1.0, 0.0, window))
        weights /= weights.sum()
    elif kind == MovingAvgModes.SMOOTHED:
        # a[i] = (a[i-1] * (window - 1) + x[i]) / window
        weights = np.array([1 / window ** (i + 1) for i in range(window)])
        weights /= weights.sum()
    else:
        raise ValueError(f"Unsupported moving average kind: {kind}")
    # return the result as the same type as the input
    if isinstance(x, pd.Series):
        return pd.Series(np.convolve(x_values, weights, mode="valid"), index=x.index[window - 1 :])
    elif isinstance(x, np.ndarray):
        return np.convolve(x_values, weights, mode="valid")
    else:
        return np.convolve(x_values, weights, mode="valid").tolist()


def _get_historical_data_on_date(df: pd.DataFrame, ref_date: dt.datetime | pd.Timestamp) -> pd.DataFrame:
    """Return historical data on date."""
    all_days_df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="D")).ffill()
    ref_ts = pd.Timestamp(ref_date)
    ref_month = int(ref_ts.month)
    ref_day = 28 if (ref_ts.month == 2 and ref_ts.day == 29) else int(ref_ts.day)

    historical_series: list[pd.Series] = []
    for col in all_days_df.columns:
        by_year = ts_by_year(
            all_days_df[col],
            frequency="D",
            start_day=ref_day,
            start_month=ref_month,
            end_day=ref_day,
            end_month=ref_month,
            over_year=True,
        )
        if by_year.empty or 0 not in by_year.index:
            sampled = pd.Series(dtype=np.float64, name=col)
            historical_series.append(sampled)
            continue

        sampled = tp.cast(pd.Series, by_year.loc[0].dropna())
        sampled.index = pd.DatetimeIndex(
            [
                pd.Timestamp(
                    year=int(year),
                    month=ref_month,
                    day=min(ref_day, calendar.monthrange(int(year), ref_month)[1]),
                )
                for year in sampled.index
            ]
        )
        sampled = sampled.sort_index().rename(col)
        historical_series.append(sampled)

    if not historical_series:
        return pd.DataFrame(columns=df.columns)
    return pd.concat(historical_series, axis=1)


def calculate_historical_mean_std_for_date(
    df: pd.DataFrame,
    seasonal: int | None = 5,
    window: str | int | None = None,
    excluded_years: tp.List[int] | None = None,
    ranking_date: dt.datetime | None = None,
) -> pd.DataFrame:
    """
    Compare the ranking row against historical values and return legacy summary stats.

    Output columns:
    - ``mean`` for the historical sample mean
    - ``std`` for the historical sample standard deviation

    Standard deviation follows
    ``.std(axis=0)`` semantics (sample standard deviation, ``ddof=1``).

    If ``seasonal`` is provided, history is built from the same calendar day
    across prior years. Otherwise history is taken from rows before the
    ranking row, optionally constrained by ``window``.
    """
    if df.empty:
        raise ValueError("df must not be empty.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("df.index must be a pandas.DatetimeIndex.")
    if seasonal is not None and seasonal <= 0:
        raise ValueError("seasonal must be greater than 0 when provided.")
    if ranking_date is None:
        ranking_date = df.index[-1]
    ranking_ts = pd.Timestamp(ranking_date)
    ranking_slice = df.loc[:ranking_ts, :]
    if ranking_slice.empty:
        raise ValueError("ranking_date must be on or after the first index value in df.")

    historical_df = pd.DataFrame(index=pd.Index([], dtype="datetime64[ns]"), columns=df.columns, dtype=np.float64)
    if seasonal:
        # data for the same day across years
        data_for_years = _get_historical_data_on_date(df, ranking_ts)
        historical_df = data_for_years.loc[data_for_years.index.year < ranking_ts.year, :]
        if excluded_years is not None:
            historical_index = pd.DatetimeIndex(historical_df.index)
            historical_df = historical_df.loc[~historical_index.year.isin(excluded_years), :]
        historical_df = historical_df.tail(seasonal)
    elif isinstance(window, str) and window.lower() in ["full", "extend"]:
        historical_df = ranking_slice.iloc[:-1, :]
    elif isinstance(window, int):
        # do rolling mean ans std
        historical_df = ranking_slice.iloc[:-1, :].tail(window)
    else:
        historical_df = ranking_slice.iloc[:-1, :]

    if excluded_years is not None and not historical_df.empty and not seasonal:
        historical_index = pd.DatetimeIndex(historical_df.index)
        historical_df = historical_df.loc[~historical_index.year.isin(excluded_years), :]

    historical_mean = tp.cast(pd.Series, historical_df.mean(axis=0)).astype(np.float64)
    historical_std = tp.cast(pd.Series, historical_df.std(axis=0)).astype(np.float64)
    output_df = pd.DataFrame(
        {
            "mean": historical_mean,
            "std": historical_std,
        },
        index=df.columns,
    )
    return output_df


def calculate_bollinger_bands(
    series: pd.Series, window: int = 20, num_std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands for a given time series.
    returns as tuple
    upper_band,
    lower_band,
    band_width,
    pct_b (series - lower_band) / (upper_band - lower_band) ie where the series is in relation to the bands
    moving average (middle_band)
    """
    if window <= 0:
        raise ValueError("window must be greater than 0.")

    if series.empty:
        return (
            pd.Series(dtype=np.float64),
            pd.Series(dtype=np.float64),
            pd.Series(dtype=np.float64),
            pd.Series(dtype=np.float64),
            pd.Series(dtype=np.float64),
        )

    middle_band = cast(pd.Series, calculate_moving_average(series, window=window, kind=MovingAvgModes.SIMPLE))
    rolling_std = series.rolling(window=window).std(ddof=0).loc[middle_band.index]
    upper_band = middle_band + (rolling_std * num_std_dev)
    lower_band = middle_band - (rolling_std * num_std_dev)
    pct_b = (series.loc[middle_band.index] - lower_band) / (upper_band - lower_band)
    bandwidth = (upper_band - lower_band) / middle_band
    return upper_band, lower_band, bandwidth, pct_b, middle_band


def calculate_change(
    data: pd.Series | np.ndarray, flag: str | None = None, n: int = 1, as_series: bool = False
) -> pd.Series | np.ndarray:
    """Calculate the difference, percentage change, or log change of a series.
    parms:
    data: the input data, can be a pandas Series or a numpy array
    flag: None - do nothing to the series (pass through);
    if flag=p we do a percentage change on the series;
    if flag=l we do a log return on the series;
    if flag=d we do a subract previous value on the series
    n: the number of periods to shift for calculating the change, default is 1 has to be more than 0
    as_series: whether to return the result as a pandas Series, default is False which means we return the same type as the input
    """
    if n == 0 or flag is None:
        if as_series and not isinstance(data, pd.Series):
            return pd.Series(data)
        else:
            return data
    if n < 0:
        log.warning(f"{n} < 0 using the abs of it")
        n = abs(n)
    # convert everything to numpy and calculate for effienceny
    zeros = np.zeros(n)
    if isinstance(data, pd.Series):
        data_values = np.asarray(data.values, dtype=np.float64)
    elif isinstance(data, pd.DataFrame):
        raise ValueError("DataFrame is not supported for change calculation.")
    else:
        data_values = np.asarray(data, dtype=np.float64)
    if flag == "d":
        vals = np.subtract(data_values[n:], data_values[:-n])
    elif flag == "p":
        vals = np.subtract(data_values[n:], data_values[:-n]) / data_values[:-n]
    elif flag == "l":
        vals = np.subtract(np.log(data_values[n:]), np.log(data_values[:-n]))
    else:
        raise ValueError(f"Unsupported flag: {flag}")
    result = np.hstack((zeros, vals)) if flag in ["d", "p", "l"] else data_values
    if as_series and not isinstance(data, pd.Series):
        return pd.Series(result)
    else:
        return result


def calculate_realised_volatility(
    data: pd.DataFrame | pd.Series | np.ndarray,
    flag: str | None = None,
    rolling_window: int = 0,
    annualize_days: int = 260,
    decaying_factor: float = 1.0,
    as_series: bool = False,
) -> pd.DataFrame | pd.Series | np.ndarray:
    """Calculate the realized volatility of a time series.
    parms:
    data: the input data, can be a pandas Series, DataFrame or a numpy array
    flag: None - do nothing to the series (pass through); if flag=p we do a percentage change on the series; if flag=l we do a log return on the series
    rolling_window: the window size for calculating the rolling volatility, if 0 then we do a simple std on the whole series
    annualize_days: the number of days to annualize the volatility, default is 260 for trading days in a year
    decaying_factor: the factor to apply to the volatility to account for decaying volatility, default is 0 which means no decay
    as_series: whether to return the result as a pandas Series, default is False which means we return the same type as the input
    """
    if isinstance(data, pd.Series) or isinstance(data, pd.DataFrame):
        data_values = np.asarray(data.values, dtype=np.float64)
    else:
        data_values = np.asarray(data, dtype=np.float64)

    # reshape data into 1d array if it's 2d with one column
    to_calc = data_values.reshape(-1)
    changes = calculate_change(to_calc, flag=flag, n=1, as_series=False)
    if rolling_window != 0:
        if decaying_factor == 0:
            weights: np.ndarray = np.ones(rolling_window) / rolling_window
        else:
            weights = np.asarray(
                [
                    (1 - decaying_factor) * pow(decaying_factor, i) / (1 - pow(decaying_factor, rolling_window))
                    for i in range(rolling_window)
                ]
            )
        am = np.convolve(changes, weights, "full")
        am2 = am**2.0
        a2 = changes**2.0
        rolling_vol = np.sqrt(np.convolve(a2, weights, "full") - am2)
        rolling_vol = rolling_vol[: -1 * (rolling_window - 1)]
        rolling_vol[:rolling_window] = np.nan
    else:
        rolling_vol = changes.std()

    annularized_vol = rolling_vol * np.sqrt(annualize_days)
    if as_series and (isinstance(data, pd.Series) or isinstance(data, pd.DataFrame)):
        return pd.Series(annularized_vol, index=data.index if isinstance(data, pd.Series) else None)
    else:
        return annularized_vol


def calculate_percential_rank(series: pd.Series | np.ndarray, test_value: float = 1.0) -> float:
    """Percentile rank with tie-aware midrank and interpolation between observations."""
    if isinstance(series, pd.Series):
        values = np.asarray(series.values, dtype=np.float64)
    else:
        values = np.asarray(series, dtype=np.float64)

    if values.size == 0:
        raise ValueError("series must contain at least one value.")

    values = values[~np.isnan(values)]
    if values.size == 0:
        raise ValueError("series must contain at least one non-NaN value.")

    sorted_values = np.sort(values)
    if test_value <= sorted_values[0]:
        return 0.0
    if test_value >= sorted_values[-1]:
        return 1.0

    num_vals = sorted_values.size
    lt = np.searchsorted(sorted_values, test_value, side="left")
    gt = np.searchsorted(sorted_values, test_value, side="right")
    eq = gt - lt

    # Exact matches use tie-aware midrank, values between observations use linear interpolation.
    if eq > 0:
        return float((lt + 0.5 * eq) / num_vals)
    # No exact matches, interpolate between the two nearest observations.
    cdf_points = np.arange(1, num_vals + 1, dtype=np.float64) / num_vals
    return float(np.interp(test_value, sorted_values, cdf_points))


def calculate_regressions(
    x: pd.Series,
    y: pd.Series,
    window: int | None = None,
    constant: bool = True,
    rolling: bool = True,
) -> tp.Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | tp.Tuple[float, float, float, float]:
    """Calculate OLS regressions, either rolling-window or full-sample."""
    if len(x) != len(y):
        raise ValueError("x and y must have the same length.")

    x_vals = x.astype(np.float64)
    y_vals = y.astype(np.float64)

    exog = pd.DataFrame({"x": x_vals.to_numpy()}, index=x_vals.index)
    if constant:
        exog = sm.add_constant(exog, has_constant="add")

    if not rolling:
        result = sm.OLS(endog=y_vals, exog=exog, missing="drop").fit()
        params = cast(pd.Series, result.params)
        alpha = float(params["const"]) if constant else np.float64(0.0)
        beta = float(params["x"])
        rsqr = float(result.rsquared)
        rmse = float(np.sqrt(result.mse_resid))
        alpha = np.float64(alpha) if np.isfinite(alpha) else np.float64(0.0)
        beta = np.float64(beta) if np.isfinite(beta) else np.float64(0.0)
        rsqr = np.float64(rsqr) if np.isfinite(rsqr) else np.float64(0.0)
        rmse = np.float64(rmse) if np.isfinite(rmse) else np.float64(0.0)
        return float(alpha), float(beta), float(rsqr), float(rmse)

    if window is None:
        raise ValueError("window must be provided when rolling=True.")

    window = int(window)
    if window < 2:
        raise ValueError("window must be at least 2.")

    result = RollingOLS(endog=y_vals, exog=exog, window=window, missing="drop").fit(method="lstsq")
    params = cast(pd.DataFrame, result.params)
    beta = params["x"]
    if constant:
        alpha = params["const"]
    else:
        alpha = pd.Series(np.float64(0.0), index=x_vals.index, dtype=np.float64)

    rsqr = pd.Series(np.asarray(result.rsquared, dtype=np.float64), index=x_vals.index)
    rmse = pd.Series(np.sqrt(np.asarray(result.mse_resid, dtype=np.float64)), index=x_vals.index)

    alpha = alpha.replace([np.inf, -np.inf], np.nan).fillna(np.float64(0.0))
    beta = beta.replace([np.inf, -np.inf], np.nan).fillna(np.float64(0.0))
    rsqr = rsqr.replace([np.inf, -np.inf], np.nan).fillna(np.float64(0.0))
    rmse = rmse.replace([np.inf, -np.inf], np.nan).fillna(np.float64(0.0))

    alpha.iloc[: window - 1] = np.float64(0.0)
    beta.iloc[: window - 1] = np.float64(0.0)
    rsqr.iloc[: window - 1] = np.float64(0.0)
    rmse.iloc[: window - 1] = np.float64(0.0)
    return alpha.to_numpy(), beta.to_numpy(), rsqr.to_numpy(), rmse.to_numpy()


def calculate_rolling_regression(
    x: pd.Series, y: pd.Series, window: int, constant: bool = True
) -> tp.Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Backward-compatible wrapper for rolling regression."""
    alpha, beta, rsqr, rmse = calculate_regressions(x=x, y=y, window=window, constant=constant, rolling=True)
    return cast(tp.Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], (alpha, beta, rsqr, rmse))


def get_rolling_residual_zscore(y, x, window, constant=True):
    """Calculate the rolling residual z-score of y on x."""
    alpha, beta, _, rmse = calculate_rolling_regression(x, y, window, constant)
    result = y - (alpha + beta * x) / rmse
    return result.replace([np.inf, -np.inf], np.nan).fillna(np.float64(0.0))


def rolling_window(values, window):
    """Handle rolling window."""
    shape = values.shape[:-1] + (values.shape[-1] - window + 1, window)
    strides = values.strides + (values.strides[-1],)
    return np.lib.stride_tricks.as_strided(values, shape=shape, strides=strides)


def calculate_donchain_channel(
    high_price: pd.Series,
    low_price: pd.Series | None = None,
    close_price: pd.Series | None = None,
    window: int = 20,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Donchian channel bands and a breakout/carry signal.

    Returns:
    upper_band, lower_band, signal
    signal rules:
    - 1.0 when close breaks above yesterday's upper band
    - -1.0 when close breaks below yesterday's lower band
    - 0.0 before enough history, otherwise carry the previous signal when no breakout
    """
    if window <= 0:
        raise ValueError("window must be greater than 0.")

    high = high_price.astype(np.float64)
    low = high if low_price is None else low_price.astype(np.float64)
    close = high if close_price is None else close_price.astype(np.float64)

    if not high.index.equals(low.index) or not high.index.equals(close.index):
        raise ValueError("high_price, low_price, and close_price must share the same index.")

    if high.empty:
        empty = pd.Series(dtype=np.float64)
        return empty, empty, empty

    # Donchian bands are rolling extrema on trailing windows.
    upper_band = high.rolling(window=window, min_periods=window).max()
    lower_band = low.rolling(window=window, min_periods=window).min()

    # Breakout checks use the previous day's bands to avoid look-ahead.
    breakout_up = close > upper_band.shift(1)
    breakout_down = close < lower_band.shift(1)

    signal = pd.Series(np.nan, index=close.index, dtype=np.float64)
    signal[breakout_up] = np.float64(1.0)
    signal[breakout_down] = np.float64(-1.0)

    # Between breakouts we carry the last signal; before warmup we expose 0.0.
    signal = signal.ffill().fillna(np.float64(0.0))
    signal.iloc[:window] = np.float64(0.0)
    return upper_band, lower_band, signal


def calculate_stochastic_indicator(
    high_price: pd.Series | np.ndarray,
    low_price: pd.Series | np.ndarray,
    close_price: pd.Series | np.ndarray,
    k_window: int = 14,
    slow_d_window: int = 3,
    sd: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate stochastic indicator in legacy quant format.

    Returns k_percent (full length), d_percent (MA-valid length), sd_percent (MA-valid length).
    """
    if k_window <= 0 or slow_d_window <= 0 or sd <= 0:
        raise ValueError("k_window, slow_d_window, and sd must be greater than 0.")

    high = np.asarray(high_price, dtype=np.float64).reshape(-1)
    low = np.asarray(low_price, dtype=np.float64).reshape(-1)
    close = np.asarray(close_price, dtype=np.float64).reshape(-1)
    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("high_price, low_price, and close_price must have the same length.")
    if len(close) == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty
    if k_window > len(close):
        raise ValueError("k_window must be less than or equal to the input length.")

    # Pandas rolling extrema are equivalent trailing-window bounds and keep NaN warmup.
    p_max = pd.Series(high, dtype=np.float64).rolling(window=k_window, min_periods=k_window).max().to_numpy()
    p_min = pd.Series(low, dtype=np.float64).rolling(window=k_window, min_periods=k_window).min().to_numpy()

    k_percent = (close - p_min) / (p_max - p_min) * np.float64(100.0)
    d_percent = np.asarray(
        calculate_moving_average(k_percent, window=slow_d_window, kind=MovingAvgModes.SIMPLE), dtype=np.float64
    )
    sd_percent = np.asarray(
        calculate_moving_average(d_percent, window=sd, kind=MovingAvgModes.SIMPLE), dtype=np.float64
    )
    return k_percent, d_percent, sd_percent


def calculate_true_range(
    high_price: pd.Series | np.ndarray,
    low_price: pd.Series | np.ndarray | None = None,
    close_price: pd.Series | np.ndarray | None = None,
    window: int | None = None,
    rolling: bool = False,
    rolling_kind: MovingAvgModes | str = MovingAvgModes.EXPONENTIAL,
) -> np.ndarray | float:
    """Calculate the true range of a time series.
    true range is the maximum of the following:
        1. current high - current low
        2. current high - previous close
        3. current low - previous close
    first element is assumed to be the oldest.
    if input is only one array, we treat it as close and use legacy fallback:
    [0, 2*abs(diff(close))].
    if rolling=True and window>1, return ATR-style smoothing via moving_average helper.
    if rolling=True and window is None, return full-sample average true range.
    """
    if window is not None and window <= 0:
        raise ValueError("window must be greater than 0.")

    high = np.asarray(high_price, dtype=np.float64).reshape(-1)
    if high.size == 0:
        return np.array([], dtype=np.float64)

    if low_price is None and close_price is None:
        if high.size == 1:
            return np.float64(0.0)
        tr = np.hstack((np.float64(0.0), np.abs(np.diff(high)) * np.float64(2.0)))
    else:
        if low_price is None or close_price is None:
            raise ValueError("low_price and close_price must either both be provided or both be omitted.")
        low = np.asarray(low_price, dtype=np.float64).reshape(-1)
        close = np.asarray(close_price, dtype=np.float64).reshape(-1)
        if len(high) != len(low) or len(high) != len(close):
            raise ValueError("high_price, low_price, and close_price must have the same length.")
        if len(close) == 1:
            return float(high[0] - low[0])

        # Preserve legacy close-only behavior when H=L=C across the full sample.
        if np.array_equal(low, close) and np.array_equal(high, close):
            tr = np.hstack((np.float64(0.0), np.abs(np.diff(close)) * np.float64(2.0)))
        else:
            prev_close = np.hstack((close[0], close[:-1]))
            range1 = high - low
            range2 = np.abs(high - prev_close)
            range3 = np.abs(low - prev_close)
            tr = np.maximum.reduce([range1, range2, range3])
    if not rolling:
        return tr

    if window is None:
        return float(np.mean(tr))

    if window == 1:
        return tr

    tr_ma = np.asarray(calculate_moving_average(tr, window=window, kind=rolling_kind), dtype=np.float64)
    # Keep full-length output and warmup NaNs for compatibility with rolling-window semantics.
    atr = np.full(len(tr), np.nan, dtype=np.float64)
    atr[window - 1 :] = tr_ma
    return atr


def calculate_fisher_indicator(
    high_price: pd.Series | np.ndarray,
    low_price: pd.Series | np.ndarray,
    close_price: pd.Series | np.ndarray,
) -> tp.Tuple[np.ndarray, np.ndarray]:
    """Calculate the Fisher indicator for a time series.
    returns the fisher high and fisher low as a tuple of numpy arrays.
    """
    high = np.asarray(high_price, dtype=np.float64).reshape(-1)
    low = np.asarray(low_price, dtype=np.float64).reshape(-1)
    close = np.asarray(close_price, dtype=np.float64).reshape(-1)

    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("high_price, low_price, and close_price must have the same length.")
    if len(high) == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty

    # Core quant formula: midpoint around typical price with symmetric offset vs (H+L)/2.
    typical_price = (high + low + close) / np.float64(3.0)
    hl_midpoint = (high + low) / np.float64(2.0)
    offset = np.abs(typical_price - hl_midpoint)
    fisher_high = typical_price + offset
    fisher_low = typical_price - offset

    invalid = ~np.isfinite(high) | ~np.isfinite(low) | ~np.isfinite(close)
    fisher_high[invalid] = np.nan
    fisher_low[invalid] = np.nan
    return fisher_high, fisher_low


def max_sharpe(pnl: pd.DataFrame, annualize: int = 260, target: float = 5) -> dict:
    """
    Mean-variance optimization to maximize Sharpe ratio.

    :param pnl: DataFrame of daily P&L in dollars, one column per instrument
    :param annualize: trading days per year (default 260)
    :param target: target annualized portfolio volatility in million dollars (default 5)
    :return: dict with "weights" (Series, in million dollars) and "sharpe" (float)
    """
    pnl = pnl.dropna()
    n = pnl.shape[1]
    mu = pnl.mean().values
    cov = pnl.cov().values

    def neg_sharpe(w):
        """Handle neg sharpe."""
        port_return = w @ mu
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol == 0:
            return 0.0
        return -(port_return / port_vol) * np.sqrt(annualize)

    bounds = [(0, None)] * n
    w0 = np.ones(n)

    result = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds)

    w_opt = result.x
    port_vol_annual = np.sqrt(w_opt @ cov @ w_opt) * np.sqrt(annualize)  # in dollars
    scale = (target * 1e6) / port_vol_annual  # scale so vol == target million dollars

    weights = pd.Series(w_opt * scale, index=pnl.columns)
    sharpe = -result.fun

    return {"weights": weights, "sharpe": sharpe}
