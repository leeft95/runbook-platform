"""Generic post-publication email delivery contracts."""

from .email import (
    EmailAttachment,
    EmailDeliveryError,
    EmailMessage,
    EmailSender,
    EmailSendReceipt,
    attempt_report_email_delivery,
    build_report_email,
    load_email_sender,
    reports_base_url,
    rewrite_dashboard_links,
)

__all__ = [
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailMessage",
    "EmailSendReceipt",
    "EmailSender",
    "attempt_report_email_delivery",
    "build_report_email",
    "load_email_sender",
    "reports_base_url",
    "rewrite_dashboard_links",
]
