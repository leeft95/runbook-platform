"""Operational profile/source catalogues built from existing repositories."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, dcc, html

from ..repository import AsyncRunRepository
from .operations import (
    STATUS_CELL_CLASS_RULES,
    as_iso,
    dataset_ids,
    empty_state,
    error_state,
    load_operations,
    profile_source_ids,
    relative_time,
    run_status,
    status_label,
)


def _latest_runs(rows: list[Any], kind: str) -> dict[str, Any]:
    """Return the newest run for each target from a bounded run query."""
    result: dict[str, Any] = {}
    for row in rows:
        if row.kind == kind:
            result.setdefault(row.target_id, row)
    return result


def _successful_runs(rows: list[Any], kind: str) -> dict[str, Any]:
    """Return the newest successful run for each target."""
    result: dict[str, Any] = {}
    for row in rows:
        if row.kind == kind and row.status == "success" and row.target_id not in result:
            result[row.target_id] = row
    return result


def profile_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Project profile configuration, latest runs, and dependency facts."""
    latest = _latest_runs(data["runs"], "profile")
    successful = _successful_runs(data["runs"], "profile")
    sources = data["sources"]
    now = datetime.now(timezone.utc)
    result = []
    for config in data["profiles"]:
        payload = dict(config.payload)
        profile_id = str(config.config_id)
        current = latest.get(profile_id)
        success = successful.get(profile_id)
        snapshot = getattr(success or current, "snapshot_payload", None) or {}
        watermark = snapshot.get("watermark") if isinstance(snapshot, dict) else None
        result.append(
            {
                "profile_id": profile_id,
                "profile": payload.get("title") or profile_id,
                "profile_link": f"[{payload.get('title') or profile_id}](/ui/profiles/{profile_id})",
                "enabled": bool(payload.get("enabled", True)),
                "status": run_status(current) if current else "not_ready",
                "status_text": status_label(run_status(current) if current else "not_ready"),
                "last_success": as_iso(getattr(success, "finished_at", None)) if success else None,
                "last_success_age": relative_time(getattr(success, "finished_at", None), now=now) if success else "—",
                "snapshot_id": getattr(success or current, "snapshot_id", None),
                "as_of": watermark,
                "source_count": len(profile_source_ids(payload, sources)),
                "updated_at": as_iso(getattr(config, "created_at", None)),
                "updated_age": relative_time(getattr(config, "created_at", None), now=now),
                "revision": config.revision,
            }
        )
    return result


