from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pandas as pd
from runbook.core.table import TableStylePlan, cot_table, render_table_html, resolve_table_style


def test_cot_template_replicates_legacy_table_using_shared_models() -> None:
    frame = pd.read_csv("data/fixtures/cot/summary.csv")
    original = frame.copy()
    links = {name: f"cot-{i}" for i, name in enumerate(frame["24-Jun to 01-Jul"])}
    payload = cot_table(
        frame,
        "Managed money",
        label_column="24-Jun to 01-Jul",
        position_column="Net Position (MM)",
        group_column="Group",
        plot_links=links,
    )["Managed money"]
    plan = TableStylePlan.model_validate(payload["style"])
    schema = json.loads(Path("packages/runbook/runbook-core/src/runbook/core/table/spec.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(plan.model_dump(mode="json", exclude_none=True))
    resolved = resolve_table_style(payload["data"], plan)
    assert resolved.cell_css[(0, "24-Jun to 01-Jul")]["background-color"] == "#C6EFCE"
    assert resolved.cell_css[(2, "24-Jun to 01-Jul")]["background-color"] == "#FFC7CE"
    assert resolved.cell_css[(0, "Weekly Delta Change")]["background-color"] == "#C6EFCE"
    assert resolved.cell_css[(2, "Weekly Delta Change")]["background-color"] == "#FFC7CE"
    assert resolved.cell_css[(2, "Weekly Delta Change")]["color"] == "red"
    assert resolved.cell_css[(0, "Weekly Delta Change")]["font-weight"] == "bold"
    assert resolved.cell_css[(1, "Weekly Delta Change")]["border-bottom"] == "1px solid #000000"
    assert "border-bottom" not in resolved.cell_css[(0, "Weekly Delta Change")]
    assert resolved.cell_links[(0, "24-Jun to 01-Jul")].value == "cot-0"
    assert resolved.formats["% OI"].kind == "percent"
    assert resolved.formats["Ref Week VWAP"].digits == 2
    assert not any(field.startswith("_") for field in resolved.visible_columns)
    html = render_table_html(payload["data"], plan)
    assert ">10.0%<" in html and ">72.25<" in html
    assert 'href="plots/cot-0.html"' in html
    assert "_thr_high" not in html and "net pos rank" not in html and ">Group<" not in html
    pd.testing.assert_frame_equal(frame, original)


def test_cot_template_handles_reordered_columns_and_empty_screeners() -> None:
    frame = pd.read_csv("data/fixtures/cot/summary.csv").rename(
        columns={"24-Jun to 01-Jul": "Asset", "Net Position (MM)": "Net Position"}
    )
    frame["Net Position (NC)"] = [50_000, 60_000, -20_000, -30_000]
    payload = cot_table(frame[frame.columns[::-1]], position_label="Dealer Net", group_column="Group")["COT"]
    resolved = resolve_table_style(payload["data"], payload["style"])
    assert resolved.cell_css[(0, "Weekly Delta Change")]["background-color"] == "#C6EFCE"
    assert "Dealer Net" in resolved.visible_columns
    assert resolved.visible_columns[:2] == ("Asset", "Net Position (NC)")
    assert resolved.cell_css[(0, "% OI")]["background-color"] == "#C6EFCE"
    assert resolved.cell_css[(2, "Net Position (NC)")]["color"] == "red"
    empty = cot_table(frame.iloc[:0], group_column="Group")["COT"]
    assert "<table" in render_table_html(empty["data"], empty["style"])
