import pandas as pd
import datetime as dt
import time
import sys
import ecm.cmds.table as table
from ecm.cmds.config import root_path, output_path, html_path
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux

send_to = ["Commods@elementcapital.com"]
report_name = "Weekly new high-low"
file_name = "weekly_high_low"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"

cc_csv_folder = f"{output_path}\\csvs\\cross_cmds"


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
        start_datetime=dt.datetime(2023, 7, 1, 13, 10),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()



def update(send_to):
    weekly_high = pd.read_csv(convert_path_to_linux(f"{cc_csv_folder}\\market_scan\\weekly_high.csv"))
    weekly_high = weekly_high.drop_duplicates(subset=['Ticker'], keep='first')
    weekly_low = pd.read_csv(convert_path_to_linux(f"{cc_csv_folder}\\market_scan\\weekly_low.csv"))
    weekly_low = weekly_low.drop_duplicates(subset=['Ticker'], keep='first')
    if len(weekly_high) > 0:
        weekly_high.set_index('Unnamed: 0', inplace=True)
        html_weekly_high = table.html_format(
            df=weekly_high,
            precision=2,
            format_column={
                'Instr': {'width': '20px', 'text-align': 'center', 'right_border': True},
                'Ticker': {'width': '160px', 'text-align': 'center', 'right_border': True},
                'Live': {'width': '60px', 'text-align': 'center'},
                'Weekly High': {'width': '60px', 'text-align': 'center'},
                'Change Today': {'width': '60px', 'text-align': 'center'},
                'Range Today': {'width': '60px', 'text-align': 'center', 'format': '{:.0%}'},
                'Volume Today': {'width': '60px', 'text-align': 'center', 'format': '{:.0%}'}
            }
        )
    else:
        html_weekly_high = 'No instruments make weekly new high.'

    if len(weekly_low) > 0:
        weekly_low.set_index('Unnamed: 0', inplace=True)
        html_weekly_low = table.html_format(
            df=weekly_low,
            precision=2,
            format_column={
                'Instr': {'width': '20px', 'text-align': 'center', 'right_border': True},
                'Ticker': {'width': '200px', 'text-align': 'center', 'right_border': True},
                'Live': {'width': '60px', 'text-align': 'center'},
                'Weekly Low': {'width': '60px', 'text-align': 'center'},
                'Change Today': {'width': '60px', 'text-align': 'center'},
                'Range Today': {'width': '60px', 'text-align': 'center', 'format': '{:.0%}'},
                'Volume Today': {'width': '60px', 'text-align': 'center', 'format': '{:.0%}'}
            }
        )
    else:
        html_weekly_low = 'No instruments make weekly new low.'

    html_table = [
        'Instruments that made new weekly high this week. <br>',
        html_weekly_high,
        '<hr style="width: 550px;align; margin-left: 0">',
        'Instruments that made new weekly low this week. <br>',
        html_weekly_low,
    ]
    table.figures_to_html(html_table, filename=f'{html_path}\\cross_cmds\\weekly_high_low.html')
    send_email(send_to=send_to, subject="Weekly new high/low",
               body=[html_table,
                     '<br><br>This is automated email sent at {:s}. <br><br>'.format(
                         time.strftime('%Y-%m-%d %H:%M'))],
               html_path=f'{html_path}\\cross_cmds\\weekly_high_low.html'
               )


if __name__ == "__main__":
    update(send_to=send_to)