def source_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Project source configuration, pointers, reverse dependencies, and runs."""
    latest = _latest_runs(data["runs"], "source")
    successful = _successful_runs(data["runs"], "source")
    pointer_map: dict[str, list[dict[str, Any]]] = {}
    for pointer in data["pointers"]:
        pointer_map.setdefault(str(pointer["source_id"]), []).append(pointer)
    now = datetime.now(timezone.utc)
    result = []
    for config in data["sources"]:
        payload = dict(config.payload)
        source_id = str(config.config_id)
        current = latest.get(source_id)
        success = successful.get(source_id)
        pointers = pointer_map.get(source_id, [])
        watermarks = [pointer.get("watermark") for pointer in pointers if pointer.get("watermark") is not None]
        watermark = max(watermarks, key=str) if watermarks else None
        used_by = [
            profile.config_id
            for profile in data["profiles"]
            if source_id in profile_source_ids(dict(profile.payload), data["sources"])
        ]
        result.append(
            {
                "source_id": source_id,
                "source": source_id,
                "source_link": f"[{source_id}](/ui/sources/{source_id})",
                "enabled": bool(payload.get("enabled", True)),
                "status": run_status(current) if current else "not_ready",
                "status_text": status_label(run_status(current) if current else "not_ready"),
                "adapter": payload.get("adapter") or "—",
                "schedule": (payload.get("schedule") or {}).get("cron", "—"),
                "watermark": as_iso(watermark),
                "watermark_age": relative_time(watermark, now=now),
                "last_success": as_iso(getattr(success, "finished_at", None)) if success else None,
                "latest_run": as_iso(getattr(current, "requested_at", None)) if current else None,
                "used_by": len(used_by),
                "dataset_count": len(dataset_ids(payload)),
                "updated_at": as_iso(getattr(config, "created_at", None)),
                "updated_age": relative_time(getattr(config, "created_at", None), now=now),
                "revision": config.revision,
            }
        )
    return result


def catalogue_layout(kind: str) -> html.Div:
    """Build the compact filter bar and dense AG Grid for one entity kind."""
    prefix = f"runbook-ui-{kind}s-catalogue"
    title = "Profiles" if kind == "profile" else "Sources"
    columns = (
        [
            {"field": "profile_link", "headerName": "Profile", "cellRenderer": "markdown", "pinned": "left"},
            {
                "field": "status_text",
                "headerName": "Latest status",
                "cellClass": "runbook-grid-status",
                "cellClassRules": STATUS_CELL_CLASS_RULES,
            },
            {"field": "last_success_age", "headerName": "Last success"},
            {"field": "snapshot_id", "headerName": "Latest snapshot"},
            {"field": "as_of", "headerName": "As of"},
            {"field": "source_count", "headerName": "Sources", "width": 100},
            {"field": "updated_age", "headerName": "Updated"},
        ]
        if kind == "profile"
        else [
            {"field": "source_link", "headerName": "Source", "cellRenderer": "markdown", "pinned": "left"},
            {
                "field": "status_text",
                "headerName": "Status",
                "cellClass": "runbook-grid-status",
                "cellClassRules": STATUS_CELL_CLASS_RULES,
            },
            {"field": "adapter", "headerName": "Adapter"},
            {"field": "watermark", "headerName": "Latest watermark"},
            {"field": "watermark_age", "headerName": "Age"},
            {"field": "last_success", "headerName": "Last success"},
            {"field": "used_by", "headerName": "Used by", "width": 100},
        ]
    )
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.TextInput(
                        id=f"{prefix}-search",
                        label="Search",
                        placeholder=f"Search {title.lower()}…",
                        size="sm",
                    ),
                    dmc.Select(
                        id=f"{prefix}-status",
                        label="Status",
                        data=[
                            {"label": label, "value": value}
                            for value, label in ([("all", "All")] + list(_STATUS_OPTIONS))
                        ],
                        value="all",
                        clearable=False,
                        size="sm",
                        w=150,
                    ),
                    dmc.Select(
                        id=f"{prefix}-enabled",
                        label="Availability",
                        data=[
                            {"label": label, "value": value}
                            for value, label in [("all", "All"), ("enabled", "Enabled"), ("disabled", "Disabled")]
                        ],
                        value="all",
                        clearable=False,
                        size="sm",
                        w=150,
                    ),
                    dmc.Button(
                        "Refresh",
                        id=f"{prefix}-refresh",
                        variant="light",
                        size="sm",
                        className="runbook-button",
                    ),
                    dmc.Anchor("Configuration management", href=f"#runbook-ui-{kind}s-config", size="sm"),
                ],
                gap="sm",
                mb="sm",
                wrap="wrap",
            ),
            dcc.Loading(
                id=f"{prefix}-loading",
                type="default",
                children=html.Div(
                    [
                        html.Div(id=f"{prefix}-summary", className="runbook-muted"),
                        dag.AgGrid(
                            id=f"{prefix}-grid",
                            className="runbook-grid",
                            rowData=[],
                            columnDefs=columns,
                            defaultColDef={"resizable": True, "sortable": True, "filter": True},
                            dashGridOptions={"pagination": True, "paginationPageSize": 50, "rowSelection": "single"},
                            style={"height": "450px", "width": "100%"},
                        ),
                        dcc.Store(id=f"{prefix}-error"),
                    ]
                ),
            ),
        ],
        className="runbook-panel runbook-catalogue",
    )


_STATUS_OPTIONS = tuple(
    (value, label)
    for value, label in (
        ("queued", "Queued"),
        ("running", "Running"),
        ("success", "Succeeded"),
        ("failed", "Failed"),
        ("waiting", "Waiting"),
        ("not_ready", "Not ready"),
        ("cancelled", "Cancelled"),
    )
)


def register_catalogue_callbacks(dash_app: Any, sessions: Any, kind: str) -> None:
    """Register one bounded page-level catalogue refresh/filter callback."""
    prefix = f"runbook-ui-{kind}s-catalogue"

    @dash_app.callback(
        Output(f"{prefix}-grid", "rowData"),
        Output(f"{prefix}-summary", "children"),
        Input(f"{prefix}-refresh", "n_clicks"),
        Input(f"{prefix}-search", "value"),
        Input(f"{prefix}-status", "value"),
        Input(f"{prefix}-enabled", "value"),
    )
    async def refresh(_clicks: int | None, search: str | None, status: str | None, enabled: str | None):
        """Refresh and filter one operational catalogue."""
        try:
            async with sessions() as session:
                data = await load_operations(AsyncRunRepository(session))
            rows = profile_rows(data) if kind == "profile" else source_rows(data)
            query = (search or "").strip().lower()
            if query:
                rows = [row for row in rows if query in str(row).lower()]
            if status and status != "all":
                rows = [row for row in rows if row["status"] == status]
            if enabled == "enabled":
                rows = [row for row in rows if row["enabled"]]
            elif enabled == "disabled":
                rows = [row for row in rows if not row["enabled"]]
            if not rows:
                title = "No matching profiles" if kind == "profile" else "No matching sources"
                return [], empty_state(title, "Adjust the filters or use configuration management to add one.")
            return rows, f"{len(rows)} {kind}{'s' if kind != 'profile' else 's'}"
        except Exception as exc:  # pragma: no cover - driver-specific failure rendering
            return [], error_state(f"Unable to load {kind}s: {exc}")


__all__ = ["catalogue_layout", "profile_rows", "register_catalogue_callbacks", "source_rows"]
