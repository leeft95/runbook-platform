import numpy as np
import pandas as pd
import pytest

from runbook.core.table import render_table_html, resolve_table_style, rollup_table_fcst, rollup_table_hst
from runbook.core.table.templates import eu_power_rollup_table
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
    all_averages = ["5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"]
    payload = rollup_table_hst(
        frame, header="Power", as_of="2025-06-20", include_total=False, use_highlighting=all_averages
    )["Power"]
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
    assert resolved.cell_css[(0, "Y-1 20d MA")]["background-color"] == "lightgreen"
    assert resolved.cell_css[(0, "5Y 20d MA")]["background-color"] == "lightgreen"
    expected_samples = {
        "5d MA": [610, 615, 617, 619],
        "20d MA": [610, 1835 / 3, 613.5, 617],
        "3m MA": [605.75, 607.6, 609.5, 3680 / 6],
        "Y-1 20d MA": [510, 1535 / 3, 513.5, 517],
        "5Y 20d MA": [310, 935 / 3, 313.5, 317],
    }
    for label, sample in expected_samples.items():
        rhs = band_rules[label]["condition"]["rhs"]
        assert payload["data"].loc["Gas", rhs["mean_column"]] == pytest.approx(pd.Series(sample).mean())
        assert payload["data"].loc["Gas", rhs["std_column"]] == pytest.approx(pd.Series(sample).std())
    assert "_rollup_0_std" not in render_table_html(payload["data"], payload["style"])
    assert resolved.index_links[0].value == payload["plot_names"][0]
    assert resolved.index_header_link.value == payload["all_plots_name"]
    assert "<tfoot>" not in render_table_html(payload["data"], payload["style"])
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

    selected = rollup_table_hst(
        frame,
        ["5Y 20d MA", "10d MA", "Y-2 3m MA"],
        as_of="2025-06-20",
        exclude_years=[2024],
        include_total=False,
        use_highlighting=["5Y 20d MA"],
    )["Roll-up"]["data"]
    assert selected.loc["Gas", ["5Y 20d MA", "10d MA", "Y-2 3m MA"]].tolist() == pytest.approx([267, 619, 2480 / 6])
    assert selected.loc["Gas", "_rollup_0_std"] == pytest.approx(pd.Series([260, 785 / 3, 263.5, 267]).std())


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


@pytest.mark.parametrize("template", [rollup_table_hst, rollup_table_fcst, eu_power_rollup_table])
def test_rollup_defaults_to_latest_and_20d_with_calendar_reference_and_selectable_columns(template) -> None:
    frame = pd.DataFrame(
        {"Gas": [-1000.0, -1.0, -2.0, -10.0, -9999.0]},
        index=pd.to_datetime(["2025-06-09", "2025-06-11", "2025-06-20", "2025-06-30", "2025-07-01"]),
    )
    options = (
        {"df_hst": frame.loc[:"2025-06-30"], "today": "2025-06-30"}
        if template is rollup_table_fcst
        else {"as_of": "2025-06-30"}
    )
    payload = template(frame, header="Power", **options)["Power"]
    data, style = payload["data"], resolve_table_style(payload["data"], payload["style"])
    rules = {
        data.columns[rule["target"]["positions"][0]]: rule
        for rule in payload["style"]["rules"]
        if rule.get("condition", {}).get("op") == "z_gt"
    }
    assert set(rules) == {"Latest", "20d MA"}
    for column in rules:
        rhs = rules[column]["condition"]["rhs"]
        sample = pd.Series([-1.0, -2.0, -10.0] if column == "Latest" else [-1001 / 2, -1003 / 3, -13 / 3])
        assert rules[column]["condition"]["lhs_column"] == column
        assert data.loc["Gas", rhs["mean_column"]] == pytest.approx(sample.mean())
        assert data.loc["Gas", rhs["std_column"]] == pytest.approx(sample.std())
    assert {column for (_, column), css in style.cell_css.items() if "background-color" in css} == {"Latest", "20d MA"}
    assert style.cell_css[(0, "Latest")]["background-color"] == "#FFA94D"
    assert style.cell_css[(0, "20d MA")]["background-color"] == "lightgreen"
    chosen_columns = list(style.visible_columns)
    chosen = template(frame, header="Power", use_highlighting=chosen_columns, **options)["Power"]
    chosen_rules = {
        chosen["data"].columns[rule["target"]["positions"][0]]
        for rule in chosen["style"]["rules"]
        if rule.get("condition", {}).get("op") == "z_gt"
    }
    assert chosen_rules == set(chosen_columns)
    pd.testing.assert_frame_equal(chosen["data"][chosen_columns], data[chosen_columns])
    disabled = template(frame, header="Power", use_highlighting=[], highlight_columns=["Latest"], **options)["Power"]
    disabled_style = resolve_table_style(disabled["data"], disabled["style"])
    assert not any("background-color" in css for css in disabled_style.cell_css.values())
    assert disabled_style.cell_css[(0, "Latest")]["color"] == "red"
    latest_only = template(frame, header="Power", params=["Latest"], **options)["Power"]
    assert list(resolve_table_style(latest_only["data"], latest_only["style"]).visible_columns) == ["Latest"]
    assert (
        resolve_table_style(latest_only["data"], latest_only["style"]).cell_css[(0, "Latest")]["background-color"]
        == "#FFA94D"
    )


