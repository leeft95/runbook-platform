from importlib import import_module
from pathlib import Path
import runpy

import numpy as np
import pandas as pd
import pytest

from runbook.core.cot import analysis, analysis_mifid
from runbook.core.plotting.templates import (
    plot_cot_long_short,
    plot_cot_net,
    plot_cot_positions,
    plot_line_with_comparison,
    plot_line_with_moving_average,
)
from runbook.core.table import render_table_html, resolve_table_style
from runbook.core.table.templates import (
    cot_cme_summary_table,
    cot_ice_mifid_summary_table,
    cot_cme_timeseries_table,
    cot_ice_mifid_timeseries_table,
    cot_timeseries_table,
    cot_macro_summary_table,
    cot_macro_timeseries_table,
    grouped_metrics_table,
)
from runbook.core.timeseries.cot import cot_summary, prepare_cot_data


def test_gallery_uses_public_templates_with_resolvable_links_and_serializable_output() -> None:
    tables, charts = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/preview_gallery.py"))[
        "build_examples"
    ]()
    assert len(tables) == 18 and len(charts) == 18
    assert len({item["template"] for item in tables}) == 17
    assert len({item["template"] for item in charts}) == 18
    chart_names = {item["key"] for item in charts}
    for item in [*tables, *charts]:
        module, name = item["template"].rsplit(".", 1)
        assert callable(getattr(import_module(module), name))
    for item in tables:
        payload = item["payload"]
        resolved = resolve_table_style(payload["data"], payload["style"])
        known = chart_names | set(payload.get("plot_names", [])) | {payload.get("all_plots_name")}
        for link in [
            *resolved.cell_links.values(),
            *resolved.index_links.values(),
            *resolved.header_links.values(),
            resolved.index_header_link,
        ]:
            if link is not None:
                assert link.value in known
        assert "text-align: center" in render_table_html(payload["data"], payload["style"])
        assert all(figure.data and figure.to_json() for figure in payload["plots"])
    assert all(item["figure"].data and item["figure"].to_json() for item in charts)
    chart_figures = {item["key"]: item["figure"] for item in charts}
    assert chart_figures["market"].layout.shapes
    assert not chart_figures["market-holdings"].layout.shapes
    examples = {item["key"]: item["payload"] for item in tables}
    for summary_key, calculated_key in (("cot", "cot-calculated"), ("cot-mifid-summary", "cot-mifid-calculated")):
        summary, calculated = examples[summary_key], examples[calculated_key]
        assert len(summary["data"]) == len(calculated["data"]) == 4
        pd.testing.assert_frame_equal(summary["data"], calculated["data"])
        assert summary["style"] == calculated["style"]
        assert render_table_html(summary["data"], summary["style"]) == render_table_html(
            calculated["data"], calculated["style"]
        )


@pytest.mark.parametrize("template, columns", [(plot_cot_net, 1), (plot_cot_long_short, 2), (plot_cot_positions, 3)])
def test_cot_templates_keep_position_price_and_oi_panels_in_seventy_thirty_ratio(template, columns) -> None:
    dates = pd.date_range("2023-01-03", periods=120, freq="W-TUE")
    data = prepare_cot_data(
        pd.DataFrame(
            {"Long": np.arange(120.0) + 1000, "Short": 100.0, "OI": 20000.0, "PX_LAST": 70.0, "Internal": 0.5},
            index=dates,
        )
    )
    figure = template(data)
    for col in range(1, columns + 1):
        top = figure.get_subplot(1, col)
        bottom = figure.get_subplot(2, col)
        assert bottom is not None
        top_height = top.yaxis.domain[1] - top.yaxis.domain[0]
        bottom_height = bottom.yaxis.domain[1] - bottom.yaxis.domain[0]
        assert top_height / (top_height + bottom_height) == pytest.approx(0.7)
        bottom_axis = f"x{columns + col}"
        lower = {trace.name: trace for trace in figure.data if trace.xaxis == bottom_axis}
        assert {"Net/OI", "Internal", "Max", "Min"}.issubset(lower)
        assert lower["Net/OI"].yaxis != lower["Internal"].yaxis
        assert lower["Min"].fill == "tonexty"
        assert top.xaxis.matches == bottom_axis
    if template is plot_cot_net:
        single = template(data[["Net", "PX_LAST"]], rows=1)
        assert {trace.xaxis for trace in single.data} == {"x"}
        named = template(data, internal_label="Model estimate")
        model = next(trace for trace in named.data if trace.name == "Model estimate")
        assert model.line.color == "blue"
        assert getattr(named.layout, "yaxis" + model.yaxis[1:]).title.text == "Model estimate"
        assert not any(trace.name == "Internal" for trace in named.data)


