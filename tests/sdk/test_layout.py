from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from runbook.core.data import DatasetFile
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLSourceType, PDLStyle, PDLTextBlock
from runbook.core.table.models import TableArtifactRef
from runbook.data import open_blob_store
from runbook.data.manifests import build_manifest, publish_manifests, resolve_snapshot, write_dataframe
from runbook.sdk import ReportProfile, execute_report
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import ReportDefinition, discover_report_definition
from runbook.sdk.execution import load_report_module
from runbook.sdk.extensions.dash.renderer import render_dash_page
from runbook.sdk.html import render_html
from runbook.sdk.layout import Report, compile_layout, grid, plot, report, section, table, text
from runbook.sdk.preview_cli import compose_dash_app


def _ctx(config: dict[str, object] | None = None) -> SimpleNamespace:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(
        snapshot=SimpleNamespace(snapshot_id="snapshot", as_of=now, watermark=now),
        config=config or {},
        report_id="layout-test",
    )


def test_two_column_flow_and_handles() -> None:
    layout = Report("Oil")
    with layout.grid(columns=2) as report_grid:
        first = report_grid.text("one", name="first")
        second = report_grid.text("two")
        third = report_grid.text("three")

    manifest = compile_layout(_ctx(), layout)
    assert first.name == "first"
    assert second.name.endswith("text-002")
    assert [block.row for block in manifest.page.blocks] == [1, 1, 2]
    assert [block.col for block in manifest.page.blocks] == [1, 2, 1]
    assert third.name.endswith("text-003")


def test_three_column_and_mixed_spans() -> None:
    layout = Report("Flow")
    with layout.grid(columns=3) as report_grid:
        report_grid.text("hero", col_span=2)
        report_grid.text("side")
        report_grid.text("tall", row_span=2)
        report_grid.text("bottom", col_span=2)

    blocks = compile_layout(_ctx(), layout).page.blocks
    assert [(block.row, block.col, block.row_span, block.col_span) for block in blocks] == [
        (1, 1, 1, 2),
        (1, 3, 1, 1),
        (2, 1, 2, 1),
        (2, 2, 1, 2),
    ]


def test_invalid_spans_have_grid_context() -> None:
    layout = Report("Flow")
    with layout.grid(columns=2) as report_grid:
        with pytest.raises(ValueError, match="columns=2.*col_span=3"):
            report_grid.text("bad", col_span=3)
        with pytest.raises(ValueError, match="col_span.*>= 1"):
            report_grid.text("bad", col_span=0)
        with pytest.raises(ValueError, match="row_span.*>= 1"):
            report_grid.text("bad", row_span=0)


def test_direct_report_block_rejects_col_span() -> None:
    layout = Report("Direct")
    layout.add(text("hello", name="summary", col_span=2))

    with pytest.raises(ValueError, match="Direct block.*col_span=2.*inside a Grid"):
        compile_layout(_ctx(), layout)

    unnamed = Report("Direct")
    unnamed_block = unnamed.add(text("hello", col_span=2))
    unnamed_block.name = None
    with pytest.raises(ValueError, match="Direct block '<unnamed>'.*inside a Grid"):
        compile_layout(_ctx(), unnamed)


def test_direct_section_block_rejects_col_span() -> None:
    layout = Report("Direct")
    with layout.section("Details") as details:
        details.add(text("hello", name="summary", col_span=2))

    with pytest.raises(ValueError, match="Direct block.*col_span=2.*inside a Grid"):
        compile_layout(_ctx(), layout)


def test_direct_blocks_are_full_width_and_preserve_row_span() -> None:
    layout = Report("Direct")
    layout.add(text("hello", row_span=2))
    with layout.grid(columns=2) as report_grid:
        report_grid.text("grid")

    blocks = compile_layout(_ctx(), layout).page.blocks
    assert (blocks[0].col, blocks[0].col_span, blocks[0].row_span) == (1, 2, 2)
    assert (blocks[1].row, blocks[1].col, blocks[1].col_span) == (3, 1, 1)


