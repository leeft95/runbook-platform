"""Canonical right-side run inspection drawer shared by every operations page."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
from runbook.core import open_blob_store

from ..logging import RunLogIdentity, read_log_tail
from ..repository import AsyncRunRepository
from .operations import copy_value, empty_state, format_duration, run_status, status_badge, status_label

PREFIX = "runbook-ui-run-drawer"
_POLL_INTERVAL_MS = 5_000
_LOCATION_INPUT = "runbook-ui-location"
_POLL_STATE_INPUT = f"{PREFIX}-poll-state"
_POLLABLE_STATUSES = {"queued", "running", "cancelling"}
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
    """Resolve selection from the triggering grid or stored drawer identity."""
    if triggered_id in {f"{PREFIX}-log-refresh", f"{PREFIX}-cancel", f"{PREFIX}-poll"}:
        return selected_state
    try:
        event_index = _ROW_INPUTS.index(triggered_id or "")
    except ValueError:
        return None
    if event_index >= len(events):
        return None
    return _run_id_from_click(events[event_index])


def _row_value(row: Any, name: str, default: Any = None) -> Any:
    """Read ORM and mapping rows uniformly in this presentation-only module."""
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _not_available(value: Any, fallback: str = "Not available") -> str:
    """Return a user-facing scalar without leaking Python null representations."""
    if value is None or value == "" or value == {} or value == []:
        return fallback
    return str(value)


def _text(value: Any, *, fallback: str = "Not available", size: str = "sm", dimmed: bool = False) -> Any:
    """Render a readable scalar value."""
    return dmc.Text(_not_available(value, fallback), size=size, **({"c": "dimmed"} if dimmed else {}))


def _copy(value: Any, *, label: str, max_length: int = 26) -> Any:
    """Copy long identifiers while keeping missing values human-readable."""
    if value is None or value == "":
        return _text(None)
    return copy_value(value, label=label, max_length=max_length)


def _metadata_group(title: str, values: list[tuple[str, Any]]) -> Any:
    """Render one compact grouped metadata card."""
    details: list[Any] = []
    for label, value in values:
        details.extend(
            [
                html.Div(label, className="runbook-detail-label"),
                html.Div(value, className="runbook-detail-value"),
            ]
        )
    return dmc.Card(
        [
            dmc.Text(title, fw=600, size="sm", mb=4, className="runbook-detail-section-title"),
            html.Div(details, className="runbook-detail-grid"),
        ],
        withBorder=True,
        padding="xs",
        radius="sm",
        className="runbook-detail-section",
    )


def _human_name(value: Any) -> str:
    """Turn an identifier into a concise sentence-case human title."""
    raw = str(value or "").replace("_", " ").replace("-", " ").strip()
    return raw[:1].upper() + raw[1:] if raw else "Run"


def _run_type(row: Any) -> str:
    """Return the operator-facing type label for a durable run."""
    return "Source run" if _row_value(row, "kind") == "source" else "Report run"


def _mode_label(row: Any) -> str:
    """Return the operator-facing execution mode."""
    mode = str(_row_value(row, "mode") or "normal").lower()
    if mode == "historical":
        return "Historical"
    trigger = str(_row_value(row, "trigger") or "").lower()
    if trigger == "manual":
        return "Manual"
    if trigger in {"schedule", "dataset", "automatic", "auto"}:
        return "Automatic"
    return _human_name(trigger) if trigger else "Automatic"


def _config_payload(config: Any | None) -> dict[str, Any]:
    """Extract a configuration payload from a revision, mapping, or model."""
    if isinstance(config, dict):
        payload = config.get("payload")
        return payload if isinstance(payload, dict) else config
    if config is not None and hasattr(config, "model_dump"):
        payload = config.model_dump(mode="json")
        return payload if isinstance(payload, dict) else {}
    payload = _row_value(config, "payload", {}) if config is not None else {}
    return payload if isinstance(payload, dict) else {}


def _config_title(row: Any, config: Any | None) -> str:
    """Resolve a human title, falling back to a prettified target ID."""
    payload = _config_payload(config)
    title = payload.get("title") if _row_value(row, "kind") != "source" else None
    return _not_available(title, _human_name(_row_value(row, "target_id")))


def _duration(start: Any, end: Any = None, *, fallback: str = "Not available") -> str:
    """Use the shared duration formatter while tolerating API string values."""
    if not isinstance(start, datetime):
        return fallback
    try:
        return format_duration(start, end if isinstance(end, datetime) else None)
    except (AttributeError, TypeError, ValueError):
        return fallback


def _status(row: Any) -> str:
    """Return a normalized status suitable for visible drawer text."""
    value = str(run_status(row) or "").lower()
    return "unknown" if value in {"", "none"} else value


def _poll_state(row: Any) -> dict[str, Any]:
    """Describe whether a loaded run still needs automatic status polling."""
    return {"run_id": _row_value(row, "run_id"), "active": _status(row) in _POLLABLE_STATUSES}


def _poll_disabled(poll_state: Any, selected_state: str | None, opened_state: bool | None) -> bool:
    """Enable polling only for the active run currently open in the drawer."""
    return not (
        opened_state is True
        and isinstance(selected_state, str)
        and isinstance(poll_state, dict)
        and poll_state.get("run_id") == selected_state
        and poll_state.get("active") is True
    )


def _is_automatic_poll(triggered_id: str | None) -> bool:
    """Identify interval refreshes that should preserve the current logs."""
    return triggered_id == f"{PREFIX}-poll"


def _status_summary(row: Any) -> Any:
    """Render the one-line operational answer to what happened."""
    status = _status(row)
    started = _row_value(row, "started_at")
    finished = _row_value(row, "finished_at")
    if status == "success":
        message = f"Succeeded in {_duration(started, finished)}"
    elif status == "failed":
        message = f"Failed after {_duration(started, finished)}"
    elif status == "queued":
        message = f"Queued for {_duration(_row_value(row, 'requested_at'))}"
    elif status == "running":
        message = f"Running for {_duration(started)}"
    elif status == "cancelling":
        message = f"Cancelling after {_duration(started)}"
    elif status == "cancelled":
        message = (
            "Cancelled before worker start" if started is None else f"Cancelled after {_duration(started, finished)}"
        )
    elif status == "waiting":
        message = "Waiting for dependencies"
    elif status == "not_ready":
        message = "Not ready"
    elif status == "skipped":
        message = "Skipped"
    else:
        message = status.replace("_", " ").title() or "Status unavailable"
    return dmc.Alert(
        [dmc.Text(message, fw=600), dmc.Text(f"Status: {status_label(status)}")],
        title="Operational status",
        color="red" if status == "failed" else "blue" if status in {"running", "cancelling"} else "gray",
        variant="light",
        className="runbook-drawer-status",
    )


def _time_label(value: Any, *, fallback: str = "Not started") -> str:
    """Format a timeline value with a clear missing-value label."""
    return fallback if value is None or value == "" else str(value)


def _timeline(row: Any) -> Any:
    """Render a compact lifecycle timeline for all durable lifecycle states."""
    status = _status(row)
    requested = _row_value(row, "requested_at")
    started = _row_value(row, "started_at")
    finished = _row_value(row, "finished_at")
    steps: list[tuple[str, str]] = [("Queued", _time_label(requested, fallback="Not available"))]
    if started is not None:
        steps.append(("Started", _time_label(started)))
    if status in {"running", "cancelling"}:
        steps.append(("Running" if status == "running" else "Cancelling", _duration(started)))
    elif status in {"success", "failed", "cancelled", "waiting", "not_ready", "skipped"}:
        terminal = "Finished" if status == "success" else status.replace("_", " ").title()
        steps.append((terminal, _time_label(finished, fallback="Not available")))
    return _metadata_group("Lifecycle", [(label, dmc.Text(value, size="sm")) for label, value in steps])


def _failure_summary(row: Any, result: dict[str, Any]) -> Any | None:
    """Put the persisted failure reason before the lower-priority log console."""
    if _status(row) != "failed":
        return None
    reason = _row_value(row, "reason") or result.get("reason")
    return dmc.Alert(
        [dmc.Text(_not_available(reason, "No failure reason recorded"), fw=600)],
        title="Failure",
        color="red",
        variant="light",
    )


def _historical_range(row: Any) -> str:
    """Format the immutable requested range for the historical summary."""
    start = _row_value(row, "start_date") or "Not available"
    end = _row_value(row, "end_date") or "Not available"
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
    return str(_row_value(row, "reason") or "No failure reason recorded")


def _historical_summary(row: Any, result: dict[str, Any]) -> Any | None:
    """Render a prominent completion or failure summary before diagnostic logs."""
    status = str(_row_value(row, "status") or "").lower()
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
                dmc.Text(f"Source: {_not_available(_row_value(row, 'target_id'))}"),
                dmc.Text(f"Range: {_historical_range(row)}"),
            ],
            title="Historical source run failed",
            color="red",
            variant="light",
        )
    return None


def _historical_inputs(row: Any, config: Any | None = None) -> Any:
    """Render the immutable historical request and its provenance."""
    return _metadata_group(
        "Inputs & provenance",
        [
            ("Source", _text(_row_value(row, "target_id"))),
            ("Run ID", _copy(_row_value(row, "run_id"), label="run ID")),
            ("Mode", _text("Historical")),
            ("Date range", _text(_historical_range(row))),
            ("Base source revision", _text(_row_value(row, "config_revision"))),
            ("Config hash", _copy(_row_value(row, "config_hash"), label="config hash")),
            ("Overrides", _text("No overrides")),
            ("Pointer update", _text("No")),
            ("Trigger", _text(_row_value(row, "trigger"))),
            ("Requested", _text(_row_value(row, "requested_at"))),
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
                _human_name(dataset_id),
                [
                    ("Dataset ID", _copy(dataset_id, label="dataset ID")),
                    ("Manifest", _copy(stored_manifest_ref, label=f"{dataset_id} manifest", max_length=32)),
                    ("Watermark", _text(metadata.get("watermark"))),
                    ("Published at", _text(metadata.get("published_at"))),
                ],
            )
        )
    if not dataset_groups:
        dataset_groups.append(dmc.Text("No artifacts", c="dimmed", size="sm"))
    return dmc.Card(
        [dmc.Text("Outputs", fw=600, size="sm", mb=4), dmc.Stack(dataset_groups, gap="xs")],
        withBorder=True,
        padding="xs",
        radius="sm",
    )


def _source_execution(row: Any, config: Any | None, result: dict[str, Any]) -> Any:
    """Render source-specific mode, adapter, range, and pointer behavior."""
    payload = _config_payload(config)
    raw_datasets = payload.get("datasets")
    datasets: dict[str, Any] = raw_datasets if isinstance(raw_datasets, dict) else {}
    parsers = [
        f"{alias}: {_not_available(binding.get('parser_id'))}"
        for alias, binding in datasets.items()
        if isinstance(binding, dict)
    ]
    status = _status(row)
    mode = str(_row_value(row, "mode") or "normal").lower()
    pointer_updates = result.get("pointer_updates")
    if mode == "historical":
        pointer_state = "No"
    elif status in {"queued", "running", "cancelling"}:
        pointer_state = "Not started"
    elif isinstance(pointer_updates, list):
        pointer_state = "Yes" if pointer_updates else "No"
    else:
        pointer_state = "Not available"
    return _metadata_group(
        "Execution",
        [
            ("Source", _text(_human_name(_row_value(row, "target_id")))),
            ("Mode", _text(_mode_label(row))),
            ("Origin", _text(_row_value(row, "trigger"))),
            ("Range", _text(_historical_range(row) if mode == "historical" else "Not applicable")),
            ("Base revision", _text(_row_value(row, "config_revision"))),
            ("Overrides", _text("No overrides")),
            ("Adapter", _text(payload.get("adapter"))),
            ("Parser", _text(", ".join(parsers) if parsers else None)),
            ("Pointer update", _text(pointer_state)),
        ],
    )


def _source_outputs(result: dict[str, Any]) -> Any:
    """Render structured source dataset and manifest outputs."""
    datasets = result.get("datasets")
    groups: list[Any] = []
    if isinstance(datasets, dict):
        for dataset_id, manifest_ref in datasets.items():
            if manifest_ref in (None, ""):
                continue
            groups.append(
                _metadata_group(
                    _human_name(dataset_id),
                    [
                        ("Dataset ID", _copy(dataset_id, label="dataset ID")),
                        ("Manifest", _copy(manifest_ref, label=f"{dataset_id} manifest", max_length=32)),
                    ],
                )
            )
    if not groups:
        groups.append(dmc.Text("No artifacts", c="dimmed", size="sm"))
    return dmc.Card(
        [dmc.Text("Outputs", fw=600, size="sm", mb=4), dmc.Stack(groups, gap="xs")],
        withBorder=True,
        padding="xs",
        radius="sm",
    )


def _snapshot_payload(row: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Return the pinned snapshot from the run or persisted report result."""
    snapshot = _row_value(row, "snapshot_payload")
    if isinstance(snapshot, dict):
        return snapshot
    snapshot = result.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _report_execution(row: Any, config: Any | None, result: dict[str, Any]) -> Any:
    """Render report-specific identity, dependencies, and barrier state."""
    payload = _config_payload(config)
    snapshot = _snapshot_payload(row, result)
    configured = payload.get("datasets") if isinstance(payload.get("datasets"), dict) else {}
    datasets = snapshot.get("datasets") if isinstance(snapshot.get("datasets"), dict) else configured
    manual = str(_row_value(row, "trigger") or "").lower() == "manual"
    barrier = "Manual — automatic barrier bypassed" if manual else "Automatic"
    return _metadata_group(
        "Execution",
        [
            ("Profile", _text(_config_title(row, config))),
            ("Report", _text(payload.get("report_id") or result.get("report_id"))),
            ("Mode", _text(_mode_label(row))),
            ("Snapshot", _copy(_row_value(row, "snapshot_id") or snapshot.get("snapshot_id"), label="snapshot ID")),
            ("Dependencies", _text(f"{len(datasets)} datasets" if datasets else None)),
            ("Barrier", _text(barrier)),
        ],
    )


