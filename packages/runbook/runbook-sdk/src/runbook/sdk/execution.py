from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

from loguru import logger
from plotly.utils import PlotlyJSONEncoder
from pydantic import BaseModel, ConfigDict, Field
from runbook.core import BlobStore
from runbook.core.keying import build_context_hash
from runbook.core.pdl.models import PDLManifest, PDLSourceType, PDLStyle
from runbook.core.utils.hashing import sha256_json
from runbook.sdk.context import Ctx
from runbook.sdk.discovery import discover_report_definition
from runbook.sdk.html import DEFAULT_GRID_CSS, DEFAULT_GRID_CSS_REF, render_html
from runbook.sdk.layout import Report, compile_layout
from runbook.sdk.live import LiveDataResolver
from runbook.sdk.profiles import ReportProfile, resolve_report_path


class ReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    artifact_id: str
    snapshot_id: str
    context_hash: str
    code_version: str
    prefix: str
    html_ref: str
    stage3_ref: str
    stage4_ref: str
    cache_hits: dict[str, bool] = Field(default_factory=dict)


def load_report_module(path: str | Path) -> Any:
    """Load report module."""
    resolved = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"runbook_report_{resolved.stem}", resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load report module: {resolved}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_code_version(explicit: str | None = None) -> str:
    """Resolve code version."""
    if explicit:
        value = str(explicit)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", value):
            raise ValueError(f"invalid code version: {value!r}")
        return value
    import os

    from_env = os.environ.get("RUNBOOK_CODE_VERSION")
    if from_env:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", from_env):
            raise ValueError(f"invalid code version: {from_env!r}")
        return from_env
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("code version is required; pass --code-version or set RUNBOOK_CODE_VERSION") from exc
    value = result.stdout.strip()
    if not value:
        raise RuntimeError("git returned an empty code version")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", value):
        raise ValueError(f"invalid code version: {value!r}")
    return value


def _sdk_version(explicit: str | None) -> str:
    """Resolve and validate the SDK distribution version used in artifact paths."""
    if explicit:
        value = explicit
    else:
        try:
            value = distribution_version("runbook-sdk")
        except PackageNotFoundError as exc:
            raise RuntimeError("runbook-sdk package version is unavailable") from exc
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", value):
        raise ValueError(f"invalid runbook-sdk package version: {value!r}")
    return value


def _report_prefix(
    store: BlobStore,
    *,
    report_id: str,
    generation_date: str,
    platform_version: str,
    identity: dict[str, str],
) -> str:
    """Reuse the revision for an identical identity or allocate the next one."""
    base = f"reports/{report_id}/date={generation_date}/version={platform_version}"
    revision = 1
    while True:
        prefix = f"{base}/{revision}"
        identity_ref = f"{prefix}/identity.json"
        if not store.exists(identity_ref):
            store.put_immutable(
                identity_ref,
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(),
            )
            return prefix
        if store.get_json(identity_ref) == identity:
            return prefix
        revision += 1


