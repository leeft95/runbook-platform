from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from dash import Input, Output, State, dcc, html, register_page
from runbook.core import open_blob_store

from ..logging import RunLogIdentity, read_log_tail
from ..repository import AsyncRunRepository

_MAX_TEXT = 128 * 1024


def _run_id_from_path(pathname: str | None) -> str | None:
    """Extract the run identifier from a detail or log route."""
    parts = [part for part in (pathname or "").split("/") if part]
    try:
        index = parts.index("runs")
    except ValueError:
        return None
    return parts[index + 1] if len(parts) > index + 1 else None


def _bounded_log(text: str) -> str:
    """Keep only the newest 128 KiB of UTF-8 log content."""
    payload = text.encode("utf-8", errors="replace")
    return payload[-_MAX_TEXT:].decode("utf-8", errors="replace")


def _aware_slot(value: datetime) -> datetime:
    """Normalize a database run slot to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def register(dash_app: Any, sessions: Any, data_store: str) -> None:
    """Register the live, bounded diagnostic-log route."""
    prefix = "runbook-ui-run-logs"

    @dash_app.callback(
        Output(f"{prefix}-text", "children"),
        Output(f"{prefix}-status", "children"),
        Output(f"{prefix}-cursor", "data"),
        Output(f"{prefix}-buffer", "data"),
        Output(f"{prefix}-refresh", "disabled"),
        Input(f"{prefix}-location", "pathname"),
        Input(f"{prefix}-refresh", "n_intervals"),
        State(f"{prefix}-cursor", "data"),
        State(f"{prefix}-buffer", "data"),
    )
    async def poll(pathname: str | None, _interval: int, after_part: int, buffer: str | None):
        """Read only new log chunks and describe the stream state."""
        run_id = _run_id_from_path(pathname)
        if run_id is None:
            return "", "unknown run ID", after_part, buffer or "", True
        async with sessions() as session:
            repository = AsyncRunRepository(session)
            row = await repository.get_run(run_id)
            config = await repository.get_config(row.kind, row.target_id, row.config_revision) if row else None
        if row is None:
            return "", "unknown run ID", after_part, buffer or "", True
        identity = RunLogIdentity(
            run_id=row.run_id,
            kind=row.kind,
            target_id=row.target_id,
            slot=_aware_slot(row.slot),
            report_id=(config.payload.get("report_id") if config and row.kind == "profile" else None),
        )
        try:
            tail = await asyncio.to_thread(read_log_tail, open_blob_store(data_store), identity, after_part)
        except Exception:
            tail = {
                "text": "",
                "next_part": after_part,
                "manifest": None,
                "complete": False,
                "incomplete": False,
                "terminal": False,
                "truncated": False,
            }
        text = _bounded_log((buffer or "") + tail.get("text", ""))
        manifest = tail.get("manifest")
        terminal = row.status not in {"queued", "running"}
        if tail.get("incomplete"):
            state = "incomplete after worker termination"
            disabled = True
        elif manifest:
            state = "completed (truncated)" if manifest.get("truncated") else "completed"
            disabled = True
        elif tail.get("text") or tail.get("parts"):
            state = "active" if not terminal else "incomplete"
            disabled = terminal
        elif row.status == "queued":
            state, disabled = "queued", False
        elif row.status == "running":
            state, disabled = "active", False
        elif (row.result or {}).get("log_ref"):
            state, disabled = "incomplete after worker termination", True
        else:
            state, disabled = "historical run without diagnostic logging", True
        captured = manifest.get("bytes") if manifest else len(text.encode("utf-8"))
        report = identity.report_id or "—"
        status = f"{state} · run status={row.status} · kind={row.kind} · target={row.target_id} · report={report} · slot={row.slot} · captured={captured} bytes"
        return text, status, tail.get("next_part", after_part), text, disabled

    register_page(
        __name__,
        path_template="/runs/<run_id>/logs",
        name="Run logs",
        order=3,
        hide_nav=True,
        layout=html.Div(
            [
                dcc.Location(id=f"{prefix}-location"),
                dcc.Interval(id=f"{prefix}-refresh", interval=2000, n_intervals=0, disabled=False),
                dcc.Store(id=f"{prefix}-cursor", data=0),
                dcc.Store(id=f"{prefix}-buffer", data=""),
                html.H2("Run logs"),
                html.Div(id=f"{prefix}-status"),
                html.Pre(id=f"{prefix}-text", className="runbook-log"),
            ]
        ),
    )


__all__ = ["_aware_slot", "_bounded_log", "_run_id_from_path", "register"]