@pytest.mark.parametrize("template", [rollup_table_hst, rollup_table_fcst])
def test_rollup_latest_and_smoothed_trend_can_agree_or_diverge(template) -> None:
    frame = pd.DataFrame(
        {"Rising": np.arange(40.0), "Pullback": [0.0] * 20 + [100.0] * 19 + [0.0]},
        index=pd.date_range("2025-01-01", periods=40),
    )
    options = {"today": frame.index[-1]} if template is rollup_table_fcst else {}
    payload = template(frame, params=["Latest", "20d MA"], include_total=False, **options)["Roll-up"]
    style = resolve_table_style(payload["data"], payload["style"])
    assert style.cell_css[(0, "Latest")]["background-color"] == "lightgreen"
    assert style.cell_css[(0, "20d MA")]["background-color"] == "lightgreen"
    assert style.cell_css[(1, "Latest")]["background-color"] == "#FF8787"
    assert style.cell_css[(1, "20d MA")]["background-color"] == "lightgreen"


def test_rollup_highlights_are_independent_of_format_and_skip_missing_or_zero_dispersion() -> None:
    dates = pd.to_datetime([f"{year}-06-{day:02d}" for year in range(2020, 2026) for day in range(1, 21)])
    values = np.tile(np.arange(20.0), 6) + np.repeat(np.arange(6) * 5, 20)
    frame = pd.DataFrame({"Volume": values, "Share": values / 100}, index=dates)
    numeric = rollup_table_hst(frame, format_spec="{:,.2f}", include_total=False)["Roll-up"]
    percent = rollup_table_hst(frame, format_spec="{:.1%}", include_total=False)["Roll-up"]
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


@pytest.mark.parametrize("forecast", [False, True])
def test_rollup_std_limits_change_both_sides_of_all_average_bands_without_changing_values(forecast) -> None:
    dates = pd.to_datetime([f"{year}-06-{day}" for year in range(2020, 2026) for day in range(16, 21)])
    values = np.tile(np.arange(-2.0, 3.0), 6) + np.repeat(np.arange(6), 5)
    frame = pd.DataFrame({"Positive": values, "Negative": -values}, index=dates)
    template = rollup_table_fcst if forecast else eu_power_rollup_table
    options = {"today": "2025-06-20"} if forecast else {}
    options["use_highlighting"] = ["Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"]
    default = template(frame, header="Power", include_total=False, **options)["Power"]
    stronger = template(frame, header="Power", include_total=False, std_limits=(0.5, 1.0), **options)["Power"]
    quieter = template(frame, header="Power", include_total=False, std_limits=(4.0, 5.0), **options)["Power"]
    for payload in (stronger, quieter):
        pd.testing.assert_frame_equal(payload["data"], default["data"])
    default_style = resolve_table_style(default["data"], default["style"])
    strong_style = resolve_table_style(stronger["data"], stronger["style"])
    quiet_style = resolve_table_style(quieter["data"], quieter["style"])
    assert default_style.cell_css[(0, "5d MA")]["background-color"] == "lightgreen"
    assert default_style.cell_css[(1, "5d MA")]["background-color"] == "#FFA94D"
    for row, color in ((0, "green"), (1, "#FF8787")):
        for column in strong_style.visible_columns:
            assert "background-color" not in quiet_style.cell_css.get((row, column), {})
            if column == "Current Month":
                assert "background-color" not in strong_style.cell_css.get((row, column), {})
            else:
                assert strong_style.cell_css[(row, column)]["background-color"] == color


