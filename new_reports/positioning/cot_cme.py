import pandas as pd
import datetime as dt
import statsmodels.api as sm
from dateutil.relativedelta import relativedelta
from ecm.cmds.config import root_path
import sys
import itertools
sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")
import cot_macro
import os
sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")
from ecm.atom.services import fetch_series
import cot_data as cot_data_module
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.ticker as ticker
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, json_path
from ecm.cmds.cdr import today
import ecm.cmds.cot as cot
import ecm.cmds.pyg as pyg
import ecm.cmds.rvx as rvx
import ecm.cmds.bbg as bbg
import ecm.cmds.config as config
from ecm.cmds.config import url
from pyg_cell import *
from functools import partial
from pyg_mongo import mongo_table
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from ecm.cmds.utils import convert_path_to_linux
from pandas.tseries.offsets import BDay

send_to = ['commods@elementcapital.com']
report_name = 'COT - FRIDAY'
file_name = 'cot_cme'  # without .py
file_path = f"{root_path}\\autoreports\\reports\\positioning\\{file_name}.py"
chart_sdate = dt.datetime(2018, 1, 1)
cal_period = '3n'


def _photo_gap(source_line, visible_prefix):
    raise NotImplementedError(f'Unrecovered cot_cme source line {source_line}: {visible_prefix}')


cot_dict = {
    'COA Comdty': {
        'MMLF': 'ICFUBMML Index',
        'MMSF': 'ICFUBMMS Index',
        'MMLFO': 'ICCBBMML Index',
        'MMSFO': 'ICCBBMMS Index',
        'OIFO': 'ICCBBOIN Index',
        'OIF': 'ICFUBOIN Index',
        'SDLF': 'ICFUBSWL Index',
        'SDSF': 'ICFUBSWS Index',
        'SDLFO': 'ICCBBSWL Index',
        'SDSFO': 'ICCBBSWS Index',
    },
    'QSA Comdty': {
        'MMLF': 'ICFUAMML Index',
        'MMSF': 'ICFUAMMS Index',
        'MMLFO': 'ICCBAMML Index',
        'MMSFO': 'ICCBAMMS Index',
        'OIFO': 'ICCBAOIN Index',
        'OIF': 'ICFUAOIN Index',
        'SDLF': 'ICFUASWL Index',
        'SDSF': 'ICFUASWS Index',
        'SDLFO': 'ICCBASWL Index',
        'SDSFO': 'ICCBASWS Index',
    },
    'CLA Comdty': {
        'MMLF': 'CFFDQMML Index',
        'MMSF': 'CFFDQMMS Index',
        'MMLFO': 'CFCDQMML Index',
        'MMSFO': 'CFCDQMMS Index',
        'OIFO': 'NYM0COIN Index',
        'OIF': 'NYM1COIN Index',
        'NCLF': 'NYM1CNCL Index',
        'NCSF': 'NYM1CNCS Index',
        'NCLFO': 'NYM0CNCL Index',
        'NCSFO': 'NYM0CNCS Index',
        'SDLF': 'CFFDQSWL Index',
        'SDSF': 'CFFDQSWS Index',
        'SDLFO': 'CFCDQSWL Index',
        'SDSFO': 'CFCDQSWS Index',
    },
    'ENA Comdty': {
        'MMLF': 'CFFDPMML Index',
        'MMSF': 'CFFDPMMS Index',
        'MMLFO': 'CFCDPMML Index',
        'MMSFO': 'CFCDPMMS Index',
        'OIFO': 'EN1CAOIN Index',
        'OIF': 'EN1FAOIN Index',
        'NCLF': 'EN1FANCL Index',
        'NCSF': 'EN1FANCS Index',
        'NCLFO': 'EN1CANCL Index',
        'NCSFO': 'EN1CANCS Index',
        'SDLF': 'CFFDPSWL Index',
        'SDSF': 'CFFDPSWS Index',
        'SDLFO': 'CFCDPSWL Index',
        'SDSFO': 'CFCDPSWS Index',
    },
    'NYMEX Brent': {
        'MMLF': 'CBTUEMML Index',
        'MMSF': 'CBTUEMMS Index',
        'MMLFO': 'CBTVEMML Index',
        'MMSFO': 'CBTVEMMS Index',
        'OIFO': 'CBTZEOIN Index',
        'OIF': 'CBTYEOIN Index',
        'NCLF': 'CBTYENCL Index',
        'NCSF': 'CBTYENCS Index',
        'NCLFO': 'CBTZENCL Index',
        'NCSFO': 'CBTZENCS Index',
        'SDLF': 'CBTUESWL Index',
        'SDSF': 'CBTUESWS Index',
        'SDLFO': 'CBTVESWL Index',
        'SDSFO': 'CBTVESWS Index',
    },
    'XBA Comdty': {
        'MMLF': 'CFFDRMML Index',
        'MMSF': 'CFFDRMMS Index',
        'MMLFO': 'CFCDRMML Index',
        'MMSFO': 'CFCDRMMS Index',
        'OIFO': 'NYM0XOIN Index',
        'OIF': 'NYM2XOIN Index',
        'NCLF': 'NYM2XNCL Index',
        'NCSF': 'NYM2XNCS Index',
        'NCLFO': 'NYM0XNCL Index',
        'NCSFO': 'NYM0XNCS Index',
        'SDLF': 'CFFDRSWL Index',
        'SDSF': 'CFFDRSWS Index',
        'SDLFO': 'CFCDRSWL Index',
        'SDSFO': 'CFCDRSWS Index',
    },
    'HOA Comdty': {
        'MMLF': 'CFFDNMML Index',
        'MMSF': 'CFFDNMMS Index',
        'MMLFO': 'CFCDNMML Index',
        'MMSFO': 'CFCDNMMS Index',
        'OIFO': 'NYM0HOIN Index',
        'OIF': 'NYM1HOIN Index',
        'NCLF': 'NYM1HNCL Index',
        'NCSF': 'NYM1HNCS Index',
        'NCLFO': 'NYM0HNCL Index',
        'NCSFO': 'NYM0HNCS Index',
        'SDLF': 'CFFDNSWL Index',
        'SDSF': 'CFFDNSWS Index',
        'SDLFO': 'CFCDNSWL Index',
        'SDSFO': 'CFCDNSWS Index',
    },
    'NGA Comdty': {
        'MMLF': 'CFFDOMML Index',
        'MMSF': 'CFFDOMMS Index',
        'MMLFO': 'CFCDOMML Index',
        'MMSFO': 'CFCDOMMS Index',
        'OIFO': 'NYM0NOIN Index',
        'OIF': 'NYM1NOIN Index',
        'NCLF': 'NYM1NNCL Index',
        'NCSF': 'NYM1NNCS Index',
        'NCLFO': 'NYM0NNCL Index',
        'NCSFO': 'NYM0NNCS Index',
    },
    'NG NYMEX Swap': {
        'MMLF': 'DFU2FMML Index',
        'MMSF': 'DFU2FMMS Index',
        'MMLFO': 'DCO2FMML Index',
        'MMSFO': 'DCO2FMMS Index',
        'OIFO': 'NYM0SOIN Index',
        'OIF': 'NYM2NOIN Index',
        'NCLF': 'NYM2NNCL Index',
        'NCSF': 'NYM2NNCS Index',
        'NCLFO': 'NYM0SNCL Index',
        'NCSFO': 'NYM0SNCS Index',
    },
    'NG NYMEX Penultimate': {
        'MMLF': 'DFU2GMML Index',
        'MMSF': 'DFU2GMMS Index',
        'MMLFO': 'DCO2GMML Index',
        'MMSFO': 'DCO2GMMS Index',
        'OIFO': 'NYM0VOIN Index',
        'OIF': 'NYM2SOIN Index',
        'NCLF': 'NYM2SNCL Index',
        'NCSF': 'NYM2SNCS Index',
        'NCLFO': 'NYM0VNCL Index',
        'NCSFO': 'NYM0VNCS Index',
    },
    'NG ICE Swap Dealers': {
        'SDLF': 'CBTUFSWL Index',
        'SDSF': 'CBTUFSWS Index',
    },
    'NG ICE Henry Hub': {
        'MMLF': 'DFU4NMML Index',
        'MMSF': 'DFU4NMMS Index',
        'MMLFO': 'DCO4NMML Index',
        'MMSFO': 'DCO4NMMS Index',
        'OIFO': 'EN1CBOIN Index',
        'OIF': 'EN1FBOIN Index',
        'NCLF': 'EN1FBNCL Index',
        'NCSF': 'EN1FBNCS Index',
        'NCLFO': 'EN1CBNCL Index',
        'NCSFO': 'EN1CBNCS Index',
    },
    'GKA Options': {
        'MMLFO': 'CFCDWMML Index',
        'MMSFO': 'CFCDWMMS Index',
    },
    'GCA Comdty': {
        'MMLF': 'CFFDUMML Index',
        'MMSF': 'CFFDUMMS Index',
        'MMLFO': 'CFCDUMML Index',
        'MMSFO': 'CFCDUMMS Index',
        'OIFO': 'CMX0GOIN Index',
        'OIF': 'CEI1GOIN Index',
        'NCLF': 'CEI1GNCL Index',
        'NCSF': 'CEI1GNCS Index',
        'NCLFO': 'CMX0GNCL Index',
        'NCSFO': 'CMX0GNCS Index',
    },
    'SIA Comdty': {
        'MMLF': 'CFFDSMML Index',
        'MMSF': 'CFFDSMMS Index',
        'MMLFO': 'CFCDSMML Index',
        'MMSFO': 'CFCDSMMS Index',
        'OIFO': 'CMX0SOIN Index',
        'OIF': 'CEI1SOIN Index',
        'NCLF': 'CEI1SNCL Index',
        'NCSF': 'CEI1SNCS Index',
        'NCLFO': 'CMX0SNCL Index',
        'NCSFO': 'CMX0SNCS Index',
    },
    'PLA Comdty': {
        'MMLF': 'DFU3OMML Index',
        'MMSF': 'DFU3OMMS Index',
        'MMLFO': 'DCO3OMML Index',
        'MMSFO': 'DCO3OMMS Index',
        'OIFO': 'NYM0POIN Index',
        'OIF': 'NYM3POIN Index',
        'NCLF': 'NYM3PNCL Index',
        'NCSF': 'NYM3PNCS Index',
        'NCLFO': 'NYM0PNCL Index',
        'NCSFO': 'NYM0PNCS Index',
    },
    'PAA Comdty': {
        'MMLF': 'DFU3NMML Index',
        'MMSF': 'DFU3NMMS Index',
        'MMLFO': 'DCO3NMML Index',
        'MMSFO': 'DCO3NMMS Index',
        'OIFO': 'NYM0AOIN Index',
        'OIF': 'NYM2POIN Index',
        'NCLF': 'NYM2PNCL Index',
        'NCSF': 'NYM2PNCS Index',
        'NCLFO': 'NYM0ANCL Index',
        'NCSFO': 'NYM0ANCS Index',
    },
    'HGA Comdty': {
        'MMLF': 'CFFDTMML Index',
        'MMSF': 'CFFDTMMS Index',
        'MMLFO': 'CFCDTMML Index',
        'MMSFO': 'CFCDTMMS Index',
        'OIFO': 'CMX0COIN Index',
        'OIF': 'CEI1COIN Index',
        'NCLF': 'CEI1CNCL Index',
        'NCSF': 'CEI1CNCS Index',
        'NCLFO': 'CMX0CNCL Index',
        'NCSFO': 'CMX0CNCS Index',
    },
    'S A Comdty': {
        'MMLF': 'CFFDGMML Index',
        'MMSF': 'CFFDGMMS Index',
        'MMLFO': 'CFCDGMML Index',
        'MMSFO': 'CFCDGMMS Index',
        'OIFO': 'CBT0SOIN Index',
        'OIF': 'CBT1SOIN Index',
        'NCLF': 'CBT1SNCL Index',
        'NCSF': 'CBT1SNCS Index',
        'NCLFO': 'CBT0SNCL Index',
        'NCSFO': 'CBT0SNCS Index',
    },
    'SMA Comdty': {
        'MMLF': 'CFFDIMML Index',
        'MMSF': 'CFFDIMMS Index',
        'MMLFO': 'CFCDIMML Index',
        'MMSFO': 'CFCDIMMS Index',
        'OIFO': 'CBTTSOIN Index',
        'OIF': 'CBT3SOIN Index',
        'NCLF': 'CBT3SNCL Index',
        'NCSF': 'CBT3SNCS Index',
        'NCLFO': 'CBTTSNCL Index',
        'NCSFO': 'CBTTSNCS Index',
    },
    'BOA Comdty': {
        'MMLF': 'CFFDHMML Index',
        'MMSF': 'CFFDHMMS Index',
        'MMLFO': 'CFCDHMML Index',
        'MMSFO': 'CFCDHMMS Index',
        'OIFO': 'CBTPSOIN Index',
        'OIF': 'CBT2SOIN Index',
        'NCLF': 'CBT2SNCL Index',
        'NCSF': 'CBT2SNCS Index',
        'NCLFO': 'CBTPSNCL Index',
        'NCSFO': 'CBTPSNCS Index',
    },
    'C A Comdty': {
        'MMLF': 'CFFDCMML Index',
        'MMSF': 'CFFDCMMS Index',
        'MMLFO': 'CFCDCMML Index',
        'MMSFO': 'CFCDCMMS Index',
        'OIFO': 'CBT0COIN Index',
        'OIF': 'CBT1COIN Index',
        'NCLF': 'CBT1CNCL Index',
        'NCSF': 'CBT1CNCS Index',
        'NCLFO': 'CBT0CNCL Index',
        'NCSFO': 'CBT0CNCS Index',
    },
    'W A Comdty': {
        'MMLF': 'CFFDAMML Index',
        'MMSF': 'CFFDAMMS Index',
        'MMLFO': 'CFCDAMML Index',
        'MMSFO': 'CFCDAMMS Index',
        'OIFO': 'CBT0WOIN Index',
        'OIF': 'CBT1WOIN Index',
        'NCLF': 'CBT1WNCL Index',
        'NCSF': 'CBT1WNCS Index',
        'NCLFO': 'CBT0WNCL Index',
        'NCSFO': 'CBT0WNCS Index',
    },
    'SBA Comdty': {
        'MMLF': 'CFFDLMML Index',
        'MMSF': 'CFFDLMMS Index',
        'MMLFO': 'CFCDLMML Index',
        'MMSFO': 'CFCDLMMS Index',
        'OIFO': 'CSC0SOIN Index',
        'OIF': 'CSC1SOIN Index',
        'NCLF': 'CSC1SNCL Index',
        'NCSF': 'CSC1SNCS Index',
        'NCLFO': 'CSC0SNCL Index',
        'NCSFO': 'CSC0SNCS Index',
    },
    'CTA Comdty': {
        'MMLF': 'CFFDJMML Index',
        'MMSF': 'CFFDJMMS Index',
        'MMLFO': 'CFCDJMML Index',
        'MMSFO': 'CFCDJMMS Index',
        'OIFO': 'NYC0COIN Index',
        'OIF': 'NYC1COIN Index',
        'NCLF': 'NYC1CNCL Index',
        'NCSF': 'NYC1CNCS Index',
        'NCLFO': 'NYC0CNCL Index',
        'NCSFO': 'NYC0CNCS Index',
    },
    'KCA Comdty': {
        'MMLF': 'CFFDMMML Index',
        'MMSF': 'CFFDMMMS Index',
        'MMLFO': 'CFCDMMML Index',
        'MMSFO': 'CFCDMMMS Index',
        'OIFO': 'CSC0FOIN Index',
        'OIF': 'CSC1FOIN Index',
        'NCLF': 'CSC1FNCL Index',
        'NCSF': 'CSC1FNCS Index',
        'NCLFO': 'CSC0FNCL Index',
        'NCSFO': 'CSC0FNCS Index',
    },
    'CCA Comdty': {
        'MMLF': 'CFFDKMML Index',
        'MMSF': 'CFFDKMMS Index',
        'MMLFO': 'CFCDKMML Index',
        'MMSFO': 'CFCDKMMS Index',
        'OIFO': 'CSC0COIN Index',
        'OIF': 'CSC1COIN Index',
        'NCLF': 'CSC1CNCL Index',
        'NCSF': 'CSC1CNCS Index',
        'NCLFO': 'CSC0CNCL Index',
        'NCSFO': 'CSC0CNCS Index',
    },
}

