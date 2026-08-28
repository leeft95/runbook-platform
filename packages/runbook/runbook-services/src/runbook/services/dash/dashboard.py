from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository
from .operations import empty_state, error_state

REFRESH_MS = 5_000
ACTIVE_LIMIT = 250
ATTENTION_LIMIT = 100
POINTER_LIMIT = 250


def _text(value: Any) -> str:
    """Render a dashboard scalar without exposing Python ``None``."""
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    return "" if value is None else str(value)


def _elapsed(row: Any, now: datetime) -> str:
    """Return elapsed wall time for an active run."""
    started = row.started_at or row.requested_at
    elapsed = max(timedelta(0), now - _aware(started))
    return str(elapsed).split(".", 1)[0]


def _terminal_time(row: Any) -> str:
    """Render the terminal operation time as an explicit UTC timestamp."""
    value = row.finished_at or getattr(row, "updated_at", None) or row.requested_at
    return _text(_aware(value))


def _active_row(row: Any, now: datetime) -> dict[str, Any]:
    """Serialize an active run for AG Grid."""
    return {
        "run_id": row.run_id,
        "kind": row.kind,
        "target_id": row.target_id,
        "mode": getattr(row, "mode", None) or "normal",
        "start_date": _text(getattr(row, "start_date", None)),
        "end_date": _text(getattr(row, "end_date", None)),
        "config_revision": getattr(row, "config_revision", None),
        "status": row.status,
        "worker_id": getattr(row, "worker_id", None),
        "cancelling": row.status == "running" and getattr(row, "cancel_requested_at", None) is not None,
        "elapsed": _elapsed(row, now),
        "slot": _text(row.slot),
        "trigger": row.trigger,
    }


def _attention_row(row: Any) -> dict[str, Any]:
    """Serialize a failed, waiting, or not-ready run for AG Grid."""
    return {
        "run_id": row.run_id,
        "kind": row.kind,
        "target_id": row.target_id,
        "mode": getattr(row, "mode", None) or "normal",
        "start_date": _text(getattr(row, "start_date", None)),
        "end_date": _text(getattr(row, "end_date", None)),
        "config_revision": getattr(row, "config_revision", None),
        "status": row.status,
        "finished_at": _terminal_time(row),
        "reason": row.reason or "—",
    }


def _pointer_row(pointer: dict[str, Any]) -> dict[str, Any]:
    """Serialize a current dataset pointer for AG Grid."""
    run_id = str(pointer["source_run_id"])
    return {
        "dataset_id": pointer["dataset_id"],
        "source_id": pointer["source_id"],
        "watermark": _text(pointer["watermark"]),
        "published_at": _text(pointer["published_at"]),
        "run_id": run_id,
    }


def _stat_card(label: str, component_id: str, *, note: str | None = None) -> html.Div:
    """Build one compact dashboard status card."""
    children: list[Any] = [dmc.Text(label, size="sm", c="dimmed"), dmc.Title(id=component_id, children="—", order=3)]
    if note:
        children.append(dmc.Text(note, size="xs", c="dimmed"))
    return dmc.Card(children, withBorder=True, padding="sm", radius="sm", className="runbook-metric")


_STATUS_STYLE = {
    "styleConditions": [
        {
            "condition": "params.value === 'failed'",
            "style": {"fontWeight": "600"},
        },
        {
            "condition": "params.value === 'running'",
            "style": {"fontWeight": "600"},
        },
        {
            "condition": "params.value === 'waiting' || params.value === 'not_ready'",
            "style": {"fontWeight": "600"},
        },
    ]
}


ACTIVE_COLUMNS = [
    {
        "field": "run_id",
        "headerName": "Run",
        "minWidth": 200,
        "pinned": "left",
    },
    {"field": "kind", "headerName": "Kind", "width": 105},
    {"field": "target_id", "headerName": "Target", "minWidth": 190, "flex": 1},
    {"field": "mode", "headerName": "Mode", "width": 110},
    {"field": "start_date", "headerName": "Start date", "width": 125},
    {"field": "end_date", "headerName": "End date", "width": 125},
    {"field": "config_revision", "headerName": "Base revision", "width": 120},
    {
        "field": "status",
        "headerName": "Status",
        "width": 120,
        "cellStyle": _STATUS_STYLE,
    },
    {"field": "worker_id", "headerName": "Worker", "minWidth": 160},
    {"field": "cancelling", "headerName": "Cancelling", "width": 110},
    {"field": "elapsed", "headerName": "Elapsed", "width": 120},
    {"field": "slot", "headerName": "Slot (UTC)", "minWidth": 210},
    {"field": "trigger", "headerName": "Trigger", "width": 120},
]

