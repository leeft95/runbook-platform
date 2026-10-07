import pandas as pd
import datetime as dtm
import numpy as np
from loguru import logger as log
from ecm.cmds.core.bbg_blp import bdh, bref
from ecm.cmds.core.cdr import today
import ecm.cmds.core.table as table
import ecm.cmds.core.chart as chart
import ecm.cmds.core.talib as talib
from ecm.cmds.core._email import send_email
from ecm.cmds.core.config import html_path, root_path
from dateutil.relativedelta import relativedelta
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay
from china_gold_cboc import update as get_china_gold_cboc_data
from ecm.cmds.core.alerting import AlertsAPI


def _unrecovered(location, *visible_values):
    raise NotImplementedError(f"etf_aum photographed source: {location}")


US_BUSINESS_DAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())
pd.set_option("display.float_format", lambda x: r"% g" % x)
send_to = ["commods@elementcapital.com"]
report_name = "ETF Flows Alert Prod"
file_name = "etf_aum"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"
threshold_z_score = 1.5
etf_html_folder = f"{html_path}\\cross_cmds\\ETF"
etf_cix_def_wiki = "https://elementcapital.atlassian.net/wiki/spaces/L025/pages/2168422403/ETF+Flow+CIX+Def" + _unrecovered('original line 36: wiki URL suffix')
alerts_api = AlertsAPI(alert_type="ETF Flows", description="ETF Flows ZScore Alerting", env="prod")

flow_tickers = {
    "Crude": ".CRUETF Index",
    "NatGas": ".NGETF S 93133693 Index",
    "Copper": ".CUETF Index",
    "Gold": ".GLETF Index",
    "GoldChina": ".GLFCNH Index",
    "SilverChina": ".SIFCHN Index",
    "GoldExChina": ".GLWFLOW Index",
    "Silver": ".SILFLW Index",
    "SilverExChina": ".SLWFLOW Index",
    "Bitcoin": ".BTC Index",
    "Etherum": ".ETHETF Index",
    "CrossCmds": None,
}
eq_fund_tickers = {
    "Crude": "XOP US Equity",
    "NatGas": ".DRY_E&P Index",
    "Copper": "COPX US Equity",
    "Gold": "GDX US Equity",
    "GoldChina": "GDX US Equity",
    "Silver": "SIL US Equity",
    "SilverChina": "SIL US Equity",
    "Bitcoin": "WGMI US Equity",
    "Etherum": "ETH US Equity",
    "CrossCmds": None,
}
future_tickers = {
    "Crude": "CODEC1 Comdty",
    "NatGas": "NGM26 Comdty",
    "Copper": "HGDEC1 Comdty",
    "Gold": "GCDEC1 Comdty",
    "GoldChina": "GCDEC1 Comdty",
    "Silver": "SIDEC1 Comdty",
    "SilverChina": "SIDEC1 Comdty",
    "Bitcoin": "BTCDEC1 Comdty",
    "Etherum": "DCRDEC1 Comdty",
    "CrossCmds": None,
}
total_holdings_tickers = {
    "Crude": ".CRUFTOT Index",
    "NatGas": ".NGETFTOT Index",
    "Copper": ".COPFTOT Index",
    "Gold": ".GLTOTL Index",
    "GoldChina": ".GLTCNH Index",
    "GoldExChina": "ETFGTOTL Index",
    "Silver": ".SILTOT Index",
    "SilverChina": ".SITCHN Index",
    "SilverExChina": "ETSITOTL Index",
    "Bitcoin": ".BTCTOT Index",
    "Etherum": ".ETHTOT Index",
    "CrossCmds": ".CMDFTOT Index",
}
scale_to_millions = {
    "Crude": 1,  # reported in Millions
    "NatGas": 1,
    "Carbon": 1,
    "Copper": 1,
    "Gold": 1e-6,  # reported in troy ounce (multiplied by ccy usd spot)
    "GoldChina": 1,  # reported in Millions
    "GoldExChina": 1e-6,  # reported in Millions
    "SilverChina": 1,
    "Silver": 1e-6,  # reported in troy ounce (multiplied by ccy usd spot)
    "SilverExChina": 1e-6,  # reported in Millions
    "Bitcoin": 1,
    "Etherum": 1,
    "CrossCmds": 1,
}
etf_start_date_overrides = {
    "Bitcoin": dtm.datetime(2024, 1, 11),
    "Etherum": dtm.datetime(2024, 1, 1),
}


def last_business_day(dt):
    if dt.weekday() == 5:
        return dt - dtm.timedelta(days=1)
    if dt.weekday() == 6:
        return dt - dtm.timedelta(days=2)
    return dt


def get_plot_data(ticker):
    start_date = dtm.datetime(today().year - 8, 1, 1)
    end_date = last_business_day(today() - dtm.timedelta(days=1))
    data = bdh([ticker], fields=["PX_LAST"], sdate=start_date, edate=end_date).sort_index()
    if not data.empty:
        data.columns = [ticker]
    else:
        data = pd.DataFrame(columns=[ticker])
    return data


def get_plot_data_oi(ticker):
    start_date = dtm.datetime(today().year - 8, 1, 1)
    end_date = last_business_day(today() - dtm.timedelta(days=1))
    data = bdh([ticker], fields=["PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW", "VOLUME"], sdate=start_date, edate=end_date)
    return data


def get_cumsum_change(series, n_days):
    result = series.iloc[-n_days:].cumsum()[-1]
    return result


def get_change(series, n_days):
    if len(series) >= n_days:
        return series.iloc[-1] - series.iloc[-n_days]
    return np.nan


def get_change_stats(series, n_days: list):
    results = {}
    for n in n_days:
        if len(series) >= n:
            n_ = 2 if n == 1 else n
            results[n] = series.iloc[-1] - series.iloc[-n_]
        else:
            results[n] = np.nan
    return results


def get_cumsum_change_stats(series, n_days: list):
    results = {}
    for n in n_days:
        if len(series) >= n:
            results[n] = series.iloc[-n:].cumsum()[-1]
        else:
            results[n] = np.nan
    return results


def get_percent_change_stats(series, n_days: list):
    results = {}
    for n in n_days:
        n_ = 2 if n == 1 else n
        if len(series) >= n_:
            results[n] = (series.iloc[-1] - series.iloc[-n_]) / (series.iloc[-1])
        else:
            results[n] = np.nan
    return results


def get_n_months_data(series, n_months, n_days: list):
    result = {}
    for n in n_days:
        if len(series) > n_months * 30:
            three_months_data = series[series.index[-n] - relativedelta(months=3):].copy()
            result[n] = three_months_data.to_frame()
        else:
            result[n] = pd.DataFrame()
    return result


def get_z_score(change, lookback_data):
    if pd.isna(change):
        return np.nan
    if not lookback_data.empty:
        z_score = (change / lookback_data.std(ddof=0)).iloc[-1]
    else:
        z_score = np.nan
    return z_score


def get_y1_ytd(data, ticker, is_pct=False, cumsum=False):
    t1y = last_business_day(data.index[-1] - relativedelta(years=1))
    try:
        etf_data_y1 = (data.iloc[-1] - data.loc[t1y])[ticker]
    except KeyError:
        if data.index.min() > t1y:
            etf_data_y1 = data.iloc[-1][ticker] - data.iloc[0][ticker]
        else:
            etf_data_y1 = (data.iloc[-1] - data.loc[f"{t1y.year}-{t1y.month}"].iloc[-1])[ticker]
    ytd_index = data[ticker].loc[f"{today().year - 1}-12"].index[-1]
    if cumsum:
        etf_data_ytd = (data[ticker].loc[ytd_index:]).cumsum()[-1]
    else:
        etf_data_ytd = data[ticker].iloc[-1] - data[ticker].loc[ytd_index]
    if is_pct:
        etf_data_y1 = etf_data_y1 / data.iloc[-1][ticker]
        etf_data_ytd = etf_data_ytd / data.iloc[-1][ticker]
    return etf_data_y1, etf_data_ytd


