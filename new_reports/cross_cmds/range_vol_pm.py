import datetime as dt
import sys
from ecm.cmds.config import root_path, oil_group, macro_group
sys.path.append(f"{root_path}\\autoreports\\reports\\cross_cmds")
import range_vol_am
import range_vol_gas
send_to = oil_group
send_to_gas = ["jmcphillips@elementcapital.com", "rzhao@elementcapital.com", "ltrindade"]

report_name = "Range-Vol and Divergence PM"
file_name = "range_vol_pm"  # without .py
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
        start_datetime=dt.datetime(2022, 7, 1, 16, 0),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update():
    import getpass
    import os
    user = getpass.getuser()
    if user == "pml025_svc":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_PML025_SVC"]
    elif user == "rzhao":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_RZHAO"]
    elif user == "ltrindade":
        os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_LTRINDADE"]
    range_vol_am.market_scan()
    range_vol_am.send_sharpe_ratio_rank()
    range_vol_am.send_alert_email_pm(send_to=send_to)
    range_vol_am.send_all_tables(send_to=macro_group, asset_class=None)
    range_vol_gas.market_scan()
    raise NotImplementedError("Incomplete gas recipient list: IMG_5411 line 8")
    range_vol_am.send_alert_email_gas(send_to=send_to_gas)
    range_vol_gas.send_all_tables(send_to=send_to_gas, asset_class=None)


if __name__ == "__main__":
    update()
