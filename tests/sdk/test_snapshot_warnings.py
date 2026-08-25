from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
from runbook.core.data import DatasetFile
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.data import open_blob_store
from runbook.data.manifests import build_manifest, publish_manifests, resolve_snapshot, write_dataframe
from runbook.sdk import ReportProfile, execute_report
from runbook.sdk import execution as execution_module
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash import render_dash_page


def test_snapshot_warnings_override_report_manifest_and_escape_html(tmp_path, pointer_registry, monkeypatch) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data_ref, data_digest = write_dataframe(store, "prices", pd.DataFrame({"price": [100.0, 101.0, 102.0]}))
    manifest, manifest_digest = build_manifest(
        dataset_id="prices",
        watermark=stamp,
        published_at=stamp,
        files=[DatasetFile(ref=data_ref, sha256=data_digest)],
    )
    publish_manifests(
        store,
        [(manifest, manifest_digest)],
        pointer_registry=pointer_registry,
        source_id="prices-source",
        source_run_id="source-0",
    )
    snapshot = resolve_snapshot(
        store,
        {"prices": "prices"},
        pointer_registry=pointer_registry,
        warnings=["immutable manual barrier bypass"],
    )

    def authored_page(_ctx):
        return PDLManifest(
            title="Authored warning",
            snapshot_id="authored",
            as_of=stamp.isoformat(),
            page=PDLPage(
                page_type=PDLPageType.grid,
                rows=1,
                columns=1,
                blocks=[PDLTextBlock(name="summary", text="body", row=1, col=1)],
            ),
            warnings=("report-authored warning",),
        )

    monkeypatch.setattr(
        execution_module,
        "discover_report_definition",
        lambda _module: ReportDefinition(["prices"], {}, authored_page),
    )
    snapshot = snapshot.model_copy(update={"warnings": ("<script>alert('x')</script>",)})
    result = execute_report(
        store=store,
        profile=ReportProfile(
            profile_id="warning-profile",
            report_id="vol_report",
            datasets={"prices": "prices"},
            params={"vol_window": 2},
        ),
        snapshot=snapshot,
        code_version="test",
        reports_root="reports",
        generated_at=stamp,
        platform_version="0.0.1",
    )
    assert store.get_json(result.stage3_ref)["warnings"] == ["<script>alert('x')</script>"]
    assert store.get_json(result.stage4_ref)["warnings"] == ["<script>alert('x')</script>"]
    html = store.get(result.html_ref)
    assert b"report-authored warning" not in html
    assert b"&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in html
    assert b"<script>alert('x')</script>" not in html
    assert store.get(result.html_ref).index(b"rb-warnings") < store.get(result.html_ref).index(b"rb-page")


def test_dash_snapshot_warnings_are_outside_grid_without_changing_block_ids() -> None:
    manifest = PDLManifest(
        title="Dash warning",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", text="body", row=1, col=1)],
        ),
        warnings=("manual barrier bypassed",),
    )
    definition = ReportDefinition([], {}, lambda _ctx: manifest)
    page = render_dash_page(manifest, definition, SimpleNamespace(), namespace="warning-page")
    layout = page.layout()
    warning, grid = layout.children[1], layout.children[2]
    assert warning.role == "alert"
    assert warning not in grid.children
    block = grid.children[0]
    assert block.id == "pdl-warning-page-block-summary-container"
    assert block.style == {"gridRow": "1 / span 1", "gridColumn": "1 / span 1"}
    assert block.children[0].id == "pdl-warning-page-block-summary"
