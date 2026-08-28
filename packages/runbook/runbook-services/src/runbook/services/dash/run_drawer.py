"""Canonical right-side run inspection drawer shared by every operations page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
from runbook.core import open_blob_store

from ..logging import RunLogIdentity, read_log_tail
from ..repository import AsyncRunRepository
from .operations import copy_value, empty_state, format_duration, run_status, status_badge

PREFIX = "runbook-ui-run-drawer"
_ROW_INPUTS = (
    "runbook-ui-runs-grid",
    "runbook-ui-dashboard-active-grid",
    "runbook-ui-dashboard-attention-grid",
    "runbook-ui-profile-detail-runs-grid",
    "runbook-ui-source-detail-runs-grid",
)


def _run_id_from_click(event: dict[str, Any] | None) -> str | None:
    """Return the stable row ID emitted by an AG Grid cell click."""
    if not event:
        return None

    run_id = event.get("rowId")
    return run_id if isinstance(run_id, str) else None


def _run_id_for_trigger(
    triggered_id: str | None,
    events: tuple[dict[str, Any] | None, ...],
    selected_state: str | None,
) -> str | None:
    """Resolve selection from the grid that triggered it."""
    if triggered_id in {f"{PREFIX}-log-refresh", f"{PREFIX}-cancel"}:
        return selected_state

    try:
        event_index = _ROW_INPUTS.index(triggered_id or "")
    except ValueError:
        return None

    if event_index >= len(events):
        return None

    return _run_id_from_click(events[event_index])


def _aware_slot(value: datetime) -> datetime:
    """Normalize a run slot for immutable log addressing."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _metadata_group(title: str, values: list[tuple[str, Any]]) -> Any:
    """Render one compact grouped metadata card."""
    return dmc.Card(
        [
            dmc.Text(title, fw=600, size="sm", mb=4),
            dmc.Stack(
                [
                    dmc.Group([dmc.Text(label, size="xs", c="dimmed", w=125), value], gap="xs", wrap="nowrap")
                    for label, value in values
                ],
                gap=3,
            ),
        ],
        withBorder=True,
        padding="xs",
        radius="sm",
    )


def _historical_range(row: Any) -> str:
    """Format the immutable requested range for the historical summary."""
    start = getattr(row, "start_date", None) or "—"
    end = getattr(row, "end_date", None) or "—"
    return f"{start} → {end} (inclusive)"


def _historical_datasets(result: dict[str, Any]) -> dict[str, str]:
    """Return persisted historical dataset outputs without querying storage."""
    datasets = result.get("datasets")
    if not isinstance(datasets, dict):
        return {}
    return {
        str(dataset_id): str(manifest_ref)
        for dataset_id, manifest_ref in datasets.items()
        if dataset_id is not None and manifest_ref not in (None, "")
    }


def _historical_failure_reason(row: Any) -> str:
    """Display the worker's persisted reason, or state that none was recorded."""
    return str(getattr(row, "reason", None) or "No failure reason recorded")


def _historical_summary(row: Any, result: dict[str, Any]) -> Any | None:
    """Render a prominent completion or failure summary before diagnostic logs."""
    status = str(getattr(row, "status", "") or "").lower()
    if status == "success":
        return dmc.Alert(
            [
                dmc.Text("Completed", fw=600),
                dmc.Text(f"Range: {_historical_range(row)}"),
                dmc.Text(f"Datasets produced: {len(_historical_datasets(result))}"),
                dmc.Text("Production pointer: Unchanged"),
            ],
            title="Historical source run completed",
            color="green",
            variant="light",
        )
    if status == "failed":
        return dmc.Alert(
            [
                dmc.Text(_historical_failure_reason(row), fw=600),
                dmc.Text(f"Source: {row.target_id}"),
                dmc.Text(f"Range: {_historical_range(row)}"),
            ],
            title="Historical source run failed",
            color="red",
            variant="light",
        )
    return None


def _historical_inputs(row: Any) -> Any:
    """Render the immutable historical request and its provenance."""
    return _metadata_group(
        "Inputs",
        [
            ("Source", dmc.Text(str(row.target_id), size="sm")),
            ("Mode", dmc.Text("Historical", size="sm")),
            ("Date range", dmc.Text(_historical_range(row), size="sm")),
            ("Base source revision", dmc.Text(str(row.config_revision), size="sm")),
            ("Config hash", copy_value(row.config_hash, label="config hash")),
            ("Pointer update", dmc.Text("No", size="sm")),
            ("Trigger", dmc.Text(str(row.trigger), size="sm")),
            ("Requested", dmc.Text(str(row.requested_at), size="sm")),
        ],
    )


