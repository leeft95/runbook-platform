from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from runbook.core.pdl.models import (
    PDLLinkDestination,
    PDLLinkKind,
    PDLManifest,
    PDLPage,
    PDLPageType,
    PDLTableBlock,
    PDLTableLink,
    PDLTextBlock,
)
from runbook.core.table.models import TableArtifactRef, TableLink


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
    assert "links" not in PDLTableBlock(name="summary_tbl", row=1, col=1, data_ref="tables/summary.parquet").model_dump(
        mode="json"
    )


def test_pdl_spec_table_block_contains_style_fields() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    table_block_props = payload["$defs"]["tableBlock"]["allOf"][1]["properties"]
    assert "style_ref" in table_block_props
    assert "html_ref" in table_block_props
    assert "style_key" in table_block_props


def test_pdl_spec_supports_linked_table_blocks_in_02() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["$id"] == "https://runbook.dev/schemas/pdl-core-0.2.json"
    assert payload["properties"]["schema_version"]["enum"] == ["pdl-core/0.1", "pdl-core/0.2"]
    assert "links" in payload["$defs"]["tableBlock"]["allOf"][1]["properties"]
    assert "TableLink" in payload["$defs"]


def test_pdl_01_spec_remains_unchanged_and_has_no_link_contract() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    table_block_props = payload["$defs"]["tableBlock"]["allOf"][1]["properties"]

    assert payload["$id"] == "https://runbook.dev/schemas/pdl-core-0.1.json"
    assert payload["properties"]["schema_version"] == {"type": "string", "const": "pdl-core/0.1"}
    assert "links" not in table_block_props


def test_pdl_spec_documents_field_uniqueness_contract() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    columns = payload["$defs"]["tableBlock"]["allOf"][1]["properties"]["columns"]
    assert columns["x-runbook-unique-by"] == "field"
    assert columns["uniqueItems"] is True


def test_pdl_spec_table_block_ref_fields_match_table_artifact_ref_schema() -> None:
    spec_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    table_block = payload["$defs"]["tableBlock"]["allOf"][1]
    table_block_props = table_block["properties"]
    table_block_required = set(table_block["required"])

    ref_schema = TableArtifactRef.model_json_schema()
    ref_props = ref_schema["properties"]
    ref_required = set(ref_schema.get("required", []))

    for field_name in ("data_ref", "style_ref", "html_ref", "style_key", "links"):
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


def _linked_table_block() -> PDLTableBlock:
    return PDLTableBlock(
        name="summary_tbl",
        row=1,
        col=1,
        data_ref="tables/summary.parquet",
        links=[
            PDLTableLink(
                area="cells",
                field="report_id",
                destination=PDLLinkDestination(kind=PDLLinkKind.report, value="reports/detail"),
            ),
            PDLTableLink(
                area="header",
                field="month",
                destination=PDLLinkDestination(kind=PDLLinkKind.plot, value="plots/month"),
            ),
            PDLTableLink(
                area="index_header",
                destination=PDLLinkDestination(kind=PDLLinkKind.url, value="https://example.test/all"),
            ),
        ],
    )


def test_pdl_table_links_cover_static_dynamic_and_areas() -> None:
    assert (
        TableLink(
            area="cells",
            field="report_id",
            destination={"kind": "report", "value": "reports/detail"},
        ).destination.kind
        == PDLLinkKind.report
    )
    assert TableLink(
        area="cells",
        field="url",
        destination={"kind": "url", "value_field": "url"},
    )
    assert TableLink(area="header", field="month", destination={"kind": "plot", "value": "plots/month"})
    assert TableLink(area="index_header", destination={"kind": "report", "value": "reports/all"})


@pytest.mark.parametrize(
    "payload",
    [
        {"area": "cells", "destination": {"kind": "report", "value": "reports/detail"}},
        {
            "area": "index_header",
            "field": "month",
            "destination": {"kind": "report", "value": "reports/all"},
        },
        {
            "area": "header",
            "field": "month",
            "destination": {"kind": "plot", "value_field": "plot_name"},
        },
        {
            "area": "cells",
            "field": "month",
            "destination": {"kind": "url", "value": "a", "value_field": "url"},
        },
    ],
)
def test_pdl_table_links_reject_invalid_combinations(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        TableLink.model_validate(payload)


def test_pdl_table_links_allow_plot_destinations_in_body_cells() -> None:
    assert (
        TableLink(
            area="cells",
            field="month",
            destination={"kind": "plot", "value": "plots/month"},
        ).destination.kind
        == PDLLinkKind.plot
    )


def test_pdl_link_serialization_is_deterministic_and_02_round_trips() -> None:
    manifest = PDLManifest(
        schema_version="pdl-core/0.2",
        title="Summary",
        snapshot_id="snapshot",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        page=PDLPage(page_type=PDLPageType.grid, rows=1, columns=1, blocks=[_linked_table_block()]),
    )
    payload = manifest.model_dump(mode="json")
    assert payload == manifest.model_dump(mode="json")
    assert PDLManifest.model_validate(payload) == manifest

    with pytest.raises(ValueError, match="pdl-core/0.1 does not support"):
        PDLManifest.model_validate({**payload, "schema_version": "pdl-core/0.1"})


def test_serialized_stage3_links_match_packaged_02_schema_shape() -> None:
    schema_path = Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = PDLManifest(
        schema_version="pdl-core/0.2",
        title="Summary",
        snapshot_id="snapshot",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        page=PDLPage(page_type=PDLPageType.grid, rows=1, columns=1, blocks=[_linked_table_block()]),
    ).model_dump(mode="json")

    table = payload["page"]["blocks"][0]
    link_schema = schema["$defs"]["TableLink"]
    destination_schema = schema["$defs"]["TableLinkDestination"]
    assert payload["schema_version"] in schema["properties"]["schema_version"]["enum"]
    assert table["links"]
    for link in table["links"]:
        assert link["area"] in link_schema["properties"]["area"]["enum"]
        destination = link["destination"]
        assert destination["kind"] in schema["$defs"]["TableLinkKind"]["enum"]
        assert set(destination) & {"value", "value_field"}
        assert len(set(destination) & {"value", "value_field"}) == 1
        selected = next(key for key in ("value", "value_field") if key in destination)
        assert destination[selected]
        assert destination_schema["properties"][selected]["type"] == ["string", "null"]
        if link["area"] == "index_header":
            assert "field" not in link
        else:
            assert link["field"]
