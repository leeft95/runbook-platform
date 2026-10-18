import pandas as pd
import datetime as dt
import sys
import typing as tp
import time
import os  # TRANSCRIPTION: environment lookup replaces photographed credential.

from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, oil_group

from bs4 import BeautifulSoup
from pathlib import Path
import ecm.cmds.core.chatGPT2 as gpt
from ecm.cmds.utils import convert_path_to_linux
import pytz
from loguru import logger as log
import httpx

report_name = "News Alerts AI Summary"
file_name = "ai_summary_news_alerts"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
send_to = oil_group


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in ai_summary_news_alerts_new.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 22, 0), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


already_processed_for_day_record = convert_path_to_linux(f"{root_path}\\data\ai_summary\\record.csv")
reports_base_path = Path(f"{root_path}\\data")
email_base_path = reports_base_path / "ai_summary"
platts = reports_base_path / "platts" / "files"
email_text_us = email_base_path / "US"
email_text_north_sea = email_base_path / "North_Sea"
email_text_waf = email_base_path / "West_Africa"
email_text_me = email_base_path / "Middle_East"
email_text_ge = email_base_path / "UNCATEGORIZED"

crude_sources = {
    "Americas/US": email_text_us / "Crude",
    "West Africa": email_text_waf / "Crude",
    "North Sea": email_text_north_sea / "Crude",
    "Asia": email_text_me / "Crude",
    "General News": email_text_ge / "Crude"
}
intraday_sources = {
    "Asia": ["ASIA CRUDE", "News Middle East Crude"],
    "North Sea/West Africa": ["NSEA CRUDE", "News North Sea Crude", "WAF CRUDE", "News W.Africa Crude"],
    "Americas/US": ["News US Cash Crude", "AMERICAS CRUDE"],
    "General News": ["General News"]
}
intraday_timings_utc = {
    "Asia": ["08:30", "12:30"],
    "North Sea/West Africa": ["16:30", "19:30"]
}
send_anyway_times = {
    "Asia": ["12:25", "12:30"],
    "North Sea/West Africa": ["19:25", "19:30"]
}
general_prompt = "Provide a bulleted summary of the main developments"
openai_key = os.environ["OPENAI_API_KEY"]  # TRANSCRIPTION: replaces embedded credential at88.
_key_to_email_subject = {
    "Americas/US": "AMERICAS",
    "North Sea/West Africa": "North Sea and WAF",
    "Asia": "ASIA",
    "General News": "General"
}


def get_all_files_for_date(source_path: Path, dt: dt.datetime) -> tp.List[Path]:
    date_path = Path(convert_path_to_linux(source_path / dt.strftime("%Y%m%d")))
    if date_path.exists():
        all_files = [x for x in date_path.glob("*.html")]
    else:
        all_files = []
    return all_files


def _check_subject(subject: str, valid_subjects: tp.List[str]) -> bool:
    if not isinstance(valid_subjects, list):
        valid_subjects = [valid_subjects]
    test_list = []
    for x in valid_subjects:
        if isinstance(x, list):
            test_list.extend(x)
        else:
            test_list.append(x)
    valid_subjects = [x.upper() for x in test_list]
    if any(x in subject.upper() for x in valid_subjects):
        return True
    return False