def _barrier_warning(row: Any, result: dict[str, Any]) -> Any | None:
    """Highlight warnings persisted by a manual dependency-barrier bypass."""
    if str(_row_value(row, "trigger") or "").lower() != "manual":
        return None
    snapshot = _snapshot_payload(row, result)
    warnings = snapshot.get("warnings")
    if not isinstance(warnings, (list, tuple)):
        warnings = []
    warning_text = [str(item) for item in warnings if item not in (None, "")]
    if not warning_text:
        warning_text = ["Automatic dependency barrier bypassed by manual profile run."]
    return dmc.Alert(
        [dmc.Text(item) for item in warning_text],
        title="Automatic dependency barrier bypassed",
        color="yellow",
        variant="light",
    )


def _report_outputs(row: Any, result: dict[str, Any]) -> Any:
    """Render report artifact references and calculation cache information."""
    if not any(
        result.get(field) or _row_value(row, field) for field in ("artifact_id", "html_ref", "stage3_ref", "stage4_ref")
    ):
        return _metadata_group("Outputs & artifacts", [("Artifacts", dmc.Text("No artifacts", c="dimmed", size="sm"))])
    values: list[tuple[str, Any]] = []
    for field, label in (
        ("artifact_id", "Artifact ID"),
        ("html_ref", "HTML"),
        ("stage3_ref", "Stage 3 manifest"),
        ("stage4_ref", "Stage 4 manifest"),
    ):
        value = result.get(field) or _row_value(row, field)
        values.append((label, _copy(value, label=label.lower())))
    cache_hits = result.get("cache_hits")
    if isinstance(cache_hits, dict):
        cached = sum(bool(value) for value in cache_hits.values())
        values.append(("Cache", _text(f"{cached} of {len(cache_hits)} calculations cached")))
    return _metadata_group("Outputs & artifacts", values)