px_ticker_dict = {
    'GAS': ['NG1 Comdty', 'NGJAN1 Comdty', 'FSNGS SU26 Index'],
    'OIL': ['CO1 Comdty', 'XB1 Comdty', 'QS1 Comdty'],
    'MIFID': ['CO1 Comdty', f'AGD2 Comdty', 'QS1 Comdty'],
    'TTF': ['TZT1 Comdty', 'QZT1 Comdty', 'QQT1 Comdty'],
    'PM': ['GC1 Comdty', 'SI1 Comdty', 'PL1 Comdty'],
    'BM': ['HG1 Comdty', 'LP1 Comdty', 'LA1 Comdty'],
    'EUA': ['MOA Comdty', 'DET2 Comdty', 'JXT2 Comdty'],
    'ICE': ['COA Comdty', 'QSA Comdty'],
}
pos_vs_px_dict = {
    'OIL': ['COA Comdty', 'CLA Comdty'],
    'OIL_PRODUCTS': ['QSA Comdty', 'XBA Comdty', 'HOA Comdty'],
    'GAS': ['NGA Comdty'],
    'MIFID': ['COA Comdty', f'AGD2 Comdty', 'QSA Comdty'],
    'TTF': ['TZTA Comdty'],
    'EUA': ['MOA Comdty'],
    'PM': ['GCA Comdty', 'SIA Comdty', 'PLA Comdty'],
    'BM': ['HGA Comdty', 'LPA Comdty', 'LAA Comdty'],
    'ICE': ['COA Comdty', 'QSA Comdty'],
}


def create_raw_data():
    for k, v in cot_dict.items():
        if k != 'NG ICE Swap Dealers':
            continue
        for k1, v1 in v.items():
            print(k)
            if k1 not in ['SDLF', 'SDSF']:
                continue
            cot.cot_cell(ticker=v1, active=k, item=k1, period=cal_period)