def test_line_templates_preserve_missing_windows_and_comparison_alignment() -> None:
    dates = pd.date_range("2026-06-01", periods=4)
    data = pd.Series([1.0, 2.0, 3.0, 4.0], index=dates, name="2d MA")
    original = data.copy()
    figure = plot_line_with_moving_average(data, window=2, title="Custom title", height=450)
    assert [trace.name for trace in figure.data] == ["2d MA", "2d MA overlay"]
    np.testing.assert_allclose(figure.data[1].y, [np.nan, 1.5, 2.5, 3.5], equal_nan=True)
    assert figure.layout.title.text == "Custom title" and figure.layout.height == 450
    short = plot_line_with_moving_average(data, window=5)
    assert pd.isna(short.data[1].y).all()
    comparison = pd.DataFrame({"2d MA": [20.0, 10.0]}, index=dates[[3, 1]])
    compared = plot_line_with_comparison(data, comparison, series_styles=None)
    assert compared.data[1].name == "Comparison: 2d MA" and compared.data[1].yaxis == "y2"
    np.testing.assert_allclose(compared.data[1].y, [np.nan, 10.0, 10.0, 20.0], equal_nan=True)
    pd.testing.assert_series_equal(data, original)
    with pytest.raises(ValueError, match="positive"):
        plot_line_with_moving_average(data, window=0)


def test_grouped_template_accepts_custom_axes_and_validates_cell_references() -> None:
    columns = pd.MultiIndex.from_tuples([("Q3", "Level"), ("Q3", "Delta")])
    frame = pd.DataFrame([[12.25, -2.0], [0.125, 0.2]], columns=columns, index=["Volume", "Share"])
    payload = grouped_metrics_table(
        frame, "Metrics", percentage_rows=[1], bar_columns=[columns[1]], bar_min=-3, bar_max=3
    )["Metrics"]
    rendered = render_table_html(payload["data"], payload["style"])
    assert "12.50%" not in rendered and "12.5%" in rendered and "12.25" in rendered
    assert "linear-gradient" in rendered
    pd.testing.assert_frame_equal(payload["data"], frame)
    with pytest.raises(ValueError, match="out of range"):
        grouped_metrics_table(frame, percentage_rows=[2])
    with pytest.raises(ValueError, match="not found"):
        grouped_metrics_table(frame, bar_columns=[("missing", "Delta")])