@pytest.mark.parametrize(
    "limits", [(), (1,), (1, 2, 3), (0, 2), (-1, 2), (2, 1), (1, 1), (np.nan, 2), (1, np.inf), (True, 2)]
)
def test_rollup_rejects_invalid_std_limits(limits) -> None:
    frame = pd.DataFrame({"Value": [1.0]}, index=pd.to_datetime(["2025-01-01"]))
    with pytest.raises(ValueError, match="std_limits"):
        rollup_table_hst(frame, std_limits=limits)


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
    payload = rollup_table_hst(frame, ["Latest", "5d MA"], include_total=False)["Roll-up"]
    assert pd.isna(payload["data"].loc["Value", "Latest"])
    assert payload["data"].loc["Value", "5d MA"] == 10.0
    assert max(pd.to_datetime(payload["plots"][0].data[0].x)) == pd.Timestamp("2025-01-02")


@pytest.mark.parametrize("label", ["Total", "Electricity demand", None])
def test_rollup_uses_matching_precomputed_total_with_custom_label_or_default(label) -> None:
    source_label = label or "Total"
    frame = pd.DataFrame(
        {"Gas": [1.0, 2.0, 3.0], "Coal": [2.0, 3.0, 4.0], source_label: [15.0, 18.0, 21.0]},
        index=pd.date_range("2025-06-01", periods=3),
    )
    original = frame.copy()
    options = {} if label == "Total" else {"total_label": label}
    payload = rollup_table_hst(frame, ["Latest", "5d MA"], row_plot_links=[source_label], **options)["Roll-up"]
    data = payload["data"]
    assert list(data.index) == ["Gas", "Coal", source_label]
    assert data.iloc[-1][["Latest", "5d MA"]].tolist() == [21.0, 18.0]
    resolved = resolve_table_style(data, payload["style"])
    assert list(resolved.index_links) == [2]
    assert resolved.index_links[2].value == payload["plot_names"][-1]
    assert list(payload["plots"][-1].data[0].y) == [15.0, 18.0, 21.0]
    assert resolved.cell_css.get((0, "Latest"), {}) == {}
    assert resolved.index_css == {2: {"font-weight": "bold", "border-top": "1px solid #000000"}}
    for column in resolved.visible_columns:
        assert resolved.cell_css[(2, column)]["font-weight"] == "bold"
        assert resolved.cell_css[(2, column)]["border-top"] == "1px solid #000000"
    assert "background-color" not in resolved.cell_css[(2, "Latest")]
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("params", [[], "Latest", ["Latest", "latest"], ["0d MA"], ["3 months"], ["5Y 0d MA"]])
def test_rollup_rejects_invalid_column_requests(params) -> None:
    frame = pd.DataFrame({"Value": [1.0]}, index=pd.to_datetime(["2025-01-01"]))
    with pytest.raises(ValueError):
        rollup_table_hst(frame, params)


