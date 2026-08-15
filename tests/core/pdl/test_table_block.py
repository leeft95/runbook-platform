from __future__ import annotations

import json
from pathlib import Path

import pytest
from runbook.core.pdl.models import PDLPage, PDLPageType, PDLTableBlock, PDLTextBlock
from runbook.core.table.models import TableArtifactRef


def test_pdl_table_block_accepts_optional_style_refs() -> None:
    block = PDLTableBlock(
        name="summary_tbl",
        row=1,
        col=1,
        data_ref="tables/summary.parquet",
        style_ref="styles/abc123.json",
        html_ref="tables/summary.abc123.html",
        style_key="summary_default",
    )
    assert block.data_ref == "tables/summary.parquet"
    assert block.style_ref == "styles/abc123.json"
    assert block.html_ref == "tables/summary.abc123.html"
    assert block.style_key == "summary_default"


def test_pdl_spec_table_block_contains_style_fields() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    table_block_props = payload["$defs"]["tableBlock"]["allOf"][1]["properties"]
    assert "style_ref" in table_block_props
    assert "html_ref" in table_block_props
    assert "style_key" in table_block_props


def test_pdl_spec_table_block_ref_fields_match_table_artifact_ref_schema() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    table_block = payload["$defs"]["tableBlock"]["allOf"][1]
    table_block_props = table_block["properties"]
    table_block_required = set(table_block["required"])

    ref_schema = TableArtifactRef.model_json_schema()
    ref_props = ref_schema["properties"]
    ref_required = set(ref_schema.get("required", []))

    for field_name in ("data_ref", "style_ref", "html_ref", "style_key"):
        pdl_prop = dict(table_block_props[field_name])
        ref_prop = dict(ref_props[field_name])
        pdl_prop.pop("title", None)
        ref_prop.pop("title", None)
        assert pdl_prop == ref_prop

    assert "data_ref" in table_block_required
    assert ref_required == {"data_ref"}


def test_pdl_page_flex_grid_requires_rows_and_columns() -> None:
    with pytest.raises(ValueError, match="rows and columns are required when page_type is 'grid' or 'flex_grid'"):
        PDLPage(
            page_type=PDLPageType.flex_grid,
            blocks=[PDLTextBlock(name="summary", row=1, col=1, text="hello")],
        )


def test_pdl_spec_page_type_includes_flex_grid() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    page_type_enum = payload["properties"]["page"]["properties"]["page_type"]["enum"]
    assert "flex_grid" in page_type_enum
