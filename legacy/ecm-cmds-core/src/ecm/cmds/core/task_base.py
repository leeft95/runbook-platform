import datetime as dt
import subprocess
import sys
from pathlib import Path

import nbformat
import pytz
from ecm.atom.clients import BranchDict
from ecm.atom.clients import ECMTaskResult
from ecm.atom.clients.argument import Argument
from ecm.atom.clients.task import ECMDockerTask
from ecm.atom.parse import distill as ds
from ecm.atom.parse import types as at
from ecm.cmds.config import root_path
from ecm.cmds.core._email import send_email as send_email_func
from ecm.cmds.core.utils import convert_path_to_linux
from loguru import logger as log
from nbconvert.preprocessors import ExecutePreprocessor


def send_email(
    task: str,
    file_path: Path,
    error: BaseException = None,
    is_fail: bool = False,
    send_from: str = "cmdrprt",
    send_to: str = "rzhao,ltrindade,jmcphillips",
    **kwargs,
):
    if is_fail:
        if isinstance(error, bytes):
            error = error.decode("utf-8")
        if sys.platform.startswith("win"):
            rerun_url = "<a href='https://lo25.elementcapital.com/" f"task-runner/trigger/{task}'" " target='_blank'>Re-run Report</a>"
        else:
            run_date = dt.datetime.now().strftime("%Y-%m-%d")
            task = task.replace("_", "-").replace(" ", "-").replace('"', "")
            folder_name = file_path.parent.stem.replace("_", "-").replace(" ", "-").replace('"', "")
            task_path = f"lo25/{folder_name}/{task}"
            rerun_url = (
                "<a href='https://prismaticprod-gfishbeinelementcapital.msappproxy.net/"
                "snaphub/LinkRunner/AskToRun"
                "?runner=Wave&action=Trigger"
                f"&activity=day/{run_date}/{task_path}'"
                " target='_blank'>Re-run Report</a>"
            )
            log.error(f"Task: {task} has failed")
            log.error(task_path)
            log.error(rerun_url)
        send_email_func(
            send_to=send_to,
            subject=f"Task: {task} has failed",
            body=f"Task Kwargs: {kwargs}<br>{rerun_url}<br>Error: <br> {error}",
        )
    else:
        send_email_func(
            reply_to="rzhao",
            subject=f"Task: {task} has completed sucessfully",
            body=f"Task Kwargs: {kwargs}",
        )


def run_jupyter(name, filepath):
    try:
        log.info(f"Running: {filepath}")
        with open(filepath, encoding="utf8") as ff:
            nb_in = nbformat.read(ff, nbformat.NO_CONVERT)
            ep = ExecutePreprocessor(timeout=600, kernel_name="python3")
            ep.preprocess(nb_in)
    except AttributeError as e:
        log.error(e)
        send_email(name, error=e, date=dt.datetime.now(), is_fail=True)


def run_function(name, filepath, python_location="python"):
    log.info(f"Running: {filepath}")
    cmd = [python_location, filepath]
    captured_lines = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            log.info(line)
            captured_lines.append(line)

    if p.returncode > 0:
        has_error = False
        error_lines = []
        for line in captured_lines:
            if has_error:
                error_lines.append(line)
            if "Traceback" in line:
                has_error = True
                error_lines.append(line)
        if "us_gas" in filepath or "eu_gas" in filepath or "ttf" in filepath:
            sendto = "rzhao,ltrindade,jmcphillips,caitcheson"
        elif "asia_gas" in filepath:
            sendto = "ltrindade,rzhao,caitcheson"
        else:
            sendto = "ltrindade,rzhao"
        err = "".join(error_lines).replace("\n", "<br>")
        send_email(name, Path(filepath), error=err, date=dt.datetime.now(), is_fail=True, send_to=sendto)
        raise subprocess.CalledProcessError(returncode=p.returncode, cmd=p.args, stderr=p.stderr)
    if p.stdout:
        log.info(f"File Run Result {p.stdout}")


class WinTaskPoC(ECMDockerTask):  # type: ignore
    location = "ecm.cmds.core.task_base"
    function = run_function
    image = {"name": "ecm/cmds/core"}

    arguments = {
        "optional": {
            "name": Argument(
                name="name",
                spec=str,
                description="name of the task",
                required=True,
            ),
            "filepath": Argument(
                name="filepath",
                spec=str,
                description="jupyter file path",
                required=True,
            ),
            "date": Argument(
                name="date",
                spec=at.TimestampLike,
                description="Execution date",
                parse=ds.parse_datetime,
                display=ds.display_execution_date,
            ),
            "log_directory": Argument(
                name="log_directory",
                spec=str,
                description="The Path to output logs to file",
                default=f'"{root_path}\\logs"',
            ),
        },
    }

    def clean_up_log_dir(self, log_dir):
        current_date = dt.datetime.today()
        for file in log_dir.iterdir():
            file_date = dt.datetime.strptime(file.stem.upper(), "%Y%m%dT%H_%M_%S")
            if file_date < (current_date - dt.timedelta(days=5)):
                log.error(f"Removing old log file: {file}")
                file.unlink()
            else:
                continue

    def prepare(self, task_kwargs: BranchDict) -> BranchDict:

        log_directory = task_kwargs.pop("log_directory")
        dtstr = dt.datetime.now(pytz.timezone("Europe/London")).strftime("%Y%m%dt%H_%M_%S").upper()
        task_name = task_kwargs.get("name").replace('"', "")
        log_dir = Path(convert_path_to_linux(f"{log_directory}"))
        log_path = log_dir / task_name / f"{dtstr}.log"
        try:
            self.clean_up_log_dir(log_path.parent)
        except Exception as e:
            log.error(f"Could not clean up log dir due to \n{e}")
        if not log_path.parent.exists():
            log_path.parent.mkdir(parents=True)
        log.error(log_path)
        log.add(str(log_path))
        return task_kwargs

    def conclude(self, task_result: ECMTaskResult) -> ECMTaskResult:
        log.info(f"Task completed in {task_result.runtime()}s")
        return task_result


if __name__ == "__main__":
    task = WinTaskPoC()
    task.cli()
