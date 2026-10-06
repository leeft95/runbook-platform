from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from runbook.core.pdl.models import PDLTableBlock
from runbook.core.storage import BlobStore
from runbook.core.report_artifacts import ArtifactRegistry
from runbook.core.table import TableStylePlan, render_table_html
from runbook.sdk.extensions.dash.renderer import _build_ag_grid, _build_native_table


def test_multiindex_table_survives_parquet_and_preserves_groups_in_both_dash_renderers(tmp_path) -> None:
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
            "links": [{"area": "index", "field": str(index[0]), "destination": {"kind": "report", "value": "europe"}}],
        }
    )
    store = BlobStore(f"file:{tmp_path}")
    registry = ArtifactRegistry(
        table_ref_resolver=lambda name: f"tables/{name}.parquet",
        table_writer=lambda name, data: store.put_immutable(f"tables/{name}.parquet", data.to_parquet(index=True)),
    )
    ref = registry.table(frame, name="windows", style=plan)
    payloads = registry.payloads()
    for key, value in payloads.table_styles.items():
        store.put_json(key, value)
    for key, value in payloads.table_htmls.items():
        store.put(key, value.encode())
    assert registry.table(frame.copy(), name="windows", style=plan) == ref
    restored = pd.read_parquet(tmp_path / ref.data_ref)
    pd.testing.assert_frame_equal(restored, frame)
    block = PDLTableBlock(name="windows", data_ref=ref.data_ref, style_ref=ref.style_ref, row=1, col=1)
    ctx = SimpleNamespace(_artifact_store=store, _artifact_prefix="")
    native = _build_native_table(restored, block, "windows", ctx)
    headers = native.children[0].children
    assert headers[0].children[2].children == "Jan"
    assert headers[0].children[2].colSpan == 2
    assert [cell.children for cell in headers[-1].children[:2]] == ["Region", "Measure"]
    body = native.children[1].children
    assert body[0].children[0].children == "Europe"
    assert body[0].children[0].rowSpan == 2
    assert body[0].children[1].children.href == "/report/europe"
    assert body[0].children[2].children == "12.5%"
    assert body[1].children[0].children == "Spread"
    assert 'rowspan="2">Europe</th>' in render_table_html(restored, plan)
    grid = _build_ag_grid(restored, block, ctx, None, {})
    assert [col["headerName"] for col in grid.column_defs] == ["Region", "Measure", "Jan", "Feb"]
    assert [col["headerName"] for col in grid.column_defs[2]["children"]] == ["Level", "Change", "_signal"]
    assert grid.column_defs[2]["children"][2]["hide"] is True
    assert grid.row_data[0][level] == 0.125
    assert grid.row_data[0]["__runbook_formats__"][level] == "12.5%"
    assert grid.row_data[0]["__runbook_index_0__"] == "Europe"
    assert grid.row_data[0]["__runbook_index_1__"] == "Returns"
