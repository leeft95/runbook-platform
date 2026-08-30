from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, cast
from uuid import uuid4

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, ctx, dcc, html, no_update, register_page

from ..config import validate_config
from ..repository import AsyncRunRepository

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_EVERY_N_HOURS_RE = re.compile(r"^(\d+)\s+\*/(\d+)\s+\*\s+\*\s+\*$")
DEFAULT_SCHEDULE = {"cron": "0 0 * * *", "timezone": "UTC"}


@dataclass(frozen=True)
class ConfigGridSpec:
    kind: str
    title: str
    columns: list[dict[str, Any]]
    new_row: Callable[[], dict[str, Any]]
    complex_fields: dict[str, str]


def _source_new_row() -> dict[str, Any]:
    """Return a new unsaved source row for the configuration grid."""
    return {
        "_row_key": f"draft:{uuid4().hex}",
        "_new": True,
        "_status": "draft",
        "_original_config_id": None,
        "config_id": "",
        "enabled": False,
        "adapter": "",
        "schedule": dict(DEFAULT_SCHEDULE),
        "datasets": {},
        "params": {},
        "revision": None,
        "config_hash": None,
        "created_at": None,
    }


def _profile_new_row() -> dict[str, Any]:
    """Return a new unsaved profile row for the configuration grid."""
    return {
        "_row_key": f"draft:{uuid4().hex}",
        "_new": True,
        "_status": "draft",
        "_original_config_id": None,
        "config_id": "",
        "enabled": False,
        "report_id": "",
        "title": "",
        "datasets": {},
        "params": {},
        "layout": {},
        "extensions": {},
        "revision": None,
        "config_hash": None,
        "created_at": None,
    }


SOURCE_COLUMNS = [
    {
        "field": "config_id",
        "headerName": "Source ID",
        "editable": {"function": "params.data._new === true"},
        "minWidth": 190,
        "pinned": "left",
    },
    {"field": "enabled", "headerName": "Enabled", "editable": True, "cellEditor": "agCheckboxCellEditor", "width": 105},
    {
        "field": "adapter",
        "headerName": "Adapter",
        "editable": True,
        "cellEditor": "agSelectCellEditor",
        "cellEditorParams": {"values": ["bloomberg", "http", "local_file"]},
        "minWidth": 150,
    },
    {
        "field": "schedule",
        "headerName": "Schedule",
        "editable": False,
        "valueFormatter": {"function": "scheduleSummary(params.value)"},
        "minWidth": 190,
    },
    {
        "field": "datasets",
        "headerName": "Datasets",
        "editable": False,
        "valueFormatter": {"function": "mappingSummary(params.value)"},
        "minWidth": 140,
    },
    {
        "field": "params",
        "headerName": "Params",
        "editable": False,
        "valueFormatter": {"function": "jsonSummary(params.value)"},
        "minWidth": 120,
    },
    {"field": "revision", "headerName": "Rev", "editable": False, "width": 85},
    {"field": "_status", "headerName": "Status", "editable": False, "width": 110},
    {"field": "created_at", "headerName": "Created", "editable": False, "minWidth": 185},
]

PROFILE_COLUMNS = [
    {
        "field": "config_id",
        "headerName": "Profile ID",
        "editable": {"function": "params.data._new === true"},
        "minWidth": 190,
        "pinned": "left",
    },
    {"field": "enabled", "headerName": "Enabled", "editable": True, "cellEditor": "agCheckboxCellEditor", "width": 105},
    {"field": "report_id", "headerName": "Report ID", "editable": True, "minWidth": 180},
    {"field": "title", "headerName": "Title", "editable": True, "minWidth": 220},
    {
        "field": "datasets",
        "headerName": "Datasets",
        "editable": False,
        "valueFormatter": {"function": "mappingSummary(params.value)"},
        "minWidth": 140,
    },
    {
        "field": "params",
        "headerName": "Params",
        "editable": False,
        "valueFormatter": {"function": "jsonSummary(params.value)"},
        "minWidth": 120,
    },
    {
        "field": "layout",
        "headerName": "Layout",
        "editable": False,
        "valueFormatter": {"function": "jsonSummary(params.value)"},
        "minWidth": 120,
    },
    {
        "field": "extensions",
        "headerName": "Extensions",
        "editable": False,
        "valueFormatter": {"function": "jsonSummary(params.value)"},
        "minWidth": 130,
    },
    {"field": "revision", "headerName": "Rev", "editable": False, "width": 85},
    {"field": "_status", "headerName": "Status", "editable": False, "width": 110},
    {"field": "created_at", "headerName": "Created", "editable": False, "minWidth": 185},
]

