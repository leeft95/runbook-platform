from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dash import Dash, dcc, html
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash import (
    DashPage,
    dashboard,
    interaction,
    render_dash_page,
    select,
)


def _manifest() -> PDLManifest:
    return PDLManifest(
        title="Renderer extension",
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", title="Summary", text="initial", row=1, col=1)],
        ),
        extensions={
            "dash": dashboard(
                controls=[select("book", options=["A", "B"])],
                interactions=[interaction(handler="filter", inputs=["book"], outputs=["summary"])],
            ).model_dump(mode="json")
        },
    )


def _heading_manifest(*, controls: bool = False) -> PDLManifest:
    return PDLManifest(
        title="Heading",
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="heading", title="Summary", text="", row=1, col=1)],
        ),
        extensions={"dash": dashboard(controls=[select("book", options=["A", "B"])]).model_dump(mode="json")}
        if controls
        else None,
    )


def _definition(manifest: PDLManifest, calls: list[dict[str, object]]) -> ReportDefinition:
    def handler(_ctx: object, state: dict[str, object]) -> dict[str, str]:
        calls.append(state)
        return {"summary": str(state["book"])}

    return ReportDefinition([], {}, lambda _ctx: manifest, {"filter": handler})


class FakeRenderer:
    """Small presentation-only extension used to characterize the public seam."""

    def __init__(self, *, fallback: bool = False) -> None:
        self.fallback = fallback
        self.page_calls: list[tuple[object, str]] = []
        self.control_calls: list[tuple[object, str, list[object] | None]] = []
        self.block_calls: list[tuple[object, object | None, object]] = []

    def wrap_page(self, content: Any, *, manifest: PDLManifest, namespace: str) -> Any | None:
        self.page_calls.append((manifest, namespace))
        if self.fallback:
            return None
        return html.Div(content, id=f"custom-{namespace}-page")

    def render_control(
        self,
        control: Any,
        *,
        component_id: str,
        options: list[object] | None,
    ) -> Any | None:
        self.control_calls.append((control, component_id, options))
        if self.fallback:
            return None
        return dcc.Input(id=component_id, value=getattr(control, "value", None))

    def wrap_block(
        self,
        body: Any,
        *,
        block: Any,
        title: Any | None,
        namespace: str,
    ) -> Any | None:
        self.block_calls.append((body, title, block))
        if self.fallback:
            return None
        return html.Div([title, body], className=f"custom-{namespace}-block")


def test_heading_block_has_no_dash_body_and_extension_receives_none() -> None:
    manifest = _heading_manifest()
    definition = _definition(manifest, [])

    page = render_dash_page(manifest, definition, SimpleNamespace(), namespace="heading")
    report_block = page.layout().children[2].children[0]
    assert report_block.id == page.ids.block("heading") + "-container"
    assert report_block.style == {"gridRow": "1 / span 1", "gridColumn": "1 / span 1"}
    assert len(report_block.children) == 1
    assert report_block.children[0].__class__.__name__ == "H2"

    renderer = FakeRenderer()
    extended_page = render_dash_page(
        manifest,
        definition,
        SimpleNamespace(),
        namespace="heading-extension",
        renderer_extension=renderer,
    )
    extended_root = extended_page.layout().children
    extended_block = extended_root.children[2].children[0]
    assert extended_block.id == extended_page.ids.block("heading") + "-container"
    assert renderer.block_calls[0][0] is None

    control_manifest = _heading_manifest(controls=True)
    control_renderer = FakeRenderer()
    control_page = render_dash_page(
        control_manifest,
        _definition(control_manifest, []),
        SimpleNamespace(),
        namespace="heading-controls",
        renderer_extension=control_renderer,
    )
    control_root = control_page.layout().children
    control_block = control_root.children[2].children[0]
    control_body: Any = control_renderer.block_calls[0][0]
    assert control_block.id == control_page.ids.block("heading") + "-container"
    assert control_renderer.control_calls[0][1] == control_page.ids.control("book")
    assert control_body.children[0].children[1].id == control_page.ids.control("book")
    assert control_body.children[1] is None


