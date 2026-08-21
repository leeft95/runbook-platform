"""Validation for the small pdl-dash extension graph."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd
from runbook.core.pdl.models import PDLManifest
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash.models import DashExtension, DatasetValues

SUPPORTED_SCHEMA_VERSION = "pdl-dash/0.1"


def parse_dash_extension(manifest: PDLManifest | Mapping[str, Any]) -> DashExtension | None:
    """Parse the optional dash namespace, leaving unsupported namespaces alone."""
    raw_extensions = manifest.extensions if isinstance(manifest, PDLManifest) else manifest.get("extensions")
    if not isinstance(raw_extensions, Mapping) or "dash" not in raw_extensions:
        return None
    raw = raw_extensions["dash"]
    if isinstance(raw, DashExtension):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("PDL extension 'dash' must be an object")
    try:
        extension = DashExtension.from_manifest(dict(raw))
    except Exception as exc:
        raise ValueError(f"invalid pdl-dash extension: {exc}") from exc
    if extension.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"unsupported pdl-dash schema version: {extension.schema_version!r}")
    return extension


def validate_dash_manifest(
    manifest: PDLManifest,
    extension: DashExtension | None,
    definition: ReportDefinition,
) -> None:
    """Validate extension references before layout or callback registration."""
    if extension is None:
        return
    if extension.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"unsupported pdl-dash schema version: {extension.schema_version!r}")

    control_names = [control.name for control in extension.controls]
    if len(control_names) != len(set(control_names)):
        raise ValueError("dash control names must be unique")
    interaction_names = [item.handler for item in extension.interactions]
    if len(interaction_names) != len(set(interaction_names)):
        raise ValueError("dash interaction handler names must be unique")

    block_names = {block.name for block in manifest.page.blocks}
    known_controls = set(control_names)
    known_handlers = set((definition.interaction_fns or {}).keys())
    owned_outputs: dict[str, str] = {}
    for item in extension.interactions:
        for input_name in item.inputs:
            if input_name not in known_controls:
                raise ValueError(f"Dash interaction {item.handler!r} references unknown control {input_name!r}")
        if item.handler not in known_handlers:
            raise ValueError(f"Dash interaction handler {item.handler!r} is not registered")
        for output_name in item.outputs:
            if output_name not in block_names:
                raise ValueError(f"Dash interaction {item.handler!r} references unknown output {output_name!r}")
            previous = owned_outputs.get(output_name)
            if previous is not None:
                raise ValueError(f"PDL output {output_name!r} is owned by both {previous!r} and {item.handler!r}")
            owned_outputs[output_name] = item.handler


def resolve_dataset_values(
    option: DatasetValues,
    dataset_loader: Callable[[str], pd.DataFrame],
) -> list[Any]:
    """Resolve distinct control options from the pinned snapshot dataset."""
    frame = dataset_loader(option.alias)
    if option.column not in frame.columns:
        raise ValueError(f"dataset option column {option.column!r} is not present in alias {option.alias!r}")
    values = frame[option.column].dropna().drop_duplicates().tolist()
    try:
        return sorted(values)
    except TypeError:
        return sorted(values, key=lambda value: str(value))


__all__ = ["parse_dash_extension", "resolve_dataset_values", "validate_dash_manifest"]