@pytest.mark.parametrize("template", [rollup_table_hst, rollup_table_fcst, eu_power_rollup_table])
def test_rollup_formats_output_dtypes_and_can_omit_supplied_total(template) -> None:
    frame = pd.DataFrame({"Gas": [1, 2, 4], "Total": [10, 20, 40]}, index=pd.date_range("2025-06-01", periods=3))
    original = frame.copy()
    options = {"today": frame.index[-1]} if template is rollup_table_fcst else {}
    payload = template(
        frame,
        params=["Latest", "5d MA"],
        header="Power",
        include_total=False,
        row_plot_links=["Gas", "Total"],
        **options,
    )["Power"]
    data, style = payload["data"], payload["style"]
    assert list(data.index) == ["Gas"]
    assert data.loc["Gas", "5d MA"] == pytest.approx(7 / 3)
    resolved = resolve_table_style(data, style)
    assert resolved.formats["Latest"].digits == 0
    assert resolved.formats["5d MA"].digits == 2
    assert resolved.index_css == {}
    assert len(payload["plots"]) == len(payload["plot_names"]) == 1
    assert resolved.index_links[0].value == payload["plot_names"][0]
    html = render_table_html(data, style)
    assert ">4</td>" in html and ">2.33</td>" in html and ">Total<" not in html
    floating = template(frame.astype(float), params=["Latest", "5d MA"], header="Power", **options)["Power"]
    assert all(
        resolve_table_style(floating["data"], floating["style"]).formats[label].digits == 2
        for label in ["Latest", "5d MA"]
    )
    custom = template(frame, params=["Latest", "5d MA"], header="Power", format_spec="{:.3f}", **options)["Power"]
    assert ">2.333</td>" in render_table_html(custom["data"], custom["style"])
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("template", [rollup_table_hst, rollup_table_fcst])
@pytest.mark.parametrize("label", [None, "Demand"])
def test_rollup_calculates_column_totals_with_missing_observations_and_last_series_zero(template, label) -> None:
    frame = pd.DataFrame(
        {"A": [1.0, float("nan"), 3.0], "B": [10.0, 20.0, float("nan")], "Zero": [0.0, 0.0, 0.0]},
        index=pd.date_range("2025-06-01", periods=3),
    )
    params = ["Latest", "5d MA", "Y-1 20d MA"]
    options = {"today": frame.index[-1]} if template is rollup_table_fcst else {}
    payload = template(frame, params=params, total_label=label, **options)["Roll-up"]
    data, total = payload["data"], label or "Total"
    assert list(data.index) == ["A", "B", "Zero", total]
    assert data.loc[total, "Latest"] == 3
    assert data.loc[total, "5d MA"] == 17
    assert data.loc[total, "_rollup_0_mean"] == pytest.approx(pd.Series([11.0, 20.0, 3.0]).mean())
    assert pd.isna(data.loc[total, "Y-1 20d MA"])
    pd.testing.assert_series_equal(
        data.loc[total, params], data.drop(total)[params].sum(min_count=1), check_names=False
    )
    assert list(payload["plots"][-1].data[0].y) == [11.0, 20.0, 3.0]
    omitted = template(frame, params=params, total_label=label, include_total=False, **options)["Roll-up"]
    assert list(omitted["data"].index) == ["A", "B", "Zero"]
    assert len(omitted["plots"]) == 3


@pytest.mark.parametrize("template", [rollup_table_hst, rollup_table_fcst])
@pytest.mark.parametrize("label", [None, "Demand"])
def test_rollup_moves_matching_precomputed_total_to_last_without_double_counting(template, label) -> None:
    total = label or "Total"
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], total: [99.0, 100.0], "B": [10.0, 20.0]},
        index=pd.date_range("2025-06-01", periods=2),
    )
    original = frame.copy()
    params = ["Latest", "5d MA"]
    options = {"today": frame.index[-1]} if template is rollup_table_fcst else {}
    payload = template(frame, params=params, total_label=label, **options)["Roll-up"]
    assert list(payload["data"].index) == ["A", "B", total]
    assert payload["data"].loc[total, params].tolist() == [100.0, 99.5]
    assert list(payload["plots"][-1].data[0].y) == [99.0, 100.0]
    omitted = template(frame, params=params, total_label=label, include_total=False, **options)["Roll-up"]
    assert list(omitted["data"].index) == ["A", "B"]
    assert len(omitted["plots"]) == 2
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("template", [rollup_table_hst, rollup_table_fcst, eu_power_rollup_table])
@pytest.mark.parametrize("enabled", [False, True])
def test_rollup_can_enable_or_disable_all_plots_link(template, enabled) -> None:
    frame = pd.DataFrame({"Gas": [1.0, 2.0]}, index=pd.date_range("2025-06-01", periods=2))
    payload = template(frame, header="Power", all_plots_link=enabled)["Power"]
    resolved = resolve_table_style(payload["data"], payload["style"])
    assert (resolved.index_header_link is not None) is enabled
    assert ("all_plots_name" in payload) is enabled
    assert len(resolved.index_links) == len(payload["plots"]) == 2


def test_rollup_omitting_the_only_total_series_has_no_dangling_plot_links() -> None:
    frame = pd.DataFrame({"Total": [10.0]}, index=pd.to_datetime(["2025-06-01"]))
    payload = rollup_table_fcst(frame, include_total=False)["Roll-up"]
    assert payload["data"].empty and payload["plots"] == [] and payload["plot_names"] == []
    assert not resolve_table_style(payload["data"], payload["style"]).links