def create_total_crude():
    """Total Crude = ICE Brent + ICE WTI + NYMEX WTI + NYMEX Brent"""
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO', 'SDLF', 'SDSF', 'SDLFO', 'SDSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='Crude', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='COA Comdty', item=item)
        c2 = pyg.get_cell(db, active='ENA Comdty', item=item)
        c3 = pyg.get_cell(db, active='CLA Comdty', item=item)
        c4 = pyg.get_cell(db, active='NYMEX Brent', item=item)
        c = periodic_cell(
            function=ts.sum_dfs,
            dfs=[c1, c2, c3, c4],
            item=item,
            active='Crude',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def create_total_brent():
    """Total Crude = ICE Brent + NYMEX Brent"""
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO', 'SDLF', 'SDSF', 'SDLFO', 'SDSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='Brent', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='COA Comdty', item=item)
        c2 = pyg.get_cell(db, active='NYMEX Brent', item=item)
        c = periodic_cell(
            function=ts.sum_dfs,
            dfs=[c1, c2],
            item=item,
            active='Brent',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def create_total_product():
    """Total product = ICE QS*0.853 + NYMEX XB + NYMEX HO"""
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO', 'SDLF', 'SDSF', 'SDLFO', 'SDSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='Product', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='QSA Comdty', item=item)
        c2 = pyg.get_cell(db, active='XBA Comdty', item=item)
        c3 = pyg.get_cell(db, active='HOA Comdty', item=item)
        c = periodic_cell(
            function=ts.sumproduct,
            dfs=[c1, c2, c3],
            w=[0.853, 1, 1],
            item=item,
            active='Product',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def create_total_oil():
    """Total oil = Crude + Product"""
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO', 'SDLF', 'SDSF', 'SDLFO', 'SDSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='Crude+Product', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='COA Comdty', item=item)
        c2 = pyg.get_cell(db, active='ENA Comdty', item=item)
        c3 = pyg.get_cell(db, active='CLA Comdty', item=item)
        c4 = pyg.get_cell(db, active='NYMEX Brent', item=item)
        c5 = pyg.get_cell(db, active='QSA Comdty', item=item)
        c6 = pyg.get_cell(db, active='XBA Comdty', item=item)
        c7 = pyg.get_cell(db, active='HOA Comdty', item=item)
        c = periodic_cell(
            function=ts.sumproduct,
            dfs=[c1, c2, c3, c4, c5, c6, c7],
            w=[1, 1, 1, 1, 0.853, 1, 1],
            item=item,
            active='Crude+Product',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def create_total_pm():
    """Total PM = Gold + Silver + Platinum + Palladium"""
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO', 'NCLF', 'NCSF', 'NCLFO', 'NCSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='Precious Metal', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='GCA Comdty', item=item)
        c2 = pyg.get_cell(db, active='SIA Comdty', item=item)
        c3 = pyg.get_cell(db, active='PLA Comdty', item=item)
        c4 = pyg.get_cell(db, active='PAA Comdty', item=item)
        c = periodic_cell(
            function=ts.sumproduct,
            dfs=[c1, c2, c3, c4],
            w=[1, 1, 1, 1],
            item=item,
            active='Precious Metal',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def create_total_natgas():
    """Total NatGas = NGA Comdty + NG NYMEX Swap + NG NYMEX Penultimate + NG ICE Henry Hub + GKA Options"""
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    item_list = ['MMLF', 'MMSF', 'OIF', 'OIFO', 'NCLF', 'NCSF', 'NCLFO', 'NCSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='NatGas', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='NGA Comdty', item=item)
        c2 = pyg.get_cell(db, active='NG NYMEX Swap', item=item)
        c3 = pyg.get_cell(db, active='NG NYMEX Penultimate', item=item)
        c4 = pyg.get_cell(db, active='NG ICE Henry Hub', item=item)
        c = periodic_cell(
            function=ts.sumproduct,
            dfs=[c1, c2, c3, c4],
            w=[1, 0.25, 0.25, 0.25],
            item=item,
            active='NG CME+ICE',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()

    item_list = ['MMLFO', 'MMSFO']
    for item in item_list:
        try:
            c = pyg.get_cell(db, active='NatGas', item=item)
            db().inc(_id=c._id).drop()
        except:
            pass
        c1 = pyg.get_cell(db, active='NGA Comdty', item=item)
        c2 = pyg.get_cell(db, active='NG NYMEX Swap', item=item)
        c3 = pyg.get_cell(db, active='NG NYMEX Penultimate', item=item)
        c4 = pyg.get_cell(db, active='NG ICE Henry Hub', item=item)
        c5 = pyg.get_cell(db, active='GKA Options', item=item)
        c = periodic_cell(
            function=ts.sumproduct,
            dfs=[c1, c2, c3, c4, c5],
            w=[1, 0.25, 0.25, 0.25, 1],
            item=item,
            active='NG CME+ICE',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def vwap(active):
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    try:
        c = pyg.get_cell(db, active=active, item='VWAP')
        db().inc(_id=c._id).drop()
    except:
        pass
    c = periodic_cell(
        function=cot.vwap,
        active=active,
        item='VWAP',
        ticker=active,
        db=db,
        period=cal_period,
    )
    c.go()


def all_vwaps():
    for k, v in cot_dict.items():
        if ticker.is_active_contract(k) and k not in ['ENA Comdty', 'GKA Options']:
            vwap(k)


def vwap_oil():
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    try:
        c = pyg.get_cell(db, active='Crude', item='VWAP')
        db().inc(_id=c._id).drop()
    except:
        pass
    c1 = pyg.get_cell(db, active='COA Comdty', item='VWAP')
    c2 = pyg.get_cell(db, active='CLA Comdty', item='VWAP')
    c = periodic_cell(
        function=ts.sumproduct,
        dfs=[c1, c2],
        w=[1, 1],
        method='mean',
        active='Crude',
        item='VWAP',
        ticker=None,
        db=db,
        period=cal_period,
    )
    c.go()
    try:
        c = pyg.get_cell(db, active='Product', item='VWAP')
        db().inc(_id=c._id).drop()
    except:
        pass
    c1 = pyg.get_cell(db, active='QSA Comdty', item='VWAP')
    c2 = pyg.get_cell(db, active='XBA Comdty', item='VWAP')
    c3 = pyg.get_cell(db, active='HOA Comdty', item='VWAP')
    c = periodic_cell(
        function=ts.sumproduct,
        dfs=[c1, c2, c3],
        w=[0.853, 1, 1],
        method='mean',
        active='Product',
        item='VWAP',
        ticker=None,
        db=db,
        period=cal_period,
    )
    c.go()


def get_px_chart(name, cot_start):
    tickers = px_ticker_dict[name]
    all_data = []
    column_titles = []
    for active in tickers:
        actual_ticker = bbg.bref(active, 'ticker').iloc[0][-1]
        if not active.lower().endswith('index'):
            ticker = f'{actual_ticker} Comdty'
        else:
            ticker = active
        data = bbg.bdh(
            ticker,
            ['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST', 'VOLUME', 'FUT_AGGTE_OPEN_INT'],
            today() - BDay(120),
            today(),
        )
        all_data.append(data)
        column_titles.append(active)
    fig = chart.cot_px_ohlc_chart(all_data, title='', column_titles=column_titles, cot_start=cot_start)
    return fig


def get_px_chart_single(active, cot_start):
    actual_ticker = bbg.bref(active, 'ticker').iloc[0][-1]
    if not active.lower().endswith('index'):
        ticker = f'{actual_ticker} Comdty'
    else:
        ticker = active
    data = bbg.bdh(
        ticker,
        ['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST', 'VOLUME', 'FUT_AGGTE_OPEN_INT'],
        today() - BDay(120),
        today(),
    )
    fig = chart.cot_px_ohlc_chart([data], title='', column_titles=[active], cot_start=cot_start)
    return fig


def get_pos_vs_px_change_chart(active, data, min_year=2024, n_weeks=1, **kwargs):
    data = data[['Net']]
    px_data = bbg.bdh(active, 'PX_LAST', sdate=dt.datetime(year=min_year, month=1, day=1), edate=today())
    data = pd.concat([data, px_data.reindex(data.index)], axis=1)
    filtered_data = data.loc[data.index.year >= min_year]
    if 'title' not in kwargs:
        kwargs['title'] = active
    if 'is_spread' not in kwargs:
        kwargs['is_spread'] = False
    fig = chart.price_vs_pos_chart(filtered_data, n_weeks=n_weeks, **kwargs)
    return fig


spread_list = ['AGD']


def get_pos_chart(name, data_dict):
    tickers = pos_vs_px_dict[name]
    fig_main = make_subplots(rows=1, cols=len(tickers), subplot_titles=tickers)
    for col, tk in enumerate(tickers, start=1):
        if any([tk.startswith(s) for s in spread_list]):
            is_spread = True
        else:
            is_spread = False
        ct_data = data_dict.get(tk)
        if ct_data is None:
            continue
        subfig = get_pos_vs_px_change_chart(tk, ct_data, is_spread=is_spread)
        for tr in subfig.data:
            if col > 1:
                tr.showlegend = False
            fig_main.add_trace(tr, row=1, col=col)
    cols = len(tickers)
    for c in range(1, cols + 1):
        fig_main.update_xaxes(title_text='WoW Net Position Change', row=1, col=c)
    for c in range(1, cols + 1):
        fig_main.update_yaxes(title_text='WoW Price Change', row=1, col=c)
    fig_main.update_layout(
        width=700 * cols,
        height=500,
        legend=dict(orientation='h', x=0.5, y=-0.12, xanchor='center', yanchor='top'),
        margin=dict(b=90),
    )
    return fig_main


def cftc_analysis_fut(active, alt_active, nc=True, cta=None, update=True):
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    if active in ['BTCA Curncy']:
        btc1 = pyg.get_cell(db, active=active, item='AMLF')
        btc2 = pyg.get_cell(db, active=active, item='AMSF')
        btc3 = pyg.get_cell(db, active=active, item='LFLF')
        btc4 = pyg.get_cell(db, active=active, item='LFSF')
        if btc1.function.__name__ != 'bdh' and update:
            btc1.go()
            btc2.go()
            btc3.go()
            btc4.go()
        long = btc1.load().data.dropna() + btc3.load().data.dropna()
        short = btc2.load().data.dropna() + btc4.load().data.dropna()
    else:
        c1 = pyg.get_cell(db, active=active, item='MMLF')
        c2 = pyg.get_cell(db, active=active, item='MMSF')
        if c1.function.__name__ != 'bdh' and update:
            c1.go()
            c2.go()
        long = c1.load().data.dropna()
        short = c2.load().data.dropna()
    if nc:
        c1_ = pyg.get_cell(db, active=active, item='NCLF')
        c2_ = pyg.get_cell(db, active=active, item='NCSF')
        if c1_.function.__name__ != 'bdh' and update:
            c1_.go()
            c2_.go()
        long1 = c1_.load().data.dropna()
        short1 = c2_.load().data.dropna()
    if active[-7:] in [' Comdty', ' Curncy']:
        c3 = pyg.get_cell(db, active=active, item='OIF')
    else:
        if update:
            c3 = pyg.get_cell(db, active=active, item='OIF').go()
        else:
            c3 = pyg.get_cell(db, active=active, item='OIF')
    if alt_active is not None:
        if update:
            c4 = pyg.get_cell(db, active=alt_active, item='VWAP').go()
        else:
            c4 = pyg.get_cell(db, active=alt_active, item='VWAP')
        if alt_active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=alt_active, item='ref')
    else:
        if active not in ['BTCA Curncy', 'Precious Metal']:
            if update:
                c4 = pyg.get_cell(db, active=active, item='VWAP').go()
            else:
                c4 = pyg.get_cell(db, active=active, item='VWAP')
        if active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        elif active == 'Product':
            ref = pyg.get_data('contracts', active='XBA Comdty', item='ref')
        elif active == 'Precious Metal':
            ref = pyg.get_data('contracts', active='GCA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=active, item='ref')
    oi = c3.load().data.dropna()
    if active not in ['BTCA Curncy', 'Precious Metal']:
        vp = c4.load().data.dropna()
        vp.fillna(method='ffill', inplace=True)
    else:
        vp = pd.DataFrame(0, index=pd.bdate_range(today() - relativedelta(years=3), today(), freq='B'),
                           columns=['PX_LAST', 'VWAP'])
    if cta is not None:
        cta = cta.reindex(long.index)
    if nc:
        df_ = cot.analysis(active=active, type='Fut', vwap=vp, ref=ref, long=long, short=short,
                           oi=oi, long1=long1, short1=short1, cta=cta)
    else:
        df_ = cot.analysis(active=active, type='Fut', vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
    return df_


def cftc_analysis_fut_dealer(active, alt_active, nc=True, cta=None, update=True):
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    if active in ['BTCA Curncy']:
        btc1 = pyg.get_cell(db, active=active, item='AMLF')
        btc2 = pyg.get_cell(db, active=active, item='AMSF')
        btc3 = pyg.get_cell(db, active=active, item='LFLF')
        btc4 = pyg.get_cell(db, active=active, item='LFSF')
        if btc1.function.__name__ != 'bdh' and update:
            btc1.go()
            btc2.go()
            btc3.go()
            btc4.go()
        long = btc1.load().data + btc3.load().data
        short = btc2.load().data + btc4.load().data
    else:
        c1 = pyg.get_cell(db, active=active, item='SDLF')
        c2 = pyg.get_cell(db, active=active, item='SDSF')
        if active == 'NG ICE Swap Dealers':
            c1.go()
            c2.go()
        if c1.function.__name__ != 'bdh' and update:
            c1.go()
            c2.go()
        long = c1.load().data
        short = c2.load().data
    if nc:
        c1_ = pyg.get_cell(db, active=active, item='NCLF')
        c2_ = pyg.get_cell(db, active=active, item='NCSF')
        if c1_.function.__name__ != 'bdh' and update:
            c1_.go()
            c2_.go()
        long1 = c1_.load().data
        short1 = c2_.load().data
    try:
        if active[-7:] in [' Comdty', ' Curncy']:
            c3 = pyg.get_cell(db, active=active, item='OIF')
        elif active == 'NG ICE Swap Dealers':
            c3 = pyg.get_cell(db, active='NG ICE Henry Hub', item='OIF')
        else:
            if update:
                c3 = pyg.get_cell(db, active=active, item='OIF').go()
            else:
                c3 = pyg.get_cell(db, active=active, item='OIF')
    except:
        c3 = None
    if alt_active is not None:
        if update:
            c4 = pyg.get_cell(db, active=alt_active, item='VWAP').go()
        else:
            c4 = pyg.get_cell(db, active=alt_active, item='VWAP')
        if alt_active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=alt_active, item='ref')
    else:
        if active not in ['BTCA Curncy', 'Precious Metal']:
            if update:
                c4 = pyg.get_cell(db, active=active, item='VWAP').go()
            else:
                c4 = pyg.get_cell(db, active=active, item='VWAP')
        if active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        elif active == 'Product':
            ref = pyg.get_data('contracts', active='XBA Comdty', item='ref')
        elif active == 'Precious Metal':
            ref = pyg.get_data('contracts', active='GCA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=active, item='ref')
    if c3 is not None:
        oi = c3.load().data
    else:
        oi = pd.DataFrame()
    if active not in ['BTCA Curncy', 'Precious Metal']:
        vp = c4.load().data
        vp.fillna(method='ffill', inplace=True)
    else:
        vp = pd.DataFrame(0, index=pd.bdate_range(today() - relativedelta(years=3), today(), freq='B'),
                           columns=['PX_LAST', 'VWAP'])
    if cta is not None:
        cta = cta.reindex(long.index)
    if nc:
        df_ = cot.analysis(active=active, type='Fut', vwap=vp, ref=ref, long=long, short=short,
                           oi=oi, long1=long1, short1=short1, cta=cta)
    else:
        df_ = cot.analysis(active=active, type='Fut', vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
    if active == 'NG ICE Swap Dealers':
        cot_data = ts.concat(
            dfs=[long, short, oi],
            axis=1,
            ignore_index=False,
            df_index=long.index,
            columns=['Long', 'Short', 'OI'],
        )
        cot_data['Net'] = cot_data['Long'] - cot_data['Short']
        cot_data['Long OI'] = cot_data['Long'] / cot_data['OI']
        cot_data['Short OI'] = cot_data['Short'] / cot_data['OI']
        cot_data['Net OI'] = cot_data['Net'] / cot_data['OI']
        dts = pd.bdate_range(vp.index[0], vp.index[-1])
        vp_ = vp.reindex(dts, method='ffill')
        cot_data['PX_LAST'] = vp_['VWAP']
        cot_data['PX_LAST_1'] = vp_['PX_LAST']
        return df_, cot_data
    return df_


def cftc_analysis_fut_opt(active, alt_active, nc=True, cta=None, update=True):
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    if active in ['BTCA Curncy']:
        btc1 = pyg.get_cell(db, active=active, item='AMLFO')
        btc2 = pyg.get_cell(db, active=active, item='AMSFO')
        btc3 = pyg.get_cell(db, active=active, item='LFLFO')
        btc4 = pyg.get_cell(db, active=active, item='LFSFO')
        if btc1.function.__name__ != 'bdh' and update:
            btc1.go()
            btc2.go()
            btc3.go()
            btc4.go()
        long = btc1.load().data.dropna() + btc3.load().data.dropna()
        short = btc2.load().data.dropna() + btc4.load().data.dropna()
    else:
        c1 = pyg.get_cell(db, active=active, item='MMLFO')
        c2 = pyg.get_cell(db, active=active, item='MMSFO')
        if c1.function.__name__ != 'bdh' and update:
            c1.load().go()
            c2.load().go()
        long = c1.load().data.dropna()
        short = c2.load().data.dropna()
    if nc:
        c1_ = pyg.get_cell(db, active=active, item='NCLFO')
        c2_ = pyg.get_cell(db, active=active, item='NCSFO')
        if c1_.function.__name__ != 'bdh' and update:
            c1_.go()
            c2_.go()
        long1 = c1_.load().data.dropna()
        short1 = c2_.load().data.dropna()
    if active[-7:] in [' Comdty', ' Curncy']:
        c3 = pyg.get_cell(db, active=active, item='OIFO')
    else:
        if update:
            c3 = pyg.get_cell(db, active=active, item='OIFO').go()
        else:
            c3 = pyg.get_cell(db, active=active, item='OIFO')
    if alt_active is not None:
        if active not in ['BTCA Curncy', 'Precious Metal']:
            if update:
                c4 = pyg.get_cell(db, active=alt_active, item='VWAP').go()
            else:
                c4 = pyg.get_cell(db, active=alt_active, item='VWAP')
        if alt_active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=alt_active, item='ref')
    else:
        if active not in ['BTCA Curncy']:
            if active == 'Precious Metal':
                if update:
                    c4 = pyg.get_cell(db, active='GCA Comdty', item='VWAP').go()
                else:
                    c4 = pyg.get_cell(db, active='GCA Comdty', item='VWAP')
            else:
                if update:
                    c4 = pyg.get_cell(db, active=active, item='VWAP').go()
                else:
                    c4 = pyg.get_cell(db, active=active, item='VWAP')
        if active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        elif active == 'Product':
            ref = pyg.get_data('contracts', active='XBA Comdty', item='ref')
        elif active == 'Precious Metal':
            ref = pyg.get_data('contracts', active='GCA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=active, item='ref')
    oi = c3.load().data.dropna()
    if active not in ['BTCA Curncy']:
        vp = c4.load().data.dropna()
        vp.fillna(method='ffill', inplace=True)
    else:
        vp = pd.DataFrame(0, index=pd.bdate_range(today() - relativedelta(years=3), today(), freq='B'),
                           columns=['PX_LAST', 'VWAP'])
    if cta is not None:
        cta = cta.reindex(long.index)
    if nc:
        df_ = cot.analysis(active=active, type='Fut,Opt', vwap=vp, ref=ref, long=long, short=short,
                           oi=oi, long1=long1, short1=short1, cta=cta)
    else:
        df_ = cot.analysis(active=active, type='Fut,Opt', vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
    cot_data = ts.concat(
        dfs=[long, short, oi],
        axis=1,
        ignore_index=False,
        df_index=long.index,
        columns=['Long', 'Short', 'OI'],
    )
    cot_data['Net'] = cot_data['Long'] - cot_data['Short']
    cot_data['Long OI'] = cot_data['Long'] / cot_data['OI']
    cot_data['Short OI'] = cot_data['Short'] / cot_data['OI']
    cot_data['Net OI'] = cot_data['Net'] / cot_data['OI']
    dts = pd.bdate_range(vp.index[0], vp.index[-1])
    vp_ = vp.reindex(dts, method='ffill')
    cot_data['PX_LAST'] = vp_['VWAP']
    cot_data['PX_LAST_1'] = vp_['PX_LAST']
    return df_, cot_data


def cftc_analysis_fut_opt_dealer(active, alt_active, nc=True, cta=None, update=True):
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    if active in ['BTCA Curncy']:
        btc1 = pyg.get_cell(db, active=active, item='AMLFO')
        btc2 = pyg.get_cell(db, active=active, item='AMSFO')
        btc3 = pyg.get_cell(db, active=active, item='LFLFO')
        btc4 = pyg.get_cell(db, active=active, item='LFSFO')
        if btc1.function.__name__ != 'bdh' and update:
            btc1.go()
            btc2.go()
            btc3.go()
            btc4.go()
        long = btc1.load().data + btc3.load().data
        short = btc2.load().data + btc4.load().data
    else:
        c1 = pyg.get_cell(db, active=active, item='SDLFO')
        c2 = pyg.get_cell(db, active=active, item='SDSFO')
        if c1.function.__name__ != 'bdh' and update:
            c1.load().go()
            c2.load().go()
        long = c1.load().data
        short = c2.load().data
    if nc:
        c1_ = pyg.get_cell(db, active=active, item='NCLFO')
        c2_ = pyg.get_cell(db, active=active, item='NCSFO')
        if c1_.function.__name__ != 'bdh' and update:
            c1_.go()
            c2_.go()
        long1 = c1_.load().data
        short1 = c2_.load().data
    if active[-7:] in [' Comdty', ' Curncy']:
        c3 = pyg.get_cell(db, active=active, item='OIFO')
    else:
        if update:
            c3 = pyg.get_cell(db, active=active, item='OIFO').go()
        else:
            c3 = pyg.get_cell(db, active=active, item='OIFO')
    if alt_active is not None:
        if active not in ['BTCA Curncy', 'Precious Metal']:
            if update:
                c4 = pyg.get_cell(db, active=alt_active, item='VWAP').go()
            else:
                c4 = pyg.get_cell(db, active=alt_active, item='VWAP')
        if alt_active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=alt_active, item='ref')
    else:
        if active not in ['BTCA Curncy']:
            if active == 'Precious Metal':
                if update:
                    c4 = pyg.get_cell(db, active='GCA Comdty', item='VWAP').go()
                else:
                    c4 = pyg.get_cell(db, active='GCA Comdty', item='VWAP')
            else:
                if update:
                    c4 = pyg.get_cell(db, active=active, item='VWAP').go()
                else:
                    c4 = pyg.get_cell(db, active=active, item='VWAP')
        if active == 'Crude':
            ref = pyg.get_data('contracts', active='COA Comdty', item='ref')
        elif active == 'Product':
            ref = pyg.get_data('contracts', active='XBA Comdty', item='ref')
        elif active == 'Precious Metal':
            ref = pyg.get_data('contracts', active='GCA Comdty', item='ref')
        else:
            ref = pyg.get_data('contracts', active=active, item='ref')
    oi = c3.load().data
    if active not in ['BTCA Curncy']:
        vp = c4.load().data
        vp.fillna(method='ffill', inplace=True)
    else:
        vp = pd.DataFrame(0, index=pd.bdate_range(today() - relativedelta(years=3), today(), freq='B'),
                           columns=['PX_LAST', 'VWAP'])
    if cta is not None:
        cta = cta.reindex(long.index)
    if nc:
        df_ = cot.analysis(active=active, type='Fut,Opt', vwap=vp, ref=ref, long=long, short=short,
                           oi=oi, long1=long1, short1=short1, cta=cta)
    else:
        df_ = cot.analysis(active=active, type='Fut,Opt', vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
    cot_data = ts.concat(
        dfs=[long, short, oi],
        axis=1,
        ignore_index=False,
        df_index=long.index,
        columns=['Long', 'Short', 'OI'],
    )
    cot_data['Net'] = cot_data['Long'] - cot_data['Short']
    cot_data['Long OI'] = cot_data['Long'] / cot_data['OI']
    cot_data['Short OI'] = cot_data['Short'] / cot_data['OI']
    cot_data['Net OI'] = cot_data['Net'] / cot_data['OI']
    dts = pd.bdate_range(vp.index[0], vp.index[-1])
    vp_ = vp.reindex(dts, method='ffill')
    cot_data['PX_LAST'] = vp_['VWAP']
    cot_data['PX_LAST_1'] = vp_['PX_LAST']
    return df_, cot_data


def get_cta_oil(k):
    cta_co = rvx.rvx(ticker='CTA LN4 CM EN CO_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_cl = rvx.rvx(ticker='CTA LN4 CM EN CL_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_ho = rvx.rvx(ticker='CTA LN4 CM EN HO_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_xb = rvx.rvx(ticker='CTA LN4 CM EN XB_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_qs = rvx.rvx(ticker='CTA LN4 CM EN QS_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    if k == 'Crude':
        cta = (cta_co.iloc[:, 0] + cta_cl.iloc[:, 0]) / 2
    elif k == 'Product':
        cta = (cta_ho.iloc[:, 0] + cta_xb.iloc[:, 0] + cta_qs.iloc[:, 0]) / 3
    elif k == 'Crude+Product':
        cta = (cta_co.iloc[:, 0] * 3 + cta_cl.iloc[:, 0] * 2 + cta_ho.iloc[:, 0] + cta_xb.iloc[:, 0]
               + _photo_gap(1228, 'remaining cta term and any scaling after cta_xb.iloc[:, 0]'))
    elif k == 'Brent':
        cta = cta_co.iloc[:, 0]
    elif k == 'CLA Comdty':
        cta = cta_cl.iloc[:, 0]
    elif k == 'QSA Comdty':
        cta = cta_qs.iloc[:, 0]
    elif k == 'HOA Comdty':
        cta = cta_ho.iloc[:, 0]
    elif k == 'XBA Comdty':
        cta = cta_xb.iloc[:, 0]
    elif k == 'COA Comdty':
        cta = cta_co.iloc[:, 0]
    else:
        cta = None
    return cta


def update_oil(send_to, update=True):
    oil_dict = {
        'Crude+Product': 'Crude', 'Crude': None, 'Brent': 'COA Comdty', 'CLA Comdty': None,
        'ENA Comdty': 'CLA Comdty', 'Product': None, 'QSA Comdty': None, 'HOA Comdty': None, 'XBA Comdty': None,
    }
    cot_table = pd.DataFrame()
    figs_net_main = []
    figs_net = []
    figs_ls_main = []
    figs_ls = []
    figs_pos_vs_px_data = {}
    chart_links = {}
    for k, v in oil_dict.items():
        cta = get_cta_oil(k)
        df_ = cftc_analysis_fut(active=k, alt_active=v, nc=False, cta=cta, update=update)
        if len(cot_table) > 0 and df_.columns[0] != cot_table.columns[0]:
            df_.columns = [cot_table.columns[0]] + list(df_.columns[1:])
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=False, cta=cta, update=update)
        if len(cot_table) > 0 and df_.columns[0] != cot_table.columns[0]:
            df_.columns = [cot_table.columns[0]] + list(df_.columns[1:])
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        if k in ['Crude+Product', 'Crude', 'Product']:
            ch_tk = 'COA Comdty' if k in ['Crude', 'Crude+Product'] else 'XBA Comdty'
            reg_fig_new = get_pos_vs_px_change_chart(ch_tk, cot_data, n_weeks=1,
                title=_photo_gap(1281, 'Price vs Net position...'))
            reg_fig_4w_new = get_pos_vs_px_change_chart(ch_tk, cot_data, n_weeks=4,
                title=_photo_gap(1282, 'Price vs Net position...'))
            cta_index = cot_data.loc[cot_data.index >= dt.datetime(cot_data['Long'].last_valid_index().year, 1, 1)].index
            cta = cta.reindex(cta_index)
            fig1, fig2 = gen_figures(k, cot_data, cta=cta)
            figs_net_main.append(fig1)
            figs_ls_main.append(fig2)
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f'{html_path}\\positioning\\links\\{k}_chart.html')
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
        else:
            cta = None
            if k in ['Brent']:
                k_ = 'COA Comdty'
            else:
                k_ = k
            reg_fig_new = get_pos_vs_px_change_chart(k_, cot_data, n_weeks=1,
                title=_photo_gap(1299, 'Price vs Net position...'))
            reg_fig_4w_new = get_pos_vs_px_change_chart(k_, cot_data, n_weeks=4,
                title=_photo_gap(1300, 'Price vs Net position...'))
            if k not in ['ENA Comdty']:
                cta = rvx.rvx(ticker=f"CTA LN4 CM EN {k_.split('A Comdty')[0]}_COMDTY",
                              field='SIGNAL', sdate=f'2023-01-01', edate=today())
                cta_index = cot_data.loc[cot_data.index >= dt.datetime(cot_data['Long'].last_valid_index().year, 1, 1)].index
                cta = cta.reindex(cta_index)
                cta = cta.iloc[:, 0]
            fig1, fig2 = gen_figures(k, cot_data, cta=cta)
            if k_ in ['COA Comdty', 'CLA Comdty', 'QSA Comdty', 'HOA Comdty', 'XBA Comdty']:
                single_px_figure = get_px_chart_single(k_, cot_start=pd.to_datetime(
                    _photo_gap(1314, 'cot_table[-1:]._last_update...')))
                figs_pos_vs_px_data[k_] = cot_data
                figs_net.append([fig1, single_px_figure])
            else:
                figs_net.append([fig1, ''])
            figs_ls.append(fig2)
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f'{html_path}\\positioning\\links\\{k}_chart.html')
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
    if not cot_table.iloc[:, 1].isnull().values.any():
        figs = []
        output_html_table = table.html_format(
            df=cot_table,
            header='Speculators Net Position (Managed money)',
            footer=None,
            show_date=False,
            format_column={
                '0': {'width': '120px', 'text-align': 'left', 'highlight': [0, 'net pos rank', '_thr_high', '_thr_low'], 'right_border': True},
                '1': {'width': '60px', 'text-align': 'center'},
                '2': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [2, 'net/oi pct rank', '_thr_high', '_thr_low']},
                '3': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'bold': True, 'highlight': [3, '_price_chg', '_thr_high', '_thr_low']},
                '4': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}', 'right_border': True},
                '5': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '6': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [6, 'net change z score', '_z_high', '_z_low']},
                '7': {'width': '60px', 'text-align': 'center'},
                '8': {'width': '60px', 'text-align': 'center'},
                '9': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '10': {'width': '60px', 'text-align': 'center', 'bold': True, 'format': '{:.1%}', 'highlight': [10, '4w price change z score', '_z_high', '_z_low']},
                '11': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [11, '4w delta change z score', '_z_high', '_z_low']},
                '12': {'width': '60px', 'text-align': 'center'},
                '13': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '14': {'width': '80px', 'text-align': 'center'},
                '15': {'width': '60px', 'text-align': 'center'},
                '16': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '17': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [16, '_thr_net']},
                '18': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [17, '_thr_net']},
                '19': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [18, '_thr_high8', '_thr_low8']},
                '20': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [19, '_thr_high8', '_thr_low8'], 'right_border': True},
                '21': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '22': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '23': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            },
            format_row={
                '1': {'bottom_border': True}, '3': {'bottom_border': True}, '5': {'bottom_border': True},
                '7': {'bottom_border': True}, '9': {'bottom_border': True}, '11': {'bottom_border': True},
                '13': {'bottom_border': True},
            },
            precision=0,
            hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low',
                       '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
            inline=False,
            background_color='lightblue',
            na_rep='-',
        )
        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        cot_start = pd.to_datetime(cot_table._last_update.dropna().max()) - relativedelta(days=7)
        px_figs = get_px_chart(name='OIL', cot_start=cot_start)
        pos_fig_oil = get_pos_chart(name='OIL', data_dict=figs_pos_vs_px_data)
        pos_fig_prds = get_pos_chart(name='OIL_PRODUCTS', data_dict=figs_pos_vs_px_data)
        figs.append(output_html_table)
        table.figures_to_html(figs, f'{html_path}\\positioning\\cot_oil_table.html', task_name=report_name)
        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        figs_net_main[0].write_json(convert_path_to_linux(f'{json_path}\\positioning\\cot_oil_total.json'))
        figs_email = figs + figs_net_main + [plots_email]
        figs_new = table.to_html(
            [table.html_text('COT - OIL', style='font-family:Calibri;', tag='h1')] + figs + [px_figs]
            + _photo_gap(1458, 'remaining figure list after + [po...'),
            add_home=False,
        )
        figs_email.append('<a href="{:s}\\positioning\\cot_oil.html">Position Charts</a><br><br>'.format(html_path))
        table.figures_to_html(figs_new, f'{html_path}\\positioning\\cot_oil.html', task_name=report_name)
        send_email(send_to=send_to, subject='COT - OIL', body=figs_email,
                   html_path=f'{html_path}\\positioning\\cot_oil.html')


