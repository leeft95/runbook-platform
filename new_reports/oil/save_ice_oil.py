import pandas as pd
import datetime as dt
import sys
import os
import ecm.cmds.data as dv

import ecm.cmds.sql as sql
from ecm.cmds.config import root_path
from ecm.cmds.data import save_ice_to_datebase_backfill
from ecm.cmds.cdr import today

report_name = "Save ICE Oil"
file_name = "save_ice_oil"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
to_folder = f"{root_path}\\data\\ice_oil"


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY,
        start_datetime=dt.datetime(2023, 7, 1, 3, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\cmds_new\pythonw.exe"
    )
    win_task.create_task()


if __name__ == '__main__':
    save_ice_to_datebase_backfill(start_date=today() - dt.timedelta(days=5), market="oil")
