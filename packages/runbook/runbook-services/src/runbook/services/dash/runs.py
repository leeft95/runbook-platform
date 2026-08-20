from __future__ import annotations

from datetime import datetime
from typing import Any

import dash_ag_grid as dag
from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository


def _run_row(row: Any) -> dict[str, Any]:
    """Serialize one run row for AG Grid."""
    result: dict[str, Any] = {}
    for name in (
        "run_id",
        "kind",
        "target_id",
        "status",
        "worker_id",
        "cancel_requested_at",
        "slot",
        "trigger",
        "reason",
        "snapshot_id",
        "context_hash",
        "code_version",
        "artifact_id",
    ):
        value = getattr(row, name, None)
        result[name] = value.isoformat() if isinstance(value, datetime) else value
    result["run_link"] = f"[{result['run_id']}](/ui/runs/{result['run_id']})"
    result["cancelling"] = result["status"] == "running" and result["cancel_requested_at"] is not None
    return result


def _cancel_state(row: Any | None) -> tuple[bool, str]:
    """Return button state from the durable row, never from UI-only state."""
    if row is None:
        return True, "Select a queued or running run to cancel."
    if row.status not in {"queued", "running"}:
        return True, f"Run is already {row.status}."
    if row.cancel_requested_at is not None:
        return True, "Cancellation requested."
    return False, ""


def register(dash_app: Any, sessions: Any) -> None:
    """Register the Runs page and its callbacks."""
    prefix = "runbook-ui-runs"
    register_page(
        __name__,
        path="/runs",
        name="Runs",
        order=2,
        layout=html.Div(
            [
                html.H2("Runs"),
                html.Div(id=f"{prefix}-summary"),
                dcc.Interval(id=f"{prefix}-refresh", interval=5000, n_intervals=0),
                dcc.Dropdown(
                    id=f"{prefix}-kind",
                    options=[{"label": value.title(), "value": value} for value in ("source", "profile")],
                    placeholder="kind",
                    clearable=True,
                    style={
                        "width": "180px",
                        "display": "inline-block",
                        "marginRight": "8px",
                    },
                ),
                dcc.Dropdown(
                    id=f"{prefix}-status",
                    options=[
                        {"label": value.replace("_", " ").title(), "value": value}
                        for value in (
                            "queued",
                            "running",
                            "cancelling",
                            "cancelled",
                            "success",
                            "failed",
                            "waiting",
                            "not_ready",
                            "skipped",
                        )
                    ],
                    placeholder="status",
                    clearable=True,
                    style={
                        "width": "180px",
                        "display": "inline-block",
                        "marginRight": "8px",
                    },
                ),
                dcc.Input(
                    id=f"{prefix}-target",
                    placeholder="target id",
                    type="text",
                    style={"width": "180px"},
                ),
                html.Button("Cancel", id=f"{prefix}-cancel", disabled=True),
                html.Span(id=f"{prefix}-cancel-result"),
                dag.AgGrid(
                    id=f"{prefix}-grid",
                    rowData=[],
                    columnDefs=[
                        {
                            "field": "run_link",
                            "headerName": "Run ID",
                            "cellRenderer": "markdown",
                            "filter": "agTextColumnFilter",
                        },
                        *[
                            {"field": field, "filter": True}
                            for field in (
                                "kind",
                                "target_id",
                                "status",
                                "worker_id",
                                "cancelling",
                                "cancel_requested_at",
                                "slot",
                                "trigger",
                                "reason",
                                "snapshot_id",
                                "context_hash",
                                "code_version",
                                "artifact_id",
                            )
                        ],
                    ],
                    dashGridOptions={"pagination": True},
                    style={"height": "360px", "width": "100%"},
                ),
            ]
        ),
    )

    @dash_app.callback(
        Output(f"{prefix}-grid", "rowData"),
        Output(f"{prefix}-summary", "children"),
        Input(f"{prefix}-refresh", "n_intervals"),
        Input(f"{prefix}-kind", "value"),
        Input(f"{prefix}-status", "value"),
        Input(f"{prefix}-target", "value"),
    )
    async def refresh(_interval: int, kind: str | None, status: str | None, target_id: str | None):
        """Refresh the recent-runs grid and summary."""
        async with sessions() as session:
            rows = await AsyncRunRepository(session).list_runs(
                kind=kind,
                status="running" if status == "cancelling" else status,
                target_id=target_id or None,
                limit=100,
            )
        if status == "cancelling":
            rows = [row for row in rows if row.cancel_requested_at is not None]
        return [_run_row(row) for row in rows], f"{len(rows)} recent runs"

    @dash_app.callback(
        Output(f"{prefix}-cancel", "disabled"),
        Output(f"{prefix}-cancel-result", "children"),
        Input(f"{prefix}-refresh", "n_intervals"),
        Input(f"{prefix}-cancel", "n_clicks"),
        Input(f"{prefix}-grid", "selectedRows"),
    )
    async def cancel(_interval: int, n_clicks: int | None, selected_rows: list[dict[str, Any]] | None):
        """Request cancellation from the database-backed selected run."""
        run_id = selected_rows[0].get("run_id") if selected_rows else None
        if not isinstance(run_id, str):
            return _cancel_state(None)
        async with sessions() as session:
            repository = AsyncRunRepository(session)
            if n_clicks:
                async with session.begin():
                    await repository.request_cancel(run_id)
            row = await repository.get_run(run_id)
        return _cancel_state(row)
