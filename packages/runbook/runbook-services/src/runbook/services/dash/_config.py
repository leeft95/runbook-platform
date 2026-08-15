from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import dash_ag_grid as dag
from dash import Input, Output, State, ctx, dcc, html, register_page

from ..repository import AsyncRunRepository


def _config_row(row: Any, kind: str) -> dict[str, Any]:
    """Serialize one configuration row for AG Grid."""
    key = f"{kind}_id"
    return {
        "config_id": row.config_id,
        "revision": row.revision,
        "config_hash": row.config_hash,
        "config": json.dumps({key: row.config_id, **row.payload}, sort_keys=True),
    }


def _config_skeleton(kind: str) -> dict[str, Any]:
    """Return the smallest editable source or profile configuration."""
    common = {
        f"{kind}_id": "",
        "enabled": False,
        "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
    }
    if kind == "source":
        return {
            **common,
            "adapter": "",
            "datasets": {
                "dataset_alias": {
                    "dataset_id": "",
                    "schema_version": "v1",
                    "partition_keys": [],
                    "parser_id": "",
                    "update_mode": "append",
                }
            },
            "params": {},
        }
    return {
        **common,
        "report_id": "",
        "title": "",
        "datasets": {"dataset_alias": ""},
        "params": {},
        "layout": {},
        "extensions": {},
    }


def register_config_page(
    dash_app: Any,
    sessions: Any,
    *,
    module: str,
    kind: str,
    path: str,
    name: str,
    order: int,
) -> None:
    """Register one source or profile page and its callbacks."""
    prefix = f"runbook-ui-{kind}s"
    register_page(
        module,
        path=path,
        name=name,
        order=order,
        layout=html.Div(
            [
                html.H2(name),
                html.Div(id=f"{prefix}-summary"),
                dcc.Interval(id=f"{prefix}-refresh", interval=5000, n_intervals=0),
                dag.AgGrid(
                    id=f"{prefix}-grid",
                    rowData=[],
                    columnDefs=[
                        {"field": "config_id", "headerName": name[:-1]},
                        {"field": "revision"},
                        {"field": "config_hash"},
                        {"field": "config"},
                    ],
                    dashGridOptions={"pagination": True},
                    style={"height": "260px", "width": "100%"},
                ),
                html.H2("Edit configuration"),
                dcc.Dropdown(id=f"{prefix}-config-id", options=[], placeholder=f"{kind} id", style={"width": "300px"}),
                dcc.Dropdown(id=f"{prefix}-revision", options=[], placeholder="revision", style={"width": "130px"}),
                html.Button("Load", id=f"{prefix}-load"),
                html.Button(f"New {kind}", id=f"{prefix}-new"),
                html.Button("Save", id=f"{prefix}-save"),
                dcc.Textarea(id=f"{prefix}-json", style={"width": "100%", "height": "220px"}),
                html.Div(id=f"{prefix}-edit-result"),
                html.H2("Trigger run"),
                dcc.Dropdown(id=f"{prefix}-trigger-id", options=[], placeholder=f"{kind} id", style={"width": "300px"}),
                html.Button("Trigger", id=f"{prefix}-trigger"),
                html.Div(id=f"{prefix}-trigger-result"),
            ]
        ),
    )

    @dash_app.callback(
        Output(f"{prefix}-grid", "rowData"),
        Output(f"{prefix}-summary", "children"),
        Output(f"{prefix}-config-id", "options"),
        Output(f"{prefix}-trigger-id", "options"),
        Input(f"{prefix}-refresh", "n_intervals"),
    )
    async def refresh(_interval: int):
        """Refresh the configuration grid and summary."""
        async with sessions() as session:
            rows = await AsyncRunRepository(session).list_latest_configs(kind)
        options = [{"label": row.config_id, "value": row.config_id} for row in rows]
        return [_config_row(row, kind) for row in rows], f"{len(rows)} {kind}s", options, options

    @dash_app.callback(
        Output(f"{prefix}-revision", "options"),
        Output(f"{prefix}-revision", "value"),
        Input(f"{prefix}-config-id", "value"),
        prevent_initial_call=True,
    )
    async def refresh_revisions(config_id: str | None):
        """Refresh revision choices for the selected configuration."""
        if not config_id:
            return [], None
        async with sessions() as session:
            rows = await AsyncRunRepository(session).list_config_revisions(kind, config_id)
        options = [{"label": f"Rev {row.revision}", "value": row.revision} for row in rows]
        return options, rows[0].revision if rows else None

    @dash_app.callback(
        Output(f"{prefix}-json", "value"),
        Input(f"{prefix}-load", "n_clicks"),
        Input(f"{prefix}-new", "n_clicks"),
        State(f"{prefix}-config-id", "value"),
        State(f"{prefix}-revision", "value"),
        prevent_initial_call=True,
    )
    async def load_config(_load_clicks: int, _new_clicks: int, config_id: str, revision: int | None):
        """Load an existing configuration or start from an empty skeleton."""
        if ctx.triggered_id == f"{prefix}-new":
            return json.dumps(_config_skeleton(kind), indent=2)
        async with sessions() as session:
            row = (
                await AsyncRunRepository(session).get_config(kind, config_id, revision)
                if revision is not None
                else await AsyncRunRepository(session).latest_config(kind, config_id)
            )
        if row is None:
            return json.dumps({"error": "unknown configuration"}, indent=2)
        return json.dumps({f"{kind}_id": row.config_id, **row.payload}, indent=2, sort_keys=True)

    @dash_app.callback(
        Output(f"{prefix}-edit-result", "children"),
        Input(f"{prefix}-save", "n_clicks"),
        State(f"{prefix}-config-id", "value"),
        State(f"{prefix}-revision", "value"),
        State(f"{prefix}-json", "value"),
        prevent_initial_call=True,
    )
    async def save_config(_clicks: int, config_id: str, revision: int | None, raw: str):
        """Validate and save the JSON editor payload."""
        try:
            payload = json.loads(raw)
            payload_id = payload.get(f"{kind}_id")
            if not isinstance(payload_id, str) or not payload_id:
                raise ValueError(f"{kind}_id is required")
            expected_revision = revision if config_id == payload_id else None
            async with sessions() as session:
                async with session.begin():
                    row = await AsyncRunRepository(session).save_config(kind, payload_id, payload, expected_revision)
            return f"Saved {kind} {payload_id} revision {row.revision}"
        except Exception as exc:  # UI displays validation/conflict details.
            return f"Save failed: {exc}"

    @dash_app.callback(
        Output(f"{prefix}-trigger-result", "children"),
        Input(f"{prefix}-trigger", "n_clicks"),
        State(f"{prefix}-trigger-id", "value"),
        prevent_initial_call=True,
    )
    async def trigger(_clicks: int, config_id: str):
        """Queue a manual run for the selected configuration."""
        from datetime import timezone

        async with sessions() as session:
            repository = AsyncRunRepository(session)
            async with session.begin():
                config = await repository.latest_config(kind, config_id)
                if config is None:
                    return "Trigger failed: unknown configuration"
                run = await repository.queue_run(
                    kind=kind,
                    target_id=config_id,
                    slot=datetime.now(timezone.utc).replace(second=0, microsecond=0),
                    trigger="manual",
                    force=False,
                    config=config,
                )
        return f"Queued {run.run_id}"
