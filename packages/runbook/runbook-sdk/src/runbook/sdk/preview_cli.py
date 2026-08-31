from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from runbook.core.keying import build_context_hash
from runbook.core.pdl.models import PDLManifest
from runbook.data import open_blob_store, open_pointer_registry, resolve_snapshot
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import discover_report_definition
from runbook.sdk.execution import ReportResult, execute_report, load_report_module, resolve_code_version
from runbook.sdk.extensions.dash import DashPage, RouteResolver, render_dash_page
from runbook.sdk.live import LiveDataResolver
from runbook.sdk.live_sqlite import build_demo_live_provider
from runbook.sdk.logging import configure_logging
from runbook.sdk.profiles import ReportProfile, load_profiles, resolve_report_path

_PREVIEW_LOCATION_ID = "runbook-preview-location"
_PREVIEW_CONTENT_ID = "runbook-preview-content"


def _preview_route_resolver(kind: str, value: str) -> str | None:
    """Resolve only plot links for the local preview host."""
    from runbook.core.table import TableLinkKind

    if kind != TableLinkKind.plot.value or any(part in {".", ".."} for part in value.split("/")):
        return None
    encoded = "/".join(quote(part, safe="") for part in value.split("/"))
    return f"/plot/{encoded}"


def _preview_layout(page: DashPage, pathname: str | None) -> Any:
    """Resolve the local preview host route to a page layout."""
    from dash import html

    if pathname in {None, "", "/"}:
        return page.layout()
    if pathname.startswith("/plot/"):
        return page.plot_layout(unquote(pathname[len("/plot/") :]))
    return html.Div(f"Unable to resolve preview route {pathname!r}.", role="alert")


def _export_html_bundle(store: Any, result: ReportResult, output: Path) -> None:
    """Copy a report's main and linked HTML artifacts to a local bundle."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(store.get(result.html_ref))
    prefix = f"{result.prefix.rstrip('/')}/"
    for linked_ref in result.linked_html_refs:
        if not linked_ref.startswith(prefix):
            raise ValueError(f"linked HTML ref is outside report prefix: {linked_ref!r}")
        linked_output = output.parent / linked_ref[len(prefix) :]
        linked_output.parent.mkdir(parents=True, exist_ok=True)
        linked_output.write_bytes(store.get(linked_ref))


def compose_dash_app(
    *,
    store: Any,
    profile: ReportProfile,
    snapshot: Any,
    reports_root: str | Path = "reports",
    code_version: str,
    live: LiveDataResolver | None = None,
    route_resolver: RouteResolver | None = None,
) -> tuple[Any, ReportResult, DashPage]:
    """Execute one report and compose its DashPage into a host-owned app."""
    result = execute_report(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version=code_version,
        reports_root=reports_root,
        live=live,
    )
    module = load_report_module(resolve_report_path(profile.report_id, reports_root))
    definition = discover_report_definition(module)
    config = profile.execution_config()
    ctx = Ctx(
        snapshot=snapshot,
        store=store,
        artifact_store=store,
        report_id=profile.report_id,
        config=copy.deepcopy(config),
        code_version=code_version,
        context_hash=build_context_hash(config),
        artifact_prefix=result.prefix,
        live=live,
    )
    for name, function in definition.calc_fns.items():
        ctx.register_calc(name, function)
    manifest = PDLManifest.model_validate(store.get_json(result.stage3_ref))
    page = render_dash_page(
        manifest,
        definition,
        ctx,
        namespace=profile.profile_id,
        route_resolver=route_resolver,
    )
    from dash import Dash

    app = Dash(
        __name__ + "_interactive_preview",
        use_pages=False,
        suppress_callback_exceptions=route_resolver is not None,
    )
    if route_resolver is None:
        app.layout = page.layout()
    else:
        from dash import Input, Output, dcc, html

        app.layout = html.Div(
            [
                dcc.Location(id=_PREVIEW_LOCATION_ID, refresh=False),
                html.Div(page.layout(), id=_PREVIEW_CONTENT_ID),
            ]
        )

        @app.callback(Output(_PREVIEW_CONTENT_ID, "children"), Input(_PREVIEW_LOCATION_ID, "pathname"))
        def resolve_preview_route(pathname: str | None) -> Any:
            return _preview_layout(page, pathname)

    page.register_callbacks(app)
    return app, result, page


def _serve_interactive_app(app: Any, *, live: Any, host: str, port: int) -> None:
    """Run a development preview and always release an owned live provider."""
    try:
        app.run(host=host, port=port, debug=False)
    finally:
        if live is not None:
            live.close()


def main(argv: list[str] | None = None) -> int:
    """Render one profile against the latest snapshot for preview."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    interactive_subcommand = bool(raw_argv and raw_argv[0] == "interactive")
    if interactive_subcommand:
        raw_argv = raw_argv[1:]
    parser = argparse.ArgumentParser(prog="runbook-preview")
    parser.add_argument("profile_id")
    parser.add_argument("--profiles", default="data/contract/report_profiles.json")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--store", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--code-version", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--interactive", action="store_true", help="serve a development-only Dash preview")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8051)
    parser.add_argument("--demo-live", action="store_true", help="inject the deterministic local SQLite demo provider")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level: DEBUG, INFO, WARNING, or ERROR (default: RUNBOOK_LOG_LEVEL or INFO)",
    )
    args = parser.parse_args(raw_argv)
    interactive = interactive_subcommand or args.interactive
    configure_logging(args.log_level)
    profile = load_profiles(args.profiles).get(args.profile_id)
    if profile is None:
        parser.error(f"unknown profile: {args.profile_id}")
    store = open_blob_store(args.store)
    pointer_registry = open_pointer_registry(args.database)
    snapshot = resolve_snapshot(store, profile.datasets, pointer_registry=pointer_registry)
    if interactive:
        dash_mode = profile.extensions.get("modes", {}).get("dash", {})
        if not isinstance(dash_mode, dict) or not dash_mode.get("enabled", False):
            parser.error("interactive preview requires extensions.modes.dash.enabled=true")
        live = build_demo_live_provider() if args.demo_live else None
        try:
            app, _, _ = compose_dash_app(
                store=store,
                profile=profile,
                snapshot=snapshot,
                reports_root=args.reports_root,
                code_version=resolve_code_version(args.code_version),
                live=live,
                route_resolver=_preview_route_resolver,
            )
            _serve_interactive_app(app, live=live, host=args.host, port=args.port)
        finally:
            if live is not None and not live.closed:
                live.close()
        return 0
    result = execute_report(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version=resolve_code_version(args.code_version),
        reports_root=args.reports_root,
    )
    if args.output is not None:
        _export_html_bundle(store, result, args.output)
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
