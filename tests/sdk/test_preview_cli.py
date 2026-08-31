from __future__ import annotations

import re
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Any
from urllib.parse import unquote

import runbook.sdk.preview_cli as preview_cli
from dash import html
from runbook.core.pdl.models import PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.execution import ReportResult
from runbook.sdk.extensions.dash import DashPage
from runbook.sdk.profiles import ReportProfile

from tests.sdk.test_linked_table_report import _run


def _result(*, prefix: str, linked_html_refs: tuple[str, ...] = ()) -> ReportResult:
    return ReportResult(
        report_id="report",
        artifact_id="artifact",
        snapshot_id="snapshot",
        context_hash="context",
        code_version="code",
        prefix=prefix,
        html_ref=f"{prefix}/report.html",
        stage3_ref=f"{prefix}/manifest.stage3.json",
        stage4_ref=f"{prefix}/manifest.stage4.json",
        linked_html_refs=linked_html_refs,
    )


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.hrefs.extend(value for name, value in attrs if name == "href" and value is not None)


def test_static_preview_exports_every_linked_page_with_relative_hrefs(tmp_path, pointer_registry, monkeypatch) -> None:
    store, snapshot, profile, result = _run(tmp_path / "store", pointer_registry)
    output = tmp_path / "export" / "report.html"
    monkeypatch.setattr(preview_cli, "load_profiles", lambda _path: {profile.profile_id: profile})
    monkeypatch.setattr(preview_cli, "open_blob_store", lambda _uri: store)
    monkeypatch.setattr(preview_cli, "open_pointer_registry", lambda _url: pointer_registry)
    monkeypatch.setattr(preview_cli, "resolve_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(preview_cli, "execute_report", lambda **_kwargs: result)

    assert preview_cli.main([profile.profile_id, "--output", str(output), "--code-version", "golden"]) == 0

    parser = _HrefParser()
    parser.feed(output.read_text(encoding="utf-8"))
    hrefs = {href for href in parser.hrefs if href.startswith("plots/") and href.endswith(".html")}
    expected = {ref.removeprefix(f"{result.prefix}/") for ref in result.linked_html_refs}
    assert hrefs == expected
    assert {"plots/asset-price-line.html", "plots/asset-volume-line.html", "plots/asset-plots.html"} <= hrefs
    assert all((output.parent / href).is_file() for href in hrefs)


def test_static_preview_without_linked_pages_does_not_create_plots_directory(tmp_path, monkeypatch) -> None:
    prefix = "reports/report/1"
    output = tmp_path / "report.html"
    store = SimpleNamespace(get=lambda ref: b"main" if ref == f"{prefix}/report.html" else b"")
    profile = ReportProfile(profile_id="profile", report_id="report", datasets={"data": "data"})
    monkeypatch.setattr(preview_cli, "load_profiles", lambda _: {"profile": profile})
    monkeypatch.setattr(preview_cli, "open_blob_store", lambda _: store)
    monkeypatch.setattr(preview_cli, "open_pointer_registry", lambda _: None)
    monkeypatch.setattr(preview_cli, "resolve_snapshot", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(preview_cli, "execute_report", lambda **_kwargs: _result(prefix=prefix))

    assert preview_cli.main(["profile", "--output", str(output), "--code-version", "code"]) == 0

    assert output.read_bytes() == b"main"
    assert not (tmp_path / "plots").exists()


def test_preview_host_routes_root_plots_and_unknown_paths() -> None:
    seen: list[str] = []

    def plot_layout(name: str):
        seen.append(name)
        return html.Div(name)

    page = DashPage(
        layout_factory=lambda: html.Div("root"),
        callback_registrar=lambda _app: None,
        namespace="preview",
        plot_layout_factory=plot_layout,
    )

    assert _children(preview_cli._preview_layout(page, "/")) == "root"
    assert _children(preview_cli._preview_layout(page, "/plot/asset%20price")) == "asset price"
    assert seen == ["asset price"]
    unknown = preview_cli._preview_layout(page, "/other")
    assert unknown.role == "alert"


def _children(component: object) -> object:
    return getattr(component, "children")


def _preview_callback(client: Any, pathname: str) -> Any:
    return client.post(
        "/_dash-update-component",
        json={
            "output": f"{preview_cli._PREVIEW_CONTENT_ID}.children",
            "outputs": {"id": preview_cli._PREVIEW_CONTENT_ID, "property": "children"},
            "inputs": [{"id": preview_cli._PREVIEW_LOCATION_ID, "property": "pathname", "value": pathname}],
            "changedPropIds": [f"{preview_cli._PREVIEW_LOCATION_ID}.pathname"],
            "state": [],
        },
    )


def test_preview_route_resolver_only_owns_encoded_plot_routes() -> None:
    assert preview_cli._preview_route_resolver("plot", "asset/a b") == "/plot/asset/a%20b"
    assert preview_cli._preview_route_resolver("report", "detail") is None
    assert preview_cli._preview_route_resolver("url", "https://example.test") is None
    assert preview_cli._preview_route_resolver("plot", "asset/..") is None


def test_compose_dash_app_registers_preview_host_boundary(monkeypatch) -> None:
    manifest = PDLManifest(
        title="Preview",
        snapshot_id="snapshot",
        as_of="2026-01-01T00:00:00Z",
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", text="body", row=1, col=1)],
        ),
    )
    # DashPage is frozen; keep the callback assertion in a mutable side channel.
    registered: list[bool] = []
    page = DashPage(
        layout_factory=lambda: html.Div("root"),
        callback_registrar=lambda _app: registered.append(True),
        namespace="preview-host",
        plot_layout_factory=lambda name: html.Div(name),
    )
    result = _result(prefix="reports/report/1")
    profile = ReportProfile(profile_id="profile", report_id="report", datasets={"data": "data"})
    store = SimpleNamespace(get_json=lambda _ref: manifest.model_dump(mode="json"))
    monkeypatch.setattr(preview_cli, "execute_report", lambda **_kwargs: result)
    monkeypatch.setattr(preview_cli, "resolve_report_path", lambda *_args: "reports/report.py")
    monkeypatch.setattr(preview_cli, "load_report_module", lambda _path: SimpleNamespace())
    monkeypatch.setattr(
        preview_cli,
        "discover_report_definition",
        lambda _module: ReportDefinition([], {}, lambda _: manifest, {}),
    )
    monkeypatch.setattr(preview_cli, "render_dash_page", lambda *_args, **_kwargs: page)

    app, _, _ = preview_cli.compose_dash_app(
        store=store,
        profile=profile,
        snapshot=SimpleNamespace(snapshot_id="snapshot", watermark=None),
        code_version="code",
        route_resolver=preview_cli._preview_route_resolver,
    )

    assert registered == [True]
    assert app.layout.children[0].refresh is False
    client = app.server.test_client()
    routes = (
        ("/", b"root"),
        ("/plot/asset%20price", b"asset price"),
        ("/unknown", b"Unable to resolve preview route"),
    )
    for pathname, expected in routes:
        response = _preview_callback(client, pathname)
        assert response.status_code == 200
        assert expected in response.data


def test_preview_host_follows_renderer_plot_href_to_plot_layout(tmp_path, pointer_registry, monkeypatch) -> None:
    store, snapshot, profile, result = _run(tmp_path / "store", pointer_registry)
    monkeypatch.setattr(preview_cli, "execute_report", lambda **_kwargs: result)

    app, _, page = preview_cli.compose_dash_app(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version="golden",
        route_resolver=preview_cli._preview_route_resolver,
    )
    rendered = str(page.layout())
    match = re.search(r"href=['\"](/plot/[^'\"]+)['\"]", rendered)
    assert match is not None
    pathname = match.group(1)
    assert "Unable to resolve report route" in rendered
    assert "https://example.com/prices/00" in rendered
    assert "Link(children='Asset', href='/plot/asset-plots')" in rendered

    client = app.server.test_client()
    empty_response = _preview_callback(client, "")
    assert empty_response.status_code == 200
    assert page.ids.block("linked_prices").encode() in empty_response.data

    root_response = _preview_callback(client, "/")
    assert root_response.status_code == 200
    assert page.ids.block("linked_prices").encode() in root_response.data

    aggregate_response = _preview_callback(client, "/plot/asset-plots")
    assert aggregate_response.status_code == 200
    assert b"asset-plots" in aggregate_response.data
    assert page.ids.block("linked_prices").encode() not in aggregate_response.data

    missing_response = _preview_callback(client, "/plot/missing")
    assert missing_response.status_code == 200
    assert b"not registered" in missing_response.data

    response = _preview_callback(client, pathname)
    assert response.status_code == 200
    plot_name = unquote(pathname.removeprefix("/plot/"))
    assert page.plot_layout(plot_name).children[1].__class__.__name__ == "Graph"
    assert plot_name.encode() in response.data
    assert page.ids.block("linked_prices").encode() not in response.data