def test_cot_timeseries_template_accepts_per_asset_calculation_options() -> None:
    dates = pd.date_range("2022-01-04", periods=120, freq="W-TUE")
    frame = pd.DataFrame(
        {"Long": np.arange(120.0) ** 2 + 1000, "Short": 100.0, "OI": 20000.0, "PX_LAST": 70.0}, index=dates
    )
    original = frame.copy()
    payload = cot_timeseries_table(
        {"Standard": frame, "Long history": frame},
        "Positions",
        summary_options={"contract_value": 1000},
        asset_options={"Long history": {"change_window": 100}},
    )["Positions"]
    result = payload["data"]
    assert result.Asset.tolist() == ["Standard", "Long history"]
    assert result["Net Position"].tolist() == [15061.0, 15061.0]
    assert result["net change z score"].nunique() == 2
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize(
    "calculate, calculate_rows, render, window, position_column, currency_column",
    [
        (
            cot_cme_timeseries_table,
            analysis,
            cot_cme_summary_table,
            52,
            "Net Position (MM)",
            "Weekly Delta Change in $m",
        ),
        (
            cot_ice_mifid_timeseries_table,
            analysis_mifid,
            cot_ice_mifid_summary_table,
            208,
            "Net Position",
            "Weekly Delta Change in $/EUR m",
        ),
    ],
)
def test_cot_timeseries_matches_report_row_assembly_and_summary_rendering(
    calculate, calculate_rows, render, window, position_column, currency_column
):
    dates = pd.date_range(end="2025-07-01", periods=320, freq="W-TUE")
    t = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame({"Long": 1000 + t**2, "Short": 100 + t, "OI": 200000, "PX_LAST": 70 + t / 20}, index=dates)
    if window == 52:
        frame = frame.assign(**{"NC Long": 2000 + t**2, "NC Short": 50 + t})
    observations = {
        "Brent Fut": frame.iloc[:-1],
        "Brent Fut+Opt": frame * 1.1,
        "WTI Fut": frame * 0.9,
        "WTI Fut+Opt": frame,
    }
    groups = {name: name.split()[0] for name in observations}
    links = {name: f"{name.split()[0].lower()}-chart" for name in observations}
    # The report calculates one row per contract, concatenates in report order,
    # and retains the first row's week heading when later rows have other dates.
    rows = pd.concat(
        [cot_summary(data, name, change_window=window, contract_value=1000) for name, data in observations.items()],
        ignore_index=True,
    )
    rows["Group"] = rows.Asset.map(groups)
    rows = rows.rename(
        columns={
            "Asset": "17-Jun to 24-Jun",
            "Net Position": position_column,
            "Weekly Delta Change in millions": currency_column,
        }
    )
    expected = render(rows, "Report", group_column="Group", plot_links=links)["Report"]
    calculated_rows = calculate_rows(observations, summary_options={"contract_value": 1000}, asset_groups=groups)
    pd.testing.assert_frame_equal(calculated_rows, expected["data"].drop(columns="_plot_link"))
    actual = calculate(
        observations, "Report", summary_options={"contract_value": 1000}, asset_groups=groups, plot_links=links
    )["Report"]
    pd.testing.assert_frame_equal(actual["data"], expected["data"])
    assert actual["style"] == expected["style"]
    assert actual["data"].iloc[:, 0].tolist() == list(observations)
    style = resolve_table_style(actual["data"], actual["style"])
    assert "Weekly Delta Change in millions" not in style.visible_columns
    assert style.cell_css[(1, position_column)]["border-bottom"] == "1px solid #000000"
    custom = calculate(observations, "Report", label_column="Instrument", position_label="Custom net")["Report"]
    assert custom["data"].columns[0] == "Instrument"
    assert "Custom net" in custom["data"]
    if window == 52:
        macro = cot_macro_timeseries_table(observations)
        assert list(macro) == ["Speculators Net Position"]
        pd.testing.assert_frame_equal(
            macro["Speculators Net Position"]["data"],
            cot_macro_summary_table(analysis(observations))["Speculators Net Position"]["data"],
        )
    with pytest.raises(ValueError, match="asset_groups"):
        calculate(observations, asset_groups={"Unknown": "Group"})
    with pytest.raises(ValueError, match="Unknown assets"):
        cot_timeseries_table({"Standard": frame}, asset_options={"typo": {}})


@pytest.mark.parametrize(
    "template, window, position_column",
    [
        (cot_cme_timeseries_table, 52, "Net Position (MM)"),
        (cot_ice_mifid_timeseries_table, 208, "Net Position"),
    ],
)
def test_cot_calculation_presets_apply_ecm_windows_and_allow_explicit_overrides(template, window, position_column):
    dates = pd.date_range("2020-01-07", periods=320, freq="W-TUE")
    t = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame(
        {"Long": 1000 + t**2, "Short": 50 + t, "OI": 200000 + t, "PX_LAST": 70 + np.sin(t / 8)}, index=dates
    )
    original = frame.copy()
    payload = template({"Asset Fut": frame}, "Positions")["Positions"]
    row = payload["data"].iloc[0]
    net = frame.Long - frame.Short
    assert row[position_column] == net.iloc[-1]
    assert row["_change_window"] == window
    assert row["net change z score"] == pytest.approx(net.diff().iloc[-1] / net.diff().tail(window).std())
    assert row["4w delta change z score"] == pytest.approx(net.diff(4).iloc[-1] / net.diff(4).tail(window).std())
    price_changes = frame.PX_LAST.pct_change(4).tail(52)
    assert row["4w price change z score"] == pytest.approx(
        (price_changes.iloc[-1] - price_changes.mean()) / price_changes.std()
    )
    assert position_column in resolve_table_style(payload["data"], payload["style"]).visible_columns
    overridden = template(
        {"Shared": frame, "Override": frame},
        "Positions",
        summary_options={"change_window": 60},
        asset_options={"Override": {"change_window": 80}},
    )["Positions"]["data"]
    assert overridden["_change_window"].tolist() == [60, 80]
    pd.testing.assert_frame_equal(frame, original)
