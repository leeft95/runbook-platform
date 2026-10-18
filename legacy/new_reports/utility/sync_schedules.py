import sys
import datetime as dt
from ecm.cmds.core.scheduler import build_schedule_and_backup
from ecm.cmds.config import root_path
from ecm.atom.wintask.scheduler import ECMWinTask
from ecm.atom.wintask.utils import Days

file_name = "sync_schedules"
report_name = "Sync Schedules"
file_path = f"{root_path}\\autoreports\\reports\\utility\\{file_name}.py"


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC

    win_task = ECMWinTask(
        days=Days.SUNDAY,
        start_datetime=dt.datetime(2022, 7, 1, 23, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f"{report_name}", filepath=f"{file_path}"),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


if __name__ == '__main__':
    build_schedule_and_backup(
        python_env_override=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe", disable_all=False
    )
