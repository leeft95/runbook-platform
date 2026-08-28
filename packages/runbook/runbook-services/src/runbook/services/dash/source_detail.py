"""Source operational drill-down page."""

from __future__ import annotations

from datetime import date
from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update, register_page

from ..repository import AsyncRunRepository
from .operations import (
    copy_value,
    detail_row,
    empty_state,
    error_state,
    exact_time,
    profile_source_ids,
    relative_time,
    run_status,
    status_badge,
    status_label,
)

PREFIX = "runbook-ui-source-detail"


def _grid(component_id: str, columns: list[dict[str, Any]], height: str = "300px") -> dag.AgGrid:
    """Build one dense source-detail AG Grid."""
    grid_options: dict[str, Any] = {"pagination": True, "paginationPageSize": 25, "rowSelection": "single"}
    if component_id == f"{PREFIX}-runs-grid":
        grid_options["getRowId"] = {"function": "params.data.run_id"}
    return dag.AgGrid(
        id=component_id,
        rowData=[],
        columnDefs=columns,
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions=grid_options,
        style={"height": height, "width": "100%"},
    )


def layout() -> Any:
    """Build the source operational drill-down page."""
    return dcc.Loading(
        id=f"{PREFIX}-loading",
        type="default",
        children=html.Div(
            [
                dcc.Location(id=f"{PREFIX}-location"),
                dcc.Interval(id=f"{PREFIX}-refresh", interval=30_000, n_intervals=0),
                html.Div(id=f"{PREFIX}-error"),
                dmc.Breadcrumbs(
                    [dmc.Anchor("Sources", href="/ui/sources"), dmc.Text(id=f"{PREFIX}-breadcrumb")],
                    mb="xs",
                ),
                dmc.Group(
                    [
                        dmc.Stack(
                            [dmc.Title(id=f"{PREFIX}-title", order=2), dmc.Text(id=f"{PREFIX}-subtitle", c="dimmed")],
                            gap=0,
                        ),
                        dmc.Group(
                            [
                                dmc.Anchor("Configuration", href="/ui/sources#runbook-ui-sources-config", size="sm"),
                                dmc.Button("Run historical job", id=f"{PREFIX}-historical-open", size="sm"),
                                dmc.Button("Refresh", id=f"{PREFIX}-manual-refresh", variant="light", size="sm"),
                            ],
                            gap="xs",
                        ),
                    ],
                    justify="space-between",
                    align="flex-end",
                    mb="md",
                ),
                dmc.SimpleGrid(id=f"{PREFIX}-metrics", cols={"base": 1, "sm": 2, "lg": 4}, spacing="sm", mb="md"),
                dmc.Card(
                    [
                        dmc.Title("Outputs and current pointers", order=4),
                        dmc.Text(
                            "Configured datasets and the latest durable watermark state.",
                            size="sm",
                            c="dimmed",
                            mb="xs",
                        ),
                        html.Div(id=f"{PREFIX}-outputs"),
                    ],
                    withBorder=True,
                    padding="md",
                    mb="md",
                ),
                dmc.Card(
                    [
                        dmc.Title("Used by profiles", order=4),
                        dmc.Text(
                            "Derived by matching current profile dataset bindings.", size="sm", c="dimmed", mb="xs"
                        ),
                        html.Div(id=f"{PREFIX}-profiles"),
                    ],
                    withBorder=True,
                    padding="md",
                    mb="md",
                ),
                dmc.Card(
                    [
                        dmc.Title("Run history", order=4),
                        dmc.Text("Select a run to inspect details and immutable logs.", size="sm", c="dimmed", mb="xs"),
                        _grid(
                            f"{PREFIX}-runs-grid",
                            [
                                {"field": "run_id", "headerName": "Run ID", "pinned": "left"},
                                {"field": "status_text", "headerName": "Status"},
                                {"field": "mode", "headerName": "Mode"},
                                {"field": "start_date", "headerName": "Start date"},
                                {"field": "end_date", "headerName": "End date"},
                                {"field": "config_revision", "headerName": "Base revision"},
                                {"field": "slot", "headerName": "Slot"},
                                {"field": "duration", "headerName": "Duration"},
                                {"field": "trigger", "headerName": "Trigger"},
                                {"field": "reason", "headerName": "Outcome"},
                            ],
                            height="360px",
                        ),
                        html.Div(id=f"{PREFIX}-runs-empty"),
                    ],
                    withBorder=True,
                    padding="md",
                ),
                dcc.Store(id=f"{PREFIX}-historical-request"),
                dmc.Modal(
                    id=f"{PREFIX}-historical-modal",
                    title="Historical source run",
                    opened=False,
                    children=[
                        html.Div(
                            [
                                dmc.Text(id=f"{PREFIX}-historical-source", size="sm"),
                                dmc.TextInput(
                                    id=f"{PREFIX}-historical-start-date",
                                    inputProps={"type": "date"},
                                    label="Start date (inclusive)",
                                    required=True,
                                    style={"width": "100%"},
                                ),
                                dmc.TextInput(
                                    id=f"{PREFIX}-historical-end-date",
                                    inputProps={"type": "date"},
                                    label="End date (inclusive)",
                                    required=True,
                                    style={"width": "100%"},
                                ),
                                html.Div(id=f"{PREFIX}-historical-feedback"),
                                dmc.Group(
                                    [
                                        dmc.Button("Cancel", id=f"{PREFIX}-historical-cancel", variant="subtle"),
                                        dmc.Button("Review", id=f"{PREFIX}-historical-review"),
                                    ],
                                    justify="flex-end",
                                    mt="sm",
                                ),
                            ],
                            id=f"{PREFIX}-historical-form",
                        ),
                        html.Div(id=f"{PREFIX}-historical-review-panel", style={"display": "none"}),
                    ],
                ),
            ],
            className="runbook-detail-page",
        ),
    )


