from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request


def mount_ui(server: Any, *, sessions: Any, data_store: str | None, reports_root: str) -> Any:
    """Mount the multipage operations UI at ``/ui/``."""
    import dash
    from dash import Dash, dcc, html
    from dash.backends._fastapi import reset_current_request, set_current_request
    from fastapi.responses import HTMLResponse

    from ..dash import dashboard, profiles, run_detail, run_logs, runs, sources

    dash_app = Dash(
        __name__,
        server=server,
        backend="fastapi",
        use_pages=True,
        pages_folder="",
        routes_pathname_prefix="/ui/",
        requests_pathname_prefix="/ui/",
        assets_folder=str(Path(__file__).resolve().parents[1] / "assets"),
        title="Runbook operations",
    )
    dashboard.register(dash_app, sessions)
    sources.register(dash_app, sessions)
    profiles.register(dash_app, sessions)
    runs.register(dash_app, sessions)
    run_detail.register(dash_app, sessions)
    run_logs.register(dash_app, sessions, data_store or "")
    dash_app.layout = html.Div(
        [
            html.H1("Runbook operations"),
            html.Nav(
                [
                    dcc.Link("Dashboard", href="/ui/"),
                    html.Span(" · "),
                    dcc.Link("Runs", href="/ui/runs"),
                    html.Span(" · "),
                    dcc.Link("Sources", href="/ui/sources"),
                    html.Span(" · "),
                    dcc.Link("Profiles", href="/ui/profiles"),
                ]
            ),
            dash.page_container,
        ],
        style={"maxWidth": "1400px", "margin": "0 auto", "padding": "24px"},
    )

    @server.get("/ui/{path:path}", include_in_schema=False)
    async def ui_page(path: str, request: Request) -> HTMLResponse:
        """Serve the Dash shell for client-side page and dynamic routes."""
        token = set_current_request(request)
        try:
            return HTMLResponse(dash_app.index())
        finally:
            reset_current_request(token)

    return dash_app