def update_oil_dealers(send_to, update=True):
    oil_dict = {
        'Crude+Product': 'Crude', 'Crude': None, 'Brent': 'COA Comdty', 'CLA Comdty': None,
        'ENA Comdty': 'CLA Comdty', 'Product': None, 'QSA Comdty': None, 'HOA Comdty': None, 'XBA Comdty': None,
    }
    cot_table = pd.DataFrame()
    figs_net_main = []
    figs_net = []
    figs_ls_main = []
    figs_ls = []
    chart_links = {}
    for k, v in oil_dict.items():
        df_ = cftc_analysis_fut_dealer(active=k, alt_active=v, nc=False, update=update)
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        df_, cot_data = cftc_analysis_fut_opt_dealer(active=k, alt_active=v, nc=False, update=update)
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        if k in ['Crude+Product', 'Crude', 'Product']:
            ch_tk = 'COA Comdty' if k in ['Crude', 'Crude+Product'] else 'XBA Comdty'
            reg_fig_new = get_pos_vs_px_change_chart(ch_tk, cot_data, n_weeks=1,
                title=_photo_gap(1499, 'Price vs Net position...'))
            reg_fig_4w_new = get_pos_vs_px_change_chart(ch_tk, cot_data, n_weeks=4,
                title=_photo_gap(1500, 'Price vs Net position...'))
            fig1, fig2 = gen_figures(k, cot_data)
            figs_net_main.append(fig1)
            figs_ls_main.append(fig2)
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f'{html_path}\\positioning\\links\\{k}_chart_dealers.html')
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart_dealers.html">{df_.iloc[0, 0]}</a>'
        else:
            cta = None
            if k in ['Brent']:
                k_ = 'COA Comdty'
            else:
                k_ = k
            reg_fig_new = get_pos_vs_px_change_chart(k_, cot_data, n_weeks=1,
                title=_photo_gap(1515, 'Price vs Net position...'))
            reg_fig_4w_new = get_pos_vs_px_change_chart(k_, cot_data, n_weeks=4,
                title=_photo_gap(1516, 'Price vs Net position...'))
            fig1, fig2 = gen_figures(k, cot_data)
            if k_ in ['COA Comdty', 'CLA Comdty', 'QSA Comdty', 'HOA Comdty', 'XBA Comdty']:
                single_px_figure = get_px_chart_single(k_, cot_start=pd.to_datetime(
                    _photo_gap(1519, 'cot_table._last_update...')))
                figs_net.append([fig1, single_px_figure])
            else:
                figs_net.append([fig1, ''])
            figs_ls.append(fig2)
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f'{html_path}\\positioning\\links\\{k}_chart_dealers.html')
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart_dealers.html">{df_.iloc[0, 0]}</a>'
    if not cot_table.iloc[:, 1].isnull().values.any():
        figs = []
        output_html_table = table.html_format(
            df=cot_table,
            header='Swap Dealers Net Position',
            footer=None,
            show_date=False,
            format_column={
                '0': {'width': '120px', 'text-align': 'left', 'highlight': [0, 'net pos rank', '_thr_high', '_thr_low'], 'right_border': True},
                '1': {'width': '60px', 'text-align': 'center'},
                '2': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [2, 'net/oi pct rank', '_thr_high', '_thr_low']},
                '3': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'bold': True, 'highlight': [3, '_price_chg', '_thr_high', '_thr_low']},
                '4': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}', 'right_border': True},
                '5': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '6': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [6, 'net change z score', '_z_high', '_z_low']},
                '7': {'width': '60px', 'text-align': 'center'},
                '8': {'width': '60px', 'text-align': 'center'},
                '9': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '10': {'width': '60px', 'text-align': 'center', 'bold': True, 'format': '{:.1%}', 'highlight': [10, '4w price change z score', '_z_high', '_z_low']},
                '11': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [11, '4w delta change z score', '_z_high', '_z_low']},
                '12': {'width': '60px', 'text-align': 'center'},
                '13': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '14': {'width': '80px', 'text-align': 'center'},
                '15': {'width': '60px', 'text-align': 'center'},
                '16': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '17': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [16, '_thr_net']},
                '18': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [17, '_thr_net']},
                '19': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [18, '_thr_high8', '_thr_low8']},
                '20': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [19, '_thr_high8', '_thr_low8'], 'right_border': True},
                '21': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '22': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '23': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            },
            format_row={
                '1': {'bottom_border': True}, '3': {'bottom_border': True}, '5': {'bottom_border': True},
                '7': {'bottom_border': True}, '9': {'bottom_border': True}, '11': {'bottom_border': True},
                '13': {'bottom_border': True},
            },
            precision=0,
            hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low',
                       '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
            inline=False,
            background_color='lightblue',
            na_rep='-',
        )
        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        figs.append(output_html_table)
        with open(convert_path_to_linux(f'{html_path}\\positioning\\cot_oil_table_dealers.html'), 'w') as f:
            f.write(output_html_table)
        cot_start = pd.to_datetime(cot_table._last_update.dropna().max()) - relativedelta(days=7)
        px_chart = get_px_chart(name='OIL', cot_start=cot_start)
        figs_net_main[0].write_json(convert_path_to_linux(f'{json_path}\\positioning\\cot_oil_total_dealers.json'))
        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        figs_email = figs + figs_net_main + [plots_email]
        figs_new = table.to_html(
            [table.html_text('COT - OIL Dealers', style='font-family:Calibri;', tag='h1')] + figs
            + [px_chart] + _photo_gap(1662, 'remaining figure list after + [px_chart...'),
            add_home=False,
        )
        figs_email.append('<a href="{:s}\\positioning\\cot_oil_dealers.html">Position Charts</a><br><br>'.format(html_path))
        table.figures_to_html(figs_new, f'{html_path}\\positioning\\cot_oil_dealers.html', task_name=report_name)
        send_email(send_to=send_to, subject='COT - OIL Dealers', body=figs_email,
                   html_path=f'{html_path}\\positioning\\cot_oil_dealers.html')