def _source_id(pathname: str | None) -> str | None:
    """Extract a source ID from the browser pathname."""
    parts = [part for part in (pathname or "").split("/") if part]
    try:
        index = parts.index("sources")
    except ValueError:
        return None
    return parts[index + 1] if len(parts) > index + 1 else None


def register(dash_app: Any, sessions: Any) -> None:
    """Register source summary, output, reverse dependency, and run loading."""
    register_page(
        "runbook.operations.source_detail",
        path_template="/sources/<source_id>",
        name="Source detail",
        order=11,
        hide_nav=True,
        layout=layout(),
    )

    @dash_app.callback(
        Output(f"{PREFIX}-title", "children"),
        Output(f"{PREFIX}-subtitle", "children"),
        Output(f"{PREFIX}-breadcrumb", "children"),
        Output(f"{PREFIX}-metrics", "children"),
        Output(f"{PREFIX}-outputs", "children"),
        Output(f"{PREFIX}-profiles", "children"),
        Output(f"{PREFIX}-runs-grid", "rowData"),
        Output(f"{PREFIX}-runs-empty", "children"),
        Output(f"{PREFIX}-error", "children"),
        Input(f"{PREFIX}-location", "pathname"),
        Input(f"{PREFIX}-refresh", "n_intervals"),
        Input(f"{PREFIX}-manual-refresh", "n_clicks"),
    )
    async def refresh(pathname: str | None, _interval: int, _clicks: int | None):
        """Refresh source state, outputs, reverse dependencies, and runs."""
        source_id = _source_id(pathname)
        if not source_id:
            return (
                "Source",
                "No source selected",
                "—",
                [],
                [],
                [],
                [],
                empty_state("No runs", "Choose a source from the catalogue."),
                "",
            )
        try:
            async with sessions() as session:
                repository = AsyncRunRepository(session)
                source = await repository.latest_config("source", source_id)
                profiles = await repository.list_latest_configs("profile")
                pointers = await repository.list_pointers(limit=500)
                runs = await repository.list_runs(kind="source", target_id=source_id, limit=100)
            if source is None:
                return (
                    source_id,
                    "Unknown source",
                    source_id,
                    [],
                    empty_state("Source not found", "The configuration may have been removed."),
                    [],
                    [],
                    empty_state("No runs", "No run history is available."),
                    "",
                )
            payload = dict(source.payload)
            latest = runs[0] if runs else None
            source_pointers = [pointer for pointer in pointers if str(pointer["source_id"]) == source_id]
            watermarks = [
                pointer.get("watermark") for pointer in source_pointers if pointer.get("watermark") is not None
            ]
            watermark = max(watermarks, key=str) if watermarks else None
            metrics = [
                dmc.Card(
                    [
                        dmc.Text("Current status", size="sm", c="dimmed"),
                        status_badge(run_status(latest) if latest else "not_ready"),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
                dmc.Card(
                    [
                        dmc.Text("Adapter", size="sm", c="dimmed"),
                        dmc.Text(str(payload.get("adapter") or "—"), size="sm"),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
                dmc.Card(
                    [
                        dmc.Text("Enabled", size="sm", c="dimmed"),
                        dmc.Text("Yes" if payload.get("enabled", True) else "No", size="sm"),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
                dmc.Card(
                    [
                        dmc.Text("Latest watermark", size="sm", c="dimmed"),
                        dmc.Text(exact_time(watermark), size="sm"),
                        dmc.Text(relative_time(watermark), size="xs", c="dimmed"),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
            ]
            outputs = [
                dmc.Group(
                    [
                        dmc.Text(alias, fw=600, w=160),
                        copy_value(spec.get("dataset_id"), label="dataset"),
                        dmc.Text(
                            exact_time(
                                next(
                                    (
                                        p.get("watermark")
                                        for p in source_pointers
                                        if p.get("dataset_id") == spec.get("dataset_id")
                                    ),
                                    None,
                                )
                            ),
                            size="sm",
                            c="dimmed",
                        ),
                    ],
                    gap="sm",
                    wrap="nowrap",
                )
                for alias, spec in (payload.get("datasets") or {}).items()
                if isinstance(spec, dict)
            ]
            used_by = [
                dmc.Anchor(str(profile.config_id), href=f"/ui/profiles/{profile.config_id}")
                for profile in profiles
                if source_id in profile_source_ids(dict(profile.payload), [source])
            ]
            return (
                source_id,
                f"{payload.get('adapter') or 'source'} · revision {source.revision} · {'enabled' if payload.get('enabled', True) else 'disabled'}",
                source_id,
                metrics,
                dmc.Stack(outputs, gap="xs")
                if outputs
                else empty_state("No configured outputs", "This source has no dataset mappings."),
                dmc.Group(used_by, gap="sm")
                if used_by
                else empty_state(
                    "No dependent profiles", "No current profile configuration references this source's datasets."
                ),
                [dict(detail_row(row), status_text=status_label(run_status(row))) for row in runs],
                ""
                if runs
                else empty_state("No source runs yet", "Queue a run from configuration management when ready."),
                "",
            )
        except Exception as exc:  # pragma: no cover - driver-specific failure rendering
            return source_id, "", source_id, [], "", "", [], "", error_state(f"Unable to load source: {exc}")

    @dash_app.callback(
        Output(f"{PREFIX}-historical-modal", "opened"),
        Output(f"{PREFIX}-historical-form", "style"),
        Output(f"{PREFIX}-historical-source", "children"),
        Output(f"{PREFIX}-historical-review-panel", "children"),
        Output(f"{PREFIX}-historical-review-panel", "style"),
        Output(f"{PREFIX}-historical-feedback", "children"),
        Output(f"{PREFIX}-historical-request", "data"),
        Input(f"{PREFIX}-historical-open", "n_clicks"),
        Input(f"{PREFIX}-historical-cancel", "n_clicks"),
        Input(f"{PREFIX}-historical-review", "n_clicks"),
        Input(f"{PREFIX}-historical-back", "n_clicks", allow_optional=True),
        Input(f"{PREFIX}-historical-submit", "n_clicks", allow_optional=True),
        State(f"{PREFIX}-location", "pathname"),
        State(f"{PREFIX}-historical-start-date", "value"),
        State(f"{PREFIX}-historical-end-date", "value"),
        State(f"{PREFIX}-historical-request", "data"),
        prevent_initial_call=True,
    )
    async def historical_request(
        _open_clicks: int | None,
        _cancel_clicks: int | None,
        _review_clicks: int | None,
        _back_clicks: int | None,
        _submit_clicks: int | None,
        pathname: str | None,
        start_value: str | None,
        end_value: str | None,
        request: dict[str, Any] | None,
    ):
        """Review and submit one historical date-range request."""
        source_id = _source_id(pathname)
        triggered = ctx.triggered_id
        hidden = {"display": "none"}
        visible = {"display": "block"}
        if triggered == f"{PREFIX}-historical-open":
            return True, visible, f"Source: {source_id or '—'}", "", hidden, "", None
        if triggered == f"{PREFIX}-historical-cancel":
            return False, visible, "", "", hidden, "", None
        if triggered == f"{PREFIX}-historical-back":
            return True, visible, f"Source: {source_id or '—'}", "", hidden, "", request
        if not source_id:
            return True, visible, "", "", hidden, "Select a source first.", request
        try:
            start = date.fromisoformat(str(start_value))
            end = date.fromisoformat(str(end_value))
            if end < start:
                raise ValueError("end date must be on or after start date")
        except (TypeError, ValueError) as exc:
            return True, visible, f"Source: {source_id}", "", hidden, str(exc), request

        if triggered == f"{PREFIX}-historical-review":
            async with sessions() as session:
                source = await AsyncRunRepository(session).latest_config("source", source_id)
            if source is None:
                return True, visible, f"Source: {source_id}", "", hidden, f"Unknown source: {source_id}", request
            payload = {
                "source_id": source_id,
                "revision": source.revision,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
            review = dmc.Stack(
                [
                    dmc.Text(f"Source: {source_id}"),
                    dmc.Text("Mode: Historical"),
                    dmc.Text(f"Base revision: {source.revision}"),
                    dmc.Text(f"Date range: {start.isoformat()} → {end.isoformat()} (inclusive)"),
                    dmc.Text("Pointer update: No"),
                    dmc.Text("Overrides: None"),
                    dmc.Group(
                        [
                            dmc.Button("Back", id=f"{PREFIX}-historical-back", variant="subtle"),
                            dmc.Button("Submit historical run", id=f"{PREFIX}-historical-submit"),
                        ],
                        justify="flex-end",
                        mt="sm",
                    ),
                ],
                gap="xs",
            )
            return True, hidden, f"Source: {source_id}", review, visible, "", payload

        if triggered == f"{PREFIX}-historical-submit":
            if not isinstance(request, dict):
                return (
                    True,
                    visible,
                    f"Source: {source_id}",
                    "",
                    hidden,
                    "Review the request before submitting.",
                    request,
                )
            try:
                async with sessions() as session:
                    async with session.begin():
                        row = await AsyncRunRepository(session).queue_historical_run(
                            source_id,
                            start_date=date.fromisoformat(str(request["start_date"])),
                            end_date=date.fromisoformat(str(request["end_date"])),
                            expected_revision=int(request["revision"]),
                        )
                return False, visible, f"Source: {source_id}", "", hidden, f"Queued historical run {row.run_id}.", None
            except Exception as exc:  # pragma: no cover - driver-specific failure rendering
                return (
                    True,
                    visible,
                    f"Source: {source_id}",
                    no_update,
                    visible,
                    f"Unable to queue historical run: {exc}",
                    request,
                )
        return True, visible, f"Source: {source_id or '—'}", "", hidden, "", request


__all__ = ["register"]
