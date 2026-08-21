"""Capability protocols for optional live report data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeAlias, runtime_checkable

JSONValue: TypeAlias = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


class LiveCapabilityUnavailableError(RuntimeError):
    """Raised when a report requests live data without an injected provider."""


@runtime_checkable
class LiveQuerySource(Protocol):
    """One logical live query source."""

    def query(self, statement: str, params: Mapping[str, JSONValue] | None = None) -> Any:
        """Execute a parameterized query against the logical source."""


@runtime_checkable
class LiveDataResolver(Protocol):
    """Resolve logical names to live query sources."""

    def sql(self, name: str) -> LiveQuerySource:
        """Resolve one logical SQL source name."""


class _UnavailableLiveDataResolver:
    def sql(self, name: str) -> LiveQuerySource:
        """Reject live access when no runtime capability was injected."""
        raise LiveCapabilityUnavailableError(
            f"live data capability is unavailable; cannot resolve logical source {name!r}"
        )


UNAVAILABLE_LIVE_RESOLVER: LiveDataResolver = _UnavailableLiveDataResolver()

__all__ = [
    "JSONValue",
    "LiveCapabilityUnavailableError",
    "LiveDataResolver",
    "LiveQuerySource",
    "UNAVAILABLE_LIVE_RESOLVER",
]
