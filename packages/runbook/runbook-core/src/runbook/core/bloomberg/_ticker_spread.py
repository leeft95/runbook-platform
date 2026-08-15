"""Spread conversion utilities for Bloomberg tickers."""

from __future__ import annotations

import re
from typing import Iterable

from ._ticker_parse import parse_contract
from ._ticker_shared import (
    BASE_WITH_PADDING_RE,
    MON,
    SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES,
    SUFFIX,
    ContractParts,
    format_contract,
    to_bbg_case,
    validate_root_padding,
)
from ._ticker_years import (
    encode_spread_year_token_long,
    encode_spread_year_token_short,
    normalize_flat_year_token,
    resolve_contract_year,
)


def convert_flat_to_spread(
    ticker1: str,
    ticker2: str,
    short: bool = True,
    *,
    as_of_year: int | None = None,
    two_digit_year_bases: Iterable[str] = (),
) -> str:
    """Convert two contract tickers into a spread ticker.

    When ``short`` is True, year token width follows date-context encoding,
    except NG/MO spreads which are single-digit.
    When ``short`` is False, both year tokens are 2-digit, except NG/MO
    spreads which are single-digit.

    ``two_digit_year_bases`` only applies in short mode and allows forcing
    ``YY`` spread year tokens for additional bases.
    """
    parsed1 = parse_contract(ticker1)
    parsed2 = parse_contract(ticker2)

    if parsed1["venue"] != parsed2["venue"]:
        raise ValueError(f"Cannot create spread from different venues: {ticker1}, {ticker2}")
    if parsed1["suffix"] != parsed2["suffix"]:
        raise ValueError(f"Cannot create spread from different suffixes: {ticker1}, {ticker2}")

    base1 = parsed1["base"]
    base2 = parsed2["base"]
    suffix = parsed1["suffix"]

    month_code_1 = parsed1["month"]
    year_abs_1 = resolve_contract_year(parsed1["year"], as_of_year=as_of_year)
    month_code_2 = parsed2["month"]
    year_abs_2 = resolve_contract_year(parsed2["year"], as_of_year=as_of_year)

    if short:
        year_token_1 = encode_spread_year_token_short(
            year=year_abs_1,
            base=base1.rstrip(),
            as_of_year=as_of_year,
            two_digit_year_bases=two_digit_year_bases,
        )
        year_token_2 = encode_spread_year_token_short(
            year=year_abs_2,
            base=base2.rstrip(),
            as_of_year=as_of_year,
            two_digit_year_bases=two_digit_year_bases,
        )
        if len(base1.rstrip()) == 3:
            # eg TZT -> TZTZ4Z5 Comdty
            return f"{base1}{month_code_1}{year_token_1}{month_code_2}{year_token_2} {suffix}"
        return f"{base1}{month_code_1}{year_token_1}{base2}{month_code_2}{year_token_2} {suffix}"

    year_token_1 = encode_spread_year_token_long(year=year_abs_1, base=base1.rstrip())
    year_token_2 = encode_spread_year_token_long(year=year_abs_2, base=base2.rstrip())
    return f"S:{base1}{base2} {month_code_1}{year_token_1}-{month_code_2}{year_token_2} {suffix}"


def convert_spread_to_flat(spread_ticker: str, *, as_of_year: int | None = None) -> tuple[str, str]:
    """Convert spread ticker (short or ``S:`` format) into two flat contract tickers."""
    normalized = to_bbg_case(spread_ticker)
    if normalized.startswith("S:"):
        return _convert_s_spread_to_flat(normalized, as_of_year=as_of_year)
    return _convert_short_spread_to_flat(normalized, as_of_year=as_of_year)


