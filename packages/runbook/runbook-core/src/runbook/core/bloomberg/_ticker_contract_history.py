"""Helpers for deterministic futures contract history construction."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from ._ticker_parse import construct_contract_ticker, get_active, parse_generic
from ._ticker_shared import (
    MONTH_CODE_TO_NUMBER,
    format_active_ticker,
    normalize_optional,
)
from ._ticker_years import normalize_month_code

FUT_GEN_MONTH_OVERRIDES: dict[str, str] = {
    "SMA Comdty": "FHKNZ",
    "BOA Comdty": "FHKNZ",
    "S A Comdty": "FHKNX",
    "GCA Comdty": "JGMQZ",
    "SIA Comdty": "HKNUZ",
    "MOA Comdty": "Z",
    "LHA Comdty": "GJMQVZ",
    "CTA Comdty": "HKNZ",
}

SYNTHETIC_FORWARD_SOURCES: dict[str, str] = {
    "ELGB": "BCFV",
    "ELGP": "BCFV",
    "ELGO": "BCFV",
    "TTFU": "OECM",
    "FSNO": "",
    "FSNN": "",
    "PMRS": "LINK",
    "WCID": "LINK",
    "PWTM": "LINK",
    "WMEH": "LINK",
    "PSHC": "LINK",
    "PSHI": "LINK",
    "BKU": "LINK",
    "CDBS": "PVMO",
    "GOEW": "PVMO",
}


def _normalize_cycle_codes(fut_gen_month: str | Iterable[int | str]) -> tuple[str, ...]:
    """Normalize cycle codes."""
    if isinstance(fut_gen_month, str):
        values: Iterable[int | str] = list(fut_gen_month.strip().upper())
    else:
        values = fut_gen_month

    ordered: list[str] = []
    seen: set[str] = set()
    for raw_month in values:
        month_code = normalize_month_code(raw_month)
        if month_code in seen:
            continue
        seen.add(month_code)
        ordered.append(month_code)

    if not ordered:
        raise ValueError("fut_gen_month cannot be empty")
    return tuple(ordered)


def synthetic_forward_source(active_ticker: str) -> str | None:
    """Return the synthetic-forward venue/source for a normalized active ticker."""
    active = get_active(active_ticker)
    base = parse_generic(active)["base"].rstrip()
    return normalize_optional(SYNTHETIC_FORWARD_SOURCES.get(base))


def is_synthetic_forward_active(active_ticker: str) -> bool:
    """Return whether the active ticker root uses synthetic-forward venue mapping."""
    active = get_active(active_ticker)
    base = parse_generic(active)["base"].rstrip()
    return base in SYNTHETIC_FORWARD_SOURCES


def resolve_effective_fut_gen_month(active_ticker: str, bloomberg_fut_gen_month: str | None) -> tuple[str, str]:
    """Resolve the effective contract cycle from overrides first, Bloomberg second."""
    active = get_active(active_ticker)
    if active in FUT_GEN_MONTH_OVERRIDES:
        cycle = "".join(_normalize_cycle_codes(FUT_GEN_MONTH_OVERRIDES[active]))
        return cycle, "override"

    normalized_bbg = normalize_optional(bloomberg_fut_gen_month)
    if normalized_bbg is None:
        raise ValueError(f"Could not resolve FUT_GEN_MONTH for {active}")
    cycle = "".join(_normalize_cycle_codes(normalized_bbg))
    return cycle, "bloomberg"


def enumerate_contract_tickers(
    active_ticker: str,
    fut_gen_month: str | Iterable[int | str],
    start_year: int,
    end_year: int,
    source: str | None = None,
    as_of_year: int | None = None,
) -> list[str]:
    """Enumerate concrete contract tickers from an active generic and month cycle."""
    if end_year < start_year:
        raise ValueError(f"end_year must be >= start_year, got {start_year=} {end_year=}")

    active = get_active(active_ticker)
    cycle = _normalize_cycle_codes(fut_gen_month)
    generic = parse_generic(active)
    venue = normalize_optional(source) if source is not None else normalize_optional(generic["venue"])
    anchor_year = as_of_year if as_of_year is not None else date.today().year
    active_for_construction = format_active_ticker(
        base=str(generic["base"]),
        venue=venue,
        suffix=str(generic["suffix"]),
    )

    tickers: list[str] = []
    for year in range(start_year, end_year + 1):
        for month_code in cycle:
            ticker = construct_contract_ticker(
                active_for_construction,
                month=MONTH_CODE_TO_NUMBER[month_code],
                year=year,
                as_of_year=anchor_year,
            )
            tickers.append(ticker)

    return sorted(dict.fromkeys(tickers))
