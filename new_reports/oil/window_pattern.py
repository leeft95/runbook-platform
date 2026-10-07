import ecm.cmds.talib as talib
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
from ecm.cmds.cdr import today
import pandas as pd
from pandas.tseries.offsets import BDay
import datetime as dtm
from enum import Enum
import numpy as np
from loguru import logger as log
from pathlib import Path
from ecm.cmds.config import html_path
from ecm.cmds.utils import convert_path_to_linux
from ecm.cmds._email import send_email
from pytz import timezone
from ecm.cmds.sql import read_sql
from concurrent.futures import ThreadPoolExecutor, as_completed

pd.options.plotting.backend = 'plotly'


class WindowType(Enum):
    SESSION = 'session'
    SETTLEMENT = 'settlement'


class WindowLocation(Enum):
    ASIA = 'asia'
    EU = 'eu'
    US = 'us'


class TimeZone(Enum):
    ASIA = 'Asia/Singapore'
    EU = 'Europe/London'
    US = 'US/Eastern'


full_index_asia = ['CO', 'CO frt Sprd', 'CL', 'CL frt Sprd', 'QS', 'QS frt Sprd', 'HO', 'HO frt Sprd', 'XB', 'XB frt Sprd']
full_index_eu = full_index_asia + ['TZT', 'TZT frt Sprd']
full_index_us = full_index_asia + ['NG', 'NG frt Sprd']
full_index_asia_mtl = ['GC', 'SI', 'HG', 'LMCADS03', 'LMAHDS03', 'LMZSDS03', 'LMNIDS03']
only_spread_tickers_raw = ['DAT 2nd Spread', 'DAT 3rd Spread', 'MUCDAT Comdty']
only_fp_tickers_raw = ['DAT3 Comdty']
only_spread_tickers = []
only_fp_tickers = []
for ticker in only_spread_tickers_raw:
    tk_ = read_sql(f"SELECT ticker FROM mkt_scan.watchlist WHERE generic_ticker = '{ticker}'")
    only_spread_tickers.append(tk_.iloc[0, 0])
for ticker in only_fp_tickers_raw:
    tk_ = read_sql(f"SELECT ticker FROM mkt_scan.watchlist WHERE generic_ticker = '{ticker}'")
    only_fp_tickers.append(tk_.iloc[0, 0])

region_dict = {
    'ASIA_OIL': only_fp_tickers + only_spread_tickers,
    'EU_NRG': ['COA Comdty', 'QSA Comdty', 'TZTA Comdty'],
    'US_NRG': ['CLA Comdty', 'HOA Comdty', 'XBA Comdty', 'NGA Comdty'],
    'ASIA_MTL': ['GCA Comdty', 'SIA Comdty', 'HGA Comdty', 'LMCADS03 Comdty', 'LMAHDS03 Comdty', 'LMZSDS03 Comdty', 'LMNIDS03 Comdty'],
    'CHINA_MACRO': ['SHSZ300 Index', 'SH000909 Index', 'SH000908 Index', 'SHPROP Index', 'USDCNH Curncy'],
    'CHINA_CMDS': ['AUAA Comdty', 'SAIA Comdty', 'CUA Comdty', 'AAA Comdty', 'ZNAA Comdty', 'AUAA Comdty',
                   'SCOA Comdty', 'IOEA Comdty', 'RBTA Comdty', 'CKCA Comdty', 'KEEA Comdty', 'ROCA Comdty']}
email_times = {
    'ASIA_OIL': [TimeZone.ASIA, dtm.time(16, 30)], 'ASIA_MTL': [TimeZone.ASIA, dtm.time(16, 30)],
    'CHINA_MACRO': [TimeZone.ASIA, dtm.time(16, 30)], 'CHINA_CMDS': [TimeZone.ASIA, dtm.time(16, 30)],
    'EU_NRG': [TimeZone.EU, dtm.time(16, 30)], 'US_NRG': [TimeZone.US, dtm.time(14, 30)]}
windows = {'asia': {'start': dtm.time(16, 0), 'end': dtm.time(16, 30)},
           'eu': {'start': dtm.time(16, 0), 'end': dtm.time(16, 30)},
           'us': {'start': dtm.time(14, 0), 'end': dtm.time(14, 30)}}
