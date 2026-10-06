from __future__ import annotations

import pandas as pd
import pytest
from runbook.core.table import TableStylePlan, render_table_html, resolve_table_style, table_style_hash


def test_row_and_cell_formats_override_columns_without_changing_values() -> None:
    frame = pd.DataFrame(
        {"Latest": [1234.5, 0.1234, None], "Change": [10.25, -0.02, 0.1]}, index=["Stock", "% OI", "Missing"]
    )
    original = frame.copy()
    plan = TableStylePlan.model_validate(
        {
            "format": {
                "precision": 0,
                "na_rep": "-",
                "columns": {"Latest": "{:,.1f}"},
                "rows": [
                    {"row_ref": {"mode": "label", "value": "% OI"}, "spec": "{0:.2%}"},
                    {"row_ref": {"mode": "position", "value": 1}, "columns": ["Change"], "spec": "{:.1%}"},
                    {"row_ref": {"mode": "label", "value": "Missing"}, "spec": "{:.1%}"},
                ],
            },
        }
    )
    resolved = resolve_table_style(frame, plan)
    assert resolved.cell_formats[(1, "Latest")].digits == 2
    assert resolved.cell_formats[(1, "Change")].digits == 1
    assert (0, "Latest") not in resolved.cell_formats
    html = render_table_html(frame, plan)
    for value in ("1,234.5", "10", "12.34%", "-2.0%", "-", "10.0%"):
        assert f">{value}</td>" in html
    assert render_table_html(frame, TableStylePlan.model_validate_json(plan.model_dump_json())) == html
    assert resolve_table_style(frame, {"format": resolved.format}).cell_formats == resolved.cell_formats
    assert table_style_hash(plan) != table_style_hash({"format": {"columns": {"Latest": "{:,.1f}"}}})
    pd.testing.assert_frame_equal(frame, original)


def test_row_formats_validate_full_input_before_truncation_and_hiding() -> None:
    frame = pd.DataFrame({"Value": [0.1, 0.2, 0.3]}, index=["a", "b", "c"])
    plan = {
        "format": {"rows": [{"row_ref": {"mode": "position", "value": 2}, "spec": "{:.1%}"}]},
        "options": {"max_rows": 2, "hidden_rows": [{"mode": "position", "value": 0}]},
    }
    resolved = resolve_table_style(frame, plan)
    assert resolved.cell_formats == {}
    assert resolved.hidden_rows == {0}
    with pytest.raises(ValueError, match="out of range"):
        resolve_table_style(frame.iloc[:2], plan)
    with pytest.raises(ValueError, match="column label not found"):
        resolve_table_style(
            frame,
            {
                "format": {
                    "rows": [{"row_ref": {"mode": "position", "value": 0}, "columns": ["absent"], "spec": "{:.0f}"}]
                }
            },
        )
    with pytest.raises(ValueError, match="does not support row formats"):
        TableStylePlan.model_validate({**plan, "schema_version": "table-style/0.1"})
