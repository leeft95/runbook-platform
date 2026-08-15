"""Reusable Stage 2 parser capabilities."""

from __future__ import annotations

from runbook.data.ingest.parsers.base import Stage2Parser
from runbook.data.ingest.parsers.csv_timeseries import parse_csv_timeseries

_PARSERS: dict[str, Stage2Parser] = {
    "csv_timeseries_v1": parse_csv_timeseries,
}


def get_parser(parser_id: str) -> Stage2Parser:
    """Return parser."""
    try:
        return _PARSERS[parser_id]
    except KeyError as exc:
        raise ValueError(f"unsupported parser_id: {parser_id!r}") from exc


__all__ = ["Stage2Parser", "get_parser"]
