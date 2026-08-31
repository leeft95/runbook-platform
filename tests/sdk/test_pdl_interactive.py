from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pyarrow as pa
import pytest
from runbook.core.data import Snapshot
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTableBlock, PDLTextBlock
from runbook.core.storage import BlobStore
from runbook.core.table import render_table_html
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
from runbook.sdk.extensions.dash.renderer import _build_ag_grid, _build_native_table, _convert_output
from runbook.sdk.table_style import link_column, link_header, link_index_header


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


def test_table_callback_outputs_normalize_declared_date_and_datetime() -> None:
    block = PDLTableBlock(
        name="positions",
        data_ref="positions.parquet",
        row=1,
        col=1,
        columns=[
            column("day", role="time", format=date()),
            column("moment", role="time", format=datetime_format()),
        ],
    )
    frame = pd.DataFrame(
        {
            "day": [pd.Timestamp("2024-01-01T12:00:00Z")],
            "moment": [pd.Timestamp("2024-01-01T12:30:45.123456Z")],
        }
    )
    assert _convert_output(block, frame) == [{"day": "2024-01-01", "moment": "2024-01-01T12:30:45.123456Z"}]


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


def test_rendered_static_table_is_native_and_preserves_pdl_formats(tmp_path) -> None:
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
        extensions={"dash": dashboard(controls=[multi_select("book", options=["Alpha"])]).model_dump(mode="json")},
    )
    definition = ReportDefinition([], {}, lambda _: manifest, {})
    page = render_dash_page(manifest, definition, ctx, namespace="grid")
    layout = page.layout()
    report_grid = layout.children[2]
    report_block = report_grid.children[0]
    body = report_block.children[0]
    assert len(report_grid.children) == 1
    assert body.__class__.__name__ == "Div"
    assert body.children[0].children[1].id == page.ids.control("book")
    table = body.children[1]
    assert table.__class__.__name__ == "Table"
    assert table.id == page.ids.block("positions")
    assert table.children[0].__class__.__name__ == "Thead"
    assert table.children[1].__class__.__name__ == "Tbody"
    headers = table.children[0].children.children
    assert [header.children for header in headers] == [
        "",
        "book",
        "amount",
        "currency_amount",
        "ratio",
        "date",
        "timestamp",
    ]
    cells = table.children[1].children[0].children
    assert [cell.children for cell in cells] == [
        "0",
        "Alpha",
        "12.50",
        "£12.50",
        "12.50%",
        "Jan 1, 2024",
        "Jan 1, 2024 12:30",
    ]


def test_interactive_table_stays_ag_grid_when_declared_as_output(tmp_path) -> None:
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
    ref = ctx.artifact.table(pd.DataFrame({"book": ["Alpha"]}), name="positions")
    manifest = PDLManifest(
        title="Grid",
        snapshot_id="s" * 64,
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTableBlock(name="positions", data_ref=ref.data_ref, row=1, col=1)],
        ),
        extensions={
            "dash": dashboard(interactions=[interaction(handler="filter", outputs=["positions"])]).model_dump(
                mode="json"
            )
        },
    )
    definition = ReportDefinition([], {}, lambda _: manifest, {"filter": lambda _ctx, _state: {}})
    page = render_dash_page(manifest, definition, ctx, namespace="grid")
    table = page.layout().children[2].children[0].children[0]
    assert table.__class__.__name__ == "AgGrid"


