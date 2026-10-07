import datetime as dt
from ecm.cmds.config import root_path
import sys
sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")

import cwg_data
import us_tdd
import us_cdd
import us_hdd
import asia_tdd
import asia_cdd
import asia_hdd
import eu_tdd
import eu_cdd
import eu_hdd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from ecm.cmds.config import output_path, html_path, root_path, gas_group_us, gas_group
from ecm.cmds.cdr import today

import ecm.cmds.config as config

send_to = gas_group
report_name = "Weather - Global TDD"
file_name = "global_tdd"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY | Days.SUNDAY,
        start_datetime=dt.datetime(2022, 7, 1, 11, 5, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update():
    cwg_data.update()
    us_tdd.update()
    asia_tdd.update()
    eu_tdd.update()
    if today().weekday() not in [5, 6]:  # not Saturday or Sunday
        is_weekend = False
    else:
        is_weekend = True
    if today().month in [4, 5, 6, 7, 8]:
        us_cdd.update(send_to=gas_group_us)
        if not is_weekend:
            asia_cdd.update(send_to=send_to)
    elif today().month in [1, 2, 3, 9, 10, 11, 12]:
        us_hdd.update(send_to=gas_group_us)
        if not is_weekend:
            asia_hdd.update(send_to=send_to)
    if not is_weekend:
        if today().month in [5, 6, 7, 8]:
            eu_cdd.update(send_to=send_to)
        elif today().month in [1, 2, 3, 4, 9, 10, 11, 12]:
            eu_hdd.update(send_to=send_to)


if __name__ == "__main__":
    update()
