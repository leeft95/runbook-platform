import pandas as pd
import datetime as dt
import sys
import typing as tp
import time
import os
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import oil_group
from pathlib import Path
import ecm.cmds.chat_gpt as gpt
from ecm.cmds.utils import convert_path_to_linux
import pytz

report_name = "EOD Refineries AI Summary"
file_name = "ai_refineries_eod"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
send_to = oil_group
already_processed_for_day_record = None  # Unrecovered value; not referenced in the available source.
reports_base_path = Path(f"{root_path}\\data")
email_base_path = reports_base_path / "ai_summary"
email_text_path = email_base_path / "Refinery"
general_prompt = "Provide a bulleted summary of the updates"
openai_key = os.environ["OPENAI_API_KEY"]


def get_all_files_for_date(source_path: Path, dt: dt.datetime) -> tp.List[Path]:
    date_path = Path(convert_path_to_linux(source_path / dt.strftime("%Y%m%d")))
    if date_path.exists():
        all_files = [x for x in date_path.glob("*.html") if not "PEC" in x.stem]
    else:
        all_files = []
    return all_files


def run_news_summary(run_date=None, ret_only: bool = False):
    if not run_date:
        run_date = dt.datetime.today()
    all_files = get_all_files_for_date(email_text_path, run_date)
    print(f"Processing refineries eod for {run_date}")
    additional_instructions = (
        "format the Answer in html format within a body tag with headings no bigger than H3 and "
        "font style Calibri, no citations or unicode characters")
    has_summary = False
    summaries = []
    if len(all_files) == 0:
        print(f"No files found for {run_date.strftime('%Y-%m-%d')}")
        return
    while not has_summary:
        qry_prmt = (
            "Provide a detailed bulleted summary of the main developments in oil refineries operations, "
            "outages, maintenance and capacity changes, based on the email updates from industrialinfo. "
            "Order the updates by the total refinery capacity and then list the details for the refinery "
            "as sub bullets. "
            "Include all updates from the reports provided. Combining the updates for the same refinery "
            "into one bullet point and its sub bullets."
        )
        print(f"{qry_prmt}")
        gpt_client = gpt.ChatGPTHelperV2(openai_key)
        try:
            resp, _ = gpt_client.query(
                vector_store_name="refineries-eod",
                files=all_files,
                message=qry_prmt,
                model="gpt-5",
                temperature=None,
                timeout=300,
            )
        except RuntimeError as e:
            if "Sorry, something went wrong" in str(e):
                print(f"Retrying Request :>>\n{e}")
                resp = ["Could not find answer try again"]
            else:
                raise e
        except TimeoutError as e:
            print(f"Vector store creation timed out: {e}")
            time.sleep(120)
            resp = ["Could not find answer try again"]
        if any(x for x in resp if "Could not find answer try again" in x):
            time.sleep(10)
        else:
            summary_text = "<br/>".join(resp)
            summaries.append(summary_text)
            has_summary = True

    if len(summaries) > 0 and not ret_only:
        email_text = []
        for summary in summaries:
            summary = (summary.replace("```html", "")
                       .replace("```", "")
                       .replace("<H1>", "<H3>")
                       .replace("</H1>", "</H3>")
                       .replace("<H2>", "<H5>")
                       .replace("</H2>", "</H5>")
                       )
            email_text.append(summary)
        sources_text = "<strong>Sources:</strong><br/><ul>"
        for file in all_files:
            sources_text += f"<li><a href='{file}' target='_blank'>{file.stem}</a></li>"
        sources_text += "</ul>"
        email_text = [sources_text] + email_text
        end_of_email = f"<br/>This AI Summary of the EOD Refineries update was generated on {dt.datetime.now().strftime('%d/%m/%YT%H:%M:%S')}"
        email_text.append(end_of_email)
        send_email(send_to=send_to or "ltrindade", subject=f"EOD Refineries Update AI Summary for {run_date.strftime('%Y-%m-%d')}", body=email_text)

    if len(summaries) > 0 and ret_only:
        email_text = []
        for summary in summaries:
            summary = (summary.replace("```html", "")
                       .replace("```", "")
                       .replace("<H1>", "<H3>")
                       .replace("</H1>", "</H3>")
                       .replace("<H2>", "<H5>")
                       .replace("</H2>", "</H5>")
                       )
            email_text.append(summary)
        sources_text = "<strong>Sources:</strong><br/><ul>"
        for file in all_files:
            sources_text += f"<li><a href='{file}' target='_blank'>{file.stem}</a></li>"
        sources_text += "</ul>"
        email_text = [sources_text] + email_text
        return email_text


def update():
    raise NotImplementedError("Missing photographed date replacement: ai_refineries_eod.py line 126")
    run_news_summary(run_date=current_dt, ret_only=False)


if __name__ == '__main__':
    raise NotImplementedError("Missing photographed main block: ai_refineries_eod.py after line 129")