sessions = {'asia': {'start': dtm.time(8, 0), 'end': dtm.time(15, 0)},
            'eu': {'start': dtm.time(8, 0), 'end': dtm.time(14, 0)},
            'us': {'start': dtm.time(9, 0), 'end': dtm.time(14, 30)}}
data_cache = {}
html_path = convert_path_to_linux(Path(html_path) / 'oil')


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f'Unrecoverable photograph text at source lines {lines}; see TRANSCRIPTION_NOTES.md')


def get_price_intraday(ticker, contract_edate):
    if ticker not in data_cache:
        df = bbg.bdib(ticker, sdate=today() - BDay(30), edate=contract_edate)
        if df is not None and not df.empty:
            df_ = df.copy()
            df_ = df_.sort_index()
            data_cache[ticker] = df
    return data_cache[ticker].copy()


def _fetch_single_ticker(ticker, contract_edate):
    """Helper function to fetch a single ticker's data for parallel execution."""
    try:
        log.debug(f'Fetching data for {ticker}')
        df = bbg.bdib(ticker, sdate=today() - BDay(30), edate=contract_edate)
        if df is not None and not df.empty:
            df_ = df.copy()
            df_ = df_.sort_index()
            return ticker, df_
        return ticker, None
    except Exception as e:
        log.error(f'Error fetching {ticker}: {e}')
        return ticker, None


def prefetch_tickers_parallel(ticker_list, max_workers=5):
    """
    Fetch multiple tickers in parallel using ThreadPoolExecutor.

    Args:
        ticker_list: List of tuples (ticker, contract_edate)
        max_workers: Number of parallel threads (default 5 to avoid overwhelming BBG API)
    """
    log.info(f'Pre-fetching {len(ticker_list)} tickers in parallel with {max_workers} workers')
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(_fetch_single_ticker, ticker, edate): ticker for ticker, edate in ticker_list}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result_ticker, df = future.result()
                if df is not None:
                    data_cache[result_ticker] = df
                    log.debug(f'Cached data for {result_ticker}')
            except Exception as e:
                log.error(f'Exception fetching {ticker}: {e}')
    log.info(f'Pre-fetch complete. Cached {len(data_cache)} tickers')


def get_daily_window_price_change(price_intraday, window_loc: WindowLocation, window_type: WindowType,
                                  is_fp=True, fp_ticker=None):
    df = price_intraday.copy()
    if window_loc == WindowLocation.ASIA:
        tz = TimeZone.ASIA.value
    elif window_loc == WindowLocation.EU:
        tz = TimeZone.EU.value
    elif window_loc == WindowLocation.US:
        tz = TimeZone.US.value
    else:
        raise ValueError('Invalid window location specified.')
    df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert(tz)
    df.index = df.index.tz_localize(None)
    df['date'] = df.index.normalize()
    df = df[df.index.dayofweek < 5]
    if window_type == WindowType.SETTLEMENT:
        window_start = windows[window_loc.value]['start']
        window_end = windows[window_loc.value]['end']
    elif window_type == WindowType.SESSION:
        window_start = sessions[window_loc.value]['start']
        window_end = sessions[window_loc.value]['end']
    else:
        raise ValueError('Invalid window type specified.')
    subset = df.between_time(window_start, window_end, inclusive='both')
    if fp_ticker:
        subset[subset.date == subset.date[-1]].plot(y=['volume'],
                                                   title=f'{fp_ticker}_{window_loc.value}_{window_type.value}', kind='scatter')
    price_start = subset.groupby('date')['close'].first()
    price_end = subset.groupby('date')['close'].last()
    if is_fp:
        price_chg = (price_end - price_start) / price_start
    else:
        price_chg = price_end - price_start
    return price_chg, subset.index[-1]


def get_ewma(price_chg, window=13):
    """
    Calculate the Exponentially Weighted Moving Average (EWMA) of the price change.
    """
    price_chg = price_chg.copy()
    p = np.array(list(reversed(price_chg[-window:].values)))
    ewma = talib.exp_avg(p)
    return ewma


