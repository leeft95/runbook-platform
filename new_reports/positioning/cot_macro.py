import pandas as pd
import datetime as dt
from ecm.cmds.config import root_path
import sys
import os

os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = "C:\\local\\certs\root.crt"
os.environ["REQUESTS_CA_BUNDLE"] = "C:\\local\\certs\root.crt"
os.environ["SSL_CERT_FILE"] = "C:\\local\\certs\root.crt"
sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")
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

send_to = ["rzhao@elementcapital.com"]
report_name = "COT - FRIDAY"
file_name = "cot_cme"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\positioning\\{file_name}.py"
chart_sdate = dt.datetime(2018, 1, 1)
cal_period = "3n"

cot_dict = {
    'ESA Index': {
        'AMLF': 'TFF1NAIL Index', 'AMSF': 'TFF1NAIS Index',
        'AMLFO': 'TFC1NAIL Index', 'AMSFO': 'TFC1NAIS Index',
        'LFLF': 'TFF1NLFL Index', 'LFSF': 'TFF1NLFS Index',
        'LFLFO': 'TFC1NLFL Index', 'LFSFO': 'TFC1NLFS Index',
        'OIFO': 'IMMTEOIN Index', 'OIF': 'IMM0EOIN Index',
        'NCLF': 'IMM0ENCL Index', 'NCSF': 'IMM0ENCS Index',
        'NCLFO': 'IMMTENCL Index', 'NCSFO': 'IMMTENCS Index',
    },
    'NQA Index': {
        'AMLF': 'TFF1RAIL Index', 'AMSF': 'TFF1RAIS Index',
        'AMLFO': 'TFC1RAIL Index', 'AMSFO': 'TFC1RAIS Index',
        'LFLF': 'TFF1RLFL Index', 'LFSF': 'TFF1RLFS Index',
        'LFLFO': 'TFC1RLFL Index', 'LFSFO': 'TFC1RLFS Index',
        'OIFO': 'IMMPNOIN Index', 'OIF': 'IMM3NOIN Index',
        'NCLF': 'IMM3NNCL Index', 'NCSF': 'IMM3NNCS Index',
        'NCLFO': 'IMMPNNCL Index', 'NCSFO': 'IMMPNNCS Index',
    },
    'RTYA Index': {
        'AMLF': 'TFF2TAIL Index', 'AMSF': 'TFF2TAIS Index',
        'AMLFO': 'TFC2TAIL Index', 'AMSFO': 'TFC2TAIS Index',
        'LFLF': 'TFF2TLFL Index', 'LFSF': 'TFF2TLFS Index',
        'LFLFO': 'TFC2TLFL Index', 'LFSFO': 'TFC2TLFS Index',
        'OIFO': 'CFC6TOIN Index', 'OIF': 'CFF6TOIN Index',
        'NCLF': 'CFF6TNCL Index', 'NCSF': 'CFF6TNCS Index',
        'NCLFO': 'CFC6TNCL Index', 'NCSFO': 'CFC6TNCS Index',
    },
    'UXA Index': {
        'AMLF': 'TFF2OAIL Index', 'AMSF': 'TFF2OAIS Index',
        'AMLFO': 'TFC2OAIL Index', 'AMSFO': 'TFC2OAIS Index',
        'LFLF': 'TFF2OLFL Index', 'LFSF': 'TFF2OLFS Index',
        'LFLFO': 'TFC2OLFL Index', 'LFSFO': 'TFC2OLFS Index',
        'OIFO': 'CVXCTOIN Index', 'OIF': 'CVXFTOIN Index',
        'NCLF': 'CVXFTNCL Index', 'NCSF': 'CVXFTNCS Index',
        'NCLFO': 'CVXCTNCL Index', 'NCSFO': 'CVXCTNCS Index',
    },
    'TUA Comdty': {
        'AMLF': 'TFF2GAIL Index', 'AMSF': 'TFF2GAIS Index',
        'AMLFO': 'TFC2GAIL Index', 'AMSFO': 'TFC2GAIS Index',
        'LFLF': 'TFF2GLFL Index', 'LFSF': 'TFF2GLFS Index',
        'LFLFO': 'TFC2GLFL Index', 'LFSFO': 'TFC2GLFS Index',
        'OIFO': 'CBTO2OIN Index', 'OIF': 'CBT42OIN Index',
        'NCLF': 'CBT42NCL Index', 'NCSF': 'CBT42NCS Index',
        'NCLFO': 'CBTO2NCL Index', 'NCSFO': 'CBTO2NCS Index',
    },
    'TYA Comdty': {
        'AMLF': 'TFF2HAIL Index', 'AMSF': 'TFF2HAIS Index',
        'AMLFO': 'TFC2HAIL Index', 'AMSFO': 'TFC2HAIS Index',
        'LFLF': 'TFF2HLFL Index', 'LFSF': 'TFF2HLFS Index',
        'LFLFO': 'TFC2HLFL Index', 'LFSFO': 'TFC2HLFS Index',
        'OIFO': 'CBTPTOIN Index', 'OIF': 'CBT4TOIN Index',
        'NCLF': 'CBT4TNCL Index', 'NCSF': 'CBT4TNCS Index',
        'NCLFO': 'CBTPTNCL Index', 'NCSFO': 'CBTPTNCS Index',
    },
    'ECA Curncy': {
        'AMLF': 'TFF1EAIL Index', 'AMSF': 'TFF1EAIS Index',
        'AMLFO': 'TFC1EAIL Index', 'AMSFO': 'TFC1EAIS Index',
        'LFLF': 'TFF1ELFL Index', 'LFSF': 'TFF1ELFS Index',
        'LFLFO': 'TFC1ELFL Index', 'LFSFO': 'TFC1ELFS Index',
        'OIFO': 'IMMPFOIN Index', 'OIF': 'IMMBEOIN Index',
        'NCLF': 'IMMBENCL Index', 'NCSF': 'IMMBENCS Index',
        'NCLFO': 'IMMPFNCL Index', 'NCSFO': 'IMMPFNCS Index',
    },
    'ADA Curncy': {
        'AMLF': 'TFF1FAIL Index', 'AMSF': 'TFF1FAIS Index',
        'AMLFO': 'TFC1FAIL Index', 'AMSFO': 'TFC1FAIS Index',
        'LFLF': 'TFF1FLFL Index', 'LFSF': 'TFF1FLFS Index',
        'LFLFO': 'TFC1FLFL Index', 'LFSFO': 'TFC1FLFS Index',
        'OIFO': 'IMM0AOIN Index', 'OIF': 'IMM6AOIN Index',
        'NCLF': 'IMM6ANCL Index', 'NCSF': 'IMM6ANCS Index',
        'NCLFO': 'IMM0ANCL Index', 'NCSFO': 'IMM0ANCS Index',
    },
    'JYA Curncy': {
        'AMLF': 'TFF1DAIL Index', 'AMSF': 'TFF1DAIS Index',
        'AMLFO': 'TFC1DAIL Index', 'AMSFO': 'TFC1DAIS Index',
        'LFLF': 'TFF1DLFL Index', 'LFSF': 'TFF1DLFS Index',
        'LFLFO': 'TFC1DLFL Index', 'LFSFO': 'TFC1DLFS Index',
        'OIFO': 'IMM0JOIN Index', 'OIF': 'IMM5JOIN Index',
        'NCLF': 'IMM5JNCL Index', 'NCSF': 'IMM5JNCS Index',
        'NCLFO': 'IMM0JNCL Index', 'NCSFO': 'IMM0JNCS Index',
    },
    'CDA Curncy': {
        'AMLF': 'TFF1AAIL Index', 'AMSF': 'TFF1AAIS Index',
        'AMLFO': 'TFC1AAIL Index', 'AMSFO': 'TFC1AAIS Index',
        'LFLF': 'TFF1ALFL Index', 'LFSF': 'TFF1ALFS Index',
        'LFLFO': 'TFC1ALFL Index', 'LFSFO': 'TFC1ALFS Index',
        'OIFO': 'IMM0COIN Index', 'OIF': 'IMM3COIN Index',
        'NCLF': 'IMM3CNCL Index', 'NCSF': 'IMM3CNCS Index',
        'NCLFO': 'IMM0CNCL Index', 'NCSFO': 'IMM0CNCS Index',
    },
    'DXA Curncy': {
        'AMLF': 'TFF2NAIL Index', 'AMSF': 'TFF2NAIS Index',
        'AMLFO': 'TFC2NAIL Index', 'AMSFO': 'TFC2NAIS Index',
        'LFLF': 'TFF2NLFL Index', 'LFSF': 'TFF2NLFS Index',
        'LFLFO': 'TFC2NLFL Index', 'LFSFO': 'TFC2NLFS Index',
        'OIFO': 'NYCOUOIN Index', 'OIF': 'NYC2UOIN Index',
        'NCLF': 'NYC2UNCL Index', 'NCSF': 'NYC2UNCS Index',
        'NCLFO': 'NYCOUNCL Index', 'NCSFO': 'NYCOUNCS Index',
    },
    'BTCA Curncy': {
        'AMLF': 'TFF2RAIL Index', 'AMSF': 'TFF2RAIS Index',
        'AMLFO': 'TFC2RAIL Index', 'AMSFO': 'TFC2RAIS Index',
        'LFLF': 'TFF2RLFL Index', 'LFSF': 'TFF2RLFS Index',
        'LFLFO': 'TFC2RLFL Index', 'LFSFO': 'TFC2RLFS Index',
        'OIFO': 'CFC5ROIN Index', 'OIF': 'CFF5ROIN Index',
        'NCLF': 'CFF5RNCL Index', 'NCSF': 'CFF5RNCS Index',
        'NCLFO': 'CFC5RNCL Index', 'NCSFO': 'CFC5RNCS Index',
    },
    'DCRA Curncy': {
        'AMLF': 'TFF3NAIL Index', 'AMSF': 'TFF3NAIS Index',
        'AMLFO': 'TFC3NAIL Index', 'AMSFO': 'TFC3NAIS Index',
        'LFLF': 'TFF3NLFL Index', 'LFSF': 'TFF3NLFS Index',
        'LFLFO': 'TFC3NLFL Index', 'LFSFO': 'TFC3NLFS Index',
        'OIFO': 'CC20NOIN Index', 'OIF': 'CF20NOIN Index',
        'NCLF': 'CF20NNCL Index', 'NCSF': 'CF20NNCS Index',
        'NCLFO': 'CC20NNCL Index', 'NCSFO': 'CC20NNCS Index',
    },
}


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 19, 30, 0),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=10),
        repetition_duration=dt.timedelta(hours=2),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


