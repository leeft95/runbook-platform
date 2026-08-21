from __future__ import annotations

from types import SimpleNamespace

from dash import Dash, Input, Output, dcc, html
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash import dashboard, interaction, render_dash_page, select


def _manifest(title: str) -> PDLManifest:
    return PDLManifest(
        title=title,
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", text=title, row=1, col=1)],
        ),
        extensions={
            "dash": dashboard(
                controls=[select("book", options=["A", "B"])],
                interactions=[interaction(handler="filter", inputs=["book"], outputs=["summary"])],
            ).model_dump(mode="json")
        },
    )


def test_two_dash_pages_compose_with_host_owned_navigation() -> None:
    definition = ReportDefinition(
        [], {}, lambda ctx: _manifest("unused"), {"filter": lambda ctx, state: {"summary": state["book"] or "all"}}
    )
    ctx = SimpleNamespace()
    page_a = render_dash_page(_manifest("A"), definition, ctx, namespace="report-a")
    page_b = render_dash_page(_manifest("B"), definition, ctx, namespace="report-b")
    app = Dash(__name__ + "_multipage", use_pages=False)
    app.layout = html.Div([dcc.Location(id="host-path"), html.Div(id="host-content")])

    @app.callback(Output("host-content", "children"), Input("host-path", "pathname"))
    def route(pathname: str | None):
        return page_b.layout() if pathname == "/report-b" else page_a.layout()

    page_a.register_callbacks(app)
    page_b.register_callbacks(app)
    assert page_a.ids.block("summary") != page_b.ids.block("summary")
    assert page_a.ids.control("book") != page_b.ids.control("book")
    assert len(app.callback_map) == 3
    assert any("host-content.children" in key for key in app.callback_map)
    assert any(page_a.ids.block("summary") in key for key in app.callback_map)
    assert any(page_b.ids.block("summary") in key for key in app.callback_map)
