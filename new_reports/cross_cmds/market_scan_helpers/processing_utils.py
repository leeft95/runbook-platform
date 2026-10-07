"""
Processing utility functions for market scan data processing.

This module breaks down the monolithic process_data function into smaller,
focused, testable components.

USAGE EXAMPLE:
--------------
from market_scan_helpers.processing_utils import (
    prepare_price_data,
    calculate_price_changes,
    calculate_stochastic,
    calculate_sharpe_ratios,
    calculate_fisher_indicators,
    determine_fisher_signals,
    calculate_moving_average_signals,
    calculate_kpi,
    calculate_trend_index,
    determine_combined_signals,
    generate_alerts
)

# In process_data function:
# 1. Prepare data
price_data = prepare_price_data(daily_price, weekly_price, monthly_price)
if price_data is None:
    return empty_return_tuple()

# 2. Calculate price changes
price_changes = calculate_price_changes(price_data['closep'], chg_type, intraday_price)

# 3. Calculate technical indicators
sto_ind = calculate_stochastic(price_data['highp'], price_data['lowp'], price_data['closep'])
sharpe_metrics = calculate_sharpe_ratios(price_changes['daily_price_chg'],
                                       price_changes['intraday_price_chg'],
                                       instr, chg_type)

# 4. Calculate Fisher indicators
fisher = calculate_fisher_indicators(
    price_data['highp'], price_data['lowp'], price_data['closep'],
    price_data['highp_w'], price_data['lowp_w'], price_data['closep_w'],
    price_data['highp_m'], price_data['lowp_m'], price_data['closep_m'],
    daily_price
)
fish, fish1, fishlt, fishlt1, counter, counter1 = determine_fisher_signals(fisher, price_data['closep'])

# 5. Calculate moving averages
ma_signals = calculate_moving_average_signals(price_data['closep'])

# 6. Calculate KPI
kpi_metrics = calculate_kpi(price_data['closep'], price_data['imp_vol'],
                           price_changes['daily_price_chg'], chg_type,
                           generic_name, intraday_price)

# 7. Calculate trend index and signals
trend_index = calculate_trend_index(...)
combined_signals = determine_combined_signals(trend_index, price_changes['price_change'], ...)

# 8. Generate alerts
alerts = generate_alerts(instr, ticker, chg_type, ...)

"""

import datetime as dt
import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay
from loguru import logger as log
import ecm.cmds.bbg as bbg
import ecm.cmds.talib as talib
from ecm.cmds.cdr import today
import ecm.cmds.table as table
from ecm.cmds.utils import convert_path_to_linux
from plotly import graph_objs as go

risk_index_def_link = table.html_text("Risk Index Definition",
                                    style="font-size: 16px; text-align:left; font-family:Calibri;",
                                    tag="div"
                                    )


def empty_return_tuple():
    """Return empty tuple matching process_data output structure"""
    return ([], [], [], [], [], [], [], [], [], [], [], [], [], [], [])


def datetime_range(start, end, delta):
    """Generate datetime range with given delta"""
    current = start
    while current <= end:
        yield current
        current += delta



def prepare_price_data(daily_price, weekly_price, monthly_price):
    """
    Prepare and clean price data (OHLC).

    Args:
        daily_price: Daily price DataFrame
        weekly_price: Weekly price DataFrame
        monthly_price: Monthly price DataFrame

    Returns:
        Dict with cleaned price series
    """
    result = {}

    if len(daily_price) > 30 and "PX_LAST" in daily_price.columns:
        if "PX_OPEN" in daily_price.columns and "PX_HIGH" in daily_price.columns and "PX_LOW" in daily_price.columns:
            daily_price.loc[pd.isna(daily_price["PX_OPEN"]), "PX_OPEN"] = daily_price.loc[pd.isna(daily_price["PX_OPEN"]), "PX_LAST"]
            daily_price.loc[pd.isna(daily_price["PX_HIGH"]), "PX_HIGH"] = daily_price.loc[pd.isna(daily_price["PX_HIGH"]), "PX_LAST"]
            daily_price.loc[pd.isna(daily_price["PX_LOW"]), "PX_LOW"] = daily_price.loc[pd.isna(daily_price["PX_LOW"]), "PX_LAST"]
            daily_price.loc[pd.isna(daily_price["PX_LAST"]), "PX_LAST"] = (
                daily_price.loc[pd.isna(daily_price["PX_LAST"]), "PX_HIGH"] + daily_price.loc[pd.isna(daily_price["PX_LAST"]), "PX_LOW"]
            ) / 2
            daily_price["PX_OPEN"].fillna(method="ffill", inplace=True)
            daily_price["PX_HIGH"].fillna(method="ffill", inplace=True)
            daily_price["PX_LOW"].fillna(method="ffill", inplace=True)
            daily_price["PX_LAST"].fillna(method="ffill", inplace=True)

        closep = daily_price["PX_LAST"]

        try:
            highp = daily_price["PX_HIGH"]
        except:
            highp = closep

        try:
            lowp = daily_price["PX_LOW"]
        except:
            lowp = closep

        try:
            imp_vol = daily_price["3MTH_IMPVOL_100.0%MNY_DF"]
        except:
            imp_vol = pd.DataFrame()

        result['closep'] = closep
        result['highp'] = highp
        result['lowp'] = lowp
        result['imp_vol'] = imp_vol
    else:
        return None

    if len(weekly_price) > 0 and "PX_LAST" in weekly_price.columns:
        closep_w = weekly_price["PX_LAST"]

        try:
            highp_w = weekly_price["PX_HIGH"]
            lowp_w = weekly_price["PX_LOW"]
        except:
            highp_w = closep_w
            lowp_w = closep_w

        result['closep_w'] = closep_w
        result['highp_w'] = highp_w
        result['lowp_w'] = lowp_w
    else:
        result['closep_w'] = pd.Series(dtype="float64")
        result['highp_w'] = pd.Series(dtype="float64")
        result['lowp_w'] = pd.Series(dtype="float64")

    if len(monthly_price) > 0 and "PX_LAST" in monthly_price.columns:
        closep_m = monthly_price["PX_LAST"]

        try:
            highp_m = monthly_price["PX_HIGH"]
            lowp_m = monthly_price["PX_LOW"]
        except:
            highp_m = closep_m
            lowp_m = closep_m

        result['closep_m'] = closep_m
        result['highp_m'] = highp_m
        result['lowp_m'] = lowp_m
    else:
        result['closep_m'] = pd.Series(dtype="float64")
        result['highp_m'] = pd.Series(dtype="float64")
        result['lowp_m'] = pd.Series(dtype="float64")

    return result



def calculate_price_changes(closep, chg_type, intraday_price=None):
    """
    Calculate price changes and returns.

    Args:
        closep: Close price series
        chg_type: "FLAT" or "SPRD"
        intraday_price: Optional intraday price DataFrame

    Returns:
        Dict with price change metrics
    """
    last_price = closep[-1]
    price_change = closep[-1] - closep[-2]
    price_change1 = closep[-2] - closep[-3]

    if chg_type == "FLAT":
        price_change_pct = (closep[-1] - closep[-2]) / closep[-2]
        price_change_pct1 = (closep[-2] - closep[-3]) / closep[-3]
        daily_price_chg = closep.diff() / closep.shift(1)
        chg_5d = (closep[-1] - closep[-5]) / closep[-5]
        if intraday_price is not None and len(intraday_price) > 0:
            intraday_price_chg = intraday_price["close"].diff() / intraday_price["close"].shift(1)
        else:
            intraday_price_chg = pd.Series(dtype="float64")
    elif chg_type == "SPRD":
        price_change_pct = price_change
        price_change_pct1 = price_change1
        daily_price_chg = closep.diff()
        chg_5d = closep[-1] - closep[-5]
        if intraday_price is not None and len(intraday_price) > 0:
            intraday_price_chg = intraday_price["close"].diff()
        else:
            intraday_price_chg = pd.Series(dtype="float64")
    else:
        raise NotImplementedError(f"ERROR! {chg_type} is not known")

    return {
        'last_price': last_price,
        'price_change': price_change,
        'price_change1': price_change1,
        'price_change_pct': price_change_pct,
        'price_change_pct1': price_change_pct1,
        'daily_price_chg': daily_price_chg,
        'chg_5d': chg_5d,
        'intraday_price_chg': intraday_price_chg
    }


