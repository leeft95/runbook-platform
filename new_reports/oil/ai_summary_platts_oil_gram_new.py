import pandas as pd
import datetime as dt
import time
import os  # TRANSCRIPTION: credential environment substitutions.
import ecm.cmds.core.chatGPT2 as gpt
import ecm.cmds.table as table

from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, oil_group
from ai_summary_news_alerts_new import run_news_summary
from ecm.cmds.utils import convert_path_to_linux
from pathlib import Path
from bs4 import BeautifulSoup
from loguru import logger as log

report_name = "Platts Oil Gram AI Summary"
file_name = "ai_summary_platts_oil_gram"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in ai_summary_platts_oil_gram_new.py, photographed lines {lines}")


def normalize_font(html: str, family="Calibri"):
    """Normalize the font of an HTML string to the specified family."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(style=True):
        decls = []
        for part in tag["style"].split(";"):
            p = part.strip()
            if not p or p.lower().startswith("font-family"):
                continue
            decls.append(p)
        tag["style"] = "; ".join(decls) if decls else ""
    css = f"body, body * {{ font-family: {family}, Arial, sans-serif !important; }}"
    existing_style = soup.find("style", attrs={"data-font-normalize": True})
    if existing_style:
        existing_style.string = css
    else:
        style_tag = soup.new_tag("style", **{"data-font-normalize": "true"})
        style_tag.string = css
        if soup.head:
            soup.head.insert(0, style_tag)
        else:
            soup.insert(0, style_tag)
    return str(soup)


openai_key = os.environ["OPENAI_API_KEY"]  # TRANSCRIPTION: credential at55 replaced.
already_processed_record = convert_path_to_linux(f"{root_path}\\data\\ai_summary\\record_oil.csv")
reports_base_path = Path(f"{root_path}\\data")
email_base_path = reports_base_path / "ai_summary"
platts = Path(convert_path_to_linux(reports_base_path / "platts" / "files"))
email_text_us = email_base_path / "US"
email_text_north_sea = email_base_path / "North_Sea"
email_text_waf = email_base_path / "West_Africa"
email_text_me = email_base_path / "Middle_East"
crude_sources = {
    "US": [platts, email_text_us / "Crude"],
    "WAF": [platts, email_text_waf / "Crude"],
    "NSea": [platts, email_text_north_sea / "Crude"],
    "MiddleEast": [platts, email_text_me / "Crude"],
}
output_html_path = f"{html_path}\\AI_Summary\\oil"


def get_latest_opr_report(min_date, base_path: Path, record: pd.DataFrame):
    all_valid_files = [x for x in base_path.iterdir() if x.suffix == f".pdf"]
    processed_files = record.file_name.values
    for fle in all_valid_files:
        date = dt.datetime.strptime(fle.stem.split("_")[-1], "%Y%m%d")
        if date.date() == min_date.date():
            if not fle.stem in processed_files:
                return fle
            else:
                print(f"{fle.stem} already processed")
    else:
        print(f"Could not find file for {min_date}")


regions = ["Americas/US", "West Africa", "North Sea", "Middle East/Asia"]
sentiment_prompt = "Is sentiment in the report for the oil markets bullish or bearish? provide evidence"
general_prompt = None
model_instructions = None


def to_html_list_item(items):
    link_list = "<ul>"
    for lt, lnk in items.items():
        link_list += f"<li><a href='{lnk}' target='_blank'>{lt}</a></li>"
    link_list += "</ul>"
    return link_list


def run_platts_summary(run_date=None, send_to=None):
    if not run_date:
        run_date = dt.datetime.today() - dt.timedelta(days=1)
    summary_record = pd.read_csv(already_processed_record)
    if "Unnamed: 0" in summary_record.columns:
        summary_record.drop(columns=["Unnamed: 0"], inplace=True)
    latest_platts_file = get_latest_opr_report(run_date, platts, summary_record)
    gpt_client = gpt.ChatGPTHelperV2(openai_key)
    summaries = []
    if latest_platts_file is not None:
        log.info(f"Processing {latest_platts_file.stem}")
        summaries.append("<H3>Platts Oil</H3>")
        log.info("General Query")
        time.sleep(20)
        has_summary = False
        while not has_summary:
            try:
                resp, _ = gpt_client.query(
                    message=general_prompt, files=latest_platts_file, vector_store_name="Platts",
                    model="gpt-5", temperature=None, timeout=300,
                )
            except RuntimeError as e:
                if "Sorry, something went wrong" in str(e):
                    log.info(f"Retrying Request :>>{e}")
                    resp = ["Could not find answer try again"]
                else:
                    raise e
            except TimeoutError as e:
                log.error(f"Vector store creation timed out: {e}")
                resp = ["Could not find answer try again"]
                time.sleep(60)
            if any(x for x in resp if "Could not find answer try again" in x):
                time.sleep(10)
            else:
                has_summary = True
        summaries.append("<br/>".join(resp))
        summaries.append("<br/><br/>")
        summaries.append("<hr>")
    summaries.append("<br/><H3>NAlrt&LSEG News Summary</H3><br/>")
    summary = run_news_summary(run_date, ret_only=True, eod=True)
    if summary is None:
        summary = "No files available"
    summary = normalize_font("".join(summary))
    summaries.append(summary)
    print(f"News for summaries complete")
    if len(summaries) > 2:
        email_text = []
        for resp in summaries:
            if resp is None:
                continue
            resp = (resp.replace("```html", "")
                    .replace("```", "")
                    .replace("<H1>", "<H3>")
                    .replace("</H1>", "</H3>")
                    .replace("<H2>", "<H5>")
                    .replace("</H2>", "</H5>")
                    .replace("font-family: times new roman;", "font-family: Calibri;")
                    .replace("font-family: Times New Roman;", "font-family: Calibri;"))
            email_text.append(normalize_font(resp))
        end_of_email = "<br/>This AI Summary of the " + _missing_photo_text("178: {latest_platts_file.stem if latest_platts_file is not N...")
        email_text.append(end_of_email)
        save_path = f"{output_html_path}\\{run_date.strftime('%Y%m%d')}_summary.html"
        save_path_latest = f"{output_html_path}\\oil_latest_summary.html"
        html_file = []
        run_date_str = run_date.strftime('%Y-%m-%d')
        opr_file_name = latest_platts_file.stem if latest_platts_file is not None else _missing_photo_text("185: ERROR: No Platts fo...")
        html_file.append(f"<H3> AI Summary of {opr_file_name} and bbg/lseg for " + _missing_photo_text("186: {run_date.strftime('%Y-%m-%d'..."))
        html_file.append("<strong>Sources:</strong>")
        file_dict = {x.stem if x is not None else run_date_str: str(x if x is not None else "Missing")
                     for x in _missing_photo_text("188")}
        html_file.append(to_html_list_item(file_dict))
        html_file.append("<hr>")
        html_file.extend(email_text)
        table.figures_to_html(html_file, filename=save_path_latest, task_name=report_name)
        table.figures_to_html(html_file, filename=save_path, task_name=report_name)
        send_email(send_to=send_to, subject=f"Oil AI Summary for {run_date.strftime('%Y-%m-%d')}",
                   body=_missing_photo_text("194: [ema..."))


def update_ai_vector_store():
    """Update the AI vector store with the latest Platts Oil Gram reports from the last 90 days."""
    from ecm.cmds.core.chatGPT2 import ChatGPTHelperV2
    openai_key = os.environ["OPENAI_API_KEY"]  # TRANSCRIPTION: credential at202 replaced.
    gpt_client = ChatGPTHelperV2(openai_key)
    vector_store_id = "vs_69403e127ca881919437dfc31b6fb71e"  # Platts Oil Gram Vector Store ID
    platts_path = Path(convert_path_to_linux(f"{root_path}\\data\\platts\\files"))
    cutoff_date = dt.datetime.now() - dt.timedelta(days=90)
    all_files = []
    for x in platts_path.iterdir():
        if x.suffix == ".pdf":
            try:
                file_date = dt.datetime.strptime(x.stem.split("_")[-1], "%Y%m%d")
                if file_date >= cutoff_date:
                    all_files.append(x)
            except ValueError:
                log.warning(f"Could not parse date from filename: {x.name}")
    log.info(f"Updating vector store with {len(all_files)} files from last 90 days")
    gpt_client.update_vector_store(vector_store_id=vector_store_id, files=all_files)
    log.info("Checking for old files to remove from vector store...")
    try:
        vs_files = gpt_client.client.vector_stores.files.list(vector_store_id=vector_store_id)
        files_to_remove = []
        for vs_file in vs_files.data:
            try:
                file_obj = gpt_client.client.files.retrieve(vs_file.id)
                if file_obj.filename.endswith('.pdf'):
                    file_date_str = file_obj.filename.split("_")[-1].replace(".pdf", "")
                    try:
                        file_date = dt.datetime.strptime(file_date_str, "%Y%m%d")
                        if file_date < cutoff_date:
                            files_to_remove.append(vs_file.id)
                            log.info(f"Marking old file for removal: {file_obj.filename} (date: {file_date.date()})")
                    except ValueError:
                        log.warning(f"Could not parse date from filename: {file_obj.filename}")
            except Exception as e:
                log.warning(f"Error checking file {vs_file.id}: {e}")
        if files_to_remove:
            log.info(f"Removing {len(files_to_remove)} old files from vector store")
            gpt_client.delete_vector_store_files(vector_store_id=vector_store_id, file_ids=files_to_remove)
            log.info("Deleting old files from OpenAI storage")
            gpt_client.delete_files(file_ids=files_to_remove)
        else:
            log.info("No old files found to remove")
    except Exception as e:
        log.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    run_platts_summary(send_to=oil_group)
    update_ai_vector_store()
