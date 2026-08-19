from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository


def _text(value: Any) -> str:
    """Render a dashboard scalar without showing Python ``None``."""
    return value.isoformat() if isinstance(value, datetime) else ("" if value is None else str(value))


def _count_children(counts: dict[str, int]) -> list[Any]:
    """Build accessible text labels for each status count."""
    return [
        html.Span(
            f"{name.replace('_', ' ')}: {counts.get(name, 0)}",
            className="runbook-stat",
        )
        for name in ("success", "failed", "waiting", "not_ready")
    ]


def _elapsed(row: Any, now: datetime) -> str:
    """Return elapsed wall time for an active run."""
    started = row.started_at or row.requested_at
    elapsed = max(timedelta(0), now - _aware(started))
    return str(elapsed).split(".", 1)[0]


def _terminal_time(row: Any) -> str:
    """Render the terminal operation time as an explicit UTC timestamp."""
    value = row.finished_at or getattr(row, "updated_at", None) or row.requested_at
    return _text(_aware(value))


def _attention_table(rows: list[Any]) -> Any:
    """Build the recent failed/waiting operations table."""
    attention_rows = [
        html.Tr(
            [
                html.Td(
                    html.A(
                        row.run_id,
                        href=f"/ui/runs/{row.run_id}",
                        target="_blank",
                    )
                ),
                html.Td(row.kind),
                html.Td(row.target_id),
                html.Td(row.status, className="runbook-status"),
                html.Td(_terminal_time(row)),
                html.Td(row.reason or "—"),
            ]
        )
        for row in rows
    ] or [html.Tr([html.Td("No recent failures or waiting runs", colSpan=6)])]
    return html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th(label)
                        for label in (
                            "Run",
                            "Kind",
                            "Target",
                            "Status",
                            "Finished (UTC)",
                            "Reason",
                        )
                    ]
                )
            ),
            html.Tbody(attention_rows),
        ],
        className="runbook-table",
    )


def register(dash_app: Any, sessions: Any) -> None:
    """Register the five-second operations dashboard."""
    prefix = "runbook-ui-dashboard"

    async def refresh(_interval: int):
        """Refresh counts, active work, recent attention, and pointers."""
        async with sessions() as session:
            repository = AsyncRunRepository(session)
            active_counts = await repository.status_counts({"queued", "running"})
            pointers = await repository.list_pointers()
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=24)
            window = await repository.status_counts({"success", "failed", "waiting", "not_ready"}, since=cutoff)
            active = await repository.list_active_runs(limit=100)
            attention = await repository.list_attention_runs(cutoff, limit=20)
        active_rows = [
            html.Tr(
                [
                    html.Td(
                        html.A(
                            row.run_id,
                            href=f"/ui/runs/{row.run_id}",
                            target="_blank",
                        )
                    ),
                    html.Td(row.kind),
                    html.Td(row.target_id),
                    html.Td(row.status, className="runbook-status"),
                    html.Td(_elapsed(row, now)),
                    html.Td(_text(row.slot)),
                    html.Td(row.trigger),
                ]
            )
            for row in active
        ] or [html.Tr([html.Td("No active operations", colSpan=7)])]
        pointer_rows = [
            html.Tr(
                [
                    html.Td(pointer["dataset_id"]),
                    html.Td(pointer["source_id"]),
                    html.Td(_text(pointer["watermark"])),
                    html.Td(_text(pointer["published_at"])),
                    html.Td(
                        html.A(
                            pointer["source_run_id"],
                            href=f"/ui/runs/{pointer['source_run_id']}",
                            target="_blank",
                        )
                    ),
                ]
            )
            for pointer in pointers
        ] or [html.Tr([html.Td("No dataset pointers", colSpan=5)])]
        return (
            str(active_counts.get("queued", 0)),
            str(active_counts.get("running", 0)),
            _count_children(window),
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(label)
                                for label in (
                                    "Run",
                                    "Kind",
                                    "Target",
                                    "Status",
                                    "Elapsed",
                                    "Slot",
                                    "Trigger",
                                )
                            ]
                        )
                    ),
                    html.Tbody(active_rows),
                ],
                className="runbook-table",
            ),
            _attention_table(attention),
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(label)
                                for label in (
                                    "Dataset",
                                    "Producer",
                                    "Watermark",
                                    "Published",
                                    "Originating run",
                                )
                            ]
                        )
                    ),
                    html.Tbody(pointer_rows),
                ],
                className="runbook-table",
            ),
        )

    dash_app.callback(
        Output(f"{prefix}-queued", "children"),
        Output(f"{prefix}-running", "children"),
        Output(f"{prefix}-window", "children"),
        Output(f"{prefix}-active", "children"),
        Output(f"{prefix}-recent", "children"),
        Output(f"{prefix}-pointers", "children"),
        Input(f"{prefix}-refresh", "n_intervals"),
    )(refresh)

    register_page(
        __name__,
        path="/",
        name="Dashboard",
        order=0,
        layout=html.Div(
            [
                html.H2("Dashboard"),
                dcc.Interval(id=f"{prefix}-refresh", interval=5000, n_intervals=0),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Small("Queued"),
                                html.Div(
                                    id=f"{prefix}-queued",
                                    className="runbook-stat-value",
                                ),
                            ],
                            className="runbook-card",
                        ),
                        html.Div(
                            [
                                html.Small("Running"),
                                html.Div(
                                    id=f"{prefix}-running",
                                    className="runbook-stat-value",
                                ),
                            ],
                            className="runbook-card",
                        ),
                    ],
                    className="runbook-cards",
                ),
                html.H3("Previous 24 hours"),
                html.Div(id=f"{prefix}-window", className="runbook-cards"),
                html.H3("Active operations"),
                html.Div(id=f"{prefix}-active"),
                html.H3("Recent failed or waiting operations"),
                html.Div(id=f"{prefix}-recent"),
                html.H3("Dataset pointers"),
                html.Div(id=f"{prefix}-pointers"),
            ]
        ),
    )


def _aware(value: datetime) -> datetime:
    """Normalize database timestamps to timezone-aware UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


__all__ = ["register"]
