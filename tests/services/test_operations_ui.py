from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import dash_mantine_components as dmc
from runbook.services.dash.catalogue import _latest_runs, _successful_runs, catalogue_layout, profile_rows, source_rows
from runbook.services.dash.dashboard import _pointer_row
from runbook.services.dash.operations import (
    dataset_ids,
    error_state,
    format_duration,
    profile_source_ids,
    relative_time,
    status_label,
)
from runbook.services.dash.profile_detail import layout as profile_detail_layout
from runbook.services.dash.run_drawer import _ROW_INPUTS, _run_id_from_rows
from runbook.services.dash.source_detail import layout as source_detail_layout
from runbook.services.dash.system import layout as system_layout


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


def test_catalogues_keep_newest_descending_run_and_success_lookup() -> None:
    stamp = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    profile = SimpleNamespace(
        config_id="pnl",
        revision=1,
        created_at=stamp,
        payload={"enabled": True, "datasets": {}},
    )
    newest = SimpleNamespace(
        kind="profile",
        target_id="pnl",
        status="failed",
        snapshot_id="new-snapshot",
        snapshot_payload={"watermark": "2026-08-24"},
        finished_at=stamp,
        requested_at=stamp,
    )
    older = SimpleNamespace(
        kind="profile",
        target_id="pnl",
        status="waiting",
        snapshot_id="old-snapshot",
        snapshot_payload={"watermark": "2026-08-23"},
        finished_at=stamp,
        requested_at=stamp,
    )
    rows = [newest, older]
    assert _latest_runs(rows, "profile")["pnl"] is newest
    successful = SimpleNamespace(**{**vars(older), "status": "success"})
    assert _successful_runs([newest, successful], "profile")["pnl"] is successful
    projected = profile_rows({"profiles": [profile], "sources": [], "runs": rows, "pointers": []})[0]
    assert projected["status"] == "failed"
    assert projected["snapshot_id"] == "new-snapshot"
    assert projected["as_of"] == "2026-08-24"


def test_dashboard_pointer_rows_and_drawer_inputs_use_run_selection() -> None:
    row = _pointer_row(
        {
            "dataset_id": "prices",
            "source_id": "market",
            "watermark": "2026-08-24",
            "published_at": "2026-08-24T12:00:00+00:00",
            "source_run_id": "source-run-1",
        }
    )
    assert row["run_id"] == "source-run-1"
    assert "run_link" not in row
    assert "runbook-ui-dashboard-pointers-grid" in _ROW_INPUTS


def test_async_pages_have_loading_surfaces_and_shared_error_alert() -> None:
    pages = (
        (catalogue_layout("profile"), "runbook-ui-profiles-catalogue-loading"),
        (catalogue_layout("source"), "runbook-ui-sources-catalogue-loading"),
        (profile_detail_layout(), "runbook-ui-profile-detail-loading"),
        (source_detail_layout(), "runbook-ui-source-detail-loading"),
        (system_layout(), "runbook-ui-system-loading"),
    )
    for page, loading_id in pages:
        assert loading_id in str(page)
    assert isinstance(error_state("database unavailable"), dmc.Alert)


def test_run_drawer_accepts_all_table_selection_shapes() -> None:
    assert _run_id_from_rows(None, [{"run_id": "run-1"}], None) == "run-1"
    assert _run_id_from_rows(None, [{"run_id": 3}]) is None