def calculate_post_close(daily_price):
    """Calculate post-close price movement"""
    try:
        if np.isnan(daily_price["PX_SETTLE"].iloc[-1]):
            return daily_price["FUT_PX"].iloc[-2] - daily_price["PX_SETTLE"].iloc[-2]
        else:
            return daily_price["FUT_PX"].iloc[-1] - daily_price["PX_SETTLE"].iloc[-1]
    except:
        return 0



def parse_fom_date(fom_date_str):
    """Parse FOM date string into datetime or tuple of datetimes"""
    if not isinstance(fom_date_str, str):
        if isinstance(fom_date_str, dt.datetime):
            return fom_date_str
        return None

    if len(fom_date_str) == 10:
        try:
            return dt.datetime.strptime(fom_date_str, "%Y-%m-%d")
        except:
            return dt.datetime.strptime(fom_date_str, "%m/%d/%Y")
    else:
        try:
            fom_date0 = dt.datetime.strptime(fom_date_str[:10], "%Y-%m-%d")
        except:
            fom_date0 = dt.datetime.strptime(fom_date_str[:10], "%m/%d/%Y")
        try:
            fom_date1 = dt.datetime.strptime(fom_date_str[-10:], "%Y-%m-%d")
        except:
            fom_date1 = dt.datetime.strptime(fom_date_str[-10:], "%m/%d/%Y")

        if fom_date0 > today():
            fom_date0 = dt.datetime(today().year, today().month, 1)

        return (fom_date0, fom_date1)


def calculate_fom_metrics(fom_comments, generic_name, daily_price_chg, highp, lowp, closep):
    """
    Calculate FOM (First of Month) related metrics.

    Args:
        fom_comments: DataFrame with FOM dates
        generic_name: Generic ticker name
        daily_price_chg: Daily price change series
        highp: High price series
        lowp: Low price series
        closep: Close price series

    Returns:
        Tuple of (fom_flag, fom_zscore, fom_date_str)
    """
    try:
        fom_date_str = fom_comments.loc[generic_name, "FOM Dates"]
        fom_date = parse_fom_date(fom_date_str)

        if fom_date is None:
            return None, None, None

        if isinstance(fom_date, tuple):
            fom_chg = daily_price_chg[(daily_price_chg.index >= fom_date[0]) & (daily_price_chg.index <= fom_date[1])].sum()
            fom_std = daily_price_chg[daily_price_chg.index < fom_date[0]].iloc[-20:].std()
            fom_high = highp[(highp.index >= fom_date[0]) & (highp.index <= fom_date[1])].max()
            fom_low = lowp[(lowp.index >= fom_date[0]) & (lowp.index <= fom_date[1])].min()
            fom_date_str = dt.datetime.strftime(fom_date[0], "%Y-%m-%d") + " - " + dt.datetime.strftime(fom_date[1], "%Y-%m-%d")
        else:
            fom_chg = daily_price_chg[daily_price_chg.index >= fom_date].iloc[0]
            fom_std = daily_price_chg[daily_price_chg.index < fom_date].iloc[-20:].std()
            fom_high = highp[highp.index >= fom_date].iloc[0]
            fom_low = lowp[lowp.index >= fom_date].iloc[0]
            fom_date_str = fom_date

        fom_zscore = fom_chg / fom_std

        if closep[-1] > fom_high:
            fom_flag = "A+"
        elif closep[-1] < fom_low:
            fom_flag = "A-"
        else:
            fom_flag = None

        return fom_flag, fom_zscore, fom_date_str

    except Exception as e:
        log.warning(f"FOM calculation failed for {generic_name}: {e}")
        return None, None, None


def calculate_fom_vwap(ticker, vwap_track_date_range, intraday_price=None):
    """
    Calculate FOM VWAP and delta.

    Args:
        ticker: Ticker symbol
        vwap_track_date_range: Dict with 'sdate' and 'edate' keys
        intraday_price: Optional intraday price DataFrame for delta calculation

    Returns:
        Tuple of (fom_vwap, fom_delta)
    """
    try:
        vwap_overrides = [
            ("VWAP_START_TIME", "00:00:00"),
            ("VWAP_END_TIME", "23:00:00"),
            ("VWAP_START_DT", f"{vwap_track_date_range.get('sdate').strftime('%Y%m%d')}"),
            ("VWAP_END_DT", f"{vwap_track_date_range.get('edate').strftime('%Y%m%d')}"),
        ]
        fom_vwap = bbg.bdh(ticker, ["EQY_WEIGHTED_AVG_PX"], ovrds=vwap_overrides, **vwap_track_date_range).iloc[-1, 0]

        if intraday_price is not None and len(intraday_price) > 0:
            fom_delta = (intraday_price.close[-1] - fom_vwap).round(2)
        else:
            fom_delta = np.nan

        return fom_vwap, fom_delta
    except Exception as e:
        return np.nan, np.nan



def calculate_stochastic(highp, lowp, closep):
    """Calculate stochastic oscillator and signal"""
    stok, stod, stods = talib.stochastic(highp.values, lowp.values, closep.values, 13, 3, 3)

    if stod[-1] > 80 and stods[-1] > 80:
        if stod[-2] > stods[-2] and stod[-1] < stods[-1]:
            return "OB CROSS"
        else:
            return "OB"
    elif stod[-1] < 20 and stods[-1] < 20:
        if stod[-2] < stods[-2] and stod[-1] > stods[-1]:
            return "OS CROSS"
        else:
            return "OS"
    return None


def calculate_sharpe_3d_cob(intraday_price_chg, sdate_3d_cob, edate_3d_cob, instr, chg_type):
    """Calculate 3-day close-of-business sharpe ratio"""
    if edate_3d_cob > intraday_price_chg.index[-1] or edate_3d_cob not in intraday_price_chg.index:
        three_d_chg_cob = intraday_price_chg[(intraday_price_chg.index >= sdate_3d_cob) & (intraday_price_chg.index <= edate_3d_cob)]
    else:
        three_d_chg_cob = intraday_price_chg.loc[sdate_3d_cob:edate_3d_cob]

    if len(three_d_chg_cob) <= 10:
        return np.nan

    weight = 1
    if instr == "FI" and chg_type == "SPRD":
        three_d_chg_cob = three_d_chg_cob * -1

    three_d_chg_cob = three_d_chg_cob.drop(three_d_chg_cob.index[0])
    chg_3d_cob = three_d_chg_cob.mean()
    stdev_3d_cob = three_d_chg_cob.std()

    try:
        return (chg_3d_cob / stdev_3d_cob * np.sqrt(len(three_d_chg_cob))) * weight
    except:
        return np.nan


