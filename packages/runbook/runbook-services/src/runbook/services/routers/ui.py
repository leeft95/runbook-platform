from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from fastapi import Request

from ..dash import OperationsBrand


def mount_ui(
    server: Any,
    *,
    sessions: Any,
    data_store: str | None,
    reports_root: str,
    operations_brand: OperationsBrand | None = None,
) -> Any:
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
    if operations_brand is None:
        operations_brand = OperationsBrand()
    if operations_brand.favicon_src is not None:
        dash_app.index_string = dash_app.index_string.replace(
            "{%favicon%}",
            f'<link rel="icon" href="{escape(operations_brand.favicon_src, quote=True)}">',
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
        ("Runs", "/ui/runs", "runbook-ui-nav-runs"),
        ("System", "/ui/system", "runbook-ui-nav-system"),
    ]
    brand_style = {
        key: value
        for key, value in {
            "--rb-primary": operations_brand.primary,
            "--rb-primary-hover": operations_brand.primary_hover,
            "--rb-primary-soft": operations_brand.primary_soft,
        }.items()
        if value is not None
    }
    brand_slot = [
        dmc.Image(
            src=operations_brand.logo_src,
            alt=f"{operations_brand.name} logo",
            h=24,
            fit="contain",
        )
        if operations_brand.logo_src
        else None,
        dmc.Text(operations_brand.name, fw=700),
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
                                dmc.Group([item for item in brand_slot if item is not None], gap="xs"),
                                dmc.Text("Control plane", size="sm", c="dimmed"),
                            ],
                            h="100%",
                            px="md",
                            gap="sm",
                        ),
                        withBorder=True,
                        className="runbook-product-header",
                    ),
                    dmc.AppShellNavbar(
                        dmc.Stack(
                            [
                                dmc.NavLink(
                                    label=label,
                                    href=href,
                                    id=component_id,
                                    className="runbook-nav-link",
                                )
                                for label, href, component_id in nav_items
                            ],
                            gap=4,
                            p="sm",
                        ),
                        withBorder=True,
                        className="runbook-product-nav",
                    ),
                    dmc.AppShellMain(dash.page_container, className="runbook-app-main"),
                ],
                header={"height": 56},
                navbar={"width": 220, "breakpoint": "sm"},
                padding=0,
                className="runbook-shell",
                style=brand_style or None,
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
