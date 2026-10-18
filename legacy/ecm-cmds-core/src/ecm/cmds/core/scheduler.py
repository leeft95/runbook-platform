import re
import sys

if sys.platform != "win32":
    raise NotImplementedError("Auto Scheduler is only defined for windows")
from ecm.cmds.core.config import root_path_s  # noqa: F401
from ecm.cmds.core.config import root_path  # noqa: F401
from ecm.cmds.core.config import root_path_jm_s, root_path_jm, root_path_jm_eu_s, root_path_jm_eu
from ecm.cmds.core.task_base import WinTaskPoC  # noqa: F401
from ecm.atom.wintask.scheduler import ECMWinTask  # noqa: F401
from ecm.atom.wintask.utils import Days  # noqa: F401
from pathlib import Path
import ast
import pandas as pd
import datetime as dt  # noqa: F401
import datetime as dtm  # noqa: F401
from ecm.cmds.core.schema import ReportScheduleConfig as Schedule  # noqa: F401
from ecm.cmds.core.cdr import today
from ecm.cmds.sql import LO25DB


from loguru import logger as log



if Path(root_path_s).exists():
    sys.path.append(root_path_jm_s)
    jm_code_website_tests: Path = Path(root_path_jm_s) / "website_tests.py"
    jm_code_eu_website_tests: Path = Path(root_path_jm_eu_s) / "eu_website_tests.py"
    base_reports_dir: Path = Path(root_path_s) / "autoreports" / "reports"
    base_schedule_dir: Path = Path(root_path_s) / "autoreports" / "schedule" / "xmlBackup"
    report_config_csv: Path = base_reports_dir / "reports_status.csv"
else:
    sys.path.append(root_path_jm)
    jm_code_website_tests = Path(root_path_jm) / "website_tests.py"
    jm_code_eu_website_tests = Path(root_path_jm_eu) / "eu_website_tests.py"
    base_reports_dir = Path(root_path) / "autoreports" / "reports"
    base_schedule_dir = Path(root_path) / "autoreports" / "schedule" / "xmlBackup"
    report_config_csv = base_reports_dir / "reports_status.csv"


MARKETS = [
    "cross_cmds",
    "data",
    "oil",
    "ttf",
    "us_gas",
    "eu_gas",
    "gas",
    "oil_detail",
    "positioning",
    "weather",
]


python_exec_string_regex = re.compile('(?P<assigner>python_executable=).*"(?P<python_exec_string>.*e)')


def find_all_py(dir, files=None):
    if not files:
        files = []
    for pth in dir.rglob("*"):
        if pth.is_dir():
            files = find_all_py(pth, files)
        if pth.is_file() and pth.suffix == ".py":
            files.append(pth)
    return files


def find_all_scripts(market, base_dir):
    search_dir = base_dir / market
    if not search_dir.exists():
        raise FileExistsError(f"Reports Directory {search_dir} does not exist")
    python_files = find_all_py(search_dir)
    return python_files




def find_all_schedules(
    market,
    base_dir,
    schedule_func_name: str = "add_schedule",
    python_env_override: str | None = None,
):
    py_files = find_all_scripts(market, base_dir)
    schedule_dict = dict()
    for fle in py_files:
        task_found = False
        is_task_file = False
        with open(fle, "r") as f:
            raw_text = f.read()
            parsed = ast.parse(raw_text)
            for node in ast.walk(parsed):
                if isinstance(node, ast.FunctionDef) and node.name == schedule_func_name:
                    is_task_file = True
            if is_task_file:
                for node in ast.walk(parsed):
                    if task_found:
                        break
                    if isinstance(node, ast.Assign) and (isinstance(node.targets[0], ast.Name) and node.targets[0].id == "report_name"):
                        report_name_code = ast.get_source_segment(raw_text, node.value)
                        if isinstance(report_name_code, str):
                            report_name = eval(report_name_code)  # noqa: F841
                        else:
                            ValueError(f"Could not parse {report_name_code}")
                    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "file_name":
                        file_name_code = ast.get_source_segment(raw_text, node.value)
                        if isinstance(file_name_code, str):
                            file_name = eval(file_name_code)  # noqa: F841
                        else:
                            raise ValueError(f"Could not parse {file_name_code}")
                    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "file_path":
                        file_path_code = ast.get_source_segment(raw_text, node.value)
                        if isinstance(file_path_code, str):
                            file_path = eval(file_path_code)  # noqa: F841
                        else:
                            raise ValueError(f"Could not parse {file_path_code}")
                    if isinstance(node, ast.FunctionDef) and node.name == schedule_func_name:
                        for n in node.body:
                            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "win_task":
                                win_task_code = ast.get_source_segment(raw_text, n.value)
                                if isinstance(win_task_code, str):
                                    win_task_code = win_task_code.replace("python_excecutable", "python_executable")
                                    if python_env_override:
                                        if match := python_exec_string_regex.search(win_task_code):
                                            replace_string = match.groupdict().get("python_exec_string", None)
                                            if replace_string is not None:
                                                win_task_code = win_task_code.replace(replace_string, python_env_override)
                                            else:
                                                log.error("Could not replace env override," " using current env")
                                                win_task_code = win_task_code.replace("python_executable", "python_excecutable")

                                    win_task = eval(win_task_code)
                                    schedule_dict[fle.stem] = win_task
                                    task_found = True
                                else:
                                    ValueError(f"Could not parse {win_task_code}")
    return schedule_dict