def _provenance(row: Any, result: dict[str, Any]) -> Any:
    """Render pinned configuration, snapshot, producer, and worker provenance."""
    snapshot = _snapshot_payload(row, result)
    datasets = snapshot.get("datasets")
    producers = snapshot.get("producer_provenance") or snapshot.get("provenance")
    if isinstance(producers, (list, tuple)):
        source_runs = [
            str(item.get("source_run_id")) for item in producers if isinstance(item, dict) and item.get("source_run_id")
        ]
    else:
        source_runs = []
    producer_ids = [
        str(item.get("producer_id")) for item in producers or () if isinstance(item, dict) and item.get("producer_id")
    ]
    manifest_refs = [
        _copy(ref, label=f"{alias} manifest", max_length=32)
        for alias, ref in (datasets.items() if isinstance(datasets, dict) else ())
        if ref not in (None, "")
    ]
    return _metadata_group(
        "Inputs & provenance",
        [
            ("Run ID", _copy(_row_value(row, "run_id"), label="run ID")),
            ("Config revision", _text(_row_value(row, "config_revision"))),
            ("Config hash", _copy(_row_value(row, "config_hash"), label="config hash")),
            ("Snapshot ID", _copy(_row_value(row, "snapshot_id") or snapshot.get("snapshot_id"), label="snapshot ID")),
            ("Dataset IDs", _text(", ".join(str(key) for key in datasets) if isinstance(datasets, dict) else None)),
            ("Dataset manifests", dmc.Stack(manifest_refs, gap=2) if manifest_refs else _text(None)),
            ("Producers", _text(", ".join(producer_ids) if producer_ids else None)),
            ("Source run IDs", _text(", ".join(source_runs) if source_runs else None)),
            ("Context hash", _copy(_row_value(row, "context_hash"), label="context hash")),
            ("Code version", _copy(_row_value(row, "code_version"), label="code version")),
            ("Log reference", _copy(result.get("log_ref"), label="log reference", max_length=32)),
            ("Worker", _copy(_row_value(row, "worker_id"), label="worker ID")),
            ("Submitted", _text(_row_value(row, "requested_at"))),
        ],
    )


