"""Host-owned composition helpers for interactive previews."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from runbook.core.keying import build_context_hash
from runbook.core.pdl.models import PDLManifest
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import discover_report_definition
from runbook.sdk.execution import ReportResult, execute_report, load_report_module
from runbook.sdk.extensions.dash import DashPage, DashRendererExtension, RouteResolver, render_dash_page
from runbook.sdk.live import LiveDataResolver
from runbook.sdk.profiles import ReportProfile, resolve_report_path


def compose_report_page(
    *,
    store: Any,
    data_store: Any | None = None,
    profile: ReportProfile,
    snapshot: Any,
    code_version: str,
    reports_root: str | Path = "reports",
    live: LiveDataResolver | None = None,
    renderer_extension: DashRendererExtension | None = None,
    route_resolver: RouteResolver | None = None,
) -> tuple[ReportResult, DashPage]:
    """Execute static report artifacts and compose a callback-capable page.

    ``execute_report`` deliberately receives no live provider: immutable Stage
    3/4 products stay snapshot-only.  The separate callback context receives
    the host-injected provider.
    """
    result = execute_report(
        store=store,
        data_store=data_store,
        profile=profile,
        snapshot=snapshot,
        code_version=code_version,
        reports_root=reports_root,
    )
    module = load_report_module(resolve_report_path(profile.report_id, reports_root))
    definition = discover_report_definition(module)
    config = profile.execution_config()
    ctx = Ctx(
        snapshot=snapshot,
        store=data_store or store,
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
    return result, render_dash_page(
        manifest,
        definition,
        ctx,
        namespace=profile.profile_id,
        renderer_extension=renderer_extension,
        route_resolver=route_resolver,
    )


__all__ = ["compose_report_page"]