def calculate_sharpe_ratios(daily_price, daily_price_chg, intraday_price_chg, instr, chg_type, folder_path, key):
    """
    Calculate all sharpe ratios (22d, 3d live, 3d COB).

    Returns:
        Dict with sharpe ratio metrics
    """
    sharpe_22d = daily_price_chg.iloc[-23:-1].mean() / daily_price_chg.iloc[-23:-1].std() * np.sqrt(22)

    if len(intraday_price_chg) == 0:
        return {
            'sharpe_22d': sharpe_22d,
            'sharpe_3d': np.nan,
            'sharpe_3d_cob': np.nan,
            'sharpe_3d_cob_1': np.nan,
            'sharpe_3d_cob_2': np.nan,
            'sharpe_3d_cob_3': np.nan,
            'upload': False
        }

    sdate_3d = daily_price_chg.index[-3]
    edate_3d = daily_price_chg.index[-1] + dt.timedelta(hours=23, minutes=59)
    sdate_3d_cob = daily_price_chg.index[-4]
    edate_3d_cob = daily_price_chg.index[-2] + dt.timedelta(hours=23, minutes=59)
    sdate_3d_cob_1 = daily_price_chg.index[-5]
    edate_3d_cob_1 = daily_price_chg.index[-3] + dt.timedelta(hours=23, minutes=59)
    sdate_3d_cob_2 = daily_price_chg.index[-6]
    edate_3d_cob_2 = daily_price_chg.index[-4] + dt.timedelta(hours=23, minutes=59)
    sdate_3d_cob_3 = daily_price_chg.index[-7]
    edate_3d_cob_3 = daily_price_chg.index[-5] + dt.timedelta(hours=23, minutes=59)

    if edate_3d > intraday_price_chg.index[-1] or edate_3d not in intraday_price_chg.index:
        three_d_chg = intraday_price_chg[(intraday_price_chg.index >= sdate_3d) & (intraday_price_chg.index <= edate_3d)]
    else:
        three_d_chg = intraday_price_chg.loc[sdate_3d:edate_3d]

    if len(three_d_chg) > 10:
        weight = 1
        three_d_chg = three_d_chg.drop(three_d_chg.index[0])
        chg_3d = three_d_chg.mean()
        stdev_3d = three_d_chg.std()

        try:
            sharpe_3d = (chg_3d / stdev_3d * np.sqrt(len(three_d_chg))) * weight
            upload = True
        except:
            sharpe_3d = np.nan
            upload = False
    else:
        sharpe_3d = np.nan
        upload = False

    if (intraday_price_chg.index[-1] > edate_3d_cob - BDay(10)) or instr == "RISK":
        sharpe_3d_cob = calculate_sharpe_3d_cob(intraday_price_chg, sdate_3d_cob, edate_3d_cob, instr, chg_type)
        sharpe_3d_cob_1 = calculate_sharpe_3d_cob(intraday_price_chg, sdate_3d_cob_1, edate_3d_cob_1, instr, chg_type)
        sharpe_3d_cob_2 = calculate_sharpe_3d_cob(intraday_price_chg, sdate_3d_cob_2, edate_3d_cob_2, instr, chg_type)
        sharpe_3d_cob_3 = calculate_sharpe_3d_cob(intraday_price_chg, sdate_3d_cob_3, edate_3d_cob_3, instr, chg_type)
        plot_frame = daily_price.copy()
        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=plot_frame.index,
                open=plot_frame["PX_OPEN"],
                high=plot_frame["PX_HIGH"],
                low=plot_frame["PX_LOW"],
                close=plot_frame["PX_LAST"],
                name="OHLC",
            )
        )
        fig.update_layout(xaxis_rangeslider_visible=False, title=f"{key[1]} OHLC", width=800, height=600)
        extras = [risk_index_def_link] if instr == "RISK" else []
        try:
            table.figures_to_html(
                [fig] + extras,
                filename=convert_path_to_linux(f"{folder_path}\\candle_plots\\{key[1]}.html"),
            )
        except Exception as e:
            log.error(f"Could not save candle plot for {key} due to {e}")
    else:
        sharpe_3d_cob = np.nan
        sharpe_3d_cob_1 = np.nan
        sharpe_3d_cob_2 = np.nan
        sharpe_3d_cob_3 = np.nan

    return {
        'sharpe_22d': sharpe_22d,
        'sharpe_3d': sharpe_3d,
        'sharpe_3d_cob': sharpe_3d_cob,
        'sharpe_3d_cob_1': sharpe_3d_cob_1,
        'sharpe_3d_cob_2': sharpe_3d_cob_2,
        'sharpe_3d_cob_3': sharpe_3d_cob_3,
        'upload': upload
    }


def calculate_range_metrics(highp, lowp, closep, daily_price):
    """Calculate true range and range spike metrics"""
    true_range = talib.tr(highp.values, lowp.values, closep.values)
    avg_true_range = talib.atr(highp.values, lowp.values, closep, 5)
    range_spike = true_range[-1] / avg_true_range[-2]

    if daily_price.index[-1] == today():
        range_spike1 = true_range[-2] / avg_true_range[-3]
    elif daily_price.index[-1] < today():
        range_spike1 = true_range[-1] / avg_true_range[-2]
    else:
        range_spike1 = true_range[-3] / avg_true_range[-4]

    return {
        'range_spike': range_spike,
        'range_spike1': range_spike1,
        'avg_true_range': avg_true_range
    }


def calculate_three_day_trend(closep):
    """Determine 3-day price trend"""
    if closep[-1] > closep[-2] > closep[-3] > closep[-4] and closep[-4] < closep[-5]:
        return "UP"
    elif closep[-1] < closep[-2] < closep[-3] < closep[-4] and closep[-4] > closep[-5]:
        return "DOWN"
    return None


def calculate_current_price_range(closep, highp, lowp):
    """Determine if current price is at high or low of range"""
    if closep[-1] > highp[-1] - (highp[-1] - lowp[-1]) * 0.1:
        return "HIGH"
    elif closep[-1] < lowp[-1] + (highp[-1] - lowp[-1]) * 0.1:
        return "LOW"
    return None



def calculate_fisher_indicators(highp, lowp, closep, highp_w, lowp_w, closep_w,
                                highp_m, lowp_m, closep_m, daily_price):
    """Calculate Fisher transform indicators for daily, weekly, monthly"""
    fdhs, fdls = talib.fisher_indicator(highp, lowp, closep)

    fwhs, fwls = talib.fisher_indicator(highp_w, lowp_w, closep_w)
    fwhs = fwhs.reindex(daily_price.index).shift(1).fillna(method="ffill")
    fwls = fwls.reindex(daily_price.index).shift(1).fillna(method="ffill")

    fmhs, fmls = talib.fisher_indicator(highp_m, lowp_m, closep_m)
    fmhs = fmhs.reindex(daily_price.index).shift(1).fillna(method="ffill")
    fmls = fmls.reindex(daily_price.index).shift(1).fillna(method="ffill")

    return {
        'fdh': fdhs[-1], 'fdl': fdls[-1],
        'fdh1': fdhs[-2], 'fdl1': fdls[-2],
        'fdh2': fdhs[-3], 'fdl2': fdls[-3],
        'fwh': fwhs[-1], 'fwl': fwls[-1],
        'fwh1': fwhs[-2], 'fwl1': fwls[-2],
        'fwh2': fwhs[-3], 'fwl2': fwls[-3],
        'fmh': fmhs[-1], 'fml': fmls[-1],
        'fmh1': fmhs[-2], 'fml1': fmls[-2],
        'fmh2': fmhs[-3], 'fml2': fmls[-3],
    }


def determine_fisher_signals(fisher, closep):
    """Determine buy/sell signals from Fisher indicators"""
    if (fisher['fdl'] > fisher['fwh'] and fisher['fwh'] > fisher['fmh'] and
        fisher['fwl'] > fisher['fml'] and closep[-1] > fisher['fwl'] and
        (fisher['fdl1'] < fisher['fwh1'] or fisher['fwh1'] < fisher['fmh1'] or fisher['fwl1'] < fisher['fml1'])):
        fish = "BUY"
    elif (fisher['fdh'] < fisher['fwl'] and fisher['fwl'] < fisher['fml'] and
          fisher['fwh'] < fisher['fmh'] and closep[-1] < fisher['fwh'] and
          (fisher['fdh1'] > fisher['fwl1'] or fisher['fwl1'] > fisher['fml1'] or fisher['fwh1'] > fisher['fmh1'])):
        fish = "SELL"
    else:
        fish = None

    if (fisher['fdl1'] > fisher['fwh1'] and fisher['fwh1'] > fisher['fmh1'] and
        fisher['fwl1'] > fisher['fml1'] and closep[-2] > fisher['fwl1'] and
        (fisher['fdl2'] < fisher['fwh2'] or fisher['fwh2'] < fisher['fmh2'] or fisher['fwl2'] < fisher['fml2'])):
        fish1 = "BUY"
    elif (fisher['fdh1'] < fisher['fwl1'] and fisher['fwl1'] < fisher['fml1'] and
          fisher['fwh1'] < fisher['fmh1'] and closep[-2] < fisher['fwh1'] and
          (fisher['fdh2'] > fisher['fwl2'] or fisher['fwl2'] > fisher['fml2'] or fisher['fwh2'] > fisher['fmh2'])):
        fish1 = "SELL"
    else:
        fish1 = None

    if fisher['fwl'] > fisher['fmh'] and closep[-1] > fisher['fmh'] and fisher['fwl1'] < fisher['fmh1']:
        fishlt = "BUY"
    elif fisher['fwh'] < fisher['fml'] and closep[-1] < fisher['fml'] and fisher['fwh1'] > fisher['fml1']:
        fishlt = "SELL"
    else:
        fishlt = None

    if fisher['fwl1'] > fisher['fmh1'] and closep[-2] > fisher['fmh1'] and fisher['fwl2'] < fisher['fmh2']:
        fishlt1 = "BUY"
    elif fisher['fwh1'] < fisher['fml1'] and closep[-2] < fisher['fml1'] and fisher['fwh2'] > fisher['fml2']:
        fishlt1 = "SELL"
    else:
        fishlt1 = None

    if (closep[-1] > closep[-2] and closep[-1] > fisher['fwl'] and
        fisher['fdl'] > fisher['fwh'] and fisher['fwh'] < fisher['fml'] and fisher['fdl1'] < fisher['fwh1']):
        counter = "BUY"
    elif (closep[-1] < closep[-2] and closep[-1] < fisher['fwh'] and
          fisher['fdh'] < fisher['fwl'] and fisher['fwl'] > fisher['fmh'] and fisher['fdh1'] > fisher['fwl1']):
        counter = "SELL"
    else:
        counter = None

    if (closep[-2] > closep[-3] and closep[-2] > fisher['fwl1'] and
        fisher['fdl1'] > fisher['fwh1'] and fisher['fwh1'] < fisher['fml1'] and fisher['fdl2'] < fisher['fwh2']):
        counter1 = "BUY"
    elif (closep[-2] < closep[-3] and closep[-2] < fisher['fwh1'] and
          fisher['fdh1'] < fisher['fwl1'] and fisher['fwl1'] > fisher['fmh1'] and fisher['fdh2'] > fisher['fwl2']):
        counter1 = "SELL"
    else:
        counter1 = None

    return fish, fish1, fishlt, fishlt1, counter, counter1