def test_renderer_extension_hooks_preserve_public_ids_and_body() -> None:
    manifest = _manifest()
    calls: list[dict[str, object]] = []
    renderer = FakeRenderer()
    page = render_dash_page(
        manifest,
        _definition(manifest, calls),
        SimpleNamespace(),
        namespace="custom",
        renderer_extension=renderer,
    )

    layout = page.layout()
    assert isinstance(layout, html.Div)
    assert getattr(layout, "id", None) == "custom-custom-page"
    content = layout.children
    report_block = content.children[2].children[0]
    assert report_block.id == page.ids.block("summary") + "-container"
    assert report_block.style == {"gridRow": "1 / span 1", "gridColumn": "1 / span 1"}
    custom_block = report_block.children[0]
    assert custom_block.className == "custom-custom-block"
    assert custom_block.children[0].children == "Summary"
    body_with_controls = custom_block.children[1]
    assert body_with_controls.children[0].children[1].id == page.ids.control("book")
    assert body_with_controls.children[1].id == page.ids.block("summary")
    assert renderer.control_calls[0][1:] == (page.ids.control("book"), ["A", "B"])
    assert len(renderer.block_calls) == 1
    assert renderer.block_calls[0][0] is body_with_controls


def test_renderer_extension_none_hooks_use_vanilla_components() -> None:
    manifest = _manifest()
    renderer = FakeRenderer(fallback=True)
    page = render_dash_page(
        manifest,
        _definition(manifest, []),
        SimpleNamespace(),
        namespace="fallback",
        renderer_extension=renderer,
    )

    layout = page.layout()
    assert getattr(layout, "id", None) is None
    report_block = layout.children[2].children[0]
    assert report_block.children[0].__class__.__name__ == "H2"
    body = report_block.children[1]
    assert body.children[0].children[1].__class__.__name__ == "Dropdown"
    assert body.children[1].__class__.__name__ == "Pre"


def test_renderer_without_extension_preserves_vanilla_tree() -> None:
    manifest = _manifest()
    page = render_dash_page(manifest, _definition(manifest, []), SimpleNamespace(), namespace="vanilla")

    layout = page.layout()
    report_block = layout.children[2].children[0]
    assert getattr(layout, "id", None) is None
    assert report_block.id == page.ids.block("summary") + "-container"
    assert report_block.children[0].__class__.__name__ == "H2"
    assert report_block.children[1].children[0].children[1].__class__.__name__ == "Dropdown"


def _callback_response(app: Dash, page: DashPage, value: str):
    page_ids = page.ids
    callback_key = next(key for key in app.callback_map if page_ids.block("summary") in key)
    return app.server.test_client().post(
        "/_dash-update-component",
        json={
            "output": callback_key,
            "outputs": [{"id": page_ids.block("summary"), "property": "children"}],
            "inputs": [{"id": page_ids.control("book"), "property": "value", "value": value}],
            "changedPropIds": [f"{page_ids.control('book')}.value"],
            "state": [],
        },
    )


def test_renderer_extension_callback_semantics_match_vanilla_and_namespace() -> None:
    manifest = _manifest()
    calls: list[dict[str, object]] = []
    vanilla = render_dash_page(manifest, _definition(manifest, calls), SimpleNamespace(), namespace="vanilla")
    custom_renderer = FakeRenderer()
    custom = render_dash_page(
        manifest,
        _definition(manifest, calls),
        SimpleNamespace(),
        namespace="custom",
        renderer_extension=custom_renderer,
    )
    other = render_dash_page(
        manifest,
        _definition(manifest, calls),
        SimpleNamespace(),
        namespace="other",
        renderer_extension=FakeRenderer(),
    )
    assert vanilla.ids.block("summary") != custom.ids.block("summary")
    assert custom.ids.control("book") != other.ids.control("book")

    vanilla_app = Dash(__name__ + "_vanilla", use_pages=False)
    vanilla_app.layout = vanilla.layout()
    vanilla.register_callbacks(vanilla_app)
    custom_app = Dash(__name__ + "_custom", use_pages=False)
    custom_app.layout = custom.layout()
    custom.register_callbacks(custom_app)
    vanilla_response = _callback_response(vanilla_app, vanilla, "B")
    custom_response = _callback_response(custom_app, custom, "B")
    assert vanilla_response.status_code == custom_response.status_code == 200
    assert b'"children":"B"' in vanilla_response.data
    assert b'"children":"B"' in custom_response.data
    assert calls == [{"book": "B"}, {"book": "B"}]
