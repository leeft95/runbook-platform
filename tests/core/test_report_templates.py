from importlib import import_module
from pathlib import Path
import runpy

import numpy as np
import pandas as pd
import pytest

from runbook.core.plotting.templates import plot_line_with_comparison, plot_line_with_moving_average
from runbook.core.table import render_table_html, resolve_table_style
from runbook.core.table.templates import cot_observations_table, grouped_metrics_table


def test_gallery_uses_public_templates_with_resolvable_links_and_serializable_output() -> None:
    tables, charts = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/preview_gallery.py"))[
        "build_examples"
    ]()
    assert len(tables) == 13 and len(charts) == 18
    assert len({item["template"] for item in tables}) == 12
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


def test_cot_observations_template_accepts_per_asset_calculation_options() -> None:
    dates = pd.date_range("2022-01-04", periods=120, freq="W-TUE")
    frame = pd.DataFrame(
        {"Long": np.arange(120.0) ** 2 + 1000, "Short": 100.0, "OI": 20000.0, "PX_LAST": 70.0}, index=dates
    )
    original = frame.copy()
    payload = cot_observations_table(
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
    with pytest.raises(ValueError, match="Unknown assets"):
        cot_observations_table({"Standard": frame}, asset_options={"typo": {}})