def get_simple_fisher_signals(fisher, closep):
    """Get simple (non-crossed) Fisher signals for previous period"""
    if fisher['fdl1'] > fisher['fwh1'] > fisher['fmh1'] and fisher['fwl1'] > fisher['fml1']:
        fish2 = "B"
    elif fisher['fdh1'] < fisher['fwl1'] < fisher['fml1'] and fisher['fwh1'] < fisher['fmh1']:
        fish2 = "S"
    else:
        fish2 = None

    if fisher['fwl1'] > fisher['fmh1']:
        fishlt2 = "B"
    elif fisher['fwh1'] < fisher['fml1']:
        fishlt2 = "S"
    else:
        fishlt2 = None


    if fisher['fdl1'] > fisher['fwh1'] and fisher['fwh1'] < fisher['fml']:
        counter2 = "B"
    elif fisher['fdh1'] < fisher['fwl1'] and fisher['fwl1'] > fisher['fmh1']:
        counter2 = "S"
    else:
        counter2 = None

    return fish2, fishlt2, counter2



def calculate_moving_average_signals(closep):
    """Calculate exponential moving average based signals"""
    emva3 = talib.mva(closep.values, 3, "e")
    emva8 = talib.mva(closep.values, 8, "e")
    emva14 = talib.mva(closep.values, 14, "e")
    emva30 = talib.mva(closep.values, 30, "e")

    if (closep[-1] > closep[-2] and emva3[-1] > emva8[-1] > emva14[-1] and
        closep[-1] > emva8[-1] and (emva3[-2] < emva8[-2] or emva8[-2] < emva14[-2])):
        mom = "BUY"
    elif (closep[-1] < closep[-2] and emva3[-1] < emva8[-1] < emva14[-1] and
          closep[-1] < emva8[-1] and (emva3[-2] > emva8[-2] or emva8[-2] > emva14[-2])):
        mom = "SELL"
    else:
        mom = None

    if (closep[-2] > closep[-3] and emva3[-2] > emva8[-2] > emva14[-2] and
        closep[-2] > emva8[-2] and (emva3[-3] < emva8[-3] or emva8[-3] < emva14[-3])):
        mom1 = "BUY"
    elif (closep[-2] < closep[-3] and emva3[-2] < emva8[-2] < emva14[-2] and
          closep[-2] < emva8[-2] and (emva3[-3] > emva8[-3] or emva8[-3] > emva14[-3])):
        mom1 = "SELL"
    else:
        mom1 = None

    if (emva8[-1] > emva14[-1] > emva30[-1] and closep[-1] > emva14[-1] and
        (emva8[-2] < emva14[-2] or emva14[-2] < emva30[-2])):
        hybrid = "BUY"
    elif (emva8[-1] < emva14[-1] < emva30[-1] and closep[-1] < emva14[-1] and
          (emva8[-2] > emva14[-2] or emva14[-2] > emva30[-2])):
        hybrid = "SELL"
    else:
        hybrid = None

    if (emva8[-2] > emva14[-2] > emva30[-2] and closep[-2] > emva14[-2] and
        (emva8[-3] < emva14[-3] or emva14[-3] < emva30[-3])):
        hybrid1 = "BUY"
    elif (emva8[-2] < emva14[-2] < emva30[-2] and closep[-2] < emva14[-2] and
          (emva8[-3] > emva14[-3] or emva14[-3] > emva30[-3])):
        hybrid1 = "SELL"
    else:
        hybrid1 = None

    if emva3[-2] > emva8[-2] > emva14[-2]:
        mom2 = "B"
    elif emva3[-2] < emva8[-2] < emva14[-2]:
        mom2 = "S"
    else:
        mom2 = None

    if emva8[-2] > emva14[-2] > emva30[-2]:
        hybrid2 = "B"
    elif emva8[-2] < emva14[-2] < emva30[-2]:
        hybrid2 = "S"
    else:
        hybrid2 = None

    return {
        'mom': mom, 'mom1': mom1, 'mom2': mom2,
        'hybrid': hybrid, 'hybrid1': hybrid1, 'hybrid2': hybrid2,
        'emva3': emva3, 'emva8': emva8, 'emva14': emva14, 'emva30': emva30
    }



def calculate_kpi(closep, imp_vol, daily_price_chg, chg_type, generic_name, intraday_price=None):
    """
    Calculate KPI (Key Performance Indicator) based on implied volatility.

    Args:
        closep: Close price series
        imp_vol: Implied volatility series (can be DataFrame or Series)
        daily_price_chg: Daily price change series
        chg_type: "FLAT" or "SPRD"
        generic_name: Generic ticker name
        intraday_price: Optional intraday price DataFrame

    Returns:
        Dict with KPI metrics
    """
    if len(imp_vol.dropna()) == 0:
        imp_vol = daily_price_chg.rolling(30).std() * 100 * np.sqrt(252)

    if len(imp_vol) == 0:
        return {'kpi_on': np.nan, 'kpi_1d': np.nan, 'kpi_avg': np.nan}

    imp_vol.fillna(method="ffill", inplace=True)

    if chg_type == "FLAT" and generic_name == "GXA Index":
        if intraday_price is not None and len(intraday_price) > 0:
            closep_gxa = intraday_price.loc[:today()].iloc[-1].close
            kpi_on = (closep[-1] - closep_gxa) / (closep_gxa * imp_vol[-2] / 100 / np.sqrt(252))
        else:
            kpi_on = (closep[-1] - closep[-2]) / (closep[-1] * imp_vol[-2] / 100 / np.sqrt(252))
        kpi_1d = (closep[-2] - closep[-3]) / (closep[-3] * imp_vol[-3] / 100 / np.sqrt(252))
        kpi = (closep - closep.shift(1)) / (closep.shift(1) * imp_vol.shift(1) / 100 / np.sqrt(252))
    elif chg_type == "SPRD":
        kpi_on = (closep[-1] - closep[-2]) / (imp_vol[-2] / 100 / np.sqrt(252))
        kpi_1d = (closep[-2] - closep[-3]) / (imp_vol[-3] / 100 / np.sqrt(252))
        kpi = (closep - closep.shift(1)) / (imp_vol.shift(1) / 100 / np.sqrt(252))
    elif chg_type == "FLAT":
        kpi_on = (closep[-1] - closep[-2]) / (closep[-1] * imp_vol[-2] / 100 / np.sqrt(252))
        kpi_1d = (closep[-2] - closep[-3]) / (closep[-2] * imp_vol[-3] / 100 / np.sqrt(252))
        kpi = (closep - closep.shift(1)) / (closep * imp_vol.shift(1) / 100 / np.sqrt(252))

    kpi_avg = talib.exp_avg(np.array(list(reversed(kpi[-14:].values))), a=0.94)

    return {'kpi_on': kpi_on, 'kpi_1d': kpi_1d, 'kpi_avg': kpi_avg}