def test_direct_section_block_is_full_width_and_preserves_row_span() -> None:
    layout = Report("Direct")
    with layout.section("Details") as details:
        details.add(text("hello", row_span=2))
        with details.grid(columns=2) as report_grid:
            report_grid.text("grid")

    manifest = compile_layout(_ctx(), layout)
    direct = manifest.page.blocks[1]
    assert (direct.col, direct.col_span, direct.row_span) == (1, manifest.page.columns, 2)
    assert manifest.page.columns == 2


def test_functional_collections_and_empty_sections() -> None:
    blocks = [text("a"), text("b")]
    empty_items: tuple[str, ...] = ()
    layout = report(
        "Functional",
        sections=[
            section("Filled", grid(blocks, columns=2)),
            section("Empty", grid((item for item in empty_items), columns=5)),
        ],
    )
    manifest = compile_layout(_ctx(), layout)
    assert manifest.page.columns == 2
    assert [block.text for block in manifest.page.blocks if block.type == "text" and block.text] == ["a", "b"]
    assert not any(block.title == "Empty" for block in manifest.page.blocks)


def test_tuple_and_non_empty_generator_inputs() -> None:
    tuple_grid = grid((text("tuple-a"), text("tuple-b")), columns=2)
    generator_grid = grid((text(f"generated-{index}") for index in range(3)), columns=2)
    layout = report("Collections", sections=[section("Tuple", tuple_grid), section("Generator", generator_grid)])
    blocks = compile_layout(_ctx(), layout).page.blocks
    assert [block.text for block in blocks if block.text] == [
        "tuple-a",
        "tuple-b",
        "generated-0",
        "generated-1",
        "generated-2",
    ]


def test_ordinary_function_composition_returns_reusable_section() -> None:
    def build_section() -> object:
        result = section("Reusable")
        result.add(text("from a function"))
        return result

    layout = Report("Composed")
    layout.add(build_section())
    manifest = compile_layout(_ctx(), layout)
    assert manifest.page.blocks[0].title == "Reusable"
    assert manifest.page.blocks[1].text == "from a function"


def test_multiple_grids_preserve_order_and_vertical_offsets() -> None:
    layout = Report("Multiple grids")
    with layout.section("Details") as details:
        with details.grid(columns=2) as first:
            first.text("a")
            first.text("b")
            first.text("c")
        details.heading("Second")
        with details.grid(columns=3) as second:
            second.text("d")
            second.text("e")
    blocks = compile_layout(_ctx(), layout).page.blocks
    assert [block.text for block in blocks] == ["", "a", "b", "c", "", "d", "e"]
    assert [block.row for block in blocks] == [1, 2, 2, 3, 4, 5, 5]
    assert "sections=1, grids=2, blocks=7" in repr(layout)


def test_lcm_scales_mixed_grids_and_ignores_empty_grid() -> None:
    layout = Report("Mixed")
    with layout.grid(columns=9) as empty:
        pass
    with layout.grid(columns=2) as two:
        two.text("a")
    with layout.grid(columns=3) as three:
        three.text("b")
    manifest = compile_layout(_ctx(), layout)
    assert manifest.page.columns == 6
    assert [(block.row, block.col, block.col_span) for block in manifest.page.blocks] == [(1, 1, 3), (2, 1, 2)]
    assert empty.blocks == []


def test_page_limit_boundary_and_explicit_ultrawide_override() -> None:
    at_limit = Report("At limit")
    with at_limit.grid(columns=2) as two:
        two.text("two")
    with at_limit.grid(columns=3) as three:
        three.text("three")
    assert compile_layout(_ctx(), at_limit).page.columns == 6
    assert compile_layout(_ctx({"layout": {"max_columns": 6}}), at_limit).page.columns == 6

    ultrawide = Report("Ultrawide")
    with ultrawide.grid(columns=5) as five:
        five.text("five")
    with ultrawide.grid(columns=6) as six:
        six.text("six")
    with pytest.raises(ValueError, match="columns=30.*max_columns=12"):
        compile_layout(_ctx(), ultrawide)
    manifest = compile_layout(_ctx({"layout": {"max_columns": 30}}), ultrawide)
    assert manifest.page.columns == 30

    for value in (True, 0, -1, 1.5, "30"):
        with pytest.raises(ValueError, match="layout.max_columns must be a positive integer"):
            compile_layout(_ctx({"layout": {"max_columns": value}}), at_limit)


