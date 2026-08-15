"""Compatibility entrypoints for the canonical data ingest package."""

from __future__ import annotations

from datetime import datetime, timezone


def slot_key(slot: datetime) -> str:
    """Return the canonical UTC acquisition-slot key."""
    if slot.tzinfo is None:
        raise ValueError("slot datetime must be timezone-aware")
    return slot.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


__all__ = ["slot_key"]