def calculate_trend_index(price_change, range_spike, volume_spike_5d, three_day,
                          sharpe_3d, sharpe_22d, current_price_range, post_close, avg_true_range):
    """Calculate trend index based on multiple factors"""
    trend_index = 0

    if price_change > 0:
        if range_spike > 1.2:
            trend_index += 1
        if not pd.isna(volume_spike_5d) and volume_spike_5d > 1.2:
            trend_index += 1
        if three_day == "UP":
            trend_index += 0.5
        if sharpe_3d > 1:
            trend_index += sharpe_3d
        elif sharpe_3d > 0.5 and sharpe_22d > 1:
            trend_index += 0.5
        if current_price_range == "HIGH":
            trend_index += 0.5
        if post_close / avg_true_range[-2] > 0.2:
            trend_index += 0.5
    elif price_change <= 0:
        if range_spike > 1.2:
            trend_index -= 1
        if not pd.isna(volume_spike_5d) and volume_spike_5d > 1.2:
            trend_index -= 1
        if three_day == "DOWN":
            trend_index -= 0.5
        if sharpe_3d < -1:
            trend_index += sharpe_3d
        elif sharpe_3d < -0.5 and sharpe_22d < -1:
            trend_index -= 0.5
        if current_price_range == "LOW":
            trend_index -= 0.5
        if post_close / avg_true_range[-2] < -0.2:
            trend_index -= 0.5

    return trend_index



def determine_combined_signals(trend_index, price_change, mom, mom1, hybrid, hybrid1,
                               fish, fish1, fishlt, fishlt1, counter, counter1):
    """Determine combined trading signals based on trend index"""
    signals = {
        'mom_signal': None, 'hybrid_signal': None, 'fish_signal': None,
        'fishlt_signal': None, 'counter_signal': None,
        'mom_signal_ystd': None, 'hybrid_signal_ystd': None, 'fish_signal_ystd': None,
        'fishlt_signal_ystd': None, 'counter_signal_ystd': None
    }

    if trend_index > 2 and price_change > 0:
        if mom == "BUY" or mom1 == "BUY":
            signals['mom_signal'] = "BUY"
        if mom1 == "BUY":
            signals['mom_signal_ystd'] = "BUY"
        if hybrid == "BUY" or hybrid1 == "BUY":
            signals['hybrid_signal'] = "BUY"
        if hybrid1 == "BUY":
            signals['hybrid_signal_ystd'] = "BUY"
        if fish == "BUY" or fish1 == "BUY":
            signals['fish_signal'] = "BUY"
        if fish1 == "BUY":
            signals['fish_signal_ystd'] = "BUY"
        if fishlt == "BUY" or fishlt1 == "BUY":
            signals['fishlt_signal'] = "BUY"
        if fishlt1 == "BUY":
            signals['fishlt_signal_ystd'] = "BUY"
        if counter == "BUY" or counter1 == "BUY":
            signals['counter_signal'] = "BUY"
        if counter1 == "BUY":
            signals['counter_signal_ystd'] = "BUY"
    elif trend_index < -2 and price_change < 0:
        if mom == "SELL" or mom1 == "SELL":
            signals['mom_signal'] = "SELL"
        if mom1 == "SELL":
            signals['mom_signal_ystd'] = "SELL"
        if hybrid == "SELL" or hybrid1 == "SELL":
            signals['hybrid_signal'] = "SELL"
        if hybrid1 == "SELL":
            signals['hybrid_signal_ystd'] = "SELL"
        if fish == "SELL" or fish1 == "SELL":
            signals['fish_signal'] = "SELL"
        if fish1 == "SELL":
            signals['fish_signal_ystd'] = "SELL"
        if fishlt == "SELL" or fishlt1 == "SELL":
            signals['fishlt_signal'] = "SELL"
        if fishlt1 == "SELL":
            signals['fishlt_signal_ystd'] = "SELL"
        if counter == "SELL" or counter1 == "SELL":
            signals['counter_signal'] = "SELL"
        if counter1 == "SELL":
            signals['counter_signal_ystd'] = "SELL"

    return signals


def calculate_signal_flag(combined_signals, trend_index):
    """Determine if ticker should be flagged for signal"""
    if (combined_signals['mom_signal'] in ["BUY", "SELL"] or
        combined_signals['hybrid_signal'] in ["BUY", "SELL"] or
        combined_signals['fish_signal'] in ["BUY", "SELL"] or
        combined_signals['fishlt_signal'] in ["BUY", "SELL"] or
        combined_signals['counter_signal'] in ["BUY", "SELL"] or
        trend_index > 3 or trend_index < -3):
        return 1
    return 0



def get_expiry_info(ticker):
    """Get expiry date and days before expiry"""
    try:
        info = bbg.bref(ticker, ["FUT_LAST_TRADE_DT", "PX_CLOSE_1D"], use_bpipe=False)
        exp_date = pd.to_datetime(info["FUT_LAST_TRADE_DT"].values[0]).date()
    except:
        exp_date = np.nan

    if isinstance(exp_date, dt.date) and not pd.isna(exp_date):
        days_before_exp = (exp_date - today().date()).days
    else:
        days_before_exp = np.nan

    return exp_date, days_before_exp


def check_iroll_tag(key_tuple_or_generic):
    """
    Check if ticker should be tagged as IROLL.

    Args:
        key_tuple_or_generic: Either a tuple like (instr, generic_name) or just generic_name string

    Returns:
        "IROLL" if matches, None otherwise
    """
    iroll_list = [
        "CO 1st Spread", "CO 2nd Spread",
        "CL 1st Spread", "CL 2nd Spread",
        "XB 1st Spread", "XB 2nd Spread",
        "HO 1st Spread", "HO 2nd Spread",
        "QS 1st Spread", "QS 2nd Spread",
        "NG 1st Spread", "NG 2nd Spread",
        "TZT 1st spread", "TZT 2nd spread",
    ]

    if isinstance(key_tuple_or_generic, tuple):
        generic_name = key_tuple_or_generic[1] if len(key_tuple_or_generic) > 1 else key_tuple_or_generic[0]
    else:
        generic_name = key_tuple_or_generic

    if key_tuple_or_generic in iroll_list or generic_name in iroll_list:
        return "IROLL"
    return None



