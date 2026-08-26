"""Static-first PDL to embeddable DashPage rendering."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import pyarrow as pa
from runbook.core.pdl.models import PDLColumn, PDLColumnRole, PDLManifest, PDLPlotRefBlock, PDLTableBlock, PDLTextBlock
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash.ids import DashIds
from runbook.sdk.extensions.dash.models import (
    DashDateRange,
    DashExtension,
    DashMultiSelect,
    DashSelect,
    DashToggle,
    DatasetValues,
)
from runbook.sdk.extensions.dash.page import DashPage
from runbook.sdk.extensions.dash.tables import ag_grid_default_col_def, build_ag_grid_column_defs
from runbook.sdk.extensions.dash.validation import (
    parse_dash_extension,
    resolve_dataset_values,
    validate_dash_manifest,
)
from runbook.sdk.ui import merge_columns


def render_dash_page(
    manifest: PDLManifest,
    definition: ReportDefinition,
    ctx: Any,
    *,
    namespace: str,
) -> DashPage:
    """Render a canonical PDL manifest into an embeddable, namespaced page."""
    extension = parse_dash_extension(manifest)
    validate_dash_manifest(manifest, extension, definition)
    ids = DashIds(namespace)
    controls = _build_controls(extension, ctx, ids) if extension else []
    components = _build_components(manifest, ctx, ids)

    def layout_factory() -> Any:
        """Build the page layout without creating or owning a Dash app."""
        from dash import html

        columns = manifest.page.columns or 1
        children = [html.H1(manifest.title), _warning_component(manifest)]
        if controls:
            children.append(html.Div(controls))
        children.append(
            html.Div(
                components,
                style={
                    "display": "grid",
                    "gridTemplateColumns": f"repeat({columns}, minmax(0, 1fr))",
                    "gap": "16px",
                },
            )
        )
        return html.Div(children)

    def callback_registrar(app: Any) -> None:
        """Register this page's callbacks on the host-owned app."""
        _register_callbacks(app, manifest, extension, definition, ctx, ids)

    return DashPage(layout_factory=layout_factory, callback_registrar=callback_registrar, namespace=namespace)


def _warning_component(manifest: PDLManifest) -> Any:
    """Render immutable snapshot warnings outside the report grid."""
    if not manifest.warnings:
        return None
    from dash import html

    return html.Div(
        [html.Strong("Warnings"), html.Ul([html.Li(warning) for warning in manifest.warnings])],
        role="alert",
        style={
            "border": "2px solid #b45309",
            "borderRadius": "8px",
            "padding": "10px 14px",
            "marginBottom": "16px",
            "background": "#fff7ed",
            "color": "#7c2d12",
        },
    )


def _build_components(manifest: PDLManifest, ctx: Any, ids: DashIds) -> list[Any]:
    """Translate PDL blocks to Dash components and place them in the PDL grid."""
    import dash_ag_grid as dag
    from dash import dcc, html

    components: list[Any] = []
    for block in manifest.page.blocks:
        title = html.H2(block.title) if block.title else None
        body: Any
        if isinstance(block, PDLTextBlock):
            body = (
                dcc.Markdown(block.text, id=ids.block(block.name))
                if block.format == "markdown"
                else html.Pre(block.text, id=ids.block(block.name))
            )
        elif isinstance(block, PDLPlotRefBlock):
            body = dcc.Graph(id=ids.block(block.name), figure=_read_json(ctx, block.ref))
        elif isinstance(block, PDLTableBlock):
            frame = _read_table(ctx, block.data_ref)
            # pandas' restored index is intentionally not part of rowData. Derive
            # the renderer schema from the same logical columns to avoid exposing
            # parquet's synthetic __index_level_0__ field in AG Grid.
            schema = pa.Schema.from_pandas(frame, preserve_index=False)
            body = dag.AgGrid(
                id=ids.block(block.name),
                rowData=_records(frame, block.columns),
                columnDefs=build_ag_grid_column_defs(schema, block.columns),
                defaultColDef=ag_grid_default_col_def(),
                dashGridOptions={"sideBar": "columns"},
                # Phase C uses client-side grouping/pivot/value aggregation in
                # local preview. Formatter functions use only Dash AG Grid's
                # trusted preloaded d3 namespace; PDL has no JS escape hatch.
                enableEnterpriseModules=True,
            )
        else:
            raise ValueError(f"unsupported PDL block type: {block.type!r}")
        position = {
            "gridRow": f"{block.row} / span {block.row_span}",
            "gridColumn": f"{block.col} / span {block.col_span}",
        }
        children = [item for item in (title, body) if item is not None]
        components.append(html.Section(children, id=ids.block(block.name) + "-container", style=position))
    return components