def _raw_details(row: Any) -> Any:
    """Keep only uncommon row metadata in the collapsed technical section."""
    metadata = {
        label: _row_value(row, field)
        for field, label in (
            ("identity_key", "identity key"),
            ("force", "force"),
            ("dependencies_released_at", "dependencies released at"),
            ("cancel_requested_at", "cancel requested at"),
        )
        if _row_value(row, field) not in (None, "", {}, [])
    }
    details = json.dumps(metadata, default=str, indent=2, sort_keys=True) if metadata else "No additional details"
    return dmc.Accordion(
        [
            dmc.AccordionItem(
                [
                    dmc.AccordionControl("Raw details"),
                    dmc.AccordionPanel(html.Pre(details, className="runbook-drawer-raw")),
                ],
                value="raw-details",
            )
        ],
        multiple=False,
    )


def _details(row: Any, config: Any | None) -> Any:
    """Build the progressive-disclosure details pane for one run."""
    result = _row_value(row, "result")
    if not isinstance(result, dict):
        result = {}
    sections: list[Any] = [_status_summary(row), _timeline(row)]
    failure = _failure_summary(row, result)
    if failure is not None:
        sections.append(failure)

    historical = str(_row_value(row, "mode") or "normal").lower() == "historical"
    if _row_value(row, "kind") == "source":
        sections.append(_source_execution(row, config, result))
        if historical:
            summary = _historical_summary(row, result)
            if summary is not None:
                sections.append(summary)
            sections.append(_historical_inputs(row, config))
            sections.append(_historical_outputs(result))
        else:
            sections.append(_provenance(row, result))
            sections.append(_source_outputs(result))
    else:
        sections.append(_report_execution(row, config, result))
        warning = _barrier_warning(row, result)
        if warning is not None:
            sections.append(warning)
        sections.append(_provenance(row, result))
        sections.append(_report_outputs(row, result))
    sections.append(_raw_details(row))
    return dmc.Stack(sections, gap="xs", className="runbook-drawer-details-sections")


