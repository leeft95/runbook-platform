from __future__ import annotations

import ast
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
from runbook.core.data import DatasetFile
from runbook.core.pdl.models import (
    PDLManifest,
    PDLPage,
    PDLPageType,
    PDLPlotRefBlock,
    PDLTableBlock,
    PDLTextBlock,
)
from runbook.core.storage import BlobStore
from runbook.data.manifests import build_manifest, publish_manifests, resolve_snapshot, write_dataframe
from runbook.sdk import ReportProfile, column, execute_report, number
from runbook.sdk.extensions.dash import build_ag_grid_column_defs, dashboard
from runbook.sdk.extensions.dash.tables import ag_grid_default_col_def
from runbook.sdk.html import render_html
from runbook.sdk.preview_cli import compose_dash_app


def _imports(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def _manifest() -> PDLManifest:
    return PDLManifest(
        title="Acceptance",
        snapshot_id="snapshot",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=3,
            columns=1,
            blocks=[
                PDLTextBlock(name="summary", text="ready", row=1, col=1),
                PDLPlotRefBlock(name="chart", ref="plot.json", row=2, col=1),
                PDLTableBlock(name="table", data_ref="table.parquet", row=3, col=1),
            ],
        ),
        extensions={"dash": dashboard().model_dump(mode="json")},
    )


def test_pdl_core_boundary_excludes_renderer_and_host_configuration() -> None:
    root = Path("packages/runbook/runbook-core/src/runbook/core/pdl")
    imports = _imports(root)
    assert not any(name.startswith(("dash", "dash_ag_grid", "runbook.services")) for name in imports)
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.glob("*.py"))
    source += Path(root / "spec.json").read_text(encoding="utf-8").lower()
    for forbidden in ("columnDefs", "enableRowGroup", "enablePivot", "route", "navigation"):
        assert forbidden.lower() not in source


def test_report_sources_use_declarative_interactions_without_native_dash_callbacks() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("reports").glob("*.py"))
    lines = {line.strip() for line in source.splitlines()}
    assert not any(line.startswith("from dash ") or line == "import dash" for line in lines)
    for forbidden in ("app.callback", "dash.Input", "dash.Output", "callback_context"):
        assert forbidden not in source
    assert "@report.interaction" in source


def test_canonical_pdl_json_has_no_runtime_or_navigation_objects() -> None:
    payload = _manifest().model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) == payload
    for forbidden in ("dash_app", "columnDefs", "route", "navigation", "credentials"):
        assert forbidden not in encoded


def test_html_fallback_renders_complete_content_with_unknown_extension(tmp_path) -> None:
    store = BlobStore(f"file:{tmp_path}")
    frame = pd.DataFrame({"book": ["Alpha"], "pnl": [12.5]})
    parquet = io.BytesIO()
    frame.to_parquet(parquet, index=False)
    store.put("reports/acceptance/table.parquet", parquet.getvalue())
    store.put_json(
        "reports/acceptance/plot.json",
        {"data": [{"x": ["Alpha"], "y": [12.5], "type": "bar"}], "layout": {"title": "PnL"}},
    )
    html = render_html(store, _manifest(), "reports/acceptance")
    assert "ready" in html and "Alpha" in html and "PnL" in html
    assert "<!doctype html>" in html


def test_ag_grid_analytical_features_are_renderer_defaults_without_callbacks() -> None:
    definitions = build_ag_grid_column_defs(pa.schema([("book", pa.string()), ("pnl", pa.float64())]))
    by_field = {item["field"]: item for item in definitions}
    assert by_field["book"]["enableRowGroup"] and by_field["book"]["enablePivot"]
    assert by_field["pnl"]["enableValue"] and by_field["pnl"]["aggFunc"] == "sum"
    assert "callback" not in json.dumps(definitions).lower()
    assert ag_grid_default_col_def()["sortable"] is True


def test_ag_grid_formatter_code_is_renderer_generated_only() -> None:
    definitions = build_ag_grid_column_defs(
        pa.schema([("amount", pa.float64())]),
        [
            column(
                "amount",
                role="measure",
                format=number(decimals=2),
            )
        ],
    )
    formatter = definitions[0]["valueFormatter"]
    assert "toLocaleString" in formatter
    assert "javascript:" not in formatter.lower()
    assert "user" not in formatter.lower()
    assert all(key not in definitions[0] for key in ("cellRenderer", "valueGetter", "function"))


