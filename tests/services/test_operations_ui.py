from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import dash
import dash_mantine_components as dmc
from fastapi import FastAPI
from runbook.services.dash import run_drawer
from runbook.services.dash.catalogue import _latest_runs, _successful_runs, catalogue_layout, profile_rows, source_rows
from runbook.services.dash.operations import (
    dataset_ids,
    error_state,
    format_duration,
    profile_source_ids,
    relative_time,
    status_label,
)
from runbook.services.dash.profile_detail import layout as profile_detail_layout
from runbook.services.dash.run_drawer import (
    _ROW_INPUTS,
    _details,
    _historical_failure_reason,
    _run_id_for_trigger,
    _run_id_from_click,
)
from runbook.services.dash.source_detail import layout as source_detail_layout
from runbook.services.dash.system import layout as system_layout
from runbook.services.routers.ui import mount_ui


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


def test_source_historical_inputs_keep_native_date_and_value_semantics() -> None:
    inputs: dict[str, dmc.TextInput] = {}
    captions: list[str] = []

    def collect(node: object) -> None:
        if isinstance(node, dmc.TextInput) and node.id in {
            "runbook-ui-source-detail-historical-start-date",
            "runbook-ui-source-detail-historical-end-date",
        }:
            inputs[node.id] = node
        if isinstance(node, dmc.Text) and isinstance(node.children, str):
            captions.append(node.children)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                collect(child)
        elif children is not None:
            collect(children)

    collect(source_detail_layout())
    assert set(inputs) == {
        "runbook-ui-source-detail-historical-start-date",
        "runbook-ui-source-detail-historical-end-date",
    }
    assert all(input_.to_plotly_json()["props"]["inputProps"] == {"type": "date"} for input_ in inputs.values())
    assert all(input_.to_plotly_json()["props"]["required"] is True for input_ in inputs.values())
    assert {input_.to_plotly_json()["props"]["label"] for input_ in inputs.values()} == {
        "Start date (inclusive)",
        "End date (inclusive)",
    }
    assert "Start date (inclusive)" not in captions
    assert "End date (inclusive)" not in captions


def test_run_drawer_does_not_reopen_stale_selection_on_navigation() -> None:
    events: tuple[dict[str, object] | None, ...] = (None,) * len(_ROW_INPUTS)

    assert (
        _run_id_for_trigger(
            "runbook-ui-profile-detail-runs-grid",
            events,
            "stale-run",
        )
        is None
    )

    assert (
        _run_id_for_trigger(
            "runbook-ui-dashboard-active-grid",
            events,
            "stale-run",
        )
        is None
    )

    assert (
        _run_id_for_trigger(
            "runbook-ui-location",
            events,
            "stale-run",
        )
        is None
    )

    assert (
        _run_id_for_trigger(
            f"{run_drawer.PREFIX}-log-refresh",
            events,
            "stored-run",
        )
        == "stored-run"
    )

    assert (
        _run_id_for_trigger(
            f"{run_drawer.PREFIX}-cancel",
            events,
            "stored-run",
        )
        == "stored-run"
    )


def test_run_drawer_accepts_all_table_click_shapes() -> None:
    assert _run_id_from_click({"rowId": "run-1"}) == "run-1"
    assert _run_id_from_click({"data": {"run_id": 3}}) is None
    assert _run_id_from_click(None) is None
    assert _run_id_from_click({}) is None


def test_run_drawer_page_inputs_are_optional() -> None:
    app = dash.Dash(__name__, use_pages=False)
    run_drawer.register(app, None, "")

    callback = next(
        callback for output, callback in app.callback_map.items() if output.startswith(f"..{run_drawer.PREFIX}.opened")
    )

    click_inputs = callback["inputs"][: len(_ROW_INPUTS)]

    assert [item["id"] for item in click_inputs] == list(_ROW_INPUTS)
    assert all(item["property"] == "cellClicked" for item in click_inputs)
    assert all(item["allow_optional"] is True for item in click_inputs)

    assert _run_id_from_click({"rowId": "profile-run"}) == "profile-run"


def test_run_drawer_preserves_selected_run_when_click_has_no_run_id() -> None:
    events: tuple[dict[str, object] | None, ...] = (
        {},
        None,
        None,
        None,
        None,
        None,
    )

    assert (
        _run_id_for_trigger(
            _ROW_INPUTS[0],
            events,
            "existing-run",
        )
        is None
    )


def test_run_id_from_click() -> None:
    assert _run_id_from_click({"rowId": "run-1"}) == "run-1"
    assert _run_id_from_click({"rowId": 3}) is None
    assert _run_id_from_click(None) is None