SOURCE_SPEC = ConfigGridSpec(
    kind="source",
    title="Sources",
    columns=SOURCE_COLUMNS,
    new_row=_source_new_row,
    complex_fields={"schedule": "schedule", "datasets": "datasets", "params": "params"},
)
PROFILE_SPEC = ConfigGridSpec(
    kind="profile",
    title="Profiles",
    columns=PROFILE_COLUMNS,
    new_row=_profile_new_row,
    complex_fields={"datasets": "datasets", "params": "params", "layout": "layout", "extensions": "extensions"},
)


def _spec(kind: str, name: str) -> ConfigGridSpec:
    """Return the grid specification for a source or profile page."""
    base = SOURCE_SPEC if kind == "source" else PROFILE_SPEC if kind == "profile" else None
    if base is None:
        raise ValueError(f"unknown config kind: {kind!r}")
    if name == base.title:
        return base
    return ConfigGridSpec(base.kind, name, base.columns, base.new_row, base.complex_fields)


def _grid_row(row: Any, kind: str) -> dict[str, Any]:
    """Project a persisted configuration revision into an AG Grid row."""
    return {
        "_row_key": f"{kind}:{row.config_id}",
        "_new": False,
        "_status": "saved",
        "_original_config_id": row.config_id,
        "config_id": row.config_id,
        "revision": row.revision,
        "config_hash": row.config_hash,
        "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else str(row.created_at),
        **dict(row.payload),
    }


