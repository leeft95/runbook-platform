"""Small, data-only helpers shared by the operations pages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import dash_mantine_components as dmc
from dash import dcc

from ..repository import AsyncRunRepository

_KNOWN_STATUSES = {
    "queued": "Queued",
    "running": "Running",
    "cancelling": "Cancelling",
    "success": "Success",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "waiting": "Waiting",
    "not_ready": "Not ready",
    "skipped": "Skipped",
}
_STATUS_COLOURS = {
    "queued": "gray",
    "running": "blue",
    "cancelling": "yellow",
    "success": "green",
    "failed": "red",
    "cancelled": "gray",
    "waiting": "orange",
    "not_ready": "orange",
    "skipped": "gray",
}


def aware(value: datetime | None) -> datetime | None:
    """Normalize a database timestamp to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def exact_time(value: datetime | None) -> str:
    """Return an explicit, stable UTC timestamp for tooltips and tables."""
    stamp = aware(value)
    return stamp.isoformat(timespec="seconds") if stamp else "—"


def relative_time(value: datetime | None, *, now: datetime | None = None) -> str:
    """Return a compact factual age without inventing a freshness threshold."""
    stamp = aware(value)
    if stamp is None:
        return "—"
    current = aware(now) or datetime.now(timezone.utc)
    seconds = int((current - stamp).total_seconds())
    if seconds < 0:
        return "in the future"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h ago"
    days, hours = divmod(hours, 24)
    return f"{days}d ago" if not hours else f"{days}d {hours}h ago"


def timestamp(value: datetime | None) -> Any:
    """Render a relative timestamp with its exact UTC value available."""
    if value is None:
        return dmc.Text("—", c="dimmed", size="sm")
    return dmc.Tooltip(dmc.Text(relative_time(value), size="sm"), label=exact_time(value))


def format_duration(start: datetime | None, end: datetime | None, *, now: datetime | None = None) -> str:
    """Format a run duration using milliseconds, seconds, or minutes."""
    begin = aware(start)
    finish = aware(end) or aware(now) or datetime.now(timezone.utc)
    if begin is None:
        return "—"
    seconds = max(0.0, (finish - begin).total_seconds())
    if seconds < 1:
        return f"{round(seconds * 1000):d} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m {remainder}s"


def status_label(status: Any) -> str:
    """Return readable status text, including for values added later."""
    value = str(status or "unknown").lower()
    return _KNOWN_STATUSES.get(value, value.replace("_", " ").title() or "Unknown")


def status_badge(status: Any) -> Any:
    """Render one status consistently and safely degrade unknown values."""
    value = str(status or "unknown").lower()
    return dmc.Badge(status_label(value), color=_STATUS_COLOURS.get(value, "gray"), variant="light")


def copy_value(value: Any, *, label: str | None = None, max_length: int = 20) -> Any:
    """Render a compact identifier with an accessible full-value copy control."""
    text = "—" if value is None or value == "" else str(value)
    display = text if len(text) <= max_length else f"{text[:max_length]}…"
    if text == "—":
        return dmc.Text(display, size="sm", c="dimmed")
    return dmc.Group(
        [
            dmc.Tooltip(dmc.Text(display, size="sm"), label=text),
            dcc.Clipboard(content=text, title=f"Copy {label or 'value'}", className="runbook-copy"),
        ],
        gap=4,
        wrap="nowrap",
    )


def metric_card(label: str, value: Any, *, note: str | None = None) -> Any:
    """Build a compact operational metric surface."""
    children: list[Any] = [dmc.Text(label, size="sm", c="dimmed"), dmc.Title(str(value), order=3)]
    if note:
        children.append(dmc.Text(note, size="xs", c="dimmed"))
    return dmc.Card(children, withBorder=True, padding="sm", radius="sm", className="runbook-metric")


def empty_state(title: str, message: str) -> Any:
    """Explain an empty table instead of leaving a blank surface."""
    return dmc.Alert(message, title=title, color="gray", variant="light")


def error_state(message: str, *, retry_id: str | None = None) -> Any:
    """Render an explicit load failure; retry remains an ordinary Dash callback."""
    children: list[Any] = [dmc.Text(message)]
    if retry_id:
        children.append(dmc.Button("Retry", id=retry_id, variant="light", size="xs"))
    return dmc.Alert(children, title="Unable to load operations data", color="red", variant="light")


def entity_link(kind: str, entity_id: Any, *, label: str | None = None) -> Any:
    """Link a profile or source to its canonical detail route."""
    value = str(entity_id)
    return dmc.Anchor(label or value, href=f"/ui/{kind}s/{value}", underline="hover")


def dataset_ids(payload: dict[str, Any] | None) -> set[str]:
    """Extract dataset IDs from either profile or source config payloads."""
    result: set[str] = set()
    for binding in (payload or {}).get("datasets", {}).values():
        if isinstance(binding, dict):
            value = binding.get("dataset_id")
        else:
            value = binding
        if value:
            result.add(str(value))
    return result


def profile_source_ids(profile_payload: dict[str, Any], source_rows: Iterable[Any]) -> list[str]:
    """Derive profile dependencies by matching configured dataset bindings."""
    wanted = dataset_ids(profile_payload)
    return [
        str(row.config_id) for row in source_rows if wanted.intersection(dataset_ids(getattr(row, "payload", None)))
    ]


async def load_operations(repository: AsyncRunRepository) -> dict[str, Any]:
    """Read existing configs, bounded runs, and pointers in one page-level refresh."""
    profiles = await repository.list_latest_configs("profile")
    sources = await repository.list_latest_configs("source")
    runs = await repository.list_runs(limit=500)
    pointers = await repository.list_pointers(limit=500)
    return {"profiles": profiles, "sources": sources, "runs": runs, "pointers": pointers}


def run_status(row: Any) -> str:
    """Expose cancellation intent as a readable operational state."""
    if getattr(row, "status", None) == "running" and getattr(row, "cancel_requested_at", None) is not None:
        return "cancelling"
    return str(getattr(row, "status", "unknown"))


def row_value(row: Any, name: str, default: Any = None) -> Any:
    """Read ORM or mapping rows uniformly for small UI serializers."""
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def as_iso(value: Any) -> Any:
    """Serialize datetimes while leaving JSON-safe scalar values unchanged."""
    return value.isoformat() if isinstance(value, datetime) else value


def detail_row(row: Any) -> dict[str, Any]:
    """Serialize a run row for AG Grid and drawer state."""
    names = (
        "run_id",
        "kind",
        "target_id",
        "status",
        "worker_id",
        "cancel_requested_at",
        "slot",
        "trigger",
        "reason",
        "config_revision",
        "config_hash",
        "snapshot_id",
        "context_hash",
        "code_version",
        "artifact_id",
        "requested_at",
        "started_at",
        "finished_at",
        "updated_at",
        "result",
        "snapshot_payload",
    )
    result = {name: as_iso(row_value(row, name)) for name in names}
    result["status"] = run_status(row)
    result["duration"] = format_duration(row_value(row, "started_at"), row_value(row, "finished_at"))
    return result


__all__ = [
    "as_iso",
    "aware",
    "copy_value",
    "dataset_ids",
    "detail_row",
    "empty_state",
    "entity_link",
    "error_state",
    "exact_time",
    "format_duration",
    "load_operations",
    "metric_card",
    "profile_source_ids",
    "relative_time",
    "row_value",
    "run_status",
    "status_badge",
    "status_label",
    "timestamp",
]
