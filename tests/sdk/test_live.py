from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
import runbook.sdk.live_report_preview as preview_module
from dash import html
from runbook.core.data import Snapshot
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.core.storage import BlobStore
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import ReportDefinition, discover_report_definition
from runbook.sdk.execution import load_report_module
from runbook.sdk.live import LiveCapabilityUnavailableError
from runbook.sdk.live_sqlite import SQLiteLiveDataResolver, build_demo_live_provider
from runbook.sdk.preview_cli import _serve_interactive_app
from runbook.sdk.profiles import ReportProfile


def _ctx(tmp_path):
    return Ctx(
        snapshot=Snapshot(
            snapshot_id="a" * 64,
            watermark=datetime(2024, 1, 1, tzinfo=timezone.utc),
            datasets={},
        ),
        store=BlobStore(f"file:{tmp_path}"),
        report_id="r",
        config={},
        code_version="c",
        context_hash="h",
        artifact_prefix="reports/r",
    )


def test_live_capability_is_explicitly_unavailable_without_provider(tmp_path) -> None:
    with pytest.raises(LiveCapabilityUnavailableError, match="capability is unavailable"):
        _ctx(tmp_path).live.sql("demo")


def test_reports_without_live_access_keep_existing_context_shape(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    assert ctx.report_id == "r"
    assert ctx.live is not None


class _PreviewRenderer:
    def wrap_page(self, content, *, manifest, namespace):
        return html.Div(content, id=f"preview-{namespace}")

    def render_control(self, control, *, component_id, options):
        return None

    def wrap_block(self, body, *, block, title, namespace):
        return None


def test_compose_report_page_applies_renderer_extension(tmp_path, monkeypatch) -> None:
    source_ctx = _ctx(tmp_path)
    manifest = PDLManifest(
        title="Composed preview",
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", text="body", row=1, col=1)],
        ),
    )
    definition = ReportDefinition([], {}, lambda _ctx: manifest, {})
    result = SimpleNamespace(prefix="reports/demo", stage3_ref="manifest.stage3.json")
    store = SimpleNamespace(get_json=lambda _ref: manifest.model_dump(mode="json"))
    monkeypatch.setattr(preview_module, "execute_report", lambda **_kwargs: result)
    monkeypatch.setattr(preview_module, "load_report_module", lambda _path: SimpleNamespace())
    monkeypatch.setattr(preview_module, "discover_report_definition", lambda _module: definition)
    monkeypatch.setattr(preview_module, "resolve_report_path", lambda *_args: "reports/demo.py")

    _, page = preview_module.compose_report_page(
        store=store,
        profile=ReportProfile(profile_id="preview", report_id="demo", datasets={"prices": "prices"}),
        snapshot=source_ctx.snapshot,
        code_version="test",
        renderer_extension=_PreviewRenderer(),
    )

    layout = page.layout()
    assert getattr(layout, "id", None) == "preview-preview"
    header = layout.children.children[0]
    assert header.children[0].children == "Composed preview"
    assert header.children[1].children == "As of: 2024-01-01T00:00:00+00:00"


def test_sqlite_provider_parameterizes_and_captures_safe_provenance() -> None:
    provider = build_demo_live_provider()
    rows = provider.sql("demo_pnl").query(
        "SELECT * FROM demo_live_pnl WHERE book = :book",
        {"book": "Alpha"},
    )
    assert rows["book"].tolist() == ["Alpha"]
    source = provider.sql("demo_pnl")
    provenance = source.last_provenance
    assert provenance is not None
    assert provenance.logical_provider == "sqlite-demo"
    assert provenance.parameter_keys == ("book",)
    assert "Alpha" not in provenance.query_hash
    assert not hasattr(provenance, "results")
    provider.close()


def test_sqlite_provider_is_thread_safe_and_close_is_idempotent() -> None:
    provider = build_demo_live_provider()
    source = provider.sql("demo_pnl")

    def query() -> list[str]:
        return source.query("SELECT book FROM demo_live_pnl ORDER BY book")["book"].tolist()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: query(), range(16)))
        list(pool.map(lambda _: provider.close(), range(8)))
    assert results == [["Alpha", "Beta", "Gamma"]] * 16
    assert provider.closed is True
    provider.close()
    with pytest.raises(LiveCapabilityUnavailableError, match="provider is closed"):
        source.query("SELECT 1")


@pytest.mark.parametrize("raises", [False, True])
def test_preview_lifecycle_closes_owned_live_provider(raises: bool) -> None:
    provider = build_demo_live_provider()

    class App:
        def run(self, **kwargs: object) -> None:
            if raises:
                raise RuntimeError("bounded preview stop")

    if raises:
        with pytest.raises(RuntimeError, match="bounded preview stop"):
            _serve_interactive_app(App(), live=provider, host="127.0.0.1", port=0)
    else:
        _serve_interactive_app(App(), live=provider, host="127.0.0.1", port=0)
    assert provider.closed is True


def test_pnl_interaction_combines_managed_and_live_rows(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    managed = pd.DataFrame(
        [
            {
                "date": "2024-01-16",
                "book": "Alpha",
                "strategy": "Macro",
                "instrument": "GBPUSD",
                "pnl": 100.0,
                "exposure": 1000.0,
                "return": 0.1,
            }
        ]
    )
    managed["date"] = pd.to_datetime(managed["date"], utc=True)
    ctx._memo["pnl"] = managed
    ctx.live = build_demo_live_provider()
    module = load_report_module("reports/pnl_explorer.py")
    definition = discover_report_definition(module)
    result = definition.interaction_fns["filter_dashboard"](ctx, {"book": ["Alpha"], "strategy": None, "date": {}})
    assert len(result["positions"]) == 2
    assert result["positions"]["pnl"].sum() == 350.0


def test_pnl_end_date_includes_intraday_managed_and_live_rows(tmp_path) -> None:
    module = load_report_module("reports/pnl_explorer.py")
    state: dict[str, object] = {"book": [], "strategy": None, "date": {"end_date": "2024-01-05"}}
    managed = pd.DataFrame(
        [
            {"date": "2024-01-05T15:30:00Z", "pnl": 10.0},
            {"date": "2024-01-06T00:00:00Z", "pnl": 20.0},
        ]
    )
    managed["date"] = pd.to_datetime(managed["date"], utc=True)
    managed_result = module._filter(managed, state)
    assert managed_result["pnl"].tolist() == [10.0]

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    pd.DataFrame(
        [
            {
                "business_date": "2024-01-05T15:30:00Z",
                "book": "Alpha",
                "strategy": "Macro",
                "instrument": "GBPUSD",
                "pnl": 10.0,
                "exposure": 100.0,
            },
            {
                "business_date": "2024-01-06T00:00:00Z",
                "book": "Alpha",
                "strategy": "Macro",
                "instrument": "GBPUSD",
                "pnl": 20.0,
                "exposure": 200.0,
            },
        ]
    ).to_sql("demo_live_pnl", connection, index=False)
    live = SQLiteLiveDataResolver.from_connection(connection)
    try:
        ctx = _ctx(tmp_path)
        ctx.live = live
        live_result = module._live_frame(ctx, state)
        assert live_result["pnl"].tolist() == [10.0]
    finally:
        live.close()