def run_news_summary(run_date=None, ret_only: bool = False, sources: tp.List[str] = None, eod=False):
    if not run_date:
        run_date = dt.datetime.today()
    if not sources:
        sources = ["Asia", "North Sea/West Africa", "Americas/US", "General News"]
    summaries = {}
    additional_instructions = "format the Answer in html format within a body tag with headings no bigger th" + _missing_photo_text("127")
    if sources == ["North Sea/West Africa"] or sources == ["Asia", "North Sea/West Africa", "Americas/US", "General News"]:
        email_subjects = {x: intraday_sources[x] for x in sources}
    else:
        email_subjects = {x: intraday_sources[x] for x in sources if x in crude_sources.keys()}
    processed_record = pd.read_csv(already_processed_for_day_record)
    processed_record_today = processed_record[processed_record["date"] == run_date.strftime("%Y-%m-%d")]
    valid_files = {}
    for key in email_subjects.keys():
        valid_files = {}
        if key not in sources:
            continue
        if "/" in key and key == "North Sea/West Africa":
            latest_files = get_all_files_for_date(crude_sources[key.split("/")[0]], run_date) + get_all_files_for_date(crude_sources[key.split("/")[1]], run_date)
        else:
            latest_files = get_all_files_for_date(crude_sources[key], run_date)
            print(latest_files)
        if len(latest_files) > 0:
            if key == "General News":
                valid_files = {"General News": latest_files}
            else:
                valid_files = dict(valid_files, **_missing_photo_text("150"))
            if (key != "General News") and (len(email_subjects[key]) != len(valid_files.values())):
                unavailable_sources = [x for x in email_subjects[key] if x not in valid_files.keys()]
                print(f"Source(s) {unavailable_sources} not available for {key}")
                if not eod:
                    valid_files = {}
        if len(valid_files.values()) > 0:
            if not ret_only and _key_to_email_subject[key] in processed_record_today.source.values:
                print(f"{key} already processed")
                continue
            print(f"Processing {key} for {run_date}")
            has_summary = False
            while not has_summary:
                qry_prmt = "Provide a detailed bulleted summary of the main developments, title it as '" + _missing_photo_text("164: {_ke...")
                print(f"{qry_prmt}")
                gpt_client = gpt.ChatGPTHelperV2(openai_key)
                try:
                    resp, _ = gpt_client.query(
                        vector_store_name="news_alerts", files=latest_files, message=qry_prmt,
                        model="gpt-5", temperature=None, clear_existing=False,
                    )
                except RuntimeError as e:
                    if "Sorry, something went wrong" in str(e):
                        log.info(f"Retrying Request :>>\n{e}")
                        resp = ["Could not find answer try again"]
                    else:
                        raise e
                except TimeoutError as e:
                    log.error(f"Vector store creation timed out: {e}")
                    time.sleep(120)
                    resp = ["Could not find answer try again"]
                if any(x for x in resp if "Could not find answer try again" in x):
                    time.sleep(10)
                else:
                    summary = resp
                    summaries[key] = summary
                    has_summary = True
                    log.info("Summaries generated")
            if len(summaries) > 0 and not ret_only:
                email_text = []
                for _, resp in summaries.items():
                    resp = ("<br/>".join(reversed(resp)).replace("```html", "")
                            .replace("```", "")
                            .replace("<H1>", "<H3>")
                            .replace("</H1>", "</H3>")
                            .replace("<H2>", "<H5>")
                            .replace("</H2>", "</H5>"))
                    email_text.append(resp)
                sources_text = "<strong>Sources:</strong><br/><ul>"
                for file in latest_files:
                    sources_text += f"<li><a href='{file}' target='_blank'>{file.stem}</a></li>"
                sources_text += "</ul>"
                email_text = [sources_text] + email_text
                end_of_email = "<br/>This AI Summary of the NI/LSEG News was generated on " + _missing_photo_text("214: {dt.datetime.now(...")
                email_text.append(end_of_email)
                send_email(send_to=send_to or "ltrindade",
                           subject=f"{_key_to_email_subject[key]} Physical A" + _missing_photo_text("216"))
                processed_record = pd.read_csv(already_processed_for_day_record)
                if processed_record.empty:
                    processed_record = pd.DataFrame(columns=["date", "source"]).set_index("date")
                else:
                    processed_record = processed_record.set_index("date")
                update_record = _missing_photo_text('222: pd.DataFrame({"date":[run_date.strftime("%Y-%m-%d")], "source":[_key_to_emai...')
                already_processed_record = pd.concat([processed_record, update_record], axis=0)
                already_processed_record.to_csv(already_processed_for_day_record)
                summaries = {}
    if len(summaries) > 0:
        email_text = []
        for _, resp in summaries.items():
            resp = ("<br/>".join(reversed(resp)).replace("```html", "")
                    .replace("```", "")
                    .replace("<H1>", "<H3>")
                    .replace("</H1>", "</H3>")
                    .replace("<H2>", "<H5>")
                    .replace("</H2>", "</H5>"))
            email_text.append(resp)
        return email_text


def update():
    current_dt = dt.datetime.now(tz=pytz.timezone("Europe/London")).replace(microsecond=0, second=0).replace(**_missing_photo_text("240"))
    for k, v in intraday_timings_utc.items():
        time_range = pd.date_range(start=f"{current_dt.strftime('%Y-%m-%d')} {v[0]}", **_missing_photo_text("242: end=current_dt.strf..."))
        send_anyway_time = pd.date_range(start=f"{current_dt.strftime('%Y-%m-%d')} {send_anyway_times[k][0]}", **_missing_photo_text("243"))
        if current_dt in time_range:
            print(f"Running for {k} on {current_dt}")
            if current_dt in send_anyway_time:
                eod = True
            else:
                eod = False
            run_news_summary(run_date=current_dt, ret_only=False, sources=[k], eod=eod)


if __name__ == '__main__':
    update()