def get_table_row_dict(
    alert_name, name, link_name, d1, d5, d13, ytd, y1, z_score_latest, z_score_latest_5d, z_score_latest_13d,
    z_score_latest_etf, z_score_latest_5d_etf, z_score_latest_13d_etf, holdings, as_of
):
    df_row = {
        "alert_group": alert_name,
        "Name": name,
        "Fund": link_name,
        "Holdings($M)": holdings,
        "1D": d1,
        "5D": d5,
        "13D": d13,
        "YTD": ytd,
        "YoY": y1,
        "Z-score 1D": z_score_latest,
        "Z-score 5D": z_score_latest_5d,
        "Z-score 13D": z_score_latest_13d,
        "Z-score 1D ETF": z_score_latest_etf,
        "Z-score 5D ETF": z_score_latest_5d_etf,
        "Z-score 13D ETF": z_score_latest_13d_etf,
        "alert_limit_max": 1.5,
        "alert_limit_min": -1.5,
        "as_of": as_of,
    }
    return df_row


def get_etf_inflows():
    start_date = today() - relativedelta(years=5)
    end_date = last_business_day(today() - dtm.timedelta(days=1))
    result_rows = []
    all_flow = []
    all_holdings = []
    for name, ticker in flow_tickers.items():
        if name in ["SilverExChina", "GoldExChina"]:
            continue #
        print(f"Processing Data {name} ...")
        start_date = etf_start_date_overrides.get(name, None) or start_date
        scale_factor_total_holdings = scale_to_millions.get(name, 1)
        fut_gen_ticker = future_tickers.get(name)
        if name not in ["Bitcoin", "Etherum", "CrossCmds"]:
            current_fut_gen_ticker = bref([fut_gen_ticker], ["FUT_CUR_GEN_TICKER"])
            if not pd.isna(current_fut_gen_ticker.loc[fut_gen_ticker][0]):
                future_ticker = current_fut_gen_ticker.loc[fut_gen_ticker][0] + " Comdty"
            else:
                future_ticker = fut_gen_ticker
        elif name in ["Bitcoin", "Etherum"]:
            future_ticker = f"BTCZ{str(end_date.year)[-2:]} Curncy" if name == "Bitcoin" else f"DCRZ{str(end_date.year)[-2:]} Curncy"
        else:
            future_ticker = None
        if ticker:
            future_data = bdh([future_ticker], fields=["PX_LAST"], sdate=start_date, edate=end_date)
            future_data_oi = bdh([future_ticker], fields=["OPEN_INT" if name not in ["Etherum"] else "FUT_AGGTE_OPEN_INT"], sdate=start_date, edate=end_date)
            future_data.columns = [future_ticker]
            future_data_oi.columns = [future_ticker]
            etf_data = bdh([ticker], fields=["PX_LAST"], sdate=start_date, edate=end_date)
            eqf_ticker = eq_fund_tickers.get(name)
            if eqf_ticker is not None:
                eqf_data = bdh([eqf_ticker], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                eqf_data.columns = [eqf_ticker]
            else:
                eqf_data = pd.DataFrame()
            etf_data.columns = [ticker]
            fta_ticker = total_holdings_tickers.get(name)
            total_holdings_data = bdh([fta_ticker], fields=["PX_LAST"], sdate=start_date, edate=end_date)
            total_holdings_data.columns = [fta_ticker]
        else:
            fta_ticker = total_holdings_tickers.get(name)
            total_holdings_data = bdh([fta_ticker], fields=["PX_LAST"], sdate=start_date, edate=end_date)
            total_holdings_data.columns = [fta_ticker]
            etf_data = total_holdings_data.diff().fillna(0)
            future_data = pd.DataFrame()
            future_data_oi = pd.DataFrame()
            eqf_data = pd.DataFrame()
            ticker = fta_ticker
        total_holdings_data[fta_ticker] = total_holdings_data[fta_ticker] * scale_factor_total_holdings
        if name in ["Gold", "GoldExChina", "GoldChina"]:
            multi = bdh(ticker=["XAU Curncy"], fields=["PX_LAST"], sdate=end_date).iloc[-1].values[-1]
            etf_data[ticker] = etf_data[ticker] * scale_factor_total_holdings
        elif name in ["Silver", "SilverChina", "SilverExChina"]:
            multi = bdh(ticker=["XAG Curncy"], fields=["PX_LAST"], sdate=end_date).iloc[-1].values[-1]
            if "SilverChina" == name:
                etf_data[ticker] = etf_data[ticker].diff() * scale_factor_total_holdings
            else:
                etf_data[ticker] = etf_data[ticker] * scale_factor_total_holdings
        else:
            multi = 1
        etf_data[ticker] = etf_data[ticker] * multi
        if name not in ["GoldChina", "SilverChina"]:
            total_holdings_data[fta_ticker] = total_holdings_data[fta_ticker] * multi
        etf_data = etf_data.reindex(total_holdings_data.index)
        if name not in ["CrossCmds"]:
            all_flow.append(etf_data)
            all_holdings.append(total_holdings_data)
        if not etf_data.empty:
            cumsum_changes_flow = get_cumsum_change_stats(etf_data[ticker], [1, 5, 13])
            etf_data_1d = cumsum_changes_flow.get(1)
            etf_data_5d = cumsum_changes_flow.get(5)
            etf_data_13d = cumsum_changes_flow.get(13)
            three_months_data_flows = get_n_months_data(etf_data[ticker], 3, [1, 5, 13])
            three_months_data_1d = three_months_data_flows.get(1)
            three_months_data_5d = three_months_data_flows.get(5)
            three_months_data_13d = three_months_data_flows.get(13)
            z_score_latest = get_z_score(etf_data_1d, three_months_data_1d)
            z_score_latest_5d = get_z_score(etf_data_5d, three_months_data_5d)
            z_score_latest_13d = get_z_score(etf_data_13d, three_months_data_13d)
            _, etf_data_ytd = get_y1_ytd(etf_data, ticker, cumsum=True)
            etf_data_y1, _ = get_y1_ytd(total_holdings_data, fta_ticker)
        else:
            etf_data_1d = np.nan
            etf_data_5d = np.nan
            etf_data_13d = np.nan
            z_score_latest = np.nan
            z_score_latest_5d = np.nan
            z_score_latest_13d = np.nan
            etf_data_ytd = np.nan
            etf_data_y1 = np.nan
        if not eqf_data.empty:
            eqf_pct_change = get_percent_change_stats(eqf_data[eqf_ticker], [1, 5, 13])
            eqf_data_1d = eqf_pct_change.get(1)
            eqf_data_5d = eqf_pct_change.get(5)
            eqf_data_13d = eqf_pct_change.get(13)
            three_months_data_eq = get_n_months_data(eqf_data[eqf_ticker], 3, [1, 5, 13])
            three_months_data_1d_eq = three_months_data_eq.get(1)
            three_months_data_5d_eq = three_months_data_eq.get(5)
            three_months_data_13d_eq = three_months_data_eq.get(13)
            z_score_latest_eqf = get_z_score(eqf_data_1d, three_months_data_1d_eq)
            z_score_5d_eqf = get_z_score(eqf_data_5d, three_months_data_5d_eq)
            z_score_13d_eqf = get_z_score(eqf_data_13d, three_months_data_13d_eq)
            eqf_data_y1, eqf_data_ytd = get_y1_ytd(eqf_data, eqf_ticker, is_pct=True)
        else:
            eqf_data_1d = np.nan
            eqf_data_5d = np.nan
            eqf_data_13d = np.nan
            z_score_latest_eqf = np.nan
            z_score_5d_eqf = np.nan
            z_score_13d_eqf = np.nan
            eqf_data_ytd = np.nan
            eqf_data_y1 = np.nan
        if not future_data.empty:
            future_data_pct_change = get_percent_change_stats(future_data[future_ticker], [1, 5, 13])
            future_data_1d = future_data_pct_change.get(1)
            future_data_5d = future_data_pct_change.get(5)
            future_data_13d = future_data_pct_change.get(13)
            three_months_data_fut = get_n_months_data(future_data[future_ticker], 3, [1, 5, 13])
            three_months_data_1d_fut = three_months_data_fut.get(1)
            three_months_data_5d_fut = three_months_data_fut.get(5)
            three_months_data_13d_fut = three_months_data_fut.get(13)
            z_score_latest_fut = get_z_score(future_data_1d, three_months_data_1d_fut)
            z_score_5d_fut = get_z_score(future_data_5d, three_months_data_5d_fut)
            z_score_13d_fut = get_z_score(future_data_13d, three_months_data_13d_fut)
            future_data_y1, future_data_ytd = get_y1_ytd(future_data, future_ticker, is_pct=True)
        else:
            future_data_1d = np.nan
            future_data_5d = np.nan
            future_data_13d = np.nan
            z_score_latest_fut = np.nan
            z_score_5d_fut = np.nan
            z_score_13d_fut = np.nan
            future_data_ytd = np.nan
            future_data_y1 = np.nan
        if not future_data_oi.empty:
            future_data_oi_stats = get_change_stats(future_data_oi[future_ticker], [1, 5, 13])
            future_data_oi_1d = future_data_oi_stats.get(1)
            future_data_oi_5d = future_data_oi_stats.get(5)
            future_data_oi_13d = future_data_oi_stats.get(13)
            three_months_data_oi_fut = get_n_months_data(future_data_oi[future_ticker], 3, [1, 5, 13])
            three_months_data_1d_oi_fut = three_months_data_oi_fut.get(1)
            three_months_data_5d_oi_fut = three_months_data_oi_fut.get(5)
            three_months_data_13d_oi_fut = three_months_data_oi_fut.get(13)
            z_score_oi_latest_fut = get_z_score(future_data_oi_1d, three_months_data_1d_oi_fut)
            z_score_oi_5d_fut = get_z_score(future_data_oi_5d, three_months_data_5d_oi_fut)
            z_score_oi_13d_fut = get_z_score(future_data_oi_13d, three_months_data_13d_oi_fut)
            future_data_oi_y1, future_data_oi_ytd = get_y1_ytd(future_data_oi, future_ticker)
        else:
            future_data_oi_1d = np.nan
            future_data_oi_5d = np.nan
            future_data_oi_13d = np.nan
            z_score_oi_latest_fut = np.nan
            z_score_oi_5d_fut = np.nan
            z_score_oi_13d_fut = np.nan
            future_data_oi_ytd = np.nan
            future_data_oi_y1 = np.nan
        holdings_chart_path = rf"{etf_html_folder}\charts\{name}_holdings.html"
        indent = ""
        if name not in ["GoldChina", "SilverChina"]:
            df_row = get_table_row_dict(
                name,
                f"{name} Flows",
                f'{indent}<a href="{holdings_chart_path}">{name} Flows</a>',
                etf_data_1d,
                etf_data_5d,
                etf_data_13d,
                etf_data_ytd,
                etf_data_y1,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                total_holdings_data.loc[total_holdings_data.index[-1]][fta_ticker],
                etf_data.index[-1].strftime("%Y-%m-%d"),
            )
            row = pd.Series(df_row)
            result_rows.append(row)
        if name in ["GoldChina", "SilverChina"]:
            indent = "&nbsp;&nbsp;&nbsp;"
            if name == "GoldChina":
                oi_name = "Gold China ETF+SFHE OI"
                alert_group = "Gold"
                shfe_ticker = "AUAA Comdty"
                shfe_data = bdh([shfe_ticker], fields=["FUT_AGGTE_OPEN_INT"], sdate=start_date, edate=end_date)
                shfe_data.columns = [shfe_ticker]
                chnusd_rate = bdh(["CNYUSD Curncy"], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                troy_oz_to_kg = 0.0311034768
                shfe_data[shfe_ticker] = (shfe_data[shfe_ticker] * troy_oz_to_kg * chnusd_rate["PX_LAST"] * _unrecovered('original line 479: remaining conversion multiplier'))
            else:
                oi_name = "Silver China ETF+SFHE OI"
                alert_group = "Silver"
                shfe_ticker = "SAIA Comdty"
                shfe_data = bdh([shfe_ticker], fields=["FUT_AGGTE_OPEN_INT"], sdate=start_date, edate=end_date)
                shfe_data.columns = [shfe_ticker]
                chnusd_rate = bdh(["CNYUSD Curncy"], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                troy_oz_to_kg = 0.0311034768
                shfe_data[shfe_ticker] = (shfe_data[shfe_ticker] * troy_oz_to_kg * chnusd_rate["PX_LAST"] * _unrecovered('original line 488: remaining conversion multiplier'))
            if not shfe_data.empty:
                shfe_data_oi_1d = shfe_data[shfe_ticker].iloc[-1] - shfe_data[shfe_ticker].iloc[-2]
                shfe_data_oi_5d = shfe_data[shfe_ticker].iloc[-1] - shfe_data[shfe_ticker].iloc[-5]
                if len(shfe_data) > 13:
                    shfe_data_oi_13d = shfe_data[shfe_ticker].iloc[-1] - shfe_data[shfe_ticker].iloc[-13]
                else:
                    shfe_data_oi_13d = np.nan
            else:
                shfe_data_oi_1d = np.nan
                shfe_data_oi_5d = np.nan
                shfe_data_oi_13d = np.nan
            if not shfe_data.empty:
                t1y = last_business_day(shfe_data.index[-1] - relativedelta(years=1))
                ytd_index = shfe_data[shfe_ticker].loc[f"{today().year - 1}-12"].index[-1]
                shfe_data_ytd = _unrecovered('original line 503: expression tail', shfe_data[shfe_ticker].iloc[-1] - shfe_data[shfe_ticker].loc[ytd_index])
                try:
                    shfe_data_y1 = _unrecovered('original line 505: division denominator and selection tail', shfe_data.loc[shfe_data.index[-1]] - shfe_data.loc[t1y])
                except KeyError:
                    shfe_data_y1 = _unrecovered('original line 509: month slice and division tail', shfe_data.loc[shfe_data.index[-1]] - shfe_data.loc[f"{t1y.year}-{t1y.month}"].iloc[-1])
            else:
                shfe_data_ytd = np.nan
                shfe_data_y1 = np.nan
            three_months_data_oi_shfe = shfe_data[shfe_data.index[-1] - relativedelta(months=3):shfe_data.index[-1]]
            three_months_data_oi_5d_shfe = shfe_data[shfe_data.index[-5] - relativedelta(months=3):shfe_data.index[-5]]
            three_months_data_oi_13d_shfe = shfe_data[shfe_data.index[-13] - relativedelta(months=3):shfe_data.index[-13]]
            d1_z_score_std_shfe = three_months_data_oi_shfe[shfe_ticker].std(ddof=0)
            z_score_oi_latest_shfe = (three_months_data_oi_shfe[shfe_ticker].iloc[-1] - _unrecovered('original line 518: subtraction and divisor tail'))
            z_score_oi_5d_shfe = (three_months_data_oi_shfe[shfe_ticker].iloc[-5] - _unrecovered('original line 519: subtraction and divisor tail'))
            z_score_oi_13d_shfe = (three_months_data_oi_shfe[shfe_ticker].iloc[-13] - _unrecovered('original line 520: subtraction and divisor tail'))
            holdings_chart_path = rf"{etf_html_folder}\charts\{alert_group}_holdings.html"
            df_row = get_table_row_dict(
                alert_group,
                f"{oi_name}",
                f'{indent}<a href="{holdings_chart_path}">{oi_name}</a>',
                shfe_data_oi_1d,
                shfe_data_oi_5d,
                shfe_data_oi_13d,
                shfe_data_ytd,
                shfe_data_y1,
                z_score_oi_latest_shfe,
                z_score_oi_5d_shfe,
                z_score_oi_13d_shfe,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                total_holdings_data.loc[total_holdings_data.index[-1]][fta_ticker],
                etf_data.index[-1].strftime("%Y-%m-%d"),
            )
            df_row = pd.Series(df_row)
            result_rows.append(df_row)
        if name not in ["GoldChina", "SilverChina", "CrossCmds"]:
            df_row_1 = get_table_row_dict(
                name,
                f"{name} EQ",
                f"{eqf_ticker.upper()} %chg",
                eqf_data_1d,
                eqf_data_5d,
                eqf_data_13d,
                eqf_data_ytd,
                eqf_data_y1,
                z_score_latest_eqf,
                z_score_5d_eqf,
                z_score_13d_eqf,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                np.nan,
                (eqf_data.index[-1].strftime("%Y-%m-%d") if not eqf_data.empty else "-"),
            )
            row1 = pd.Series(df_row_1)
            result_rows.append(row1)
            df_row_2 = get_table_row_dict(
                name,
                f"{name} Fut",
                f"{future_ticker.upper()} %chg",
                future_data_1d,
                future_data_5d,
                future_data_13d,
                future_data_ytd,
                future_data_y1,
                z_score_latest_fut,
                z_score_5d_fut,
                z_score_13d_fut,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                np.nan,
                (future_data.index[-1].strftime("%Y-%m-%d") if not future_data.empty else "-"),
            )
            row2 = pd.Series(df_row_2)
            result_rows.append(row2)
            df_row_3 = get_table_row_dict(
                name,
                f"{name} OI",
                f"{future_ticker.upper()} OI chg",
                future_data_oi_1d,
                future_data_oi_5d,
                future_data_oi_13d,
                future_data_oi_ytd,
                future_data_oi_y1,
                z_score_oi_latest_fut,
                z_score_oi_5d_fut,
                z_score_oi_13d_fut,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                np.nan,
                (future_data.index[-1].strftime("%Y-%m-%d") if not future_data.empty else "-"),
            )
            row3 = pd.Series(df_row_3)
            result_rows.append(row3)
        if name == "Copper":
            t1y = last_business_day(etf_data.index[-1] - relativedelta(years=1))
            total_flow = pd.concat(all_flow, axis=1).sum(axis=1).to_frame("TOTAL_FLOW")
            total_holdings = pd.concat(all_holdings, axis=1).sum(axis=1).to_frame("TOTAL_HOLDINGS")
            total_1d = get_cumsum_change(total_flow["TOTAL_FLOW"], 1)
            total_5d = get_cumsum_change(total_flow["TOTAL_FLOW"], 5)
            total_13d = get_cumsum_change(total_flow["TOTAL_FLOW"], 13)
            ytd_index = total_flow["TOTAL_FLOW"].loc[f"{today().year - 1}-12"].index[-1]
            total_data_ytd = (total_flow["TOTAL_FLOW"].loc[ytd_index:]).cumsum()[-1]
            total_y1 = (total_holdings.loc[total_flow.index[-1]] - total_holdings.loc[t1y])["TOTAL_HOLDINGS"]
            complete_holdings = total_holdings.loc[total_holdings.index[-1]]["TOTAL_HOLDINGS"]
            three_months_data_1d = total_flow[total_flow.index[-1] - relativedelta(months=3):total_flow.index[-1]]
            three_months_data_5d = total_flow[total_flow.index[-5] - relativedelta(months=3):total_flow.index[-5]]
            three_months_data_13d = total_flow[total_flow.index[-13] - relativedelta(months=3):total_flow.index[-13]]
            d1_z_score_std = three_months_data_1d["TOTAL_FLOW"].std(ddof=0)
            z_score_latest = (three_months_data_1d["TOTAL_FLOW"].loc[etf_data.index[-1]]) / d1_z_score_std
            z_score_latest_5d = (total_5d) / three_months_data_5d["TOTAL_FLOW"].std(ddof=0)
            z_score_latest_13d = (total_13d) / three_months_data_13d["TOTAL_FLOW"].std(ddof=0)
            cross_market_link = rf"{etf_html_folder}\charts\all_holdings.html"
            df_row_total = get_table_row_dict(
                "Cross Market",
                "Beta Commods Market Total Flow",
                f'<a href="{cross_market_link}">Beta Commods Market Total</a>',
                total_1d,
                total_5d,
                total_13d,
                total_data_ytd,
                total_y1,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                z_score_latest,
                z_score_latest_5d,
                z_score_latest_13d,
                complete_holdings,
                (future_data.index[-1].strftime("%Y-%m-%d") if not future_data.empty else "-"),
            )
            result_rows.append(pd.Series(df_row_total))
    etf_inflows = pd.DataFrame(result_rows)
    table_order = [
        "Crude Flows",
        "Crude EQ",
        "Crude Fut",
        "Crude OI",
        "NatGas Flows",
        "NatGas EQ",
        "NatGas Fut",
        "NatGas OI",
        "Copper Flows",
        "Copper EQ",
        "Copper Fut",
        "Copper OI",
        "Beta Commods Market Total Flow",
        "Gold Flows",
        "Gold China ETF+SFHE OI",
        "Gold EQ",
        "Gold Fut",
        "Gold OI",
        "Silver Flows",
        "Silver China ETF+SFHE OI",
        "Silver EQ",
        "Silver Fut",
        "Silver OI",
        "Bitcoin Flows",
        "Bitcoin EQ",
        "Bitcoin Fut",
        "Bitcoin OI",
        "Etherum Flows",
        "Etherum EQ",
        "Etherum Fut",
        "Etherum OI",
        "CrossCmds Flows"
    ]
    return etf_inflows.set_index("Name").loc[table_order].reset_index(drop=True)


def get_pos_vs_price_chart(holdings_data, px_data, change_type="D", title=""):
    composite_df = px_data.join(holdings_data, how="inner")
    composite_df.columns = ["PX_LAST", "Net"]
    composite_df = composite_df.loc[composite_df.index >= f"{today().year - 1}-01-01"]
    axis_title = "DoD" if change_type == "D" else "WoW"
    if change_type == "W":
        composite_df = composite_df.resample("W-FRI").last()
    fig = chart.price_vs_pos_chart(
        composite_df,
        y_axis_title=f"{axis_title} Price Change %",
        x_axis_title=f"{axis_title} Holdings Change $M",
        title=f"{axis_title} Position vs Price Change for {title}",
        change_type=change_type,
    )
    return fig


def update_plots():
    all_page = []
    total_flow_data = []
    total_holdings_data = []
    end_date = last_business_day(today() - dtm.timedelta(days=1))
    for name, ticker in total_holdings_tickers.items():
        print(f"Processing Plot {name} ...")
        if name in ["GoldChina", "SilverChina", "GoldExChina", "SilverExChina"]:
            continue
        scaling_factor = scale_to_millions.get(name)
        raw_data = get_plot_data(ticker) * scaling_factor
        raw_data = raw_data.reindex(pd.bdate_range(raw_data.index[0], raw_data.index[-1])).ffill()
        if name not in ["CrossCmds"]:
            flow_ticker = flow_tickers.get(name)
            raw_data_flow = get_plot_data(flow_ticker) * scaling_factor
            raw_data_flow = raw_data_flow.reindex(pd.bdate_range(raw_data_flow.index[0], raw_data_flow.index[-1])).ffill()
            eq_ticker = eq_fund_tickers.get(name)
            if eq_ticker is not None:
                raw_data_eq = get_plot_data(eq_ticker)
            else:
                raw_data_eq = pd.DataFrame(raw_data.index)
            raw_data_eq = raw_data_eq.reindex(pd.bdate_range(raw_data_flow.index[0], raw_data_flow.index[-1])).ffill()
            fut_gen_ticker = future_tickers.get(name)
            if name not in ["Bitcoin", "Etherum"]:
                current_fut_gen_ticker = bref([fut_gen_ticker], ["FUT_CUR_GEN_TICKER"])
                if pd.isna(current_fut_gen_ticker.loc[fut_gen_ticker][0]):
                    current_fut_gen_ticker = bref([fut_gen_ticker], ["FUT_CUR_GEN_TICKER"])
                if name not in ["Gold", "Silver"]:
                    future_ticker = current_fut_gen_ticker.loc[fut_gen_ticker][0] + " Comdty" if not pd.isna(current_fut_gen_ticker.loc[fut_gen_ticker][0]) else fut_gen_ticker
                else:
                    if name == "Gold":
                        future_ticker = "XAU Curncy"
                        fut_gen_ticker = "XAU Curncy"
                    elif name == "Silver":
                        future_ticker = "XAG Curncy"
                        fut_gen_ticker = "XAG Curncy"
                    else:
                        raise ValueError(f"{name} is not supported")
            else:
                future_ticker = f"BTCZ{str(end_date.year)[-2:]} Curncy" if name == "Bitcoin" else f"DCRZ{str(end_date.year)[-2:]} Curncy"
            raw_data_future = get_plot_data(future_ticker)
            raw_data_future = raw_data_future.reindex(pd.bdate_range(raw_data_flow.index[0], raw_data_flow.index[-1])).ffill()
            if name == "Gold":
                multi = bdh(ticker=["XAU Curncy"], fields=["PX_LAST"], sdate=end_date).iloc[-1].values[-1]
            elif name == "Silver":
                multi = bdh(ticker=["XAG Curncy"], fields=["PX_LAST"], sdate=end_date).iloc[-1].values[-1]
            else:
                multi = 1
        else:
            raw_data_flow = raw_data.diff().fillna(0)
            raw_data_eq = pd.DataFrame()
            raw_data_future = pd.DataFrame()
            flow_ticker = ticker
            fut_gen_ticker = None
            eq_ticker = None
            multi = 1
        raw_data[ticker] = raw_data[ticker] * multi
        raw_data_flow[flow_ticker] = raw_data_flow[flow_ticker] * multi
        if name not in ["Bitcoin", "Etherum", "Gold", "Silver", "CrossCmds"]:
            total_flow_data.append(raw_data_flow.copy())
            total_holdings_data.append(raw_data.copy())
        raw_data.columns = [f"{name} Holdings"]
        raw_data_flow.columns = [f"{name} Flow"]
        if not raw_data_eq.empty:
            raw_data_eq.columns = [eq_ticker]
        if not raw_data_future.empty:
            raw_data_future.columns = [f"{future_ticker.upper()}"]
        if not raw_data_eq.empty and not raw_data_future.empty:
            raw_data_future = raw_data_future.reindex(raw_data_eq.index)
        if name in etf_start_date_overrides.keys():
            curr_date_last_year = today().year - 1
            override_start_date = etf_start_date_overrides.get(name)
            if override_start_date.year > curr_date_last_year:
                vs_avg = False
            else:
                vs_avg = True
        else:
            vs_avg = True
        y_axis_title = "$M"
        x_axis_title = "Date"
        if name in ["Bitcoin", "Etherum"]:
            if name == "Bitcoin":
                sp_ticker = "BTC1 Curncy"
            elif name == "Etherum":
                sp_ticker = "DCR1 Curncy"
            else:
                raise ValueError(f"{name} is not supported")
            sp_data = get_plot_data(sp_ticker).diff()
            sp_data = sp_data.reindex(raw_data_flow.index)
            sp_data_mva = talib.mva(sp_data, 5, "s")
            etf_data_mva = talib.mva(raw_data_flow, 5, "s")
            plot_crypto_mva = chart.line_chart(
                df=sp_data_mva,
                data_p1y2=etf_data_mva,
                x_axis_title="Date",
                y_axis_title="5D MVA Delta of 1st Generic Fut Price",
                p1y2_axis_title="5D MVA of ETF Flows",
                secondary_y=True,
                title=f"{name} 5D MVA Delta Price vs ETF Flows",
                height=500,
                width=800,
            )
        else:
            plot_crypto_mva = None
        if len(raw_data_flow.index.year.unique()) == 1 and len(raw_data.index.year.unique()) == 1:
            avail_year_holdings = raw_data.index.year.unique()[-1]
            plot_single = chart.seasonal_chart(
                df=raw_data.rename(columns={raw_data.columns[0]: avail_year_holdings}),
                freq="B",
                title=f"{name} ETFs Total Holdings By Year",
                y_axis_title=y_axis_title,
                x_axis_title=x_axis_title,
                y1_axis_title=y_axis_title,
                df_ytd=False,
                ytd=True,
                vs_avg=False,
                ytd_diff=True,
                convert_to_dby=False,
                height=500,
                width=800,
            )
        else:
            if name in ["Etherum"]:
                plot_data = raw_data.reindex(pd.bdate_range("2024-01-01", today()))
            else:
                plot_data = raw_data
            plot_single = chart.seasonal_chart(
                df=plot_data,
                freq="B",
                title=f"{name} ETFs Total Holdings By Year",
                y_axis_title=y_axis_title,
                x_axis_title=x_axis_title,
                y1_axis_title=y_axis_title,
                df_ytd=False,
                ytd=True,
                vs_avg=False,
                ytd_diff=True,
                height=500,
                width=800,
            )
        if not raw_data_eq.empty:
            if len(raw_data_eq.index.year.unique()) == 1:
                avail_year_eq = raw_data_eq.index.year.unique()[-1]
                plot_single_eq = chart.seasonal_chart(
                    df=raw_data_eq.rename(columns={raw_data_eq.columns[0]: avail_year_eq}),
                    freq="B",
                    title=f"{eq_ticker.upper()} Price By Year",
                    y_axis_title="$",
                    x_axis_title=x_axis_title,
                    vs_avg=False,
                    convert_to_dby=False,
                    tickformat=False,
                    height=500,
                    width=800,
                )
                plot_seasonal_fut = chart.seasonal_chart(
                    df=raw_data_future.rename(columns={raw_data_future.columns[0]: avail_year_eq}),
                    freq="B",
                    title=f"{fut_gen_ticker} Price By Year",
                    y_axis_title="$",
                    x_axis_title=x_axis_title,
                    vs_avg=False,
                    convert_to_dby=False,
                    tickformat=False,
                    height=500,
                    width=800,
                )
            else:
                plot_single_eq = chart.seasonal_chart(
                    df=raw_data_eq,
                    freq="B",
                    title=f"{eq_ticker.upper()} Price By Year",
                    y_axis_title="$",
                    x_axis_title=x_axis_title,
                    vs_avg=vs_avg,
                    tickformat=False,
                    height=500,
                    width=800,
                )
                plot_seasonal_fut = chart.seasonal_chart(
                    df=raw_data_future,
                    freq="B",
                    title=f"{fut_gen_ticker} Price By Year",
                    x_axis_title=x_axis_title,
                    y_axis_title="$",
                    vs_avg=vs_avg,
                    tickformat=False,
                    height=500,
                    width=800,
                )
        else:
            plot_single_eq = "<p style='justify-content: center; align-items: center;'>No Data available</p>"
            plot_seasonal_fut = "<p style='text-align: center; text-align: justify;'>No Data available</p>"
        highlight_dict = {raw_data_flow.columns[0]: {"mode": "bars"}}
        if not (raw_data_eq.empty or raw_data_future.empty):
            plot_combined = chart.line_chart(
                df=raw_data[f"{str(today().year - 1)}-{str(today().month)}":],
                data_p1y2=raw_data_future[f"{str(today().year - 1)}-{str(today().month)}":],
                data_p2y1=raw_data_flow[f"{str(today().year - 1)}-{str(today().month)}":],
                data_p3y1=raw_data_eq[f"{str(today().year - 1)}-{str(today().month)}":],
                y_axis_title=y_axis_title + " Holdings",
                x_axis_title=x_axis_title,
                p2y1_axis_title=y_axis_title + " Flows",
                p1y2_axis_title="Price",
                p3y2_axis_title="Future Price",
                secondary_y=True,
                subplots=3,
                width=800,
                height=500,
                tickformat=False,
                highlight_dict=highlight_dict,
                title=f"{name.capitalize()} YoY ETFs Holdings, Net Flows and Price",
            )
            plot_combined.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.25,
                    xanchor="center",
                    x=0.5
                )
            )
        else:
            plot_combined = chart.line_chart(
                df=raw_data[f"{str(today().year - 1)}-{str(today().month)}":],
                data_p1y2=raw_data_flow[f"{str(today().year - 1)}-{str(today().month)}":],
                y_axis_title=y_axis_title + " Holdings",
                x_axis_title=x_axis_title,
                p1y2_axis_title=y_axis_title + " Flows",
                secondary_y=True,
                width=800,
                height=500,
                tickformat=False,
                highlight_dict=highlight_dict,
                title=f"{name.capitalize() if name not in ['CrossCmds'] else name} YoY ETFs Holdings and Net Flows",
            )
            plot_combined.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.25,
                    xanchor="center",
                    x=0.5
                )
            )
        if plot_crypto_mva:
            crypto_plots = [plot_crypto_mva]
        else:
            crypto_plots = []
        if name in ["Gold", "Silver"]:
            start_date = dtm.datetime(today().year - 8, 1, 1)
            end_date = last_business_day(today() - dtm.timedelta(days=1))
            china_ticker = flow_tickers.get(f"{name}China")
            scaling_factor = scale_to_millions.get(f"{name}China")
            raw_data = get_plot_data(china_ticker).cumsum() * scaling_factor
            troy_oz_to_kg = 0.0311034768
            if name == "Gold":
                shfe_ticker = "AUAA Comdty"
                shfe_data = bdh([shfe_ticker], fields=["FUT_AGGTE_OPEN_INT"], sdate=start_date, edate=end_date)
                shfe_data.columns = [shfe_ticker]
                chnusd_rate = bdh(["CNYUSD Curncy"], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                shfe_data[shfe_ticker] = (shfe_data[shfe_ticker] * troy_oz_to_kg * chnusd_rate["PX_LAST"] * _unrecovered('original line 986: conversion tail'))
            else:
                shfe_ticker = "SAIA Comdty"
                shfe_data = bdh([shfe_ticker], fields=["FUT_AGGTE_OPEN_INT"], sdate=start_date, edate=end_date)
                shfe_data.columns = [shfe_ticker]
                chnusd_rate = bdh(["CNYUSD Curncy"], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                china_ticker = flow_tickers.get(f"{name}China")
                raw_data = get_plot_data(china_ticker).reindex(shfe_data.index) * scaling_factor
                shfe_data[shfe_ticker] = shfe_data[shfe_ticker] * troy_oz_to_kg * chnusd_rate["PX_LAST"] * _unrecovered('original line 994: conversion tail')
            plot_single_china = chart.seasonal_chart(
                df=shfe_data * 1e-6, # convert to M$
                freq="B",
                title=f"{name} China ETF+SHFE OI Positioning By Year",
                y_axis_title="M$/troy oz.",
                x_axis_title=x_axis_title,
                vs_avg=vs_avg,
                tickformat=False,
                height=500,
                width=800,
                dropna_all=True,
            )
            if name == "Gold":
                pboc_data = get_china_gold_cboc_data(data_only=True)
                fig_china_total = chart.line_chart(
                    data_p1y2=pboc_data.diff().to_frame("BBG+UKTI Monthly Delta"),
                    df=pboc_data.to_frame("BBG+UKTI"),
                    secondary_y=True,
                    title="PBoC BBG+UKTI Gold Holdings",
                    y_axis_title="Gold Holdings (M$/troy oz)",
                    p1y2_axis_title="Monthly Change (M$/troy oz)",
                    x_axis_title="Date",
                    tickformat=None,
                    highlight_dict={
                        "BBG+UKTI": {"color": "black", "width": 2},
                        "BBG+UKTI Monthly Delta": {"mode": "bars", "color": "#EF553B"},
                    },
                    height=500,
                    width=800,
                )
                fig_china_total.update_traces(opacity=0.6, selector=dict(type="bar"))
                fig_china_total.update_yaxes(
                    range=pboc_data.diff().quantile([0.01, 0.99]).values, # china repoted a lot of gold at
                    secondary_y=True,
                )
                fig_china_total.update_layout(
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.25,
                        xanchor="center",
                        x=0.5
                    )
                )
                china_flow_ticker = flow_tickers.get(f"{name}China")
                china_gold_flow_data = get_plot_data(china_flow_ticker)
                china_holdings_data = china_gold_flow_data.cumsum()
                china_holdings_data.columns = [f"{name} China Holdings"]
                china_gold_flow_data.columns = [f"{name} China Flows"]
                china_gold_holdings_flow = chart.line_chart(
                    df=china_gold_flow_data[f"{str(today().year - 1)}-{str(today().month)}":],
                    data_p2y1=china_holdings_data[f"{str(today().year - 1)}-{str(today().month)}":],
                    x_axis_title=x_axis_title,
                    p2y1_axis_title=y_axis_title + " Holdings",
                    y_axis_title=y_axis_title + " Flows",
                    width=800,
                    height=500,
                    subplots=2,
                    tickformat=False,
                    highlight_dict={
                        f"{name} China Flows": {"mode": "bars", "color": "red"},
                        f"{name} China Holdings": {"color": "blue"}
                    },
                    title="YOY China ETF Flows and Holdings",
                )
                shangai_gold_price = bdh("SHGF9999 Index", fields=["PX_LAST"], sdate=china_gold_flow_data.index[0], edate=end_date)
                shangai_gold_price_dollars = (shangai_gold_price["PX_LAST"] * _unrecovered('original line 1063: FX reindex and remaining conversion', chnusd_rate.reindex(shangai_gold_price.index)))
                china_holdings_data = china_holdings_data[f"{name} China Holdings"] # in $M
                china_holdings_data = china_holdings_data.to_frame(f"{name} China Holdings")
                china_price_vs_pos_chart = get_pos_vs_price_chart(
                    holdings_data=china_holdings_data,
                    px_data=shangai_gold_price_dollars,
                    title=f"China ETF holdings vs SHGF9999 Index"
                )
                china_price_vs_pos_chart_weekly = get_pos_vs_price_chart(
                    holdings_data=china_holdings_data,
                    px_data=shangai_gold_price_dollars,
                    title=f"China ETF holdings vs SHGF9999 Index",
                    change_type="W",
                )
                daily_holdigs_change = china_holdings_data.diff().fillna(0)
                daily_price_change_scatter = chart.line_chart(
                    df=shangai_gold_price_dollars.iloc[-90:]["PX_LAST"].to_frame("SHGF9999 Index"),
                    data_p2y1=daily_holdigs_change.iloc[-90:],
                    highlight_dict={f"{name} China Holdings": {"mode": "bars"}},
                    y_axis_title="$/troy oz.",
                    p2y1_axis_title="Holdings Change<br>M$/day",
                    title="SHGF9999 Index vs Holdings Change",
                    subplots=2,
                    width=800,
                    height=500,
                )
                fig_china_all = [plot_single_china, china_gold_holdings_flow, china_price_vs_pos_chart, *_unrecovered('original line 1091: chart list tail')]
            else:
                china_silver_flow_ticker = flow_tickers.get(f"{name}China")
                china_silver_flow_data = get_plot_data(china_silver_flow_ticker)
                china_silver_holdings_data = china_silver_flow_data.cumsum()
                china_silver_holdings_data.columns = [f"{name} China Holdings"]
                china_silver_flow_data.columns = [f"{name} China Flows"]
                china_silver_holdings_flow = chart.line_chart(
                    df=china_silver_flow_data[f"{str(today().year - 1)}-{str(today().month)}":],
                    data_p2y1=china_silver_holdings_data[f"{str(today().year - 1)}-{str(today().month)}":],
                    x_axis_title=x_axis_title,
                    p2y1_axis_title=y_axis_title + " Holdings",
                    y_axis_title=y_axis_title + " Flows",
                    width=800,
                    height=500,
                    subplots=2,
                    tickformat=False,
                    highlight_dict={
                        f"{name} China Flows": {"mode": "bars", "color": "red"},
                        f"{name} China Holdings": {"color": "blue"}
                    },
                    title="YOY China ETF Flows and Holdings",
                )
                shangai_silver_price = bdh("SHGFAS99 Index", fields=["PX_LAST"], sdate=china_silver_holdings_data.index[0], edate=end_date)
                shangai_silver_price_dollars = (shangai_silver_price["PX_LAST"] * _unrecovered('original line 1116: FX reindex and remaining conversion', chnusd_rate.reindex(shangai_silver_price.index)))
                china_silver_holdings_data = china_silver_holdings_data[f"{name} China Holdings"] # in $M
                china_silver_holdings_data = china_silver_holdings_data.to_frame(f"{name} China Holdings")
                daily_holdigs_change = china_silver_holdings_data.diff().fillna(0)
                daily_price_change_scatter = chart.line_chart(
                    df=shangai_silver_price_dollars.iloc[-90:]["PX_LAST"].to_frame("SHGFAS99 Index"),
                    data_p2y1=daily_holdigs_change.iloc[-90:],
                    highlight_dict={f"{name} China Holdings": {"mode": "bars"}},
                    y_axis_title="$/troy oz.",
                    p2y1_axis_title="Holdings Change<br>M$/day",
                    title="SHGFAS99 Index vs Holdings Change",
                    subplots=2,
                    width=800,
                    height=500,
                )
                pos_vs_px_chart_silver = get_pos_vs_price_chart(
                    holdings_data=china_silver_holdings_data,
                    px_data=bdh("SHGFAS99 Index", fields=["PX_LAST"], sdate=china_silver_holdings_data.index[0], edate=end_date),
                    title=f"China ETF holdings vs SHGFAS99 Index"
                )
                pos_vs_px_chart_silver_weekly = get_pos_vs_price_chart(
                    holdings_data=china_silver_holdings_data,
                    px_data=bdh("SHGFAS99 Index", fields=["PX_LAST"], sdate=china_silver_holdings_data.index[0], edate=end_date),
                    title=f"China ETF holdings vs SHGFAS99 Index",
                    change_type="W",
                )
                pos_vs_px_chart_silver.update_xaxes(title="DoD Holdings Change $")
                fig_china_all = [plot_single_china, china_silver_holdings_flow, pos_vs_px_chart_silver, *_unrecovered('original line 1144: chart list tail')]
            if name == "Gold":
                ccy_oi_holdings_chart_tickers = ["GCA Comdty", "AUAA Comdty", "GDX US Equity"]
                ccy_oi_holdings_plots = {}
                for tc in ccy_oi_holdings_chart_tickers:
                    plot_data = get_plot_data_oi(tc)
                    if tc == "GCA Comdty":
                        holdings_ticker = total_holdings_tickers.get("GoldExChina")
                        scaling_factor = scale_to_millions.get("GoldExChina")
                        last_price = plot_data["PX_LAST"]
                        raw_holdings = get_plot_data(holdings_ticker)
                        holdings_plot_data = raw_holdings[holdings_ticker] * scaling_factor * last_price #
                        holdings_plot_data = holdings_plot_data.to_frame("HOLDINGS")
                        plot_data = plot_data.join(holdings_plot_data)
                    elif tc == "AUAA Comdty":
                        holdings_ticker = flow_tickers.get("GoldChina")
                        scaling_factor = scale_to_millions.get("GoldChina")
                        last_price = bdh(["SHGF9999 Index"], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                        holdings_plot_data = get_plot_data(holdings_ticker)[holdings_ticker].cumsum() # in
                        holdings_plot_data = holdings_plot_data.to_frame("HOLDINGS")
                        plot_data = plot_data.join(holdings_plot_data)
                    elif tc == "GDX US Equity":
                        holdings_ticker = tc
                        holdings_plot_data = bdh([holdings_ticker], fields=["FUND_TOTAL_ASSETS"], sdate=start_date, edate=end_date)
                        holdings_plot_data.columns = ["HOLDINGS"]
                        plot_data = plot_data.join(holdings_plot_data)
                    else:
                        raise ValueError(f"{tc} not supported")
                    fig = chart.cot_px_ohlc_chart(data=[plot_data], title=tc, column_titles=None, **_unrecovered('original line 1173: no_highli keyword tail'))
                    ccy_oi_holdings_plots[tc] = fig
                west_flow_ticker = flow_tickers.get("GoldExChina")
                west_holdings_ticker = total_holdings_tickers.get("GoldExChina")
                scaling_factor = scale_to_millions.get("GoldExChina")
                west_flow_data = get_plot_data(west_flow_ticker) * scaling_factor * multi # in $M
                west_holdings_data = get_plot_data(west_holdings_ticker) * scaling_factor * multi # holdings
                west_holdings_plot_seasonal = chart.seasonal_chart(
                    df=west_holdings_data,
                    freq="B",
                    title=f"Gold West ETF Holdings",
                    y_axis_title="$M",
                    x_axis_title=x_axis_title,
                    vs_avg=vs_avg,
                    tickformat=False,
                    height=500,
                    width=800,
                )
                west_holdings_data.columns = [f"{name} West Holdings"]
                west_flow_data.columns = [f"{name} West Flows"]
                west_flows_and_holdings_chart = chart.line_chart(
                    df=west_flow_data[f"{str(today().year - 1)}-{str(today().month)}":],
                    data_p2y1=west_holdings_data[f"{str(today().year - 1)}-{str(today().month)}":],
                    x_axis_title=x_axis_title,
                    p2y1_axis_title=y_axis_title + " Holdings",
                    y_axis_title=y_axis_title + " Flows",
                    width=800,
                    height=500,
                    subplots=2,
                    tickformat=False,
                    highlight_dict={f"{name} West Flows": {"mode": "bars", "color": "red"},
                                    f"{name} West Holdings": {"color": "blue"}},
                    title="YOY Gold West ETF Net Flows and Holdings",
                )
                price_vs_pos_chart_west = get_pos_vs_price_chart(
                    holdings_data=west_holdings_data,
                    px_data=bdh("XAU Curncy", fields=["PX_LAST"], sdate=west_holdings_data.index[0], edate=end_date),
                    title="West ETF holdings vs XAU Curncy"
                )
                price_vs_pos_chart_west_weekly = get_pos_vs_price_chart(
                    holdings_data=west_holdings_data,
                    px_data=bdh("XAU Curncy", fields=["PX_LAST"], sdate=west_holdings_data.index[0], edate=end_date),
                    title="West ETF holdings vs XAU Curncy",
                    change_type="W",
                )
                daily_price_change = bdh(["XAU Curncy"], fields=["PX_LAST"], sdate=west_holdings_data.index[0], edate=end_date)
                daily_holdigs_change = west_flow_data
                west_daily_price_change_scatter = chart.line_chart(
                    df=daily_price_change.iloc[-90:]["PX_LAST"].to_frame("XAU Curncy"),
                    data_p2y1=daily_holdigs_change.iloc[-90:],
                    highlight_dict={f"{name} West Flows": {"mode": "bars"}},
                    y_axis_title="$/oz",
                    p2y1_axis_title="Holdings Change<br>M$/day",
                    title="XAU Curncy vs Holdings Change",
                    subplots=2,
                    width=800,
                    height=500,
                )
                west_figs = [west_daily_price_change_scatter, west_holdings_plot_seasonal, west_flows_and_holdings_chart, *_unrecovered('original line 1233: chart list tail')]
            else:
                ccy_oi_holdings_chart_tickers = ["SIA Comdty", "SAIA Comdty", "SIL US Equity"]
                ccy_oi_holdings_plots = {}
                for tc in ccy_oi_holdings_chart_tickers:
                    plot_data = get_plot_data_oi(tc)
                    if tc == "SIA Comdty":
                        holdings_ticker = total_holdings_tickers.get("SilverExChina")
                        scaling_factor = scale_to_millions.get("SilverExChina")
                        last_price = plot_data["PX_LAST"]
                        raw_holdings = get_plot_data(holdings_ticker)
                        holdings_plot_data = raw_holdings[holdings_ticker] * scaling_factor * last_price #
                        holdings_plot_data = holdings_plot_data.to_frame("HOLDINGS")
                        plot_data = plot_data.join(holdings_plot_data)
                    elif tc == "SAIA Comdty":
                        holdings_ticker = total_holdings_tickers.get("SilverChina")
                        scaling_factor = scale_to_millions.get("SilverChina")
                        last_price = bdh(["SHGFAS99 Index"], fields=["PX_LAST"], sdate=start_date, edate=end_date)
                        holdings_plot_data = get_plot_data(holdings_ticker)[holdings_ticker] # in $M
                        holdings_plot_data = holdings_plot_data.to_frame("HOLDINGS")
                        plot_data = plot_data.join(holdings_plot_data)
                    elif tc == "SIL US Equity":
                        holdings_ticker = tc
                        holdings_plot_data = bdh([holdings_ticker], fields=["FUND_TOTAL_ASSETS"], sdate=start_date, edate=end_date)
                        holdings_plot_data.columns = ["HOLDINGS"]
                        plot_data = plot_data.join(holdings_plot_data)
                    else:
                        raise ValueError(f"{tc} not supported")
                    fig = chart.cot_px_ohlc_chart(data=[plot_data], title=tc, column_titles=None, **_unrecovered('original line 1264: no_highli keyword tail'))
                    ccy_oi_holdings_plots[tc] = fig
                    west_flow_ticker = flow_tickers.get("SilverExChina")
                    west_holdings_ticker = total_holdings_tickers.get("SilverExChina")
                    scaling_factor = scale_to_millions.get("SilverExChina")
                    west_flow_data = get_plot_data(west_flow_ticker) * scaling_factor * multi # in $M
                    west_holdings_data = get_plot_data(west_holdings_ticker) * scaling_factor * multi # holdings
                    west_holdings_plot_seasonal = chart.seasonal_chart(
                        df=west_holdings_data,
                        freq="B",
                        title=f"{name} West ETF Holdings",
                        y_axis_title="$M",
                        x_axis_title=x_axis_title,
                        vs_avg=vs_avg,
                        tickformat=False,
                        height=500,
                        width=800,
                    )
                    west_holdings_data.columns = [f"{name} West Holdings"]
                    west_flow_data.columns = [f"{name} West Flows"]
                    west_flows_and_holdings_chart = chart.line_chart(
                        df=west_flow_data[f"{str(today().year - 1)}-{str(today().month)}":],
                        data_p2y1=west_holdings_data[f"{str(today().year - 1)}-{str(today().month)}":],
                        x_axis_title=x_axis_title,
                        p2y1_axis_title=y_axis_title + " Holdings",
                        y_axis_title=y_axis_title + " Flows",
                        width=800,
                        height=500,
                        subplots=2,
                        tickformat=False,
                        highlight_dict={f"{name} West Flows": {"mode": "bars", "color": "red"},
                                        f"{name} West Holdings": {"color": "blue"}},
                        title=f"YOY {name} West ETF Net Flows and Holdings",
                    )
                    daily_price_change = bdh(["XAG Curncy"], fields=["PX_LAST"], sdate=west_holdings_data.index[0], edate=end_date)
                    daily_holdigs_change = west_flow_data
                    west_daily_price_change_scatter = chart.line_chart(
                        df=daily_price_change.iloc[-90:]["PX_LAST"].to_frame("XAG Curncy"),
                        data_p2y1=daily_holdigs_change.iloc[-90:],
                        highlight_dict={f"{name} West Flows": {"mode": "bars"}},
                        y_axis_title="$/oz",
                        p2y1_axis_title="Holdings Change<br>M$/day",
                        title="XAG Curncy vs Holdings Change",
                        subplots=2,
                        width=800,
                        height=500,
                    )
                    price_vs_pos_chart_west = get_pos_vs_price_chart(
                        holdings_data=west_holdings_data,
                        px_data=bdh("XAG Curncy", fields=["PX_LAST"], sdate=west_holdings_data.index[0], edate=end_date),
                        title="West ETF holdings vs XAG Curncy"
                    )
                    price_vs_pos_chart_west_weekly = get_pos_vs_price_chart(
                        holdings_data=west_holdings_data,
                        px_data=bdh("XAG Curncy", fields=["PX_LAST"], sdate=west_holdings_data.index[0], edate=end_date),
                        title="West ETF holdings vs XAG Curncy",
                        change_type="W",
                    )
                    west_figs = [west_daily_price_change_scatter, west_holdings_plot_seasonal, west_flows_and_holdings_chart, *_unrecovered('original line 1322: chart list tail')]
            plots = list(ccy_oi_holdings_plots.values()) + ["", plot_combined, plot_seasonal_fut, plot_single_eq, *_unrecovered('original line 1327: remaining plot grid list')]
            plots_html = table.figs_to_grid(plots, 4)
        else:
            plots = [plot_combined, plot_single, plot_seasonal_fut, plot_single_eq] + crypto_plots
            plots_html = table.figs_to_grid(plots, 4)
        table.figures_to_html(plots_html, rf"{etf_html_folder}\\charts\\{name}_holdings.html")
        all_page.append(plots_html)
    total_flows = pd.concat(total_flow_data, axis=1).sum(axis=1).to_frame("TOTAL_FLOWS")
    total_holdings = pd.concat(total_holdings_data, axis=1).sum(axis=1).to_frame("TOTAL_HOLDINGS")
    total_chart = chart.line_chart(
        df=total_holdings[f"{str(today().year - 1)}-{str(today().month)}":],
        data_p2y1=total_flows[f"{str(today().year - 1)}-{str(today().month)}":],
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title + " Holdings",
        p2y1_axis_title=y_axis_title + " Flows",
        width=800,
        height=500,
        subplots=2,
        tickformat=False,
        highlight_dict={"TOTAL_FLOWS": {"mode": "bars"}},
        title="Total Beta Commods Net Flows and ETF Holdings",
    )
    table.figures_to_html([total_chart], f"{etf_html_folder}\\charts\\all_holdings.html")
    all_page = [total_chart] + all_page
    table.figures_to_html(all_page, f"{etf_html_folder}\\charts\\etf_charts.html")
    return all_page


def update(send_to=None):
    figures = update_plots()
    inflows = get_etf_inflows()
    column_format = {
        "Fund": {"width": "180px", "text-align": "left"},
        "Holdings($M)": {"width": "100px", "text-align": "center", "format": "{:,.0f}"},
        "1D": {"width": "100px", "text-align": "center"},
        "5D": {"width": "100px", "text-align": "center"},
        "13D": {"width": "100px", "text-align": "center"},
        "YTD": {"width": "100px", "text-align": "center"},
        "YoY": {"width": "100px", "text-align": "center"},
        "Z-score 1D": {"width": "100px", "text-align": "center", "highlight": ["Z-score 1D", *_unrecovered('original line 1371: alert_limit_m highlight tail')]},
        "Z-score 5D": {"width": "100px", "text-align": "center", "highlight": ["Z-score 5D", *_unrecovered('original line 1372: alert_limit_m highlight tail')]},
        "Z-score 13D": {"width": "100px", "text-align": "center", "highlight": ["Z-score 13D", *_unrecovered('original line 1373: alert_limit highlight tail')]},
    }
    percent_columns = ["1D", "5D", "13D", "YTD", "YoY"]
    format_row = {
        0: {"bold": {"columns": inflows.columns}},
        1: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        2: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        3: {"bottom_border": True, "format": {"format": "{:,.2f}", "columns": "Holdings($M)"}},
        4: {"bold": {"columns": inflows.columns}},
        5: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        6: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        7: {"bottom_border": True},
        8: {"bold": {"columns": inflows.columns}},
        9: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        10: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        11: {"bottom_border": {"size": "3"}},
        12: {"bottom_border": {"size": "3"}, "bold": {"columns": inflows.columns}},
        13: {"bold": {"columns": inflows.columns}},
        15: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        16: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        17: {"bottom_border": True},
        18: {"bold": {"columns": inflows.columns}},
        20: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        21: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        22: {"bottom_border": {"size": "3"}},
        23: {"bold": {"columns": inflows.columns}},
        24: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        25: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        26: {"bottom_border": True},
        27: {"bold": {"columns": inflows.columns}},
        28: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        29: {"format": {"format": "{:.2%}", "columns": percent_columns}},
        30: {"bottom_border": {"size": "3"}},
        31: {"bold": {"columns": inflows.columns}},
    }
    wiki_link_html = f"</br><p><a href={etf_cix_def_wiki} target='_blank'> CIX Descriptions</a></p></br>"
    html_table = table.html_format(
        inflows,
        header="Commodity ETF inflows",
        footer=f"Last updated {dtm.datetime.now()}",
        hide_cols=[
            "alert_limit_max",
            "alert_limit_min",
            "Z-score 1D ETF",
            "Z-score 5D ETF",
            "Z-score 13D ETF",
            "as_of",
            "alert_group",
        ],
        format_column=column_format,
        format_row=format_row,
        precision=0,
    )
    html_table = html_table + "<br>" + wiki_link_html
    html_table_path = f"{etf_html_folder}\\etf_inflows_summary.html"
    main_page_figs = [html_table] + figures
    table.figures_to_html(main_page_figs, html_table_path, task_name=report_name)
    log.info("Tables Updated")
    if any((inflows[["Z-score 1D ETF", "Z-score 5D ETF"]].apply(abs) >= threshold_z_score).apply(sum, axis=1)):
        log.info("Alerting")
        figs = []
        alerts = inflows[(inflows[["Z-score 1D ETF", "Z-score 5D ETF"]].apply(abs) >= threshold_z_score).apply(sum, axis=1) > 0].alert_group.unique()
        inflows = inflows[inflows.alert_group.isin(alerts)].reset_index(drop=True)
        format_row = {i: {"top_border": True, "bold": {"columns": inflows.columns}} for i, (_, row) in enumerate(inflows.iterrows()) if _unrecovered('original line 1455: row-selection tail')}
        pct_formating = {i: {"format": {"format": "{:.2%}", "columns": percent_columns}} for i, (_, row) in enumerate(inflows.iterrows()) if _unrecovered('original line 1456: row-selection tail')}
        format_row = {**format_row, **pct_formating}
        alert_table = table.html_format(
            inflows,
            header="Commodity ETF inflows",
            hide_cols=[
                "alert_limit_max",
                "alert_limit_min",
                "Z-score 1D ETF",
                "Z-score 5D ETF",
                "Z-score 13D ETF",
                "as_of",
                "alert_group",
            ],
            format_column=column_format,
            format_row=format_row,
            precision=0,
        )
        figs.append(alert_table)
        figs.append(wiki_link_html)
        all_charts_path = rf"{etf_html_folder}\etf_inflows_summary.html"
        figs.append(f'</br><a href="{all_charts_path}"> All Markets </a>')
        email_html = table.to_html(figs=figs, add_home=False)
        if send_to is not None:
            send_email(
                send_to=send_to,
                subject="ETF Fund Flows Alert",
                body=email_html,
                html_path=html_table_path,
            )


if __name__ == "__main__":
    update(send_to=send_to)
    all_etf_alerts = alerts_api.get_alert_history(alert_type="ETF Flows", limit=None)
    all_etf_alerts.set_index(["product", "alert_time"]).to_csv(r"c:\dev\l025\test_alerts_api.csv")
