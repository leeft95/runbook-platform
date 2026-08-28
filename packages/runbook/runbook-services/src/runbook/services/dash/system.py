"""Small factual system state page; no new monitoring service is introduced."""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, dcc, html, register_page

from ..repository import AsyncRunRepository
from .operations import error_state, metric_card, status_label

PREFIX = "runbook-ui-system"


def layout() -> html.Div:
    """Build the factual system state page."""
    return html.Div(
        [
            dcc.Interval(id=f"{PREFIX}-refresh", interval=30_000, n_intervals=0),
            dmc.Group(
                [
                    dmc.Stack(
                        [
                            dmc.Title("System", order=2),
                            dmc.Text("Factual control-plane state available to this service.", c="dimmed"),
                        ],
                        gap=0,
                    ),
                    dmc.Button("Refresh", id=f"{PREFIX}-manual-refresh", variant="light", size="sm"),
                ],
                justify="space-between",
                align="flex-end",
                mb="md",
                className="runbook-page-heading",
            ),
            dcc.Loading(
                id=f"{PREFIX}-loading",
                type="default",
                children=html.Div(
                    [
                        html.Div(id=f"{PREFIX}-error"),
                        dmc.SimpleGrid(
                            id=f"{PREFIX}-metrics",
                            cols={"base": 1, "sm": 2, "lg": 4},
                            spacing="sm",
                            mb="md",
                            className="runbook-metrics",
                        ),
                        dmc.Card(
                            id=f"{PREFIX}-details",
                            withBorder=True,
                            padding="md",
                            className="runbook-panel",
                        ),
                    ]
                ),
            ),
        ],
        className="runbook-page runbook-detail-page",
    )


def register(dash_app: Any, sessions: Any) -> None:
    """Register the system page refresh callback."""
    # A path template keeps this compatibility page out of the legacy static-page set.
    register_page("runbook.operations.system", path_template="/system", name="System", order=4, layout=layout())

    @dash_app.callback(
        Output(f"{PREFIX}-metrics", "children"),
        Output(f"{PREFIX}-details", "children"),
        Output(f"{PREFIX}-error", "children"),
        Input(f"{PREFIX}-refresh", "n_intervals"),
        Input(f"{PREFIX}-manual-refresh", "n_clicks"),
    )
    async def refresh(_interval: int, _clicks: int | None):
        """Refresh repository-backed service counts."""
        try:
            async with sessions() as session:
                repository = AsyncRunRepository(session)
                profiles = await repository.list_latest_configs("profile")
                sources = await repository.list_latest_configs("source")
                runs = await repository.list_runs(limit=500)
                pointers = await repository.list_pointers(limit=500)
            counts: dict[str, int] = {}
            for row in runs:
                counts[row.status] = counts.get(row.status, 0) + 1
            metrics = [
                metric_card("Profiles", len(profiles)),
                metric_card("Sources", len(sources)),
                metric_card("Recent runs", len(runs), note="bounded to 500"),
                metric_card("Current pointers", len(pointers)),
            ]
            details = dmc.Stack(
                [
                    dmc.Title("Service data", order=4, className="runbook-panel-title"),
                    dmc.Text("Run status counts from the durable repository.", c="dimmed", size="sm"),
                    dmc.Group(
                        [dmc.Text(f"{status_label(status)}: {count}") for status, count in sorted(counts.items())],
                        gap="lg",
                    ),
                ],
                gap="xs",
            )
            return metrics, details, ""
        except Exception as exc:  # pragma: no cover - driver-specific failure rendering
            return [], "", error_state(f"Unable to load system data: {exc}", retry_id=f"{PREFIX}-manual-refresh")


__all__ = ["register"]