def test_ag_grid_consumes_resolved_style_and_semantic_links(tmp_path) -> None:
    store = BlobStore(f"file:{tmp_path}")
    ctx = SimpleNamespace(_artifact_store=store, _artifact_prefix="reports/r")
    style = {
        "format": {"na_rep": "NA", "columns": {"amount": "{:,.1f}"}},
        "sizing": {"columns": [{"label": "label", "width_px": 140}]},
        "rules": [
            {
                "id": "negative",
                "target": {"scope": "columns", "labels": ["amount"]},
                "condition": {"op": "lt", "rhs": {"kind": "literal", "value": 0}},
                "action": {"background_color": "#fee2e2", "font_weight": "bold"},
            }
        ],
        "options": {"hidden_columns": ["helper"], "hidden_rows": [{"mode": "position", "value": 1}]},
    }
    store.put_json("reports/r/styles/table.json", style)
    store.put_json("reports/r/plots/plot-one.json", {})
    store.put_json("reports/r/plots/plot-two.json", {})
    store.put_json("reports/r/plots/all-a.json", {})
    frame = pd.DataFrame(
        {
            "label": ["one", "hidden", "null"],
            "amount": [-12.5, 1.0, 2.0],
            "report": ["detail/one", "detail/two", None],
            "url": ["https://example.test/one", None, None],
            "plot": ["plot-one", "plot-two", None],
            "helper": ["one-helper", "two-helper", "null-helper"],
        },
        index=pd.Index(["row-a", "row-b", "row-c"], name="Region"),
    )
    block = PDLTableBlock(
        name="table",
        data_ref="table.parquet",
        style_ref="styles/table.json",
        row=1,
        col=1,
        width="40vw",
        links=[
            {"area": "cells", "field": "label", "destination": {"kind": "report", "value_field": "report"}},
            {"area": "cells", "field": "report", "destination": {"kind": "url", "value_field": "url"}},
            {"area": "cells", "field": "plot", "destination": {"kind": "plot", "value_field": "plot"}},
            {"area": "header", "field": "label", "destination": {"kind": "report", "value": "header"}},
            {"area": "index_header", "destination": {"kind": "plot", "value": "all-plots"}},
        ],
        columns=[
            column("label"),
            column("amount", role="measure"),
            column("report", hidden=True),
            column("url"),
            column("plot"),
            column("helper"),
        ],
    )

    def route(kind: str, value: str) -> str:
        return f"/resolved/{kind}/{value}"

    config = _build_ag_grid(
        frame,
        block,
        ctx,
        route,
        {"plot-one": "plots/plot-one.json", "plot-two": "plots/plot-two.json", "all-a": "plots/all-a.json"},
    )
    definitions = {definition["field"]: definition for definition in config.column_defs}
    assert len(config.row_data) == 2
    assert config.row_data[0]["__runbook_links__"] == {
        "label": "/resolved/report/detail/one",
        "report": "https://example.test/one",
        "plot": "/resolved/plot/plot-one",
    }
    assert config.row_data[1]["__runbook_links__"] == {}
    styles = config.row_data[0]["__runbook_styles__"]
    assert styles["amount"]["backgroundColor"] == "#fee2e2"
    assert styles["amount"]["fontWeight"] == "bold"
    assert definitions["label"]["width"] == definitions["label"]["minWidth"] == 140
    assert definitions["helper"]["hide"] is True
    assert definitions["report"]["cellRenderer"]["function"]
    assert definitions["label"]["headerLink"] == "/resolved/report/header"
    assert definitions["label"]["headerComponent"]["function"]
    assert config.column_defs[0]["headerName"] == "Region"
    assert config.column_defs[0]["headerLink"] == "/resolved/plot/all-plots"
    assert config.style["border"] == "2px solid black"
    # Interactive AG Grid keeps its own full-slot sizing model in v0.3.2.
    assert config.style["width"] == "100%"


def test_native_table_consumes_persisted_style_resolution(tmp_path) -> None:
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
    frame = pd.DataFrame(
        {
            "signal": [-1234.56, 10.0, None],
            "ratio": [0.125, 0.5, None],
            "day": ["2024-01-01", "2024-02-03", None],
            "raw": [1234.5, 10.0, None],
            "_mean": [0.0, 0.0, 0.0],
            "_std": [1.0, 1.0, 1.0],
            "empty": ["", "value", None],
        },
        index=["negative", "positive", "missing"],
    )
    style = {
        "format": {
            "na_rep": "NA",
            "precision": 2,
            "thousands": ".",
            "columns": {
                "signal": "{:,.1f}",
                "ratio": "{:.1%}",
                "day": {"kind": "date", "pattern": "%Y/%m/%d"},
            },
        },
        "sizing": {"columns": [{"label": "signal", "width_px": 120}]},
        "rules": [
            {
                "id": "negative",
                "target": {"scope": "columns", "labels": ["signal"]},
                "condition": {"op": "lt", "rhs": {"kind": "literal", "value": 0}},
                "action": {
                    "background_color": "#fee2e2",
                    "font_weight": "bold",
                    "border_bottom": "2px solid #b91c1c",
                },
            }
        ],
        "options": {
            "show_index": False,
            "hidden_columns": ["_std"],
            "global_style": {
                "background_color": "#f8fafc",
                "one_bg_color": True,
                "font_family": "Arial",
                "font_size": "12pt",
                "header_text_align": "left",
                "header_border_bottom": "3px solid #111827",
                "table_border": "1px solid #111827",
            },
        },
    }
    ref = ctx.artifact.table(frame, name="styled", style=style)
    for style_ref, payload in ctx.artifact.payloads().table_styles.items():
        store.put_json(f"reports/r/{style_ref}", payload)
    block = PDLTableBlock(
        name="styled",
        data_ref=ref.data_ref,
        style_ref=ref.style_ref,
        row=1,
        col=1,
        columns=[
            column("signal", label="Signal"),
            column("ratio", label="Ratio"),
            column("day", label="Day"),
            column("_mean", hidden=True),
        ],
    )
    manifest = PDLManifest(
        title="Styled",
        snapshot_id="s" * 64,
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(page_type=PDLPageType.grid, rows=1, columns=1, blocks=[block]),
    )
    page = render_dash_page(manifest, ReportDefinition([], {}, lambda _: manifest, {}), ctx, namespace="styled")
    table = page.layout().children[2].children[0].children[0]
    payload = table.to_plotly_json()
    headers = payload["props"]["children"][0].children.children
    assert [header.children for header in headers] == ["Signal", "Ratio", "Day", "raw", "empty"]
    rows = payload["props"]["children"][1].children
    assert len(rows) == 3
    first_cells = rows[0].children
    assert [cell.children for cell in first_cells] == ["-1,234.6", "12.5%", "2024/01/01", "1.234.50", ""]
    assert first_cells[0].style["backgroundColor"] == "#fee2e2"
    assert first_cells[0].style["fontWeight"] == "bold"
    assert first_cells[0].style["borderBottom"] == "2px solid #b91c1c"
    assert first_cells[0].style["width"] == "120px"
    assert rows[2].children[0].children == "NA"
    assert table.style["border"] == "1px solid #111827"
    assert table.style["fontFamily"] == "Arial"
    assert "_mean" not in str(payload) and "_std" not in str(payload)
    assert "iframe" not in str(payload).lower()
    html = next(iter(ctx.artifact.payloads().table_htmls.values()))
    assert ">1.234.50<" in html


