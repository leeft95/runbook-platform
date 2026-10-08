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
    band_rules = {
        payload["data"].columns[rule["target"]["positions"][0]]: rule
        for rule in payload["style"]["rules"]
        if rule.get("condition", {}).get("op") == "z_gt" and rule["condition"]["rhs"]["num_std"] == 1
    }
    assert set(band_rules) == {"5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"}
    assert resolved.cell_css[(0, "Y-1 20d MA")]["background-color"] == "green"
    assert resolved.cell_css[(0, "5Y 20d MA")]["background-color"] == "lightgreen"
    expected_samples = {
        "5d MA": [615, 619, 623],
        "20d MA": [611, 615, 619, 623],
        "3m MA": [603, 609, 611, 615, 619, 623],
        "Y-1 20d MA": [511, 515, 519, 523],
        "5Y 20d MA": [117, 217, 317, 417, 517],
    }
    for label, sample in expected_samples.items():
        rhs = band_rules[label]["condition"]["rhs"]
        assert payload["data"].loc["Gas", rhs["mean_column"]] == pytest.approx(pd.Series(sample).mean())
        assert payload["data"].loc["Gas", rhs["std_column"]] == pytest.approx(pd.Series(sample).std())
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
    assert selected.loc["Gas", ["5Y 20d MA", "10d MA", "Y-2 3m MA"]].tolist() == pytest.approx([267, 619, 2480 / 6])
    assert selected.loc["Gas", "_rollup_0_std"] == pytest.approx(pd.Series([117, 217, 317, 417]).std())


def test_rollup_highlighting_can_select_historical_columns_or_be_disabled() -> None:
    dates = pd.date_range("2020-01-01", "2025-06-20")
    frame = pd.DataFrame({"Gas": np.arange(len(dates), dtype=float)}, index=dates)
    selected = rollup_table_hst(frame, highlight_columns=["Y-1 20d MA", "5Y 20d MA"])["Roll-up"]
    data = selected["data"]
    highlighted = {
        data.columns[rule["target"]["positions"][0]]
        for rule in selected["style"]["rules"]
        if rule.get("condition", {}).get("op") in {"z_gt", "z_lt"}
    }
    assert highlighted == {"Y-1 20d MA", "5Y 20d MA"}
    disabled = rollup_table_hst(frame, highlight_columns=[])["Roll-up"]
    assert not any(col.startswith("_rollup_") for col in disabled["data"])
    assert not any(rule.get("condition", {}).get("op") in {"z_gt", "z_lt"} for rule in disabled["style"]["rules"])
    with pytest.raises(ValueError, match="highlight_columns"):
        rollup_table_hst(frame, highlight_columns=["Unknown"])
    with pytest.raises(ValueError, match="Latest is not highlighted"):
        rollup_table_hst(frame, highlight_columns=["Latest"])


def test_rollup_highlights_are_independent_of_format_and_skip_missing_or_zero_dispersion() -> None:
    dates = pd.to_datetime([f"{year}-06-{day:02d}" for year in range(2020, 2026) for day in range(1, 21)])
    values = np.tile(np.arange(20.0), 6) + np.repeat(np.arange(6) * 5, 20)
    frame = pd.DataFrame({"Volume": values, "Share": values / 100}, index=dates)
    numeric = rollup_table_hst(frame, format_spec="{:,.2f}")["Roll-up"]
    percent = rollup_table_hst(frame, format_spec="{:.1%}")["Roll-up"]
    numeric_style = resolve_table_style(numeric["data"], numeric["style"])
    percent_style = resolve_table_style(percent["data"], percent["style"])
    assert numeric_style.cell_css == percent_style.cell_css
    for column in numeric_style.visible_columns:
        assert numeric_style.cell_css.get((0, column)) == numeric_style.cell_css.get((1, column))

    sparse = pd.DataFrame(
        {"Constant history": [5.0, 5.0, 10.0]}, index=pd.to_datetime(["2024-06-19", "2024-06-20", "2025-06-20"])
    )
    payload = rollup_table_hst(sparse, ["Latest", "Y-1 20d MA", "5Y 20d MA"])["Roll-up"]
    assert payload["data"].filter(regex="_std$").isna().all().all()
    style = resolve_table_style(payload["data"], payload["style"])
    assert all("background-color" not in css for css in style.cell_css.values())


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
