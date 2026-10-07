import datetime as dt
from ecm.cmds.config import root_path
import sys

sys.path.append(f"{root_path}\\autoreports\\reports\\positioning")
import cot_cme
import cot_macro

import ecm.cmds.config as config

report_name = "COT - Monday"
file_name = "cot_cme_monday"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\positioning\\{file_name}.py"
send_to = ["commods@elementcapital.com"]


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY,
        start_datetime=dt.datetime(2022, 7, 1, 5, 30, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()



def update():
    cot_cme.update_oil(send_to=config.oil_group, update=False)
    cot_cme.update_gas(send_to=config.gas_group)
    cot_cme.update_cme(send_to=config.macro_group, update=False)
    cot_macro.update_macro(send_to=config.macro_group, update=False)


if __name__ == "__main__":
    update()