def _build_controls(extension: DashExtension, ctx: Any, ids: DashIds) -> list[Any]:
    """Translate the small supported control set to Dash inputs."""
    from dash import dcc, html

    controls: list[Any] = []
    for control in extension.controls:
        label = html.Label(control.label or control.name, htmlFor=ids.control(control.name))
        widget: Any
        if isinstance(control, DashSelect):
            options = _options(control.options, ctx)
            widget = dcc.Dropdown(
                id=ids.control(control.name),
                options=options,
                value=control.value,
                clearable=True,
            )
        elif isinstance(control, DashMultiSelect):
            options = _options(control.options, ctx)
            widget = dcc.Dropdown(
                id=ids.control(control.name),
                options=options,
                value=control.value,
                multi=True,
                clearable=True,
            )
        elif isinstance(control, DashDateRange):
            widget = dcc.DatePickerRange(
                id=ids.control(control.name),
                start_date=control.start_date,
                end_date=control.end_date,
            )
        elif isinstance(control, DashToggle):
            widget = dcc.Checklist(
                id=ids.control(control.name),
                options=[{"label": control.label or control.name, "value": True}],
                value=[True] if control.value else [],
            )
        else:
            raise ValueError(f"unsupported Dash control: {type(control)!r}")
        controls.append(html.Div([label, widget], className="runbook-control"))
    return controls


def _options(options: list[Any] | DatasetValues | None, ctx: Any) -> list[Any] | None:
    """Resolve explicit or pinned-snapshot dataset-backed control options."""
    if isinstance(options, DatasetValues):
        return resolve_dataset_values(options, ctx.dataset)
    return options


def _register_callbacks(
    app: Any,
    manifest: PDLManifest,
    extension: DashExtension | None,
    definition: ReportDefinition,
    ctx: Any,
    ids: DashIds,
) -> None:
    """Bind declared plain-Python interactions to host Dash callbacks."""
    if extension is None:
        return
    from dash import Input, Output

    blocks = {block.name: block for block in manifest.page.blocks}
    for declaration in extension.interactions:
        outputs = [Output(ids.block(name), _output_property(blocks[name])) for name in declaration.outputs]
        inputs = _input_specs(extension, ids, declaration.inputs, Input)
        handler = (definition.interaction_fns or {})[declaration.handler]

        callback = _make_callback(
            ctx=ctx,
            extension=extension,
            handler=handler,
            input_names=tuple(declaration.inputs),
            output_names=tuple(declaration.outputs),
            output_blocks={name: blocks[name] for name in declaration.outputs},
        )

        if outputs:
            app.callback(outputs, inputs)(callback)


def _make_callback(
    *,
    ctx: Any,
    extension: DashExtension,
    handler: Any,
    input_names: tuple[str, ...],
    output_names: tuple[str, ...],
    output_blocks: Mapping[str, Any],
) -> Any:
    """Create one isolated callback closure for one declared interaction."""

    def callback(*values: Any) -> list[Any]:
        """Convert ordinary Dash input values to JSON-like report state."""
        state = _state_from_values(extension, list(input_names), values)
        result = handler(ctx, state)
        if not isinstance(result, Mapping):
            raise TypeError(f"interaction {handler.__name__!r} must return a mapping")
        return [_convert_output(output_blocks[name], result.get(name)) for name in output_names]

    return callback


