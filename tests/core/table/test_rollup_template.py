import numpy as np
import pandas as pd
import pytest

from runbook.core.table import render_table_html, resolve_table_style, rollup_table_hst
from runbook.core.timeseries.rollup import calendar_moving_average


def test_rollup_uses_calendar_windows_prior_years_and_cutoff_for_data_and_plots() -> None:
    rows = {
        pd.Timestamp(f"{year}-{day}"): (year - 2019) * 100 + value
        for year in range(2019, 2026)
        for day, value in [
            ("03-20", 0),
            ("03-21", 3),
            ("05-31", 9),
            ("06-01", 11),
            ("06-16", 15),
            ("06-17", 19),
            ("06-20", 23),
            ("06-21", 999),
        ]
    }
    frame = pd.DataFrame({"Gas": pd.Series(rows)})
    original = frame.copy()
    payload = rollup_table_hst(frame, header="Power", as_of="2025-06-20")["Power"]
    resolved = resolve_table_style(payload["data"], payload["style"])
    row = payload["data"].loc["Gas", list(resolved.visible_columns)]
    assert row.to_dict() == pytest.approx(
        {"Latest": 623, "5d MA": 619, "20d MA": 617, "3m MA": 3680 / 6, "Y-1 20d MA": 517, "5Y 20d MA": 317}
    )
    assert resolved.cell_css[(0, "20d MA")]["background-color"] == "lightgreen"
    assert "_rollup_0_std" not in render_table_html(payload["data"], payload["style"])
    assert resolved.index_links[0].value == payload["plot_names"][0]
    assert resolved.index_header_link.value == payload["all_plots_name"]
    assert "Latest data: 2025-06-20" in render_table_html(payload["data"], payload["style"])
    figure = payload["plots"][0]
    assert {"History", "Base", "5d MA", "20d MA", "3m MA"}.issubset({a.text for a in figure.layout.annotations})
    history = figure.data[0]
    assert max(pd.to_datetime(history.x)) == pd.Timestamp("2025-06-20")
    assert history.y[-1] == 623
    # The 2025 20d MA seasonal line is on column 4, axis x4.
    average = next(trace for trace in figure.data if trace.name == "2025" and trace.xaxis == "x4")
    assert next(
        value for date, value in zip(average.x, average.y) if pd.Timestamp(date).strftime("%m-%d") == "06-20"
    ) == pytest.approx(617)
    pd.testing.assert_frame_equal(frame, original)

    selected = rollup_table_hst(frame, ["5Y 20d MA", "10d MA", "Y-2 3m MA"], as_of="2025-06-20", exclude_years=[2024])[
        "Roll-up"
    ]["data"]
    assert selected.loc["Gas"].tolist() == pytest.approx([267, 619, 2480 / 6])


def test_rollup_missing_years_are_not_filled_and_latest_keeps_missing_values() -> None:
    frame = pd.DataFrame(
        {"Share": [0.1, 0.9, 0.4, np.nan, 99.0]},
        index=pd.to_datetime(["2020-06-20", "2022-06-01", "2024-06-22", "2025-06-20", "2025-06-21"]),
    )
    payload = rollup_table_hst(
        frame,
        ["Latest", "Y-1 20d MA", "5Y 20d MA"],
        as_of="2025-06-20",
        format_spec="{:.1%}",
        row_plot_links=False,
        all_plots_link=False,
    )["Roll-up"]
    row = payload["data"].iloc[0]
    assert pd.isna(row.Latest) and pd.isna(row["Y-1 20d MA"])
    assert row["5Y 20d MA"] == pytest.approx(0.5)
    assert "50.0%" in render_table_html(payload["data"], payload["style"])
    assert not resolve_table_style(payload["data"], payload["style"]).links


def test_calendar_average_handles_dst_and_month_lengths() -> None:
    dates = pd.date_range("2024-01-01 12:00", "2024-04-02 12:00", tz="Europe/London")
    frame = pd.DataFrame({"Value": np.arange(len(dates), dtype=float)}, index=dates)
    for window, offset in [("5d", pd.DateOffset(days=5)), ("3m", pd.DateOffset(months=3))]:
        means = calendar_moving_average(frame, window)
        for date in dates[-3:]:
            assert means.loc[date, "Value"] == pytest.approx(
                frame.loc[(frame.index > date - offset) & (frame.index <= date), "Value"].mean()
            )


def test_rollup_latest_is_the_final_supplied_row() -> None:
    frame = pd.DataFrame(
        {"Value": [30.0, 10.0, np.nan]}, index=pd.to_datetime(["2025-01-03", "2025-01-01", "2025-01-02"])
    )
    payload = rollup_table_hst(frame, ["Latest", "5d MA"])["Roll-up"]
    assert pd.isna(payload["data"].loc["Value", "Latest"])
    assert payload["data"].loc["Value", "5d MA"] == 10.0
    assert max(pd.to_datetime(payload["plots"][0].data[0].x)) == pd.Timestamp("2025-01-02")


@pytest.mark.parametrize("params", [[], "Latest", ["Latest", "latest"], ["0d MA"], ["3 months"], ["5Y 0d MA"]])
def test_rollup_rejects_invalid_column_requests(params) -> None:
    frame = pd.DataFrame({"Value": [1.0]}, index=pd.to_datetime(["2025-01-01"]))
    with pytest.raises(ValueError):
        rollup_table_hst(frame, params)
