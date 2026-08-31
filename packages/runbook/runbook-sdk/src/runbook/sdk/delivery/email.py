"""Provider-neutral email delivery for already-published report HTML."""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from importlib import metadata
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from loguru import logger
from runbook.core import BlobStore, ReportProfile
from runbook.sdk.execution import ReportResult

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*?)>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"""(?P<name>[^\s=/>]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)\2""", re.DOTALL)


class EmailDeliveryError(ValueError):
    """Raised when a report cannot be prepared or sent by the email seam."""


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class EmailMessage:
    to: tuple[str, ...]
    cc: tuple[str, ...]
    subject: str
    text_body: str
    attachments: tuple[EmailAttachment, ...]


@dataclass(frozen=True)
class EmailSendReceipt:
    message_id: str | None = None


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> EmailSendReceipt:
        """Send one provider-neutral message."""


def _entry_points(group: str, name: str) -> list[Any]:
    """Return exact entry-point matches across supported metadata APIs."""
    discovered = metadata.entry_points()
    if hasattr(discovered, "select"):
        return list(discovered.select(group=group, name=name))
    if isinstance(discovered, dict):
        return [item for item in discovered.get(group, ()) if getattr(item, "name", None) == name]
    return [
        item for item in discovered if getattr(item, "group", None) == group and getattr(item, "name", None) == name
    ]


def _entry_point_key(entry_point: Any) -> tuple[str, str, str]:
    """Return a stable sort key for an installed entry point."""
    distribution = getattr(entry_point, "dist", None)
    metadata_value = getattr(distribution, "metadata", {}) if distribution is not None else {}
    return (
        str(metadata_value.get("Name", "")).casefold(),
        str(getattr(entry_point, "value", "")),
        str(getattr(entry_point, "name", "")),
    )


def _provider_id(value: str) -> str:
    """Validate a provider identifier before querying installed metadata."""
    if not isinstance(value, str):
        raise EmailDeliveryError("email provider must be a safe lowercase identifier")
    if not _ID.fullmatch(value):
        raise EmailDeliveryError("email provider must be a safe lowercase identifier")
    return value


def load_email_sender(provider: str) -> EmailSender:
    """Load one zero-argument sender factory from the public entry-point group."""
    provider_id = _provider_id(provider)
    try:
        matches = sorted(_entry_points("runbook.email_senders", provider_id), key=_entry_point_key)
    except Exception:
        raise EmailDeliveryError(f"failed discovering email sender for provider {provider_id!r}") from None
    if not matches:
        raise EmailDeliveryError(f"no email sender is installed for provider {provider_id!r}")
    if len(matches) > 1:
        names = ", ".join(
            f"{getattr(getattr(item, 'dist', None), 'name', 'unknown')}:{getattr(item, 'value', '')}"
            for item in matches
        )
        raise EmailDeliveryError(f"multiple email senders are installed for provider {provider_id!r}: {names}")
    try:
        factory = matches[0].load()
    except Exception:
        raise EmailDeliveryError(f"failed loading email sender for provider {provider_id!r}") from None
    if not callable(factory):
        raise EmailDeliveryError(f"email sender entry point for provider {provider_id!r} is not callable")
    try:
        sender = factory()
    except Exception:
        raise EmailDeliveryError(f"email sender factory failed for provider {provider_id!r}") from None
    if not callable(getattr(sender, "send", None)):
        raise EmailDeliveryError(f"email sender for provider {provider_id!r} has no callable send method")
    return sender


def reports_base_url(value: str | None = None) -> str | None:
    """Return a validated deployment-level reporting URL."""
    raw = value if value is not None else os.environ.get("RUNBOOK_REPORTS_BASE_URL")
    if raw is None:
        return None
    if (
        not isinstance(raw, str)
        or not raw
        or any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in raw)
    ):
        raise EmailDeliveryError("RUNBOOK_REPORTS_BASE_URL must be an http(s) URL without credentials")
    try:
        parsed = urlsplit(raw)
        has_userinfo = parsed.username is not None or parsed.password is not None
    except ValueError:
        raise EmailDeliveryError("RUNBOOK_REPORTS_BASE_URL must be an http(s) URL without credentials") from None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or has_userinfo:
        raise EmailDeliveryError("RUNBOOK_REPORTS_BASE_URL must be an http(s) URL without credentials")
    if parsed.query or parsed.fragment or "?" in raw or "#" in raw:
        raise EmailDeliveryError("RUNBOOK_REPORTS_BASE_URL must not contain a query or fragment")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _semantic_attributes(tag: str) -> dict[str, tuple[str, int, int]]:
    """Extract quoted attributes from one generated anchor tag."""
    attrs: dict[str, tuple[str, int, int]] = {}
    for match in _ATTR_RE.finditer(tag):
        attrs[match.group("name").lower()] = (
            match.group("value"),
            match.start("value"),
            match.end("value"),
        )
    return attrs


def _dashboard_href(base: str, segments: tuple[str, ...]) -> str:
    """Build a dashboard URL while encoding each logical path segment."""
    return "/".join((base.rstrip("/"), *(quote(segment, safe="") for segment in segments)))


