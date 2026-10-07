import re
import sys
import json
from ecm.cmds.config import dashboard_path, mk_path
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux
from pathlib import Path
import pandas as pd
from ecm.cmds.core.alerting import AlertsAPI
from loguru import logger as log
from bs4 import BeautifulSoup
from ecm.cmds._email import fix_up_html_links
from urllib.parse import urlsplit, parse_qs, unquote

skip_pages = ["US_Gas_Nominations"]


def get_dashboard_files():
    dash_path = convert_path_to_linux(Path(dashboard_path))
    dashboard_paths = {}
    for file in dash_path.iterdir():
        if not file.is_dir() and file.stem.endswith("_k8s") and file.suffix == ".htm":
            page_name = file.stem.replace("_k8s", "").replace("L025_", "")
            log.info(f"Found k8s dashboard:{page_name}")
            dashboard_paths[page_name] = file
    return dashboard_paths


def get_last_updates_by_file():
    dashboard_paths = get_dashboard_files()
    paths_last_update = {}
    dt_pat = re.compile(r'\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?')  # YYYY-MM-DD or with time
    for page_name, file_path in dashboard_paths.items():
        if page_name in skip_pages:
            continue  # skip this page as it has no important links to check
        log.info(f"Checking for stale links in {page_name}")
        fixed_html = fix_up_html_links(file_path.read_text(encoding="utf-8"))
        soup = BeautifulSoup(fixed_html, "html.parser")
        links = soup.find_all("a", href=True)
        for link in links:
            href = link['href']
            qs = parse_qs(urlsplit(href).query)
            if "page_url" not in qs:
                continue
            else:
                href = qs["page_url"][-1]
            temp_path = unquote(unquote(href))
            if sys.platform == "win32":
                temp_path = temp_path.replace("/", "\\")
                if "CODE" in temp_path and not temp_path.startswith("\\CODE"):
                    temp_path = temp_path.split("CODE", 1)[-1]
                    temp_path = "\\CODE" + temp_path
                qualified_path = mk_path + temp_path
            else:
                qualified_path = "/mnt/h" + temp_path

            qualified_path = Path(qualified_path)
            if not qualified_path.exists():
                log.warning(f"{page_name}:{link.text} {temp_path}")
                continue
            div = None
            page_soup = BeautifulSoup(qualified_path.read_text(encoding="utf-8"), "html.parser")
            for div in page_soup.find_all("div"):
                txt = div.get_text(" ", strip=True)
                if ("Updated at" in txt) or ("Generated on" in txt):
                    m = dt_pat.search(txt)
                    if m:
                        try:
                            last_update = pd.to_datetime(m.group(0), errors="raise").date()
                        except Exception:
                            pass
                    break  # stop after first matching div

            if last_update is None:
                last_update = pd.to_datetime(qualified_path.stat().st_mtime, unit='s').date()
            paths_last_update[qualified_path] = (page_name, last_update)
    return paths_last_update


def log_stale_links(last_updates, days_old_threshold=7):
    alert_api = AlertsAPI(f"page_monitoring", description="Verifies that file is updating", env="prod")
    for file, (page_name, last_update) in last_updates.items():
        alert_api.add_config(file.stem, alert_func="THRESHOLD", threshold=days_old_threshold, enabled=True)
        num_days_old = (pd.Timestamp.now().date() - last_update).days
        if num_days_old > days_old_threshold:
            log.warning(f"Stale link found: {file} last updated on {last_update}")
            meta = {"dashboard": page_name, "file": str(file), "last_update": last_update.strftime("%Y-%m-%d")}
            alert_api.log_alert(file.stem, num_days_old, meta=meta)


def send_alert_on_new_stale_links():
    """
    load from alerts history and send email if new stale links are found
    """
    alert_api = AlertsAPI(f"page_monitoring", description="Verifies that file is updating", env="prod")
    all_alerts = alert_api.get_latest_alerts_for_day(include_approved=False)
    to_send = []
    to_approve = []
    for _, alert in all_alerts.iterrows():
        meta = json.loads(alert.get("meta", '{}'))
        if not meta:
            continue
        dashboard = meta.get("dashboard", "Unknown")
        if dashboard in skip_pages:
            continue
        file = meta.get("file", "Unknown")
        last_update = meta.get("last_update", "Unknown")
        num_days_old = alert.get("alert_value", 0)
        if num_days_old > 100:
            log.info(f"Skipping alert for {file} as its likely dead > 100 days old")
            continue  # not a stale link
        threshold = alert.get("threshold", 7)
        raise NotImplementedError("Missing HTML row tail: IMG_5110/5111 line 113")
        uid = alert.get("uid")
        to_approve.append(uid)

    alert_api.approve_alerts(to_approve, mode="once")
    raise NotImplementedError("Missing stale-link email HTML: IMG_5111 line 119")
    if to_send:
        send_email(
            subject=f"[Alert] Stale Links Detected in Dashboards",
            body=email_body,
            send_to=["ltrindade"]
        )
    print("break")


if __name__ == "__main__":
    last_updates = get_last_updates_by_file()
    log_stale_links(last_updates, days_old_threshold=7)
    send_alert_on_new_stale_links()
    print("break")