def test_duplicate_names_and_empty_report_fail_clearly() -> None:
    layout = Report("Duplicate")
    with layout.grid(columns=1) as report_grid:
        report_grid.text("one", name="same")
        report_grid.text("two", name="same")
    with pytest.raises(ValueError, match="duplicate layout block name 'same'"):
        compile_layout(_ctx(), layout)

    with pytest.raises(ValueError, match="has no blocks"):
        compile_layout(_ctx(), Report("Empty"))


def test_direct_blocks_and_headings_are_full_width_and_ordered() -> None:
    layout = Report("Order")
    layout.heading("Summary")
    layout.add(text("intro"))
    with layout.section("Details") as details:
        details.heading("Rows")
        details.add(text("body"))
    blocks = compile_layout(_ctx(), layout).page.blocks
    assert [block.title for block in blocks] == ["Summary", None, "Details", "Rows", None]
    assert [block.row for block in blocks] == [1, 2, 3, 4, 5]
    assert all(block.col == 1 and block.col_span == 1 for block in blocks)


def test_heading_compiles_as_title_only_text_block() -> None:
    layout = Report("Heading")
    layout.heading("Summary")

    block = compile_layout(_ctx(), layout).page.blocks[0]
    assert block.type == "text"
    assert block.title == "Summary"
    assert block.text == ""


def test_static_html_accepts_compiled_layout() -> None:
    layout = Report("<HTML &>")
    layout.add(text("hello", title="Greeting"))
    manifest = compile_layout(_ctx(), layout)
    html = render_html(SimpleNamespace(), manifest, "reports/layout")
    assert "Greeting" in html
    assert "hello" in html
    assert "<title>&lt;HTML &amp;&gt;</title>" in html
    assert html.count("<h1>&lt;HTML &amp;&gt;</h1>") == 1
    assert "<h1><HTML &></h1>" not in html
    assert "<p>As of: 2026-01-01T00:00:00+00:00</p>" in html
    assert html.index("<h1>") < html.index("<p>As of:") < html.index('<main class="rb-page"')


def test_static_html_omits_heading_body_but_preserves_empty_text_body() -> None:
    layout = Report("HTML")
    layout.heading("Summary")
    layout.add(text(""))

    html = render_html(SimpleNamespace(), compile_layout(_ctx(), layout), "reports/layout")
    assert "<h2>Summary</h2>" in html
    assert html.count("<pre></pre>") == 1


def test_static_html_escapes_style_closing_sequence(tmp_path) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    store.put("reports/layout/styles/grid.css", b'.example { content: "</StYle><script>"; }')
    layout = Report("HTML")
    layout.add(text("hello"))
    manifest = compile_layout(_ctx(), layout).model_copy(
        update={
            "style": PDLStyle(
                css_ref="styles/grid.css",
                source_type=PDLSourceType.manual,
                source_key="test",
            )
        }
    )

    html = render_html(store, manifest, "reports/layout")

    assert html.count("</style>") == 1
    assert '<style>.example { content: "<\\/style><script>"; }</style>' in html


def test_large_loop_composition_is_coordinates_free() -> None:
    layout = Report("Synthetic Market")
    with layout.section("Price Markets") as prices:
        with prices.grid(columns=2) as pair_grid:
            for index in range(60):
                pair_grid.text(f"table-{index}")
                pair_grid.text(f"plot-{index}")
    with layout.section("Regional Flows") as flows:
        with flows.grid(columns=3) as plots:
            for index in range(9):
                plots.text(f"flow-{index}")
        flows.heading("Regional Detail")
        with flows.grid(columns=2) as tables:
            for index in range(9):
                tables.text(f"detail-{index}")
    manifest = compile_layout(_ctx(), layout)
    assert len(manifest.page.blocks) == 141
    assert manifest.page.columns == 6


