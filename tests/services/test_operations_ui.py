from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import dash
import dash_mantine_components as dmc
from dash import no_update
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
    _closed_content,
    _details,
    _header,
    _historical_failure_reason,
    _is_automatic_poll,
    _poll_disabled,
    _poll_state,
    _run_id_for_trigger,
    _run_id_from_click,
    _shell_selection,
    _status_summary,
    _timeline,
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


def test_run_drawer_text_omits_null_color_and_keeps_dimmed_color() -> None:
    plain_props = run_drawer._text("abc").to_plotly_json()["props"]
    dimmed_props = run_drawer._text("abc", dimmed=True).to_plotly_json()["props"]

    assert "c" not in plain_props
    assert dimmed_props["c"] == "dimmed"


def _drawer_row(status: str, *, kind: str = "source", trigger: str = "schedule", **updates: object) -> SimpleNamespace:
    """Build a compact durable run row for drawer presentation tests."""
    stamp = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
    values: dict[str, object] = {
        "run_id": "run-1234567890",
        "kind": kind,
        "target_id": "murban_export_availability" if kind == "source" else "crude_weekly",
        "mode": "normal",
        "trigger": trigger,
        "status": status,
        "requested_at": stamp,
        "started_at": stamp if status not in {"queued", "cancelled"} else None,
        "finished_at": stamp.replace(minute=1) if status in {"success", "failed", "cancelled"} else None,
        "slot": stamp,
        "config_revision": 18,
        "config_hash": "config-hash",
        "snapshot_id": "snapshot-id",
        "context_hash": "context-hash",
        "code_version": "v1",
        "artifact_id": None,
        "worker_id": "local:1",
        "cancel_requested_at": None,
        "reason": "parser failed" if status == "failed" else None,
        "result": {},
        "snapshot_payload": {},
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_run_drawer_shell_selection_clears_native_close_and_never_reopens_on_poll() -> None:
    """A closed drawer must clear its store before any poll can refresh content."""
    closed, selected, loading, polling = _shell_selection(run_drawer.PREFIX, (), "run-1", False)
    assert closed is no_update
    assert selected is None
    assert loading == "hide"
    assert polling is True
    assert _run_id_for_trigger(f"{run_drawer.PREFIX}-poll", (), selected) is None


def test_run_drawer_shell_selection_opens_only_from_valid_cell_click() -> None:
    """Only a rowId cell click synchronously opens and selects a run."""
    event_list: list[dict[str, object] | None] = [None] * len(_ROW_INPUTS)
    event_list[0] = {"rowId": "clicked-run"}
    events = tuple(event_list)
    assert _shell_selection(_ROW_INPUTS[0], events, None, False) == (True, "clicked-run", "show", True)
    assert _shell_selection(_ROW_INPUTS[0], ({},) + (None,) * (len(_ROW_INPUTS) - 1), "old-run", True) == (
        no_update,
        no_update,
        no_update,
        no_update,
    )


def test_run_drawer_navigation_clears_selection_without_async_shell_outputs() -> None:
    """Navigation closes and clears synchronously, while content cannot own shell state."""
    assert _shell_selection("runbook-ui-location", (), "old-run", True) == (False, None, "hide", True)
    app = dash.Dash(__name__, use_pages=False)
    run_drawer.register(app, None, "")
    content_key = next(key for key in app.callback_map if key.startswith(f"..{run_drawer.PREFIX}-title"))
    assert f"{run_drawer.PREFIX}.opened" not in content_key
    assert f"{run_drawer.PREFIX}-selected.data" not in content_key


def test_run_drawer_loader_display_is_owned_by_shell_and_content_callbacks() -> None:
    """Shell clicks show the local loader; content completion hides it."""
    app = dash.Dash(__name__, use_pages=False)
    run_drawer.register(app, None, "")
    loading_id = f"{run_drawer.PREFIX}-details-loading"
    shell_key = next(key for key in app.callback_map if key.startswith(f"..{run_drawer.PREFIX}.opened"))
    inspect_key = next(key for key in app.callback_map if key.startswith(f"..{run_drawer.PREFIX}-title"))
    shell = app.callback_map[shell_key]
    inspect = app.callback_map[inspect_key]
    shell_record = next(record for record in app._callback_list if record["output"] == shell_key)

    shell_outputs = shell["output"]
    inspect_outputs = inspect["output"]
    assert shell_record["prevent_initial_call"] is True
    assert any(output.component_id == loading_id and output.component_property == "display" for output in shell_outputs)
    assert shell_outputs[2].allow_duplicate is True
    assert shell_outputs[-1].component_id == f"{run_drawer.PREFIX}-poll"
    assert shell_outputs[-1].component_property == "disabled"
    assert inspect_outputs[-2].component_id == loading_id
    assert inspect_outputs[-2].component_property == "display"
    assert inspect_outputs[-1].component_id == f"{run_drawer.PREFIX}-poll-state"
    assert inspect_outputs[-1].component_property == "data"
    assert all(
        output.component_id not in {run_drawer.PREFIX, f"{run_drawer.PREFIX}-selected", f"{run_drawer.PREFIX}-poll"}
        for output in inspect_outputs
    )
    assert _closed_content()[-2] == "hide"
    assert _closed_content()[-1] is None
    assert run_drawer.drawer().children[2].disabled is True
    loading = run_drawer.drawer().children[3].children[1].children
    assert loading.to_plotly_json()["props"]["display"] == "hide"


def test_run_drawer_poll_state_only_enables_matching_active_selection() -> None:
    """Initial, terminal, stale, and closed states all keep polling disabled."""
    active = {"run_id": "run-1", "active": True}
    terminal = {"run_id": "run-1", "active": False}
    assert _poll_disabled(None, "run-1", True) is True
    assert _poll_disabled(active, "run-1", True) is False
    assert _poll_disabled(terminal, "run-1", True) is True
    assert _poll_disabled({"run_id": "run-2", "active": True}, "run-1", True) is True
    assert _poll_disabled(active, "run-1", False) is True
    assert _poll_disabled(active, None, True) is True
    assert _poll_state(_drawer_row("running")) == {"run_id": "run-1234567890", "active": True}
    for status in ("success", "waiting", "not_ready"):
        assert _poll_state(_drawer_row(status)) == {"run_id": "run-1234567890", "active": False}


def test_run_drawer_automatic_poll_preserves_existing_logs() -> None:
    """Only the interval path skips the blob-store log read."""
    assert _is_automatic_poll(f"{run_drawer.PREFIX}-poll") is True
    assert _is_automatic_poll(f"{run_drawer.PREFIX}-log-refresh") is False
    assert _is_automatic_poll(f"{run_drawer.PREFIX}-cancel") is False


def test_run_drawer_automatic_poll_does_not_reread_logs(monkeypatch) -> None:
    """Interval refreshes retain rendered logs while updating run details."""

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class Sessions:
        def __call__(self):
            return Session()

    row = _drawer_row("running")

    class Repository:
        def __init__(self, _session):
            pass

        async def get_run(self, _run_id):
            return row

        async def get_config(self, *_args):
            return None

    async def fail_read_logs(*_args):
        raise AssertionError("automatic polls must not read logs")

    monkeypatch.setattr(run_drawer, "AsyncRunRepository", Repository)
    monkeypatch.setattr(run_drawer, "_read_logs", fail_read_logs)
    monkeypatch.setattr(run_drawer, "ctx", SimpleNamespace(triggered_id=f"{run_drawer.PREFIX}-poll"))
    app = dash.Dash(__name__, use_pages=False)
    run_drawer.register(app, Sessions(), "store")
    key = next(key for key in app.callback_map if key.startswith(f"..{run_drawer.PREFIX}-title"))
    callback = app.callback_map[key]["callback"].__wrapped__
    result = asyncio.run(callback(row.run_id, 1, "/ui/", True, None, None))
    assert result[2:5] == (no_update, no_update, no_update)
    assert result[-2] == "hide"
    assert result[-1] == {"run_id": row.run_id, "active": True}


def test_run_drawer_layout_keeps_loading_inside_scrollable_details_parent() -> None:
    """The flex class belongs to the Loading parent rather than its inner child."""
    rendered = repr(run_drawer.drawer())
    assert "className='runbook-drawer-details'" in rendered
    assert "className='runbook-drawer-details-content'" in rendered
    assert "runbook-ui-run-drawer-details-loading" in rendered


def test_run_drawer_human_headers_and_type_specific_sections() -> None:
    """Source IDs and configured report titles establish identity before technical fields."""
    source = _drawer_row(
        "success",
        result={"status": "success", "datasets": {"prices": "manifests/prices.json"}, "log_ref": "logs/source"},
    )
    source_config = SimpleNamespace(
        payload={
            "adapter": "http",
            "datasets": {"prices": {"dataset_id": "prices", "parser_id": "csv"}},
        }
    )
    source_rendered = repr(_header(source, source_config)) + repr(_details(source, source_config))
    assert "Murban export availability" in source_rendered
    assert "Source run · Automatic" in source_rendered
    assert "Execution" in source_rendered and "Adapter" in source_rendered and "Parser" in source_rendered
    assert "manifests/prices.json" in source_rendered

    report = _drawer_row(
        "success",
        kind="profile",
        trigger="dataset",
        result={
            "status": "success",
            "report_id": "crude_weekly",
            "artifact_id": "artifact-1",
            "snapshot_id": "snapshot-id",
            "context_hash": "context-hash",
            "code_version": "v1",
            "html_ref": "reports/crude.html",
            "stage3_ref": "reports/stage3.json",
            "stage4_ref": "reports/stage4.json",
            "cache_hits": {"prices": True},
            "snapshot": {"datasets": {"prices": "manifests/prices.json"}},
        },
        snapshot_payload={"datasets": {"prices": "manifests/prices.json"}},
    )
    report_config = SimpleNamespace(
        payload={"title": "Crude Weekly", "report_id": "crude_weekly", "datasets": {"prices": "prices"}}
    )
    report_rendered = repr(_header(report, report_config)) + repr(_details(report, report_config))
    assert "Crude Weekly" in report_rendered
    assert "Report run · Automatic" in report_rendered
    assert "Outputs & artifacts" in report_rendered and "reports/crude.html" in report_rendered


def test_run_drawer_status_summaries_and_timeline_cover_lifecycle_states() -> None:
    """Every durable lifecycle state gets readable status and lifecycle text."""
    expectations = {
        "queued": "Queued for",
        "running": "Running for",
        "success": "Succeeded in",
        "failed": "Failed after",
        "cancelled": "Cancelled before worker start",
        "waiting": "Waiting for dependencies",
        "not_ready": "Not ready",
        "skipped": "Skipped",
    }
    for status, expected in expectations.items():
        row = _drawer_row(status)
        rendered = repr(_status_summary(row)) + repr(_timeline(row))
        assert expected in rendered
        assert status.replace("_", " ").title() in rendered or status == "success"


def test_run_drawer_failure_is_prominent_and_logs_are_collapsed_lower_down() -> None:
    """Failure reasons render in details before the drawer's collapsed logs section."""
    row = _drawer_row(
        "failed", reason=None, result={"status": "failed", "reason": "worker error", "log_ref": "logs/fail"}
    )
    details = repr(_details(row, None))
    shell = repr(run_drawer.drawer())
    assert "Failure" in details and "worker error" in details
    assert shell.index("runbook-ui-run-drawer-details") < shell.index("Logs")
    assert "AccordionItem" in shell


def test_run_drawer_report_without_artifacts_uses_one_empty_state() -> None:
    """Queued and failed report runs do not show four repetitive missing artifact rows."""
    config = SimpleNamespace(
        payload={"title": "Crude Weekly", "report_id": "crude_weekly", "datasets": {"prices": "prices"}}
    )
    for status in ("queued", "failed"):
        rendered = repr(_details(_drawer_row(status, kind="profile"), config))
        assert rendered.count("No artifacts") == 1
        assert "Artifact ID" not in rendered


def test_run_drawer_manual_report_keeps_barrier_warning_prominent_and_raw_details_collapsed() -> None:
    """Manual report provenance retains the persisted dependency-barrier warning."""
    row = _drawer_row(
        "success",
        kind="profile",
        trigger="manual",
        snapshot_payload={
            "snapshot_id": "snapshot-id",
            "datasets": {"prices": "manifests/prices.json"},
            "producer_provenance": [{"producer_id": "prices-source", "source_run_id": "source-run"}],
            "warnings": ["Automatic dependency barrier bypassed by manual profile run."],
        },
        result={"status": "success", "snapshot": {"warnings": ["ignored"]}, "debug": {"secret": True}},
    )
    config = SimpleNamespace(
        payload={"title": "Crude Weekly", "report_id": "crude_weekly", "datasets": {"prices": "prices"}}
    )
    rendered = repr(_details(row, config))
    assert "Automatic dependency barrier bypassed" in rendered
    assert "source-run" in rendered and "prices-source" in rendered
    assert "secret" not in rendered
    assert "Raw details" in rendered


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
