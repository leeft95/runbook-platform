from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from dash import dcc, html
from runbook.core.pdl.models import (
    PDLArtifacts,
    PDLLinkBlock,
    PDLManifest,
    PDLPage,
    PDLPageType,
    PDLTextBlock,
)
from runbook.core.storage import BlobStore
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash.renderer import render_dash_page
from runbook.sdk.html import DEFAULT_GRID_CSS, render_html, render_html_bundle
from runbook.sdk.layout import Link, Report, compile_layout


def _ctx(tmp_path) -> SimpleNamespace:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(
        snapshot=SimpleNamespace(snapshot_id="snapshot", as_of=now, watermark=now),
        config={},
        report_id="links",
        _artifact_store=BlobStore(f"file:{tmp_path}"),
        _artifact_prefix="reports/links",
    )


def _manifest(*blocks: PDLLinkBlock, plots: list[str] | None = None) -> PDLManifest:
    return PDLManifest(
        schema_version="pdl-core/0.2",
        title="Links",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(page_type=PDLPageType.grid, rows=len(blocks), columns=1, blocks=list(blocks)),
        artifacts=PDLArtifacts(plots=plots) if plots is not None else None,
    )


class _LinkRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, Any, str]] = []

    def wrap_page(self, content: Any, *, manifest: PDLManifest, namespace: str) -> Any | None:
        return None

    def render_control(
        self,
        control: Any,
        *,
        component_id: str,
        options: list[Any] | None,
    ) -> Any | None:
        return None

    def wrap_block(
        self,
        body: Any,
        *,
        block: Any,
        title: Any | None,
        namespace: str,
    ) -> Any | None:
        self.calls.append((body, block, title, namespace))
        if isinstance(block, PDLLinkBlock):
            return html.Div(["custom", body], id="custom-link")
        return None


def test_link_authoring_compiles_for_all_targets_and_layout_placements(tmp_path) -> None:
    report = Report(
        "Links",
        children=[
            Link("Report", report="child", name="report-link"),
            Link("Plot", plot="plot-name", title="Plot title"),
        ],
    )
    section = report.section("Details")
    section.add(Link("URL", url="https://example.test", row_span=2))
    grid = report.grid(columns=2)
    grid.link("Grid report", report="grid-child", col_span=2)

    manifest = compile_layout(_ctx(tmp_path), report)

    assert manifest.schema_version == "pdl-core/0.2"
    links = [block for block in manifest.page.blocks if isinstance(block, PDLLinkBlock)]
    assert [block.destination.value for block in links] == ["child", "plot-name", "https://example.test", "grid-child"]
    assert links[1].title == "Plot title"
    assert links[-1].col_span == manifest.page.columns


def test_link_requires_exactly_one_target() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        Link("Open")
    with pytest.raises(ValueError, match="exactly one"):
        Link("Open", report="child", url="https://example.test")


def test_html_renders_safe_standalone_link_labels(tmp_path) -> None:
    manifest = PDLManifest(
        schema_version="pdl-core/0.2",
        title="Links",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=4,
            columns=1,
            blocks=[
                PDLTextBlock(name="summary", title="Summary", text="body", row=1, col=1),
                PDLLinkBlock(
                    name="report",
                    row=2,
                    col=1,
                    label="<Report & more>",
                    title="Details",
                    destination={"kind": "report", "value": "child"},
                ),
                PDLLinkBlock(
                    name="plot", row=3, col=1, label="Plot", destination={"kind": "plot", "value": "seasonal"}
                ),
                PDLLinkBlock(
                    name="url",
                    row=4,
                    col=1,
                    label="Method",
                    destination={"kind": "url", "value": "https://example.test"},
                ),
            ],
        ),
    )
    store = BlobStore(f"file:{tmp_path}")

    rendered = render_html(store, manifest, "reports/links")

    assert (
        '<section class="rb-block" style="grid-row: 1 / span 1; grid-column: 1 / span 1;"><h2>Summary</h2><pre>body</pre></section>'
        in rendered
    )
    assert (
        '<section class="rb-block" style="grid-row: 2 / span 1; grid-column: 1 / span 1;"><h2>Details</h2>' in rendered
    )
    assert 'class="rb-link-block"' not in rendered
    assert rendered.count('class="rb-block"') == 4
    assert "&lt;Report &amp; more&gt;" in rendered
    assert 'href="/report/child"' in rendered
    assert 'href="plots/seasonal.html"' in rendered
    assert 'href="https://example.test"' in rendered
    assert ".rb-link-block {" not in DEFAULT_GRID_CSS


def test_html_bundle_publishes_standalone_aggregate_plot_link(tmp_path) -> None:
    manifest = _manifest(
        PDLLinkBlock(
            name="plots", row=1, col=1, label="Open plots", destination={"kind": "plot", "value": "asset-plots"}
        )
    )
    store = BlobStore(f"file:{tmp_path}")
    payload: dict[str, object] = {"data": [], "layout": {}}

    rendered = render_html_bundle(store, manifest, "reports/links", {"asset-a": payload, "asset-b": payload})

    assert set(rendered.linked_pages) == {"asset-plots"}
    assert rendered.main.count('href="plots/asset-plots.html"') == 1


