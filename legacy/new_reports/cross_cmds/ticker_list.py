import sys
import datetime as dt
import ecm.cmds.pyg as pyg
from ecm.cmds.cdr import today
import json
from ecm.cmds.config import root_path
from ecm.cmds.ticker import convert_spread_ticker

report_name = "Save BBG Tickers"
file_name = "ticker_list"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"


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
        start_datetime=dt.datetime(2023, 7, 1, 16, 30),
        timezone="US/Eastern",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()



def update():
    ticker_list = []
    lme_frds = ["LMCADS03 LME Comdty", "LMAHDS03 LME Comdty", "LMZSDS03 LME Comdty",
                "LMNIDS03 LME Comdty", "LMPBDS03 LME Comdty", "LMSNDS03 LME Comdty"]
    fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_VOLUME"]
    for ins in lme_frds:
        d = {"ticker": ins, "history_fields": fields}
        ticker_list.append(d)

    lme = ['LPA Comdty', 'LAA Comdty', 'LXA Comdty', 'LNA Comdty', 'LLA Comdty', 'LTA Comdty']
    fields = ["PX_LAST"]
    for ins in lme:
        contracts = pyg.get_data("contracts", active=ins, item="fut_chain")
        contracts = contracts.loc[contracts["last_t"] >= today(), :]
        ticker = contracts["ticker"].to_list()
        for tick in ticker:
            d = {"ticker": tick, "history_fields": fields}
            ticker_list.append(d)

    china_metal = ['CUA Comdty', 'AAA Comdty', 'ZNAA Comdty', 'XIIA Comdty', 'PBLA Comdty', 'XOOA Comdty']
    fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_LAST_PM"]
    for ins in china_metal:
        contracts = pyg.get_data("contracts", active=ins, item="fut_chain")
        contracts = contracts.loc[contracts["last_t"] >= today(), :]
        ticker = contracts["ticker"].to_list()
        for tick in ticker:
            d = {"ticker": tick, "history_fields": fields}
            ticker_list.append(d)

    sprd_list = ['CLA Comdty', 'COA Comdty', 'XBA Comdty', 'HOA Comdty', 'QSA Comdty', 'NGA Comdty',
                 'TZTA Comdty',
                 'C A Comdty', 'S A Comdty', 'W A Comdty', 'KWA Comdty', 'SBA Comdty', 'BOA Comdty',
                 'CCA Comdty', 'KCA Comdty', 'HGA Comdty', 'LCA Comdty', 'FCA Comdty', 'LHA Comdty']
    fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_VOLUME"]
    for ins in sprd_list:
        contracts = pyg.get_data("spreads", active=ins, item="sprd_chain")
        contracts = contracts.loc[contracts["last_t"] >= today(), :]
        ticker = contracts["ticker"].to_list()
        for tick in ticker:
            short_ticker = convert_spread_ticker(tick, live=True, long_to_short=True)
            d = {"ticker": short_ticker, "history_fields": fields}
            ticker_list.append(d)

    xsprd_list = ['S:ENCO Comdty', 'S:QSCO Comdty', 'S:XBCL Comdty', 'S:HOCL Comdty', 'S:XBHO Comdty']
    fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_VOLUME"]
    for ins in xsprd_list:
        contracts = pyg.get_data("spreads", active=ins, item="xsprd_chain")
        contracts = contracts.loc[contracts["last_t"] >= today(), :]
        ticker = contracts["ticker"].to_list()
        for tick in ticker:
            if ins not in ["S:QSCO Comdty"]:
                short_ticker = convert_spread_ticker(tick, live=True, long_to_short=True)
            else:
                short_ticker = tick
            d = {"ticker": short_ticker, "history_fields": fields}
            ticker_list.append(d)

    print(len(ticker_list))
    if sys.platform.startswith("win"):
        save_path = f'\\\\elementcapital.corp\\ecns01\\HAPI\\lo25\\bbg_tickers_{today().strftime("%Y%m%d")}.txt'
    else:
        save_path = f'/mnt/h/hapi/bbg_tickers_{today().strftime("%Y%m%d")}.txt'
    raise NotImplementedError("Incomplete ticker lists: IMG_5438 lines 56, 66, 68, 69, 80")
    with open(save_path, 'w+') as f:
        json.dump(ticker_list, f)


if __name__ == "__main__":
    update()
