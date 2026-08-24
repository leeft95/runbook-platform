"""Reusable Stage 2 parser capabilities."""

from __future__ import annotations

import inspect
from collections.abc import Mapping

from runbook.data.ingest.discovery import EntryPointDiscoveryError, find_named_entry_points, load_named_entry_point
from runbook.data.ingest.parsers.base import Stage2Parser
from runbook.data.ingest.parsers.csv_timeseries import parse_csv_timeseries

_PARSERS: dict[str, Stage2Parser] = {
    "csv_timeseries_v1": parse_csv_timeseries,
}


def get_parser(parser_id: str) -> Stage2Parser:
    """Resolve and validate a built-in or installed parser."""
    if parser_id in _PARSERS:
        collisions = find_named_entry_points("runbook.parsers", parser_id)
        if collisions:
            raise ValueError(
                f"parser {parser_id!r} is reserved by a built-in; external entry point "
                f"group='runbook.parsers' name={parser_id!r} cannot shadow it"
            )
        return _PARSERS[parser_id]
    try:
        parser = load_named_entry_point("runbook.parsers", parser_id)
    except EntryPointDiscoveryError as exc:
        raise ValueError(f"unsupported parser_id: {parser_id!r}; {exc}") from None
    if not callable(parser):
        raise ValueError(
            f"incompatible parser entry point group='runbook.parsers' name={parser_id!r}: "
            "expected a callable Stage2Parser"
        )
    parameters: Mapping[str, inspect.Parameter]
    try:
        parameters = inspect.signature(parser).parameters
    except (TypeError, ValueError):  # pragma: no cover - uncommon extension callables
        parameters = {}
    required = {"source_config", "dataset_alias", "acquired"}
    if (
        parameters
        and not required <= parameters.keys()
        and not any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    ):
        raise ValueError(
            f"incompatible parser entry point group='runbook.parsers' name={parser_id!r}: "
            "callable must accept source_config, dataset_alias, and acquired"
        )
    return parser


__all__ = ["Stage2Parser", "get_parser"]
