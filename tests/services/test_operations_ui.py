from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from runbook.services.dash.catalogue import profile_rows, source_rows
from runbook.services.dash.operations import (
    dataset_ids,
    format_duration,
    profile_source_ids,
    relative_time,
    status_label,
)
from runbook.services.dash.run_drawer import _run_id_from_rows


def test_operations_formatting_and_dependency_derivation() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    assert relative_time(datetime(2026, 8, 24, 11, 59, tzinfo=timezone.utc), now=now) == "1m ago"
    assert format_duration(datetime(2026, 8, 24, 11, 59, tzinfo=timezone.utc), now, now=now) == "1m 0s"
    assert status_label("future_status") == "Future Status"
    profile = {"datasets": {"prices": "market-prices"}}
    source = SimpleNamespace(config_id="market", payload={"datasets": {"prices": {"dataset_id": "market-prices"}}})
    assert dataset_ids(source.payload) == {"market-prices"}
    assert profile_source_ids(profile, [source]) == ["market"]


def test_catalogues_project_operational_state_and_reverse_dependencies() -> None:
    stamp = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    source = SimpleNamespace(
        config_id="market",
        revision=2,
        created_at=stamp,
        payload={"enabled": True, "adapter": "http", "datasets": {"prices": {"dataset_id": "market-prices"}}},
    )
    profile = SimpleNamespace(
        config_id="pnl",
        revision=1,
        created_at=stamp,
        payload={"enabled": True, "title": "PnL", "datasets": {"prices": "market-prices"}},
    )
    run = SimpleNamespace(
        kind="source",
        target_id="market",
        status="success",
        finished_at=stamp,
        requested_at=stamp,
        started_at=stamp,
        snapshot_id=None,
        snapshot_payload=None,
    )
    data = {"profiles": [profile], "sources": [source], "runs": [run], "pointers": []}
    assert profile_rows(data)[0]["source_count"] == 1
    assert source_rows(data)[0]["used_by"] == 1


def test_run_drawer_accepts_all_table_selection_shapes() -> None:
    assert _run_id_from_rows(None, [{"run_id": "run-1"}], None) == "run-1"
    assert _run_id_from_rows(None, [{"run_id": 3}]) is None