def _convert_s_spread_to_flat(spread_ticker: str, *, as_of_year: int | None = None) -> tuple[str, str]:
    """Convert ``S:`` spread forms into two flat tickers.

    Supports both generic nearby format (``S:COCO 2-6 Comdty``) and
    month-year format (``S:CLCL Z26-F27 Comdty``).
    """
    generic_match = re.match(
        rf"^S:(?P<roots>.+) (?P<p1>[1-9]\d*)-(?P<p2>[1-9]\d*) (?P<suffix>{SUFFIX})$",
        spread_ticker,
    )
    if generic_match is not None:
        roots = generic_match.group("roots")
        position_1 = generic_match.group("p1")
        position_2 = generic_match.group("p2")
        suffix = generic_match.group("suffix")
        if roots is None or position_1 is None or position_2 is None or suffix is None:
            raise ValueError(f"Invalid S: spread ticker: {spread_ticker}")
        base_1, base_2 = _split_concatenated_roots(roots, spread_ticker)
        return (f"{base_1}{position_1} {suffix}", f"{base_2}{position_2} {suffix}")

    match = re.match(
        rf"^S:(?P<roots>.+) (?P<m1>[{MON}])(?P<y1>\d{{1,2}})-(?P<m2>[{MON}])(?P<y2>\d{{1,2}}) (?P<suffix>{SUFFIX})$",
        spread_ticker,
    )
    if match is None:
        raise ValueError(f"Invalid S: spread ticker: {spread_ticker}")

    roots = match.group("roots")
    month_1 = match.group("m1")
    year_1 = match.group("y1")
    month_2 = match.group("m2")
    year_2 = match.group("y2")
    suffix = match.group("suffix")
    if roots is None or month_1 is None or year_1 is None or month_2 is None or year_2 is None or suffix is None:
        raise ValueError(f"Invalid S: spread ticker: {spread_ticker}")

    base_1, base_2 = _split_concatenated_roots(roots, spread_ticker)
    base_1_stripped = base_1.rstrip()
    base_2_stripped = base_2.rstrip()

    if len(year_1) == 1 and base_1_stripped not in SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES:
        raise ValueError(f"Single-digit S: year token not allowed for base {base_1_stripped}: {spread_ticker}")
    if len(year_2) == 1 and base_2_stripped not in SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES:
        raise ValueError(f"Single-digit S: year token not allowed for base {base_2_stripped}: {spread_ticker}")

    year_abs_1 = resolve_contract_year(year_1, as_of_year=as_of_year)
    year_abs_2 = resolve_contract_year(year_2, as_of_year=as_of_year)

    year_token_1 = normalize_flat_year_token(
        year_token=year_1,
        year_abs=year_abs_1,
        base=base_1_stripped,
    )
    year_token_2 = normalize_flat_year_token(
        year_token=year_2,
        year_abs=year_abs_2,
        base=base_2_stripped,
    )

    return (
        format_contract(base=base_1, month=month_1, year_token=year_token_1, suffix=suffix),
        format_contract(base=base_2, month=month_2, year_token=year_token_2, suffix=suffix),
    )


def _convert_short_spread_to_flat(spread_ticker: str, *, as_of_year: int | None = None) -> tuple[str, str]:
    """Convert non-``S:`` short spread format into two flat tickers."""
    body, sep, suffix = spread_ticker.rpartition(" ")
    if sep == "" or suffix not in {"Comdty", "Curncy", "Index"}:
        raise ValueError(f"Invalid short spread ticker: {spread_ticker}")

    candidates = _short_spread_candidates(body=body, suffix=suffix)
    if len(candidates) == 1:
        left_parsed, right_parsed = candidates[0]
        return (
            _format_flat_contract_from_parsed(left_parsed, as_of_year=as_of_year),
            _format_flat_contract_from_parsed(right_parsed, as_of_year=as_of_year),
        )

    if len(candidates) > 1:
        same_base = [candidate for candidate in candidates if candidate[0]["base"] == candidate[1]["base"]]
        if len(same_base) == 1:
            left_parsed, right_parsed = same_base[0]
            return (
                _format_flat_contract_from_parsed(left_parsed, as_of_year=as_of_year),
                _format_flat_contract_from_parsed(right_parsed, as_of_year=as_of_year),
            )

    compressed = re.fullmatch(
        rf"(?P<base>[A-Z0-9]{{3}})(?P<m1>[{MON}])(?P<y1>\d{{1,2}})(?P<m2>[{MON}])(?P<y2>\d{{1,2}})",
        body,
    )
    if compressed is not None:
        base = compressed.group("base")
        month_1 = compressed.group("m1")
        year_1 = compressed.group("y1")
        month_2 = compressed.group("m2")
        year_2 = compressed.group("y2")
        if base is None or month_1 is None or year_1 is None or month_2 is None or year_2 is None:
            raise ValueError(f"Invalid short spread ticker: {spread_ticker}")
        return (
            format_contract(
                base=base,
                month=month_1,
                year_token=normalize_flat_year_token(
                    year_token=year_1,
                    year_abs=resolve_contract_year(year_1, as_of_year=as_of_year),
                    base=base,
                ),
                suffix=suffix,
            ),
            format_contract(
                base=base,
                month=month_2,
                year_token=normalize_flat_year_token(
                    year_token=year_2,
                    year_abs=resolve_contract_year(year_2, as_of_year=as_of_year),
                    base=base,
                ),
                suffix=suffix,
            ),
        )

    raise ValueError(f"Invalid short spread ticker: {spread_ticker}")