def create_raw_data():
    for k, v in cot_dict.items():
        for k1, v1 in v.items():
            cot.cot_cell(ticker=v1, active=k, item=k1, period=cal_period)


def create_total_crude():
    """Total Crude = ICE Brent + ICE WTI + NYMEX WTI + NYMEX Brent"""
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO']
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
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO']
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
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO']
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
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    item_list = ['MMLF', 'MMSF', 'MMLFO', 'MMSFO', 'OIF', 'OIFO']
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
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
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
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
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
            active='NatGas',
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
            active='NatGas',
            ticker=None,
            db=db,
            period=cal_period,
        )
        c.go()


def vwap(active):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    try:
        c = pyg.get_cell(db, active=active, item="VWAP")
        db().inc(_id=c._id).drop()
    except:
        pass
    c = periodic_cell(
        function=cot.vwap,
        active=active,
        item="VWAP",
        ticker=active,
        db=db,
        period=cal_period,
    )
    c.go()


def all_vwaps():
    for k in cot_dict.keys():
        vwap(k)


def cftc_analysis_fut(active, alt_active, nc=True, cta=None, update=True):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    btc1 = pyg.get_cell(db, active=active, item="AMLF")
    btc2 = pyg.get_cell(db, active=active, item="AMSF")
    btc3 = pyg.get_cell(db, active=active, item="LFLF")
    btc4 = pyg.get_cell(db, active=active, item="LFSF")
    btc1.go()
    btc2.go()
    btc3.go()
    btc4.go()
    long = btc1.load().data + btc3.load().data
    short = btc2.load().data + btc4.load().data
    if nc:
        c1_ = pyg.get_cell(db, active=active, item="NCLF")
        c2_ = pyg.get_cell(db, active=active, item="NCSF")
        c1_.go()
        c2_.go()
        long1 = c1_.load().data
        short1 = c2_.load().data
    if update:
        c3 = pyg.get_cell(db, active=active, item="OIF").go()
    else:
        c3 = pyg.get_cell(db, active=active, item="OIF")
    if alt_active is not None:
        if update:
            c4 = pyg.get_cell(db, active=alt_active, item="VWAP").go()
        else:
            c4 = pyg.get_cell(db, active=alt_active, item="VWAP")
        ref = pyg.get_data("contracts", active=alt_active, item="ref")
    else:
        if update:
            try:
                c4 = pyg.get_cell(db, active=active, item="VWAP").go()
            except:
                c4 = pyg.get_cell(db, active=active, item="VWAP")
        else:
            c4 = pyg.get_cell(db, active=active, item="VWAP")
        ref = pyg.get_data("contracts", active=active, item="ref")
    oi = c3.load().data
    vp = c4.load().data
    if vp.index[-1] < long.index[-1]:
        vp = vp.reindex(pd.bdate_range(vp.index[0], long.index[-1]))
    vp.fillna(method="ffill", inplace=True)
    if cta is not None:
        cta = cta.reindex(long.index)
    if nc:
        df_ = cot.analysis(active=active, type="Fut", vwap=vp, ref=ref, long=long, short=short, oi=oi, long1=long1,
                           short1=short1, cta=cta)
    else:
        df_ = cot.analysis(active=active, type="Fut", vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
    return df_


def cftc_analysis_fut_opt(active, alt_active, nc=True, cta=None, update=True):
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    btc1 = pyg.get_cell(db, active=active, item="AMLFO")
    btc2 = pyg.get_cell(db, active=active, item="AMSFO")
    btc3 = pyg.get_cell(db, active=active, item="LFLFO")
    btc4 = pyg.get_cell(db, active=active, item="LFSFO")
    btc1.go()
    btc2.go()
    btc3.go()
    btc4.go()
    long = btc1.load().data + btc3.load().data
    short = btc2.load().data + btc4.load().data
    if nc:
        c1_ = pyg.get_cell(db, active=active, item="NCLFO")
        c2_ = pyg.get_cell(db, active=active, item="NCSFO")
        c1_.go()
        c2_.go()
        long1 = c1_.load().data
        short1 = c2_.load().data
    if update:
        c3 = pyg.get_cell(db, active=active, item="OIFO").go()
    else:
        c3 = pyg.get_cell(db, active=active, item="OIFO")
    if alt_active is not None:
        if update:
            c4 = pyg.get_cell(db, active=alt_active, item="VWAP").go()
        else:
            c4 = pyg.get_cell(db, active=alt_active, item="VWAP")
        ref = pyg.get_data("contracts", active=alt_active, item="ref")
    else:
        if update:
            try:
                c4 = pyg.get_cell(db, active=active, item="VWAP").go()
            except:
                c4 = pyg.get_cell(db, active=active, item="VWAP")
        else:
            c4 = pyg.get_cell(db, active=active, item="VWAP")
        ref = pyg.get_data("contracts", active=active, item="ref")
    oi = c3.load().data
    vp = c4.load().data
    vp.fillna(method="ffill", inplace=True)
    if cta is not None:
        cta = cta.reindex(long.index)
    if nc:
        df_ = cot.analysis(active=active, type="Fut,Opt", vwap=vp, ref=ref, long=long, short=short, oi=oi, long1=long1,
                           short1=short1, cta=cta)
    else:
        df_ = cot.analysis(active=active, type="Fut,Opt", vwap=vp, ref=ref, long=long, short=short, oi=oi, cta=cta)
    cot_data = ts.concat(dfs=[long, short, oi], axis=1, ignore_index=False, df_index=long.index,
                         columns=["Long", "Short", "OI"])
    cot_data["Net"] = cot_data["Long"] - cot_data["Short"]
    cot_data["Long OI"] = cot_data["Long"] / cot_data["OI"]
    cot_data["Short OI"] = cot_data["Short"] / cot_data["OI"]
    cot_data["Net OI"] = cot_data["Net"] / cot_data["OI"]
    dts = pd.bdate_range(vp.index[0], vp.index[-1])
    vp_ = vp.reindex(dts, method="ffill")
    cot_data["PX_LAST"] = vp_["VWAP"]
    cot_data["PX_LAST_1"] = vp_["PX_LAST"]
    return df_, cot_data


def gen_figures(k, cot_data, cta=None):
    if cta is not None and not cta.empty:
        cta_index = cot_data.loc[cot_data.index >= dt.datetime(cot_data["Long"].last_valid_index().year, 1, 1), :].index
        cta = cta.reindex(cta_index)
        cot_data = cot_data.join(cta.to_frame("CTA LN4"))
        fig1 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=["Net", "PX_LAST", "Net OI", "CTA LN4"],
            freq="W-TUE",
            titles=f"{k} Net Position vs Price",
            ex2020=False
        )
        fig2 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=[["Net", "PX_LAST", "Net OI", "CTA LN4"], ["Long", "PX_LAST", "Long OI", "CTA LN4"],
                     ["Short", "PX_LAST", "Short OI", "CTA LN4"]],
            freq="W-TUE",
            titles=[f"{k} Net Position vs Price", f"{k} Long Position vs Price", f"{k} Short Position vs Price"],
            title=f"{k} CTA",
            ex2020=False
        )
    else:
        fig1 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=["Net", "PX_LAST", "Net OI"],
            freq="W-TUE",
            title=f"{k} Net Position vs Price",
            ex2020=False
        )
        fig2 = chart.cot_chart_new(
            df=cot_data,
            start=dt.datetime(2018, 1, 1),
            columns=[["Net", "PX_LAST", "Net OI"], ["Long", "PX_LAST", "Long OI"], ["Short", "PX_LAST", "Short OI"]],
            freq="W-TUE",
            titles=[f"{k} Net Position vs Price", f"{k} Long Position vs Price", f"{k} Short Position vs Price"],
            title=f"{k} CTA",
            ex2020=False
        )
    return fig1, fig2  # [fig1, fig2]


