from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from runbook.sdk.authoring import REPORT_CALC_ATTR, REPORT_INTERACTION_ATTR, REPORT_PAGE_ATTR, RequiredAliases


@dataclass(frozen=True)
class ReportDefinition:
    aliases: list[str]
    calc_fns: dict[str, Callable[..., Any]]
    page_fn: Callable[..., Any]
    interaction_fns: dict[str, Callable[..., Any]] | None = None

    def __post_init__(self) -> None:
        if self.interaction_fns is None:
            object.__setattr__(self, "interaction_fns", {})


def discover_report_definition(module: Any) -> ReportDefinition:
    """Handle discover report definition."""
    aliases = getattr(module, "ALIASES", None)
    if not isinstance(aliases, RequiredAliases):
        raise AttributeError("report must define ALIASES = required_aliases(...)")
    calc_fns: dict[str, Callable[..., Any]] = {}
    page_fns: list[Callable[..., Any]] = []
    interaction_fns: dict[str, Callable[..., Any]] = {}
    for value in module.__dict__.values():
        if not callable(value):
            continue
        calc_name = getattr(value, REPORT_CALC_ATTR, None)
        if calc_name is not None:
            if calc_name in calc_fns:
                raise ValueError(f"duplicate report calculation: {calc_name!r}")
            calc_fns[str(calc_name)] = value
        if getattr(value, REPORT_PAGE_ATTR, None) is not None:
            page_fns.append(value)
        interaction_name = getattr(value, REPORT_INTERACTION_ATTR, None)
        if interaction_name is not None:
            if interaction_name in interaction_fns:
                raise ValueError(f"duplicate report interaction: {interaction_name!r}")
            interaction_fns[str(interaction_name)] = value
    if not calc_fns or len(page_fns) != 1:
        raise AttributeError("report requires calculations and exactly one page function")
    return ReportDefinition(sorted(aliases.values()), calc_fns, page_fns[0], interaction_fns)
