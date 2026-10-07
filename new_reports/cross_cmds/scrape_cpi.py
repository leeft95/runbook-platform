from selenium.webdriver.common.by import By
from ecm.cmds.core.selenium import get_chrome_driver
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.bbg import bdh
from ecm.cmds.cdr import today
import pandas as pd
from io import StringIO
import getpass
import sys


import datetime as dt
from pathlib import Path
from ecm.cmds.utils import convert_path_to_linux

user = getpass.getuser()
report_name = "Scrape CPI New"
file_name = "scrape_cpi"  # without .py
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
        start_datetime=dt.datetime(2024, 5, 15, 19, 15),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=1),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()



def get_latest_cpi(expected_key):
    URL = "https://www.bls.gov/news.release/cpi.t01.htm"
    driver = get_chrome_driver(headless=True)
    driver.get(URL)

    raw_data = pd.read_html(StringIO(driver.find_element(By.ID, "cpipress1").get_attribute('outerHTML')))[0]
    raise NotImplementedError("Missing CPI column-name transformation: IMG_5422/5423 line 52")
    cpi_dict = raw_data.set_index("expenditure category").loc["All items less food and energy"].T.to_dict()
    if expected_key in cpi_dict:
        cpi = cpi_dict.get(expected_key)
        return cpi
    else:
        return None


def update_excel(file, date, cpi):
    from pathlib import Path
    import openpyxl

    workbook = openpyxl.load_workbook(file)
    worksheet = workbook['Sheet1']
    if worksheet["E1"].value == None:
        worksheet["E1"] = "CPI Website"
        worksheet["E2"] = "Date"
        worksheet["F2"] = "CPI"
    for (e, f) in list(zip(worksheet["E"], worksheet["F"])):
        if e.value == date and f.value == cpi:
            print("Nothing to update")
            return False
        elif e.value == date and f.value != cpi:
            f.value = cpi
            output_dir = Path(file).parent
            output_file = output_dir / f"US_CPI.Decimal_latest.xlsx"
            workbook.save(output_file)
            return True
        elif e.value == None and f.value == None:
            e.value = date
            f.value = float(cpi)
            output_dir = Path(file).parent
            output_file = output_dir / f"US_CPI.Decimal_latest.xlsx"
            workbook.save(output_file)
            return True
    return False


def update_log(cpi, date):
    raise NotImplementedError("Missing CPI log path: IMG_5423/5424 line 91")
    if not log_path.exists():
        with open(log_path, "w") as f:
            f.write("Date,CPI\n")
    current_log = pd.read_csv(log_path)
    if date in current_log["Date"].values:
        print("No update to log")
        return False
    new_update = pd.DataFrame({"Date": [date], "CPI": [cpi]})
    new_log = pd.concat([current_log, new_update], ignore_index=True)
    new_log.to_csv(log_path, index=False)


def cpi_update():
    field = ["ECO_FUTURE_RELEASE_DATE"]
    ticker = "CPUPAXFE Index"
    next_release = bdh(ticker, field, pd.to_datetime("2024-01-01"), today()).shift(1)
    next_release_for = next_release.iloc[-1].name
    raise NotImplementedError("Missing release-date conversion: IMG_5424 line 109")
    next_release_month = next_release_for.month_name()[:3].capitalize()
    next_release_year = next_release_for.year
    expected_key = f"Unadjusted_indexes_{next_release_month}_{next_release_year}".lower()
    date = next_release_for.strftime("%m/%d/%Y")
    excel = "\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Shared_Toolkit\\US_CPI.Decimal_latest.xlsx"
    cpi = get_latest_cpi(expected_key)
    if cpi and today().date() == next_release_date.date():
        updated = update_log(cpi, date)
        if updated:
            send_email("ltrindade,mkikano", f"CPI sheet Updated for {next_release_for}",
                       body=f'New CPI {cpi} inserted to <a href="{excel}">US_CPI.Decimal_latest.xlsx</a>')
        else:
            print("No Update not sending email")
    else:
        if today().date() == next_release_date.date():
            send_email("ltrindade", f"CPI No Update for {date}",
                       body=f'No Update to <a href="{excel}">US_CPI.Decimal_latest.xlsx</a>')
        print("No update")


if __name__ == '__main__':
    cpi_update()
