"""Small helpers for source locator and filename templates."""

from __future__ import annotations

from calendar import month_name
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def template_values(*, acquisition_run: str, observed_at: datetime) -> dict[str, object]:
    """Handle template values."""
    return {
        "acquisition_run": acquisition_run,
        "slot": acquisition_run,
        "observed_at": observed_at.isoformat(),
        "year": observed_at.year,
        "month": observed_at.month,
        "month_name": month_name[observed_at.month],
        "full_month_english": month_name[observed_at.month],
    }


def render_template(template: object, *, acquisition_run: str, observed_at: datetime) -> str | None:
    """Render template."""
    if not isinstance(template, str) or not template:
        return None
    return template.format(**template_values(acquisition_run=acquisition_run, observed_at=observed_at))


def filename_from_locator(locator: str) -> str:
    """Handle filename from locator."""
    return Path(urlparse(locator).path).name or "source.bin"


__all__ = ["filename_from_locator", "render_template", "template_values"]