def _historical_outputs(result: dict[str, Any]) -> Any:
    """Render immutable manifest refs and persisted publication metadata."""
    datasets = _historical_datasets(result)
    updates: dict[str, dict[str, Any]] = {}
    raw_updates = result.get("pointer_updates")
    if isinstance(raw_updates, (list, tuple)):
        for item in raw_updates:
            if not isinstance(item, dict) or item.get("dataset_id") is None:
                continue
            updates[str(item["dataset_id"])] = item

    dataset_groups: list[Any] = []
    for dataset_id, stored_manifest_ref in datasets.items():
        metadata = updates.get(dataset_id, {})
        dataset_groups.append(
            _metadata_group(
                dataset_id,
                [
                    ("Dataset ID", dmc.Text(dataset_id, size="sm")),
                    ("Manifest", copy_value(stored_manifest_ref, label=f"{dataset_id} manifest")),
                    ("Watermark", dmc.Text(str(metadata.get("watermark") or "—"), size="sm")),
                    ("Published at", dmc.Text(str(metadata.get("published_at") or "—"), size="sm")),
                ],
            )
        )
    if not dataset_groups:
        dataset_groups.append(dmc.Text("No datasets produced.", c="dimmed", size="sm"))
    return dmc.Card(
        [dmc.Text("Outputs", fw=600, size="sm", mb=4), dmc.Stack(dataset_groups, gap="xs")],
        withBorder=True,
        padding="xs",
        radius="sm",
    )


def _details(row: Any, config: Any | None) -> Any:
    """Group execution, ownership, provenance, and outcome metadata."""
    status = run_status(row)
    result = getattr(row, "result", None)
    if not isinstance(result, dict):
        result = {}
    historical = str(getattr(row, "mode", None) or "normal").lower() == "historical"
    reason = _historical_failure_reason(row) if historical and status == "failed" else getattr(row, "reason", None)
    sections: list[Any] = []
    if historical:
        summary = _historical_summary(row, result)
        if summary is not None:
            sections.append(summary)
        sections.extend([_historical_inputs(row), _historical_outputs(result)])
    sections.extend(
        [
            _metadata_group(
                "Execution",
                [
                    ("Status", status_badge(status)),
                    ("Target", dmc.Text(f"{row.kind}: {row.target_id}", size="sm")),
                    ("Run kind", dmc.Text(row.kind, size="sm")),
                    ("Mode", dmc.Text(str(getattr(row, "mode", None) or "normal").title(), size="sm")),
                    (
                        "Date range",
                        dmc.Text(
                            f"{getattr(row, 'start_date', None) or '—'} → {getattr(row, 'end_date', None) or '—'}",
                            size="sm",
                        ),
                    ),
                    ("Trigger", dmc.Text(row.trigger, size="sm")),
                    ("Slot", dmc.Text(str(row.slot), size="sm")),
                    ("Requested", dmc.Text(str(row.requested_at), size="sm")),
                    ("Started", dmc.Text(str(row.started_at or "—"), size="sm")),
                    ("Finished", dmc.Text(str(row.finished_at or "—"), size="sm")),
                    ("Duration", dmc.Text(format_duration(row.started_at, row.finished_at), size="sm")),
                ],
            ),
            _metadata_group(
                "Ownership",
                [
                    ("Worker", copy_value(row.worker_id, label="worker ID")),
                    ("Cancel requested", dmc.Text(str(row.cancel_requested_at or "—"), size="sm")),
                ],
            ),
            _metadata_group(
                "Provenance",
                [
                    ("Run ID", copy_value(row.run_id, label="run ID", max_length=26)),
                    ("Config revision", dmc.Text(str(row.config_revision), size="sm")),
                    ("Config hash", copy_value(row.config_hash, label="config hash")),
                    ("Snapshot", copy_value(row.snapshot_id, label="snapshot ID")),
                    ("Context hash", copy_value(row.context_hash, label="context hash")),
                    ("Code version", copy_value(row.code_version, label="code version")),
                    ("Artifact", copy_value(row.artifact_id, label="artifact ID")),
                ],
            ),
            _metadata_group(
                "Outcome",
                [
                    ("Status", status_badge(status)),
                    ("Reason", dmc.Text(reason or "—", size="sm")),
                    ("Result", dmc.Text(str(result.get("status") or result.get("message") or "—"), size="sm")),
                    ("Pinned config", copy_value(getattr(config, "config_hash", None), label="pinned config hash")),
                ],
            ),
        ]
    )
    return dmc.Stack(
        sections,
        gap="xs",
    )


def drawer() -> Any:
    """Build the mounted right-side drawer and its independent panes."""
    return dmc.Drawer(
        id=PREFIX,
        opened=False,
        title=dmc.Text(id=f"{PREFIX}-title", fw=600),
        position="right",
        size="min(760px, 50vw)",
        withCloseButton=True,
        closeButtonProps={"aria-label": "Close run inspection"},
        closeOnClickOutside=False,
        closeOnEscape=True,
        children=[
            dcc.Store(id=f"{PREFIX}-selected"),
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            dmc.Text("Run metadata", fw=600),
                            dmc.Button(
                                "Cancel", id=f"{PREFIX}-cancel", size="xs", color="red", variant="light", disabled=True
                            ),
                        ],
                        justify="space-between",
                    ),
                    html.Div(id=f"{PREFIX}-details", className="runbook-drawer-details"),
                    html.Hr(),
                    dmc.Group(
                        [
                            dmc.Text("Logs", fw=600),
                            dmc.Button("Refresh logs", id=f"{PREFIX}-log-refresh", size="xs", variant="light"),
                            dcc.Clipboard(id=f"{PREFIX}-copy", title="Copy all logs", className="runbook-copy"),
                        ],
                        justify="space-between",
                    ),
                    html.Div(id=f"{PREFIX}-log-status", className="runbook-muted"),
                    html.Pre(id=f"{PREFIX}-logs", className="runbook-drawer-logs"),
                    html.Div(id=f"{PREFIX}-cancel-result", className="runbook-muted"),
                ],
                gap="xs",
                className="runbook-drawer-stack",
            ),
        ],
    )