def execute_report(
    *,
    store: BlobStore,
    data_store: BlobStore | None = None,
    profile: ReportProfile,
    snapshot: Any,
    code_version: str,
    reports_root: str | Path = "reports",
    use_cache: bool = True,
    generated_at: datetime | None = None,
    platform_version: str | None = None,
    live: LiveDataResolver | None = None,
) -> ReportResult:
    """Execute a report's Stage 3 manifest and Stage 4 HTML publication."""
    logger.info(
        "stage=3 start report={} snapshot={} code={}",
        profile.report_id,
        snapshot.snapshot_id,
        code_version,
    )
    config = profile.execution_config()
    original_config = copy.deepcopy(config)
    context_hash = build_context_hash(config)
    artifact_id = sha256_json(
        {
            "report_id": profile.report_id,
            "snapshot_id": snapshot.snapshot_id,
            "code_version": code_version,
            "context_hash": context_hash,
        }
    )
    module = load_report_module(resolve_report_path(profile.report_id, reports_root))
    definition = discover_report_definition(module)
    aliases = sorted(profile.datasets)
    if aliases != definition.aliases:
        raise ValueError(f"report aliases do not match profile: required={definition.aliases}, configured={aliases}")
    generated = generated_at or datetime.now(timezone.utc)
    if generated.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    generation_date = generated.astimezone(timezone.utc).date().isoformat()
    resolved_platform_version = _sdk_version(platform_version)
    prefix = _report_prefix(
        store,
        report_id=profile.report_id,
        generation_date=generation_date,
        platform_version=resolved_platform_version,
        identity={
            "artifact_id": artifact_id,
            "code_version": code_version,
            "context_hash": context_hash,
            "generation_date": generation_date,
            "platform_version": resolved_platform_version,
            "report_id": profile.report_id,
            "snapshot_id": snapshot.snapshot_id,
        },
    )
    ctx = Ctx(
        snapshot=snapshot,
        store=data_store or store,
        artifact_store=store,
        report_id=profile.report_id,
        config=config,
        code_version=code_version,
        context_hash=context_hash,
        artifact_prefix=prefix,
        use_cache=use_cache,
        live=live,
    )
    for name, function in definition.calc_fns.items():
        ctx.register_calc(name, function)
    result = definition.page_fn(ctx)
    if isinstance(result, Report):
        result = compile_layout(ctx, result)
    if (
        ctx.config != original_config
        or ctx.context_hash != context_hash
        or build_context_hash(ctx.config) != context_hash
    ):
        raise ValueError("report code mutated execution config or context hash")
    if not isinstance(result, PDLManifest):
        raise TypeError("report page must return a pdl-core/0.1 or pdl-core/0.2 PDLManifest")
    # Snapshot notices are authoritative: report code cannot hide an immutable
    # warning or add a misleading authored replacement.
    manifest = result.model_copy(
        update={
            "snapshot_id": snapshot.snapshot_id,
            "as_of": snapshot.watermark,
            "warnings": tuple(getattr(snapshot, "warnings", ()) or ()),
        }
    )
    payloads = ctx.artifact.payloads()
    for ref, payload in sorted(payloads.plot_jsons.items()):
        store.put_immutable(
            f"{prefix}/{ref}",
            json.dumps(payload, cls=PlotlyJSONEncoder, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
    for ref, payload in sorted(payloads.table_styles.items()):
        store.put_immutable(
            f"{prefix}/{ref}",
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )
    for ref, payload in sorted(payloads.table_htmls.items()):
        store.put_immutable(f"{prefix}/{ref}", payload.encode("utf-8"))
    stage3_ref = f"{prefix}/manifest.stage3.json"
    store.put_immutable(
        stage3_ref,
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode(),
    )
    logger.info("stage=3 manifest report={} ref={}", profile.report_id, stage3_ref)
    stage4_manifest = PDLManifest.model_validate(store.get_json(stage3_ref))
    if stage4_manifest.style is None:
        store.put_immutable(f"{prefix}/{DEFAULT_GRID_CSS_REF}", DEFAULT_GRID_CSS.encode("utf-8"))
        stage4_manifest = manifest.model_copy(
            update={
                "style": PDLStyle(
                    css_ref=DEFAULT_GRID_CSS_REF,
                    source_type=PDLSourceType.default,
                    source_key="simple_grid",
                )
            }
        )
    html_ref = f"{prefix}/report.html"
    logger.info("stage=4 render report={} prefix={}", profile.report_id, prefix)
    store.put_immutable(html_ref, render_html(store, stage4_manifest, prefix).encode("utf-8"))
    stage4_ref = f"{prefix}/manifest.stage4.json"
    store.put_immutable(
        stage4_ref,
        json.dumps(
            stage4_manifest.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    logger.info(
        "stage=4 complete report={} html_ref={} manifest_ref={}",
        profile.report_id,
        html_ref,
        stage4_ref,
    )
    return ReportResult(
        report_id=profile.report_id,
        artifact_id=artifact_id,
        snapshot_id=snapshot.snapshot_id,
        context_hash=context_hash,
        code_version=code_version,
        prefix=prefix,
        html_ref=html_ref,
        stage3_ref=stage3_ref,
        stage4_ref=stage4_ref,
        cache_hits=dict(ctx.cache_hits),
    )
