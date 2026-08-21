from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pyarrow as pa
import pytest
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.sdk import column, currency, infer_columns, merge_columns
from runbook.sdk.authoring import report, required_aliases
from runbook.sdk.discovery import discover_report_definition
from runbook.sdk.extensions.dash import (
    DashIds,
    dashboard,
    interaction,
    multi_select,
    parse_dash_extension,
    validate_dash_manifest,
)


def test_interaction_discovery_preserves_calc_and_page() -> None:
    module = SimpleNamespace(ALIASES=required_aliases(history="history"))

    @report.calc("history")
    def calc(ctx: object) -> pd.DataFrame:
        return pd.DataFrame()

    @report.interaction("filter")
    def filter_report(ctx: object, state: dict[str, object]) -> dict[str, str]:
        return {"summary": "ok"}

    @report.page
    def page(ctx: object) -> PDLManifest:
        return PDLManifest(
            title="T",
            snapshot_id="s",
            as_of="2024-01-01T00:00:00Z",
            page=PDLPage(
                page_type=PDLPageType.grid,
                rows=1,
                columns=1,
                blocks=[PDLTextBlock(name="summary", text="ok", row=1, col=1)],
            ),
        )

    module.calc = calc
    module.filter_report = filter_report
    module.page = page
    definition = discover_report_definition(module)
    assert definition.calc_fns["history"] is calc
    assert definition.interaction_fns == {"filter": filter_report}
    assert definition.page_fn is page


def test_duplicate_interaction_names_are_rejected() -> None:
    module = SimpleNamespace(ALIASES=required_aliases(history="history"))

    @report.calc("history")
    def calc(ctx: object) -> pd.DataFrame:
        return pd.DataFrame()

    @report.interaction("same")
    def first(ctx: object, state: dict[str, object]) -> dict[str, str]:
        return {}

    @report.interaction("same")
    def second(ctx: object, state: dict[str, object]) -> dict[str, str]:
        return {}

    @report.page
    def page(ctx: object) -> PDLManifest:
        raise AssertionError

    module.calc, module.first, module.second, module.page = calc, first, second, page
    with pytest.raises(ValueError, match="duplicate report interaction"):
        discover_report_definition(module)


def test_semantic_inference_and_override() -> None:
    schema = pa.schema([("book", pa.string()), ("pnl", pa.float64()), ("date", pa.date32())])
    inferred = infer_columns(schema)
    merged = merge_columns(schema, [column("book", role="identifier"), column("pnl", format=currency("GBP"))])
    assert [item.role.value if item.role else None for item in inferred] == ["dimension", "measure", "time"]
    assert merged[0].role.value == "identifier"
    assert merged[1].format is not None and merged[1].format.kind == "currency"
    with pytest.raises(ValueError, match="unknown fields"):
        merge_columns(schema, [column("missing")])


def test_dash_extension_validation_and_namespacing() -> None:
    manifest = PDLManifest(
        title="T",
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", text="ok", row=1, col=1)],
        ),
        extensions={
            "dash": dashboard(
                controls=[multi_select("book", options=["A"])],
                interactions=[interaction(handler="filter", inputs=["book"], outputs=["summary"])],
            ).model_dump(mode="json")
        },
    )
    extension = parse_dash_extension(manifest)
    definition = SimpleNamespace(interaction_fns={"filter": lambda ctx, state: {}})
    validate_dash_manifest(manifest, extension, definition)
    assert DashIds("one").block("summary") != DashIds("two").block("summary")
    assert DashIds("one").control("book") != DashIds("two").control("book")
    with pytest.raises(ValueError, match="unknown control"):
        bad = manifest.model_copy(
            update={
                "extensions": {
                    "dash": dashboard(
                        controls=[],
                        interactions=[interaction(handler="filter", inputs=["book"], outputs=["summary"])],
                    ).model_dump(mode="json")
                }
            }
        )
        validate_dash_manifest(bad, parse_dash_extension(bad), definition)