def update_gas(send_to):
    gas_dict = {
        'NG CME+ICE': 'NGA Comdty', 'NGA Comdty': None, 'NG ICE Henry Hub': 'NGA Comdty',
        'NG ICE Swap Dealers': 'NGA Comdty', 'GKA Options': 'NGA Comdty',
    }
    cot_table = pd.DataFrame()
    figs_net = []
    figs_ls = []
    chart_links = {}
    px_vs_pos_chart_data = {}
    cta = rvx.rvx(ticker='CTA LN4 CM EN NG_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    for k, v in gas_dict.items():
        if k not in ['GKA Options']:
            if k in ['NG ICE Swap Dealers']:
                df_, cot_data = cftc_analysis_fut_dealer(active=k, alt_active=v, nc=False, cta=cta.iloc[:, 0])
            else:
                df_ = cftc_analysis_fut(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0])
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            if k not in ['NG ICE Swap Dealers']:
                df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0])
                cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            reg_fig_new = get_pos_vs_px_change_chart('NGA Comdty', cot_data, n_weeks=1,
                title=_photo_gap(1702, 'Price vs Net position...'))
            reg_fig_4w_new = get_pos_vs_px_change_chart('NGA Comdty', cot_data, n_weeks=4,
                title=_photo_gap(1703, 'Price vs Net position...'))
            print('break')
            if k in ['NG ICE Henry Hub', 'NG ICE Swap Dealers']:
                chart_prices = bbg.bdh(ticker='FSNGY1 Index', sdate=cot_data.index[0], edate=cot_data.index[-1])
                cot_data['PX_LAST'] = chart_prices.reindex(cot_data.index).values
                fig1, fig2 = gen_figures(k, cot_data, cta=cta.iloc[:, 0], price_override_name='FSNGY1 Index')
            else:
                fig1, fig2 = gen_figures(k, cot_data, cta=cta.iloc[:, 0])
            if k in ['NGA Comdty']:
                single_px_figure = get_px_chart_single(k, cot_start=pd.to_datetime(
                    _photo_gap(1712, 'cot_table._last_update.d...')))
                px_vs_pos_chart_data[k] = cot_data
                figs_net.append([fig1, single_px_figure])
            else:
                figs_net.append([fig1, ''])
            figs_ls.append(fig2)
            figs_reg = []
            figs_reg.append(fig2)
            figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
            table.to_html(figs_reg, f'{html_path}\\positioning\\links\\{k}_chart.html')
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
    if not cot_table.iloc[:-1:, 1].isnull().values.any():
        figs = []
        output_html_table = table.html_format(
            df=cot_table,
            header='Speculators Net Position (Managed money)',
            footer=None,
            show_date=False,
            format_column={
                '0': {'width': '120px', 'text-align': 'left', 'highlight': [0, 'net pos rank', '_thr_high', '_thr_low'], 'right_border': True},
                '1': {'width': '60px', 'text-align': 'center'},
                '2': {'width': '60px', 'text-align': 'center'},
                '3': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [3, 'net/oi pct rank', '_thr_high', '_thr_low']},
                '4': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'bold': True, 'highlight': [4, '_price_chg', '_thr_high', '_thr_low']},
                '5': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}', 'right_border': True},
                '6': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '7': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [7, 'net change z score', '_z_high', '_z_low']},
                '8': {'width': '60px', 'text-align': 'center'},
                '9': {'width': '60px', 'text-align': 'center'},
                '10': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '11': {'width': '60px', 'text-align': 'center', 'bold': True, 'format': '{:.1%}', 'highlight': [11, '4w price change z score', '_z_high', '_z_low']},
                '12': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [12, '4w delta change z score', '_z_high', '_z_low']},
                '13': {'width': '60px', 'text-align': 'center'},
                '14': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '15': {'width': '80px', 'text-align': 'center'},
                '16': {'width': '60px', 'text-align': 'center'},
                '17': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '18': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [17, '_thr_net']},
                '19': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [18, '_thr_net']},
                '20': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [19, '_thr_high8', '_thr_low8']},
                '21': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [20, '_thr_high8', '_thr_low8'], 'right_border': True},
                '22': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '23': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '24': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            },
            format_row={'1': {'bottom_border': True}, '3': {'bottom_border': True}, '5': {'bottom_border': True}},
            precision=0,
            hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
            inline=False,
            background_color='lightblue',
            na_rep='-',
        )
        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        figs.append(output_html_table)
        cot_start = pd.to_datetime(cot_table._last_update.dropna().max()) - relativedelta(days=7)
        px_fig = get_px_chart(name='GAS', cot_start=cot_start)
        pos_fig = get_pos_chart(name='GAS', data_dict=px_vs_pos_chart_data)
        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        figs_email = figs + [plots_email]
        figs_new = table.to_html(
            [table.html_text('COT - GAS', style='font-family:Calibri;', tag='h1')] + figs + [px_fig]
            + _photo_gap(1849, 'remaining figure list after + [pos...'),
            add_home=False,
        )
        figs_email.append('<a href="{:s}\\positioning\\cot_gas.html">Long Short Position Charts</a><br><br>'.format(html_path))
        table.figures_to_html(figs_new, f'{html_path}\\positioning\\cot_gas.html', task_name=report_name)
        send_email(send_to=send_to, subject='COT - GAS', body=figs_email,
                   html_path=f'{html_path}\\positioning\\cot_gas.html')