def get_stats(price_chg, ticker, is_fp):
    df = pd.DataFrame(columns=['13D (EWMA)', '5D (EWMA)', 'D-2', 'D-1', 'D'], index=[ticker])
    price_chg_ = price_chg.copy()
    if not price_chg.empty:
        for i in (13, 5):
            ewma = get_ewma(price_chg_, window=i)
            df[f'{i}D (EWMA)'] = ewma
        df['D-2'] = price_chg_[-3]
        df['D-1'] = price_chg_[-2]
        df['D'] = price_chg_[-1]
        hist = price_chg_.iloc[:-1]
        mu = hist.mean()
        sig = hist.std()
        df['_zscore'] = (price_chg_.iloc[-1] - mu) / sig
        df['_thr1'] = 1.5
        df['_thr2'] = -1.5
    return df


def update():
    tables = {}
    for region, tickers in region_dict.items():
        log.info(f'Processing region: {region}')
        all_data = pd.DataFrame()
        if 'asia' in region.lower():
            window_loc = WindowLocation.ASIA
        elif 'eu' in region.lower():
            window_loc = WindowLocation.EU
        elif 'us' in region.lower():
            window_loc = WindowLocation.US
        elif 'china' in region.lower():
            window_loc = WindowLocation.ASIA
        else:
            raise ValueError(f'Region {region} not recognized.')
        log.info(f'Collecting ticker information for {region}...')
        tickers_to_fetch = []
        ticker_info = {}  # Store contract info to avoid redundant lookups
        for active in tickers:
            suffix = active.lower().split()[-1]
            is_index_or_ccy = suffix in {'index', 'curncy'}
            is_spread_or_fp_only = active in (only_spread_tickers + only_fp_tickers)
            is_whitelisted_cmdty = active in ['GCA Comdty', 'SIA Comdty', 'HGA Comdty', 'CUA Comdty', 'AAA Comdty',
                                              'ZNAA Comdty', 'AUAA Comdty', 'SCOA Comdty', 'IOEA Comdty', 'RBTA Comdty',
                                              'SAIA Comdty', 'CKCA Comdty', 'KEE1 Comdty', 'ROCA Comdty']
            if ('mtl' not in region.lower() and not is_spread_or_fp_only and (not is_index_or_ccy)) or is_whitelisted_cmdty:
                ticker_contract = bbg.live_contract(active, db='contracts', seq=0, roll='t1')
                if 'china' not in region.lower():
                    sprd_ticker = bbg.live_spread_ticker(active, roll='t1', spread='12', short_ticker=True)
                else:
                    sprd_ticker = active
                fp_ticker = ticker_contract.ticker
                contract_edate = ticker_contract.last_tradeable_dt
                ticker_info[active] = {'fp_ticker': fp_ticker, 'sprd_ticker': sprd_ticker,
                                       'contract_sdate': ticker_contract.fut_first_trade_dt, 'contract_edate': contract_edate}
                if active not in only_spread_tickers and fp_ticker not in data_cache:
                    tickers_to_fetch.append((fp_ticker, contract_edate))
                if sprd_ticker not in only_fp_tickers and sprd_ticker not in data_cache:
                    tickers_to_fetch.append((sprd_ticker, contract_edate))
            else:
                fp_ticker = active
                sprd_ticker = active
                contract_edate = dtm.datetime(today().year, 12, 31)
                ticker_info[active] = {'fp_ticker': fp_ticker, 'sprd_ticker': sprd_ticker,
                                       'contract_sdate': dtm.datetime(today().year, 1, 1), 'contract_edate': contract_edate}
                if fp_ticker not in data_cache:
                    tickers_to_fetch.append((fp_ticker, contract_edate))
        if tickers_to_fetch:
            log.info(f'Pre-fetching {len(tickers_to_fetch)} tickers for {region}...')
            prefetch_tickers_parallel(tickers_to_fetch, max_workers=5)
        else:
            log.info(f'All tickers already cached for {region}')
        for active in tickers:
            info = ticker_info[active]
            fp_ticker = info['fp_ticker']
            sprd_ticker = info['sprd_ticker']
            contract_sdate = info['contract_sdate']
            contract_edate = info['contract_edate']
            log.info(f'Processing {active}: FP={fp_ticker}, Spread={sprd_ticker}')
            if not active in only_spread_tickers:
                intraday_fp = get_price_intraday(fp_ticker, contract_edate)
                session_price_change, last_bar_time_session = get_daily_window_price_change(
                    intraday_fp, window_loc=window_loc, window_type=WindowType.SESSION, is_fp=True, fp_ticker=fp_ticker)
                session_frame = get_stats(session_price_change, fp_ticker, is_fp=True)
                if 'mtl' not in region.lower() and 'china' not in region.lower():
                    window_price_change, last_bar_time_window = get_daily_window_price_change(
                        intraday_fp, window_loc=window_loc, window_type=WindowType.SETTLEMENT, is_fp=True, fp_ticker=fp_ticker)
                    if window_price_change.empty:
                        log.warning(f'No data for {fp_ticker} in {region}. Skipping.')
                    window_frame = get_stats(window_price_change, fp_ticker, is_fp=True)
                    midx = pd.MultiIndex.from_arrays([
                        ['Session'] * len(session_frame.columns) + ['Window'] * (len(session_frame.columns) + 2),
                        session_frame.columns.to_list() + session_frame.columns.to_list() + ['_last_update_session', '_last_update_window']],
                        names=[region, ''])  # name the top-level 'Asia', leave second blank
                    window_frame['_last_update_session'] = last_bar_time_session
                    window_frame['_last_update_window'] = last_bar_time_window
                    full_data = pd.concat([session_frame, window_frame], axis=1)
                else:
                    midx = pd.MultiIndex.from_arrays([
                        ['Session'] * (len(session_frame.columns) + 1), session_frame.columns.to_list() + ['_last_update_session']],
                        names=[region, ''])  # name the top-level 'Asia', leave second blank
                    session_frame['_last_update_session'] = last_bar_time_session
                    full_data = session_frame
                full_data.columns = midx
            else:
                full_data = pd.DataFrame()
            allow_spread_stats = ('mtl' not in region.lower() and 'china' not in region.lower() and sprd_ticker not in only_fp_tickers)
            if allow_spread_stats:
                intraday_sprd = get_price_intraday(sprd_ticker, contract_edate)
                session_price_change_sprd, last_bar_time_session = get_daily_window_price_change(
                    intraday_sprd, window_loc=window_loc, window_type=WindowType.SESSION, is_fp=False, fp_ticker=fp_ticker)
                session_frame_sprd = get_stats(session_price_change_sprd, sprd_ticker, is_fp=False)
                window_price_change_sprd, last_bar_time_window = get_daily_window_price_change(
                    intraday_sprd, window_loc=window_loc, window_type=WindowType.SETTLEMENT, is_fp=False, fp_ticker=fp_ticker)
                window_frame_sprd = get_stats(window_price_change_sprd, sprd_ticker, is_fp=False)
                window_frame_sprd['_last_update_session'] = last_bar_time_session
                window_frame_sprd['_last_update_window'] = last_bar_time_window
                full_data_sprd = pd.concat([session_frame_sprd, window_frame_sprd], axis=1)
                midx = pd.MultiIndex.from_arrays([
                    ['Session'] * len(session_frame.columns) + ['Window'] * (len(session_frame.columns) + 2),
                    session_frame.columns.to_list() + session_frame.columns.to_list() + ['_last_update_session', '_last_update_window']],
                    names=[region, ''])  # name the top-level 'Asia', leave second blank
                full_data_sprd.columns = midx
                _data = pd.concat([full_data, full_data_sprd], axis=0)
            else:
                _data = full_data
            all_data = pd.concat([all_data, _data], axis=0)
        tables[region] = all_data
        log.info(f'Data for region {region} processed successfully.')
        log.info('--------------------')
    return tables


