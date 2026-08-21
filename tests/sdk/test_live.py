from __future__ import annotations

from datetime import datetime, timezone

import pytest
from runbook.core.data import Snapshot
from runbook.core.storage import BlobStore
from runbook.sdk.context import Ctx
from runbook.sdk.live import LiveCapabilityUnavailableError
from runbook.sdk.live_sqlite import build_demo_live_provider


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
