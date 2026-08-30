from __future__ import annotations

import io
from types import SimpleNamespace

import pandas as pd
from dash import dcc
from runbook.core.pdl.models import PDLArtifacts, PDLManifest, PDLPage, PDLPageType, PDLTableBlock
from runbook.core.storage import BlobStore
from runbook.core.table import TableLink
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash import render_dash_page
from runbook.sdk.extensions.dash.renderer import _build_native_table


def _plot_payload(title: str) -> dict[str, object]:
    return {"data": [{"type": "bar", "x": [1], "y": [2]}], "layout": {"title": {"text": title}}}


def _ctx(tmp_path, plots: dict[str, dict[str, object]] | None = None) -> SimpleNamespace:
    store = BlobStore(f"file:{tmp_path}")
    for ref, payload in (plots or {}).items():
        store.put_json(f"reports/r/{ref}", payload)
    return SimpleNamespace(_artifact_store=store, _artifact_prefix="reports/r")


def _table_frame(ctx: SimpleNamespace) -> None:
    parquet = io.BytesIO()
    pd.DataFrame({"value": [1]}).to_parquet(parquet, index=False)
    ctx._artifact_store.put("reports/r/table.parquet", parquet.getvalue())


def _manifest(*links: TableLink, plots: list[str] | None = None) -> PDLManifest:
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
        artifacts=PDLArtifacts(plots=plots),
    )


def test_native_links_use_history_safe_defaults_and_host_routes() -> None:
    frame = pd.DataFrame({"value": [1]}, index=pd.Index(["row"], name="index"))
    block = PDLTableBlock(
        name="table",
        data_ref="table.parquet",
        row=1,
        col=1,
        links=[
            TableLink(area="header", field="value", destination={"kind": "report", "value": "detail/a b"}),
            TableLink(area="index_header", destination={"kind": "plot", "value": "chart/a b"}),
        ],
    )
    table = _build_native_table(frame, block, "table", SimpleNamespace())
    assert table.children[0].children.children[1].children.href == "/report/detail/a%20b"
    assert table.children[0].children.children[0].children.href == "/plot/chart/a%20b"

    calls: list[tuple[str, str]] = []

    def resolver(kind: str, value: str) -> str | None:
        calls.append((kind, value))
        return "/host/detail" if kind == "report" else None

    resolved = _build_native_table(frame, block, "table", SimpleNamespace(), resolver)
    assert resolved.children[0].children.children[1].children.href == "/host/detail"
    assert resolved.children[0].children.children[0].children.role == "alert"
    assert calls == [("plot", "chart/a b"), ("report", "detail/a b")]


def test_default_routes_reject_dot_segments() -> None:
    frame = pd.DataFrame({"value": [1]}, index=pd.Index(["row"], name="index"))
    block = PDLTableBlock(
        name="table",
        data_ref="table.parquet",
        row=1,
        col=1,
        links=[
            TableLink(area="header", field="value", destination={"kind": "report", "value": "detail/.."}),
            TableLink(area="index_header", destination={"kind": "plot", "value": "chart/."}),
        ],
    )
    table = _build_native_table(frame, block, "table", SimpleNamespace())
    assert table.children[0].children.children[0].children.role == "alert"
    assert table.children[0].children.children[1].children.role == "alert"


def test_external_url_remains_an_anchor() -> None:
    frame = pd.DataFrame({"value": [1]})
    block = PDLTableBlock(
        name="table",
        data_ref="table.parquet",
        row=1,
        col=1,
        links=[TableLink(area="cells", field="value", destination={"kind": "url", "value": "https://example.test"})],
    )
    table = _build_native_table(frame, block, "table", SimpleNamespace())
    anchor = table.children[1].children[0].children[1].children
    assert anchor.__class__.__name__ == "A"
    assert anchor.href == "https://example.test"


def test_native_plot_pages_render_individual_and_sorted_aggregate(tmp_path) -> None:
    ctx = _ctx(
        tmp_path,
        {
            "plots/asset-z.json": _plot_payload("z"),
            "plots/asset-a.json": _plot_payload("a"),
        },
    )
    _table_frame(ctx)
    manifest = _manifest(plots=["plots/asset-z.json", "plots/asset-a.json"])
    page = render_dash_page(manifest, ReportDefinition([], {}, lambda _: manifest, {}), ctx, namespace="plots")

    individual = page.plot_layout("asset-a")
    assert individual.children[1].__class__.__name__ == "Graph"
    aggregate = page.plot_layout("asset-plots")
    assert [graph.figure["layout"]["title"]["text"] for graph in aggregate.children[1:]] == ["a", "z"]
    assert all(isinstance(graph, dcc.Graph) for graph in aggregate.children[1:])


def test_native_plot_pages_report_missing_empty_and_stale_as_alert(tmp_path) -> None:
    ctx = _ctx(tmp_path, {"plots/asset-a.json": _plot_payload("a")})
    _table_frame(ctx)
    manifest = _manifest(plots=["plots/asset-a.json", "plots/asset-stale.json"])
    page = render_dash_page(manifest, ReportDefinition([], {}, lambda _: manifest, {}), ctx, namespace="plots-errors")

    assert page.plot_layout("missing").role == "alert"
    assert page.plot_layout("other-plots").role == "alert"
    assert page.plot_layout("asset-plots").role == "alert"
    assert page.plot_layout("asset-stale").role == "alert"


def test_missing_plot_link_is_an_alert_in_the_report_table(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    _table_frame(ctx)
    link = TableLink(area="header", field="value", destination={"kind": "plot", "value": "missing"})
    manifest = _manifest(link, plots=[])
    page = render_dash_page(manifest, ReportDefinition([], {}, lambda _: manifest, {}), ctx, namespace="link-errors")
    table = page.layout().children[2].children[0].children[0]
    assert table.children[0].children.children[1].children.role == "alert"
