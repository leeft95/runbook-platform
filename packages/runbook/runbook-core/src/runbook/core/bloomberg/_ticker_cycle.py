"""Contract navigation helpers (next/previous contract tickers)."""

from __future__ import annotations

from typing import Iterable

from ._ticker_parse import construct_contract_ticker, get_active, parse_contract
from ._ticker_shared import MONTH_CODE_TO_NUMBER
from ._ticker_years import normalize_month_code, resolve_contract_year


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
    """
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
    """Get previous contract ticker, with optional custom month cycle."""
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


def _shift_contract_month(
    *,
    ticker: str,
    months: int,
    as_of_year: int | None,
    fut_gen_month: Iterable[int | str] | None = None,
) -> tuple[int, int]:
    """Shift a contract by ``months`` in monthly or custom ``fut_gen_month`` cycle."""
    parsed = parse_contract(ticker)
    month = MONTH_CODE_TO_NUMBER[parsed["month"]]
    year = resolve_contract_year(parsed["year"], as_of_year=as_of_year)

    cycle = _normalize_fut_gen_month(fut_gen_month)
    if cycle is None:
        year_shift, shifted_month_index = divmod((month - 1) + months, 12)
        return year + year_shift, shifted_month_index + 1

    if month not in cycle:
        raise ValueError(f"Contract month {parsed['month']} not in fut_gen_month cycle: {tuple(cycle)}")

    idx = cycle.index(month)
    total = year * len(cycle) + idx + months
    shifted_year, shifted_idx = divmod(total, len(cycle))
    return shifted_year, cycle[shifted_idx]


def _normalize_fut_gen_month(fut_gen_month: Iterable[int | str] | None) -> list[int] | None:
    """Normalize optional contract cycle months into ordered unique month numbers."""
    if fut_gen_month is None:
        return None

    cycle: list[int] = []
    seen: set[int] = set()
    for raw_month in fut_gen_month:
        month_code = normalize_month_code(raw_month)
        month_num = MONTH_CODE_TO_NUMBER[month_code]
        if month_num in seen:
            continue
        seen.add(month_num)
        cycle.append(month_num)

    if not cycle:
        raise ValueError("fut_gen_month cannot be empty")
    return cycle