def update_pm(send_to):
    pm_dict = {'Precious Metal': None, 'GCA Comdty': 'GCA Comdty', 'SIA Comdty': 'SIA Comdty',
               'PLA Comdty': 'PLA Comdty', 'PAA Comdty': 'PAA Comdty'}
    etf_holdings = {'GCA Comdty': '.GLTOTL Index', 'SIA Comdty': 'ETSITOTL Index'}
    ccy_map = {'GCA Comdty': 'XAU Curncy', 'SIA Comdty': 'XAG Curncy'}
    cot_table = pd.DataFrame()
    figs_net = []
    figs_ls = []
    cta_dict = {}
    pos_vs_px_chart_data = {}
    cta_dict['GCA Comdty'] = rvx.rvx(ticker='CTA LN4 CM PM GC_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['SIA Comdty'] = rvx.rvx(ticker='CTA LN4 CM PM SI_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['PLA Comdty'] = rvx.rvx(ticker='CTA LN4 CM HM PL_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['PAA Comdty'] = rvx.rvx(ticker='CTA LN4 CM HM PA_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['Precious Metal'] = (cta_dict['GCA Comdty'].iloc[:, 0] + cta_dict['SIA Comdty'].iloc[:, 0]
                                   + _photo_gap(1887, 'remaining cta_dict terms and any scaling'))
    cta_dict['Precious Metal'] = cta_dict['Precious Metal'].to_frame('Total')
    for k, v in pm_dict.items():
        df_ = cftc_analysis_fut(active=k, alt_active=v, nc=True, cta=cta_dict[k].iloc[:, 0])
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=True, cta=cta_dict[k].iloc[:, 0])
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        if k in ['GCA Comdty', 'SIA Comdty']:
            start_date = pd.to_datetime(cot_table[-1:]._last_update.iloc[-1]) - relativedelta(days=7)
            end_date = pd.to_datetime(cot_table[-1:]._last_update.iloc[-1])
            net_ = cot_data['Long'] - cot_data['Short']
            last_year_loc = np.where(net_.index < dt.datetime(today().year, 1, 1))[0][-1]
            ticker = etf_holdings[k]
            ticker_ccy = ccy_map[k]
            vwap_price = cot_table.iloc[-1:]['Ref Week VWAP'].iloc[-1]
            ytd_price_chg = cot_table.iloc[-1:]['YTD price change'].iloc[-1]
            weekly_price_chg = cot_table.iloc[-1:]['Weekly Price Change'].iloc[-1]
            net_position_nc = cot_table.iloc[-1:]['Net Position (NC)'].iloc[-1]
            net_position_mm = cot_table.iloc[-1:]['Net Position (MM)'].iloc[-1]
            weekly_delta_chg_in_m = cot_table.iloc[-1:]['Weekly Delta Change in $m'].iloc[-1]
            weekly_delta_chg_lots = cot_table.iloc[-1:]['Weekly Delta Change'].iloc[-1]
            fw_chg_ = cot_table.iloc[-1:]['4w change of net position'].iloc[-1]
            ytd_chg_ = cot_table.iloc[-1:]['YTD position change'].iloc[-1]
            px_metal = bbg.bdh(ticker=[ticker_ccy], fields=['PX_LAST'], sdate=dt.datetime(2005, 1, 1), edate=today())
            vwap_etf_chart = cot.vwap(k)
            total_holdings = bbg.bdh([ticker], ['PX_LAST'], sdate=dt.datetime(2005, 1, 1), edate=today())
            total_holdings = total_holdings * px_metal.iloc[-1].values[-1]  # in millions $ per troy oz
            etf_chart_total_holdings = (total_holdings / vwap_etf_chart.iloc[-1][0]) / (100 if k == 'GCA Comdty' else 5000)
            total_holdings_lots_ = (total_holdings / vwap_price) / (100 if k == 'GCA Comdty' else 5000)
            total_holdings_lots = total_holdings_lots_.reindex(net_.index)
            total_holdings_lots_chart = total_holdings_lots_.rename(columns={'PX_LAST': 'Net'})
            total_holdings_lots_chart_ = total_holdings_lots_chart.copy().reindex(total_holdings_lots.index)
            _photo_gap(1928, 'remaining expression after (total_holdings_lots_chart.copy().reindex(total_holdings_lots.index...')
            total_holdings_lots_chart_['price'] = px_metal['PX_LAST'].reindex(total_holdings_lots.index)
            net_pos_nc = total_holdings_lots.iloc[-1][0] + net_position_nc
            net_pos_mm = total_holdings_lots.iloc[-1][0] + net_position_mm
            wk_chg = total_holdings.diff().iloc[-1][0] * 1e-6 + weekly_delta_chg_in_m  # in $m
            wk_chg_lots = total_holdings_lots.diff().iloc[-1][0] + weekly_delta_chg_lots
            ytd_chg = (total_holdings_lots.iloc[-1][0] - total_holdings_lots.iloc[last_year_loc][0]) + ytd_chg_
            fw_chg_lots = (total_holdings_lots.iloc[-1][0] - total_holdings_lots.iloc[-4][0]) + fw_chg_
            net_chg_z = (net_ + total_holdings_lots['PX_LAST']).diff().iloc[-1] / _photo_gap(1939, '(net_ + total_holdings_lots...) denominator')
            fw_chg_z = (net_ + total_holdings_lots['PX_LAST']).diff(4).iloc[-1] / _photo_gap(1940, '(net_ + total_holdings_lots...) denominator')
            fw_chg_price = px_metal['PX_LAST'].pct_change(4)
            fw_chg_price_mean = fw_chg_price.rolling(window=52).mean()
            fw_chg_price_std = fw_chg_price.rolling(window=52).std()
            fw_chg_price_z = (fw_chg_price - fw_chg_price_mean) / fw_chg_price_std
            new_data = {
                cot_table.columns[0]: 'GCA Fut,Opt,ETF' if k == 'GCA Comdty' else 'SIA Fut,Opt,ETF',
                'Net Position (NC)': net_pos_nc,
                'Net Position (MM)': net_pos_mm,
                'Weekly Price Change': weekly_price_chg,
                'Ref Week VWAP': vwap_price,
                'Weekly Delta Change': wk_chg_lots,
                'Weekly Delta Change in $m': wk_chg,
                '4w change of price': fw_chg_price.iloc[-1],
                '4w change of net position': fw_chg_lots,
                'YTD position change': ytd_chg,
                'net change z score': net_chg_z,
                '4w price change z score': fw_chg_price_z.iloc[-1],
                '4w delta change z score': fw_chg_z,
                'YTD price change': ytd_price_chg,
                '_thr_high': 0.9, '_thr_low': 0.1, '_thr_high8': 0.8, '_thr_low8': 0.2, '_z_high': 1.5, '_z_low': -1.5,
            }
            fw_price_holdings = (total_holdings * 1e-6).pct_change(4)  # in $m
            fw_price_holdings_mean = fw_price_holdings.rolling(window=52).mean()
            fw_price_holdings_std = fw_price_holdings.rolling(window=52).std()
            fw_price_holdings_z = (fw_price_holdings - fw_price_holdings_mean) / fw_price_holdings_std
            new_data_etf = {
                cot_table.columns[0]: 'GCA ETF' if k == 'GCA Comdty' else 'SIA ETF',
                'Net Position (NC)': total_holdings_lots.iloc[-1][0],
                'Net Position (MM)': total_holdings_lots.iloc[-1][0],
                'Weekly Price Change': weekly_price_chg,
                'Ref Week VWAP': vwap_price,
                'Weekly Delta Change': total_holdings_lots.diff().iloc[-1][0],
                'Weekly Delta Change in $m': total_holdings.diff().iloc[-1][0] * 1e-6,
                '4w change of price': fw_price_holdings.iloc[-1, 0],
                '4w change of net position': total_holdings_lots.iloc[-1][0] - total_holdings_lots.iloc[-4][0],
                'YTD position change': total_holdings_lots.iloc[-1][0] - total_holdings_lots.iloc[last_year_loc][0],
                'net change z score': total_holdings_lots.diff().iloc[-1, 0] / _photo_gap(1983, 'total_holdings_lots.diff().iloc... denominator'),
                '4w price change z score': fw_price_holdings_z.iloc[-1, 0],
                '4w delta change z score': total_holdings_lots.diff(4).iloc[-1, 0] / _photo_gap(1985, 'total_holdings_lots.diff... denominator'),
                'YTD price change': ytd_price_chg,
                '_thr_high': 0.9, '_thr_low': 0.1, '_thr_high8': 0.8, '_thr_low8': 0.2, '_z_high': 1.5, '_z_low': -1.5,
            }
            cot_table = pd.concat([cot_table, pd.DataFrame(new_data_etf, index=[0]), pd.DataFrame(new_data, index=[0])], ignore_index=True)
            china_holding_bbg = bbg.bdh('CNGFGOLD Index', ['PX_LAST'], sdate=dt.datetime(2015, 1, 1), edate=today())
            china_holding_bbg = china_holding_bbg * px_metal.iloc[-1].values[-1]  # in lots
            bbg_start = china_holding_bbg.index[0]
            new_idx = pd.date_range(start=dt.datetime(bbg_start.year, 1, 1), periods=len(china_holding_bbg),
                                    freq='MS')
            china_holding_bbg.index = new_idx
            china_holding = fetch_series('UKTI CN', 'GOLD', start='2015-01-01', end=today()).cumsum()
            kg_to_oz = 32.1507466
            china_holding = china_holding * kg_to_oz
            china_holding = china_holding * px_metal.iloc[-1].values[-1] * 1e-6
            china_holding_chg = china_holding.diff()
            china_holding_chg = china_holding_chg.to_frame('Monthly Change in Holdings')
            chart_total_holdings = china_holding_bbg['PX_LAST'].reindex(china_holding.index) + china_holding
        if k == 'Precious Metal':
            k_ = 'GCA Comdty'  # use gold for price vs position change chart
        else:
            k_ = k
        reg_fig_new = get_pos_vs_px_change_chart(k_, cot_data, n_weeks=1,
            title=_photo_gap(2027, 'Price vs Net position wow...'))
        reg_fig_4w_new = get_pos_vs_px_change_chart(k_, cot_data, n_weeks=4,
            title=_photo_gap(2028, 'Price vs Net position...'))
        cta = cta_dict[k]
        fig1, fig2 = gen_figures(k, cot_data, cta=cta.iloc[:, 0])
        if k in ['GCA Comdty', 'SIA Comdty', 'PLA Comdty', 'PAA Comdty']:
            single_px_figure = get_px_chart_single(k, cot_start=pd.to_datetime(
                _photo_gap(2032, 'cot_table._last_update.dropna...')))
            pos_vs_px_chart_data[k] = cot_data
            figs_net.append([fig1, single_px_figure])
        else:
            figs_net.append([fig1, ''])
        figs_ls.append(fig2)
        if k in ['GCA Comdty', 'SIA Comdty']:
            if k == 'GCA Comdty':
                fig_china = chart.line_chart(
                    df=chart_total_holdings.to_frame('BBG+UKIT\u00b9'),
                    data_p1y2=chart_total_holdings.diff().to_frame('Monthly Delta BBG+UKIT'),
                    secondary_y=True,
                    title='PBoC Gold BBG+UKIT\u00b9 Holdings',
                    y_axis_title='Gold Holdings (M$/troy oz)',
                    p1y2_axis_title='Monthly Change',
                    x_axis_title='Date', tickformat=None,
                    highlight_dict={'BBG+UKIT\u00b9': {'color': 'black', 'width': 2}, 'Monthly Delta BBG+UKIT': {'mode': 'bars'}},
                    height=500, width=800,
                )
                fig_china.update_traces(opacity=0.6, selector=dict(type='bar'))
                fig_china.update_yaxes(range=chart_total_holdings.diff().quantile([0.01, 0.99]).values, secondary_y=True)  # china repoted a lot [photo clipped]
                fig_china.update_layout(margin=dict(b=100), width=700, height=500,
                    legend=dict(orientation='h', x=0.5, y=-0.12, xanchor='center', yanchor='top'))
                fig_china.add_annotation(
                    text=_photo_gap(2076, '\u00b9Comes from UK export data of a certain size of gold bar, which is almost ex...'),
                    xref='paper', yref='paper', x=0.1, y=-0.20, xanchor='left', yanchor='top',
                    font=dict(family='Calibri', size=10), showarrow=False,
                )
            else:
                fig_china = ''
            high_dict = {
                'price': {'mode': 'lines+markers', 'color': 'black', 'width': 1, 'dash': 'dash'},
                today().year: {'mode': 'lines+markers', 'color': 'red', 'width': 2},
            }
            fig_etf = chart.seasonal_chart(
                df=etf_chart_total_holdings['PX_LAST'],  # use the non truncated data for the chart
                x_axis_title='Date', y_axis_title='Contracts',
                title=f"{'Gold' if k == 'GCA Comdty' else 'Silver'} ETF Positioning",
                ytd_cum_sum=True, vs_avg=False, freq='B', height=500, width=800, start=dt.datetime(2018, 1, 1),
            )
            px_vs_pos_chart_etf_data = etf_chart_total_holdings['PX_LAST'].reindex(cot_data.index).to_frame('Net')
            fig_etf_flows_vs_px_chg = get_pos_vs_px_change_chart(k, px_vs_pos_chart_etf_data,
                min_year=_photo_gap(2105, 'today... and any remaining chart arguments'))
            fig_etf_flows_vs_px_chg.update_layout(width=700, height=500,
                legend=dict(orientation='h', x=0.5, y=-0.12, xanchor='center', yanchor='top'), margin=dict(b=90))
            if k == 'GCA Comdty':
                to_add = (chart_total_holdings.to_frame('Net') / vwap_price) / (1000 if k == 'GCA Comdty' else _photo_gap(2119, 'else denominator'))
                to_plot = total_holdings_lots_chart_['Net'] + _photo_gap(2120, 'to_add.reindex(total_holdings_lots_chart_.index...) and remaining selection')
            else:
                to_plot = total_holdings_lots_chart_[['Net']]
            fig_position_ = chart.seasonal(
                df=to_plot, start=dt.datetime(2018, 1, 1), x_axis_title='Date', y_axis_title='Contracts',
                p1y2_axis_title='Price', data_p1y2=total_holdings_lots_chart_[['price']], seasonal_p1y2=False, freq='W-TUE',
                title=_photo_gap(2133, "{'Gold' if k == 'GCA Comdty' else 'Silver'} Fut,Opt,ETF {',PBoC' if k == 'GCA Comdty'..."),
                dropna_all=True, ex2020=False, secondary_y=True, height=500, width=800, highlight_dict=high_dict,
            )
            fig_position_.update_xaxes(title='Date', dtick='M1', tickformat='%b')
            figs_etf = [fig_position_, fig_etf, fig_china, fig_etf_flows_vs_px_chg]
            figs_etf_formatted = table.figs_to_grid(figs_etf, columns=3)
            figs_ls.append(figs_etf_formatted)
        figs_reg = []
        figs_reg.append(fig2)
        figs_reg.append(table.figs_to_grid([reg_fig_new, reg_fig_4w_new], columns=2))
        table.to_html(figs_reg, f'{html_path}\\positioning\\links\\{k}_chart.html')
        cot_table.loc[(cot_table[cot_table.columns[0]] == df_.iloc[0, 0]), cot_table.columns[0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
    if not cot_table.iloc[:, 1].isnull().values.any():
        figs = []
        output_html_table = table.html_format(
            df=cot_table,
            header='Speculators Net Position (Managed money)',
            footer=None,
            show_date=False,
            format_column={
                '0': {'width': '120px', 'text-align': 'left', 'highlight': [0, 'net pos rank', '_thr_high', '_thr_low'], 'right_border': True},
                '1': {'width': '60px', 'text-align': 'center'},
                '2': {'width': '60px', 'text-align': 'center'},
                '3': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [3, 'net/oi pct rank', '_thr_high', '_thr_low']},
                '4': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'bold': True, 'highlight': [4, '_price_chg', '_thr_high', '_thr_low']},
                '5': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}', 'right_border': True},
                '6': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '7': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [7, 'net change z score', '_z_high', '_z_low']},
                '8': {'width': '60px', 'text-align': 'center'},
                '9': {'width': '60px', 'text-align': 'center'},
                '10': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '11': {'width': '60px', 'text-align': 'center', 'bold': True, 'format': '{:.1%}', 'highlight': [11, '4w price change z score', '_z_high', '_z_low']},
                '12': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [12, '4w delta change z score', '_z_high', '_z_low']},
                '13': {'width': '60px', 'text-align': 'center'},
                '14': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '15': {'width': '80px', 'text-align': 'center'},
                '16': {'width': '60px', 'text-align': 'center'},
                '17': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '18': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [17, '_thr_net']},
                '19': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [18, '_thr_net']},
                '20': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [19, '_thr_high8', '_thr_low8']},
                '21': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [20, '_thr_high8', '_thr_low8'], 'right_border': True},
                '22': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '23': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '24': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            },
            format_row={'1': {'bottom_border': True}, '5': {'bottom_border': True}, '9': {'bottom_border': True}, '11': {'bottom_border': True}},
            precision=0,
            hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
            inline=False,
            background_color='lightblue',
            na_rep='-',
        )
        cot_start = pd.to_datetime(cot_table._last_update.dropna().max()) - relativedelta(days=7)
        px_chart = get_px_chart(name='PM', cot_start=cot_start)
        pos_chart = get_pos_chart(name='PM', data_dict=pos_vs_px_chart_data)
        figs.append(output_html_table)
        razed_plots_email = list(itertools.chain.from_iterable(figs_net))
        plots_email = table.figs_to_grid(razed_plots_email, columns=2, email=True)
        figs_email = figs + [plots_email]
        figs_new = table.to_html(
            [table.html_text('COT - PM', style='font-family:Calibri;', tag='h1')] + figs + [px_chart]
            + _photo_gap(2277, 'remaining figure list after + [po...'),
            add_home=False,
        )
        figs_email.append('<a href="{:s}\\positioning\\cot_pm.html">Long Short Position Charts</a><br><br>'.format(html_path))
        table.figures_to_html(figs_new, f'{html_path}\\positioning\\cot_pm.html', task_name=report_name)
        send_email(send_to=send_to, subject='COT - PM', body=figs_email,
                   html_path=f'{html_path}\\positioning\\cot_pm.html')


