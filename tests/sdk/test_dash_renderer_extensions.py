from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from dash import Dash, dcc, html
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash import (
    DashPage,
    DashRenderedControl,
    dashboard,
    date_range,
    interaction,
    multi_select,
    render_dash_page,
    select,
    toggle,
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


def _controls_manifest(*, interactions: list[Any] | None = None) -> PDLManifest:
    return PDLManifest(
        title="Controls",
        snapshot_id="s",
        as_of="2024-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[
                PDLTextBlock(name="summary", title="Summary", text="initial", row=1, col=1),
                PDLTextBlock(name="summary-2", title="Summary 2", text="initial", row=1, col=1),
            ],
        ),
        extensions={
            "dash": dashboard(
                controls=[
                    select("vanilla", options=["A", "B"]),
                    select("choice", options=[1, True, "short"]),
                    multi_select("tags", options=[1, True, "short"]),
                    date_range("dates"),
                    toggle("enabled"),
                ],
                interactions=interactions or [interaction(handler="update", inputs=["vanilla"], outputs=["summary"])],
            ).model_dump(mode="json")
        },
    )


def _callback_inputs(app: Dash, page: DashPage) -> list[tuple[str, str]]:
    callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
    return [(item["id"], item["property"]) for item in app.callback_map[callback_key]["inputs"]]


def test_vanilla_bindings_preserve_properties_and_logical_state() -> None:
    captured: list[dict[str, object]] = []
    manifest = _controls_manifest(
        interactions=[
            interaction(
                handler="update",
                inputs=["vanilla", "choice", "tags", "dates", "enabled"],
                outputs=["summary"],
            )
        ]
    )

    def update(_ctx: object, state: dict[str, object]) -> dict[str, str]:
        captured.append(state)
        return {"summary": "updated"}

    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _ctx: manifest, {"update": update}),
        SimpleNamespace(),
        namespace="vanilla-bindings",
    )
    app = Dash(__name__ + "_vanilla_bindings", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)

    def expected_id(name: str) -> str:
        return page.ids.control(name)

    assert _callback_inputs(app, page) == [
        (expected_id("vanilla"), "value"),
        (expected_id("choice"), "value"),
        (expected_id("tags"), "value"),
        (expected_id("dates"), "start_date"),
        (expected_id("dates"), "end_date"),
        (expected_id("enabled"), "value"),
    ]
    callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
    app.callback_map[callback_key]["callback"](
        "B",
        True,
        ["short", 1],
        "2026-01-01",
        "2026-01-31",
        [True],
        outputs_list=[{"id": page.ids.block("summary"), "property": "children"}],
    )
    assert captured == [
        {
            "vanilla": "B",
            "choice": True,
            "tags": ["short", 1],
            "dates": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "enabled": [True],
        }
    ]


class _BindingRenderer:
    def __init__(self) -> None:
        self.control_calls = 0

    def wrap_page(self, content: Any, *, manifest: PDLManifest, namespace: str) -> Any | None:
        return None

    def render_control(
        self,
        control: Any,
        *,
        component_id: str,
        options: list[object] | None,
    ) -> Any | None:
        self.control_calls += 1
        if control.name == "vanilla":
            return None
        if control.name == "choice":
            return DashRenderedControl(
                dcc.Input(id=component_id),
                ("value",),
                lambda values: json.loads(values[0].removeprefix("runbook-value:")),
            )
        if control.name == "tags":
            return DashRenderedControl(
                dcc.Input(id=component_id),
                ("value",),
                lambda values: [json.loads(value.removeprefix("runbook-value:")) for value in values[0]],
            )
        if control.name == "dates":
            return DashRenderedControl(
                dcc.Input(id=component_id),
                ("value",),
                lambda values: {"start_date": values[0][0], "end_date": values[0][1]},
            )
        if control.name == "enabled":
            return DashRenderedControl(
                dcc.Input(id=component_id),
                ("checked",),
                lambda values: [True] if values[0] else [],
            )
        raise AssertionError(control.name)

    def wrap_block(
        self,
        body: Any,
        *,
        block: Any,
        title: Any | None,
        namespace: str,
    ) -> Any | None:
        return None


