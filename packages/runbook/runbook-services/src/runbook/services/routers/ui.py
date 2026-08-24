from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request


def mount_ui(server: Any, *, sessions: Any, data_store: str | None, reports_root: str) -> Any:
    """Mount the multipage operations UI at ``/ui/``."""
    import dash
    import dash_mantine_components as dmc
    from dash import ClientsideFunction, Dash, Input, Output, dcc
    from dash.backends._fastapi import reset_current_request, set_current_request
    from fastapi.responses import HTMLResponse

    from ..dash import (
        dashboard,
        profile_detail,
        profiles,
        run_detail,
        run_drawer,
        run_logs,
        runs,
        source_detail,
        sources,
        system,
    )

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
    profile_detail.register(dash_app, sessions)
    source_detail.register(dash_app, sessions)
    system.register(dash_app, sessions)
    run_drawer.register(dash_app, sessions, data_store or "")

    nav_items = [
        ("Overview", "/ui/", "runbook-ui-nav-overview"),
        ("Profiles", "/ui/profiles", "runbook-ui-nav-profiles"),
        ("Sources", "/ui/sources", "runbook-ui-nav-sources"),
        ("All Runs", "/ui/runs", "runbook-ui-nav-runs"),
        ("System", "/ui/system", "runbook-ui-nav-system"),
    ]
    dash_app.layout = dmc.MantineProvider(
        [
            dcc.Location(id="runbook-ui-location"),
            dcc.Store(id="runbook-ui-hash-scroll"),
            dmc.AppShell(
                [
                    dmc.AppShellHeader(
                        dmc.Group(
                            [
                                dmc.Text("Runbook Operations", fw=700),
                                dmc.Text("Control plane", size="sm", c="dimmed"),
                            ],
                            h="100%",
                            px="md",
                            gap="sm",
                        ),
                        withBorder=True,
                    ),
                    dmc.AppShellNavbar(
                        dmc.Stack(
                            [
                                dmc.NavLink(label=label, href=href, id=component_id)
                                for label, href, component_id in nav_items
                            ],
                            gap=4,
                            p="sm",
                        ),
                        withBorder=True,
                    ),
                    dmc.AppShellMain(dash.page_container),
                ],
                header={"height": 56},
                navbar={"width": 220, "breakpoint": "sm"},
                padding="md",
                className="runbook-shell",
            ),
            run_drawer.drawer(),
        ],
        theme={
            "primaryColor": "blue",
            "defaultRadius": "sm",
            "fontFamily": "Inter, ui-sans-serif, system-ui, sans-serif",
        },
    )

    @dash_app.callback(
        *(Output(component_id, "active") for _label, _href, component_id in nav_items),
        Input("runbook-ui-location", "pathname"),
    )
    def active_navigation(pathname: str | None) -> tuple[bool, ...]:
        """Keep active navigation obvious while preserving browser history."""
        path = (pathname or "/ui/").rstrip("/") or "/"
        return tuple(
            path == href.rstrip("/") or (href != "/ui/" and path.startswith(href.rstrip("/") + "/"))
            for _label, href, _component_id in nav_items
        )

    dash_app.clientside_callback(
        ClientsideFunction(namespace="runbookNavigation", function_name="scrollToHash"),
        Output("runbook-ui-hash-scroll", "data"),
        Input("runbook-ui-location", "pathname"),
        Input("runbook-ui-location", "hash"),
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
