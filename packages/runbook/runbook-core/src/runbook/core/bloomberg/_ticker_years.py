"""Month/year normalization and encoding helpers for Bloomberg contracts/spreads."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from ._ticker_shared import (
    FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES,
    MONTH_CODE_TO_NUMBER,
    MONTH_NAME_TO_CODE,
    MONTH_NUMBER_TO_CODE,
    SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES,
)


def normalize_month_code(month: int | str) -> str:
    """Normalize month input (number, code, or month name) into Bloomberg code."""
    if isinstance(month, int):
        try:
            return MONTH_NUMBER_TO_CODE[month]
        except KeyError as exc:
            raise ValueError(f"Invalid month number: {month}") from exc

    month_str = month.strip().upper()
    if len(month_str) == 1 and month_str in MONTH_CODE_TO_NUMBER:
        return month_str
    if month_str in MONTH_NAME_TO_CODE:
        return MONTH_NAME_TO_CODE[month_str]
    if month_str.isdigit():
        month_num = int(month_str)
        try:
            return MONTH_NUMBER_TO_CODE[month_num]
        except KeyError as exc:
            raise ValueError(f"Invalid month number: {month_str}") from exc

    raise ValueError(f"Invalid month value: {month}")


def resolve_contract_year(year_token: str, *, as_of_year: int | None = None) -> int:
    """Resolve 1-digit/2-digit Bloomberg year token to a four-digit year."""
    if not year_token.isdigit() or len(year_token) not in {1, 2}:
        raise ValueError(f"Invalid contract year token: {year_token}")

    if len(year_token) == 2:
        yy = int(year_token)
        return 1900 + yy if yy >= 70 else 2000 + yy

    anchor_year = as_of_year if as_of_year is not None else date.today().year
    digit = int(year_token)
    decade = anchor_year - (anchor_year % 10)
    candidates = [decade - 10 + digit, decade + digit, decade + 10 + digit]
    return min(candidates, key=lambda candidate: (abs(candidate - anchor_year), candidate < anchor_year))


def contract_year_token(
    year: int,
    *,
    base: str,
    as_of_year: int | None = None,
    two_digit_year_bases: Iterable[str] = (),
) -> str:
    """Encode a full year into Bloomberg ``Y`` or ``YY`` token format.

    ``two_digit_year_bases`` forces ``YY`` for matching bases regardless of date.
    """
    if year < 1900 or year > 2199:
        raise ValueError(f"Unsupported year: {year}")

    yy2 = f"{year % 100:02d}"
    force_two_digit = base in set(two_digit_year_bases)

    anchor_year = as_of_year if as_of_year is not None else date.today().year
    if force_two_digit or year < anchor_year or year > anchor_year + 9:
        return yy2

    return str(year % 10)


def normalize_flat_year_token(*, year_token: str, year_abs: int, base: str) -> str:
    """Normalize flat contract year token to product-specific width conventions."""
    if base in FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES:
        return f"{year_abs % 100:02d}"
    return year_token


def encode_spread_year_token_short(
    *,
    year: int,
    base: str,
    as_of_year: int | None,
    two_digit_year_bases: Iterable[str],
) -> str:
    """Encode spread year token for short spread output."""
    if base in SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES:
        return str(year % 10)
    return contract_year_token(
        year,
        base=base,
        as_of_year=as_of_year,
        two_digit_year_bases=two_digit_year_bases,
    )


def encode_spread_year_token_long(*, year: int, base: str) -> str:
    """Encode spread year token for long ``S:`` spread output."""
    if base in SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES:
        return str(year % 10)
    return f"{year % 100:02d}"