def calculate_volume_spikes(intraday_price, daily_price, ticker_val, edate):
    """
    Calculate intraday volume cumulative and spike metrics.

    Args:
        intraday_price: Intraday price DataFrame
        daily_price: Daily price DataFrame
        ticker_val: Ticker value tuple (ticker, instr, chg_type, enabled, has_vol)
        edate: End date

    Returns:
        Dict with volume metrics and processed volume data
    """
    has_vol = ticker_val[4]
    ticker = ticker_val[0]
    chg_type = ticker_val[2]

    if not has_vol or len(intraday_price) <= 10 or ticker_val[0].rpartition(" ")[-1] == "Equity":
        return {
            'volume_spike_5d': np.nan,
            'volume_spike_5d_1': np.nan,
            'volume_spike_20d': np.nan,
            'volume_at_minute': pd.Series(dtype="float64")
        }

    date_range_by_minute = pd.DatetimeIndex([
        dt for dt in datetime_range(
            intraday_price.index[0],
            intraday_price.index[-1],
            dt.timedelta(minutes=10),
        )
    ])
    date_range_by_minute = date_range_by_minute[date_range_by_minute.dayofweek != 5]
    date_range_by_minute = date_range_by_minute[date_range_by_minute.dayofweek != 6]

    volume_by_minute = intraday_price["volume"].reindex(date_range_by_minute)
    volume_by_minute.fillna(value=0, inplace=True)
    volume_by_minute = volume_by_minute.to_frame("volume")
    volume_by_minute["date"] = volume_by_minute.index.date

    agg_volume = volume_by_minute.groupby(["date"])["volume"].cumsum()
    agg_volume = agg_volume.to_frame("agg_volume")
    agg_volume["time"] = volume_by_minute.index.time

    volume_at_minute = agg_volume.loc[agg_volume["time"] == agg_volume["time"].iloc[-1], "agg_volume"]
    volume_at_minute.drop(volume_at_minute.loc[volume_at_minute == 0].index, axis=0, inplace=True)
    volume_at_minute = volume_at_minute.sort_index()

    volume_at_minute = adjust_volume_for_roll(volume_at_minute, ticker_val, edate)

    if len(volume_at_minute) > 20 and volume_at_minute.index[-1] > today():
        volume_spike_5d = volume_at_minute.iloc[-1] / volume_at_minute.rolling(5).mean().iloc[-2]
        volume_spike_20d = volume_at_minute.iloc[-1] / volume_at_minute.rolling(20).mean().iloc[-2]
    else:
        volume_spike_5d = np.nan
        volume_spike_20d = np.nan

    if daily_price.index[-1] == today():
        volume_spike_5d_1 = daily_price["VOLUME"].iloc[-2] / daily_price["VOLUME"].rolling(5).mean().iloc[-3]
    elif daily_price.index[-1] > today():
        volume_spike_5d_1 = daily_price["VOLUME"].iloc[-3] / daily_price["VOLUME"].rolling(5).mean().iloc[-4]
    else:
        volume_spike_5d_1 = daily_price["VOLUME"].iloc[-1] / daily_price["VOLUME"].rolling(5).mean().iloc[-2]

    return {
        'volume_spike_5d': volume_spike_5d,
        'volume_spike_5d_1': volume_spike_5d_1,
        'volume_spike_20d': volume_spike_20d,
        'volume_at_minute': volume_at_minute
    }


def adjust_volume_for_roll(volume_at_minute, ticker_val, edate):
    """Adjust volume for contract rolls"""
    ticker, instr, chg_type, enabled, has_vol = ticker_val
    last_contract = None
    roll_date = None

    try:
        if chg_type == "SPRD":
            from ecm.cmds.ticker import spread_to_flat, last_ticker
            sprd1 = spread_to_flat(ticker)[0]
            try:
                from market_scan_helpers import MarketDataLoader
                loader = MarketDataLoader()
                gen_month = loader.get_gen_month(sprd1)
                sprd0 = last_ticker(sprd1, gen_month)
                if sprd1[:2] in ["NG", "MO"]:
                    last_contract = f"{sprd0[:3]}{sprd0[4]}{sprd1[:3]}{sprd1[4]} Comdty"
                else:
                    last_contract = f"{sprd0.split(' ')[0]}{sprd1}"
                expiry = bbg.bref(sprd0, ["LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST"], use_bpipe=False)
                expiry = expiry.min(axis=1).values[0]
                if isinstance(expiry, str):
                    expiry = pd.to_datetime(expiry)
                roll_date = expiry - BDay(3)
            except:
                pass
        elif chg_type == "FLAT" and ticker[:3] not in ["DET", "JXY", "TRC"]:
            try:
                from ecm.cmds.ticker import last_ticker
                from market_scan_helpers import MarketDataLoader
                loader = MarketDataLoader()
                gen_month = loader.get_gen_month(ticker)
                last_contract = last_ticker(ticker, gen_month)
                expiry = bbg.bref(last_contract, ["LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST"], use_bpipe=False)
                expiry = expiry.min(axis=1).values[0]
                if isinstance(expiry, str):
                    expiry = pd.to_datetime(expiry)
                roll_date = expiry - BDay(3)
            except:
                pass

        if last_contract is not None and roll_date is not None and edate > roll_date > edate - BDay(10):
            intraday_price_last = bbg.bdib(last_contract, sdate=today() - BDay(10), edate=today() + BDay(1), interval=10)
            date_range_by_minute_last = pd.DatetimeIndex([
                d for d in datetime_range(intraday_price_last.index[0], intraday_price_last.index[-1], dt.timedelta(minutes=10))
            ])
            date_range_by_minute_last = date_range_by_minute_last[date_range_by_minute_last.dayofweek != 5]
            date_range_by_minute_last = date_range_by_minute_last[date_range_by_minute_last.dayofweek != 6]

            volume_by_minute_last = intraday_price_last["volume"].reindex(date_range_by_minute_last)
            volume_by_minute_last.fillna(value=0, inplace=True)
            volume_by_minute_last = volume_by_minute_last.to_frame("volume")
            volume_by_minute_last["date"] = volume_by_minute_last.index.date

            agg_volume_last = volume_by_minute_last.groupby(["date"])["volume"].cumsum()
            agg_volume_last = agg_volume_last.to_frame("agg_volume")
            agg_volume_last["time"] = agg_volume_last.index.time

            volume_at_minute_last = agg_volume_last.loc[agg_volume_last["time"] == agg_volume_last["time"].iloc[-1], "agg_volume"]
            volume_at_minute_last.drop(volume_at_minute_last.loc[volume_at_minute_last == 0].index, axis=0, inplace=True)
            volume_at_minute_last = volume_at_minute_last.sort_index()

            if roll_date >= today():
                roll_date = roll_date - BDay(1)
            volume_at_minute[volume_at_minute.index < roll_date] = volume_at_minute_last[volume_at_minute_last.index < roll_date]
    except Exception as e:
        log.debug(f"Volume roll adjustment failed: {e}")

    return volume_at_minute



def generate_alerts(instr, ticker, chg_type, price_change_pct, price_change_pct1,
                    range_spike, range_spike1, volume_spike_5d, volume_spike_5d_1,
                    sharpe_3d_cob, daily_price):
    """
    Generate alert lists based on range/volume spikes.

    Returns:
        Tuple of (all_alerts, oil_alerts, ng_alerts, macro_alerts,
                  all_today_alerts, oil_today_alerts, ng_today_alerts, macro_today_alerts)
    """
    alert_email_all = []
    alert_email_oil = []
    alert_email_ng = []
    alert_email_macro = []
    alert_email_all_today = []
    alert_email_oil_today = []
    alert_email_ng_today = []
    alert_email_macro_today = []

    follow_through = price_change_pct / price_change_pct1

    alert_row = [
        instr, ticker, follow_through, price_change_pct, range_spike,
        volume_spike_5d, price_change_pct1, range_spike1,
        volume_spike_5d_1, chg_type, sharpe_3d_cob
    ]

    if range_spike1 * volume_spike_5d_1 > 2.25:
        if instr not in ["EQT", "FI", "CCY", "VOL"]:
            alert_email_all.append(alert_row)
        else:
            alert_email_macro.append(alert_row)

        if instr in ["WTI", "BRT", "GASOLINE", "DIST"]:
            alert_email_oil.append(alert_row)
        elif instr in ["NG", "TTF", "US_POWER", "HH"]:
            alert_email_ng.append(alert_row)

    if range_spike > 1.5 and daily_price.index[-1] >= today():
        if instr not in ["EQT", "FI", "CCY", "VOL"]:
            alert_email_all_today.append(alert_row)
        else:
            alert_email_macro_today.append(alert_row)

        if instr in ["WTI", "BRT", "GASOLINE", "DIST"]:
            alert_email_oil_today.append(alert_row)
        elif instr in ["NG", "TTF", "US_POWER", "HH"]:
            alert_email_ng_today.append(alert_row)

    return (alert_email_all, alert_email_oil, alert_email_ng, alert_email_macro,
            alert_email_all_today, alert_email_oil_today, alert_email_ng_today, alert_email_macro_today)