def test_run_drawer_uses_stored_run_for_drawer_actions() -> None:
    events = (None,) * len(_ROW_INPUTS)

    assert (
        _run_id_for_trigger(
            f"{run_drawer.PREFIX}-log-refresh",
            events,
            "existing-run",
        )
        == "existing-run"
    )

    assert (
        _run_id_for_trigger(
            f"{run_drawer.PREFIX}-cancel",
            events,
            "existing-run",
        )
        == "existing-run"
    )


def test_run_drawer_uses_the_grid_that_triggered_click() -> None:
    events: list[dict[str, object] | None] = [None] * len(_ROW_INPUTS)

    events[_ROW_INPUTS.index("runbook-ui-dashboard-attention-grid")] = {
        "rowId": "attention-run",
        "colId": "status",
        "value": "failed",
    }

    events[_ROW_INPUTS.index("runbook-ui-dashboard-active-grid")] = {
        "rowId": "active-run",
        "colId": "status",
        "value": "running",
    }

    events[_ROW_INPUTS.index("runbook-ui-runs-grid")] = {
        "rowId": "other-run",
        "colId": "status",
        "value": "success",
    }

    assert (
        run_drawer._run_id_for_trigger(
            "runbook-ui-dashboard-attention-grid",
            tuple(events),
            "stale-run",
        )
        == "attention-run"
    )

    assert (
        run_drawer._run_id_for_trigger(
            "runbook-ui-dashboard-active-grid",
            tuple(events),
            "stale-run",
        )
        == "active-run"
    )

    assert (
        run_drawer._run_id_for_trigger(
            "runbook-ui-runs-grid",
            tuple(events),
            "stale-run",
        )
        == "other-run"
    )


def test_historical_run_drawer_renders_summary_inputs_outputs_and_complete_copy_refs() -> None:
    stamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    first_ref = "curated/historical-prices/manifests/sha256=0123456789abcdef0123456789abcdef.json"
    second_ref = "curated/historical-volumes/manifests/sha256=fedcba9876543210fedcba9876543210.json"
    first_wrong_ref = "curated/wrong-prices/manifests/sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
    second_wrong_ref = "curated/wrong-volumes/manifests/sha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.json"
    row = SimpleNamespace(
        run_id="historical-run",
        kind="source",
        target_id="prices",
        mode="historical",
        start_date="2026-01-01",
        end_date="2026-03-31",
        trigger="manual",
        slot=stamp,
        requested_at=stamp,
        started_at=stamp,
        finished_at=stamp,
        worker_id="local:1",
        cancel_requested_at=None,
        config_revision=18,
        config_hash="config-hash",
        snapshot_id=None,
        context_hash=None,
        code_version=None,
        artifact_id=None,
        reason=None,
        status="success",
        result={
            "status": "success",
            "datasets": {"historical-prices": first_ref, "historical-volumes": second_ref},
            "pointer_updates": [
                {
                    "dataset_id": "historical-prices",
                    "manifest_ref": first_wrong_ref,
                    "watermark": "2026-02-28T00:00:00+00:00",
                    "published_at": "2026-04-02T00:00:00+00:00",
                },
                {
                    "dataset_id": "historical-volumes",
                    "manifest_ref": second_wrong_ref,
                    "watermark": "2026-03-31T00:00:00+00:00",
                    "published_at": "2026-04-03T00:00:00+00:00",
                },
            ],
        },
    )

    rendered = repr(_details(row, None))
    for text in (
        "Historical source run completed",
        "Range: 2026-01-01 → 2026-03-31 (inclusive)",
        "Datasets produced: 2",
        "Production pointer: Unchanged",
        "Inputs",
        "Base source revision",
        "Config hash",
        "Pointer update",
        "Outputs",
        "Dataset ID",
        "Watermark",
        "Published at",
        "2026-02-28T00:00:00+00:00",
        "2026-04-02T00:00:00+00:00",
        "2026-03-31T00:00:00+00:00",
        "2026-04-03T00:00:00+00:00",
        first_ref,
        second_ref,
        f"content='{first_ref}'",
        f"content='{second_ref}'",
    ):
        assert text in rendered
    assert first_wrong_ref not in rendered
    assert second_wrong_ref not in rendered


