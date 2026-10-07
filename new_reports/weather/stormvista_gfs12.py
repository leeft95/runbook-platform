import sys
from ecm.cmds.config import output_path, html_path, root_path, gas_group
sys.path.append(f"{root_path}\\autoreports\\reports\\weather")
import datetime as dt
import stormvista_gfs00


send_to = gas_group
report_name = "Weather - Global GFS12z"
file_name = "stormvista_gfs12"  # without .py
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
        start_datetime=dt.datetime(2023, 7, 1, 18, 2),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(minutes=10),
        repetition_duration=dt.timedelta(minutes=120),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update():
    stormvista_gfs00.gfs_run(cycle='12', send_to=send_to, file_name=file_name, report_name=report_name)


if __name__ == "__main__":
    update()