def generate_base_metal_alerts(instr, ticker, closep, chg_type):
    """Generate alerts for base metals based on z-score"""
    alert_bm = []
    alert_bm_pm = []

    excluded_tickers = [
        "SXPP Index", "XME US Equity", "GLEN LN Equity",
        "AA US Equity", "NUE US Equity", "BHP LN Equity",
        "SH000909 Index"
    ]

    if instr != "BM" or ticker in excluded_tickers:
        return alert_bm, alert_bm_pm

    if chg_type == "FLAT":
        pchg = closep.diff() / closep.shift(1)
    elif chg_type == "SPRD":
        pchg = closep.diff()
    else:
        return alert_bm, alert_bm_pm

    std20d = pchg.rolling(20).std()

    if closep.index[-1] >= today():
        zscore_am = pchg[-2] / std20d[-2]
        zscore_pm = pchg[-1] / std20d[-1]

        if zscore_am > 1.5 or zscore_am < -1.5:
            alert_bm.append([
                ticker, pchg[-2], closep[-2],
                closep.rolling(20).mean()[-2],
                zscore_am, closep.index[-2], chg_type
            ])

        if zscore_pm > 1.5 or zscore_pm < -1.5:
            alert_bm_pm.append([
                ticker, pchg[-1], closep[-1],
                closep.rolling(20).mean()[-1],
                zscore_pm, closep.index[-1], chg_type
            ])
    else:
        zscore_am = pchg[-1] / std20d[-1]
        if zscore_am > 1.5 or zscore_am < -1.5:
            alert_bm.append([
                ticker, pchg[-1], closep[-1],
                closep.rolling(20).mean()[-1],
                zscore_am, closep.index[-1], chg_type
            ])

    return alert_bm, alert_bm_pm


def generate_volume_alert(instr, ticker, volume_spike_5d, price_change_pct, chg_type, volume_at_minute):
    """Generate intraday volume alert"""
    if volume_spike_5d > 1.5 and len(volume_at_minute) > 0 and volume_at_minute.index[-1] >= today():
        return [instr, ticker, volume_spike_5d, price_change_pct, chg_type]
    return None



def check_weekly_high_low(instr, ticker, closep, highp, lowp, week_sdate,
                          price_change_pct, range_spike, volume_spike_5d):
    """
    Check if current price represents a weekly high or low.

    Returns:
        Tuple of (weekly_high_row, weekly_low_row) or (None, None)
    """
    if week_sdate >= today() or week_sdate >= closep.index[-1]:
        return None, None

    if (today() + BDay(1)).weekday() >= today().weekday():
        return None, None

    try:
        from dateutil.relativedelta import relativedelta

        if (highp.index[0] <= today() - relativedelta(years=1)) and (lowp.index[0] <= today() - relativedelta(years=1)):
            _highp = highp[highp.index[-1] - relativedelta(years=1) : highp.index[-1]]
            _lowp = lowp[lowp.index[-1] - relativedelta(years=1) : lowp.index[-1]]
        else:
            _highp = highp
            _lowp = lowp

        rolling_high_price = _highp[-252:].rolling(5)
        rolling_low_price = _lowp[-252:].rolling(5)

        z_score_latest = (_highp.iloc[-1] - rolling_high_price.mean()) / rolling_high_price.std(ddof=0)
        z_score_latest_low = (_lowp.iloc[-1] - rolling_low_price.mean()) / rolling_low_price.std(ddof=0)

        if z_score_latest.iloc[-1] > 1.5:
            weekly_high_row = [
                instr, ticker, closep.iloc[-1],
                np.max(highp.loc[week_sdate : highp.index[-2]]),
                price_change_pct, range_spike, volume_spike_5d
            ]
            return weekly_high_row, None
        elif z_score_latest_low.iloc[-1] < -1.5:
            weekly_low_row = [
                instr, ticker, closep.iloc[-1],
                np.min(lowp.loc[week_sdate : lowp.index[-2]]),
                price_change_pct, range_spike, volume_spike_5d
            ]
            return None, weekly_low_row
    except Exception as e:
        log.debug(f"Weekly high/low check failed: {e}")

    return None, None



def generate_sharpe_ratio_row(instr, ticker, chg_type, sharpe_3d, sharpe_3d_cob,
                              sharpe_22d, sharpe_3d_cob_1, sharpe_3d_cob_2,
                              sharpe_3d_cob_3, kpi_on, kpi_1d, kpi_avg,
                              trend_index, generic_name, folder_path):
    """
    Generate sharpe ratio row for tracking list.

    Returns:
        List with sharpe ratio metrics for output
    """
    if (sharpe_3d_cob > 0 and sharpe_22d > 0) or (sharpe_3d_cob < 0 and sharpe_22d < 0):
        signal = "TREND"
    elif (sharpe_3d_cob > 1 and sharpe_22d < -0.5) or (sharpe_3d_cob < -1 and sharpe_22d > 0.5):
        signal = "COUNTER"
    else:
        signal = "-"

    plot_link = f"<a href='{folder_path}\\candle_plots\\{generic_name}.html'>{ticker}</a>"

    return [
        instr,
        ticker,
        chg_type,
        sharpe_3d,
        sharpe_3d_cob,
        sharpe_22d,
        signal,
        sharpe_3d_cob_1,
        sharpe_3d_cob_2,
        sharpe_3d_cob_3,
        kpi_on,
        kpi_1d,
        kpi_avg,
        trend_index,
        plot_link,
    ]



