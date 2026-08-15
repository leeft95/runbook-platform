from __future__ import annotations

import pytest
from runbook.core.bloomberg.tickers import (
    CONTRACT_NOBASE_RE,
    CONTRACT_RE,
    GENERIC_NOBASE_RE,
    GENERIC_RE,
    construct_contract_ticker,
    contract_to_active_ym,
    contract_year_token,
    convert_flat_to_spread,
    convert_spread_to_flat,
    enumerate_contract_tickers,
    get_active,
    is_synthetic_forward_active,
    next_contract_ticker,
    parse_contract,
    parse_generic,
    previous_contract_ticker,
    resolve_contract_year,
    resolve_effective_fut_gen_month,
    synthetic_forward_source,
)


def _contract_tickers_from_resolved() -> list[str]:
    return ["CLZ24 Comdty", "CLZ4 Comdty", "NGM26 Comdty"]


def _generic_tickers_from_resolved() -> list[str]:
    return ["CLA Comdty", "C A Comdty", "C DEC1 Comdty", "S NOV2 Comdty"]


def _fut_cur_gen_tickers_from_scanlist() -> list[str]:
    return ["CLA Comdty", "C A Comdty", "C DEC1 Comdty", "S NOV2 Comdty"]


def test_contract_regex_matches_resolved_contract_tickers() -> None:
    failures: list[str] = []
    for ticker in _contract_tickers_from_resolved():
        if CONTRACT_RE.fullmatch(ticker) is None:
            failures.append(ticker)

    assert not failures, f"Unmatched CONTRACT tickers ({len(failures)}): {failures[:10]}"


def test_baseless_regex_matches_tail_from_resolved_contract_tickers() -> None:
    failures: list[str] = []

    for ticker in _contract_tickers_from_resolved():
        full_match = CONTRACT_RE.fullmatch(ticker)
        if full_match is None:
            failures.append(f"{ticker} (full contract did not match)")
            continue

        month = full_match.group("month")
        year = full_match.group("year")
        venue = full_match.group("venue")
        suffix = full_match.group("suffix")
        baseless = f"{month}{year}"
        if venue:
            baseless += f" {venue}"
        baseless += f" {suffix}"

        if CONTRACT_NOBASE_RE.fullmatch(baseless) is None:
            failures.append(f"{ticker} -> {baseless}")

    assert not failures, f"Baseless regex failures ({len(failures)}): {failures[:10]}"


def test_generic_regex_matches_resolved_generic_contract_tickers() -> None:
    failures: list[str] = []
    for ticker in _generic_tickers_from_resolved():
        if GENERIC_RE.fullmatch(ticker) is None:
            failures.append(ticker)

    assert not failures, f"Unmatched generic CONTRACT tickers ({len(failures)}): {failures[:10]}"


def test_generic_baseless_regex_matches_tail() -> None:
    failures: list[str] = []

    for ticker in _generic_tickers_from_resolved():
        if GENERIC_RE.fullmatch(ticker) is None:
            failures.append(f"{ticker} (full generic did not match)")
            continue

        parsed = parse_generic(ticker)
        month_name = parsed["month_name"]
        position = parsed["position"]
        venue = parsed["venue"]
        suffix = parsed["suffix"]
        baseless = f"{month_name or ''}{position}"
        if venue:
            baseless += f" {venue}"
        baseless += f" {suffix}"

        if GENERIC_NOBASE_RE.fullmatch(baseless) is None:
            failures.append(f"{ticker} -> {baseless}")

    assert not failures, f"Generic baseless regex failures ({len(failures)}): {failures[:10]}"


def test_parse_generic_examples() -> None:
    assert parse_generic("CLA Comdty") == {
        "base": "CL",
        "month_name": None,
        "position": "A",
        "venue": None,
        "suffix": "Comdty",
    }
    assert parse_generic("cla comdty") == {
        "base": "CL",
        "month_name": None,
        "position": "A",
        "venue": None,
        "suffix": "Comdty",
    }