def update_macro(send_to, update=True):
    other_dict = {
        'ESA Index': None,
        'NQA Index': None,
        'RTYA Index': None,
        'UXA Index': None,
        'TUA Comdty': None,
        'TYA Comdty': None,
        'ECA Curncy': None,
        'ADA Curncy': None,
        'JYA Curncy': None,
        'CDA Curncy': None,
        'DXA Curncy': None,
        'BTCA Curncy': None,
        'DCRA Curncy': None,
    }
    cta_map_other = {
        'ESA Index': 'CTA LN4 EQ DM ES_INDEX',
        'NQA Index': 'CTA LN4 EQ DM NQ_INDEX',
        'RTYA Index': 'CTA LN4 EQ DM RTA_INDEX',
        'UXA Index': 'CTA LN4 EQ DM UX_INDEX',
        'TUA Comdty': 'CTA LN4 DMFI 2Y TU_COMDTY',
        'TYA Comdty': 'CTA LN4 DMFI 10Y TY_COMDTY',
        'ECA Curncy': 'CTA LN4 FX DM EUR',
        'ADA Curncy': 'CTA LN4 FX DM AUD',
        'JYA Curncy': 'CTA LN4 FX DM JPY',
        'CDA Curncy': 'CTA LN4 FX DM CAD',
        'DXA Curncy': 'CTA LN4 FX DM DX_CURNCY',
        'BTCA Curncy': 'CTA LN4 FX DM BTC_CURNCY',
        'DCRA Curncy': 'CTA LN4 FX DM DCR_CURNCY',
    }
    cot_table = pd.DataFrame()
    figs_net = []
    figs_ls = []
    chart_links = {}
    cta_dict = {}
    for k, v in other_dict.items():
        cta = cta_dict.get(k)
        if cta is None:
            cta_ticker = cta_map_other.get(k, f"CTA LN4 CM EN {k.split('A Comdty')[0]}_COMDTY")
            cta = rvx.rvx(
                ticker=cta_ticker,
                field="SIGNAL",
                sdate=f"2023-01-01",
                edate=today()
            )
        df_1 = cftc_analysis_fut(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0], update=update)
        cot_table = pd.concat([cot_table, df_1], axis=0, ignore_index=True)
        df_, cot_data = cftc_analysis_fut_opt(active=k, alt_active=v, nc=True, cta=cta.iloc[:, 0], update=update)
        cot_table = pd.concat([cot_table, df_], axis=0, ignore_index=True)
        reg_data = pd.DataFrame()
        reg_data["price chg"] = cot_data["PX_LAST_1"].diff() / cot_data["PX_LAST_1"].shift(1)
        reg_data["net chg"] = cot_data["Net"].diff()
        reg_fig, lm = chart.regression_chart(
            data=reg_data.iloc[-104:, :].dropna(),
            title=f"Price vs Net position change - {k}",
            xaxis_title='Net position change',
            yaxis_title='Price change',
        )
        reg_str = "<p style='font-family:Calibri'>Beta (price chg in % for 10k net position chg): "
        raise NotImplementedError("Missing regression text after lm.param: IMG_4625 line 629")
        reg_data_4w = pd.DataFrame()
        reg_data_4w["price chg"] = (cot_data["PX_LAST_1"] - cot_data["PX_LAST_1"].shift(4)) / cot_data[
            "PX_LAST_1"].shift(4)
        reg_data_4w["net chg"] = cot_data["Net"] - cot_data["Net"].shift(4)
        reg_fig_4w, lm_4w = chart.regression_chart(
            data=reg_data_4w.iloc[-104:, :].dropna(),
            title=f"Price vs Net position 4w change - {k}",
            xaxis_title='Net position change',
            yaxis_title='Price change',
        )
        reg_str_4w = "<p style='font-family:Calibri'>Beta (price chg in % for 10k net position chg): "
        raise NotImplementedError("Missing regression text after lm_4w: IMG_4625 line 640")
        fig_net, fig_ls = gen_figures(k, cot_data, cta.iloc[:, 0])
        figs_reg = []
        figs_reg.append(fig_ls)
        figs_reg.append(table.figs_to_grid([reg_fig, reg_fig_4w] + [reg_str, reg_str_4w], columns=2))
        table.to_html(figs_reg, f"{html_path}\\positioning\\links\\{k}_chart.html")
        figs_net.append(fig_net)
        figs_ls.append(fig_ls)
        chart_links[df_.iloc[0, 0]] = (
            f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_.iloc[0, 0]}</a>')
        chart_links[df_1.iloc[0, 0]] = (
            f'<a href="{html_path}\\positioning\\links\\{k}_chart.html">{df_1.iloc[0, 0]}</a>')

    if cot_table.columns[1] != "Net Position (NC)":
        new_cols = [cot_table.columns[0], cot_table.columns[-1]] + list(cot_table.columns[1:-1])
        cot_table = cot_table[new_cols]
    if not cot_table.iloc[:, 0].isnull().values.any():
        figs = []
        figs_all = []
        position_change = cot.position_change(cot_table, thr=1.5)
        if not position_change.empty:
            position_change_idx = cot_table.loc[cot_table.iloc[:, 0].isin(position_change.iloc[:, 0]), :].index
        else:
            position_change_idx = []
        position_diverge = cot.position_divergence(cot_table)
        if not position_diverge.empty:
            position_diverge_idx = cot_table.loc[cot_table.iloc[:, 0].isin(position_diverge.iloc[:, 0]), :].index
        else:
            position_diverge_idx = []
        format_column = {
            '0': {'width': '120px', 'text-align': 'left', 'right_border': True, 'highlight': [0, 'net pos rank', '_thr_high', '_thr_low']},
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
            '11': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'bold': True, 'highlight': [11, '4w price change z score', '_z_high', '_z_low']},
            '12': {'width': '60px', 'text-align': 'center', 'bold': True, 'highlight': [12, '4w delta change z score', '_z_high', '_z_low']},
            '13': {'width': '60px', 'text-align': 'center'},
            '14': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            '15': {'width': '80px', 'text-align': 'center'},
            '16': {'width': '60px', 'text-align': 'center'},
            '17': {'width': '60px', 'text-align': 'center', 'right_border': True},
            '18': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [17, '_thr_net']},
            '19': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [18, '_thr_net']},
            '20': {'width': '60px', 'text-align': 'center', 'format': '{:.1%}', 'highlight': [19, '_thr_high8', '_thr_low8']},
            '21': {'width': '80px', 'text-align': 'center', 'format': '{:.1%}', 'right_border': True, 'highlight': [20, '_thr_high8', '_thr_low8']},
            '22': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            '23': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
            '24': {'width': '60px', 'text-align': 'center', 'format': '{:.2f}'},
        }
        if not position_change.empty:
            output_html_table1 = table.html_format(
                df=position_change,
                header='Weekly or 4w position change more than 1.5 zscore (4y window)',
                footer=None,
                show_date=False,
                format_column=format_column,
                format_row=None,
                precision=0,
                hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
                inline=False,
                background_color="lightblue",
                na_rep="-")
            for i in position_change_idx:
                output_html_table1 = output_html_table1.replace(cot_table.iloc[i, 0], chart_links[cot_table.iloc[i, 0]])
            figs.append(output_html_table1)
        else:
            output_html_table1 = table.html_text('No position change more than 1.5 zscore (4y window) in the last week')
            figs.append(output_html_table1)
        if not position_diverge.empty:
            output_html_table2 = table.html_format(
                df=position_diverge,
                header='Weekly position change diverges from price change',
                footer=None,
                show_date=False,
                format_column=format_column,
                format_row=None,
                precision=0,
                hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
                inline=False,
                background_color="lightblue",
                na_rep="-")
            for i in position_diverge_idx:
                output_html_table2 = output_html_table2.replace(cot_table.iloc[i, 0], chart_links[cot_table.iloc[i, 0]])
            figs.append(output_html_table2)
        else:
            output_html_table2 = table.html_text('No position change diverges from price change in the last week')
            figs.append(output_html_table2)
        output_html_table = table.html_format(
            df=cot_table,
            header="Speculators Net Position",
            footer=None,
            show_date=False,
            format_column=format_column,
            format_row={
                "1": {"bottom_border": True},
                "3": {"bottom_border": True},
                "5": {"bottom_border": True},
                "7": {"bottom_border": True},
                "9": {"bottom_border": True},
                "11": {"bottom_border": True},
                "13": {"bottom_border": True},
                "15": {"bottom_border": True},
                "17": {"bottom_border": True},
                "19": {"bottom_border": True},
                "21": {"bottom_border": True},
                "23": {"bottom_border": True},
            },
            precision=0,
            hide_cols=['net pos rank', 'net/oi pct rank', 'YTD price change', '_thr_high', '_thr_low', '_thr_high8', '_thr_low8', '_thr_net', '_z_high', '_z_low', '_price_chg', '_last_update'],
            inline=False,
            background_color="lightblue",
            na_rep="-")
        for _idx, i in chart_links.items():
            output_html_table = output_html_table.replace(_idx, i)
        figs_all.append(output_html_table)
        table.figures_to_html(figs_all, f"{html_path}\\positioning\\links\\cot_table_macro.html", task_name=report_name)
        table.figures_to_html(table.to_html(figs_ls, add_home=False),
                              f"{html_path}\\positioning\\links\\position_macro.html", task_name=report_name)
        figs.append(u'<a href="{:s}\\positioning\\links\\cot_table_macro.html">Full Macro Cot Table</a><br>'.format(html_path))
        figs.append(
            u'<a href="{:s}\\positioning\\links\\position_macro.html">Position Charts</a><br><br>'.format(
                html_path))
        figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
        table.figures_to_html(
            [table.html_text("Macro COT Alert", style="font-family:Calibri;", tag='h1'),
             "<div style='font-family:Calibri;' >"] + figs,
            f"{html_path}\\positioning\\cot_macro.html", task_name=report_name)
        send_email(send_to=send_to, subject="COT - Macro ALERT", body=figs,
                   html_path=f"{html_path}\\positioning\\cot_macro.html")


def update():
    db = partial(mongo_table, table="cot", pk=["ticker", "active", "item"], db="data", url=url)
    old = pyg.get_data(db, active="BTCA Curncy", item="AMLF")
    new = bbg.bdh("TFF2RAIL Index", ["PX_LAST"], sdate=today() - dt.timedelta(180), edate=today())
    if old.index[-1] < new.index[-1]:
        update_macro(send_to=config.macro_group)


if __name__ == "__main__":
    update()