def _output_property(block: Any) -> str:
    """Select the Dash property updated by a PDL block type."""
    if isinstance(block, PDLTextBlock):
        return "children"
    if isinstance(block, PDLPlotRefBlock):
        return "figure"
    if isinstance(block, PDLTableBlock):
        return "rowData"
    raise TypeError(f"unsupported interaction output block: {type(block)!r}")


def _input_specs(extension: DashExtension, ids: DashIds, names: list[str], input_type: Any) -> list[Any]:
    """Expand logical controls into native Dash input properties."""
    return [
        input_type(ids.control(name), property_name)
        for name in names
        for property_name in _properties_for_input(extension, name)
    ]


def _properties_for_input(extension: DashExtension, name: str) -> tuple[str, ...]:
    """Return native input properties for one logical control."""
    for control in extension.controls:
        if control.name == name:
            if isinstance(control, DashDateRange):
                return ("start_date", "end_date")
            return ("value",)
    raise ValueError(f"unknown Dash input control: {name!r}")


def _state_from_values(extension: DashExtension, names: list[str], values: tuple[Any, ...]) -> dict[str, Any]:
    """Reassemble expanded native inputs into logical interaction state."""
    state: dict[str, Any] = {}
    cursor = 0
    for name in names:
        properties = _properties_for_input(extension, name)
        if len(properties) == 1:
            state[name] = values[cursor]
        else:
            state[name] = {properties[0]: values[cursor], properties[1]: values[cursor + 1]}
        cursor += len(properties)
    if cursor != len(values):
        raise ValueError("Dash callback input state does not match declared controls")
    return state


def _convert_output(block: Any, value: Any) -> Any:
    """Validate and convert a handler result to a Dash component property value."""
    if isinstance(block, PDLTextBlock):
        if not isinstance(value, str):
            raise TypeError(f"interaction output {block.name!r} expects str")
        return value
    if isinstance(block, PDLPlotRefBlock):
        if hasattr(value, "to_plotly_json"):
            return value.to_plotly_json()
        if isinstance(value, Mapping):
            return dict(value)
        raise TypeError(f"interaction output {block.name!r} expects a Plotly figure or mapping")
    if isinstance(block, PDLTableBlock):
        if not isinstance(value, pd.DataFrame):
            raise TypeError(f"interaction output {block.name!r} expects a pandas.DataFrame")
        return _records(value, block.columns)
    raise TypeError(f"unsupported interaction output block: {type(block)!r}")


def _records(frame: pd.DataFrame, columns: Sequence[PDLColumn] | None = None) -> list[dict[str, Any]]:
    """Convert a dataframe to JSON-safe AG Grid row records with PDL time types."""
    schema = pa.Schema.from_pandas(frame, preserve_index=False)
    semantics = merge_columns(schema, columns)
    normalized = frame.copy()
    for semantic in semantics:
        if semantic.role != PDLColumnRole.time or semantic.field not in normalized:
            continue
        parsed = pd.to_datetime(normalized[semantic.field], errors="coerce", utc=True)
        kind = semantic.format.kind if semantic.format is not None else "date"
        if kind == "datetime":
            values = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            values = parsed.dt.strftime("%Y-%m-%d")
        normalized[semantic.field] = values.where(parsed.notna(), None)
    return json.loads(normalized.to_json(orient="records", date_format="iso"))


def _read_bytes(ctx: Any, ref: str) -> bytes:
    """Read one relative PDL artifact from the report artifact store."""
    store = getattr(ctx, "_artifact_store", None) or getattr(ctx, "_store", None)
    if store is None:
        raise TypeError("Dash renderer context must expose an artifact store")
    prefix = str(getattr(ctx, "_artifact_prefix", "")).rstrip("/")
    key = ref if not prefix or ref.startswith(prefix + "/") else f"{prefix}/{ref}"
    return store.get(key)


def _read_json(ctx: Any, ref: str) -> Any:
    """Read one JSON plot artifact."""
    return json.loads(_read_bytes(ctx, ref).decode("utf-8"))


def _read_table(ctx: Any, ref: str) -> pd.DataFrame:
    """Read one Parquet table artifact."""
    return pd.read_parquet(io.BytesIO(_read_bytes(ctx, ref)))


__all__ = ["render_dash_page"]
