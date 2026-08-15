"""Shared constants, types, regexes, and formatting helpers for Bloomberg tickers."""

from __future__ import annotations

import re
from typing import TypedDict


class ContractParts(TypedDict):
    base: str
    month: str
    year: str
    venue: str | None
    suffix: str


class GenericParts(TypedDict):
    base: str
    month_name: str | None
    position: str
    venue: str | None
    suffix: str


# Bloomberg futures month codes.
MON = "FGHJKMNQUVXZ"
BASE = r"[A-Z0-9]+(?: [A-Z0-9]+)*"
VENUE = r"OECM|BCFV|LINK|PVMO|BGN"
SUFFIX = r"Comdty|Curncy|Index"
GENERIC_MONTH = r"JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"
FLAT_ALWAYS_TWO_DIGIT_YEAR_BASES = {"NG", "MO", "TC5FM", "GK", "LP", "LA"}
SPREAD_ALWAYS_SINGLE_DIGIT_YEAR_BASES = {"NG", "MO"}
SPACE_SEPARATED_CONTRACT_BASES = {"TC5FM"}

MONTH_CODE_TO_NUMBER = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}
MONTH_NUMBER_TO_CODE = {month: code for code, month in MONTH_CODE_TO_NUMBER.items()}
MONTH_NAME_TO_CODE = {
    "JAN": "F",
    "FEB": "G",
    "MAR": "H",
    "APR": "J",
    "MAY": "K",
    "JUN": "M",
    "JUL": "N",
    "AUG": "Q",
    "SEP": "U",
    "OCT": "V",
    "NOV": "X",
    "DEC": "Z",
}

BASE_RE = re.compile(rf"^{BASE}$")
BASE_WITH_PADDING_RE = re.compile(rf"^{BASE} ?$")

# Example matches:
# - H24 Comdty
# - Z4 BGN Curncy
# - M25 LINK Index
CONTRACT_NOBASE_BODY = rf"(?P<month>[{MON}])(?P<year>\d{{1,2}})(?: (?P<venue>{VENUE}))? (?P<suffix>{SUFFIX})"
CONTRACT_NOBASE = rf"^{CONTRACT_NOBASE_BODY}$"
CONTRACT_NOBASE_RE = re.compile(CONTRACT_NOBASE)

# Full contract examples:
# - CLH24 Comdty
# - C M24 Comdty
# - ESM25 Index
# - TYZ4 BGN Comdty
CONTRACT = rf"^(?P<base>{BASE})(?P<between> ?){CONTRACT_NOBASE_BODY}$"
CONTRACT_RE = re.compile(CONTRACT)

GENERIC_NOBASE_BODY = (
    rf"(?P<month_name>{GENERIC_MONTH})?(?P<position>A|[1-9]\d*)(?: (?P<venue>{VENUE}))? (?P<suffix>{SUFFIX})"
)
GENERIC_NOBASE_RE = re.compile(rf"^{GENERIC_NOBASE_BODY}$")

# Full generic examples:
# - CLA Comdty
# - CL1 Comdty
# - CL2 Comdty
# - CLDEC1 Comdty
# - CLDEC2 Comdty
# - C  DEC1 Comdty
GENERIC_WITH_MONTH = rf"{BASE}\s*(?:{GENERIC_MONTH})[1-9]\d*(?: (?:{VENUE}))? (?:{SUFFIX})"
GENERIC_PLAIN = rf"{BASE}\s*(?:A|[1-9]\d*)(?: (?:{VENUE}))? (?:{SUFFIX})"
GENERIC = rf"^(?:{GENERIC_WITH_MONTH}|{GENERIC_PLAIN})$"
GENERIC_RE = re.compile(GENERIC)

GENERIC_WITH_MONTH_PARSE_RE = re.compile(
    rf"^(?P<base>.+?)(?P<between>\s*)(?P<month_name>{GENERIC_MONTH})(?P<position>[1-9]\d*)(?: (?P<venue>{VENUE}))? (?P<suffix>{SUFFIX})$"
)
GENERIC_PLAIN_PARSE_RE = re.compile(
    rf"^(?P<base>.+?)(?P<between>\s*)(?P<position>A|[1-9]\d*)(?: (?P<venue>{VENUE}))? (?P<suffix>{SUFFIX})$"
)

