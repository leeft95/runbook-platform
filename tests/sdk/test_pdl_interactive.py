from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pyarrow as pa
import pytest
from runbook.core.data import Snapshot
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTableBlock, PDLTextBlock
from runbook.core.storage import BlobStore
from runbook.sdk import (
    column,
    currency,
    date,
    infer_columns,
    merge_columns,
    number,
    percent,
)
from runbook.sdk import (
    datetime as datetime_format,
)
from runbook.sdk.authoring import report, required_aliases
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import ReportDefinition, discover_report_definition
from runbook.sdk.extensions.dash import (
    DashIds,
    dashboard,
    interaction,
    multi_select,
    parse_dash_extension,
    render_dash_page,
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
    schema = pa.schema(
        [
            ("book", pa.string()),
            ("flag", pa.bool_()),
            ("count", pa.int64()),
            ("pnl", pa.float64()),
            ("ratio", pa.decimal128(10, 2)),
            ("date", pa.date32()),
            ("timestamp", pa.timestamp("us", tz="UTC")),
        ]
    )
    inferred = infer_columns(schema)
    merged = merge_columns(schema, [column("book", role="identifier"), column("pnl", format=currency("GBP"))])
    assert [item.role.value if item.role else None for item in inferred] == [
        "dimension",
        "dimension",
        "measure",
        "measure",
        "measure",
        "time",
        "time",
    ]
    assert inferred[2].aggregation.value == "sum"
    assert inferred[4].aggregation.value == "sum"
    assert inferred[5].format.kind == "date"
    assert inferred[6].format.kind == "datetime"
    assert merged[0].role.value == "identifier"
    assert merged[3].format is not None and merged[3].format.kind == "currency"
    with pytest.raises(ValueError, match="unknown fields"):
        merge_columns(schema, [column("missing")])
    with pytest.raises(ValueError, match="aggregation is only valid for measure columns"):
        merge_columns(schema, [column("book", aggregation="sum")])
    with pytest.raises(ValueError, match="duplicate fields"):
        merge_columns(schema, [column("book"), column("book")])


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

    duplicate_controls = manifest.model_copy(
        update={
            "extensions": {
                "dash": dashboard(
                    controls=[multi_select("book"), multi_select("book")],
                ).model_dump(mode="json")
            }
        }
    )
    with pytest.raises(ValueError, match="control names must be unique"):
        validate_dash_manifest(duplicate_controls, parse_dash_extension(duplicate_controls), definition)

    duplicate_outputs = manifest.model_copy(
        update={
            "extensions": {
                "dash": dashboard(
                    controls=[multi_select("book")],
                    interactions=[
                        interaction(handler="filter", inputs=["book"], outputs=["summary"]),
                        interaction(handler="other", inputs=["book"], outputs=["summary"]),
                    ],
                ).model_dump(mode="json")
            }
        }
    )
    definition_with_other = SimpleNamespace(
        interaction_fns={"filter": lambda ctx, state: {}, "other": lambda ctx, state: {}}
    )
    with pytest.raises(ValueError, match="owned by both"):
        validate_dash_manifest(duplicate_outputs, parse_dash_extension(duplicate_outputs), definition_with_other)

    with pytest.raises(ValueError, match="unknown output"):
        unknown_output = manifest.model_copy(
            update={
                "extensions": {
                    "dash": dashboard(
                        controls=[multi_select("book")],
                        interactions=[interaction(handler="filter", inputs=["book"], outputs=["missing"])],
                    ).model_dump(mode="json")
                }
            }
        )
        validate_dash_manifest(unknown_output, parse_dash_extension(unknown_output), definition)

    with pytest.raises(ValueError, match="not registered"):
        unknown_handler = manifest.model_copy(
            update={
                "extensions": {
                    "dash": dashboard(
                        controls=[multi_select("book")],
                        interactions=[interaction(handler="missing", inputs=["book"], outputs=["summary"])],
                    ).model_dump(mode="json")
                }
            }
        )
        validate_dash_manifest(unknown_handler, parse_dash_extension(unknown_handler), definition)

    unsupported = manifest.model_copy(
        update={"extensions": {"dash": {"schema_version": "pdl-dash/9.9", "controls": [], "interactions": []}}}
    )
    with pytest.raises(ValueError, match="unsupported pdl-dash schema version"):
        parse_dash_extension(unsupported)


def test_date_formats_have_no_ignored_pattern_contract() -> None:
    from runbook.core.pdl.models import PDLDateFormat, PDLDateTimeFormat
    from runbook.sdk import date
    from runbook.sdk import datetime as datetime_format

    assert date().model_dump(mode="json") == {"kind": "date"}
    assert datetime_format().model_dump(mode="json") == {"kind": "datetime"}
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        PDLDateFormat(pattern="ignored")
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        PDLDateTimeFormat(pattern="ignored")


def test_rendered_table_uses_logical_schema_and_trusted_grid_props(tmp_path) -> None:
    store = BlobStore(f"file:{tmp_path}")
    ctx = Ctx(
        snapshot=Snapshot(
            snapshot_id="a" * 64,
            watermark=datetime(2024, 1, 1, tzinfo=timezone.utc),
            datasets={},
        ),
        store=store,
        artifact_store=store,
        report_id="r",
        config={},
        code_version="c",
        context_hash="h",
        artifact_prefix="reports/r",
    )
    ref = ctx.artifact.table(
        pd.DataFrame(
            {
                "book": ["Alpha"],
                "amount": [12.5],
                "currency_amount": [12.5],
                "ratio": [0.125],
                "date": ["2024-01-01"],
                "timestamp": ["2024-01-01T12:30:00Z"],
            }
        ),
        name="positions",
    )
    manifest = PDLManifest(
        title="Grid",
        snapshot_id="s" * 64,
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[
                PDLTableBlock(
                    name="positions",
                    data_ref=ref.data_ref,
                    row=1,
                    col=1,
                    columns=[
                        column("book"),
                        column("amount", role="measure", format=number(decimals=2)),
                        column("currency_amount", role="measure", format=currency("GBP", decimals=2)),
                        column("ratio", role="measure", format=percent(decimals=2)),
                        column("date", role="time", format=date()),
                        column("timestamp", role="time", format=datetime_format()),
                    ],
                )
            ],
        ),
        extensions={"dash": dashboard().model_dump(mode="json")},
    )
    definition = ReportDefinition([], {}, lambda _: manifest, {})
    page = render_dash_page(manifest, definition, ctx, namespace="grid")
    layout = page.layout()

    def find_grid(node):
        if node.__class__.__name__ == "AgGrid":
            return node
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found = find_grid(child)
                if found is not None:
                    return found
        elif children is not None:
            return find_grid(children)
        return None

    grid = find_grid(layout)
    assert grid is not None
    payload = grid.to_plotly_json()
    encoded = str(payload)
    assert "__index_level_0__" not in encoded
    assert payload["props"]["enableEnterpriseModules"] is True
    assert payload["props"]["dangerously_allow_code"] is True
    assert all(value in encoded for value in ("book", "amount", "currency_amount", "ratio", "date", "timestamp"))
    assert "toLocaleString" in encoded and "toLocaleDateString" in encoded
    by_field = {item["field"]: item for item in payload["props"]["columnDefs"]}
    assert by_field["date"]["cellDataType"] == "dateString"
    assert by_field["timestamp"]["cellDataType"] == "dateTimeString"
    assert by_field["date"]["sortable"] is True and by_field["date"]["filter"] == "agDateColumnFilter"
    assert by_field["timestamp"]["sortable"] is True and by_field["timestamp"]["filter"] == "agDateColumnFilter"
    assert by_field["date"]["filterParams"] == {"inRangeInclusive": True}
    assert by_field["timestamp"]["filterParams"] == {"inRangeInclusive": True}
    formatters = [item["valueFormatter"] for item in payload["props"]["columnDefs"] if "valueFormatter" in item]
    assert all(set(formatter) == {"function"} for formatter in formatters)
    formatter_sources = [formatter["function"] for formatter in formatters]
    assert any("style: 'currency'" in source for source in formatter_sources)
    assert any("style: 'percent'" in source for source in formatter_sources)
    assert "toLocaleString" in by_field["amount"]["valueFormatter"]["function"]
    assert "style: 'currency'" in by_field["currency_amount"]["valueFormatter"]["function"]
    assert "style: 'percent'" in by_field["ratio"]["valueFormatter"]["function"]
    assert "toLocaleDateString" in by_field["date"]["valueFormatter"]["function"]
    assert "toLocaleString" in by_field["timestamp"]["valueFormatter"]["function"]