def test_parse_generic_handles_space_bearing_roots() -> None:
    assert parse_generic("C A Comdty") == {
        "base": "C ",
        "month_name": None,
        "position": "A",
        "venue": None,
        "suffix": "Comdty",
    }
    assert parse_generic("C  DEC1 Comdty") == {
        "base": "C ",
        "month_name": "DEC",
        "position": "1",
        "venue": None,
        "suffix": "Comdty",
    }
    assert parse_generic("S  NOV2 Comdty") == {
        "base": "S ",
        "month_name": "NOV",
        "position": "2",
        "venue": None,
        "suffix": "Comdty",
    }


def test_generic_regex_matches_scanlist_fut_cur_gen_contracts() -> None:
    failures: list[str] = []
    for ticker in _fut_cur_gen_tickers_from_scanlist():
        if not ticker.endswith(" Comdty"):
            continue
        if GENERIC_RE.fullmatch(ticker) is None:
            failures.append(ticker)

    assert not failures, f"Unmatched ScanList FUT_CUR_GEN_TICKER contracts ({len(failures)}): {failures[:10]}"


def test_contract_to_active_ym() -> None:
    assert contract_to_active_ym("CLZ24 Comdty") == {
        "active": "CLA Comdty",
        "m": "Z",
        "month": 12,
        "y": 2024,
    }
    assert contract_to_active_ym("CLZ4 Comdty", as_of_year=2026) == {
        "active": "CLA Comdty",
        "m": "Z",
        "month": 12,
        "y": 2024,
    }
    assert contract_to_active_ym("clz4 comdty", as_of_year=2026) == {
        "active": "CLA Comdty",
        "m": "Z",
        "month": 12,
        "y": 2024,
    }


def test_construct_contract_ticker_auto_year_digits() -> None:
    assert construct_contract_ticker("CLA Comdty", month=12, year=2026, as_of_year=2026) == "CLZ6 Comdty"
    assert construct_contract_ticker("CLA Comdty", month=12, year=2024, as_of_year=2026) == "CLZ24 Comdty"


def test_construct_contract_ticker_uses_two_digits_for_historical_roots() -> None:
    assert construct_contract_ticker("COA Comdty", month="K", year=2002, as_of_year=2026) == "COK02 Comdty"


def test_construct_contract_ticker_two_digit_override() -> None:
    assert (
        construct_contract_ticker(
            "NGA Comdty",
            month="JUN",
            year=2026,
            as_of_year=2026,
            two_digit_year_bases={"NG"},
        )
        == "NGM26 Comdty"
    )
    assert construct_contract_ticker("NGA Comdty", month="JUN", year=2026, as_of_year=2026) == "NGM26 Comdty"


def test_resolve_effective_fut_gen_month_prefers_override() -> None:
    assert resolve_effective_fut_gen_month("SMA Comdty", "FGHJKMNQUVXZ") == ("FHKNZ", "override")


def test_resolve_effective_fut_gen_month_falls_back_to_bloomberg() -> None:
    assert resolve_effective_fut_gen_month("CLA Comdty", "fghjkmnquvxz") == ("FGHJKMNQUVXZ", "bloomberg")


def test_enumerate_contract_tickers_sorts_output_by_ticker() -> None:
    assert enumerate_contract_tickers("CLA Comdty", "HMUZ", 2025, 2025, as_of_year=2025) == [
        "CLH5 Comdty",
        "CLM5 Comdty",
        "CLU5 Comdty",
        "CLZ5 Comdty",
    ]


def test_enumerate_contract_tickers_supports_single_month_cycles() -> None:
    assert enumerate_contract_tickers("MOA Comdty", "Z", 2025, 2026, as_of_year=2025) == [
        "MOZ25 Comdty",
        "MOZ26 Comdty",
    ]


def test_synthetic_forward_helpers_use_root_mapping() -> None:
    assert is_synthetic_forward_active("ELGBA Comdty") is True
    assert synthetic_forward_source("ELGBA Comdty") == "BCFV"
    assert is_synthetic_forward_active("CLA Comdty") is False
    assert synthetic_forward_source("CLA Comdty") is None


