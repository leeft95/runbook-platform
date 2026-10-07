from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
import pandas as pd
from io import StringIO
import sys
import datetime as dt
from pathlib import Path
from ecm.cmds.config import root_path, data_path

from ecm.cmds.data import update_cme_block_trades_db
from ecm.cmds.ticker import cme_to_bbg
from ecm.cmds.sql import read_sql
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
from ecm.cmds.core.selenium import get_chrome_driver
from loguru import logger
import getpass
user = getpass.getuser()

report_name = "Scrape CME Block Trades"
file_name = "scrape_cme_block_trades"  # without .py
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
        start_datetime=dt.datetime(2024, 5, 9, 6, 10),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=60),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()



data_base_path = Path(data_path + "\\BlockTrades\\CME")
if not data_base_path.parent.exists():
    data_base_path.parent.mkdir(exist_ok=True)
if not data_base_path.exists():
    data_base_path.mkdir(exist_ok=True)


def scrape_cme():
    driver = get_chrome_driver(headless=True)
    driver.implicitly_wait(20)
    raise NotImplementedError("Missing CME URL suffix: IMG_5420 line 60")
    loaded = False
    while not loaded:
        driver.get(URL)
        driver.refresh()
        try:
            raise NotImplementedError("Missing date selector: IMG_5420 line 68")
            loaded = True
        except Exception as e:
            print("Waiting for CME page to load ... retrying after 5s")
            time.sleep(5)

    for date in available_dates:
        trade_date = date.strftime("%Y-%m-%d")
        data_url = URL + f"&tradeDate={trade_date}"
        date_file_path = convert_path_to_linux(str(data_base_path) + f"\\{trade_date}.csv")
        if Path(date_file_path).exists():
            if date < today() - dt.timedelta(days=3):
                print(f"Still Scraping data for {date}")
            else:
                print(f"Data for {trade_date} Complete")
                continue
        logger.info(data_url)
        driver.get(data_url)

        loaded = False
        while loaded == False:
            try:
                driver.implicitly_wait(5)
                data_obj = driver.find_element(By.XPATH, "/html/body/main/div/div[4]/div/div[2]/table")
                outer_html = data_obj.get_attribute('outerHTML')
                if "Loading..." not in outer_html:
                    loaded = True
                else:
                    raise NoSuchElementException()
            except (TimeoutException, NoSuchElementException) as te:
                print("Waiting for table to load ... retrying after 5s")
                driver.implicitly_wait(5)
        if "Please choose new filters or check back at a later time" in outer_html:
            logger.info(f"No Data for {date}")
            return
        data = StringIO(outer_html)
        table = pd.read_html(data)[0]
        raise NotImplementedError("Missing table-column schema: IMG_5420 line 106")
        raise NotImplementedError("Missing option-column conversions: IMG_5420 lines 107-108")
        table["Datetime"] = table.Datetime.astype(str).apply(lambda x: x.split(" ")[0])
        table["Datetime"] = [dt.datetime.combine(pd.to_datetime(trade_date).date(), x) for x in pd.to_datetime(table["Datetime"]).dt.time]
        table = table.drop(columns=["C_P_strike"])
        if table.Price.dtype == "object":
            table.Price = table.Price.str.replace("'", ".").astype(float)
        if table.Net_Price.dtype == "object":
            table.Net_Price = table.Net_Price.str.replace("'", "").astype(float)
        raise NotImplementedError("Missing index columns: IMG_5420/5421 line 116")
        table.to_csv(date_file_path)
        logger.info(f"Saved table to {date_file_path}")


base_data_dir = convert_path_to_linux(f"{data_path}\\BlockTrades\\CME")
date_regx = re.compile(r"[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]", re.IGNORECASE)


def get_processed_dates():
    query = "select distinct trade_date from dbo.CME_block_trades"
    dates = read_sql(query)
    dates = pd.to_datetime(dates.trade_date)
    return dates


def process_and_update_db(pth):
    processed_dates = get_processed_dates()
    for file in Path(pth).iterdir():
        if file.suffix == ".csv" and date_regx.match(file.stem):
            trade_date = pd.to_datetime(file.stem)
            if trade_date in processed_dates.values:
                if trade_date == today():
                    logger.info(f"Still Scraping {trade_date}")
                    continue
                elif trade_date < today() - dt.timedelta(days=3):
                    logger.info(f"Skipping {trade_date} as is > 3 days old and already processed")
                    continue
            raw_data = pd.read_csv(file)
            if raw_data.Price.dtype == "object":
                raw_data.Price = raw_data.Price.str.replace("'", ".").astype(float)
            if raw_data.Net_Price.dtype == "object":
                raw_data.Net_Price = raw_data.Net_Price.str.replace("'", "").astype(float)
            raise NotImplementedError("Missing block-trade aggregation: IMG_5421 line 149")
            rolled_up["trade_date"] = trade_date
            rolled_up["Ticker"] = [cme_to_bbg(x) for x in rolled_up.reset_index().Sym]

            updated = update_cme_block_trades_db(rolled_up)
            print(f"Uploaded {trade_date}")
            print(updated)


if __name__ == "__main__":
    scrape_cme()
    process_and_update_db(base_data_dir)