def _header(row: Any, config: Any | None) -> Any:
    """Render human identity and explicit status in the drawer title area."""
    return dmc.Group(
        [
            dmc.Stack(
                [
                    dmc.Text(_config_title(row, config), fw=700, size="lg"),
                    dmc.Text(
                        f"{_run_type(row)} · {_mode_label(row)}",
                        size="sm",
                        c="dimmed",
                        className="runbook-mode-label",
                    ),
                ],
                gap=0,
            ),
            status_badge(run_status(row)),
        ],
        justify="space-between",
        align="start",
        wrap="nowrap",
        className="runbook-drawer-header",
    )


def drawer() -> Any:
    """Build the mounted right-side drawer and its independent panes."""
    return dmc.Drawer(
        id=PREFIX,
        className="runbook-drawer",
        opened=False,
        title=html.Div(id=f"{PREFIX}-title"),
        position="right",
        size="50vw",
        withCloseButton=True,
        closeButtonProps={"aria-label": "Close run inspection"},
        closeOnClickOutside=False,
        closeOnEscape=True,
        children=[
            dcc.Store(id=f"{PREFIX}-selected"),
            dcc.Store(id=_POLL_STATE_INPUT),
            dcc.Interval(id=f"{PREFIX}-poll", interval=_POLL_INTERVAL_MS, n_intervals=0, disabled=True),
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            dmc.Text("Run inspection", fw=600),
                            dmc.Button(
                                "Cancel run",
                                id=f"{PREFIX}-cancel",
                                size="xs",
                                color="red",
                                variant="light",
                                disabled=True,
                                style={"display": "none"},
                                className="runbook-button runbook-button--danger",
                            ),
                        ],
                        justify="space-between",
                        className="runbook-drawer-action-row",
                    ),
                    html.Div(
                        dcc.Loading(
                            id=f"{PREFIX}-details-loading",
                            display="hide",
                            type="dot",
                            children=html.Div(id=f"{PREFIX}-details", className="runbook-drawer-details-content"),
                        ),
                        className="runbook-drawer-details",
                    ),
                    dmc.Accordion(
                        [
                            dmc.AccordionItem(
                                [
                                    dmc.AccordionControl("Logs"),
                                    dmc.AccordionPanel(
                                        dmc.Stack(
                                            [
                                                dmc.Group(
                                                    [
                                                        dmc.Button(
                                                            "Refresh logs",
                                                            id=f"{PREFIX}-log-refresh",
                                                            size="xs",
                                                            variant="light",
                                                            className="runbook-button",
                                                        ),
                                                        dcc.Clipboard(
                                                            id=f"{PREFIX}-copy",
                                                            title="Copy all logs",
                                                            className="runbook-copy",
                                                        ),
                                                    ],
                                                    justify="flex-end",
                                                ),
                                                html.Div(id=f"{PREFIX}-log-status", className="runbook-muted"),
                                                html.Pre(
                                                    "No logs available",
                                                    id=f"{PREFIX}-logs",
                                                    className="runbook-drawer-logs",
                                                ),
                                            ],
                                            gap="xs",
                                        )
                                    ),
                                ],
                                value="logs",
                            )
                        ],
                        multiple=False,
                        className="runbook-drawer-log-section",
                    ),
                    html.Div(id=f"{PREFIX}-cancel-result", className="runbook-muted"),
                ],
                gap="xs",
                className="runbook-drawer-stack",
            ),
        ],
    )


