"""Profile operational drill-down page."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository
from .operations import (
    copy_value,
    detail_row,
    empty_state,
    exact_time,
    profile_source_ids,
    relative_time,
    run_status,
    status_badge,
    status_label,
    timestamp,
)

PREFIX = "runbook-ui-profile-detail"


def _grid(component_id: str, columns: list[dict[str, Any]], height: str = "300px") -> dag.AgGrid:
    """Build one dense profile-detail AG Grid."""
    return dag.AgGrid(
        id=component_id,
        rowData=[],
        columnDefs=columns,
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 25, "rowSelection": "single"},
        style={"height": height, "width": "100%"},
    )


def layout() -> html.Div:
    """Build the profile operational drill-down page."""
    return html.Div(
        [
            dcc.Location(id=f"{PREFIX}-location"),
            dcc.Interval(id=f"{PREFIX}-refresh", interval=30_000, n_intervals=0),
            html.Div(id=f"{PREFIX}-error"),
            dmc.Breadcrumbs(
                [dmc.Anchor("Profiles", href="/ui/profiles"), dmc.Text(id=f"{PREFIX}-breadcrumb")],
                mb="xs",
            ),
            dmc.Group(
                [
                    dmc.Stack(
                        [dmc.Title(id=f"{PREFIX}-title", order=2), dmc.Text(id=f"{PREFIX}-subtitle", c="dimmed")], gap=0
                    ),
                    dmc.Group(
                        [
                            dmc.Anchor("Configuration", href="/ui/profiles#runbook-ui-profiles-config", size="sm"),
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
                    dmc.Title("Dependent sources", order=4),
                    dmc.Text("Derived from this profile's current dataset bindings.", size="sm", c="dimmed", mb="xs"),
                    _grid(
                        f"{PREFIX}-sources-grid",
                        [
                            {
                                "field": "source_link",
                                "headerName": "Source",
                                "cellRenderer": "markdown",
                                "pinned": "left",
                            },
                            {"field": "status_text", "headerName": "Status"},
                            {"field": "watermark", "headerName": "Latest watermark"},
                            {"field": "last_success", "headerName": "Last success"},
                            {"field": "age", "headerName": "Age"},
                        ],
                    ),
                    html.Div(id=f"{PREFIX}-sources-empty"),
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
    )


def _profile_id(pathname: str | None) -> str | None:
    """Extract a profile ID from the browser pathname."""
    parts = [part for part in (pathname or "").split("/") if part]
    try:
        index = parts.index("profiles")
    except ValueError:
        return None
    return parts[index + 1] if len(parts) > index + 1 else None


def _source_rows(
    profile: Any,
    sources: list[Any],
    runs: list[Any],
    pointers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Project dependent source state for one profile."""
    ids = profile_source_ids(dict(profile.payload), sources)
    result = []
    now = datetime.now(timezone.utc)
    for source_id in ids:
        config = next((source for source in sources if str(source.config_id) == source_id), None)
        source_runs = [row for row in runs if row.kind == "source" and row.target_id == source_id]
        latest = source_runs[0] if source_runs else None
        success = next((row for row in source_runs if row.status == "success"), None)
        source_config = dict(config.payload) if config else {}
        source_dataset_ids = set()
        for binding in source_config.get("datasets", {}).values():
            if isinstance(binding, dict) and binding.get("dataset_id"):
                source_dataset_ids.add(str(binding["dataset_id"]))
        source_pointers = [
            pointer
            for pointer in pointers or []
            if str(pointer.get("source_id")) == source_id and str(pointer.get("dataset_id")) in source_dataset_ids
        ]
        watermarks = [pointer.get("watermark") for pointer in source_pointers if pointer.get("watermark") is not None]
        watermark = max(watermarks, key=str) if watermarks else None
        result.append(
            {
                "source_id": source_id,
                "source_link": f"[{source_id}](/ui/sources/{source_id})",
                "status_text": status_label(run_status(latest) if latest else "not_ready"),
                "watermark": exact_time(watermark),
                "last_success": exact_time(getattr(success, "finished_at", None)),
                "age": relative_time(getattr(success, "finished_at", None), now=now),
                "enabled": bool((config.payload if config else {}).get("enabled", True)),
            }
        )
    return result


