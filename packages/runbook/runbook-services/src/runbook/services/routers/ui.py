from __future__ import annotations

from typing import Any


def mount_ui(server: Any, *, sessions: Any, data_store: str | None, reports_root: str) -> Any:
    """Mount the multipage operations UI at ``/ui/``."""
    import dash
    from dash import Dash, dcc, html

    from ..dash import profiles, runs, sources

    dash_app = Dash(
        __name__,
        server=server,
        backend="fastapi",
        use_pages=True,
        pages_folder="",
        routes_pathname_prefix="/ui/",
        requests_pathname_prefix="/ui/",
        title="Runbook operations",
    )
    sources.register(dash_app, sessions)
    profiles.register(dash_app, sessions)
    runs.register(dash_app, sessions)
    dash_app.layout = html.Div(
        [
            html.H1("Runbook operations"),
            html.Nav(
                [
                    dcc.Link("Sources", href="/ui/"),
                    html.Span(" · "),
                    dcc.Link("Profiles", href="/ui/profiles"),
                    html.Span(" · "),
                    dcc.Link("Runs", href="/ui/runs"),
                ]
            ),
            dash.page_container,
        ],
        style={"maxWidth": "1400px", "margin": "0 auto", "padding": "24px"},
    )
    return dash_app
