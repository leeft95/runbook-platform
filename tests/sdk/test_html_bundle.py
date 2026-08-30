from __future__ import annotations

import io

import pandas as pd
import pytest
from plotly.offline import get_plotlyjs_version
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTableBlock
from runbook.core.storage import BlobStore
from runbook.core.table import TableLink, TableStylePlan, render_table_html
from runbook.sdk.html import render_html, render_html_bundle

PLOTLY_CDN_URL = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"


def _plot_payload(title: str) -> dict[str, object]:
    return {"data": [{"x": [1], "y": [2], "type": "bar"}], "layout": {"title": {"text": title}}}


def _manifest(*links: TableLink) -> PDLManifest:
    return PDLManifest(
        schema_version="pdl-core/0.2" if links else "pdl-core/0.1",
        title="Report",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTableBlock(name="table", data_ref="table.parquet", row=1, col=1, links=list(links) or None)],
        ),
    )


def _store(tmp_path, manifest: PDLManifest) -> BlobStore:
    store = BlobStore(f"file:{tmp_path}")
    frame = pd.DataFrame({"value": [1]})
    parquet = io.BytesIO()
    frame.to_parquet(parquet, index=False)
    store.put("reports/report/table.parquet", parquet.getvalue())
    if manifest.page.blocks[0].type == "table" and manifest.page.blocks[0].links:
        html = render_table_html(frame, TableStylePlan(links=manifest.page.blocks[0].links))
        store.put("reports/report/table.html", html.encode())
        manifest.page.blocks[0].html_ref = "table.html"
    return store


def _two_aggregate_manifest() -> PDLManifest:
    return PDLManifest(
        schema_version="pdl-core/0.2",
        title="Report",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=2,
            blocks=[
                PDLTableBlock(
                    name="asset-table",
                    data_ref="asset.parquet",
                    html_ref="asset.html",
                    row=1,
                    col=1,
                    links=[TableLink(area="index_header", destination={"kind": "plot", "value": "asset-plots"})],
                ),
                PDLTableBlock(
                    name="flow-table",
                    data_ref="flow.parquet",
                    html_ref="flow.html",
                    row=1,
                    col=2,
                    links=[TableLink(area="index_header", destination={"kind": "plot", "value": "flow-plots"})],
                ),
            ],
        ),
    )


def test_no_link_bundle_main_matches_existing_renderer(tmp_path) -> None:
    manifest = _manifest()
    store = _store(tmp_path, manifest)

    rendered = render_html_bundle(store, manifest, "reports/report", {})

    assert rendered.main == render_html(store, manifest, "reports/report")
    assert rendered.linked_pages == {}


def test_individual_page_and_main_href_use_semantic_name(tmp_path) -> None:
    link = TableLink(area="header", field="value", destination={"kind": "plot", "value": "asset-value-line"})
    manifest = _manifest(link)
    store = _store(tmp_path, manifest)

    rendered = render_html_bundle(
        store,
        manifest,
        "reports/report",
        {"plots/asset-value-line.json": _plot_payload("individual")},
    )

    assert set(rendered.linked_pages) == {"asset-value-line"}
    assert 'href="plots/asset-value-line.html"' in rendered.main
    assert "<h1>asset-value-line</h1>" in rendered.linked_pages["asset-value-line"]
    assert rendered.linked_pages["asset-value-line"].count(PLOTLY_CDN_URL) == 1


def test_aggregate_pages_are_sorted_and_include_only_namespace_members(tmp_path) -> None:
    link = TableLink(area="index_header", destination={"kind": "plot", "value": "asset-plots"})
    manifest = _manifest(link)
    store = _store(tmp_path, manifest)
    payloads = {
        "plots/asset-z-line.json": _plot_payload("z-member"),
        "plots/asset-a-line.json": _plot_payload("a-member"),
        "plots/asset-plots.json": _plot_payload("aggregate-key"),
        "plots/assets-a-line.json": _plot_payload("other-namespace"),
    }

    rendered = render_html_bundle(store, manifest, "reports/report", payloads)
    page = rendered.linked_pages["asset-plots"]

    assert set(rendered.linked_pages) == {"asset-plots"}
    assert page.index("a-member") < page.index("z-member")
    assert "aggregate-key" not in page
    assert "other-namespace" not in page
    assert page.count(PLOTLY_CDN_URL) == 1


def test_two_aggregate_pages_keep_registered_namespaces_separate(tmp_path) -> None:
    manifest = _two_aggregate_manifest()
    store = BlobStore(f"file:{tmp_path}")
    store.put("reports/report/asset.html", b"<table></table>")
    store.put("reports/report/flow.html", b"<table></table>")
    payloads = {
        "plots/asset-a-line.json": _plot_payload("asset-member"),
        "plots/flow-a-line.json": _plot_payload("flow-member"),
    }

    rendered = render_html_bundle(store, manifest, "reports/report", payloads)

    assert set(rendered.linked_pages) == {"asset-plots", "flow-plots"}
    assert "asset-member" in rendered.linked_pages["asset-plots"]
    assert "flow-member" not in rendered.linked_pages["asset-plots"]
    assert "flow-member" in rendered.linked_pages["flow-plots"]
    assert "asset-member" not in rendered.linked_pages["flow-plots"]
    assert all(page.count(PLOTLY_CDN_URL) == 1 for page in rendered.linked_pages.values())


def test_unlinked_plots_are_not_published_and_missing_destinations_fail(tmp_path) -> None:
    store = _store(tmp_path, _manifest())
    rendered = render_html_bundle(
        store,
        _manifest(),
        "reports/report",
        {"plots/unlinked.json": _plot_payload("unlinked")},
    )
    assert rendered.linked_pages == {}

    manifest = _manifest(TableLink(area="header", field="value", destination={"kind": "plot", "value": "missing"}))
    store = _store(tmp_path / "missing", manifest)
    with pytest.raises(ValueError, match="missing from registered payloads"):
        render_html_bundle(store, manifest, "reports/report", {})


def test_missing_aggregate_group_fails(tmp_path) -> None:
    manifest = _manifest(TableLink(area="index_header", destination={"kind": "plot", "value": "asset-plots"}))
    store = _store(tmp_path, manifest)

    with pytest.raises(ValueError, match="no matching registered members"):
        render_html_bundle(store, manifest, "reports/report", {"plots/other-line.json": _plot_payload("other")})