def test_table_and_plot_helpers_keep_artifact_semantics() -> None:
    ref = TableArtifactRef(data_ref="tables/demo.parquet")
    layout = Report("Artifacts")
    with layout.grid(columns=2) as report_grid:
        report_grid.add(table(ref, title="Table"))
        report_grid.add(plot("plots/demo.json", title="Plot"))
    blocks = compile_layout(_ctx(), layout).page.blocks
    assert blocks[0].type == "table"
    assert blocks[0].data_ref == ref.data_ref
    assert blocks[1].type == "plot_ref"
    assert blocks[1].ref == "plots/demo.json"


def test_pdl_page_accepts_explicit_ultrawide_columns() -> None:
    page = PDLPage(
        page_type=PDLPageType.grid,
        rows=1,
        columns=30,
        blocks=[PDLTextBlock(name="summary", text="ok", row=1, col=1, col_span=30)],
    )
    assert page.columns == 30


def test_ultrawide_compiled_layout_reaches_dash_renderer() -> None:
    layout = Report("Dash wide")
    with layout.grid(columns=5) as five:
        five.text("five")
    with layout.grid(columns=6) as six:
        six.text("six")
    ctx = _ctx({"layout": {"max_columns": 30}})
    manifest = compile_layout(ctx, layout)
    definition = ReportDefinition([], {}, lambda _ctx: manifest, {})
    page = render_dash_page(manifest, definition, ctx, namespace="wide")
    report_grid = page.layout().children[2]
    assert report_grid.style["gridTemplateColumns"] == "repeat(30, minmax(0, 1fr))"


def test_market_dashboard_golden_executes_and_uses_renderer_extension(tmp_path, pointer_registry) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ref, digest = write_dataframe(store, "market_fixture", pd.DataFrame({"market": ["synthetic"], "value": [1.0]}))
    dataset_manifest, manifest_digest = build_manifest(
        dataset_id="market_fixture",
        watermark=now,
        published_at=now,
        files=[DatasetFile(ref=ref, sha256=digest, partition={})],
    )
    publish_manifests(
        store,
        [(dataset_manifest, manifest_digest)],
        pointer_registry=pointer_registry,
        source_id="market_golden",
        source_run_id="test",
    )
    snapshot = resolve_snapshot(store, {"market": "market_fixture"}, pointer_registry=pointer_registry)
    profile = ReportProfile(
        profile_id="market_golden",
        report_id="market_dashboard",
        datasets={"market": "market_fixture"},
    )
    result = execute_report(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version="golden",
        reports_root="reports",
        generated_at=now,
        platform_version="0.2.0",
    )
    manifest = PDLPage.model_validate(store.get_json(result.stage3_ref).get("page"))
    assert len(manifest.blocks) >= 100
    stage3 = store.get_json(result.stage3_ref)
    assert stage3["schema_version"] == "pdl-core/0.1"
    html = store.get(result.html_ref).decode()
    assert "Market Dashboard" in html and "Price Markets" in html

    source_ctx = Ctx(
        snapshot=snapshot,
        store=store,
        artifact_store=store,
        report_id="market_dashboard",
        config=profile.execution_config(),
        code_version="golden",
        context_hash=result.context_hash,
        artifact_prefix=result.prefix,
    )
    definition = discover_report_definition(load_report_module("reports/market_dashboard.py"))

    class Extension:
        def __init__(self) -> None:
            self.page_calls = 0
            self.block_calls = 0

        def wrap_page(self, content, *, manifest, namespace):
            self.page_calls += 1
            return content

        def render_control(self, control, *, component_id, options):
            return None

        def wrap_block(self, body, *, block, title, namespace):
            self.block_calls += 1
            return None

    extension = Extension()
    page = render_dash_page(
        PDLManifest.model_validate(store.get_json(result.stage3_ref)),
        definition,
        source_ctx,
        namespace="market-golden",
        renderer_extension=extension,
    )
    page.layout()
    assert extension.page_calls == 1
    assert extension.block_calls == len(manifest.blocks)