def test_custom_bindings_decode_values_and_mix_with_vanilla_controls() -> None:
    captured: list[dict[str, object]] = []
    manifest = _controls_manifest(
        interactions=[
            interaction(
                handler="update",
                inputs=["vanilla", "choice", "tags", "dates", "enabled"],
                outputs=["summary"],
            )
        ]
    )

    def update(_ctx: object, state: dict[str, object]) -> dict[str, str]:
        captured.append(state)
        return {"summary": "updated"}

    renderer = _BindingRenderer()
    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _ctx: manifest, {"update": update}),
        SimpleNamespace(),
        namespace="custom-bindings",
        renderer_extension=renderer,
    )
    app = Dash(__name__ + "_custom_bindings", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)
    assert renderer.control_calls == 5
    assert _callback_inputs(app, page) == [
        (page.ids.control("vanilla"), "value"),
        (page.ids.control("choice"), "value"),
        (page.ids.control("tags"), "value"),
        (page.ids.control("dates"), "value"),
        (page.ids.control("enabled"), "checked"),
    ]
    callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
    app.callback_map[callback_key]["callback"](
        "B",
        "runbook-value:true",
        ['runbook-value:"short"', "runbook-value:1"],
        ["2026-01-01", "2026-01-31"],
        True,
        outputs_list=[{"id": page.ids.block("summary"), "property": "children"}],
    )
    assert captured == [
        {
            "vanilla": "B",
            "choice": True,
            "tags": ["short", 1],
            "dates": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "enabled": [True],
        }
    ]


def test_custom_binding_identity_decoder_reaches_handler() -> None:
    captured: list[dict[str, object]] = []
    manifest = _controls_manifest(interactions=[interaction(handler="update", inputs=["choice"], outputs=["summary"])])

    class IdentityRenderer(_BindingRenderer):
        def render_control(self, control: Any, *, component_id: str, options: list[object] | None) -> Any | None:
            if control.name == "choice":
                return DashRenderedControl(dcc.Input(id=component_id), ("value",))
            return None

    def update(_ctx: object, state: dict[str, object]) -> dict[str, str]:
        captured.append(state)
        return {"summary": "updated"}

    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _ctx: manifest, {"update": update}),
        SimpleNamespace(),
        namespace="identity-binding",
        renderer_extension=IdentityRenderer(),
    )
    app = Dash(__name__ + "_identity_binding", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)
    callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
    app.callback_map[callback_key]["callback"](
        7,
        outputs_list=[{"id": page.ids.block("summary"), "property": "children"}],
    )
    assert captured == [{"choice": 7}]


def test_plain_custom_date_range_and_toggle_keep_vanilla_state_contract() -> None:
    captured: list[dict[str, object]] = []
    manifest = _controls_manifest(
        interactions=[interaction(handler="update", inputs=["dates", "enabled"], outputs=["summary"])]
    )

    class PlainDateToggleRenderer(_BindingRenderer):
        def render_control(self, control: Any, *, component_id: str, options: list[object] | None) -> Any | None:
            if control.name in {"dates", "enabled"}:
                return dcc.Input(id=component_id)
            return None

    def update(_ctx: object, state: dict[str, object]) -> dict[str, str]:
        captured.append(state)
        return {"summary": "updated"}

    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _ctx: manifest, {"update": update}),
        SimpleNamespace(),
        namespace="plain-date-toggle",
        renderer_extension=PlainDateToggleRenderer(),
    )
    app = Dash(__name__ + "_plain_date_toggle", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)
    assert _callback_inputs(app, page) == [
        (page.ids.control("dates"), "start_date"),
        (page.ids.control("dates"), "end_date"),
        (page.ids.control("enabled"), "value"),
    ]
    callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
    app.callback_map[callback_key]["callback"](
        "2026-01-01",
        "2026-01-31",
        [True],
        outputs_list=[{"id": page.ids.block("summary"), "property": "children"}],
    )
    assert captured == [
        {
            "dates": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "enabled": [True],
        }
    ]