def find_all_schedules_jm(market, python_env_override: str = None):
    file_to_market = dict(us_gas=jm_code_website_tests, eu_gas=jm_code_eu_website_tests)
    py_file = file_to_market.get(market)
    if py_file is None:
        raise ValueError(f"Market {market} is not mapped for JM")
    schedule_dict = dict()
    with open(py_file, "r") as f:
        raw_text = f.read()
        parsed = ast.parse(raw_text)
        for node in ast.walk(parsed):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("schedule_"):
                for n in node.body:
                    if isinstance(n, ast.Assign) and (isinstance(n.targets[0], ast.Name) and n.targets[0].id == "report_name"):
                        report_name_code = ast.get_source_segment(raw_text, n.value)
                        if isinstance(report_name_code, str):
                            report_name = eval(report_name_code)  # noqa: F841
                        else:
                            ValueError(f"Could not parse {report_name_code}")
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "file_name":
                        file_name_code = ast.get_source_segment(raw_text, n.value)
                        if isinstance(file_name_code, str):
                            file_name = eval(file_name_code)  # noqa: F841
                        else:
                            raise ValueError(f"Could not parse {file_name_code}")
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "file_path":
                        file_path_code = ast.get_source_segment(raw_text, n.value)
                        if isinstance(file_path_code, str):
                            file_path = eval(file_path_code)  # noqa: F841
                        else:
                            raise ValueError(f"Could not parse {file_path_code}")
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "win_task":
                        win_task_code = ast.get_source_segment(raw_text, n.value)
                        if isinstance(win_task_code, str):
                            win_task_code = win_task_code.replace("python_excecutable", "python_executable")
                            if python_env_override:
                                if match := python_exec_string_regex.search(win_task_code):
                                    replace_string = match.groupdict().get("python_exec_string", None)
                                    if replace_string is not None:
                                        win_task_code = win_task_code.replace(replace_string, python_env_override)
                                    else:
                                        log.error("Could not replace env override, using current env")
                                        win_task_code = win_task_code.replace("python_executable", "python_excecutable")
                            win_task = eval(win_task_code)
                            schedule_dict[report_name] = win_task
                        else:
                            ValueError(f"Could not parse {win_task_code}")
    return schedule_dict


def persist_schedules(schedule_dict: dict):
    for group, tasks in schedule_dict.items():
        output_dir = base_schedule_dir / group
        if not output_dir.exists():
            output_dir.mkdir(parents=True)
        for name, task in tasks.items():
            output_path = output_dir / f"{name}.xml"
            with open(output_path, "w") as fe:
                xml = task.get_task_xml()
                fe.write(xml)


def backup_task_xml(task: ECMWinTask, group: str, name: str):
    output_dir = base_schedule_dir / group
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
    output_path = output_dir / f"{name}.xml"
    with open(output_path, "w") as fe:
        xml = task.get_task_xml()
        fe.write(xml)


def time_to_timedelta(t: dt.time) -> dt.timedelta:
    return dt.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second, microseconds=t.microsecond)


def get_winTask(
    schedule_time,
    timezone,
    days,
    report_name,
    file_path,
    python_executable,
    repeat_interval=None,
    repeat_duration=None,
):
    repititon_args = dict()
    if repeat_interval is not None:
        repititon_args["repetition_interval"] = time_to_timedelta(repeat_interval)
    if repeat_duration is not None:
        repititon_args["repetition_duration"] = time_to_timedelta(repeat_duration)
    start = dt.datetime(dt.datetime.today().year, dt.datetime.today().month, dt.datetime.today().day) + time_to_timedelta(schedule_time)
    win_task = ECMWinTask(
        days=Days(days),
        start_datetime=start,
        timezone=timezone,
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f"{file_path}"),
        background_task=True,
        python_excecutable=python_executable,
        **repititon_args,
    )
    return win_task