def _payload_from_row(kind: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Build json payload from ag-grid row"""
    config_id = str(row.get("config_id") or "").strip()
    if not config_id:
        raise ValueError(f"{kind}_id is required")
    if not _ID.fullmatch(config_id):
        raise ValueError(f"invalid {kind}_id: {config_id!r}")
    if kind == "source":
        payload = {
            "source_id": config_id,
            "enabled": bool(row.get("enabled")),
            "adapter": row.get("adapter") or "",
            "schedule": row.get("schedule") or dict(DEFAULT_SCHEDULE),
            "datasets": row.get("datasets") or {},
            "params": row.get("params") or {},
        }
    else:
        payload = {
            "profile_id": config_id,
            "enabled": bool(row.get("enabled")),
            "report_id": row.get("report_id") or "",
            "title": row.get("title") or "",
            "datasets": row.get("datasets") or {},
            "params": row.get("params") or {},
            "layout": row.get("layout") or {},
            "extensions": row.get("extensions") or {},
        }
    return config_id, payload


def _cron_form_values(schedule: dict[str, Any] | None) -> dict[str, Any]:
    """Build the cron schedule from the string schedule"""
    schedule = schedule or {}
    cron = str(schedule.get("cron") or DEFAULT_SCHEDULE["cron"]).strip()
    values = {
        "mode": "custom",
        "minute": 0,
        "hour": 0,
        "interval": 6,
        "dow": "1",
        "dom": 1,
        "custom": cron,
        "timezone": str(schedule.get("timezone") or "UTC"),
    }
    match = _EVERY_N_HOURS_RE.match(cron)
    if match:
        minute, interval = match.groups()
        values.update(mode="every_n_hours", minute=int(minute), interval=int(interval))
        return values
    parts = cron.split()
    if len(parts) != 5:
        return values
    minute, hour, dom, month, dow = parts
    if month != "*" or not minute.isdigit():
        return values
    minute_i = int(minute)
    if hour == "*" and dom == "*" and dow == "*":
        values.update(mode="hourly", minute=minute_i)
    elif hour.isdigit() and dom == "*" and dow == "*":
        values.update(mode="daily", minute=minute_i, hour=int(hour))
    elif hour.isdigit() and dom == "*" and dow == "1-5":
        values.update(mode="weekdays", minute=minute_i, hour=int(hour))
    elif hour.isdigit() and dom == "*" and dow in {"0", "1", "2", "3", "4", "5", "6"}:
        values.update(mode="weekly", minute=minute_i, hour=int(hour), dow=dow)
    elif hour.isdigit() and dom.isdigit() and dow == "*":
        values.update(mode="monthly", minute=minute_i, hour=int(hour), dom=int(dom))
    return values


def _build_cron(
    mode: str | None,
    minute: int | None,
    hour: int | None,
    interval: int | None,
    dow: str | None,
    dom: int | None,
    custom: str | None,
) -> str:
    """Builds the cron from the inputs to be validated then saved"""
    mode = mode or "daily"
    minute = 0 if minute is None else int(minute)
    hour = 0 if hour is None else int(hour)
    interval = 6 if interval is None else int(interval)
    dow = dow or "1"
    dom = 1 if dom is None else int(dom)
    if not 0 <= minute <= 59:
        raise ValueError("minute must be 0..59")
    if not 0 <= hour <= 23:
        raise ValueError("hour must be 0..23")
    if not 1 <= interval <= 23:
        raise ValueError("hour interval must be 1..23")
    if dow not in {"0", "1", "2", "3", "4", "5", "6"}:
        raise ValueError("day of week must be 0..6")
    if not 1 <= dom <= 31:
        raise ValueError("day of month must be 1..31")
    if mode == "hourly":
        return f"{minute} * * * *"
    if mode == "every_n_hours":
        return f"{minute} */{interval} * * *"
    if mode == "daily":
        return f"{minute} {hour} * * *"
    if mode == "weekdays":
        return f"{minute} {hour} * * 1-5"
    if mode == "weekly":
        return f"{minute} {hour} * * {dow}"
    if mode == "monthly":
        return f"{minute} {hour} {dom} * *"
    if mode == "custom":
        cron = str(custom or "").strip()
        if len(cron.split()) != 5:
            raise ValueError("custom cron must have 5 fields")
        return cron
    raise ValueError(f"unknown cron mode: {mode!r}")


def _source_dataset_rows(datasets: dict[str, Any] | None) -> list[dict[str, Any]]:
    """build row for the source dataset mapping"""
    return [
        {
            "alias": alias,
            "dataset_id": spec.get("dataset_id", ""),
            "schema_version": spec.get("schema_version", "v1"),
            "parser_id": spec.get("parser_id", ""),
            "update_mode": spec.get("update_mode", "append"),
            "partition_keys": ",".join(spec.get("partition_keys") or []),
        }
        for alias, spec in (datasets or {}).items()
    ]


def _profile_dataset_rows(datasets: dict[str, Any] | None) -> list[dict[str, Any]]:
    """build row for the profile dataset mapping"""
    return [{"alias": alias, "dataset_id": dataset_id} for alias, dataset_id in (datasets or {}).items()]


def _datasets_from_editor(kind: str, rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Build datasets from the editor inputs"""
    result: dict[str, Any] = {}
    for row in rows or []:
        alias = str(row.get("alias") or "").strip()
        dataset_id = str(row.get("dataset_id") or "").strip()
        if not alias and not dataset_id:
            continue
        if not alias:
            raise ValueError("dataset alias is required")
        if not dataset_id:
            raise ValueError(f"dataset_id is required for {alias!r}")
        if alias in result:
            raise ValueError(f"duplicate dataset alias: {alias!r}")
        if kind == "profile":
            result[alias] = dataset_id
        else:
            parser_id = str(row.get("parser_id") or "").strip()
            if not parser_id:
                raise ValueError(f"parser_id is required for {alias!r}")
            update_mode = str(row.get("update_mode") or "append")
            result[alias] = {
                "dataset_id": dataset_id,
                "schema_version": str(row.get("schema_version") or "v1"),
                "parser_id": parser_id,
                "update_mode": update_mode,
                "partition_keys": [
                    item.strip() for item in str(row.get("partition_keys") or "").split(",") if item.strip()
                ],
            }
    return result


def _source_dataset_columns() -> list[dict[str, Any]]:
    """AG-Grid column definitions for the source dataset editor table"""
    return [
        {"field": "alias", "headerName": "Alias", "editable": True, "minWidth": 150},
        {"field": "dataset_id", "headerName": "Dataset ID", "editable": True, "minWidth": 220},
        {"field": "schema_version", "headerName": "Schema", "editable": True, "width": 110},
        {"field": "parser_id", "headerName": "Parser ID", "editable": True, "minWidth": 180},
        {
            "field": "update_mode",
            "headerName": "Update",
            "editable": True,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": ["append", "full"]},
            "width": 120,
        },
        {"field": "partition_keys", "headerName": "Partition keys", "editable": True, "minWidth": 180},
    ]


def _profile_dataset_columns() -> list[dict[str, Any]]:
    """AG-Grid column definitions for the profile dataset editor table"""
    return [
        {"field": "alias", "headerName": "Alias", "editable": True, "minWidth": 220},
        {"field": "dataset_id", "headerName": "Dataset ID", "editable": True, "minWidth": 320},
    ]


def _main_grid(prefix: str, spec: ConfigGridSpec) -> dag.AgGrid:
    """Main definition for the AG-Grid"""
    return dag.AgGrid(
        id=f"{prefix}-grid",
        className="runbook-grid",
        rowData=[],
        columnDefs=spec.columns,
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={
            "singleClickEdit": True,
            "stopEditingWhenCellsLoseFocus": True,
            "rowSelection": "single",
            "getRowId": {"function": "params.data._row_key"},
        },
        style={"height": "560px", "width": "100%"},
    )


def _editor_modal(prefix: str) -> html.Div:
    """Popout modal for datasets and cron, hidden and unhidden depending on field"""
    return html.Div(
        id=f"{prefix}-editor-modal",
        style={"display": "none"},
        children=[
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(id=f"{prefix}-editor-title", style={"margin": 0}),
                            cast(Any, html.Button)(
                                "×",
                                id=f"{prefix}-editor-close",
                                n_clicks=0,
                                title="Close editor",
                                **{"aria-label": "Close editor"},
                                className="runbook-config-editor-close",
                            ),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
                        className="runbook-config-editor-header",
                    ),
                    html.Hr(),
                    html.Div(
                        id=f"{prefix}-schedule-section",
                        style={"display": "none"},
                        children=[
                            dmc.Select(
                                id=f"{prefix}-schedule-mode",
                                label="Schedule mode",
                                data=[
                                    {"label": x.replace("_", " ").title(), "value": x}
                                    for x in [
                                        "hourly",
                                        "every_n_hours",
                                        "daily",
                                        "weekdays",
                                        "weekly",
                                        "monthly",
                                        "custom",
                                    ]
                                ],
                                clearable=False,
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Minute",
                                                htmlFor=f"{prefix}-schedule-minute",
                                                className="runbook-form-label",
                                            ),
                                            dcc.Input(
                                                id=f"{prefix}-schedule-minute",
                                                type="number",
                                                min=0,
                                                max=59,
                                                style={"width": "100%"},
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Hour",
                                                htmlFor=f"{prefix}-schedule-hour",
                                                className="runbook-form-label",
                                            ),
                                            dcc.Input(
                                                id=f"{prefix}-schedule-hour",
                                                type="number",
                                                min=0,
                                                max=23,
                                                style={"width": "100%"},
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Every N hours",
                                                htmlFor=f"{prefix}-schedule-interval",
                                                className="runbook-form-label",
                                            ),
                                            dcc.Input(
                                                id=f"{prefix}-schedule-interval",
                                                type="number",
                                                min=1,
                                                max=23,
                                                style={"width": "100%"},
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            dmc.Select(
                                                id=f"{prefix}-schedule-dow",
                                                label="Day of week",
                                                data=[
                                                    {"label": n, "value": str(i)}
                                                    for i, n in enumerate(
                                                        [
                                                            "Sunday",
                                                            "Monday",
                                                            "Tuesday",
                                                            "Wednesday",
                                                            "Thursday",
                                                            "Friday",
                                                            "Saturday",
                                                        ]
                                                    )
                                                ],
                                                clearable=False,
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Day of month",
                                                htmlFor=f"{prefix}-schedule-dom",
                                                className="runbook-form-label",
                                            ),
                                            dcc.Input(
                                                id=f"{prefix}-schedule-dom",
                                                type="number",
                                                min=1,
                                                max=31,
                                                style={"width": "100%"},
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            dmc.Select(
                                                id=f"{prefix}-schedule-timezone",
                                                label="Timezone",
                                                data=[
                                                    {"label": x, "value": x}
                                                    for x in ["UTC", "Europe/London", "America/New_York", "Asia/Dubai"]
                                                ],
                                                clearable=False,
                                            ),
                                        ]
                                    ),
                                ],
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                                    "gap": "12px",
                                    "marginTop": "12px",
                                },
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Custom cron",
                                        htmlFor=f"{prefix}-schedule-custom",
                                        className="runbook-form-label",
                                    ),
                                    dcc.Input(id=f"{prefix}-schedule-custom", style={"width": "100%"}),
                                ],
                                style={"marginTop": "12px"},
                            ),
                            html.Div(
                                id=f"{prefix}-schedule-preview",
                                style={
                                    "marginTop": "12px",
                                    "padding": "10px",
                                    "border": "1px solid #ddd",
                                    "borderRadius": "6px",
                                },
                                className="runbook-config-preview",
                            ),
                        ],
                    ),
                    html.Div(
                        id=f"{prefix}-datasets-section",
                        style={"display": "none"},
                        children=[
                            dag.AgGrid(
                                id=f"{prefix}-datasets-grid",
                                className="runbook-grid",
                                rowData=[],
                                columnDefs=[],
                                defaultColDef={"resizable": True},
                                dashGridOptions={
                                    "singleClickEdit": True,
                                    "stopEditingWhenCellsLoseFocus": True,
                                    "rowSelection": "single",
                                },
                                style={"height": "320px", "width": "100%"},
                            ),
                            html.Div(
                                [
                                    html.Button("+ Add mapping", id=f"{prefix}-datasets-add", n_clicks=0),
                                    html.Button("Remove selected", id=f"{prefix}-datasets-remove", n_clicks=0),
                                ],
                                style={"display": "flex", "gap": "8px", "marginTop": "10px"},
                            ),
                        ],
                    ),
                    html.Div(
                        id=f"{prefix}-json-section",
                        style={"display": "none"},
                        children=[
                            html.Label("JSON value", htmlFor=f"{prefix}-json-editor", className="runbook-form-label"),
                            dcc.Textarea(
                                id=f"{prefix}-json-editor",
                                style={"width": "100%", "height": "320px", "fontFamily": "monospace"},
                            ),
                        ],
                    ),
                    html.Div(
                        id=f"{prefix}-editor-error",
                        style={"marginTop": "10px", "minHeight": "24px"},
                        className="runbook-config-editor-error",
                    ),
                    html.Div(
                        [
                            html.Button("Cancel", id=f"{prefix}-editor-cancel", n_clicks=0, className="runbook-button"),
                            html.Button(
                                "Apply",
                                id=f"{prefix}-editor-apply",
                                n_clicks=0,
                                className="runbook-button runbook-button--primary",
                            ),
                        ],
                        style={"display": "flex", "justifyContent": "flex-end", "gap": "8px", "marginTop": "16px"},
                        className="runbook-form-actions",
                    ),
                ],
                style={
                    "width": "min(900px, 96vw)",
                    "maxHeight": "88vh",
                    "overflowY": "auto",
                    "background": "white",
                    "borderRadius": "10px",
                    "padding": "18px",
                    "boxShadow": "0 14px 40px rgba(0,0,0,.22)",
                },
                className="runbook-panel runbook-config-editor",
            )
        ],
    )