def test_year_token_helpers() -> None:
    assert resolve_contract_year("26") == 2026
    assert resolve_contract_year("98") == 1998
    assert resolve_contract_year("4", as_of_year=2026) == 2024
    assert resolve_contract_year("0", as_of_year=2025) == 2030

    assert contract_year_token(2026, base="CL", as_of_year=2026) == "6"
    assert contract_year_token(2024, base="CL", as_of_year=2026) == "24"
    assert contract_year_token(2026, base="NG", as_of_year=2026, two_digit_year_bases={"NG"}) == "26"


def test_get_active_handles_contract_and_generic() -> None:
    assert get_active("CLH6 Comdty") == "CLA Comdty"
    assert get_active("CL2 Comdty") == "CLA Comdty"
    assert get_active("CLDEC1 Comdty") == "CLA Comdty"
    assert get_active("cldec1 comdty") == "CLA Comdty"
    assert get_active("C H6 Comdty") == "C A Comdty"
    assert get_active("S:COCO M26-N26 Comdty") == "COA Comdty"
    assert parse_generic("CL1 Comdty") == {
        "base": "CL",
        "month_name": None,
        "position": "1",
        "venue": None,
        "suffix": "Comdty",
    }
    assert parse_generic("CLDEC2 Comdty") == {
        "base": "CL",
        "month_name": "DEC",
        "position": "2",
        "venue": None,
        "suffix": "Comdty",
    }


def test_single_letter_roots_must_be_padded() -> None:
    with pytest.raises(ValueError, match="root padding"):
        parse_generic("CA Comdty")
    with pytest.raises(ValueError, match="root padding"):
        parse_contract("CH6 Comdty")


def test_convert_flat_to_spread_short_uses_date_context() -> None:
    assert (
        convert_flat_to_spread(
            "CLZ4 Comdty",
            "CLF5 Comdty",
            short=True,
            as_of_year=2026,
        )
        == "CLZ24CLF25 Comdty"
    )
    assert (
        convert_flat_to_spread(
            "CLZ4 Comdty",
            "CLF5 Comdty",
            short=True,
            as_of_year=2024,
        )
        == "CLZ4CLF5 Comdty"
    )


def test_convert_flat_to_spread_long_forces_two_digit_years() -> None:
    assert (
        convert_flat_to_spread(
            "CLZ6 Comdty",
            "CLF7 Comdty",
            short=False,
            as_of_year=2026,
        )
        == "S:CLCL Z26-F27 Comdty"
    )


def test_convert_flat_to_spread_ng_mo_use_single_digit_years() -> None:
    assert (
        convert_flat_to_spread(
            "NGZ24 Comdty",
            "NGF25 Comdty",
            short=True,
            as_of_year=2026,
        )
        == "NGZ4NGF5 Comdty"
    )
    assert (
        convert_flat_to_spread(
            "NGZ24 Comdty",
            "NGF25 Comdty",
            short=False,
            as_of_year=2026,
        )
        == "S:NGNG Z4-F5 Comdty"
    )


def test_convert_spread_to_flat_short_format() -> None:
    assert convert_spread_to_flat("CLZ24 CLF25 Comdty") == ("CLZ24 Comdty", "CLF25 Comdty")
    assert convert_spread_to_flat("TZTZ4Z5 Comdty") == ("TZTZ4 Comdty", "TZTZ5 Comdty")
    assert convert_spread_to_flat("NGZ4NGF5 Comdty", as_of_year=2026) == ("NGZ24 Comdty", "NGF25 Comdty")
    assert convert_spread_to_flat("ngz4ngf5 comdty", as_of_year=2026) == ("NGZ24 Comdty", "NGF25 Comdty")


