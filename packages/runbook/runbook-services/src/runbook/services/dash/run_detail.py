from __future__ import annotations

import json
from typing import Any

from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository


def register(dash_app: Any, sessions: Any) -> None:
    """Register the dynamic run detail route."""
    prefix = "runbook-ui-run-detail"

    @dash_app.callback(
        Output(f"{prefix}-content", "children"),
        Input(f"{prefix}-location", "pathname"),
        Input(f"{prefix}-refresh", "n_intervals"),
    )
    async def detail(pathname: str | None, _interval: int):
        """Load and render one run's pinned configuration and provenance."""
        run_id = (pathname or "").rstrip("/").rsplit("/", 1)[-1]
        async with sessions() as session:
            repository = AsyncRunRepository(session)
            row = await repository.get_run(run_id)
            config = await repository.get_config(row.kind, row.target_id, row.config_revision) if row else None
            pointers = await repository.list_pointers() if row else []
        if row is None:
            return html.P("Unknown run")
        dataset_ids = set((config.payload.get("datasets") or {}).values()) if config and row.kind == "profile" else set()
        current_pointers = [pointer for pointer in pointers if (pointer["source_id"] == row.target_id if row.kind == "source" else pointer["dataset_id"] in dataset_ids)]
        payload = {name: getattr(row, name) for name in row.__table__.columns.keys()}
        payload["pinned_config"] = dict(config.payload) if config else None
        payload["provenance"] = {
            "kind": row.kind,
            "target_id": row.target_id,
            "snapshot_id": row.snapshot_id,
            "context_hash": row.context_hash,
            "code_version": row.code_version,
            "result": row.result,
            "current_pointers": current_pointers,
        }
        return [
            html.Div(["Status: ", html.Span(row.status, className="runbook-status")]),
            html.Div(f"Requested: {row.requested_at}"),
            html.Div(f"Started: {row.started_at or '—'}"),
            html.Div(f"Finished: {row.finished_at or '—'}"),
            html.Div(f"Reason: {row.reason or '—'}"),
            html.A(
                "Open diagnostic logs",
                href=f"/ui/runs/{row.run_id}/logs",
            ),
            html.H3("Pinned configuration and provenance"),
            html.Pre(json.dumps(payload, default=str, indent=2, sort_keys=True)),
        ]

    register_page(
        __name__,
        path_template="/runs/<run_id>",
        name="Run detail",
        order=4,
        hide_nav=True,
        layout=html.Div(
            [
                dcc.Location(id=f"{prefix}-location"),
                dcc.Interval(id=f"{prefix}-refresh", interval=5000, n_intervals=0),
                html.H2("Run detail"),
                html.Div(id=f"{prefix}-content"),
            ]
        ),
    )


__all__ = ["register"]
