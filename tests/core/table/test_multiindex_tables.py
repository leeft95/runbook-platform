from __future__ import annotations

import pandas as pd
from runbook.core.table import TableStylePlan, render_table_html, resolve_table_style, table_axis_spans


def test_multiindex_formats_signals_hiding_and_links_survive_json_round_trip() -> None:
    columns = pd.MultiIndex.from_tuples(
        [("Jan", "Level"), ("Jan", "Change"), ("Jan", "_signal"), ("Feb", "Level")], names=["Month", "Metric"]
    )
    index = pd.MultiIndex.from_tuples(
        [("Europe", "Returns"), ("Europe", "Spread"), ("Asia", "Returns")], names=["Region", "Measure"]
    )
    frame = pd.DataFrame(
        [[0.125, -0.02, -2, 0.2], [10.25, 1.5, 2, 11.5], [0.33, 0.01, 0, 0.4]], index=index, columns=columns
    )
    level, change, signal, feb = map(str, columns)
    plan = TableStylePlan.model_validate(
        {
            "format": {
                "columns": {level: "{:.1f}", change: "{:.2f}", feb: "{:.1f}"},
                "rows": [
                    {
                        "row_ref": {"mode": "label", "value": ("Europe", "Returns")},
                        "columns": [level, feb],
                        "spec": "{:.1%}",
                    }
                ],
            },
            "options": {"hidden_columns": [signal]},
            "rules": [
                {
                    "id": "negative",
                    "target": {"scope": "columns", "labels": [level]},
                    "condition": {"op": "lt", "lhs_column": signal, "rhs": {"kind": "literal", "value": 0}},
                    "action": {"background_color": "pink"},
                }
            ],
            "links": [
                {"area": "cells", "field": level, "destination": {"kind": "plot", "value": "detail"}},
                {"area": "header", "field": level, "destination": {"kind": "plot", "value": "overview"}},
                {"area": "index", "field": str(index[0]), "destination": {"kind": "plot", "value": "region"}},
                {"area": "index_header", "destination": {"kind": "plot", "value": "all"}},
            ],
        }
    )
    restored = TableStylePlan.model_validate_json(plan.model_dump_json())
    resolved = resolve_table_style(frame, restored)
    assert resolved.visible_columns == (level, change, feb)
    assert resolved.cell_css[(0, level)]["background-color"] == "pink"
    html = render_table_html(frame, restored)
    assert html == render_table_html(frame, plan)
    assert 'colspan="2">Jan</th>' in html
    assert 'rowspan="2">Europe</th>' in html
    assert "_signal" not in html
    assert 'data-runbook-plot-name="detail">12.5%</a>' in html
    assert 'data-runbook-plot-name="overview">Level</a>' in html
    assert 'data-runbook-plot-name="region">Returns</a>' in html
    assert 'data-runbook-plot-name="all">Measure</a>' in html
    assert ">Month</th>" in html and ">Metric</th>" in html
    hidden_payload = restored.model_dump()
    hidden_payload["options"]["hidden_rows"] = [{"mode": "label", "value": ["Europe", "Spread"]}]
    hidden = TableStylePlan.model_validate(hidden_payload)
    assert ">Spread</th>" not in render_table_html(frame, hidden)


def test_axis_spans_keep_noncontiguous_groups_and_equal_children_separate() -> None:
    columns = pd.MultiIndex.from_tuples([("Oil", "Last"), ("Oil", "Change"), ("Gas", "Last"), ("Oil", "Last")])
    spans = table_axis_spans(columns)
    assert spans[0] == [(0, 2, "Oil"), (2, 1, "Gas"), (3, 1, "Oil")]
    assert spans[1] == [(0, 1, "Last"), (1, 1, "Change"), (2, 1, "Last"), (3, 1, "Last")]


def test_multiindex_dates_missing_labels_and_unnamed_header_links() -> None:
    index = pd.MultiIndex.from_tuples([(pd.Timestamp("2025-01-01"), 1), (pd.Timestamp("2025-01-01"), None)])
    frame = pd.DataFrame({"Value": [0.125, 0.2]}, index=index)
    plan = TableStylePlan.model_validate(
        {
            "format": {"rows": [{"row_ref": {"mode": "label", "value": index[0]}, "spec": "{:.1%}"}]},
            "links": [{"area": "index_header", "destination": {"kind": "report", "value": "summary"}}],
        }
    )
    html = render_table_html(frame, plan)
    assert html == render_table_html(frame, TableStylePlan.model_validate_json(plan.model_dump_json()))
    assert ">12.5%</td>" in html
    assert 'data-runbook-report-id="summary"' in html
