"""Source operational drill-down page."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, dcc, html, register_page

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
    return dag.AgGrid(
        id=component_id,
        rowData=[],
        columnDefs=columns,
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "rowSelection": "single"},
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


__all__ = ["register"]