_SUFFIX_CASE_MAP = {
    "comdty": "Comdty",
    "curncy": "Curncy",
    "index": "Index",
}
_BBG_SUFFIX_TAIL_RE = re.compile(
    rf"^(?P<body>.+?)\s+(?P<suffix>{SUFFIX})$",
    re.IGNORECASE,
)
_BBG_CASE_PARSE_RES = (
    re.compile(CONTRACT_RE.pattern, re.IGNORECASE),
    re.compile(GENERIC_WITH_MONTH_PARSE_RE.pattern, re.IGNORECASE),
    re.compile(GENERIC_PLAIN_PARSE_RE.pattern, re.IGNORECASE),
)


def to_bbg_case(ticker: str) -> str:
    """Format ticker with Bloomberg casing conventions."""
    stripped = ticker.strip()
    if not stripped:
        return stripped

    for pattern in _BBG_CASE_PARSE_RES:
        match = pattern.fullmatch(stripped)
        if match is None:
            continue

        groups = match.groupdict()
        base = groups["base"].upper()
        between = groups.get("between") or ""
        venue = normalize_optional(groups.get("venue"))
        suffix = _SUFFIX_CASE_MAP[groups["suffix"].lower()]

        month = groups.get("month")
        month_name = groups.get("month_name")
        position = groups.get("position")
        year = groups.get("year")

        if month is not None and year is not None:
            body = f"{base}{between}{month.upper()}{year}"
        elif month_name is not None and position is not None:
            body = f"{base}{between}{month_name.upper()}{position.upper()}"
        elif position is not None:
            body = f"{base}{between}{position.upper()}"
        else:
            break

        parts = [body]
        if venue:
            parts.append(venue.upper())
        parts.append(suffix)
        return " ".join(parts)

    suffix_match = _BBG_SUFFIX_TAIL_RE.fullmatch(stripped)
    if suffix_match is None:
        return stripped.upper()

    body = suffix_match.group("body")
    suffix = suffix_match.group("suffix")
    if body is None or suffix is None:
        return stripped.upper()
    return f"{body.upper()} {_SUFFIX_CASE_MAP[suffix.lower()]}"


def format_active_ticker(*, base: str, venue: str | None, suffix: str) -> str:
    """Format active ticker text from normalized pieces."""
    parts = [base + "A"]
    if venue:
        parts.append(venue)
    parts.append(suffix)
    return " ".join(parts)


def normalize_optional(value: str | None) -> str | None:
    """Return stripped optional string value, or ``None`` when empty."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def preserve_space_bearing_root(base: str, between: str | None) -> str:
    """Preserve one trailing space for space-bearing Bloomberg roots."""
    if between:
        return base + " "
    return base


def normalize_contract_base(*, base_raw: str, between: str | None) -> str:
    """Normalize contract base, preserving configured space-separated root behavior."""
    base = preserve_space_bearing_root(base_raw, between)
    if between and base_raw in SPACE_SEPARATED_CONTRACT_BASES:
        return base_raw
    return base


def validate_root_padding(*, base: str, ticker: str) -> None:
    """Bloomberg roots are min two chars; 1-char roots are right-padded with a space."""
    stripped = base.rstrip()
    if len(stripped) == 1 and not base.endswith(" "):
        raise ValueError(f"Invalid ticker root padding: {ticker}")
    if len(stripped) >= 2 and base.endswith(" "):
        raise ValueError(f"Invalid ticker root padding: {ticker}")


def uses_contract_separator(base: str) -> bool:
    """Return whether contract for this base must include separator before month/year."""
    return base.rstrip() in SPACE_SEPARATED_CONTRACT_BASES


def format_contract(*, base: str, month: str, year_token: str, suffix: str, venue: str | None = None) -> str:
    """Format canonical flat contract ticker from normalized fields."""
    separator = " " if uses_contract_separator(base) else ""
    if venue:
        return f"{base}{separator}{month}{year_token} {venue} {suffix}"
    return f"{base}{separator}{month}{year_token} {suffix}"