def process_ticker_data(key, val, data_dict, fom_comments, fom_dict, week_sdate, folder_path):
    """
    Main orchestration function that processes all ticker data and generates signals.

    This function coordinates all the modular processing functions to replicate
    the original monolithic process_data function.

    Args:
        key: Tuple of (index, generic_name)
        val: Tuple of (ticker, instr, chg_type, enabled, has_vol)
        data_dict: Dict with 'daily', 'weekly', 'monthly', 'intraday' DataFrames
        fom_comments: DataFrame with FOM dates and comments
        fom_dict: Dict mapping instrument to vwap_track_date_range
        week_sdate: Week start date for weekly high/low detection
        folder_path: Path for output files

    Returns:
        Tuple of 15 lists:
            (output_list, alert_email_all, alert_email_oil, alert_email_ng, alert_email_macro,
             alert_email_all_today, alert_email_oil_today, alert_email_ng_today, alert_email_macro_today,
             alert_bm, alert_bm_pm, sharpe_ratio_list, weekly_high, weekly_low, intraday_cum_volume)
    """
    output_list = []
    alert_email_all = []
    alert_email_oil = []
    alert_email_ng = []
    alert_email_macro = []
    intraday_cum_volume = []
    alert_email_all_today = []
    alert_email_oil_today = []
    alert_email_ng_today = []
    alert_email_macro_today = []
    alert_bm = []
    alert_bm_pm = []
    sharpe_ratio_list = []
    weekly_high = []
    weekly_low = []

    ticker, instr, chg_type, enabled, has_vol = val
    generic_name = key[1]
    vwap_track_date_range = fom_dict[instr]
    edate = dt.datetime.now()

    if ticker is None:
        log.error(f"{generic_name} is not mapped not generating Signal")
        return empty_return_tuple()

    if not enabled:
        log.warning(f"Skipping Signals for: {instr}|{ticker}")
        return empty_return_tuple()

    log.info(f"Processing signals for {instr}|{ticker}")

    daily_price = data_dict.get("daily", pd.DataFrame())
    weekly_price = data_dict.get("weekly", pd.DataFrame())
    monthly_price = data_dict.get("monthly", pd.DataFrame())
    intraday_price = data_dict.get("intraday", pd.DataFrame())

    price_data = prepare_price_data(daily_price, weekly_price, monthly_price)
    if price_data is None:
        output_list.append([
            instr, ticker, generic_name,
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
        ])
        return (
            output_list, alert_email_all, alert_email_oil, alert_email_ng, alert_email_macro,
            alert_email_all_today, alert_email_oil_today, alert_email_ng_today, alert_email_macro_today,
            alert_bm, alert_bm_pm, sharpe_ratio_list, weekly_high, weekly_low, intraday_cum_volume,
        )

    fom_vwap, fom_delta = calculate_fom_vwap(ticker, vwap_track_date_range, intraday_price)

    exp_date, days_before_exp = get_expiry_info(ticker)

    price_changes = calculate_price_changes(price_data['closep'], chg_type, intraday_price)

    post_close = calculate_post_close(daily_price)

    fom_flag, fom_zscore, fom_date_str = calculate_fom_metrics(
        fom_comments, instr, price_changes['daily_price_chg'],
        price_data['highp'], price_data['lowp'], price_data['closep']
    )

    sto_ind = calculate_stochastic(price_data['highp'], price_data['lowp'], price_data['closep'])

    sharpe_metrics = calculate_sharpe_ratios(
        daily_price,
        price_changes['daily_price_chg'],
        price_changes['intraday_price_chg'],
        instr,
        chg_type,
        folder_path,
        key
    )

    fisher = calculate_fisher_indicators(
        price_data['highp'], price_data['lowp'], price_data['closep'],
        price_data['highp_w'], price_data['lowp_w'], price_data['closep_w'],
        price_data['highp_m'], price_data['lowp_m'], price_data['closep_m'],
        daily_price
    )

    fish, fish1, fishlt, fishlt1, counter, counter1 = determine_fisher_signals(fisher, price_data['closep'])
    fish2, fishlt2, counter2 = get_simple_fisher_signals(fisher, price_data['closep'])

    ma_signals = calculate_moving_average_signals(price_data['closep'])

    kpi_metrics = calculate_kpi(
        price_data['closep'], price_data['imp_vol'],
        price_changes['daily_price_chg'], chg_type,
        generic_name, intraday_price
    )

    range_metrics = calculate_range_metrics(
        price_data['highp'], price_data['lowp'],
        price_data['closep'], daily_price
    )

    three_day = calculate_three_day_trend(price_data['closep'])

    current_price_range = calculate_current_price_range(
        price_data['closep'], price_data['highp'], price_data['lowp']
    )

    if has_vol and len(intraday_price) > 10 and val[0].rpartition(" ")[-1] != "Equity":
        volume_metrics = calculate_volume_spikes(
            intraday_price, daily_price, val, edate
        )
        volume_spike_5d = volume_metrics['volume_spike_5d']
        volume_spike_5d_1 = volume_metrics['volume_spike_5d_1']
        volume_spike_20d = volume_metrics['volume_spike_20d']
        volume_at_minute = volume_metrics['volume_at_minute']
    else:
        volume_spike_5d = np.nan
        volume_spike_5d_1 = np.nan
        volume_spike_20d = np.nan
        volume_at_minute = pd.Series(dtype="float64")

    trend_index = calculate_trend_index(
        price_changes['price_change'],
        range_metrics['range_spike'],
        volume_spike_5d,
        three_day,
        sharpe_metrics['sharpe_3d'],
        sharpe_metrics['sharpe_22d'],
        current_price_range,
        post_close,
        range_metrics['avg_true_range']
    )

    combined_signals = determine_combined_signals(
        trend_index,
        price_changes['price_change'],
        ma_signals['mom'],
        ma_signals['mom1'],
        ma_signals['hybrid'],
        ma_signals['hybrid1'],
        fish,
        fish1,
        fishlt,
        fishlt1,
        counter,
        counter1
    )

    mom_signal = combined_signals['mom_signal']
    hybrid_signal = combined_signals['hybrid_signal']
    fish_signal = combined_signals['fish_signal']
    fishlt_signal = combined_signals['fishlt_signal']
    counter_signal = combined_signals['counter_signal']
    mom_signal_ystd = combined_signals['mom_signal_ystd']
    hybrid_signal_ystd = combined_signals['hybrid_signal_ystd']
    fish_signal_ystd = combined_signals['fish_signal_ystd']
    fishlt_signal_ystd = combined_signals['fishlt_signal_ystd']
    counter_signal_ystd = combined_signals['counter_signal_ystd']

    signal_flag = calculate_signal_flag(combined_signals, trend_index)

    iroll_tag = check_iroll_tag(key)

    (alerts_all, alerts_oil, alerts_ng, alerts_macro,
     alerts_all_today, alerts_oil_today, alerts_ng_today, alerts_macro_today) = generate_alerts(
        instr, ticker, chg_type,
        price_changes['price_change_pct'],
        price_changes['price_change_pct1'],
        range_metrics['range_spike'],
        range_metrics['range_spike1'],
        volume_spike_5d,
        volume_spike_5d_1,
        sharpe_metrics['sharpe_3d_cob'],
        daily_price
    )

    alert_email_all.extend(alerts_all)
    alert_email_oil.extend(alerts_oil)
    alert_email_ng.extend(alerts_ng)
    alert_email_macro.extend(alerts_macro)
    alert_email_all_today.extend(alerts_all_today)
    alert_email_oil_today.extend(alerts_oil_today)
    alert_email_ng_today.extend(alerts_ng_today)
    alert_email_macro_today.extend(alerts_macro_today)

    bm_alert_am, bm_alert_pm = generate_base_metal_alerts(instr, ticker, price_data['closep'], chg_type)
    alert_bm.extend(bm_alert_am)
    alert_bm_pm.extend(bm_alert_pm)

    vol_alert = generate_volume_alert(
        instr, ticker, volume_spike_5d,
        price_changes['price_change_pct'],
        chg_type, volume_at_minute
    )
    if vol_alert:
        intraday_cum_volume.append(vol_alert)

    high_alert, low_alert = check_weekly_high_low(
        instr, ticker, price_data['closep'],
        price_data['highp'], price_data['lowp'],
        week_sdate,
        price_changes['price_change_pct'],
        range_metrics['range_spike'],
        volume_spike_5d
    )
    if high_alert:
        weekly_high.append(high_alert)
    if low_alert:
        weekly_low.append(low_alert)

    sharpe_row = generate_sharpe_ratio_row(
        instr, ticker, chg_type,
        sharpe_metrics['sharpe_3d'],
        sharpe_metrics['sharpe_3d_cob'],
        sharpe_metrics['sharpe_22d'],
        sharpe_metrics['sharpe_3d_cob_1'],
        sharpe_metrics['sharpe_3d_cob_2'],
        sharpe_metrics['sharpe_3d_cob_3'],
        kpi_metrics['kpi_on'],
        kpi_metrics['kpi_1d'],
        kpi_metrics['kpi_avg'],
        trend_index,
        generic_name,
        folder_path
    )
    sharpe_ratio_list.append(sharpe_row)

    output_row = [
        instr,
        ticker,
        generic_name,
        days_before_exp,  # Use days not the date itself
        price_changes['last_price'],
        kpi_metrics['kpi_on'],
        kpi_metrics['kpi_1d'],
        price_changes['price_change'],
        chg_type,
        fom_flag,
        fom_date_str,
        sto_ind,
        post_close,
        sharpe_metrics['sharpe_3d'],
        sharpe_metrics['sharpe_22d'],
        ma_signals['mom2'],     # Simple mom
        ma_signals['hybrid2'],  # Simple hybrid
        fish2,                 # Simple fish
        fishlt2,               # Simple fishlt
        counter2,              # Simple counter
        mom_signal,            # Complex mom signal (from combined_signals)
        hybrid_signal,         # Complex hybrid signal (from combined_signals)
        fish_signal,           # Complex fish signal (from combined_signals)
        fishlt_signal,         # Complex fishlt signal (from combined_signals)
        counter_signal,        # Complex counter signal (from combined_signals)
        kpi_metrics['kpi_avg'], # KPI Index
        trend_index,
        three_day,
        range_metrics['range_spike'],
        volume_spike_5d,
        volume_spike_20d,
        current_price_range,
        signal_flag,
        mom_signal_ystd,        # Yesterday mom (from combined_signals)
        hybrid_signal_ystd,     # Yesterday hybrid (from combined_signals)
        fish_signal_ystd,       # Yesterday fish (from combined_signals)
        fishlt_signal_ystd,     # Yesterday fishlt (from combined_signals)
        counter_signal_ystd,    # Yesterday counter (from combined_signals)
        price_changes['price_change_pct'],
        price_changes['chg_5d'],
        iroll_tag,
        fom_delta,
        fom_vwap,
        fom_zscore,
    ]

    output_list.append(output_row)

    return (
        output_list,
        alert_email_all,
        alert_email_oil,
        alert_email_ng,
        alert_email_macro,
        alert_email_all_today,
        alert_email_oil_today,
        alert_email_ng_today,
        alert_email_macro_today,
        alert_bm,
        alert_bm_pm,
        sharpe_ratio_list,
        weekly_high,
        weekly_low,
        intraday_cum_volume,
    )
