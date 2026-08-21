from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import pytest
from runbook.core.data import Snapshot
from runbook.core.storage import BlobStore
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import discover_report_definition
from runbook.sdk.execution import load_report_module
from runbook.sdk.live import LiveCapabilityUnavailableError
from runbook.sdk.live_sqlite import build_demo_live_provider
from runbook.sdk.preview_cli import _serve_interactive_app


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