ATTENTION_COLUMNS = [
    {
        "field": "run_id",
        "headerName": "Run",
        "minWidth": 200,
        "pinned": "left",
    },
    {"field": "kind", "headerName": "Kind", "width": 105},
    {"field": "target_id", "headerName": "Target", "minWidth": 190},
    {"field": "mode", "headerName": "Mode", "width": 110},
    {"field": "start_date", "headerName": "Start date", "width": 125},
    {"field": "end_date", "headerName": "End date", "width": 125},
    {"field": "config_revision", "headerName": "Base revision", "width": 120},
    {
        "field": "status",
        "headerName": "Status",
        "width": 120,
        "cellStyle": _STATUS_STYLE,
    },
    {"field": "finished_at", "headerName": "Updated (UTC)", "minWidth": 210},
    {
        "field": "reason",
        "headerName": "Reason",
        "minWidth": 300,
        "flex": 1,
        "wrapText": True,
        "autoHeight": True,
    },
]

POINTER_COLUMNS = [
    {
        "field": "dataset_id",
        "headerName": "Dataset",
        "minWidth": 240,
        "pinned": "left",
    },
    {"field": "source_id", "headerName": "Producer", "minWidth": 190},
    {"field": "watermark", "headerName": "Watermark", "minWidth": 210},
    {"field": "published_at", "headerName": "Published (UTC)", "minWidth": 210},
    {
        "field": "run_id",
        "headerName": "Originating run",
        "minWidth": 210,
    },
]


def _grid(
    component_id: str,
    columns: list[dict[str, Any]],
    *,
    height: str,
    row_id_field: str,
    pagination: bool = False,
    page_size: int = 50,
) -> dag.AgGrid:
    """Build a read-only live operations grid."""
    options: dict[str, Any] = {
        "animateRows": True,
        "getRowId": {"function": f"params.data.{row_id_field}"},
        "suppressCellFocus": False,
        "rowBuffer": 10,
    }
    if pagination:
        options.update(
            {
                "pagination": True,
                "paginationPageSize": page_size,
                "paginationPageSizeSelector": [25, 50, 100],
            }
        )
    return dag.AgGrid(
        id=component_id,
        rowData=[],
        columnDefs=columns,
        defaultColDef={
            "resizable": True,
            "sortable": True,
            "filter": True,
        },
        dashGridOptions=options,
        style={"height": height, "width": "100%"},
    )