def _split_concatenated_roots(roots: str, ticker: str) -> tuple[str, str]:
    """Split concatenated spread roots into two valid base roots."""
    candidates: list[tuple[str, str]] = []
    for idx in range(1, len(roots)):
        left = roots[:idx]
        right = roots[idx:]
        if not _is_valid_root(left) or not _is_valid_root(right):
            continue
        candidates.append((left, right))

    if not candidates:
        raise ValueError(f"Cannot split spread roots: {ticker}")
    if len(candidates) == 1:
        return candidates[0]

    equal_candidates = [candidate for candidate in candidates if candidate[0] == candidate[1]]
    if len(equal_candidates) == 1:
        return equal_candidates[0]

    raise ValueError(f"Ambiguous spread roots: {ticker}")


def _is_valid_root(root: str) -> bool:
    """Return whether a root candidate satisfies base and padding constraints."""
    if BASE_WITH_PADDING_RE.fullmatch(root) is None:
        return False
    try:
        validate_root_padding(base=root, ticker=root)
    except ValueError:
        return False
    return True


def _format_flat_contract_from_parsed(parsed: ContractParts, *, as_of_year: int | None) -> str:
    """Format flat ticker from parsed parts applying flat year-width normalization."""
    year_abs = resolve_contract_year(parsed["year"], as_of_year=as_of_year)
    year_token = normalize_flat_year_token(
        year_token=parsed["year"],
        year_abs=year_abs,
        base=parsed["base"].rstrip(),
    )
    return format_contract(
        base=parsed["base"],
        month=parsed["month"],
        year_token=year_token,
        suffix=parsed["suffix"],
        venue=parsed.get("venue"),
    )


def _short_spread_candidates(*, body: str, suffix: str) -> list[tuple[ContractParts, ContractParts]]:
    """Generate and deduplicate plausible left/right flat legs for short spread body."""
    candidates: list[tuple[ContractParts, ContractParts]] = []

    if " " in body:
        split_points = [idx for idx, char in enumerate(body) if char == " "]
        split_iter = ((body[:idx].strip(), body[idx + 1 :].strip()) for idx in split_points)
    else:
        split_iter = ((body[:idx], body[idx:]) for idx in range(1, len(body)))

    for left, right in split_iter:
        if not left or not right:
            continue
        try:
            left_parsed = parse_contract(f"{left} {suffix}")
            right_parsed = parse_contract(f"{right} {suffix}")
        except ValueError:
            continue
        candidates.append((left_parsed, right_parsed))

    deduped: list[tuple[ContractParts, ContractParts]] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for left_contract, right_contract in candidates:
        key = (
            left_contract["base"],
            left_contract["month"],
            left_contract["year"],
            right_contract["base"],
            right_contract["month"],
            right_contract["year"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append((left_contract, right_contract))
    return deduped
