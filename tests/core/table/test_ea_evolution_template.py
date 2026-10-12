from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from runbook.core.table import ea_evolution_table, ea_evolution_table_yoy, render_table_html, resolve_table_style


def test_evolution_aggregates_months_by_release_and_interleaves_full_year_means() -> None:
    months = pd.date_range("2024-01-01", "2027-12-01", freq="MS")
    newest = months.month.to_numpy(dtype=float) + (months.year - 2026) * 100
    frame = pd.DataFrame({"2026-09-28": newest - 1, "2026-10-05": newest}, index=months).iloc[::-1]
    original = frame.copy()
    payload = ea_evolution_table(frame, as_of="2026-10-12")["EA Evolution"]
    result = payload["data"]
    assert result.index.tolist() == ["2026Q2", "2026Q3", "2026Q4", "2026Y", "2027Q1", "2027Q2", "2027Y"]
    assert result.index.name == "Date"
    assert result.columns.tolist() == ["Oct-05", "Sep-28"]
    assert result["Oct-05"].tolist() == [5, 8, 11, 6.5, 102, 105, 106.5]
    pd.testing.assert_series_equal(result["Sep-28"], result["Oct-05"] - 1, check_names=False)
    assert payload["plots"] == []
    style = resolve_table_style(result, payload["style"])
    assert style.global_style.one_bg_color is False
    assert style.formats["Oct-05"].digits == 2
    html = render_table_html(result, payload["style"])
    assert ">106.50</td>" in html and ">Date</th>" in html
    pd.testing.assert_frame_equal(frame, original)


def test_evolution_starts_with_one_release_and_accepts_later_release_columns() -> None:
    dates = pd.date_range("2026-01-01", periods=12, freq="MS")
    first = pd.DataFrame({"2026-09-28": np.arange(12.0) / 10}, index=dates)
    initial = ea_evolution_table(first, as_of="2026-10-12")["EA Evolution"]["data"]
    assert initial.columns.tolist() == ["Sep-28"]
    combined = first.assign(**{"2026-10-05": first.iloc[:, 0] + 0.05})
    updated = ea_evolution_table(combined, as_of="2026-10-12")["EA Evolution"]["data"]
    pd.testing.assert_series_equal(initial["Sep-28"], updated["Sep-28"])
    np.testing.assert_allclose(updated["Oct-05"], initial["Sep-28"] + 0.05)


def test_evolution_missing_months_are_not_shifted_into_other_quarters_and_units_stay_unchanged() -> None:
    frame = pd.DataFrame(
        {"2026-10-05": [1.5, 4.5, np.nan, -3.0], "2026-09-28": [np.nan, 2.0, np.nan, np.nan]},
        index=pd.to_datetime(["2026-01-01", "2026-03-01", "2026-05-01", "2026-10-01"]),
    )
    payload = ea_evolution_table(frame, quarter_window=None)["EA Evolution"]
    result = payload["data"]
    assert result.index.tolist() == ["2026Q1", "2026Q4", "2026Y"]
    assert result["Oct-05"].tolist() == [3, -3, 1]
    assert pd.isna(result.loc["2026Q4", "Sep-28"])
    assert resolve_table_style(result, payload["style"]).cell_css[(1, "Oct-05")]["color"] == "red"


def test_evolution_uses_today_by_default_and_disambiguates_release_years(monkeypatch) -> None:
    from runbook.core.table.templates import ea_evolution

    monkeypatch.setattr(ea_evolution, "datetime", SimpleNamespace(today=lambda: pd.Timestamp("2026-10-12")))
    # Patch only the clock used by the template; input type validation still accepts string dates.
    frame = pd.DataFrame({"2025-10-05": [1.0], "2026-10-05": [2.0]}, index=pd.to_datetime(["2026-04-01"]))
    payload = ea_evolution_table(frame)["EA Evolution"]
    assert payload["data"].columns.tolist() == ["Oct-05-2026", "Oct-05-2025"]
    assert payload["data"].index.tolist() == ["2026Q2", "2026Y"]


def test_evolution_yoy_uses_shared_quarterly_baseline_but_each_releases_annual_history() -> None:
    dates = pd.date_range("2025-01-01", "2027-12-01", freq="MS")
    values = np.repeat([100.0, 110.0, 130.0], 12) + dates.month.to_numpy()
    frame = pd.DataFrame({"2026-09-28": values - 3, "2026-10-05": values}, index=dates)
    payload = ea_evolution_table_yoy(frame, as_of="2026-10-12")["EA Evolution YoY"]
    result = payload["data"]
    assert result["Oct-05"].tolist() == [10, 10, 10, 10, 20, 20, 20]
    # Quarters share the newest release's history; annual differences use each release's own history.
    assert result["Sep-28"].tolist() == [7, 7, 7, 10, 17, 17, 20]
    single = ea_evolution_table_yoy(frame[["2026-10-05"]], as_of="2026-10-12")["EA Evolution YoY"]["data"]
    pd.testing.assert_series_equal(single["Oct-05"], result["Oct-05"])
    base = ea_evolution_table(frame, yoy=True, as_of="2026-10-12")["EA Evolution"]["data"]
    pd.testing.assert_frame_equal(base, result)


def test_evolution_yoy_drops_unavailable_comparisons_and_retains_zero_and_partial_rows() -> None:
    frame = pd.DataFrame(
        {"2026-10-05": [10.0, np.nan, 10.0, 20.0], "2026-09-28": [8.0, 9.0, np.nan, 19.0]},
        index=pd.to_datetime(["2025-04-01", "2025-07-01", "2026-04-01", "2026-07-01"]),
    )
    result = ea_evolution_table_yoy(frame, as_of="2026-10-12")["EA Evolution YoY"]["data"]
    assert result.index.tolist() == ["2026Q2", "2026Y"]
    assert result.loc["2026Q2", "Oct-05"] == 0
    assert pd.isna(result.loc["2026Q2", "Sep-28"])
    assert result.loc["2026Y"].tolist() == [5, 10.5]
    no_history = ea_evolution_table_yoy(frame.loc["2026":], as_of="2026-10-12")["EA Evolution YoY"]
    assert no_history["data"].empty
    assert ">Date</th>" in render_table_html(no_history["data"], no_history["style"])


@pytest.mark.parametrize(
    "frame, message",
    [
        (pd.DataFrame(), "at least one"),
        (pd.DataFrame({"bad": [1.0]}, index=["2026-01-01"]), "Unknown datetime string"),
        (pd.DataFrame({"NaT": [1.0]}, index=["2026-01-01"]), "non-missing dates"),
        (pd.DataFrame({"2026-10-05": [1.0, 2.0]}, index=["2026-01-01", "2026-01-15"]), "one observation"),
        (pd.DataFrame([[1.0, 2.0]], columns=["2026-10-05", "2026-10-05"], index=["2026-01-01"]), "unique"),
    ],
)
def test_evolution_rejects_ambiguous_inputs(frame, message) -> None:
    with pytest.raises(ValueError, match=message):
        ea_evolution_table(frame)