def test_unsupported_historical_run_drawer_keeps_domain_error_before_logs() -> None:
    stamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    row = SimpleNamespace(
        run_id="historical-run",
        kind="source",
        target_id="prices",
        mode="historical",
        start_date="2026-01-01",
        end_date="2026-03-31",
        trigger="manual",
        slot=stamp,
        requested_at=stamp,
        started_at=None,
        finished_at=stamp,
        worker_id="local:1",
        cancel_requested_at=None,
        config_revision=18,
        config_hash="config-hash",
        snapshot_id=None,
        context_hash=None,
        code_version=None,
        artifact_id=None,
        reason="Source 'prices' does not support historical date-range execution.",
        status="failed",
        result={"status": "failed", "reason": "TypeError: unexpected keyword argument 'execution_context'"},
    )

    rendered = repr(_details(row, None))
    assert "Historical source run failed" in rendered
    assert "Source 'prices' does not support historical date-range execution." in rendered
    assert "Range: 2026-01-01 → 2026-03-31 (inclusive)" in rendered
    assert "TypeError" not in rendered


def test_historical_run_drawer_keeps_genuine_runtime_type_error() -> None:
    stamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    runtime_reason = "TypeError: vendor payload has an invalid value"
    row = SimpleNamespace(
        run_id="historical-run",
        kind="source",
        target_id="prices",
        mode="historical",
        start_date="2026-01-01",
        end_date="2026-03-31",
        trigger="manual",
        slot=stamp,
        requested_at=stamp,
        started_at=None,
        finished_at=stamp,
        worker_id="local:1",
        cancel_requested_at=None,
        config_revision=18,
        config_hash="config-hash",
        snapshot_id=None,
        context_hash=None,
        code_version=None,
        artifact_id=None,
        reason=runtime_reason,
        status="failed",
        result={"status": "failed"},
    )

    rendered = repr(_details(row, None))
    assert runtime_reason in rendered
    assert "does not support historical date-range execution" not in rendered


def test_historical_run_drawer_reports_missing_failure_reason_neutrally() -> None:
    assert _historical_failure_reason(SimpleNamespace(target_id="prices", reason=None)) == "No failure reason recorded"


def test_run_drawer_ignores_malformed_or_missing_click() -> None:
    events: list[dict[str, object] | None] = [None] * len(_ROW_INPUTS)
    attention_index = _ROW_INPUTS.index("runbook-ui-dashboard-attention-grid")

    events[attention_index] = {"rowId": 42}

    assert (
        run_drawer._run_id_for_trigger(
            _ROW_INPUTS[attention_index],
            tuple(events),
            "stale-run",
        )
        is None
    )

    events[attention_index] = {}

    assert (
        run_drawer._run_id_for_trigger(
            _ROW_INPUTS[attention_index],
            tuple(events),
            "stale-run",
        )
        is None
    )

    events[attention_index] = None

    assert (
        run_drawer._run_id_for_trigger(
            _ROW_INPUTS[attention_index],
            tuple(events),
            "stale-run",
        )
        is None
    )


def test_shell_hash_scroll_callback_and_config_offsets() -> None:
    app = mount_ui(FastAPI(), sessions=None, data_store=None, reports_root="")
    callback = app.callback_map["runbook-ui-hash-scroll.data"]
    assert callback["inputs"] == [
        {"id": "runbook-ui-location", "property": "pathname"},
        {"id": "runbook-ui-location", "property": "hash"},
    ]
    callback_record = next(item for item in app._callback_list if item["output"] == "runbook-ui-hash-scroll.data")
    assert callback_record["clientside_function"] == {
        "namespace": "runbookNavigation",
        "function_name": "scrollToHash",
    }
    assert "runbook-ui-hash-scroll" in str(app.layout)
    navigation_js = (
        Path(__file__).resolve().parents[2]
        / "packages/runbook/runbook-services/src/runbook/services/assets/navigation.js"
    ).read_text(encoding="utf-8")
    assert "window.dash_clientside" in navigation_js
    assert "runbookNavigation" in navigation_js
    assert "scrollToHash" in navigation_js
    assert "decodeURIComponent" in navigation_js
    assert 'scrollIntoView({block: "start"})' in navigation_js
    assert "MutationObserver" in navigation_js
    assert "observer.disconnect()" in navigation_js
    assert "window.clearTimeout(timeoutId)" in navigation_js
    assert "window.clearTimeout(settleTimeoutId)" in navigation_js
    assert "let settleTimeoutId" in navigation_js
    assert "settleTimeoutId = undefined" in navigation_js
    assert "window.setTimeout(function ()" in navigation_js
    assert "}, 80)" in navigation_js
    assert "window.setTimeout(cleanup, 2000)" in navigation_js
    assert 'window.addEventListener("hashchange"' in navigation_js
    assert "scrollToHash(window.location.pathname, window.location.hash)" in navigation_js
    css = (
        Path(__file__).resolve().parents[2]
        / "packages/runbook/runbook-services/src/runbook/services/assets/operations.css"
    ).read_text(encoding="utf-8")
    assert "#runbook-ui-profiles-config, #runbook-ui-sources-config" in css
    assert "scroll-margin-top: 72px" in css
