from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dash import Dash, Input, Output, dcc, html
from runbook.core.data import DatasetFile
from runbook.core.keying import build_context_hash
from runbook.core.pdl.models import PDLManifest
from runbook.data import open_blob_store
from runbook.data.manifests import build_manifest, publish_manifests, resolve_snapshot, write_dataframe
from runbook.sdk import ReportProfile, execute_report
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import discover_report_definition
from runbook.sdk.execution import load_report_module
from runbook.sdk.extensions.dash import render_dash_page


def _run(tmp_path, pointer_registry):
    store = open_blob_store(f"file:{tmp_path}")
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="D", tz="UTC"),
            "close": [100.0 + index * 0.5 for index in range(20)],
        }
    )
    ref, digest = write_dataframe(store, "linked_prices", frame)
    manifest, manifest_digest = build_manifest(
        dataset_id="linked_prices",
        watermark=now,
        published_at=now,
        files=[DatasetFile(ref=ref, sha256=digest, partition={})],
    )
    publish_manifests(
        store,
        [(manifest, manifest_digest)],
        pointer_registry=pointer_registry,
        source_id="linked_prices_source",
        source_run_id="golden",
    )
    snapshot = resolve_snapshot(store, {"prices": "linked_prices"}, pointer_registry=pointer_registry)
    profile = ReportProfile(
        profile_id="linked_table_golden",
        report_id="linked_table_report",
        datasets={"prices": "linked_prices"},
    )
    result = execute_report(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version="golden",
        reports_root=Path("reports"),
        generated_at=now,
        platform_version="0.3.2",
    )
    return store, snapshot, profile, result


def test_linked_table_golden_publishes_semantic_links_and_plot_pages(tmp_path, pointer_registry) -> None:
    store, _, _, result = _run(tmp_path, pointer_registry)
    manifest = PDLManifest.model_validate(store.get_json(result.stage4_ref))
    assert manifest.schema_version == "pdl-core/0.2"
    assert set(manifest.artifacts.plots) == {
        "plots/asset-price-line.json",
        "plots/asset-volume-line.json",
        "plots/price-overview.json",
    }

    html_output = store.get(result.html_ref).decode()
    assert 'href="/report/price-detail/00"' in html_output
    assert 'href="https://example.com/prices/00"' in html_output
    assert 'href="plots/asset-price-line.html"' in html_output
    assert 'href="plots/asset-volume-line.html"' in html_output
    assert 'href="plots/asset-plots.html"' in html_output
    assert "<table" in html_output
    assert "iframe" not in html_output.lower()
    assert store.exists(f"{result.prefix}/plots/asset-price-line.html")
    assert store.exists(f"{result.prefix}/plots/asset-volume-line.html")
    aggregate = store.get(f"{result.prefix}/plots/asset-plots.html").decode()
    assert aggregate.index('"name":"price"') < aggregate.index('"name":"volume"')


def test_linked_table_golden_uses_host_owned_native_dash_routes(tmp_path, pointer_registry) -> None:
    store, snapshot, profile, result = _run(tmp_path, pointer_registry)
    module = load_report_module(Path("reports/linked_table_report.py"))
    definition = discover_report_definition(module)
    config = profile.execution_config()
    ctx = Ctx(
        snapshot=snapshot,
        store=store,
        artifact_store=store,
        report_id=profile.report_id,
        config=config,
        code_version="golden",
        context_hash=build_context_hash(config),
        artifact_prefix=result.prefix,
    )
    for name, function in definition.calc_fns.items():
        ctx.register_calc(name, function)
    manifest = PDLManifest.model_validate(store.get_json(result.stage4_ref))

    def route(kind: str, value: str) -> str:
        return f"/host/{kind}/{value}"

    page = render_dash_page(manifest, definition, ctx, namespace="linked-golden", route_resolver=route)
    tree = str(page.layout())
    assert "/host/report/price-detail/00" in tree
    assert "/host/plot/asset-price-line" in tree
    assert "/host/plot/asset-plots" in tree
    assert "https://example.com/prices/00" in tree
    assert "AgGrid" not in tree

    app = Dash(__name__ + "_host", use_pages=False)
    app.layout = html.Div([dcc.Location(id="path"), html.Div(id="content")])

    @app.callback(Output("content", "children"), Input("path", "pathname"))
    def host_route(pathname: str | None):
        if pathname == "/host/plot/asset-plots":
            return page.plot_layout("asset-plots")
        return page.layout()

    client = app.server.test_client()
    callback = "content.children"
    response = client.post(
        "/_dash-update-component",
        json={
            "output": callback,
            "outputs": {"id": "content", "property": "children"},
            "inputs": [{"id": "path", "property": "pathname", "value": "/host/plot/asset-plots"}],
            "changedPropIds": ["path.pathname"],
            "state": [],
        },
    )
    assert response.status_code == 200
    assert b"asset-plots" in response.data
    assert page.plot_layout("asset-price-line").children[1].__class__.__name__ == "Graph"


def test_existing_pnl_report_is_the_explicit_ag_grid_fixture() -> None:
    source = Path("reports/pnl_explorer.py").read_text(encoding="utf-8")
    assert "dashboard(" in source
    assert 'outputs=["summary", "pnl_chart", "positions"]' in source