def _aware_slot(value: datetime) -> datetime:
    """Normalize a run slot for immutable log addressing."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _read_logs(row: Any, config: Any | None, data_store: str) -> tuple[str, str]:
    """Read the immutable log tail and describe its terminal state."""
    if not data_store:
        return "", "No logs available"
    slot = _row_value(row, "slot")
    if not isinstance(slot, datetime):
        return "", "No logs available"
    identity = RunLogIdentity(
        run_id=_row_value(row, "run_id"),
        kind=_row_value(row, "kind"),
        target_id=_row_value(row, "target_id"),
        slot=_aware_slot(slot),
        report_id=(
            _config_payload(config).get("report_id") if config and _row_value(row, "kind") == "profile" else None
        ),
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
    elif _row_value(row, "status") in {"queued", "running"}:
        state = "active; refresh manually"
    elif text:
        state = "incomplete"
    else:
        state = "No logs available"
    return text, f"{state} · {len(text.encode('utf-8'))} bytes" if text else state


def _shell_selection(
    triggered_id: str | None,
    events: tuple[dict[str, Any] | None, ...],
    selected_state: str | None,
    opened_state: bool | None,
    poll_state: Any = None,
) -> tuple[Any, Any, Any, Any]:
    """Synchronously resolve drawer opening, closing, and stable selection."""
    if triggered_id in _ROW_INPUTS:
        run_id = _run_id_for_trigger(triggered_id, events, selected_state)
        return (True, run_id, "show", True) if run_id else (no_update, no_update, no_update, no_update)
    if triggered_id == _LOCATION_INPUT:
        # The initial location event has no selection and must not flash or
        # rewrite the drawer. Once selected, any page navigation clears it.
        return (False, None, "hide", True) if selected_state else (no_update, no_update, no_update, no_update)
    if triggered_id == PREFIX and opened_state is False and selected_state:
        # Native close/Escape changes Drawer.opened without changing the Store.
        return no_update, None, "hide", True
    if triggered_id == _POLL_STATE_INPUT:
        return no_update, no_update, no_update, _poll_disabled(poll_state, selected_state, opened_state)
    return no_update, no_update, no_update, no_update


def _closed_content() -> tuple[Any, ...]:
    """Return content values that clear details after navigation or close."""
    return (
        "Run inspection",
        empty_state("No run selected", "Select a run from an operational table."),
        "",
        "No logs available",
        "",
        True,
        {"display": "none"},
        "",
        "hide",
        None,
    )


def register(dash_app: Any, sessions: Any, data_store: str) -> None:
    """Register synchronous shell selection and asynchronous run content callbacks."""
    inputs = [Input(component, "cellClicked", allow_optional=True) for component in _ROW_INPUTS]

    @dash_app.callback(
        Output(PREFIX, "opened"),
        Output(f"{PREFIX}-selected", "data"),
        Output(f"{PREFIX}-details-loading", "display", allow_duplicate=True),
        Output(f"{PREFIX}-poll", "disabled"),
        *inputs,
        Input(_LOCATION_INPUT, "pathname"),
        Input(PREFIX, "opened"),
        Input(_POLL_STATE_INPUT, "data"),
        State(f"{PREFIX}-selected", "data"),
        prevent_initial_call=True,
    )
    def select_run(*args: Any):
        """Open on a valid grid click and synchronously clear on navigation or close."""
        count = len(_ROW_INPUTS)
        events = args[:count]
        pathname = args[count]
        opened_state = args[count + 1]
        poll_state = args[count + 2]
        selected_state = args[count + 3]
        del pathname
        return _shell_selection(ctx.triggered_id, events, selected_state, opened_state, poll_state)

    @dash_app.callback(
        Output(f"{PREFIX}-title", "children"),
        Output(f"{PREFIX}-details", "children"),
        Output(f"{PREFIX}-logs", "children"),
        Output(f"{PREFIX}-log-status", "children"),
        Output(f"{PREFIX}-copy", "content"),
        Output(f"{PREFIX}-cancel", "disabled"),
        Output(f"{PREFIX}-cancel", "style"),
        Output(f"{PREFIX}-cancel-result", "children"),
        Output(f"{PREFIX}-details-loading", "display"),
        Output(_POLL_STATE_INPUT, "data"),
        Input(f"{PREFIX}-selected", "data"),
        Input(f"{PREFIX}-poll", "n_intervals"),
        Input(_LOCATION_INPUT, "pathname"),
        Input(PREFIX, "opened"),
        Input(f"{PREFIX}-log-refresh", "n_clicks"),
        Input(f"{PREFIX}-cancel", "n_clicks"),
    )
    async def inspect(*args: Any):
        """Refresh selected content without opening or changing shell selection."""
        selected_state = args[0]
        pathname = args[2]
        opened_state = args[3]
        cancel_clicks = args[5]
        selected = selected_state if isinstance(selected_state, str) else None

        if ctx.triggered_id == _LOCATION_INPUT:
            return _closed_content() if selected else (no_update,) * 10
        if not selected:
            return _closed_content() if ctx.triggered_id in {f"{PREFIX}-selected", PREFIX} else (no_update,) * 10
        if opened_state is False:
            return _closed_content()
        del pathname
        run_id = selected
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
            return _closed_content()

        if _is_automatic_poll(ctx.triggered_id):
            log_values = (no_update, no_update, no_update)
        else:
            logs, log_status = await _read_logs(row, config, data_store)
            log_values = (logs or "No logs available", log_status, logs)
        status = _status(row)
        can_cancel = status in {"queued", "running"} and _row_value(row, "cancel_requested_at") is None
        return (
            _header(row, config),
            _details(row, config),
            *log_values,
            not can_cancel,
            {"display": "inline-flex"} if can_cancel else {"display": "none"},
            message,
            "hide",
            _poll_state(row),
        )


__all__ = [
    "PREFIX",
    "_ROW_INPUTS",
    "_details",
    "_historical_failure_reason",
    "_historical_outputs",
    "_header",
    "_run_id_from_click",
    "_run_id_for_trigger",
    "_poll_disabled",
    "_is_automatic_poll",
    "_poll_state",
    "_shell_selection",
    "_status_summary",
    "_timeline",
    "drawer",
    "register",
]