def test_convert_spread_to_flat_s_format() -> None:
    assert convert_spread_to_flat("S:CLCL Z26-F27 Comdty", as_of_year=2026) == ("CLZ26 Comdty", "CLF27 Comdty")
    assert convert_spread_to_flat("s:clcl z26-f27 comdty", as_of_year=2026) == ("CLZ26 Comdty", "CLF27 Comdty")


def test_convert_spread_to_flat_s_generic_format() -> None:
    assert convert_spread_to_flat("S:COCO 2-6 Comdty") == ("CO2 Comdty", "CO6 Comdty")
    assert convert_spread_to_flat("S:CLCL 2-6 Comdty") == ("CL2 Comdty", "CL6 Comdty")


def test_convert_spread_to_flat_s_format_ng_mo_single_digit_special_case() -> None:
    assert convert_spread_to_flat("S:NGNG Z4-F5 Comdty", as_of_year=2026) == ("NGZ24 Comdty", "NGF25 Comdty")
    assert convert_spread_to_flat("S:MOMO Z4-F5 Comdty", as_of_year=2026) == ("MOZ24 Comdty", "MOF25 Comdty")

    with pytest.raises(ValueError, match="Single-digit S: year token not allowed"):
        convert_spread_to_flat("S:CLCL Z4-F5 Comdty", as_of_year=2026)


def test_next_previous_contract_ticker() -> None:
    assert next_contract_ticker("CLZ24 Comdty", as_of_year=2026) == "CLF25 Comdty"
    assert previous_contract_ticker("CLF5 Comdty", as_of_year=2026) == "CLZ24 Comdty"
    assert next_contract_ticker("CLZ6 Comdty", as_of_year=2026) == "CLF7 Comdty"
    assert previous_contract_ticker("CLF6 Comdty", as_of_year=2026) == "CLZ25 Comdty"
    assert next_contract_ticker("CLZ4 Comdty", as_of_year=2024) == "CLF5 Comdty"


def test_next_previous_contract_ticker_ng_uses_two_digit_flat_years() -> None:
    assert next_contract_ticker("NGZ24 Comdty", as_of_year=2026) == "NGF25 Comdty"
    assert previous_contract_ticker("NGF25 Comdty", as_of_year=2026) == "NGZ24 Comdty"


def test_next_previous_contract_ticker_with_fut_gen_month_cycle() -> None:
    cycle = ["H", "M", "U", "Z"]
    assert next_contract_ticker("CLH6 Comdty", as_of_year=2026, fut_gen_month=cycle) == "CLM6 Comdty"
    assert next_contract_ticker("CLZ6 Comdty", as_of_year=2026, fut_gen_month=cycle) == "CLH7 Comdty"
    assert previous_contract_ticker("CLH7 Comdty", as_of_year=2026, fut_gen_month=cycle) == "CLZ6 Comdty"

    # NG still keeps 2-digit year on flat outputs even on quarterly cycle.
    assert next_contract_ticker("NGH26 Comdty", as_of_year=2026, fut_gen_month=cycle) == "NGM26 Comdty"


def test_next_contract_ticker_fut_gen_month_requires_current_month_in_cycle() -> None:
    with pytest.raises(ValueError, match="not in fut_gen_month cycle"):
        next_contract_ticker("CLF6 Comdty", as_of_year=2026, fut_gen_month=["H", "M", "U", "Z"])


def test_edge_case_base_tc5fm_space_separated_contracts() -> None:
    assert parse_contract("TC5FM H26 Index") == {
        "base": "TC5FM",
        "month": "H",
        "year": "26",
        "venue": None,
        "suffix": "Index",
    }
    assert construct_contract_ticker("TC5FMA Index", month="H", year=2026, as_of_year=2026) == "TC5FM H26 Index"
    spread = convert_flat_to_spread("TC5FM H26 Index", "TC5FM M26 Index", short=True, as_of_year=2026)
    assert spread == "TC5FMH6TC5FMM6 Index"
    assert convert_spread_to_flat(spread, as_of_year=2026) == ("TC5FM H26 Index", "TC5FM M26 Index")