def _page_layout(prefix: str, spec: ConfigGridSpec) -> html.Div:
    """Main page layout"""
    profile_run = spec.kind == "profile"
    return html.Div(
        [
            dcc.Store(id=f"{prefix}-editor-context"),
            dcc.ConfirmDialog(
                id=f"{prefix}-run-confirm",
                message="Run the latest pinned snapshot? This manually bypasses the automatic dependency barrier.",
            )
            if profile_run
            else None,
            html.H2(spec.title, className="runbook-panel-title"),
            html.Div(
                [
                    html.Button(f"+ New {spec.kind}", id=f"{prefix}-new", n_clicks=0, className="runbook-button"),
                    html.Button(
                        "Validate",
                        id=f"{prefix}-validate",
                        n_clicks=0,
                        className="runbook-button runbook-button--secondary",
                    ),
                    html.Button(
                        "Save", id=f"{prefix}-save", n_clicks=0, className="runbook-button runbook-button--primary"
                    ),
                    html.Button(
                        "Run latest snapshot (manual)",
                        id=f"{prefix}-run",
                        n_clicks=0,
                        title="Requires confirmation and bypasses the automatic dependency barrier.",
                        className="runbook-button runbook-button--primary",
                    )
                    if profile_run
                    else html.Button(
                        "Run selected",
                        id=f"{prefix}-run",
                        n_clicks=0,
                        className="runbook-button runbook-button--primary",
                    ),
                    html.Button(
                        "Disable", id=f"{prefix}-disable", n_clicks=0, className="runbook-button runbook-button--danger"
                    ),
                    html.Button("Refresh", id=f"{prefix}-refresh", n_clicks=0, className="runbook-button"),
                ],
                style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "12px"},
                className="runbook-form-actions",
            ),
            html.Div(
                "Edit scalar cells directly. Click Schedule, Datasets, Params, Layout or Extensions to open an editor.",
                style={"marginBottom": "10px", "opacity": 0.75},
            ),
            _main_grid(prefix, spec),
            html.Div(id=f"{prefix}-result", style={"marginTop": "12px", "minHeight": "28px"}),
            _editor_modal(prefix),
        ],
        className="runbook-panel runbook-config-section",
    )


