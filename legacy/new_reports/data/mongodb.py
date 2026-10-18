import datetime as dt
import ecm.cmds.pyg as pyg
import ecm.cmds.cdr as cdr
import ecm.cmds.bbg as bbg
from functools import partial
from pyg_mongo import *
from pyg_cell import *
from ecm.atom.services.tools import rvx_query_frame
from fastparquet import write, ParquetFile
import pandas as pd
import os
import sys
from pyg_base import mkdir
from ecm.cmds.config import root_path, data_path
from ecm.atom.wintask.scheduler import ECMWinTask
from ecm.atom.wintask.utils import Days


def _unrecovered(location):
    """Recovery marker: missing text is not a usable empty collection/default."""
    raise NotImplementedError(f"Unrecovered source: {location}")


fut_list = ['CLA Comdty', 'COA Comdty', 'XBA Comdty',
            'HOA Comdty', 'QSA Comdty', 'NGA Comdty',
            'MOA Comdty', 'TZTA Comdty', 'DATA Comdty',
            'CUA Comdty', 'AAA Comdty', 'ZNAA Comdty', 'XIIA Comdty', 'PBLA Comdty', 'XOOA Comdty',
            'LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'LLA Comdty', 'LTA Comdty',
            'GCA Comdty', 'SIA Comdty', 'PLA Comdty', 'PAA Comdty',
            'C A Comdty', 'S A Comdty', 'SMA Comdty', 'BOA Comdty',
            'W A Comdty', 'SBA Comdty', 'CCA Comdty', 'KCA Comdty',
            'LCA Comdty', 'FCA Comdty', 'LHA Comdty',
            'KWA Comdty', 'HGA Comdty', 'CTA Comdty',
            'ESA Index', 'NQA Index', 'RTYA Index', 'UXA Index',
            'TUA Comdty', 'TYA Comdty', 'ECA Curncy', 'ADA Curncy',
            'JYA Curncy', 'CDA Curncy', 'DXA Curncy', 'BTCA Curncy', 'DCRA Curncy', 'AGDA Comdty',
            ]

fut_list_px_last = [
    'MUCA Comdty', 'ZHEA Comdty', 'PTYA Comdty', 'PUBA Comdty', 'ATOA Comdty', 'WMEHM Index', 'PMRSM Index',
    *_unrecovered('IMG_5016 line 35: additional ticker entries offscreen'),
    'PGA Comdty', 'NVA Comdty', 'AFYA Comdty', 'BGLA Comdty', 'AWOA Comdty', 'AZBA Comdty', 'PTLA Comdty',
    *_unrecovered('IMG_5016 line 36: additional ticker entries offscreen'),
]

sprd_list = [
    'CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty', 'NGA Comdty', 'DATA Comdty', 'TZTA Comdty',
    *_unrecovered('IMG_5016 line 40: ticker-list tail offscreen after TZTA'),
    'C A Comdty', 'S A Comdty', 'W A Comdty', 'KWA Comdty', 'SBA Comdty', 'BOA Comdty', 'SMA Comdty',
    'CCA Comdty', 'KCA Comdty', 'HGA Comdty', 'LCA Comdty', 'FCA Comdty', 'LHA Comdty', 'CTA Comdty',
]

xsprd_list = ['S:ENCO Comdty', 'S:QSCO Comdty', 'S:XBCL Comdty', 'S:HOCL Comdty',
              'S:XBHO Comdty', 'S:CODAT Comdty', 'S:MUCDAT Comdty', 'S:PGCO Comdty',
              'S:NVQS Comdty', 'S:NVCO Comdty', ]

spot_list = ['LMAHDS03 LME Comdty', 'LMCADS03 LME Comdty', 'LMNIDS03 LME Comdty',
             'LMZSDS03 LME Comdty', 'LMPBDS03 LME Comdty', 'LMSNDS03 LME Comdty',
             'XAU BGN Curncy', 'XAG BGN Curncy', 'XPT BGN Curncy', 'XPD BGN Curncy',
             'AUDUSD BGN Curncy', 'EURUSD BGN Curncy', 'GBPUSD BGN Curncy', 'NZDUSD BGN Curncy',
             'USDCAD BGN Curncy', 'USDCHF BGN Curncy', 'USDJPY BGN Curncy']

gen_list = [
    'CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty',
    'QSA Comdty', 'NGA Comdty', 'MOA Comdty', 'TZTA Comdty',
    'GCA Comdty', 'SIA Comdty', 'PLA Comdty', 'PAA Comdty',
    'LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'LLA Comdty', 'LTA Comdty',
    'C A Comdty', 'S A Comdty', 'SMA Comdty', 'BOA Comdty',
    'W A Comdty', 'SBA Comdty', 'CCA Comdty', 'KCA Comdty',
    'LCA Comdty', 'FCA Comdty', 'LHA Comdty',
    'KWA Comdty', 'HGA Comdty', 'CTA Comdty',
]

volume_list = [
    'CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty',
    'QSA Comdty', 'NGA Comdty', 'MOA Comdty', 'TZTA Comdty',
    'GCA Comdty', 'SIA Comdty', 'PLA Comdty', 'PAA Comdty',
    'LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'LLA Comdty', 'LTA Comdty',
    'C A Comdty', 'S A Comdty', 'SMA Comdty', 'BOA Comdty',
    'W A Comdty', 'SBA Comdty', 'CCA Comdty', 'KCA Comdty',
    'LCA Comdty', 'FCA Comdty', 'LHA Comdty',
    'KWA Comdty', 'HGA Comdty', 'CTA Comdty',
    'ESA Index', 'NQA Index', 'RTYA Index', 'UXA Index',
    'TUA Comdty', 'TYA Comdty', 'ECA Curncy', 'ADA Curncy',
    'JYA Curncy', 'CDA Curncy', 'DXA Curncy', 'BTCA Curncy', 'DCRA Curncy',
]