def test_forecast_rollup_anchors_all_averages_to_history_but_keeps_current_month_and_full_plots() -> None:
    rows = {
        pd.Timestamp(f"{year}-{day}"): (year - 2020) * 100 + value
        for year in range(2020, 2026)
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
    rows.update({pd.Timestamp("2025-07-01"): 40, pd.Timestamp("2025-07-31"): 60})
    frame = pd.DataFrame({"Gas": pd.Series(rows)})
    # The final supplied historical row supplies Latest; averages still use frame.
    history = pd.DataFrame({"Gas": [-999, -888]}, index=pd.to_datetime(["2025-06-22", "2025-06-20"]))
    original, original_history = frame.copy(), history.copy()
    payload = rollup_table_fcst(frame, history, today="2025-07-10", include_total=False)["Roll-up"]
    resolved = resolve_table_style(payload["data"], payload["style"])
    assert list(resolved.visible_columns) == [
        "Current Month",
        "Latest",
        "5d MA",
        "20d MA",
        "3m MA",
        "Y-1 20d MA",
        "5Y 20d MA",
    ]
    assert payload["data"].loc["Gas", list(resolved.visible_columns)].to_dict() == pytest.approx(
        {
            "Current Month": 50,
            "Latest": -888,
            "5d MA": 519,
            "20d MA": 517,
            "3m MA": 3080 / 6,
            "Y-1 20d MA": 417,
            "5Y 20d MA": 217,
        }
    )
    assert resolved.index_links[0].value == payload["plot_names"][0]
    assert max(pd.to_datetime(payload["plots"][0].data[0].x)) == pd.Timestamp("2025-07-31")
    assert payload["plots"][0].data[0].y[-1] == 60
    pd.testing.assert_frame_equal(frame, original)
    pd.testing.assert_frame_equal(history, original_history)

    assert "background-color" not in resolved.cell_css.get((0, "Current Month"), {})
    assert "background-color" not in resolved.cell_css[(0, "Latest")]
    assert resolved.cell_css[(0, "Latest")]["color"] == "red"
    selected = rollup_table_fcst(frame, history, today="2025-07-10", use_highlighting=["Current Month"])["Roll-up"]
    selected_style = resolve_table_style(selected["data"], selected["style"])
    assert selected_style.cell_css[(0, "Current Month")]["background-color"] == "#FFA94D"
    assert "background-color" not in selected_style.cell_css.get((0, "Latest"), {})


@pytest.mark.parametrize("history", [None, pd.DataFrame()])
def test_forecast_rollup_without_history_uses_today_not_final_df_row(history) -> None:
    frame = pd.DataFrame(
        {"Total": [100.0, 10.0, 20.0]},
        index=pd.to_datetime(["2025-02-01", "2025-01-30", "2025-01-31"]),
    )
    payload = rollup_table_fcst(
        frame, history, ["Current Month", "Latest", "5d MA"], today="2025-02-01", format_spec="{:,.2f}"
    )["Roll-up"]
    assert payload["data"].loc["Total", ["Current Month", "Latest", "5d MA"]].tolist() == [100, 100, 130 / 3]
    resolved = resolve_table_style(payload["data"], payload["style"])
    assert resolved.index_css[0] == {"font-weight": "bold", "border-top": "1px solid #000000"}
    assert "100.00" in render_table_html(payload["data"], payload["style"])
    assert "<tfoot>" not in render_table_html(payload["data"], payload["style"])


def test_forecast_rollup_uses_history_latest_even_when_date_is_absent_from_df() -> None:
    frame = pd.DataFrame(
        {"Value": [10.0, 14.0, 100.0]}, index=pd.to_datetime(["2025-01-29", "2025-01-30", "2025-02-01"])
    )
    history = pd.DataFrame({"Value": [50.0]}, index=pd.to_datetime(["2025-01-31"]))
    payload = rollup_table_fcst(frame, history, ["Latest", "5d MA"], include_total=False)["Roll-up"]
    assert payload["data"].loc["Value", "Latest"] == 50
    assert payload["data"].loc["Value", "5d MA"] == 12
    assert all(
        "background-color" not in css
        for css in resolve_table_style(payload["data"], payload["style"]).cell_css.values()
    )


@pytest.mark.parametrize("precomputed", [False, True])
@pytest.mark.parametrize("forecast_total", [False, True])
def test_forecast_history_values_align_by_column_and_supply_the_latest_total(precomputed, forecast_total) -> None:
    dates = pd.date_range("2025-01-01", periods=3)
    frame = pd.DataFrame({"A": [1, 2, 3], "B": [10, 20, 30], "Missing": [7, 8, 9]}, index=dates)
    history = pd.DataFrame({"B": [100, 200], "Extra": [999, 999], "A": [10, np.nan]}, index=dates[:2])
    if precomputed:
        history["Demand"] = [500, 600]
    if forecast_total:
        frame["Demand"] = [5000, 6000, 7000]
    original, original_history = frame.copy(), history.copy()
    payload = rollup_table_fcst(frame, history, params=["Latest", "5d MA"], total_label="Demand")["Roll-up"]
    data = payload["data"]
    assert list(data.index) == ["A", "B", "Missing", "Demand"]
    assert pd.isna(data.loc["A", "Latest"]) and pd.isna(data.loc["Missing", "Latest"])
    assert data.loc["B", "Latest"] == 200
    assert data.loc["Demand", "Latest"] == (600 if precomputed else 200)
    assert data["5d MA"].tolist() == [1.5, 15, 7.5, 5500 if forecast_total else 24]
    pd.testing.assert_frame_equal(frame, original)
    pd.testing.assert_frame_equal(history, original_history)


def test_forecast_latest_zscore_uses_only_twenty_calendar_days_of_history() -> None:
    frame = pd.DataFrame({"A": np.arange(34.0)}, index=pd.date_range("2025-01-01", periods=34))
    history = pd.DataFrame(
        {"A": [-9999.0, -1.0, -2.0, 9999.0, -10.0]},
        index=pd.to_datetime(["2025-01-11", "2025-01-12", "2025-01-20", "2025-02-02", "2025-01-31"]),
    )
    payload = rollup_table_fcst(frame, history, params=["Latest", "20d MA"], include_total=False)["Roll-up"]
    data = payload["data"]
    assert data.loc["A", ["Latest", "20d MA"]].tolist() == [-10, 20.5]
    expected = {
        "Latest": pd.Series([-1.0, -2.0, -10.0]),
        "20d MA": calendar_moving_average(frame, "20d").loc["2025-01-12":"2025-01-31", "A"],
    }
    for rule in payload["style"]["rules"]:
        condition = rule.get("condition", {})
        if condition.get("op") == "z_gt":
            sample = expected[condition["lhs_column"]]
            assert data.loc["A", condition["rhs"]["mean_column"]] == pytest.approx(sample.mean())
            assert data.loc["A", condition["rhs"]["std_column"]] == pytest.approx(sample.std())


@pytest.mark.parametrize("missing_today", [False, True])
def test_forecast_today_none_uses_current_day_without_falling_back_to_last_df_row(monkeypatch, missing_today) -> None:
    from types import SimpleNamespace
    from runbook.core.table.templates import rollup

    monkeypatch.setattr(rollup, "datetime", SimpleNamespace(today=lambda: pd.Timestamp("2025-02-01 15:30")))
    frame = pd.DataFrame({"A": [10, 20, 999]}, index=pd.date_range("2025-01-31", periods=3))
    if missing_today:
        frame = frame.drop(pd.Timestamp("2025-02-01"))
    payload = rollup_table_fcst(frame, params=["Latest", "5d MA"], include_total=False, today=None)["Roll-up"]
    row = payload["data"].loc["A"]
    assert pd.isna(row["Latest"]) if missing_today else row["Latest"] == 20
    assert row["5d MA"] == (10 if missing_today else 15)


def test_forecast_rollup_current_month_and_history_anchor_use_df_timezone() -> None:
    frame = pd.DataFrame(
        {"Value": [10.0, 20.0, 100.0, 200.0]},
        index=pd.to_datetime(
            ["2025-03-31 12:00", "2025-04-01 12:00", "2025-04-30 12:00", "2025-05-01 12:00"]
        ).tz_localize("Europe/London"),
    )
    history = pd.DataFrame({"Value": [999.0]}, index=pd.to_datetime(["2025-04-01 11:00Z"]))
    payload = rollup_table_fcst(
        frame, history, ["Current Month", "Latest", "5d MA"], today="2025-03-31 23:30Z", include_total=False
    )["Roll-up"]
    assert payload["data"].loc["Value", ["Current Month", "Latest", "5d MA"]].tolist() == [60, 999, 15]


@pytest.mark.parametrize(
    "history", [pd.DataFrame({"Value": [1]}), pd.DataFrame({"Value": [1]}, index=pd.DatetimeIndex([pd.NaT]))]
)
def test_forecast_rollup_rejects_invalid_history_dates(history) -> None:
    frame = pd.DataFrame({"Value": [1.0]}, index=pd.to_datetime(["2025-01-01"]))
    with pytest.raises(ValueError, match="df_hst must have a DatetimeIndex without NaT"):
        rollup_table_fcst(frame, history)
