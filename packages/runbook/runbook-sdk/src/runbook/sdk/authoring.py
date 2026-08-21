from __future__ import annotations

from dataclasses import dataclass
from keyword import iskeyword
from typing import Any, Callable

REPORT_CALC_ATTR = "__runbook_report_calc_name__"
REPORT_PAGE_ATTR = "__runbook_report_page__"
REPORT_INTERACTION_ATTR = "__runbook_report_interaction_name__"


@dataclass(frozen=True)
class RequiredAliases:
    _items: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self._items:
            raise TypeError("required_aliases(...) must declare at least one alias")
        attrs: set[str] = set()
        aliases: set[str] = set()
        for attr_name, alias in self._items:
            if not attr_name.isidentifier() or iskeyword(attr_name) or not alias:
                raise TypeError(f"invalid required alias: {attr_name!r} -> {alias!r}")
            if attr_name in attrs or alias in aliases:
                raise TypeError("required alias names and attributes must be unique")
            attrs.add(attr_name)
            aliases.add(alias)

    def __getattr__(self, name: str) -> str:
        for attr_name, alias in self._items:
            if attr_name == name:
                return alias
        raise AttributeError(name)

    def values(self) -> tuple[str, ...]:
        """Return aliases in deterministic declaration order."""
        return tuple(value for _, value in self._items)


def required_aliases(**aliases: str) -> RequiredAliases:
    """Declare the dataset aliases required by a report template."""
    return RequiredAliases(tuple(sorted(aliases.items())))


class _ReportNamespace:
    def calc(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Mark a function as a named lazy report calculation."""
        if not isinstance(name, str) or not name:
            raise TypeError("report.calc(name) requires a non-empty name")

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            """Attach the calculation marker to a report function."""
            setattr(fn, REPORT_CALC_ATTR, name)
            return fn

        return decorate

    def page(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Mark a function as the report page builder."""
        setattr(fn, REPORT_PAGE_ATTR, "page")
        return fn

    def interaction(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Mark a plain-Python function as a named report interaction handler."""
        if not isinstance(name, str) or not name:
            raise TypeError("report.interaction(name) requires a non-empty name")

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            """Attach the interaction marker to a report function."""
            setattr(fn, REPORT_INTERACTION_ATTR, name)
            return fn

        return decorate


report = _ReportNamespace()