async def _read_logs(row: Any, config: Any | None, data_store: str) -> tuple[str, str]:
    """Read the immutable log tail and describe its terminal state."""
    if not data_store:
        return "", "Diagnostic log store is not configured."
    identity = RunLogIdentity(
        run_id=row.run_id,
        kind=row.kind,
        target_id=row.target_id,
        slot=_aware_slot(row.slot),
        report_id=(config.payload.get("report_id") if config and row.kind == "profile" else None),
    )
    try:
        tail = await asyncio.to_thread(read_log_tail, open_blob_store(data_store), identity, 0)
    except Exception as exc:  # pragma: no cover - driver/store-specific failure rendering
        return "", f"Unable to load logs: {exc}"
    text = str(tail.get("text") or "")
    if tail.get("incomplete"):
        state = "incomplete after worker termination"
    elif tail.get("manifest"):
        state = "completed (truncated)" if tail["manifest"].get("truncated") else "completed"
    elif row.status in {"queued", "running"}:
        state = "active; refresh manually"
    elif text:
        state = "incomplete"
    else:
        state = "no diagnostic logging captured"
    return text, f"{state} · {len(text.encode('utf-8'))} bytes"


def register(dash_app: Any, sessions: Any, data_store: str) -> None:
    """Register one callback for all run-table entry points and log refresh."""
    inputs = [Input(component, "cellClicked", allow_optional=True) for component in _ROW_INPUTS]

    @dash_app.callback(
        Output(PREFIX, "opened"),
        Output(f"{PREFIX}-title", "children"),
        Output(f"{PREFIX}-details", "children"),
        Output(f"{PREFIX}-logs", "children"),
        Output(f"{PREFIX}-log-status", "children"),
        Output(f"{PREFIX}-copy", "content"),
        Output(f"{PREFIX}-cancel", "disabled"),
        Output(f"{PREFIX}-cancel-result", "children"),
        Output(f"{PREFIX}-selected", "data"),
        *inputs,
        Input(f"{PREFIX}-log-refresh", "n_clicks"),
        Input(f"{PREFIX}-cancel", "n_clicks"),
        State(f"{PREFIX}-selected", "data"),
    )
    async def inspect(*args: Any):
        """Open, refresh, or cancel the clicked run without changing its route."""
        events = args[: len(_ROW_INPUTS)]
        cancel_clicks = args[len(_ROW_INPUTS) + 1]
        selected_state = args[len(_ROW_INPUTS) + 2]
        run_id = _run_id_for_trigger(
            ctx.triggered_id,
            events,
            selected_state if isinstance(selected_state, str) else None,
        )
        if ctx.triggered_id in {f"{PREFIX}-cancel", f"{PREFIX}-log-refresh"} and not run_id:
            return (
                False,
                "Run inspection",
                empty_state("No run selected", "Select a run from an operational table."),
                "",
                "",
                "",
                True,
                "",
                None,
            )
        if not run_id:
            return (
                no_update,  # opened
                no_update,  # title
                no_update,  # details
                no_update,  # logs
                no_update,  # log status
                no_update,  # clipboard
                no_update,  # cancel disabled
                no_update,  # cancel result
                no_update,  # selected run
            )
        message = ""
        async with sessions() as session:
            repository = AsyncRunRepository(session)
            if ctx.triggered_id == f"{PREFIX}-cancel" and cancel_clicks:
                async with session.begin():
                    await repository.request_cancel(run_id)
                message = "Cancellation requested where the durable run state permits it."
            row = await repository.get_run(run_id)
            config = await repository.get_config(row.kind, row.target_id, row.config_revision) if row else None
        if row is None:
            return (
                False,
                f"Run {run_id}",
                empty_state("Run not found", "The run may have been compacted or removed."),
                "",
                "",
                "",
                True,
                "",
                None,
            )
        logs, log_status = await _read_logs(row, config, data_store)
        cancel_disabled = row.status not in {"queued", "running"} or row.cancel_requested_at is not None
        return (
            True,
            f"Run {row.run_id[:12]}…",
            _details(row, config),
            logs,
            log_status,
            logs,
            cancel_disabled,
            message,
            row.run_id,
        )


__all__ = ["PREFIX", "_run_id_from_click", "_run_id_for_trigger", "drawer", "register"]