def register_schedules(disable_all: bool = False):
    latest_schedules = Schedule.load_sql(LO25DB("prod"), form="db")
    for mkt, mkt_df in latest_schedules.groupby("market"):
        log.warning(f"Processing {mkt}")
        for _, row in mkt_df.reset_index().iterrows():
            report_name = row.report_name
            schedule_time = row.schedule_time
            timezone = row.timezone
            days = row.schedule_days
            repeat_duration = row.repeat_duration
            repeat_interval = row.repeat_interval
            file_path = row.report_path
            python_executable = row.python_executable
            enabled = row.enabled
            win_task = get_winTask(
                schedule_time,
                timezone,
                days,
                report_name,
                file_path,
                python_executable,
                repeat_interval,
                repeat_duration,
            )
            if enabled and not disable_all:
                win_task.create_task()
                backup_task_xml(win_task, row.market, row.report_name)
                log.info(f"Scheduled {report_name} under {mkt}")
            else:
                win_task.create_task(disable=True)
                backup_task_xml(win_task, row.market, row.report_name)
                log.error(f"Not Scheudling {report_name}")


def build_schedule_dict(python_env_override: str = None):
    reports = dict()
    for mkt in MARKETS:
        if mkt in ["us_gas", "eu_gas"]:
            schdeuled_report_dict = find_all_schedules_jm(mkt, python_env_override)
        else:
            schdeuled_report_dict = find_all_schedules(mkt, base_reports_dir, python_env_override=python_env_override)
        report_names = list(schdeuled_report_dict.keys())
        if len(report_names) > 0:
            reports[mkt] = schdeuled_report_dict
    return reports


def update_report_config(schedule_dict: dict | None = None):
    if not schedule_dict:
        schedule_dict = build_schedule_dict()
    report_config = pd.read_csv(report_config_csv)
    updated_cols = []
    for mkt in MARKETS:
        mkt_cols = [x for x in report_config.columns if x.startswith(mkt)]
        if len(mkt_cols) > 0:
            schedule = report_config[mkt_cols].set_index(mkt).dropna(how="all")
            mkt_tasks = schedule_dict.get(mkt)  # type: ignore
            if mkt_tasks is None:
                continue
            for name, _ in mkt_tasks.items():
                if name not in schedule.index:
                    schedule.loc[name] = "+"
            updated_cols.append(schedule.reset_index().dropna(how="all"))
    updated_df = pd.concat(list(reversed(sorted(updated_cols, key=len))), axis=1)
    updated_df.to_csv(report_config_csv)


def update_db(report_dict, python_env_override=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"):
    schedules = []
    exist_raw_record = pd.read_csv(report_config_csv)
    for mkt, reports in report_dict.items():
        for report_name, schedule in reports.items():
            scheduler_args = dict(schedule.scheduler_args)
            schedule_time = scheduler_args.get("start_datetime", dt.time(8, 0, 0))
            if isinstance(schedule_time, dt.datetime):
                schedule_time = schedule_time.time()
            timezone = scheduler_args.get("timezone", "Europe/London")
            schedule_days = scheduler_args.get("days", Days.WEEKDAYS).value  # weekdays
            repeat_duration = scheduler_args.get("repetition_duration", None)
            repeat_interval = scheduler_args.get("repetition_interval", None)
            python_executable = scheduler_args.get("path", python_env_override)
            task_args = schedule.ecm_task._kwargs
            report_path = task_args.get("filepath")
            task_name = task_args.get("name", report_name).replace('"', "")
            try:
                enabled = True if exist_raw_record.set_index(mkt)[f"{mkt}_active"].loc[report_name] == "+" else False
            except KeyError:
                enabled = True

            table_row = dict(
                market=mkt,
                report_name=task_name,
                enabled=enabled,
                schedule_time=schedule_time,
                timezone=timezone,
                repeat_duration=repeat_duration,
                repeat_interval=repeat_interval,
                schedule_days=schedule_days,
                report_path=report_path,
                python_executable=python_executable,
            )
            schedules.append(table_row)
    schedules_df = pd.DataFrame(schedules)
    if not schedules_df.dropna(subset=["repeat_interval"]).empty:
        schedules_df.repeat_interval = (today() + schedules_df.repeat_interval).dt.time
    if not schedules_df.dropna(subset=["repeat_duration"]).empty:
        schedules_df.repeat_duration = (today() + schedules_df.repeat_duration).dt.time

    schedules_schema_latest = Schedule(schedules_df)
    schedules_exist_in_db = Schedule.load_sql(source=LO25DB("prod"), form="db")
    updated_df = Schedule(schedules_schema_latest.combine_first(schedules_exist_in_db).drop_duplicates())
    if not updated_df.empty:
        updated_df.dump_sql(db=LO25DB("prod"), form="db", mode="update_first")


def build_schedule_and_backup(python_env_override: str = None, disable_all: bool = False, rebuild: bool = False):
    if rebuild:
        reports_dict = build_schedule_dict(python_env_override=python_env_override)
        update_db(reports_dict)
        update_report_config(reports_dict)
        register_schedules(disable_all=disable_all)
    else:
        register_schedules(disable_all=disable_all)


if __name__ == "__main__":
    raise NotImplementedError("Clipped main invocation at photographed scheduler.py line 387")
