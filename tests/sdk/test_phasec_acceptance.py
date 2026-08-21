from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
from runbook.core.pdl.models import (
    PDLManifest,
    PDLPage,
    PDLPageType,
    PDLPlotRefBlock,
    PDLTableBlock,
    PDLTextBlock,
)
from runbook.core.storage import BlobStore
from runbook.sdk.extensions.dash import build_ag_grid_column_defs, dashboard
from runbook.sdk.extensions.dash.tables import ag_grid_default_col_def
from runbook.sdk.html import render_html


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


def test_services_and_reusable_package_boundaries_remain_one_way() -> None:
    services = _imports(Path("packages/runbook/runbook-services/src/runbook/services"))
    assert not any(name.startswith(("runbook.data", "runbook.sdk", "runbook.worker")) for name in services)
    for package in ("runbook-core", "runbook-data", "runbook-sdk"):
        imports = _imports(Path("packages/runbook") / package / "src")
        assert not any(name.startswith("runbook.services") for name in imports)