def register(dash_app: Any, sessions: Any) -> None:
    """Register the live operations dashboard."""
    prefix = "runbook-ui-dashboard"

    @dash_app.callback(
        Output(f"{prefix}-queued", "children"),
        Output(f"{prefix}-running", "children"),
        Output(f"{prefix}-success", "children"),
        Output(f"{prefix}-failed", "children"),
        Output(f"{prefix}-waiting", "children"),
        Output(f"{prefix}-active-grid", "rowData"),
        Output(f"{prefix}-attention-grid", "rowData"),
        Output(f"{prefix}-pointers-grid", "rowData"),
        Output(f"{prefix}-updated", "children"),
        Output(f"{prefix}-active-empty", "children"),
        Output(f"{prefix}-attention-empty", "children"),
        Output(f"{prefix}-pointers-empty", "children"),
        Output(f"{prefix}-state", "children"),
        Input(f"{prefix}-refresh", "n_intervals"),
        Input(f"{prefix}-manual-refresh", "n_clicks"),
    )
    async def refresh(_interval: int, _clicks: int | None):
        """Refresh bounded dashboard summaries and live grid rows."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        try:
            async with sessions() as session:
                repository = AsyncRunRepository(session)

                active_counts = await repository.status_counts({"queued", "running"})
                window_counts = await repository.status_counts(
                    {"success", "failed", "waiting", "not_ready"},
                    since=cutoff,
                )
                active = await repository.list_active_runs(limit=ACTIVE_LIMIT)
                attention = await repository.list_attention_runs(
                    cutoff,
                    limit=ATTENTION_LIMIT,
                )
                pointers = await repository.list_pointers(limit=POINTER_LIMIT)
        except Exception as exc:  # pragma: no cover - driver-specific failure rendering
            message = f"Unable to refresh operations data: {exc}"
            return ("—", "—", "—", "—", "—", [], [], [], "Refresh failed", "", "", "", error_state(message))

        waiting = window_counts.get("waiting", 0) + window_counts.get("not_ready", 0)

        active_rows = [_active_row(row, now) for row in active]
        attention_rows = [_attention_row(row) for row in attention]
        pointer_rows = [_pointer_row(pointer) for pointer in pointers]
        return (
            str(active_counts.get("queued", 0)),
            str(active_counts.get("running", 0)),
            str(window_counts.get("success", 0)),
            str(window_counts.get("failed", 0)),
            str(waiting),
            active_rows,
            attention_rows,
            pointer_rows,
            f"Updated {_text(now)} · refreshes every {REFRESH_MS // 1000}s",
            "" if active_rows else empty_state("No active operations", "There are no queued or running operations."),
            ""
            if attention_rows
            else empty_state(
                "No operations need attention", "No failed, waiting, or not-ready runs were found in the last 24 hours."
            ),
            ""
            if pointer_rows
            else empty_state("No dataset pointers", "No published dataset pointers are currently available."),
            ""
            if active_rows or attention_rows or pointer_rows
            else empty_state("No current operations", "Refresh when runs or dataset pointers are available."),
        )

    register_page(
        __name__,
        path="/",
        name="Dashboard",
        order=0,
        layout=html.Div(
            [
                dcc.Interval(
                    id=f"{prefix}-refresh",
                    interval=REFRESH_MS,
                    n_intervals=0,
                ),
                html.Div(id=f"{prefix}-state"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H2("Operations", style={"marginBottom": "2px"}),
                                html.Div(
                                    "Live control-plane health and current dataset state.",
                                    style={"opacity": 0.65},
                                ),
                            ]
                        ),
                        html.Div(
                            id=f"{prefix}-updated",
                            style={"opacity": 0.55, "fontSize": "12px"},
                        ),
                        dmc.Button("Refresh", id=f"{prefix}-manual-refresh", variant="light", size="sm"),
                    ],
                    style={
                        "display": "flex",
                        "justifyContent": "space-between",
                        "alignItems": "end",
                        "gap": "20px",
                        "marginBottom": "16px",
                    },
                ),
                html.Div(
                    [
                        _stat_card("Queued", f"{prefix}-queued", note="Current"),
                        _stat_card("Running", f"{prefix}-running", note="Current"),
                        _stat_card("Succeeded", f"{prefix}-success", note="Previous 24h"),
                        _stat_card("Failed", f"{prefix}-failed", note="Previous 24h"),
                        _stat_card(
                            "Waiting / not ready",
                            f"{prefix}-waiting",
                            note="Previous 24h",
                        ),
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
                        "gap": "10px",
                        "marginBottom": "24px",
                    },
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H3("Active operations", style={"marginBottom": "3px"}),
                                html.Div(
                                    f"Newest {ACTIVE_LIMIT} queued and running operations.",
                                    style={"opacity": 0.6, "fontSize": "13px"},
                                ),
                            ],
                            style={"marginBottom": "8px"},
                        ),
                        _grid(
                            f"{prefix}-active-grid",
                            ACTIVE_COLUMNS,
                            height="330px",
                            row_id_field="run_id",
                        ),
                        html.Div(id=f"{prefix}-active-empty"),
                    ],
                    style={"marginBottom": "26px"},
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H3(
                                    "Profiles and sources requiring attention",
                                    style={"marginBottom": "3px"},
                                ),
                                html.Div(
                                    "Recent failures, waiting, and not-ready operations from the previous 24 hours.",
                                    style={"opacity": 0.6, "fontSize": "13px"},
                                ),
                            ],
                            style={"marginBottom": "8px"},
                        ),
                        _grid(
                            f"{prefix}-attention-grid",
                            ATTENTION_COLUMNS,
                            height="360px",
                            row_id_field="run_id",
                            pagination=True,
                            page_size=50,
                        ),
                        html.Div(id=f"{prefix}-attention-empty"),
                    ],
                    style={"marginBottom": "26px"},
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H3("Dataset pointers", style={"marginBottom": "3px"}),
                                html.Div(
                                    f"Current dataset state, capped at {POINTER_LIMIT} rows on the dashboard.",
                                    style={"opacity": 0.6, "fontSize": "13px"},
                                ),
                            ],
                            style={"marginBottom": "8px"},
                        ),
                        _grid(
                            f"{prefix}-pointers-grid",
                            POINTER_COLUMNS,
                            height="440px",
                            row_id_field="dataset_id",
                            pagination=True,
                            page_size=50,
                        ),
                        html.Div(id=f"{prefix}-pointers-empty"),
                    ]
                ),
            ]
        ),
    )


def _aware(value: datetime) -> datetime:
    """Normalize database timestamps to timezone-aware UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


__all__ = ["register"]
