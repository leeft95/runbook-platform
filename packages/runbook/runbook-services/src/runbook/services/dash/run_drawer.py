"""Canonical right-side run inspection drawer shared by every operations page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html
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


def _run_id_from_rows(*rows: list[dict[str, Any]] | None) -> str | None:
    """Return the selected run ID from any supported table entry point."""
    for selected in rows:
        if selected and isinstance(selected[0].get("run_id"), str):
            return selected[0]["run_id"]
    return None


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


def _details(row: Any, config: Any | None) -> Any:
    """Group execution, ownership, provenance, and outcome metadata."""
    status = run_status(row)
    result = getattr(row, "result", None) or {}
    return dmc.Stack(
        [
            _metadata_group(
                "Execution",
                [
                    ("Status", status_badge(status)),
                    ("Target", dmc.Text(f"{row.kind}: {row.target_id}", size="sm")),
                    ("Run kind", dmc.Text(row.kind, size="sm")),
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
                    ("Reason", dmc.Text(row.reason or "—", size="sm")),
                    ("Result", dmc.Text(str(result.get("status") or result.get("message") or "—"), size="sm")),
                    ("Pinned config", copy_value(getattr(config, "config_hash", None), label="pinned config hash")),
                ],
            ),
        ],
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
    inputs = [Input(f"{component}", "selectedRows") for component in _ROW_INPUTS]

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
        """Open, refresh, or cancel the selected run without changing its route."""
        selected = args[: len(_ROW_INPUTS)]
        cancel_clicks = args[len(_ROW_INPUTS) + 1]
        selected_state = args[len(_ROW_INPUTS) + 2]
        run_id = _run_id_from_rows(*selected) or (selected_state if isinstance(selected_state, str) else None)
        if ctx.triggered_id == f"{PREFIX}-cancel" and cancel_clicks:
            run_id = selected_state if isinstance(selected_state, str) else run_id
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
                False,
                "Run inspection",
                empty_state("Select a run", "Select any run row to inspect metadata and logs."),
                "",
                "",
                "",
                True,
                "",
                None,
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


__all__ = ["PREFIX", "_run_id_from_rows", "drawer", "register"]