def test_vol_report_native_dash_and_html_golden(tmp_path, pointer_registry) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=7, freq="D", tz="UTC"),
            "price": [100.0, 80.0, 120.0, 60.0, 120.0, 60.0, 120.0],
        }
    )
    ref, digest = write_dataframe(store, "vol_prices", prices)
    dataset_manifest, manifest_digest = build_manifest(
        dataset_id="vol_prices",
        watermark=now,
        published_at=now,
        files=[DatasetFile(ref=ref, sha256=digest, partition={})],
    )
    publish_manifests(
        store,
        [(dataset_manifest, manifest_digest)],
        pointer_registry=pointer_registry,
        source_id="vol_report_golden",
        source_run_id="test",
    )
    snapshot = resolve_snapshot(store, {"prices": "vol_prices"}, pointer_registry=pointer_registry)
    profile = ReportProfile(
        profile_id="vol_report_golden",
        report_id="vol_report",
        datasets={"prices": "vol_prices"},
        params={"vol_window": 2},
        extensions={"modes": {"dash": {"enabled": True}}},
    )
    app, result, page = compose_dash_app(
        store=store,
        profile=profile,
        snapshot=snapshot,
        reports_root="reports",
        code_version="golden",
    )
    layout = page.layout()
    report_grid = layout.children[2]
    sections = {section.id: section for section in report_grid.children}
    returns_section = sections[page.ids.block("returns_table") + "-container"]
    returns_plot_section = sections[page.ids.block("returns_plot") + "-container"]
    vol_section = sections[page.ids.block("vol_table") + "-container"]
    vol_plot_section = sections[page.ids.block("vol_plot") + "-container"]
    assert returns_section.style == {"gridRow": "1 / span 1", "gridColumn": "1 / span 1"}
    assert returns_plot_section.style == {"gridRow": "1 / span 1", "gridColumn": "2 / span 1"}
    assert vol_section.style == {"gridRow": "2 / span 1", "gridColumn": "1 / span 1"}
    assert vol_plot_section.style == {"gridRow": "2 / span 1", "gridColumn": "2 / span 1"}
    assert returns_section.children[0].children == "Returns"
    assert vol_section.children[0].children == "Volatility"
    returns_table = returns_section.children[1]
    vol_table = vol_section.children[1]
    assert returns_table.__class__.__name__ == "Table"
    assert vol_table.__class__.__name__ == "Table"
    assert returns_plot_section.children[1].__class__.__name__ == "Graph"
    assert vol_plot_section.children[1].__class__.__name__ == "Graph"
    returns_rows = returns_table.children[1].children
    vol_rows = vol_table.children[1].children
    assert returns_rows[0].children[2].children == "-"
    assert returns_rows[1].children[2].children == "-20.00%"
    assert returns_rows[1].children[2].style["color"] == "#B00020"
    assert returns_rows[1].children[2].style["fontWeight"] == "600"
    assert vol_rows[0].children[2].children == "-"
    assert vol_rows[2].children[2].style["backgroundColor"] == "#FFF3CD"
    assert all(
        child.__class__.__name__ not in {"AgGrid", "Iframe"}
        for section in sections.values()
        for child in section.children
    )
    html = store.get(result.html_ref).decode()
    assert all(value in html for value in ("Returns", "Volatility", "-20.00%", ">-<"))
    assert "color: #B00020" in html
    assert "font-weight: 600" in html
    assert "background-color: #FFF3CD" in html
    assert "iframe" not in html.lower()
    assert html.count("https://cdn.plot.ly/plotly-") == 1
    assert app.server.test_client().get("/").status_code == 200
