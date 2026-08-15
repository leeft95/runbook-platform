from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import dash_ag_grid as dag
from dash import Input, Output, State, dcc, html, register_page

from ..repository import AsyncRunRepository


def _run_row(row: Any) -> dict[str, Any]:
    """Serialize one run row for AG Grid."""
    result: dict[str, Any] = {}
    for name in (
        "run_id",
        "kind",
        "target_id",
        "status",
        "slot",
        "trigger",
        "reason",
        "snapshot_id",
        "context_hash",
        "code_version",
        "artifact_id",
    ):
        value = getattr(row, name)
        result[name] = value.isoformat() if isinstance(value, datetime) else value
    return result


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
                dag.AgGrid(
                    id=f"{prefix}-grid",
                    rowData=[],
                    columnDefs=[
                        {"field": "run_id"},
                        {"field": "kind"},
                        {"field": "target_id"},
                        {"field": "status"},
                        {"field": "slot"},
                        {"field": "trigger"},
                        {"field": "reason"},
                        {"field": "snapshot_id"},
                        {"field": "context_hash"},
                        {"field": "code_version"},
                        {"field": "artifact_id"},
                    ],
                    dashGridOptions={"pagination": True},
                    style={"height": "360px", "width": "100%"},
                ),
                html.H2("Run detail and provenance"),
                dcc.Dropdown(id=f"{prefix}-run-id", options=[], placeholder="run id", style={"width": "400px"}),
                html.Button("Load run", id=f"{prefix}-load-run"),
                html.Pre(id=f"{prefix}-detail"),
            ]
        ),
    )

    @dash_app.callback(
        Output(f"{prefix}-grid", "rowData"),
        Output(f"{prefix}-summary", "children"),
        Output(f"{prefix}-run-id", "options"),
        Input(f"{prefix}-refresh", "n_intervals"),
    )
    async def refresh(_interval: int):
        """Refresh the recent-runs grid and summary."""
        async with sessions() as session:
            rows = await AsyncRunRepository(session).list_runs(limit=100)
        options = [{"label": row.run_id, "value": row.run_id} for row in rows]
        return [_run_row(row) for row in rows], f"{len(rows)} recent runs", options

    @dash_app.callback(
        Output(f"{prefix}-detail", "children"),
        Input(f"{prefix}-load-run", "n_clicks"),
        State(f"{prefix}-run-id", "value"),
        prevent_initial_call=True,
    )
    async def load_run(_clicks: int, run_id: str):
        """Load one run and its provenance fields."""
        async with sessions() as session:
            row = await AsyncRunRepository(session).get_run(run_id)
        if row is None:
            return json.dumps({"error": "unknown run"}, indent=2)
        return json.dumps(
            {name: getattr(row, name) for name in row.__table__.columns.keys()},
            default=str,
            indent=2,
            sort_keys=True,
        )