def _modal_style(open_: bool) -> dict[str, Any]:
    """sets the modal styling depending on if the modal is opened"""
    if not open_:
        return {"display": "none"}
    return {
        "display": "flex",
        "position": "fixed",
        "inset": "0",
        "zIndex": 2000,
        "background": "rgba(0, 0, 0, 0.38)",
        "alignItems": "center",
        "justifyContent": "center",
        "padding": "24px",
    }


async def _latest_grid_rows(sessions: Any, kind: str) -> list[dict[str, Any]]:
    """Builds rows for the ag-grid using the db table"""
    async with sessions() as session:
        rows = await AsyncRunRepository(session).list_latest_configs(kind)
    return [_grid_row(row, kind) for row in rows]


def _current_selected_row(
    row_data: list[dict[str, Any]] | None, selected_rows: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """Determines what row is selected from the list of selected rows"""
    if not selected_rows:
        return None
    key = selected_rows[0].get("_row_key")
    return next((row for row in row_data or [] if row.get("_row_key") == key), selected_rows[0])


def register_config_page(
    dash_app: Any,
    sessions: Any,
    *,
    module: str,
    kind: str,
    path: str,
    name: str,
    order: int,
    page_layout: Any | None = None,
) -> None:
    """Register a generic database-backed config grid. Existing sources.py/profiles.py work unchanged."""
    spec = _spec(kind, name)
    prefix = f"runbook-ui-{kind}s"
    register_page(module, path=path, name=name, order=order, layout=page_layout or _page_layout(prefix, spec))

    if kind == "profile":

        @dash_app.callback(
            Output(f"{prefix}-run-confirm", "displayed"),
            Input(f"{prefix}-run", "n_clicks"),
            prevent_initial_call=True,
        )
        def confirm_profile_run(_n_clicks):
            return True

    run_trigger = f"{prefix}-run-confirm" if kind == "profile" else f"{prefix}-run"
    run_input = run_trigger

    @dash_app.callback(
        Output(f"{prefix}-grid", "rowData"),
        Output(f"{prefix}-result", "children"),
        Input(f"{prefix}-refresh", "n_clicks"),
        Input(f"{prefix}-new", "n_clicks"),
        Input(f"{prefix}-validate", "n_clicks"),
        Input(f"{prefix}-save", "n_clicks"),
        Input(run_input, "submit_n_clicks" if kind == "profile" else "n_clicks"),
        Input(f"{prefix}-disable", "n_clicks"),
        State(f"{prefix}-grid", "rowData"),
        State(f"{prefix}-grid", "selectedRows"),
        prevent_initial_call=False,
    )
    async def grid_actions(_refresh, _new, _validate, _save, _run, _disable, row_data, selected_rows):
        """Modifies grid depending on what button is clicked"""
        triggered = ctx.triggered_id
        if triggered == f"{prefix}-new":
            return [spec.new_row(), *(row_data or [])], f"New {kind} draft added."

        if triggered == f"{prefix}-validate":
            selected = _current_selected_row(row_data, selected_rows)
            if selected is None:
                return no_update, "Select a row first."
            try:
                config_id, payload = _payload_from_row(kind, selected)
                validate_config(kind, config_id, payload)
                return no_update, f"{kind.title()} {config_id} is valid."
            except Exception as exc:
                return no_update, f"Validation failed: {exc}"

        if triggered == f"{prefix}-save":
            selected = _current_selected_row(row_data, selected_rows)
            if selected is None:
                return no_update, "Select a row first."
            try:
                config_id, payload = _payload_from_row(kind, selected)
                validate_config(kind, config_id, payload)
                expected_revision = (
                    selected.get("revision")
                    if selected.get("_original_config_id") == config_id and not selected.get("_new")
                    else None
                )
                async with sessions() as session:
                    repository = AsyncRunRepository(session)
                    async with session.begin():
                        saved = await repository.save_config(kind, config_id, payload, expected_revision)
                rows = await _latest_grid_rows(sessions, kind)
                return rows, f"Saved {kind} {config_id} revision {saved.revision}."
            except Exception as exc:
                return no_update, f"Save failed: {exc}"

        if triggered == f"{prefix}-disable":
            selected = _current_selected_row(row_data, selected_rows)
            if selected is None:
                return no_update, "Select a row first."
            if selected.get("_new"):
                rows = [row for row in (row_data or []) if row.get("_row_key") != selected.get("_row_key")]
                return rows, f"Removed unsaved {kind} draft."
            try:
                config_id, payload = _payload_from_row(kind, selected)
                if not payload.get("enabled", False):
                    return no_update, f"{kind.title()} {config_id} is already disabled."
                payload["enabled"] = False
                async with sessions() as session:
                    repository = AsyncRunRepository(session)
                    async with session.begin():
                        saved = await repository.save_config(
                            kind,
                            config_id,
                            payload,
                            selected.get("revision"),
                        )
                rows = await _latest_grid_rows(sessions, kind)
                return rows, f"Disabled {kind} {config_id} at revision {saved.revision}."
            except Exception as exc:
                return no_update, f"Disable failed: {exc}"

        if triggered == run_trigger:
            selected = _current_selected_row(row_data, selected_rows)
            if selected is None or selected.get("_new"):
                return no_update, "Select a saved row first."
            config_id = str(selected.get("config_id") or "").strip()
            try:
                async with sessions() as session:
                    repository = AsyncRunRepository(session)
                    async with session.begin():
                        config = await repository.latest_config(kind, config_id)
                        if config is None:
                            raise ValueError("configuration no longer exists")
                        run = await repository.queue_run(
                            kind=kind,
                            target_id=config_id,
                            slot=datetime.now(timezone.utc).replace(second=0, microsecond=0),
                            trigger="manual",
                            force=False,
                            config=config,
                        )
                return no_update, f"Queued {run.run_id}."
            except Exception as exc:
                return no_update, f"Run failed: {exc}"

        rows = await _latest_grid_rows(sessions, kind)
        return rows, f"{len(rows)} {kind}s loaded."

    @dash_app.callback(
        Output(f"{prefix}-editor-context", "data"),
        Output(f"{prefix}-editor-modal", "style"),
        Output(f"{prefix}-editor-title", "children"),
        Output(f"{prefix}-schedule-section", "style"),
        Output(f"{prefix}-datasets-section", "style"),
        Output(f"{prefix}-json-section", "style"),
        Output(f"{prefix}-schedule-mode", "value"),
        Output(f"{prefix}-schedule-minute", "value"),
        Output(f"{prefix}-schedule-hour", "value"),
        Output(f"{prefix}-schedule-interval", "value"),
        Output(f"{prefix}-schedule-dow", "value"),
        Output(f"{prefix}-schedule-dom", "value"),
        Output(f"{prefix}-schedule-custom", "value"),
        Output(f"{prefix}-schedule-timezone", "value"),
        Output(f"{prefix}-datasets-grid", "columnDefs"),
        Output(f"{prefix}-datasets-grid", "rowData"),
        Output(f"{prefix}-json-editor", "value"),
        Output(f"{prefix}-editor-error", "children"),
        Input(f"{prefix}-grid", "cellClicked"),
        State(f"{prefix}-grid", "rowData"),
        prevent_initial_call=True,
    )
    def open_editor(cell, row_data):
        """Opens the editor modal depending on which cell is clicked"""
        if not cell or cell.get("colId") not in spec.complex_fields:
            return (no_update,) * 18
        field = spec.complex_fields[cell["colId"]]
        row_index = cell.get("rowIndex")
        if row_index is None or row_index < 0 or row_index >= len(row_data or []):
            return (no_update,) * 18
        row = (row_data or [])[row_index]
        context = {"row_key": row.get("_row_key"), "field": field, "kind": kind}
        cron = _cron_form_values(row.get("schedule"))
        if field == "datasets":
            columns = _source_dataset_columns() if kind == "source" else _profile_dataset_columns()
            dataset_rows = (
                _source_dataset_rows(row.get("datasets"))
                if kind == "source"
                else _profile_dataset_rows(row.get("datasets"))
            )
        else:
            columns, dataset_rows = [], []
        json_value = (
            json.dumps(row.get(field) or {}, indent=2, sort_keys=True)
            if field in {"params", "layout", "extensions"}
            else "{}"
        )
        titles = {
            "schedule": "Edit schedule",
            "datasets": "Edit dataset mappings",
            "params": "Edit params",
            "layout": "Edit layout",
            "extensions": "Edit extensions",
        }
        return (
            context,
            _modal_style(True),
            titles[field],
            {"display": "block"} if field == "schedule" else {"display": "none"},
            {"display": "block"} if field == "datasets" else {"display": "none"},
            {"display": "block"} if field in {"params", "layout", "extensions"} else {"display": "none"},
            cron["mode"],
            cron["minute"],
            cron["hour"],
            cron["interval"],
            cron["dow"],
            cron["dom"],
            cron["custom"],
            cron["timezone"],
            columns,
            dataset_rows,
            json_value,
            "",
        )

    dash_app.clientside_callback(
        ClientsideFunction(namespace="runbookConfig", function_name="cronPreview"),
        Output(f"{prefix}-schedule-preview", "children"),
        Input(f"{prefix}-schedule-mode", "value"),
        Input(f"{prefix}-schedule-minute", "value"),
        Input(f"{prefix}-schedule-hour", "value"),
        Input(f"{prefix}-schedule-interval", "value"),
        Input(f"{prefix}-schedule-dow", "value"),
        Input(f"{prefix}-schedule-dom", "value"),
        Input(f"{prefix}-schedule-custom", "value"),
        Input(f"{prefix}-schedule-timezone", "value"),
    )

    @dash_app.callback(
        Output(f"{prefix}-datasets-grid", "rowData", allow_duplicate=True),
        Input(f"{prefix}-datasets-add", "n_clicks"),
        Input(f"{prefix}-datasets-remove", "n_clicks"),
        State(f"{prefix}-datasets-grid", "rowData"),
        State(f"{prefix}-datasets-grid", "selectedRows"),
        State(f"{prefix}-editor-context", "data"),
        prevent_initial_call=True,
    )
    def edit_dataset_mappings(_add, _remove, rows, selected, editor_context):
        """Updates the state of the dataset mappings for the modal"""
        rows = list(rows or [])
        if ctx.triggered_id == f"{prefix}-datasets-add":
            rows.append(
                {
                    "alias": "",
                    "dataset_id": "",
                    "schema_version": "v1",
                    "parser_id": "",
                    "update_mode": "append",
                    "partition_keys": "",
                }
                if (editor_context or {}).get("kind") == "source"
                else {"alias": "", "dataset_id": ""}
            )
            return rows
        if ctx.triggered_id == f"{prefix}-datasets-remove" and selected:
            target = selected[0]
            removed = False
            result = []
            for row in rows:
                if not removed and row == target:
                    removed = True
                    continue
                result.append(row)
            return result
        return no_update

    @dash_app.callback(
        Output(f"{prefix}-editor-modal", "style", allow_duplicate=True),
        Output(f"{prefix}-grid", "rowData", allow_duplicate=True),
        Output(f"{prefix}-editor-error", "children", allow_duplicate=True),
        Input(f"{prefix}-editor-apply", "n_clicks"),
        Input(f"{prefix}-editor-cancel", "n_clicks"),
        Input(f"{prefix}-editor-close", "n_clicks"),
        State(f"{prefix}-editor-context", "data"),
        State(f"{prefix}-grid", "rowData"),
        State(f"{prefix}-schedule-mode", "value"),
        State(f"{prefix}-schedule-minute", "value"),
        State(f"{prefix}-schedule-hour", "value"),
        State(f"{prefix}-schedule-interval", "value"),
        State(f"{prefix}-schedule-dow", "value"),
        State(f"{prefix}-schedule-dom", "value"),
        State(f"{prefix}-schedule-custom", "value"),
        State(f"{prefix}-schedule-timezone", "value"),
        State(f"{prefix}-datasets-grid", "rowData"),
        State(f"{prefix}-json-editor", "value"),
        prevent_initial_call=True,
    )
    def apply_or_close_editor(
        _apply,
        _cancel,
        _close,
        editor_context,
        rows,
        mode,
        minute,
        hour,
        interval,
        dow,
        dom,
        custom,
        tz,
        dataset_rows,
        json_text,
    ):
        """Save operations for the editor modal"""
        if ctx.triggered_id in {f"{prefix}-editor-cancel", f"{prefix}-editor-close"}:
            return _modal_style(False), no_update, ""
        if not editor_context:
            return no_update, no_update, "No editor context."
        try:
            updated_rows = [dict(row) for row in (rows or [])]
            target = next((row for row in updated_rows if row.get("_row_key") == editor_context.get("row_key")), None)
            if target is None:
                raise ValueError("configuration row is no longer available")
            field = editor_context["field"]
            if field == "schedule":
                schedule = {
                    "cron": _build_cron(mode, minute, hour, interval, dow, dom, custom),
                    "timezone": tz or "UTC",
                }
                target["schedule"] = schedule
            elif field == "datasets":
                datasets = _datasets_from_editor(kind, dataset_rows)
                target["datasets"] = datasets
            elif field in {"params", "layout", "extensions"}:
                value = json.loads(json_text or "{}")
                if not isinstance(value, dict):
                    raise ValueError(f"{field} must be a JSON object")
                target[field] = value
            else:
                raise ValueError(f"unsupported field: {field!r}")
            target["_status"] = "draft" if target.get("_new") else "modified"
            return _modal_style(False), updated_rows, ""
        except Exception as exc:
            return no_update, no_update, f"Apply failed: {exc}"