@pytest.mark.parametrize("na_rep, expected_nulls", [(None, ["<NA>", "None", "nan"]), ("NA", ["NA", "NA", "NA"])])
def test_native_null_values_match_html_with_and_without_na_rep(na_rep, expected_nulls, tmp_path) -> None:
    frame = pd.DataFrame({"value": pd.Series([pd.NA, None, float("nan"), ""], dtype=object)})
    style = {"format": {"na_rep": na_rep}} if na_rep is not None else None
    block = PDLTableBlock(name="values", data_ref="values.parquet", row=1, col=1)
    ctx: object = SimpleNamespace()
    if style is not None:
        store = BlobStore(f"file:{tmp_path}")
        store.put_json("reports/r/styles/values.json", style)
        block = block.model_copy(update={"style_ref": "styles/values.json"})
        ctx = SimpleNamespace(_artifact_store=store, _artifact_prefix="reports/r")
    native = _build_native_table(frame, block, "values", ctx)
    native_values = [row.children[1].children for row in native.children[1].children]
    html = render_table_html(frame, style)
    expected = [*expected_nulls, ""]
    assert native_values == expected
    assert all(f">{value}<" in html for value in expected)


def test_native_table_renders_report_url_and_header_links_without_html_parsing() -> None:
    frame = pd.DataFrame(
        {
            "label": ["US", "Europe", "Missing"],
            "report_id": ["us/inventories", None, pd.NA],
            "url": ["https://example.test/us", "https://example.test/eu", None],
        },
        index=pd.Index(["a", "b", "c"], name="Region"),
    )
    block = PDLTableBlock(
        name="linked",
        data_ref="linked.parquet",
        row=1,
        col=1,
        links=[
            link_column("label", report_id_from="report_id"),
            link_column("report_id", url_from="url"),
            link_header("label", report_id="summary/x"),
            link_index_header(url="https://example.test/all"),
        ],
    )

    table = _build_native_table(frame, block, "linked", SimpleNamespace())
    headers = table.children[0].children.children
    rows = table.children[1].children

    assert headers[0].children.__class__.__name__ == "A"
    assert headers[0].children.href == "https://example.test/all"
    assert headers[1].children.__class__.__name__ == "Link"
    assert headers[1].children.href == "/report/summary/x"
    assert rows[0].children[1].children.__class__.__name__ == "Link"
    assert rows[0].children[1].children.href == "/report/us/inventories"
    assert rows[1].children[1].children.__class__.__name__ == "str"
    assert rows[0].children[2].children.__class__.__name__ == "A"
    assert rows[0].children[2].children.href == "https://example.test/us"


def test_native_and_html_linked_unformatted_numeric_values_match() -> None:
    frame = pd.DataFrame({"value": [1.23456789], "report_id": ["detail"]})
    link = link_column("value", report_id_from="report_id")
    block = PDLTableBlock(
        name="linked",
        data_ref="linked.parquet",
        row=1,
        col=1,
        links=[link],
    )

    native = _build_native_table(frame, block, "linked", SimpleNamespace())
    native_text = native.children[1].children[0].children[1].children.children
    html = render_table_html(frame, {"links": [link]})
    html_match = re.search(r"<a\b[^>]*>([^<]*)</a>", html)

    assert html_match is not None
    assert native_text == html_match.group(1) == "1.234568"