def register(dash_app: Any, sessions: Any) -> None:
    """Register profile summary, dependency, and run-history loading."""
    register_page(
        "runbook.operations.profile_detail",
        path_template="/profiles/<profile_id>",
        name="Profile detail",
        order=10,
        hide_nav=True,
        layout=layout(),
    )

    @dash_app.callback(
        Output(f"{PREFIX}-title", "children"),
        Output(f"{PREFIX}-subtitle", "children"),
        Output(f"{PREFIX}-breadcrumb", "children"),
        Output(f"{PREFIX}-metrics", "children"),
        Output(f"{PREFIX}-sources-grid", "rowData"),
        Output(f"{PREFIX}-sources-empty", "children"),
        Output(f"{PREFIX}-runs-grid", "rowData"),
        Output(f"{PREFIX}-runs-empty", "children"),
        Output(f"{PREFIX}-error", "children"),
        Input(f"{PREFIX}-location", "pathname"),
        Input(f"{PREFIX}-refresh", "n_intervals"),
        Input(f"{PREFIX}-manual-refresh", "n_clicks"),
    )
    async def refresh(pathname: str | None, _interval: int, _clicks: int | None):
        """Refresh profile summary, dependent sources, and run history."""
        profile_id = _profile_id(pathname)
        if not profile_id:
            return (
                "Profile",
                "No profile selected",
                "—",
                [],
                [],
                empty_state("No profile", "Choose a profile from the catalogue."),
                [],
                empty_state("No runs", "This profile has no configured runs."),
                "",
            )
        try:
            async with sessions() as session:
                repository = AsyncRunRepository(session)
                profile = await repository.latest_config("profile", profile_id)
                sources = await repository.list_latest_configs("source")
                runs = await repository.list_runs(kind="profile", target_id=profile_id, limit=100)
                source_runs = await repository.list_runs(kind="source", limit=500)
                pointers = await repository.list_pointers(limit=500)
            if profile is None:
                return (
                    profile_id,
                    "Unknown profile",
                    profile_id,
                    [],
                    [],
                    empty_state("Profile not found", "The configuration may have been removed."),
                    [],
                    empty_state("No runs", "No run history is available."),
                    "",
                )
            payload = dict(profile.payload)
            latest = runs[0] if runs else None
            success = next((row for row in runs if row.status == "success"), None)
            snapshot = getattr(success or latest, "snapshot_payload", None) or {}
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
                        dmc.Text("Latest snapshot", size="sm", c="dimmed"),
                        copy_value(getattr(success or latest, "snapshot_id", None), label="snapshot"),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
                dmc.Card(
                    [
                        dmc.Text("Last successful run", size="sm", c="dimmed"),
                        timestamp(getattr(success, "finished_at", None)),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
                dmc.Card(
                    [
                        dmc.Text("Snapshot as of", size="sm", c="dimmed"),
                        dmc.Text(str(snapshot.get("watermark") or "—"), size="sm"),
                    ],
                    withBorder=True,
                    padding="sm",
                ),
            ]
            source_data = _source_rows(
                profile,
                sources,
                source_runs,
                pointers,
            )
            run_data = [dict(detail_row(row), status_text=status_label(run_status(row))) for row in runs]
            return (
                payload.get("title") or profile_id,
                f"{profile_id} · revision {profile.revision} · {'enabled' if payload.get('enabled', True) else 'disabled'}",
                payload.get("title") or profile_id,
                metrics,
                source_data,
                ""
                if source_data
                else empty_state("No configured sources", "This profile has no dataset bindings matching a source."),
                run_data,
                ""
                if run_data
                else empty_state("No profile runs yet", "Queue a run from configuration management when ready."),
                "",
            )
        except Exception as exc:  # pragma: no cover - driver-specific failure rendering
            return profile_id, "", profile_id, [], [], "", [], "", f"Unable to load profile: {exc}"


__all__ = ["register"]
