from __future__ import annotations

from typing import Any

from dash import html

from ._config import _page_layout, _spec, register_config_page
from .catalogue import catalogue_layout, register_catalogue_callbacks


def _layout() -> html.Div:
    """Keep config management reachable below the profile-first catalogue."""
    prefix = "runbook-ui-profiles"
    config = _page_layout(prefix, _spec("profile", "Profiles"))
    return html.Div(
        [
            html.Div(
                [html.H1("Profiles"), html.P("Primary operational catalogue for report products.")],
                className="runbook-page-heading",
            ),
            catalogue_layout("profile"),
            html.Hr(className="runbook-divider"),
            html.H2("Configuration management", id="runbook-ui-profiles-config"),
            *config.children,
        ]
    )


def register(dash_app: Any, sessions: Any) -> None:
    """Register the Profiles page."""
    register_config_page(
        dash_app,
        sessions,
        module=__name__,
        kind="profile",
        path="/profiles",
        name="Profiles",
        order=1,
        page_layout=_layout(),
    )
    register_catalogue_callbacks(dash_app, sessions, "profile")
