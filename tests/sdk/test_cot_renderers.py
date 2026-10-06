from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from runbook.core.pdl.models import PDLTableBlock
from runbook.core.storage import BlobStore
from runbook.core.table import TableStylePlan, cot_table
from runbook.sdk.extensions.dash.renderer import _build_native_table


def test_cot_shared_plan_reaches_native_dash_with_formats_rules_and_links(tmp_path) -> None:
    frame = pd.read_csv("data/fixtures/cot/summary.csv")
    payload = cot_table(
        frame,
        label_column="24-Jun to 01-Jul",
        position_column="Net Position (MM)",
        group_column="Group",
        plot_links={"Brent Fut": "cot-brent"},
    )["COT"]
    plan = TableStylePlan.model_validate(payload["style"])
    store = BlobStore(f"file:{tmp_path}")
    store.put_json("styles/cot.json", plan.model_dump(mode="json", exclude_none=True))
    store.put_json("plots/cot-brent.json", {})
    block = PDLTableBlock(
        name="cot", data_ref="cot.parquet", style_ref="styles/cot.json", links=plan.links, row=1, col=1
    )
    table = _build_native_table(
        payload["data"],
        block,
        "cot",
        SimpleNamespace(_artifact_store=store, _artifact_prefix=""),
        lambda kind, value: f"/host/{kind}/{value}",
        {"cot-brent": "plots/cot-brent.json"},
    )
    headers = [cell.children for cell in table.children[0].children.children]
    rows = table.children[1].children
    assert headers[0] == "24-Jun to 01-Jul"
    assert not any(str(header).startswith("_") for header in headers)
    assert "Group" not in headers
    assert rows[0].children[0].children.href == "/host/plot/cot-brent"
    assert rows[0].children[headers.index("% OI")].children == "10.0%"
    assert rows[0].children[headers.index("Ref Week VWAP")].children == "72.25"
    change = headers.index("Weekly Delta Change")
    assert rows[2].children[change].style["backgroundColor"] == "#FFC7CE"
    assert rows[2].children[change].style["color"] == "red"
    assert rows[1].children[change].style["borderBottom"] == "1px solid #000000"
