from __future__ import annotations

from typing import Any

from dash import html

from ._config import _page_layout, _spec, register_config_page
from .catalogue import catalogue_layout, register_catalogue_callbacks


def _layout() -> html.Div:
    """Keep source configuration actions alongside the operational catalogue."""
    prefix = "runbook-ui-sources"
    config = _page_layout(prefix, _spec("source", "Sources"))
    return html.Div(
        [
            html.Div(
                [html.H1("Sources"), html.P("Operational source catalogue and freshness view.")],
                className="runbook-page-heading",
            ),
            catalogue_layout("source"),
            html.Hr(className="runbook-divider"),
            html.H2("Configuration management", id="runbook-ui-sources-config", className="runbook-panel-title"),
            *config.children,
        ],
        className="runbook-page",
    )


def register(dash_app: Any, sessions: Any) -> None:
    """Register the Sources page."""
    register_config_page(
        dash_app,
        sessions,
        module=__name__,
        kind="source",
        path="/sources",
        name="Sources",
        order=0,
        page_layout=_layout(),
    )
    register_catalogue_callbacks(dash_app, sessions, "source")