def _get_region_email_html(region, data):
    data_ = data.copy()
    numerical_cols = {
        col: dict(width='100px', align='center', right_border=(x == 4),
                  **({'highlight': [col, (col[0], '_zscore'), (col[0], '_thr1'), (col[0], '_thr2')]}
                     if col[1] == 'D' and (col[0], '_zscore') in data_.columns else {}))
        for x, col in enumerate(data_.columns[1:-2], start=1)}
    col_fromat = {data_.columns[0]: {'width': '120px', 'align': 'left'}, **numerical_cols}
    data_.columns.name = ''
    data_.index.name = region.replace('_', ' - ')
    data_.reset_index(inplace=True)
    if 'mtl' in region.lower():
        base_row_format = {'format': '{:.2%}', 'columns': data_.columns[1:-2]}
        rows = {}
        for i, _ in enumerate(data_.index):
            row_fmt = base_row_format.copy()  # make a per-row copy
            if i in {2}:
                row_fmt['top_border'] = {'size': 3, 'color': 'black'}
            rows[i] = row_fmt
    elif 'china' in region.lower():
        region_lc = region.lower()
        is_cmds = 'cmds' in region_lc
        is_macro = 'macro' in region_lc
        base_row_format = {'format': '{:.2%}', 'columns': data_.columns[1:-2]}
        rows = {}
        for i, _ in enumerate(data_.index):
            row_fmt = base_row_format.copy()  # make a per-row copy
            if is_cmds and i in {2, 6, 9}:
                row_fmt['top_border'] = {'size': 3, 'color': 'black'}
            elif is_macro and i == 4:
                row_fmt['top_border'] = {'size': 3, 'color': 'black'}
            rows[i] = row_fmt
    else:
        rows = {i: {'format': '{:.2f}' if i % 2 != 0 or data_.loc[_idx].iloc[0] in only_spread_tickers else '{:.2%}',
                    'columns': data_.columns[1:-2]} for i, _idx in enumerate(data_.index)}
    formatted_table_ = table.html_format(
        data_, format_column=col_fromat.copy(), format_row=rows.copy(),
        hide_cols=[x for x in data_.columns.to_list() if x[1] in
                   ['_zscore', '_thr1', '_thr2', '_last_update_session', '_last_update_window']],
        multiindex=True, precision=2)
    if not 'mtl' in region.lower() and not 'china' in region.lower():
        latest_session_time = data_[data_.columns[-2]].max()
        latest_window_time = data_[data_.columns[-1]].max()
    else:
        latest_session_time = data_[data_.columns[-1]].max()
        latest_window_time = None
    end_note = f"""<div style='font-size: 12px; text-align:left;
                    font-family:Calibri'>Latest data Session: {latest_session_time}<br>
                    Latest data Window: {latest_window_time if latest_window_time else 'N/A'}<br>
                    </div><br>"""
    formatted_table_ = formatted_table_ + end_note
    return formatted_table_


