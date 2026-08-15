"""Public Bloomberg ticker API."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from ._ticker_contract_history import (
    enumerate_contract_tickers,
    is_synthetic_forward_active,
    resolve_effective_fut_gen_month,
    synthetic_forward_source,
)
from ._ticker_cycle import _shift_contract_month
from ._ticker_shared import (
    BASE,
    BASE_RE,
    BASE_WITH_PADDING_RE,
    CONTRACT,
    CONTRACT_NOBASE,
    CONTRACT_NOBASE_BODY,
    CONTRACT_NOBASE_RE,
    CONTRACT_RE,
    FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES,
    GENERIC,
    GENERIC_MONTH,
    GENERIC_NOBASE_BODY,
    GENERIC_NOBASE_RE,
    GENERIC_PLAIN,
    GENERIC_PLAIN_PARSE_RE,
    GENERIC_RE,
    GENERIC_WITH_MONTH,
    GENERIC_WITH_MONTH_PARSE_RE,
    MON,
    MONTH_CODE_TO_NUMBER,
    MONTH_NAME_TO_CODE,
    MONTH_NUMBER_TO_CODE,
    SPACE_SEPARATED_CONTRACT_BASES,
    SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES,
    SUFFIX,
    VENUE,
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
from ._ticker_spread import _convert_s_spread_to_flat, _convert_short_spread_to_flat
from ._ticker_years import (
    encode_spread_year_token_long as _encode_spread_year_token_long,
)
from ._ticker_years import (
    encode_spread_year_token_short as _encode_spread_year_token_short,
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
    """Return the active generic ticker (``<base>A ...``) for contract or generic input.

    For spread tickers, returns the active of the first (near) leg.
    """
    normalized = to_bbg_case(ticker)
    if is_spread(normalized):
        first_leg, _ = convert_spread_to_flat(normalized)
        return get_active(first_leg)
    contract_match = CONTRACT_RE.match(normalized)
    if contract_match is not None:
        parsed = parse_contract(normalized)
        return format_active_ticker(
            base=parsed["base"],
            venue=parsed.get("venue"),
            suffix=parsed["suffix"],
        )
    try:
        generic = parse_generic(normalized)
        return format_active_ticker(
            base=str(generic["base"]),
            venue=normalize_optional(generic["venue"]),
            suffix=str(generic["suffix"]),
        )
    except Exception:
        return ticker


def contract_to_active_ym(ticker: str, *, as_of_year: int | None = None) -> dict[str, str | int]:
    """Deconstruct contract ticker into ``active`` plus absolute month/year fields.

    For spread tickers, the first (near) leg is used.
    """
    if is_spread(ticker):
        first_leg, _ = convert_spread_to_flat(ticker, as_of_year=as_of_year)
        return contract_to_active_ym(first_leg, as_of_year=as_of_year)
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


def convert_to_live_ticker(ticker: str) -> str:
    """Convert a contract ticker with a two-digit year token to one-digit form.

    For example, ``CON25 Comdty`` becomes ``CON5 Comdty``.
    Idempotent: already single-digit tickers are returned unchanged.
    """
    ym = contract_to_active_ym(ticker)
    year = int(ym["y"])
    return construct_contract_ticker(str(ym["active"]), month=str(ym["m"]), year=year, as_of_year=year)


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
        year_token_1 = _encode_spread_year_token_short(
            year=year_abs_1,
            base=base1.rstrip(),
            as_of_year=as_of_year,
            two_digit_year_bases=two_digit_year_bases,
        )
        year_token_2 = _encode_spread_year_token_short(
            year=year_abs_2,
            base=base2.rstrip(),
            as_of_year=as_of_year,
            two_digit_year_bases=two_digit_year_bases,
        )
        if len(base1.rstrip()) == 3:
            # eg TZT -> TZTZ4Z5 Comdty
            return f"{base1}{month_code_1}{year_token_1}{month_code_2}{year_token_2} {suffix}"
        return f"{base1}{month_code_1}{year_token_1}{base2}{month_code_2}{year_token_2} {suffix}"

    year_token_1 = _encode_spread_year_token_long(year=year_abs_1, base=base1.rstrip())
    year_token_2 = _encode_spread_year_token_long(year=year_abs_2, base=base2.rstrip())
    return f"S:{base1}{base2} {month_code_1}{year_token_1}-{month_code_2}{year_token_2} {suffix}"


def convert_spread_to_flat(spread_ticker: str, *, as_of_year: int | None = None) -> tuple[str, str]:
    """Convert spread ticker (short or ``S:`` format) into two flat contract tickers."""
    normalized = to_bbg_case(spread_ticker)
    if normalized.startswith("S:"):
        return _convert_s_spread_to_flat(normalized, as_of_year=as_of_year)
    return _convert_short_spread_to_flat(normalized, as_of_year=as_of_year)


def is_spread(ticker: str) -> bool:
    """Return True if the ticker is a spread (``S:`` prefix or short spread format)."""
    try:
        convert_spread_to_flat(ticker)
        return True
    except ValueError:
        return False


def next_contract_ticker(
    ticker: str,
    *,
    as_of_year: int | None = None,
    two_digit_year_bases: Iterable[str] = (),
    fut_gen_month: Iterable[int | str] | None = None,
) -> str:
    """Get next contract ticker, with optional custom month cycle.

    ``fut_gen_month`` can constrain stepping to a cycle (for example
    ``["H", "M", "U", "Z"]`` for quarterly contracts).
    For spread tickers, both legs are advanced by one month and the spread is reconstructed.
    """
    if is_spread(ticker):
        leg1, leg2 = convert_spread_to_flat(ticker, as_of_year=as_of_year)
        next_leg1 = next_contract_ticker(
            leg1, as_of_year=as_of_year, two_digit_year_bases=two_digit_year_bases, fut_gen_month=fut_gen_month
        )
        next_leg2 = next_contract_ticker(
            leg2, as_of_year=as_of_year, two_digit_year_bases=two_digit_year_bases, fut_gen_month=fut_gen_month
        )
        short = not to_bbg_case(ticker).startswith("S:")
        return convert_flat_to_spread(
            next_leg1, next_leg2, short=short, as_of_year=as_of_year, two_digit_year_bases=two_digit_year_bases
        )
    next_year, next_month = _shift_contract_month(
        ticker=ticker,
        months=1,
        as_of_year=as_of_year,
        fut_gen_month=fut_gen_month,
    )
    active = get_active(ticker)
    return construct_contract_ticker(
        active,
        month=next_month,
        year=next_year,
        as_of_year=as_of_year,
        two_digit_year_bases=two_digit_year_bases,
    )


def previous_contract_ticker(
    ticker: str,
    *,
    as_of_year: int | None = None,
    two_digit_year_bases: Iterable[str] = (),
    fut_gen_month: Iterable[int | str] | None = None,
) -> str:
    """Get previous contract ticker, with optional custom month cycle.

    For spread tickers, both legs are moved back by one month and the spread is reconstructed.
    """
    if is_spread(ticker):
        leg1, leg2 = convert_spread_to_flat(ticker, as_of_year=as_of_year)
        prev_leg1 = previous_contract_ticker(
            leg1, as_of_year=as_of_year, two_digit_year_bases=two_digit_year_bases, fut_gen_month=fut_gen_month
        )
        prev_leg2 = previous_contract_ticker(
            leg2, as_of_year=as_of_year, two_digit_year_bases=two_digit_year_bases, fut_gen_month=fut_gen_month
        )
        short = not to_bbg_case(ticker).startswith("S:")
        return convert_flat_to_spread(
            prev_leg1, prev_leg2, short=short, as_of_year=as_of_year, two_digit_year_bases=two_digit_year_bases
        )
    prev_year, prev_month = _shift_contract_month(
        ticker=ticker,
        months=-1,
        as_of_year=as_of_year,
        fut_gen_month=fut_gen_month,
    )
    active = get_active(ticker)
    return construct_contract_ticker(
        active,
        month=prev_month,
        year=prev_year,
        as_of_year=as_of_year,
        two_digit_year_bases=two_digit_year_bases,
    )


__all__ = [
    "ContractParts",
    "GenericParts",
    "MON",
    "BASE",
    "VENUE",
    "SUFFIX",
    "GENERIC_MONTH",
    "FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES",
    "SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES",
    "SPACE_SEPARATED_CONTRACT_BASES",
    "MONTH_CODE_TO_NUMBER",
    "MONTH_NUMBER_TO_CODE",
    "MONTH_NAME_TO_CODE",
    "BASE_RE",
    "BASE_WITH_PADDING_RE",
    "CONTRACT_NOBASE_BODY",
    "CONTRACT_NOBASE",
    "CONTRACT_NOBASE_RE",
    "CONTRACT",
    "CONTRACT_RE",
    "GENERIC_NOBASE_BODY",
    "GENERIC_NOBASE_RE",
    "GENERIC_WITH_MONTH",
    "GENERIC_PLAIN",
    "GENERIC",
    "GENERIC_RE",
    "GENERIC_WITH_MONTH_PARSE_RE",
    "GENERIC_PLAIN_PARSE_RE",
    "parse_contract",
    "parse_generic",
    "get_active",
    "contract_to_active_ym",
    "construct_contract_ticker",
    "convert_to_live_ticker",
    "normalize_month_code",
    "resolve_contract_year",
    "contract_year_token",
    "convert_flat_to_spread",
    "convert_spread_to_flat",
    "is_spread",
    "next_contract_ticker",
    "previous_contract_ticker",
    "resolve_effective_fut_gen_month",
    "enumerate_contract_tickers",
    "is_synthetic_forward_active",
    "synthetic_forward_source",
]