def gen_figures(k, cot_data, cta=None, price_override_name=None):
    if cta is not None and not cta.empty:
        cta_index = cot_data.loc[cot_data.index >= dt.datetime(cot_data['Long'].last_valid_index().year, 1, 1)].index
        cta = cta.reindex(cta_index)
        cot_data = cot_data.join(cta.to_frame('CTA LN4'))
        fig1 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=['Net', 'PX_LAST', 'Net OI', 'CTA LN4'],
            freq='W-TUE',
            titles=f'{k} Net Position vs Price',
            ex2020=False,
            price_override_name=price_override_name,
        )
        fig2 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=[
                ['Net', 'PX_LAST', 'Net OI', 'CTA LN4'],
                ['Long', 'PX_LAST', 'Long OI', 'CTA LN4'],
                ['Short', 'PX_LAST', 'Short OI', 'CTA LN4'],
            ],
            freq='W-TUE',
            titles=[f'{k} Net Position vs Price', f'{k} Long Position vs Price', f'{k} Short Position vs Price'],
            title=f'{k} MM',
            ex2020=False,
            price_override_name=price_override_name,
        )
    else:
        fig1 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=['Net', 'PX_LAST', 'Net OI'],
            freq='W-TUE',
            title=f'{k} Net Position vs Price',
            ex2020=False,
            price_override_name=price_override_name,
        )
        fig2 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=[['Net', 'PX_LAST', 'Net OI'], ['Long', 'PX_LAST', 'Long OI'], ['Short', 'PX_LAST', 'Short OI']],
            freq='W-TUE',
            titles=[f'{k} Net Position vs Price', f'{k} Long Position vs Price', f'{k} Short Position vs Price'],
            title=f'{k} MM',
            ex2020=False,
            price_override_name=price_override_name,
        )
    return fig1, fig2


def regression_chart(data, title):
    """first column in data is y, 2nd is x"""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=data.iloc[:, 1], y=data.iloc[:, 0], text=data.index.strftime('%d/%b/%Y'),
                   opacity=0.8, showlegend=True, mode='markers', name='last 2 years')
    )
    fig.add_trace(
        go.Scatter(x=data.iloc[-8:, 1], y=data.iloc[-8:, 0], text=data.index.strftime('%d/%b/%Y'),
                   opacity=0.8, showlegend=True, mode='markers', name='last 8 weeks',
                   marker=dict(color='black', size=12))
    )
    fig.add_trace(
        go.Scatter(x=data.iloc[-1:, 1], y=data.iloc[-1:, 0], text=data.index.strftime('%d/%b/%Y'),
                   opacity=0.8, showlegend=True, mode='markers', name='latest change',
                   marker=dict(color='red', size=12))
    )
    lm = sm.OLS(data.iloc[:, 0], data.iloc[:, 1]).fit()
    y_fit = data.iloc[:, 1] * lm.params.values
    fig.add_trace(
        go.Scatter(x=data.iloc[:, 1], y=y_fit, opacity=0.8, showlegend=True, mode='lines',
                   name='fit', marker=dict(color='grey', size=2))
    )
    fig.add_trace(
        go.Scatter(x=data.iloc[:, 1], y=y_fit + 2 * lm.scale ** 0.5, mode='lines', name='+2sd', line=dict(color='grey', width=2, dash='dash'))
    )
    fig.add_trace(
        go.Scatter(x=data.iloc[:, 1], y=y_fit - 2 * lm.scale ** 0.5, mode='lines', name='-2sd', line=dict(color='grey', width=2, dash='dash'))
    )
    fig.update_traces(hovertemplate='date: %{text} <br>x: %{x} <br>y: %{y}')
    fig.update_layout(title={'text': title, 'x': 0.5, 'xanchor': 'center'},
                      xaxis_title='Net position change', yaxis_title='Price change', width=900, height=600)
    return fig