def _check_send_email(region):
    for region_, (tz, send_time) in email_times.items():
        if region_ == region:
            current_time_dt = dtm.datetime.now(timezone(tz.value))
            current_time = current_time_dt.time()
            window_end = (dtm.datetime.combine(dtm.date.today(), send_time) + dtm.timedelta(minutes=30)).time()
            if current_time >= send_time and current_time <= window_end:
                log.info(_missing_photo_text('576', f"Email check for {region}: Current time {current_time_dt.strftime('%H:%M:%S %Z')}"))
                return True
            else:
                log.info(_missing_photo_text('580', f"Email check for {region}: Current time {current_time_dt.strftime('%H:%M:%S %Z')}"))
                return False


def format_tables(tables, all_regions=False):
    formatted_tables = {}
    output_path = html_path / 'window_pattern.html'
    if not all_regions:
        all_tables = []
        email_subject = None
        for region in tables.keys():
            if _check_send_email(region):
                table_html = _get_region_email_html(region, tables[region])
                all_tables.append(table_html)
                log.info(f'Email table for region generated: {region}')
                if _missing_photo_text('596'):
                    region_subject = _missing_photo_text('597')
                else:
                    region_subject = region
                email_subject = f'Window Pattern Report - {region_subject}'
            else:
                log.info(f'Skipping email for region: {region}')
                continue
        if email_subject:
            email_body = (f"<br/>Window Pattern Report {dtm.datetime.now().strftime('%Y-%m-%d')}<br/>") + ''.join(all_tables)
            send_email(send_to=['commods'], body=email_body, subject=email_subject, html_path=output_path)
    else:
        for region, data in tables.items():
            data_ = data.copy()
            numerical_cols = {
                col: dict(width='100px', align='center', right_border=(x == 4),
                          **({'highlight': [col, (col[0], '_zscore'), (col[0], '_thr1'), (col[0], '_thr2')]}
                             if col[1] == 'D' and (col[0], '_zscore') in data_.columns else {}))
                for x, col in enumerate(data_.columns[1:-2], start=1)}
            col_fromat = {data_.columns[0]: {'width': '120px', 'align': 'left'}, **numerical_cols}
            data_.columns.name = ''
            data_.index.name = region.replace('_', ' - ')
            data_.reset_index(inplace=True)
            if 'mtl' in region.lower():
                base_row_format = {'format': '{:.2%}', 'columns': data_.columns[1:-2]}
                rows = {}
                for i, _ in enumerate(data_.index):
                    row_fmt = base_row_format.copy()  # make a per-row copy
                    if i in {2}:
                        row_fmt['top_border'] = {'size': 3, 'color': 'black'}
                    rows[i] = row_fmt
            elif 'china' in region.lower():
                region_lc = region.lower()
                is_cmds = 'cmds' in region_lc
                is_macro = 'macro' in region_lc
                base_row_format = {'format': '{:.2%}', 'columns': data_.columns[1:-2]}
                rows = {}
                for i, _ in enumerate(data_.index):
                    row_fmt = base_row_format.copy()  # make a per-row copy
                    if is_cmds and i in {2, 6, 9}:
                        row_fmt['top_border'] = {'size': 3, 'color': 'black'}
                    elif is_macro and i == 4:
                        row_fmt['top_border'] = {'size': 3, 'color': 'black'}
                    rows[i] = row_fmt
            else:
                rows = {i: {'format': '{:.2f}' if i % 2 != 0 or data_.loc[_idx].iloc[0] in only_spread_tickers else '{:.2%}',
                            'columns': data_.columns[1:-2]} for i, _idx in enumerate(data_.index)}
            formatted_table_ = table.html_format(
                data_, format_column=col_fromat.copy(), format_row=rows.copy(),
                hide_cols=[x for x in data_.columns.to_list() if x[1] in
                           ['_zscore', '_thr1', '_thr2', '_last_update_session', '_last_update_window']],
                multiindex=True, precision=2)
            if not 'mtl' in region.lower() and not 'china' in region.lower():
                latest_session_time = data_[data_.columns[-2]].max()
                latest_window_time = data_[data_.columns[-1]].max()
            else:
                latest_session_time = data_[data_.columns[-1]].max()
                latest_window_time = None
            end_note = f"""<div style='font-size: 12px; text-align:left;
                            font-family:Calibri'>Latest data Session: {latest_session_time}<br>
                            Latest data Window: {latest_window_time if latest_window_time else 'N/A'}<br>
                            </div><br>"""
            formatted_table_ = formatted_table_ + end_note
            formatted_tables[region] = formatted_table_
        fmtd_w = [f'{v.get("start").strftime("%H:%M")}-{v.get("end").strftime("%H:%M")}' for v in windows.values()]
        fmtd_s = [f'{v.get("start").strftime("%H:%M")}-{v.get("end").strftime("%H:%M")}' for v in sessions.values()]
        x = pd.DataFrame({'Session Window': fmtd_s, 'Platts Window': fmtd_w}, index=list(sessions.keys()))
        x.index.name = 'Region'
        x.index = x.index.str.upper()
        x.reset_index(inplace=True)
        session_des_html = table.html_format(
            x, header='Window Defintions (Local Time)',
            format_column={'Region': {'width': '150px', 'align': 'left'},
                           'Session Window': {'width': '150px', 'align': 'center'},
                           'Platts Window': {'width': '150px', 'align': 'center'}}, multiindex=False, hide_cols=[])
        description = table.html_text(
            body=('Sessions are all in Local Time converted from the ET equivalent.<br>'
                  'eg 20:00-03:00 (ET) is 08:00-15:00 (SGT) for Asia session.<br>'),
            style='font-size: 14px; text-align:left; font-family:Calibri;')
        table.to_html([description + session_des_html + '<br>'] + list(formatted_tables.values()), output_path,
                      title='Window Pattern Report', task_name='Window Pattern Report')
        log.info(f'Full dashboard page saved to {output_path}')


if __name__ == '__main__':
    tables = update()
    format_tables(tables)
    format_tables(tables, all_regions=True)
