from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest
from runbook.core.pdl.models import (
    PDLLinkBlock,
    PDLManifest,
    PDLPage,
    PDLPageType,
)


def _manifest(block: PDLLinkBlock, *, schema_version: str = "pdl-core/0.2") -> PDLManifest:
    return PDLManifest(
        schema_version=schema_version,
        title="Report",
        snapshot_id="snapshot",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        page=PDLPage(page_type=PDLPageType.grid, rows=1, columns=1, blocks=[block]),
    )


@pytest.mark.parametrize(
    ("kind", "value"),
    [("report", "child/report"), ("plot", "seasonal"), ("url", "https://example.test/methodology")],
)
def test_standalone_link_block_accepts_static_destinations(kind: str, value: str) -> None:
    block = PDLLinkBlock(name="link", row=1, col=1, label="Open", destination={"kind": kind, "value": value})

    assert _manifest(block).model_dump(mode="json")["page"]["blocks"][0]["type"] == "link"
    assert PDLManifest.model_validate(_manifest(block).model_dump(mode="json")) == _manifest(block)


def test_standalone_link_block_rejects_empty_label_and_dynamic_destination() -> None:
    with pytest.raises(ValueError):
        PDLLinkBlock(name="link", row=1, col=1, label="", destination={"kind": "report", "value": "child"})
    with pytest.raises(ValueError, match="static"):
        PDLLinkBlock(
            name="link",
            row=1,
            col=1,
            label="Open",
            destination={"kind": "report", "value_field": "report_id"},
        )


def test_standalone_link_block_rejects_unsafe_url() -> None:
    with pytest.raises(ValueError, match="http or https"):
        PDLLinkBlock(name="link", row=1, col=1, label="Open", destination={"kind": "url", "value": "javascript:bad"})


def test_pdl_01_manifest_rejects_standalone_link() -> None:
    block = PDLLinkBlock(name="link", row=1, col=1, label="Open", destination={"kind": "report", "value": "child"})

    with pytest.raises(ValueError, match="pdl-core/0.1 does not support"):
        _manifest(block, schema_version="pdl-core/0.1")


def test_packaged_02_schema_contains_static_link_block_and_01_guard() -> None:
    schema = json.loads(
        Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json").read_text(encoding="utf-8")
    )
    link_block = schema["$defs"]["linkBlock"]
    assert "linkBlock" in [item["$ref"].rsplit("/", 1)[-1] for item in schema["$defs"]["block"]["oneOf"]]
    assert link_block["allOf"][1]["properties"]["label"]["minLength"] == 1
    destination = link_block["allOf"][1]["properties"]["destination"]["allOf"][1]
    assert destination["required"] == ["value"]
    assert destination["not"] == {"required": ["value_field"]}
    conditional = link_block["allOf"][1]["properties"]["destination"]["allOf"][2]
    assert conditional["then"]["properties"]["value"]["pattern"]
    guard = schema["allOf"][0]["then"]["properties"]["page"]["properties"]["blocks"]
    assert any(
        item.get("properties", {}).get("type", {}).get("const") == "link" for item in guard["not"]["contains"]["anyOf"]
    )

    legacy = json.loads(
        Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec.json").read_text(encoding="utf-8")
    )
    assert "linkBlock" not in legacy["$defs"]


def test_packaged_02_schema_validates_standalone_url_safety() -> None:
    schema = json.loads(
        Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json").read_text(encoding="utf-8")
    )
    validator_type = getattr(jsonschema, "Draft202012Validator", jsonschema.Draft7Validator)
    validator = validator_type(schema)

    def payload(value: str) -> dict[str, object]:
        return {
            "schema_version": "pdl-core/0.2",
            "title": "Report",
            "snapshot_id": "snapshot",
            "as_of": "2026-01-01T00:00:00Z",
            "page": {
                "page_type": "grid",
                "rows": 1,
                "columns": 1,
                "blocks": [
                    {
                        "type": "link",
                        "name": "link",
                        "row": 1,
                        "col": 1,
                        "label": "Open",
                        "destination": {"kind": "url", "value": value},
                    }
                ],
            },
        }

    validator.validate(payload("HTTPS://example.test/methodology"))
    for unsafe in (
        "javascript:bad",
        " https://example.test",
        "https://example.test ",
        "https://example.test/bad path",
        "https://example.test/bad\npath",
        "https://example.test/bad\x7fpath",
    ):
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload(unsafe))