def rewrite_dashboard_links(
    html_text: str,
    *,
    current_report_id: str,
    dashboard_base_url: str | None,
) -> str:
    """Rewrite only Runbook semantic report and plot anchors in a copy of HTML."""
    base = reports_base_url(dashboard_base_url)
    semantic_found = False

    def replace_anchor(match: re.Match[str]) -> str:
        """Rewrite one semantic anchor or leave an authored anchor untouched."""
        nonlocal semantic_found
        tag = match.group(0)
        attrs = _semantic_attributes(tag)
        kind = attrs.get("data-runbook-link-kind", ("", 0, 0))[0].lower()
        if kind not in {"report", "plot"}:
            return tag
        semantic_found = True
        if base is None:
            raise EmailDeliveryError("dashboard_base_url_required")
        href_attr = attrs.get("href")
        if href_attr is None:
            raise EmailDeliveryError("semantic link is missing href")
        if kind == "report":
            report_attr = attrs.get("data-runbook-report-id")
            if report_attr is None or not report_attr[0]:
                raise EmailDeliveryError("semantic report link is missing report ID")
            href = _dashboard_href(base, ("reports", report_attr[0]))
        else:
            plot_attr = attrs.get("data-runbook-plot-name")
            if plot_attr is None or not plot_attr[0]:
                raise EmailDeliveryError("semantic plot link is missing plot name")
            href = _dashboard_href(base, ("reports", current_report_id, "plots", plot_attr[0]))
        value_start, value_end = href_attr[1:]
        return tag[:value_start] + escape(href, quote=True) + tag[value_end:]

    rewritten = _ANCHOR_RE.sub(replace_anchor, html_text)
    if semantic_found:
        return rewritten
    return html_text


def build_report_email_attachment(
    store: BlobStore,
    result: ReportResult,
    *,
    dashboard_base_url: str | None,
) -> EmailAttachment:
    """Package an immutable report HTML copy as a deterministic ZIP."""
    html_text = store.get(result.html_ref).decode("utf-8")
    emailed_html = rewrite_dashboard_links(
        html_text,
        current_report_id=result.report_id,
        dashboard_base_url=dashboard_base_url,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        info = zipfile.ZipInfo("report.html", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o600 << 16
        archive.writestr(info, emailed_html.encode("utf-8"))
    return EmailAttachment(
        filename=f"{result.report_id}.zip",
        content_type="application/zip",
        content=output.getvalue(),
    )


def build_report_email(
    *,
    profile: ReportProfile,
    result: ReportResult,
    attachment: EmailAttachment,
    dashboard_base_url: str | None = None,
) -> EmailMessage:
    """Build the deterministic plain-text message for one published report."""
    delivery = profile.delivery
    if delivery is None or delivery.email is None:
        raise EmailDeliveryError("email delivery is not configured")
    email = delivery.email
    base = reports_base_url(dashboard_base_url)
    title = profile.title or result.report_id
    lines = [title, ""]
    if base is not None:
        lines.extend(["View report:", _dashboard_href(base, ("reports", result.report_id)), ""])
    else:
        lines.extend([f"Report ID: {result.report_id}", ""])
    lines.extend(
        [
            f"Snapshot: {result.snapshot_id}",
            f"Artifact: {result.artifact_id}",
            "",
            "The generated HTML report is attached.",
        ]
    )
    return EmailMessage(
        to=email.to,
        cc=email.cc,
        subject=email.subject or title,
        text_body="\n".join(lines),
        attachments=(attachment,),
    )


def _previous_attempts(previous: dict[str, Any] | None) -> int:
    """Read a prior attempt count from either delivery metadata shape."""
    if not isinstance(previous, dict):
        return 0
    value: Any = previous.get("attempts")
    nested = previous.get("email")
    if value is None and isinstance(previous.get("delivery"), dict):
        nested = previous["delivery"].get("email")
    if value is None and isinstance(nested, dict):
        value = nested.get("attempts")
    return value if isinstance(value, int) and value >= 0 else 0


def attempt_report_email_delivery(
    *,
    store: BlobStore,
    profile: ReportProfile,
    result: ReportResult,
    dashboard_base_url: str | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Attempt delivery while keeping provider errors out of report execution."""
    delivery = profile.delivery
    if delivery is None or delivery.email is None:
        return None
    provider = delivery.email.provider
    attempts = _previous_attempts(previous) + 1
    attempted_at = datetime.now(timezone.utc).isoformat()
    started = datetime.now(timezone.utc)
    try:
        base = reports_base_url(dashboard_base_url) if dashboard_base_url is not None else reports_base_url()
        sender = load_email_sender(provider)
        attachment = build_report_email_attachment(store, result, dashboard_base_url=base)
        message = build_report_email(profile=profile, result=result, attachment=attachment, dashboard_base_url=base)
        receipt = sender.send(message)
        message_id = getattr(receipt, "message_id", None)
        outcome: dict[str, Any] = {
            "status": "sent",
            "provider": provider,
            "attempts": attempts,
            "attempted_at": attempted_at,
        }
        if isinstance(message_id, str) and message_id:
            outcome["message_id"] = message_id
        logger.info(
            "email delivery status=sent provider={} duration_ms={}",
            provider,
            int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        )
        return outcome
    except Exception as exc:
        logger.warning(
            "email delivery status=failed provider={} error_type={} duration_ms={}",
            provider,
            type(exc).__name__,
            int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        )
        return {
            "status": "failed",
            "provider": provider,
            "attempts": attempts,
            "attempted_at": attempted_at,
            "error": type(exc).__name__,
        }


__all__ = [
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailMessage",
    "EmailSendReceipt",
    "EmailSender",
    "attempt_report_email_delivery",
    "build_report_email",
    "build_report_email_attachment",
    "load_email_sender",
    "reports_base_url",
    "rewrite_dashboard_links",
]
