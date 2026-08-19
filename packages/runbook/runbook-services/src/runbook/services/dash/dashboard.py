from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import dash_ag_grid as dag
from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository


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


def _run_link(run_id: str) -> str:
    """Return a markdown link to a run detail page."""
    return f"[{run_id}](/ui/runs/{run_id})"


def _active_row(row: Any, now: datetime) -> dict[str, Any]:
    """Serialize an active run for AG Grid."""
    return {
        "run_id": row.run_id,
        "run_link": _run_link(row.run_id),
        "kind": row.kind,
        "target_id": row.target_id,
        "status": row.status,
        "elapsed": _elapsed(row, now),
        "slot": _text(row.slot),
        "trigger": row.trigger,
    }


def _attention_row(row: Any) -> dict[str, Any]:
    """Serialize a failed, waiting, or not-ready run for AG Grid."""
    return {
        "run_id": row.run_id,
        "run_link": _run_link(row.run_id),
        "kind": row.kind,
        "target_id": row.target_id,
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
        "run_link": _run_link(run_id),
    }


def _stat_card(label: str, component_id: str, *, note: str | None = None) -> html.Div:
    """Build one compact dashboard status card."""
    children: list[Any] = [
        html.Small(label, style={"opacity": 0.7}),
        html.Div(
            id=component_id,
            children="—",
            className="runbook-stat-value",
            style={"fontSize": "28px", "fontWeight": 600, "lineHeight": "1.2"},
        ),
    ]
    if note:
        children.append(html.Small(note, style={"opacity": 0.55}))
    return html.Div(
        children,
        className="runbook-card",
        style={
            "minWidth": "150px",
            "padding": "14px 16px",
            "border": "1px solid #ddd",
            "borderRadius": "8px",
        },
    )


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
        "field": "run_link",
        "headerName": "Run",
        "cellRenderer": "markdown",
        "minWidth": 200,
        "pinned": "left",
    },
    {"field": "kind", "headerName": "Kind", "width": 105},
    {"field": "target_id", "headerName": "Target", "minWidth": 190, "flex": 1},
    {
        "field": "status",
        "headerName": "Status",
        "width": 120,
        "cellStyle": _STATUS_STYLE,
    },
    {"field": "elapsed", "headerName": "Elapsed", "width": 120},
    {"field": "slot", "headerName": "Slot (UTC)", "minWidth": 210},
    {"field": "trigger", "headerName": "Trigger", "width": 120},
]

ATTENTION_COLUMNS = [
    {
        "field": "run_link",
        "headerName": "Run",
        "cellRenderer": "markdown",
        "minWidth": 200,
        "pinned": "left",
    },
    {"field": "kind", "headerName": "Kind", "width": 105},
    {"field": "target_id", "headerName": "Target", "minWidth": 190},
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
        "field": "run_link",
        "headerName": "Originating run",
        "cellRenderer": "markdown",
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
        "rowSelection": "single",
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
        Input(f"{prefix}-refresh", "n_intervals"),
    )
    async def refresh(_interval: int):
        """Refresh bounded dashboard summaries and live grid rows."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

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

        waiting = (
            window_counts.get("waiting", 0)
            + window_counts.get("not_ready", 0)
        )

        return (
            str(active_counts.get("queued", 0)),
            str(active_counts.get("running", 0)),
            str(window_counts.get("success", 0)),
            str(window_counts.get("failed", 0)),
            str(waiting),
            [_active_row(row, now) for row in active],
            [_attention_row(row) for row in attention],
            [_pointer_row(pointer) for pointer in pointers],
            f"Updated {_text(now)} · refreshes every {REFRESH_MS // 1000}s",
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
                    ],
                    style={"marginBottom": "26px"},
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H3(
                                    "Needs attention",
                                    style={"marginBottom": "3px"},
                                ),
                                html.Div(
                                    "Failed, waiting and not-ready operations from the previous 24 hours.",
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
                    ]
                ),
            ]
        ),
    )


def _aware(value: datetime) -> datetime:
    """Normalize database timestamps to timezone-aware UTC."""
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


__all__ = ["register"]