def test_custom_binding_metadata_is_reused_across_interactions() -> None:
    manifest = _controls_manifest(
        interactions=[
            interaction(handler="update-1", inputs=["choice"], outputs=["summary"]),
            interaction(handler="update-2", inputs=["choice"], outputs=["summary-2"]),
        ]
    )
    renderer = _BindingRenderer()
    page = render_dash_page(
        manifest,
        ReportDefinition(
            [],
            {},
            lambda _ctx: manifest,
            {
                "update-1": lambda _ctx, _state: {"summary": "ok"},
                "update-2": lambda _ctx, _state: {"summary-2": "ok"},
            },
        ),
        SimpleNamespace(),
        namespace="reused-binding",
        renderer_extension=renderer,
    )
    app = Dash(__name__ + "_reused_binding", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)

    assert renderer.control_calls == 5
    callback_inputs = [
        callback["inputs"]
        for callback in app.callback_map.values()
        if callback["inputs"] == [{"id": page.ids.control("choice"), "property": "value"}]
    ]
    assert len(callback_inputs) == 2


@pytest.mark.parametrize(
    ("properties", "decode", "message"),
    [
        ((), None, "has no input properties"),
        (("value", "value"), lambda values: values[0], "duplicate input properties"),
        (("start", "end"), None, "multiple input properties but no decoder"),
    ],
)
def test_invalid_custom_bindings_fail_with_control_name(properties: tuple[str, ...], decode: Any, message: str) -> None:
    manifest = _controls_manifest(interactions=[interaction(handler="update", inputs=["choice"], outputs=["summary"])])

    class InvalidRenderer(_BindingRenderer):
        def render_control(self, control: Any, *, component_id: str, options: list[object] | None) -> Any | None:
            if control.name == "choice":
                return DashRenderedControl(dcc.Input(id=component_id), properties, decode)
            return None

    with pytest.raises(ValueError, match=rf"Custom Dash control 'choice'.*{message}"):
        render_dash_page(
            manifest,
            ReportDefinition([], {}, lambda _ctx: manifest, {"update": lambda _ctx, _state: {"summary": "ok"}}),
            SimpleNamespace(),
            namespace="invalid-binding",
            renderer_extension=InvalidRenderer(),
        )


@pytest.mark.parametrize(
    ("control_name", "property_name", "decoded", "message"),
    [
        ("dates", "value", "not-a-date-range", "mapping with exactly"),
        ("enabled", "checked", [1], "must return \\[\\] or \\[True\\]"),
    ],
)
def test_custom_decoder_preserves_fixed_logical_control_contract(
    control_name: str, property_name: str, decoded: Any, message: str
) -> None:
    manifest = _controls_manifest(
        interactions=[interaction(handler="update", inputs=[control_name], outputs=["summary"])]
    )

    class InvalidLogicalRenderer(_BindingRenderer):
        def render_control(self, control: Any, *, component_id: str, options: list[object] | None) -> Any | None:
            if control.name == control_name:
                return DashRenderedControl(dcc.Input(id=component_id), (property_name,), lambda _values: decoded)
            return None

    page = render_dash_page(
        manifest,
        ReportDefinition([], {}, lambda _ctx: manifest, {"update": lambda _ctx, _state: {"summary": "ok"}}),
        SimpleNamespace(),
        namespace="invalid-logical-binding",
        renderer_extension=InvalidLogicalRenderer(),
    )
    app = Dash(__name__ + "_invalid_logical_binding", use_pages=False)
    app.layout = page.layout()
    page.register_callbacks(app)
    callback_key = next(key for key in app.callback_map if page.ids.block("summary") in key)
    with pytest.raises(ValueError, match=rf"Custom Dash control {control_name!r}.*{message}"):
        app.callback_map[callback_key]["callback"](
            ["2026-01-01", "2026-01-31"] if control_name == "dates" else True,
            outputs_list=[{"id": page.ids.block("summary"), "property": "children"}],
        )


def test_dash_rendered_control_is_frozen_and_publicly_importable() -> None:
    rendered = DashRenderedControl(component="component", input_properties=("value",))
    assert rendered.component == "component"
    with pytest.raises(AttributeError):
        rendered.component = "other"  # type: ignore[misc]