sprd_roll_list = ['CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty', 'NGA Comdty',
                  *_unrecovered('IMG_5017 line 80: list tail begins DATA and extends offscreen'),
                  'C A Comdty', 'S A Comdty', 'W A Comdty', 'KWA Comdty', 'SBA Comdty',
                  'S:ENCO Comdty', 'S:QSCO Comdty', 'S:XBCL Comdty', 'S:HOCL Comdty', 'S:XBHO Comdty',
                  *_unrecovered('IMG_5017 line 82: cross-spread list tail begins S:CO and extends offscreen')]

gas_list = [
    "TTFUM Index"  # TTF monthly forward
]

report_name = "Update Mongodb"
file_name = "mongodb"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\data\\{file_name}.py"


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 6, 40),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f"{report_name}", filepath=f"{file_path}"),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update_outright(ticker_list):
    for i in ticker_list:
        print(i)
        c = pyg.get_cell('contracts', active=i, item='fut_chain').go()


def update_spread():
    for i in sprd_list:
        print(i)
        c = pyg.get_cell('spreads', active=i, item='sprd_chain').go()


def update_xspread():
    for i in xsprd_list:
        print(i)
        c = pyg.get_cell('spreads', active=i, item='xsprd_chain').go()


def update_spot():
    db = partial(mongo_table, db='bbg', table='spot', url='mongodb://nypmdevlo25v:27017/', pk=_unrecovered('IMG_5018 line 134: pk list and possible trailing arguments'))
    fields = ['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST']
    for ticker in spot_list:
        for att in fields:
            print(ticker, att)
            c = pyg.get_cell('spot', ticker=ticker, field=att)
            c.period = '1b'
            c.go(0)


def update_rolls():
    fields = ['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST']
    for ticker in gen_list:
        c1 = pyg.get_cell('contracts', active=ticker, item='gen_contract')
        c1.go(0)
        c2 = pyg.get_cell('contracts', active=ticker, item="roll_spread")
        c2.go(0)
        if ticker in ['LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'LLA Comdty', 'LTA Comdty',
                      'ESA Index', 'NQA Index', 'RTYA Index', 'UXA Index',
                      'TUA Comdty', 'TYA Comdty', 'ECA Curncy', 'ADA Curncy',
                      'JYA Curncy', 'CDA Curncy', 'DXA Curncy', 'BTCA Curncy', 'DCRA Curncy'
                      ]:
            print(ticker, "PX_LAST")
            c3 = pyg.get_cell('contracts', active=ticker, item="PX_LAST_gen")
            c3.go(0)
            c4 = pyg.get_cell('contracts', active=ticker, item="PX_LAST_roll")
            c4.go(0)
        else:
            for att in fields:
                print(ticker, att)
                c3 = pyg.get_cell('contracts', active=ticker, item=f"{att}_gen")
                c3.go(0)
                c4 = pyg.get_cell('contracts', active=ticker, item=f"{att}_roll")
                c4.go(0)


def update_spread_rolls():
    for ticker in sprd_roll_list:
        c1 = pyg.get_cell('spreads', active=ticker, item='gen_spread')
        c1.go(0)
        c2 = pyg.get_cell('spreads', active=ticker, item="roll_spread")
        c2.go(0)
        if ticker in ["DATA Comdty", 'S:ENCO Comdty', 'S:QSCO Comdty', 'S:XBCL Comdty', 'S:HOCL Comdty',
                      *_unrecovered('IMG_5018/5019 line 176: membership-list tail begins S:')]:
            fields = ["PX_LAST"]
        else:
            fields = ['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST']
        for att in fields:
            print(ticker, att)
            c3 = pyg.get_cell('spreads', active=ticker, item=f"{att}_gen")
            c3.go(0)
            c4 = pyg.get_cell('spreads', active=ticker, item=f"{att}_roll")
            c4.go(0)


def update_volume():
    for ticker in volume_list:
        contracts = pyg.get_data('contracts', active=ticker, item='fut_chain')
        for idx, row in contracts.iterrows():
            if row["t5"] > cdr.today() and row["last_t"] < cdr.today() + dt.timedelta(days=364):
                try:
                    c = pyg.get_cell("contracts_PX_VOLUME", active=ticker, m=row["m"], y=row["y"])
                except:
                    db = partial(mongo_table, db='bbg', table="contracts_PX_VOLUME", url=_unrecovered('IMG_5019 line 196: MongoDB URL tail'),
                                 pk=['active', 'm', 'y'])
                    c = periodic_cell(function=bbg.bdh_update, ticker=row['ticker'], fields=["PX_VOLUME"],
                                      sdate=row['fut_first_trade_dt'], edate=row["last_t"],
                                      data=None, db=db, active=ticker, m=row["m"], y=row["y"],
                                      period='1b', end_date=row['last_t'])
                c.go()


def update():
    update_spread()
    update_spot()
    update_xspread()
    update_outright(fut_list)
    update_outright(gas_list)
    update_outright(fut_list_px_last)
    update_rolls()
    update_spread_rolls()
    update_volume()


if __name__ == '__main__':
    update()