def test_dash_renders_standalone_links_using_existing_navigation(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    ctx._artifact_store.put_json("reports/links/plots/seasonal.json", {"data": []})
    manifest = _manifest(
        PDLLinkBlock(name="report", row=1, col=1, label="Report", destination={"kind": "report", "value": "child/a b"}),
        PDLLinkBlock(name="plot", row=2, col=1, label="Plot", destination={"kind": "plot", "value": "seasonal"}),
        PDLLinkBlock(
            name="url", row=3, col=1, label="URL", destination={"kind": "url", "value": "https://example.test"}
        ),
        plots=["plots/seasonal.json"],
    )
    definition = ReportDefinition([], {}, lambda _: manifest, {})

    page = render_dash_page(manifest, definition, ctx, namespace="standalone-links")
    blocks = page.layout().children[2].children
    report_link, plot_link, url_link = blocks

    assert isinstance(report_link, html.Section) and isinstance(report_link.children[0], dcc.Link)
    assert getattr(report_link.children[0], "href") == "/report/child/a%20b"
    assert isinstance(plot_link, html.Section) and isinstance(plot_link.children[0], dcc.Link)
    assert getattr(plot_link.children[0], "href") == "/plot/seasonal"
    assert isinstance(url_link, html.Section) and isinstance(url_link.children[0], html.A)
    assert getattr(url_link.children[0], "href") == "https://example.test"
    assert [block.id for block in blocks] == [
        page.ids.block("report") + "-container",
        page.ids.block("plot") + "-container",
        page.ids.block("url") + "-container",
    ]
    assert [block.style for block in blocks] == [
        {"gridRow": "1 / span 1", "gridColumn": "1 / span 1"},
        {"gridRow": "2 / span 1", "gridColumn": "1 / span 1"},
        {"gridRow": "3 / span 1", "gridColumn": "1 / span 1"},
    ]


def test_dash_mixed_blocks_keep_normal_section_and_lightweight_link_container() -> None:
    manifest = PDLManifest(
        schema_version="pdl-core/0.2",
        title="Mixed",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=2,
            columns=1,
            blocks=[
                PDLTextBlock(name="summary", title="Summary", text="body", row=1, col=1),
                PDLLinkBlock(
                    name="details",
                    title="Details",
                    label="Open details",
                    destination={"kind": "report", "value": "details"},
                    row=2,
                    col=1,
                ),
            ],
        ),
    )

    page = render_dash_page(
        manifest, ReportDefinition([], {}, lambda _: manifest, {}), SimpleNamespace(), namespace="mixed"
    )
    report_grid = page.layout().children[2]
    normal, link = report_grid.children

    assert "gridAutoRows" not in report_grid.style
    assert isinstance(normal, html.Section)
    assert normal.children[0].children == "Summary"
    assert normal.children[1].children == "body"
    assert isinstance(link, html.Section)
    assert getattr(link, "id") == page.ids.block("details") + "-container"
    assert getattr(link, "style") == {"gridRow": "2 / span 1", "gridColumn": "1 / span 1"}
    assert isinstance(link.children[0], html.H2)
    assert isinstance(link.children[1], dcc.Link)
    assert link.children[1].children == "Open details"
    assert getattr(link.children[1], "href") == "/report/details"


def test_dash_link_renderer_extension_wraps_inside_lightweight_container() -> None:
    manifest = PDLManifest(
        schema_version="pdl-core/0.2",
        title="Custom links",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[
                PDLLinkBlock(
                    name="details",
                    title="Details",
                    label="Open details",
                    destination={"kind": "report", "value": "details"},
                    row=1,
                    col=1,
                )
            ],
        ),
    )
    renderer = _LinkRenderer()

    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _: manifest, {}),
        SimpleNamespace(),
        namespace="custom-links",
        renderer_extension=renderer,
    )
    link_container = page.layout().children[2].children[0]

    assert len(renderer.calls) == 1
    body, block, title, namespace = renderer.calls[0]
    assert isinstance(body, dcc.Link)
    assert block is manifest.page.blocks[0]
    assert title.children == "Details"
    assert namespace == "custom-links"
    assert isinstance(link_container, html.Section)
    assert getattr(link_container, "style") == {"gridRow": "1 / span 1", "gridColumn": "1 / span 1"}
    assert link_container.children[0].id == "custom-link"
    assert link_container.children[0].children[1] is body


def test_dash_unresolved_standalone_plot_is_an_accessible_alert(tmp_path) -> None:
    manifest = _manifest(
        PDLLinkBlock(name="plot", row=1, col=1, label="Plot", destination={"kind": "plot", "value": "missing"}),
        plots=[],
    )
    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _: manifest, {}),
        _ctx(tmp_path),
        namespace="standalone-missing",
    )

    alert = page.layout().children[2].children[0].children[0]
    assert isinstance(alert, html.Span)
    assert getattr(alert, "role") == "alert"