def test_pnl_artifact_manifest_drives_complete_static_html_and_dash_callback(tmp_path, pointer_registry) -> None:
    store = BlobStore(f"file:{tmp_path}")
    now = datetime(2024, 1, 20, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        [
            {
                "date": "2024-01-17",
                "book": "Alpha",
                "strategy": "Macro",
                "instrument": "GBPUSD",
                "pnl": 100.0,
                "exposure": 1000.0,
                "return": 0.1,
            },
            {
                "date": "2024-01-18",
                "book": "Beta",
                "strategy": "RV",
                "instrument": "EURGBP",
                "pnl": -20.0,
                "exposure": 750.0,
                "return": -0.02,
            },
        ]
    )
    ref, digest = write_dataframe(store, "demo_pnl_explorer", frame)
    dataset_manifest, manifest_digest = build_manifest(
        dataset_id="demo_pnl_explorer",
        watermark=now,
        published_at=now,
        files=[DatasetFile(ref=ref, sha256=digest, partition={})],
    )
    publish_manifests(
        store,
        [(dataset_manifest, manifest_digest)],
        pointer_registry=pointer_registry,
        source_id="pnl_acceptance",
        source_run_id="test",
    )
    snapshot = resolve_snapshot(store, {"pnl": "demo_pnl_explorer"}, pointer_registry=pointer_registry)
    profile = ReportProfile(
        profile_id="pnl_acceptance",
        report_id="pnl_explorer",
        datasets={"pnl": "demo_pnl_explorer"},
        extensions={"modes": {"dash": {"enabled": True}}},
    )
    result = execute_report(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version="acceptance",
        reports_root="reports",
        generated_at=now,
        platform_version="0.2.0",
    )
    html = store.get(result.html_ref).decode()
    assert all(value in html for value in ("PnL Explorer", "Total PnL", "PnL through time", "Alpha", "GBPUSD"))

    from runbook.sdk.live_sqlite import build_demo_live_provider

    live = build_demo_live_provider()
    try:
        app, _, page = compose_dash_app(
            store=store,
            profile=profile,
            snapshot=snapshot,
            reports_root="reports",
            code_version="acceptance",
            live=live,
        )
        assert page.namespace == "pnl_acceptance"
        page_payload = page.layout().to_plotly_json()
        assert "pdl-pnl_acceptance-block-summary" in str(page_payload)
        assert "pdl-pnl_acceptance-block-pnl_chart" in str(page_payload)
        assert "pdl-pnl_acceptance-block-positions" in str(page_payload)
        assert app.server.test_client().get("/").status_code == 200
        callback_key = next(key for key in app.callback_map if "pdl-pnl_acceptance-block-summary" in key)
        response = app.server.test_client().post(
            "/_dash-update-component",
            json={
                "output": callback_key,
                "outputs": [
                    {"id": "pdl-pnl_acceptance-block-summary", "property": "children"},
                    {"id": "pdl-pnl_acceptance-block-pnl_chart", "property": "figure"},
                    {"id": "pdl-pnl_acceptance-block-positions", "property": "rowData"},
                ],
                "inputs": [
                    {"id": "pdl-pnl_acceptance-control-book", "property": "value", "value": []},
                    {"id": "pdl-pnl_acceptance-control-strategy", "property": "value", "value": None},
                    {"id": "pdl-pnl_acceptance-control-date", "property": "start_date", "value": None},
                    {"id": "pdl-pnl_acceptance-control-date", "property": "end_date", "value": None},
                ],
                "changedPropIds": ["pdl-pnl_acceptance-control-book.value"],
                "state": [],
            },
        )
        assert response.status_code == 200
        assert b"Total PnL" in response.data
        assert b"GBPUSD" in response.data
    finally:
        live.close()


def test_services_and_reusable_package_boundaries_remain_one_way() -> None:
    services = _imports(Path("packages/runbook/runbook-services/src/runbook/services"))
    assert not any(name.startswith(("runbook.data", "runbook.sdk", "runbook.worker")) for name in services)
    for package in ("runbook-core", "runbook-data", "runbook-sdk"):
        imports = _imports(Path("packages/runbook") / package / "src")
        assert not any(name.startswith("runbook.services") for name in imports)
