import pandas as pd
import numpy as np
import datetime as dt
from loguru import logger as log
import os
import sys
from scipy.interpolate import CubicSpline
from dateutil.relativedelta import relativedelta
import ecm.cmds.cdr as cdr
import ecm.cmds.time_series as ts
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.ticker as tk
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.core.mongo_chart import MongoChartStore
from ecm.cmds.utils import convert_path_to_linux
from ecm.cmds.config import html_path, root_path, output_path

lme_dict = {'LPA Comdty': ['LMCADS03 LME Comdty', 'CUA Comdty', 'LMCADY LME Comdty', 'CCSMCUG1 Index'],
            'LAA Comdty': ['LMAHDS03 LME Comdty', 'AAA Comdty', 'LMAHDY LME Comdty', 'CCSMAL00 Index'],
            'LXA Comdty': ['LMZSDS03 LME Comdty', 'ZNAA Comdty', 'LMZSDY LME Comdty', 'CCSMZN01 Index'],
            'LNA Comdty': ['LMNIDS03 LME Comdty', 'XIIA Comdty', 'LMNIDY LME Comdty', 'NICNASDG Index'],
            'LLA Comdty': ['LMPBDS03 LME Comdty', 'PBLA Comdty', 'LMPBDY LME Comdty', 'CCSMLEAD Index'],
            }

report_name = "Copper Arb"
file_name = "copper_arb"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"
metal_csv_folder = f"{output_path}\\csvs\\metal"


