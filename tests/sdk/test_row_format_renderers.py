from __future__ import annotations

from types import SimpleNamespace
import re

import pandas as pd
from runbook.core.pdl.models import PDLTableBlock
from runbook.core.storage import BlobStore
from runbook.core.table import TableFormatNumber, TableStylePlan, render_table_html, rollup_table_hst
from runbook.sdk.extensions.dash.renderer import _build_ag_grid, _build_native_table
from runbook.sdk.table_style import action, format_number, format_row, rule, table_style, target_columns


def test_row_format_plan_persists_and_renders_in_html_native_dash_and_ag_grid(tmp_path) -> None:
    frame = pd.DataFrame(
        {"Label": ["Stock", "% OI", "Missing"], "Latest": [1234.5, 0.1234, None], "Change": [10.25, -0.02, 0.1]}
    )
    style = table_style(
        formats=[
            format_number("Latest", digits=1, thousands=True),
            {"column": "Change", "spec": TableFormatNumber(digits=0)},
            format_row({"mode": "position", "value": 1}, "{:.2%}", columns=["Latest", "Change"]),
            format_row({"mode": "position", "value": 1}, "{:.1%}", columns=["Change"]),
            format_row({"mode": "position", "value": 2}, "{:.1%}", columns=["Latest"]),
        ],
        show_index=False,
        na_rep="-",
        rules=[rule("change_bar", target_columns(["Change"]), action=action(data_bar={"vmin": -1, "vmax": 1}))],
    )
    plan = TableStylePlan.model_validate(style)
    store = BlobStore(f"file:{tmp_path}")
    store.put_json("style.json", plan.model_dump(mode="json", exclude_none=True))
    store.put("data.parquet", frame.to_parquet())
    frame = pd.read_parquet(tmp_path / "data.parquet")
    block = PDLTableBlock(name="inventory", data_ref="data.parquet", style_ref="style.json", row=1, col=1)
    ctx = SimpleNamespace(_artifact_store=store, _artifact_prefix="")
    table = _build_native_table(frame, block, "inventory", ctx)
    rows = table.children[1].children
    assert [[cell.children for cell in row.children] for row in rows] == [
        ["Stock", "1,234.5", "10"],
        ["% OI", "12.34%", "-2.0%"],
        ["Missing", "-", "0"],
    ]
    html = render_table_html(frame, plan)
    assert ">12.34%</td>" in html and ">-2.0%</td>" in html
    grid = _build_ag_grid(frame, block, ctx, None, {})
    assert grid.row_data[1]["Latest"] == 0.1234
    assert grid.row_data[1]["Change"] == -0.02
    assert grid.row_data[1]["__runbook_formats__"] == {"Latest": "12.34%", "Change": "-2.0%"}
    assert grid.row_data[2]["__runbook_formats__"] == {"Latest": "-"}
    columns = {col["field"]: col for col in grid.column_defs}
    assert columns["Latest"]["filter"] == "agNumberColumnFilter"
    assert "__runbook_formats__" in columns["Latest"]["valueFormatter"]["function"]
    native_bar = rows[1].children[2].style["backgroundImage"]
    assert "linear-gradient" in native_bar and "#d65f5f" in native_bar
    assert grid.row_data[1]["__runbook_styles__"]["Change"]["backgroundImage"] == native_bar
    assert native_bar in html


def test_index_width_and_plain_text_footer_survive_style_storage(tmp_path) -> None:
    frame = pd.DataFrame({"Value": [1]}, index=pd.Index(["Brent"], name="Market"))
    style = table_style(index_width_px=171, footer="Updated <today>")
    store = BlobStore(f"file:{tmp_path}")
    store.put_json("style.json", style)
    ctx = SimpleNamespace(_artifact_store=store, _artifact_prefix="")
    block = PDLTableBlock(name="prices", data_ref="prices.parquet", style_ref="style.json", row=1, col=1)
    table = _build_native_table(frame, block, "prices", ctx)
    assert table.children[0].children.children[0].style["width"] == "171px"
    assert table.children[1].children[0].children[0].style["width"] == "171px"
    assert table.children[2].children.children.children == "Updated <today>"
    assert table.children[2].children.children.colSpan == 2
    grid = _build_ag_grid(frame, block, ctx, None, {})
    assert grid.footer == "Updated <today>"
    assert grid.column_defs[0]["headerName"] == "Market"
    assert grid.column_defs[0]["width"] == 171
    assert grid.row_data[0]["__runbook_index__"] == "Brent"
    assert "Updated &lt;today&gt;" in render_table_html(frame, style)


def test_rollup_total_label_and_values_share_bold_and_top_border_in_all_renderers(tmp_path) -> None:
    source = pd.DataFrame({"Gas": [10.0, 20.0], "Load": [80.0, 100.0]}, index=pd.date_range("2025-06-01", periods=2))
    payload = rollup_table_hst(source, ["Latest", "5d MA"])["Roll-up"]
    frame, style = payload["data"], payload["style"]
    store = BlobStore(f"file:{tmp_path}")
    store.put_json("style.json", style)
    ctx = SimpleNamespace(_artifact_store=store, _artifact_prefix="")
    block = PDLTableBlock(name="power", data_ref="power.parquet", style_ref="style.json", row=1, col=1)
    table = _build_native_table(frame, block, "power", ctx)
    total = table.children[1].children[-1].children
    assert total[0].children.children == "Total"
    assert [cell.children for cell in total[1:]] == ["100", "90"]
    for cell in total:
        assert cell.style["fontWeight"] == "bold"
        assert cell.style["borderTop"] == "1px solid #000000"
    grid = _build_ag_grid(frame, block, ctx, None, {})
    assert grid.row_data[-1]["__runbook_index__"] == "Total"
    assert grid.row_data[-1]["Latest"] == 100.0
    for column in grid.column_defs:
        if column.get("hide"):
            continue
        assert "__runbook_styles__" in column["cellStyle"]["function"]
        css = grid.row_data[-1]["__runbook_styles__"][column["field"]]
        assert css["fontWeight"] == "bold"
        assert css["borderTop"] == "1px solid #000000"
    rendered = render_table_html(frame, style)
    assert ">Total</a>" in rendered
    for selector in (".row_heading.row1", "_row1_col0", "_row1_col1"):
        blocks = [body for group, body in re.findall(r"([^{}]+)\{([^{}]+)\}", rendered) if selector in group]
        assert any("font-weight: bold" in body and "border-top: 1px solid #000000" in body for body in blocks)
