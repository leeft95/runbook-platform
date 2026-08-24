"""Small package-entry-point discovery helpers for ingest extensions."""

from __future__ import annotations

from importlib import metadata
from typing import Any


class EntryPointDiscoveryError(ValueError):
    """Raised when an installed entry point cannot be resolved safely."""


def _matches(group: str, name: str) -> list[Any]:
    """Select exact entry-point matches across supported metadata APIs."""
    discovered = metadata.entry_points()
    if hasattr(discovered, "select"):
        return list(discovered.select(group=group, name=name))
    if isinstance(discovered, dict):  # pragma: no cover - Python 3.9 compatibility
        return [item for item in discovered.get(group, ()) if item.name == name]
    return [item for item in discovered if item.group == group and item.name == name]


def _sort_key(entry_point: Any) -> tuple[str, str, str]:
    """Return a stable distribution/value ordering key."""
    distribution = getattr(entry_point, "dist", None)
    metadata_value = getattr(distribution, "metadata", {}) if distribution is not None else {}
    distribution_name = str(metadata_value.get("Name", ""))
    return distribution_name.casefold(), str(getattr(entry_point, "value", "")), str(entry_point)


def _describe(entry_point: Any) -> str:
    """Return a concise entry-point description for configuration errors."""
    distribution = getattr(entry_point, "dist", None)
    metadata_value = getattr(distribution, "metadata", {}) if distribution is not None else {}
    distribution_name = metadata_value.get("Name") or "unknown distribution"
    return f"{distribution_name}:{getattr(entry_point, 'value', entry_point)}"


def find_named_entry_points(group: str, name: str) -> list[Any]:
    """Return exact group/name matches in deterministic order."""
    return sorted(_matches(group, name), key=_sort_key)


def load_named_entry_point(group: str, name: str) -> object:
    """Load one exact-name entry point, rejecting missing and duplicate matches."""
    matches = find_named_entry_points(group, name)
    if not matches:
        raise EntryPointDiscoveryError(f"no entry point group={group!r} name={name!r}")
    if len(matches) > 1:
        found = ", ".join(_describe(item) for item in matches)
        raise EntryPointDiscoveryError(f"duplicate entry points group={group!r} name={name!r}: {found}")
    try:
        return matches[0].load()
    except Exception as exc:
        raise EntryPointDiscoveryError(f"failed loading entry point group={group!r} name={name!r}: {exc}") from None


__all__ = ["EntryPointDiscoveryError", "find_named_entry_points", "load_named_entry_point"]