def _photo_gap(source_line, visible_prefix):
    """Recovery marker for an expression cut off by the photographs."""
    raise NotImplementedError(f"Photo gap: copper_arb source {source_line}; visible prefix: {visible_prefix}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 6, 00),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(hours=8),
        repetition_duration=dt.timedelta(hours=9),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


def get_contracts(active="LPA Comdty"):
    if active == "HGA Comdty":
        lme_contracts = pyg.get_data("contracts", active="LPA Comdty", item="fut_chain")
        cmx_contracts = pyg.get_data("contracts", active="HGA Comdty", item="fut_chain")
        contract_table = pd.merge(lme_contracts, cmx_contracts, how='left', left_on=['m', 'y'], right_on=['m', 'y'])
    else:
        lme_contracts = pyg.get_data("contracts", active=active, item="fut_chain")
        shfe_contracts = pyg.get_data("contracts", active=lme_dict[active][1], item="fut_chain")
        contract_table = pd.merge(lme_contracts, shfe_contracts, how='left', left_on=['m', 'y'], right_on=['m', 'y'])
    return contract_table


def daily_arb(active="LPA Comdty"):
    pos_by_instrument = pd.DataFrame()
    edate = dt.datetime.now()
    arb_folder = convert_path_to_linux("\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\model\\")
    arb_file = f"{arb_folder}{active}.csv"
    contract_table = get_contracts(active=active)
    trade_contract = contract_table[contract_table['last_t_x'] > cdr.today()].iloc[1]
    if os.path.exists(arb_file):
        try:
            total_arb = ts.read_csv(arb_file, index_name='date')
        except:
            total_arb = ts.read_csv(arb_file, index_name='Unnamed: 0')
        total_arb = total_arb[~total_arb.index.duplicated(keep='first')]
        sdate = total_arb.last_valid_index()
        sloc = total_arb.index.get_loc(sdate)
    else:
        total_arb = pd.DataFrame()
        sdate = cdr.today()
    arb_contracts = contract_table.copy()
    arb_contracts['last_t_x'] = arb_contracts['last_t_x'].shift(1)
    arb_contracts = arb_contracts[
        (arb_contracts['last_t_x'] > sdate) & (arb_contracts['last_t_x'] <= edate + dt.timedelta(35))]
    arb_contracts.reset_index(inplace=True, drop=True)
    lme_hols = cdr.CDR('GB').holidays
    ch_hols = cdr.CDR('CH').holidays
    usdcnh = bbg.bdh('USDCNY Curncy', ['PX_LAST'], sdate=sdate - dt.timedelta(days=28), edate=edate)
    if active in ['LAA Comdty']:
        cash = bbg.bdh(lme_dict[active][3], ['PX_LAST'], sdate=sdate - dt.timedelta(days=28), edate=edate)
        if cash.index[-1] < cdr.today():
            cash = ts.read_csv(_photo_gap(98, r'\\elementcapital.corp\ecns01\PM\Michel Kikano\Data\model\Ali_spot.cs'))
    for idx, row in arb_contracts.iterrows():
        print(row['ticker_x'])
        ticker = row['ticker_x']
        if idx == 0:
            contract_sdate = sdate
        else:
            contract_sdate = arb_contracts.loc[idx - 1, 'last_t_x']
        contract_edate = arb_contracts.loc[idx, 'last_t_x']
        price = bbg.bdh(ticker, ['PX_LAST'], sdate=row['last_t_x'] - dt.timedelta(days=364), edate=row['last_t_x'])
        price_cu = bbg.bdh(
            row['ticker_y'], ['PX_LAST_PM'], sdate=row['last_t_x'] - dt.timedelta(days=364), edate=row['last_t_x'])
        if ticker == trade_contract['ticker_x']:
            if (cdr.today() - dt.timedelta(days=1)).date() in cdr.CDR(tk.get_active(row['ticker_x'])).holidays:
                sdate = cdr.today() - dt.timedelta(days=2)
            else:
                sdate = cdr.today()
            lme_bid = bbg.bdib(ticker, event_type='BID', sdate=sdate, edate=_photo_gap(122, 'cdr.today() + dt.timedelta(days='))
            lme_ask = bbg.bdib(ticker, event_type='ASK', sdate=sdate, edate=_photo_gap(123, 'cdr.today() + dt.timedelta(days='))
            lme_intraday = (lme_bid['close'] + lme_ask['close']) / 2
            lme_intraday.dropna(inplace=True)
            if price.index[-1] == cdr.today():
                price.loc[price.index[-1], 'PX_LAST'] = lme_intraday.loc[lme_intraday.last_valid_index()]
            elif price.index[-1] < cdr.today() and price.index[-1] < row['last_t_x']:
                price = pd.concat([price, pd.DataFrame(lme_intraday.iloc[-1], index=[cdr.today()], columns=['PX_LAST'])], axis=0)
        if len(price_cu) == 0:
            ticker_dict = tk.decompose_ticker(row['ticker_y'])
            ticker_y = (f"{ticker_dict['base_ticker']}{ticker_dict['m']}{str(ticker_dict['y'])[-2:]} "
                        f"{ticker_dict['asset_class']}")
            price_cu = bbg.bdh(ticker_y, ['PX_LAST_PM'], sdate=row['last_t_x'] - dt.timedelta(days=364), edate=row['last_t_x'])
        if active in ['LAA Comdty']:
            price_combine = pd.concat([price, cash.loc[price.index[0]: price.index[-1], :]], axis=1)
            price_combine.columns = ['PX_LAST', 'PX_LAST_PM']
        else:
            price_combine = pd.concat([price, price_cu], axis=1)
            price_combine['PX_LAST_PM'] = price_combine['PX_LAST_PM'].shift(-1)
        if np.isnan(price_combine['PX_LAST_PM'].iloc[-1]) and not np.isnan(price_combine['PX_LAST'].iloc[-1]):
            if (cdr.today() - dt.timedelta(days=1)).date() in cdr.CDR(tk.get_active(row['ticker_y'])).holidays:
                sdate = cdr.today() - dt.timedelta(days=2)
            else:
                sdate = cdr.today()
            shfe_bid = bbg.bdib(row['ticker_y'], event_type='BID', sdate=sdate, edate=_photo_gap(151, 'cdr.today() + dt.timedelta'))
            shfe_ask = bbg.bdib(row['ticker_y'], event_type='ASK', sdate=sdate, edate=_photo_gap(152, 'cdr.today() + dt.timedelta'))
            shfe_intraday = (shfe_bid['close'] + shfe_ask['close']) / 2
            shfe_intraday.dropna(inplace=True)
            combine_intraday = pd.concat([lme_intraday, shfe_intraday], axis=1)
            combine_intraday.dropna(inplace=True)
            price_combine.loc[price_combine.index[-1], :] = combine_intraday.iloc[-1, :].values
        if row['last_t_x'] <= dt.datetime(2019, 4, 1):
            vat = 1.17
        elif row['last_t_x'] > dt.datetime(2019, 4, 1) and row['last_t_x'] < dt.datetime(2024, 12, 1):
            vat = 1.13
        else:
            if active in ['LAA Comdty']:
                vat = 1.065
            else:
                vat = 1.13
        cnh = usdcnh.reindex(price_combine.index, method='ffill')
        arb = (price_combine['PX_LAST_PM'] - (
                price_combine['PX_LAST'] * vat * cnh['PX_LAST'] + 200)) / cnh['PX_LAST']
        arb = arb.to_frame('PX_LAST')
        if arb.index[-1] > cdr.today():
            arb.drop(arb[arb.index > cdr.today()].index, axis=0, inplace=True)
        arb[arb.index.isin(lme_hols)] = np.nan
        arb[arb.index.isin(ch_hols)] = np.nan
        for i in range(len(arb)):
            if i > 1:
                if not np.isnan(arb.iloc[i, 0]) and np.isnan(arb.iloc[i - 1, 0]) and not \
                        np.isnan(arb.iloc[i - 2, 0]):
                    arb.loc[arb.index[i - 1], :] = arb.loc[arb.index[i - 2], :]
        pos_by_instrument = pd.concat([pos_by_instrument, arb[contract_sdate: contract_edate].iloc[:-1]], axis=0)
        if not np.isnan(arb['PX_LAST'].iloc[-1]) and arb.index[-1] >= cdr.today():
            break  # only trade first contract which is the 2nd contract casue shift 1 previously
    if price.index[-1] < cdr.today():
        pass
    else:
        if len(total_arb) == 0:
            total_arb = pd.concat([pos_by_instrument, arb.iloc[-1:, :]], axis=0)
        else:
            total_arb = pd.concat([total_arb.iloc[:sloc, :], pos_by_instrument, arb.iloc[-1:, :]], axis=0)
    print(total_arb.tail())
    if total_arb.empty:
        raise ValueError("Arb DataFrame is empty. Check data sources and calculations.")
    if isinstance(total_arb, pd.Series):
        total_arb = total_arb.to_frame(f"{trade_contract['ticker_y'].split(' ')[0]}-{trade_contract['ticker_x'].split(' ')[0]}")
    else:
        total_arb.columns = [f"{trade_contract['ticker_y'].split(' ')[0]}-{trade_contract['ticker_x'].split(' ')[0]}"]
    return total_arb


def intraday_arb():
    look_back_window = 14
    contract_table = get_contracts(active="LPA Comdty")
    trade_contract = contract_table[contract_table['last_t_x'] > cdr.today()].iloc[1]
    lme_p1 = bbg.bdib("LMCADS03 LME Comdty", sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(217, 'edate='))
    lme_p21 = bbg.bdib("LMCADS H2603 LME Comdty", event_type='BID', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(218, 'look_back_window), ...'))
    lme_p22 = bbg.bdib("LMCADS H2603 LME Comdty", event_type='ASK', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(219, 'look_back_window), ...'))
    lme_p0 = lme_p1['close'] + (lme_p21['close'] + lme_p22['close']) / 2
    log.info(f"Querying LME price for {trade_contract['ticker_x']}")
    try:
        lme_bid = bbg.bdib(trade_contract['ticker_x'], event_type='BID', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(223, 'sdate=cdr.today() - dt.timedelta(da'))
        lme_ask = bbg.bdib(trade_contract['ticker_x'], event_type='ASK', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(224, 'sdate=cdr.today() - dt.timedelta(da'))
    except Exception as e:
        log.error(f"Error querying LME price for {trade_contract['ticker_x']}: {e}")
        lme_bid = lme_p0
        lme_ask = lme_p0
    lme_p = (lme_bid['close'] + lme_ask['close']) / 2
    shfe_p = bbg.bdib(trade_contract['ticker_y'], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(231, 'edate='))
    usdcny = bbg.bdib('USDCNY Curncy', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(233, 'cdr.to'))
    df = pd.concat([lme_p, shfe_p['close'], usdcny['close']], axis=1)
    df.columns = ['LME', 'SHFE', 'USDCNY']
    df.dropna(axis=0, inplace=True)
    arb = (df['SHFE'] - (df['LME'] * 1.13 * df['USDCNY'] + 200)) / df['USDCNY']
    arb = arb.to_frame(f"{trade_contract['ticker_y'].split(' ')[0]}-{trade_contract['ticker_x'].split(' ')[0]}")
    return pd.concat([arb, df], axis=1)


def intraday_arb_comex():
    look_back_window = 14
    contract_table = get_contracts(active="HGA Comdty")
    trade_contract = contract_table.loc[contract_table['last_t_x'] > cdr.today(), :]
    trade_contract = trade_contract.reset_index(drop=True)
    price_dict_lme = {}
    price_dict_cmx = {}
    for idx, row in trade_contract.iterrows():
        if idx < 4:
            lme_bid = bbg.bdib(row['ticker_x'], event_type='BID', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(252, 'look_back_window), ...'))
            lme_ask = bbg.bdib(row['ticker_x'], event_type='ASK', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(253, 'look_back_window), ...'))
            lme_p = (lme_bid['close'] + lme_ask['close']) / 2
        else:
            price_03 = bbg.bdib("LMCADS03 Comdty", sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(256, 'edate or remaining arguments'))
            sprd_ticker = f"LMCADS 03{row['ticker_x'].split(' ')[0][-3:]} Comdty"
            lme_bid = bbg.bdib(sprd_ticker, event_type='BID', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(258, 'look_back_window), ...'))
            lme_ask = bbg.bdib(sprd_ticker, event_type='ASK', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(259, 'look_back_window), ...'))
            lme_p = price_03['close'] - (lme_bid['close'] + lme_ask['close']) / 2
        price_dict_lme[row['ticker_x']] = lme_p.dropna()
        _photo_gap(263, "if row['last_t_y'] > cdr.today() and ((isinstance(row['ticker_y'], str) and row['ticker_y'] != 'nan'")
        if row['last_t_y'] > cdr.today() and ((isinstance(row['ticker_y'], str) and row['ticker_y'] != 'nan')):
            cmx_bid = bbg.bdib(row['ticker_y'], event_type='BID', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(264, 'look_back_window), ...'))
            cmx_ask = bbg.bdib(row['ticker_y'], event_type='ASK', sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(265, 'look_back_window), ...'))
            cmx_p = (cmx_bid['close'] + cmx_ask['close']) / 2
            price_dict_cmx[row['ticker_y']] = cmx_p.dropna()
    lme_price_df = pd.DataFrame.from_dict(price_dict_lme)
    cmx_price_df = pd.DataFrame.from_dict(price_dict_cmx)
    cmx_dates = trade_contract.loc[trade_contract['ticker_y'].isin(cmx_price_df.columns), 'last_t_y']
    lme_dates = trade_contract.loc[trade_contract['ticker_x'].isin(lme_price_df.columns), 'last_t_x']
    lme_match_cmx = pd.DataFrame(np.nan, index=lme_price_df.index, columns=cmx_price_df.columns)
    for idx, row in lme_price_df.iterrows():
        row_ = pd.Series(row.values, index=lme_dates.values).dropna()
        if len(row_) > 1:
            cs = CubicSpline(x=row_.index, y=row_.values, extrapolate=False)
            lme_match_cmx.loc[idx, :] = cs(cmx_dates.values)
    arb = cmx_price_df.reindex(lme_match_cmx.index) * 22.0462 - lme_match_cmx
    return arb, cmx_price_df, lme_price_df


def daily_arb_comex(intraday_arb=None, intraday_lme=None):
    look_back_window = 364
    contract_table = get_contracts(active="HGA Comdty")
    trade_contract = contract_table.loc[contract_table['last_t_x'] > cdr.today(), :]
    trade_contract = trade_contract.reset_index(drop=True)
    price_dict_lme = {}
    price_dict_cmx = {}
    for idx, row in trade_contract.iterrows():
        if idx < 4:
            price_dict_lme[row['ticker_x']] = bbg.bdh(row['ticker_x'], ['PX_LAST'], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(294, 'sdate=cdr.today() - dt.t'))
        else:
            price_03 = bbg.bdh("LMCADS03 Comdty", ['PX_LAST'], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(296, 'look_back_window), ...'))
            sprd_ticker = f"LMCADS 03{row['ticker_x'].split(' ')[0][-3:]} Comdty"
            sprd = bbg.bdh(sprd_ticker, ['PX_LAST'], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(298, 'look_back_window), ...'))
            price_dict_lme[row['ticker_x']] = price_03 - sprd
        _photo_gap(301, "if row['last_t_y'] > cdr.today() and ((isinstance(row['ticker_y'], str) and row['ticker_y'] != 'nan'")
        if row['last_t_y'] > cdr.today() and ((isinstance(row['ticker_y'], str) and row['ticker_y'] != 'nan')):
            price_dict_cmx[row['ticker_y']] = bbg.bdh(row['ticker_y'], ['PX_LAST'], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=_photo_gap(302, 'sdate=cdr.today() - dt.t'))
    lme_price_df = pd.DataFrame.from_dict(price_dict_lme)
    cmx_price_df = pd.DataFrame.from_dict(price_dict_cmx)
    cmx_dates = trade_contract.loc[trade_contract['ticker_y'].isin(cmx_price_df.columns), 'last_t_y']
    lme_dates = trade_contract.loc[trade_contract['ticker_x'].isin(lme_price_df.columns), 'last_t_x']
    lme_match_cmx = pd.DataFrame(np.nan, index=lme_price_df.index, columns=cmx_price_df.columns)
    for idx, row in lme_price_df.iterrows():
        row_ = pd.Series(row.values, index=lme_dates.values).dropna()
        if len(row_) > 1:
            cs = CubicSpline(x=row_.index, y=row_.values, extrapolate=False)
            lme_match_cmx.loc[idx, :] = cs(cmx_dates.values)
    arb = cmx_price_df.reindex(lme_match_cmx.index) * 22.0462 - lme_match_cmx
    if intraday_arb is not None:
        intraday_arb.dropna(inplace=True)
        if intraday_arb.index[-1] > arb.index[-1]:
            arb.loc[arb.index[-1], :] = intraday_arb.loc[intraday_arb.index[-1], :].values
            lme_price_df.loc[lme_price_df.index[-1], :] = intraday_lme.loc[intraday_lme.index[-1], :].values
    return arb, cmx_price_df, lme_price_df


def update():
    arb0 = intraday_arb()
    arb0.to_csv(convert_path_to_linux(_photo_gap(326, 'metal_csv_folder/copper_arb/shfe_lme_arb_{dt.datetime.now().strftime...')))
    arb1 = daily_arb()
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    figs.append("SHFE-LME arb = (SHFE - (LME * 1.13 * CNY + 200)) / CNY")
    arb0_chart = chart.line_chart(
        df=arb0.iloc[:, [0]],
        title="SHFE-LME copper 15min arb",
        tickformat=None,
        width=750,
        height=500,
    )
    arb0_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    arb0_chart.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
            dict(bounds=[7, 13], pattern="hour"),
            dict(bounds=[17, 24], pattern="hour"),
            dict(bounds=[0, 1], pattern="hour"),
            dict(bounds=[3, 5], pattern="hour"),
        ]
    )
    MongoChartStore().save(name="copper.arb.shfe-lme.intraday", data=arb0_chart, collection="chart")
    arb1_chart = chart.line_chart(
        df=arb1.iloc[-364*3:, :],
        title="SHFE-LME copper daily arb",
        tickformat=None,
        width=750,
        height=500,
    )
    arb1_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    arb1_chart.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    MongoChartStore().save(name="copper.arb.shfe-lme.daily", data=arb1_chart, collection="chart")
    figs.append([arb0_chart, arb1_chart])
    arb2, cmx_price_df, lme_price_df = intraday_arb_comex()
    cmx_price_df.to_csv(convert_path_to_linux(_photo_gap(369, 'metal_csv_folder/copper_arb/cmx_price_{dt.datetime.now()...')))
    lme_price_df.to_csv(convert_path_to_linux(_photo_gap(370, 'metal_csv_folder/copper_arb/lme_price_{dt.datetime.now()...')))
    arb3, cmx_daily, lme_daily = daily_arb_comex(intraday_arb=arb2, intraday_lme=lme_price_df)
    figs.append("<br>COMEX-LME arb = COMEX * 22.0462 - LME")
    cmx_daily.index = cmx_daily.index.strftime("%Y-%m-%d")
    lme_daily.index = lme_daily.index.strftime("%Y-%m-%d")
    arb3_ = arb3.copy()
    arb3_.index = arb3_.index.strftime("%Y-%m-%d")
    curve1_data = cmx_daily.iloc[[-5, -2, -1], :].T
    curve1_data.index = [x.split(' ')[0] for x in curve1_data.index]
    curve2_data = lme_daily.iloc[[-5, -2, -1], :].T
    curve2_data.index = [x.split(' ')[0] for x in curve2_data.index]
    curve3_data = arb3_.iloc[[-5, -2, -1], :].T
    curve3_data.index = [x.split(' ')[0][-2:] for x in curve3_data.index]
    curve1_chart = chart.line_chart(
        df=curve1_data,
        title="COMEX copper curve",
        tickformat=None,
        mode='lines+markers',
        width=750,
        height=500,
    )
    curve1_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    curve2_chart = chart.line_chart(
        df=curve2_data,
        title="LME copper curve",
        tickformat=None,
        mode='lines+markers',
        width=750,
        height=500,
    )
    curve2_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    curve3_chart = chart.line_chart(
        df=curve3_data,
        title="COMEX-LME copper arb curve",
        tickformat=None,
        mode='lines+markers',
        width=750,
        height=500,
    )
    curve3_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    figs.append([curve1_chart, curve2_chart, curve3_chart])
    arb2_chart = chart.line_chart(
        df=arb2,
        title="COMEX-LME copper 15min arb",
        tickformat=None,
        width=750,
        height=500,
    )
    arb2_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    arb2_chart.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
            dict(bounds=[18, 24], pattern="hour"),
            dict(bounds=[0, 3], pattern="hour"),
        ]
    )
    MongoChartStore().save(name="copper.arb.comex-lme.intraday", data=arb2_chart, collection="chart")
    arb3_chart = chart.line_chart(
        df=arb3,
        title="COMEX-LME copper daily arb",
        tickformat=None,
        width=750,
        height=500,
    )
    arb3_chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    arb3_chart.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # hide weekends
        ]
    )
    MongoChartStore().save(name="copper.arb.comex-lme.daily", data=arb3_chart, collection="chart")
    figs.append([arb2_chart, arb3_chart])
    table.to_html(figs, f"{html_path}\\cross_cmds\\metal\\copper_arb.html")


if __name__ == "__main__":
    update()