def update_cme(send_to, update=True):
    oil_dict = {'Crude': None, 'CLA Comdty': None, 'COA Comdty': None, 'Product': None,
                'QSA Comdty': None, 'HOA Comdty': None, 'XBA Comdty': None}
    gas_dict = {'NG CME+ICE': 'NGA Comdty', 'NGA Comdty': None, 'NG ICE Henry Hub': 'NGA Comdty',
                'NG ICE Swap Dealers': 'NGA Comdty'}
    other_dict = {'GCA Comdty': None, 'SIA Comdty': None, 'PLA Comdty': None, 'PAA Comdty': None,
                  'HGA Comdty': None, 'S A Comdty': None, 'SMA Comdty': None, 'BOA Comdty': None,
                  'C A Comdty': None, 'W A Comdty': None, 'SBA Comdty': None, 'CTA Comdty': None,
                  'KCA Comdty': None, 'CCA Comdty': None}
    cta_map_other = {
        'GCA Comdty': 'CTA LN4 CM PM GC_Comdty',
        'SIA Comdty': 'CTA LN4 CM PM SI_Comdty',
        'PLA Comdty': 'CTA LN4 CM HM PL_COMDTY',
        'PAA Comdty': 'CTA LN4 CM HM PA_COMDTY',
        'S A Comdty': 'CTA LN4 CM GR S__Comdty',
        'BOA Comdty': 'CTA LN4 CM GR BO_COMDTY',
        'C A Comdty': 'CTA LN4 CM GR C__COMDTY',
        'W A Comdty': 'CTA LN4 CM GR W__COMDTY',
        'SBA Comdty': 'CTA LN4 CM SO SB_Comdty',
        'CTA Comdty': 'CTA LN4 CM SO CT_Comdty',
        'KCA Comdty': 'CTA LN4 CM SO KC_Comdty',
        'CCA Comdty': 'CTA LN4 CM SO CC_Comdty',
    }
    cot_table = pd.DataFrame()
    figs_net = []
    figs_ls = []
    chart_links = {}
    cta_dict = {}
    cta_dict['GCA Comdty'] = rvx.rvx(ticker='CTA LN4 CM PM GC_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['SIA Comdty'] = rvx.rvx(ticker='CTA LN4 CM PM SI_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['PLA Comdty'] = rvx.rvx(ticker='CTA LN4 CM HM PL_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['PAA Comdty'] = rvx.rvx(ticker='CTA LN4 CM HM PA_COMDTY', field='SIGNAL', sdate=f'2023-01-01', edate=today())
    cta_dict['Precious Metal'] = (cta_dict['GCA Comdty'].iloc[:, 0] + cta_dict['SIA Comdty'].iloc[:, 0]
                                   + _photo_gap(2498, 'remaining cta_dict terms and any scaling'))
    cta_dict['Precious Metal'] = cta_dict['Precious Metal'].to_frame('Total')
    for k, v in oil_dict.items():
        cta = get_cta_oil(k)
        if k in ['COA Comdty', 'QSA Comdty', 'Crude', 'Product']:
            df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=False, update=update)
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
        else:
            df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=True, update=update)
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
        fig_net, fig_ls = gen_figures(k, cot_data, cta)
        figs_net.append(fig_net)
        figs_ls.append(fig_ls)
        table.to_html([fig_ls], f'{html_path}\\positioning\\links\\{k}_chart.html')
    for k, v in gas_dict.items():
        cta = rvx.rvx(ticker='CTA LN4 CM EN NG_COMDTY', field='SIGNAL', sdate='2023-01-01', edate=today())
        if k not in ['GKA Options']:
            if k in ['NG ICE Swap Dealers']:
                df_, cot_data = cftc_analysis_fut_dealer(active=k, alt_active=v, nc=False, cta=cta.iloc[:, 0])
            else:
                df_1 = cftc_analysis_fut(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0])
                df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=True, update=update)
            cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
            chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
        fig_net, fig_ls = gen_figures(k, cot_data, cta.iloc[:, 0])
        figs_net.append(fig_net)
        figs_ls.append(fig_ls)
        table.to_html([fig_ls], f'{html_path}\\positioning\\links\\{k}_chart.html')
    for k, v in other_dict.items():
        cta = cta_dict.get(k)
        if cta is None:
            cta_ticker = cta_map_other.get(k, f"CTA LN4 CM EN {k.split('A Comdty')[0]}_COMDTY")
            cta = rvx.rvx(ticker=cta_ticker, field='SIGNAL', sdate=f'2023-01-01', edate=today())
        df_1 = cftc_analysis_fut(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0], update=update)
        cot_table = pd.concat([cot_table, df_1], axis=0, ignore_index=True)
        df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0], update=update)
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        reg_data = pd.DataFrame()
        reg_data['price chg'] = cot_data['PX_LAST'].diff() / cot_data['PX_LAST'].shift(1)
        reg_data['net chg'] = cot_data['Net'].diff()
        reg_fig, lm = chart.regression_chart(
            data=reg_data.iloc[-104:, :], title=f'Price vs Net position change - {k}',
            xaxis_title='Net position change', yaxis_title='Price change',
        )
        reg_str = _photo_gap(2551, "<p style='font-family:Calibri'>Beta (price chg in % for 10k net position chg): {lm.para...")
        fig_net, fig_ls = gen_figures(k, cot_data, cta.iloc[:, 0])
        table.to_html([fig_ls, reg_fig, reg_str], f'{html_path}\\positioning\\links\\{k}_chart.html')
        figs_net.append(fig_net)
        figs_ls.append(fig_ls)
        chart_links[df_.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>'
        chart_links[df_1.iloc[0, 0]] = f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_1.iloc[0, 0]}</a>'
    if cot_table.columns[1] != 'Net Position (NC)':
        new_cols = [cot_table.columns[0], cot_table.columns[-1]] + list(cot_table.columns[1:-1])
        cot_table = cot_table[new_cols]
    if not cot_table.iloc[:, 0].isnull().values.any():
        figs = []
        figs_all = []
        position_change = cot.position_change(cot_table, thr=1.5)
        if not position_change.empty:
            position_change_idx = cot_table.loc[cot_table.iloc[:, 0].isin(position_change.iloc[:, 0]), :].index
        position_diverge = cot.position_divergence(cot_table)
        if not position_diverge.empty:
            position_diverge_idx = cot_table.loc[cot_table.iloc[:, 0].isin(position_diverge.iloc[:, 0]), :].index
        format_column = {
                '0': {'width': '120px', 'text-align': 'left', 'highlight': [0, 'net pos rank', '_thr_high', '_thr_low'], 'right_border': True},
                '1': {'width': '60px', 'text-align': 'center'},
                '2': {'width': '60px', 'text-align': 'center'},
                '3': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [3, 'net/oi pct rank', '_thr_high', '_thr_low']},
                '4': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'bold': True, 'highlight': [4, '_price_chg', '_thr_high', '_thr_low']},
                '5': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}', 'right_border': True},
                '6': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '7': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [7, 'net change z score', '_z_high', '_z_low']},
                '8': {'width': '60px', 'text-align': 'center'},
                '9': {'width': '60px', 'text-align': 'center'},
                '10': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '11': {'width': '60px', 'text-align': 'center', 'bold': True, 'format': '{:.1%}', 'highlight': [11, '4w price change z score', '_z_high', '_z_low']},
                '12': {'width': '60px', 'text-align': 'center', 'highlight': [11, '4w delta change z score', '_z_high', '_z_low']},
                '13': {'width': '60px', 'text-align': 'center'},
                '14': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '15': {'width': '80px', 'text-align': 'center'},
                '16': {'width': '60px', 'text-align': 'center'},
                '17': {'width': '60px', 'text-align': 'center', 'right_border': True},
                '18': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [17, '_thr_net']},
                '19': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [18, '_thr_net']},
                '20': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [19, '_thr_high8', '_thr_low8']},
                '21': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [20, '_thr_high8', '_thr_low8'], 'right_border': True},
                '22': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '23': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
                '24': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
        }
        if not position_change.empty:
            output_html_table1 = table.html_format(
                df=position_change,
                header='Weekly or 4w position change more than 1.5 zscore (4y window)',
                footer=None, show_date=False, format_column=format_column, format_row=None, precision=0,
                hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
                inline=False, background_color='lightblue', na_rep='-',
            )
            for i in position_change_idx:
                output_html_table1 = output_html_table1.replace(cot_table.iloc[i, 0], chart_links[cot_table.iloc[i, 0]])
        else:
            output_html_table1 = table.html_text(
                'No position change more than 1.5 zscore (4y window)', style='font-family:Calibri;', tag='h2'
            )
        figs.append(output_html_table1)
        if not position_diverge.empty:
            output_html_table2 = table.html_format(
                df=position_diverge, header='Weekly position change diverges from price change',
                footer=None, show_date=False, format_column=format_column, format_row=None, precision=0,
                hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
                inline=False, background_color='lightblue', na_rep='-',
            )
            for i in position_diverge_idx:
                output_html_table2 = output_html_table2.replace(cot_table.iloc[i, 0], chart_links[cot_table.iloc[i, 0]])
        else:
            output_html_table2 = table.html_text(
                'No diverges from price change', style='font-family:Calibri;', tag='h2'
            )
        figs.append(output_html_table2)
        output_html_table = table.html_format(
            df=cot_table, header='Speculators Net Position', footer=None, show_date=False,
            format_column=format_column,
            format_row={
                '2': {'bottom_border': True}, '6': {'bottom_border': True}, '10': {'bottom_border': True},
                '12': {'bottom_border': True}, '14': {'bottom_border': True}, '16': {'bottom_border': True},
                '18': {'bottom_border': True}, '20': {'bottom_border': True}, '22': {'bottom_border': True},
                '24': {'bottom_border': True}, '26': {'bottom_border': True}, '28': {'bottom_border': True},
                '30': {'bottom_border': True}, '32': {'bottom_border': True}, '34': {'bottom_border': True},
                '36': {'bottom_border': True},
            },
            precision=0,
            hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
            inline=False, background_color='lightblue', na_rep='-',
        )
        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        figs_all.append(output_html_table)
        table.figures_to_html(figs_all, f'{html_path}\\positioning\\links\\cot_table_cme.html', task_name=report_name)
        table.figures_to_html(
            table.to_html(figs_ls, add_home=False),
            f'{html_path}\\positioning\\links\\position_cme.html', task_name=report_name,
        )
        figs.append('<a href="{:s}\\positioning\\links\\cot_table_cme.html">Full Cot Table</a><br>'.format(html_path))
        figs.append('<a href="{:s}\\positioning\\links\\position_cme.html">Position Charts</a><br><br>'.format(html_path))
        figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
        table.figures_to_html(
            [table.html_text('COT Alert', style='font-family:Calibri;', tag='h1'), '<div style=font-family:Calibri; >'] + figs,
            f'{html_path}\\positioning\\cot_cme.html', task_name=report_name,
        )
        send_email(send_to=send_to, subject='COT - CMD ALERT', body=figs,
                   html_path=f'{html_path}\\positioning\\cot_cme.html')


def update():
    db = partial(mongo_table, table='cot', pk=['ticker', 'active', 'item'], db='data', url=url)
    old = pyg.get_data(db, active='CLA Comdty', item='MMLFO')
    new = bbg.bdh('CFCDQMML Index', ['PX_LAST'], sdate=today() - dt.timedelta(180), edate=today())
    if old.index[-1] < new.index[-1]:
        cot_data_module.update_cme()
        update_oil(send_to=config.oil_group)
        update_oil_dealers(send_to=config.oil_group)
        update_gas(send_to=config.gas_group)
        update_pm(send_to=config.macro_group)
        update_cme(send_to=config.macro_group)
        cot_macro.update()


if __name__ == '__main__':
    update()
