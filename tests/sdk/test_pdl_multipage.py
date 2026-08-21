from __future__ import annotations

from types import SimpleNamespace

from dash import Dash, Input, Output, dcc, html
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash import dashboard, interaction, render_dash_page, select


def _manifest(title: str, *, handler: str = "filter") -> PDLManifest:
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
                interactions=[interaction(handler=handler, inputs=["book"], outputs=["summary"])],
            ).model_dump(mode="json")
        },
    )


def test_two_dash_pages_compose_with_host_owned_navigation() -> None:
    definition = ReportDefinition(
        [],
        {},
        lambda ctx: _manifest("unused"),
        {
            "filter_a": lambda ctx, state: {"summary": f"A:{state['book'] or 'all'}"},
            "filter_b": lambda ctx, state: {"summary": f"B:{state['book'] or 'all'}"},
        },
    )
    ctx = SimpleNamespace()
    page_a = render_dash_page(_manifest("A", handler="filter_a"), definition, ctx, namespace="report-a")
    page_b = render_dash_page(_manifest("B", handler="filter_b"), definition, ctx, namespace="report-b")
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

    client = app.server.test_client()
    assert client.get("/").status_code == 200

    route_key = next(key for key in app.callback_map if key == "host-content.children")
    route_response = client.post(
        "/_dash-update-component",
        json={
            "output": route_key,
            "outputs": {"id": "host-content", "property": "children"},
            "inputs": [{"id": "host-path", "property": "pathname", "value": "/report-b"}],
            "changedPropIds": ["host-path.pathname"],
            "state": [],
        },
    )
    assert route_response.status_code == 200
    assert page_b.ids.block("summary").encode() in route_response.data
    assert page_a.ids.block("summary").encode() not in route_response.data

    for page, prefix in ((page_a, "A"), (page_b, "B")):
        callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
        response = client.post(
            "/_dash-update-component",
            json={
                "output": callback_key,
                "outputs": [{"id": page.ids.block("summary"), "property": "children"}],
                "inputs": [{"id": page.ids.control("book"), "property": "value", "value": "B"}],
                "changedPropIds": [f"{page.ids.control('book')}.value"],
                "state": [],
            },
        )
        assert response.status_code == 200
        assert f'"children":"{prefix}:B"'.encode() in response.data


def test_same_page_interactions_keep_distinct_inputs_handlers_and_outputs() -> None:
    manifest = PDLManifest(
        title="Two interactions",
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=2,
            columns=1,
            blocks=[
                PDLTextBlock(name="summary_a", text="A", row=1, col=1),
                PDLTextBlock(name="summary_b", text="B", row=2, col=1),
            ],
        ),
        extensions={
            "dash": dashboard(
                controls=[select("book_a", options=["A"]), select("book_b", options=["B"])],
                interactions=[
                    interaction(handler="first", inputs=["book_a"], outputs=["summary_a"]),
                    interaction(handler="second", inputs=["book_b"], outputs=["summary_b"]),
                ],
            ).model_dump(mode="json")
        },
    )
    definition = ReportDefinition(
        [],
        {},
        lambda ctx: manifest,
        {
            "first": lambda ctx, state: {"summary_a": f"first:{state['book_a']}"},
            "second": lambda ctx, state: {"summary_b": f"second:{state['book_b']}"},
        },
    )
    page = render_dash_page(manifest, definition, SimpleNamespace(), namespace="two-interactions")
    app = Dash(__name__ + "_same_page", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)
    assert len(app.callback_map) == 2
    client = app.server.test_client()

    for output_name, input_name, value, expected in (
        ("summary_a", "book_a", "A", "first:A"),
        ("summary_b", "book_b", "B", "second:B"),
    ):
        callback_key = next(key for key in app.callback_map if page.ids.block(output_name) in key)
        response = client.post(
            "/_dash-update-component",
            json={
                "output": callback_key,
                "outputs": [{"id": page.ids.block(output_name), "property": "children"}],
                "inputs": [{"id": page.ids.control(input_name), "property": "value", "value": value}],
                "changedPropIds": [f"{page.ids.control(input_name)}.value"],
                "state": [],
            },
        )
        assert response.status_code == 200
        assert f'"children":"{expected}"'.encode() in response.data
