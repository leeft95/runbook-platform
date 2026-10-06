from __future__ import annotations

import pandas as pd
import pytest
from runbook.core.table import TableDataBar, TableStylePlan, render_table_html, resolve_table_style


def test_bounded_data_bars_clip_geometry_and_preserve_values_and_highlights() -> None:
    frame = pd.DataFrame({"Percentile": [-2.0, -0.5, 0.0, 0.25, 2.0, None]})
    plan = TableStylePlan.model_validate(
        {
            "format": {"columns": {"Percentile": "{:.1%}"}, "na_rep": "-"},
            "rules": [
                {
                    "id": "bar",
                    "target": {"scope": "columns", "labels": ["Percentile"]},
                    "action": {"background_color": "lightblue", "data_bar": {"vmin": -1, "vmax": 1}},
                }
            ],
        }
    )
    resolved = resolve_table_style(frame, plan)
    bars = [resolved.cell_css[(i, "Percentile")]["background-image"] for i in range(len(frame))]
    assert "#d65f5f 0.000%" in bars[0] and "#d65f5f 50.000%" in bars[0]
    assert "#d65f5f 25.000%" in bars[1]
    assert bars[2] == bars[5] == "none"
    assert "#5fba7d 50.000%" in bars[3] and "#5fba7d 62.500%" in bars[3]
    assert "#5fba7d 100.000%" in bars[4]
    assert resolved.cell_css[(0, "Percentile")]["background-color"] == "lightblue"
    html = render_table_html(frame, plan)
    assert ">-200.0%</td>" in html and ">200.0%</td>" in html
    assert "background-image: linear-gradient" in html
    assert html == render_table_html(frame, TableStylePlan.model_validate_json(plan.model_dump_json()))


@pytest.mark.parametrize(
    "values,align,expected",
    [
        ([1.0, 2.0], "mid", "#5fba7d 50.000%"),
        ([-2.0, -1.0], "mid", "#d65f5f 100.000%"),
        ([2.0, 2.0], "mid", "#5fba7d 100.000%"),
        ([0.0, 0.0], "mid", "none"),
        ([None, float("inf")], "mid", "none"),
        ([-1.0, 3.0], "zero", "#d65f5f 33.333%"),
    ],
)
def test_data_bar_auto_bounds_and_degenerate_inputs(values, align, expected) -> None:
    frame = pd.DataFrame({"x": values})
    style = {"rules": [{"id": "bar", "target": {"scope": "all"}, "action": {"data_bar": {"align": align}}}]}
    assert expected in resolve_table_style(frame, style).cell_css[(0, "x")]["background-image"]


def test_data_bar_bounds_are_validated() -> None:
    for bounds in ({"vmin": 2, "vmax": 1}, {"vmin": 1, "vmax": 1}, {"vmax": float("inf")}):
        with pytest.raises(ValueError):
            TableDataBar.model_validate(bounds)
