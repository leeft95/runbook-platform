"""Parsing and construction utilities for Bloomberg contract/generic tickers."""

from __future__ import annotations

from typing import Iterable

from ._ticker_shared import (
    BASE_WITH_PADDING_RE,
    CONTRACT_RE,
    FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES,
    GENERIC_PLAIN_PARSE_RE,
    GENERIC_WITH_MONTH_PARSE_RE,
    MONTH_CODE_TO_NUMBER,
    ContractParts,
    GenericParts,
    format_active_ticker,
    format_contract,
    normalize_contract_base,
    normalize_optional,
    preserve_space_bearing_root,
    to_bbg_case,
    validate_root_padding,
)
from ._ticker_years import (
    contract_year_token,
    normalize_month_code,
    resolve_contract_year,
)


def parse_contract(ticker: str) -> ContractParts:
    """Parse a flat Bloomberg contract ticker into normalized components."""
    normalized = to_bbg_case(ticker)
    match = CONTRACT_RE.match(normalized)
    if match is None:
        raise ValueError(f"Invalid contract ticker: {ticker}")

    base_raw = match.group("base")
    between = match.group("between")
    month = match.group("month")
    year = match.group("year")
    venue = match.group("venue")
    suffix = match.group("suffix")
    if base_raw is None or month is None or year is None or suffix is None:
        raise ValueError(f"Invalid contract ticker: {ticker}")

    base = normalize_contract_base(base_raw=base_raw, between=between)
    if BASE_WITH_PADDING_RE.fullmatch(base) is None:
        raise ValueError(f"Invalid contract ticker: {ticker}")
    validate_root_padding(base=base, ticker=normalized)
    return {
        "base": base,
        "month": month,
        "year": year,
        "venue": venue,
        "suffix": suffix,
    }


def parse_generic(ticker: str) -> GenericParts:
    """Parse a Bloomberg generic futures ticker into normalized components."""
    normalized = to_bbg_case(ticker)
    match = GENERIC_WITH_MONTH_PARSE_RE.match(normalized)
    if match is None:
        match = GENERIC_PLAIN_PARSE_RE.match(normalized)
    if match is None:
        raise ValueError(f"Invalid generic ticker: {ticker}")

    groups = match.groupdict()
    base_raw = groups.get("base")
    between = groups.get("between")
    month_name = groups.get("month_name")
    position = groups.get("position")
    venue = groups.get("venue")
    suffix = groups.get("suffix")
    if base_raw is None or position is None or suffix is None:
        raise ValueError(f"Invalid generic ticker: {ticker}")

    base = preserve_space_bearing_root(base_raw, between)
    if BASE_WITH_PADDING_RE.fullmatch(base) is None:
        raise ValueError(f"Invalid generic ticker: {ticker}")
    validate_root_padding(base=base, ticker=normalized)

    return {
        "base": base,
        "month_name": month_name,
        "position": position,
        "venue": venue,
        "suffix": suffix,
    }


def get_active(ticker: str) -> str:
    """Return the active generic ticker (``<base>A ...``) for contract or generic input."""
    normalized = to_bbg_case(ticker)
    contract_match = CONTRACT_RE.match(normalized)
    if contract_match is not None:
        parsed = parse_contract(normalized)
        return format_active_ticker(
            base=parsed["base"],
            venue=parsed.get("venue"),
            suffix=parsed["suffix"],
        )

    generic = parse_generic(normalized)
    return format_active_ticker(
        base=str(generic["base"]),
        venue=normalize_optional(generic["venue"]),
        suffix=str(generic["suffix"]),
    )


def contract_to_active_ym(ticker: str, *, as_of_year: int | None = None) -> dict[str, str | int]:
    """Deconstruct contract ticker into ``active`` plus absolute month/year fields."""
    parsed = parse_contract(ticker)
    month_code = parsed["month"]
    year = resolve_contract_year(parsed["year"], as_of_year=as_of_year)
    return {
        "active": format_active_ticker(
            base=parsed["base"],
            venue=parsed.get("venue"),
            suffix=parsed["suffix"],
        ),
        "m": month_code,
        "month": MONTH_CODE_TO_NUMBER[month_code],
        "y": year,
    }


def construct_contract_ticker(
    active_ticker: str,
    *,
    month: int | str,
    year: int,
    as_of_year: int | None = None,
    two_digit_year_bases: Iterable[str] = (),
) -> str:
    """Construct a flat contract from active generic plus month/year.

    ``two_digit_year_bases`` lets callers force ``YY`` year tokens for additional
    bases beyond module defaults in ``FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES``.
    """
    generic = parse_generic(active_ticker)

    month_code = normalize_month_code(month)
    effective_two_digit_bases = set(two_digit_year_bases) | FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES
    year_token = contract_year_token(
        year,
        base=str(generic["base"]),
        as_of_year=as_of_year,
        two_digit_year_bases=effective_two_digit_bases,
    )

    venue = normalize_optional(generic["venue"])
    suffix = str(generic["suffix"])
    base = str(generic["base"])
    return format_contract(base=base, month=month_code, year_token=year_token, suffix=suffix, venue=venue)
