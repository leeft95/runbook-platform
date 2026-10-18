import base64
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from ecm.atom.services import context
from ecm.cmds.core.to_html import HTML
from ecm.cmds.core.utils import convert_path_to_linux
from premailer import transform

link_end_rgx = r"\.html?(?:#.*)?|\.pdf"


def fix_up_html_links(html):
    soup = BeautifulSoup(html, "html.parser")
    website_prefix = "https://lo25.elementcapital.com"
    for link in soup.find_all("a"):
        if link.get("href"):
            lnk = link["href"]
            if lnk.endswith("xlsx") or lnk.endswith("xls"):
                if lnk.startswith(".."):
                    lnk = lnk.replace("..", "file://elementcapital.corp/ecns01/PM/Michel%20Kikano")
                if lnk.startswith("//elementcapital"):
                    lnk = lnk.replace("//elementcapital", "file://elementcapital")
                open_exl_pfx = "ms-excel:ofe|u|"
                if lnk.startswith(open_exl_pfx):
                    continue
                modded_link = open_exl_pfx + lnk
                link["href"] = modded_link
            elif re.findall(link_end_rgx, lnk):
                modded_link = lnk.replace("\\", "/").replace("file:", "")
                if modded_link.startswith("//elementcapital") or modded_link.startswith("/mnt/h"):
                    modded_link = (
                        modded_link.replace("//elementcapital.corp/ecns01/PM/Michel Kikano", "")
                        .replace("//elementcapital.corp/ECNS01/PM/Michel Kikano", "")
                        .replace("//elementcapital.corp/ecns01/PM/Michel%20Kikano", "")
                        .replace("/mnt/h/code", "CODE")
                    )
                    if not modded_link.startswith("/"):
                        modded_link = "/" + quote(modded_link, safe="/")
                    raise NotImplementedError("Unrecoverable page-viewer quoting arguments: IMG_5589.JPG:42")
                elif modded_link.startswith(".."):
                    modded_link = (
                        modded_link.replace("../", "")
                        .replace("ecns01/PM/Michel%20Kikano", "")
                        .replace("ecns01/PM/Michel Kikano", "")
                        .replace("ECNS01/PM/Michel Kikano", "")
                        .replace("/mnt/h/code", "CODE")
                    )
                    if not modded_link.startswith("/"):
                        modded_link = "/" + quote(modded_link, safe="/")
                    raise NotImplementedError("Unrecoverable page-viewer quoting arguments: IMG_5589.JPG:53")
                else:
                    link["href"] = modded_link.replace("https://lo25.wagyu.elementcapital.corp", website_prefix)
            else:
                continue
    full_html = str(soup)
    return full_html


def send_email(send_to, subject, body, **kwargs):
    """
    imgs is dict with format - image name: image file path
    """
    send_from = kwargs.get("send_from", "CmdRprt")
    reply_to = kwargs.get("reply_to", "CmdRprt")
    body_end = kwargs.get("body_end", None)
    attachments = kwargs.get("attachments", None)
    imgs = kwargs.get("imgs", None)
    use_premailer = kwargs.get("use_premailer", None)
    dashboard_url = kwargs.get("html_path")

    if send_to is None:
        return 0

    config = {"email": {"environment": "prod", "send_to": send_to, "pause_for_read": 1, "timeout": 180}}

    if isinstance(body, str):
        html_body = body
    else:
        html_body = HTML(body, fn=False, mode="email", div=False, path=None)
    if dashboard_url:
        dashboard_link = f'<a href="{dashboard_url}">Full Dashboard Page</a>'
        html_body = HTML(dashboard_link, fn=False, mode="email", div=False, path=None) + html_body
    html_body = fix_up_html_links(html_body)

    if imgs is not None:
        html_img = []
        if isinstance(imgs, dict):
            for key, val in imgs.items():
                with open(val, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode()
                html_img.append(
                    """{:s}<br> <img alt="Embedded Image" src="data:image/png;base64,{:s}"
                    /><br><br>""".format(
                        key, encoded_string
                    )
                )
        elif isinstance(imgs, list):
            for val in imgs:
                with open(val, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode()
                html_img.append(
                    """<br> <img alt="Embedded Image" src="data:image/png;base64,{:s}"
                    /><br><br>""".format(
                        encoded_string
                    )
                )
        html_body += HTML(html_img, fn=False, mode="email", div=False, path=None)

    if body_end is not None:
        html_body += HTML(body_end, fn=False, mode="email", div=False, path=None)

    if use_premailer:
        html_body = transform(html_body)
    if attachments is None:
        with context(config) as services:
            services.email.send_email(
                send_from=send_from,
                reply_to=reply_to,
                subject=subject,
                body=html_body,
            )
    else:
        if not isinstance(attachments, list):
            attachments = [attachments]
        attachments = [convert_path_to_linux(x) for x in attachments]
        with context(config) as services:
            services.email.send_email(
                send_from=send_from,
                reply_to=reply_to,
                subject=subject,
                attach=attachments,
                body=html_body,
            )
