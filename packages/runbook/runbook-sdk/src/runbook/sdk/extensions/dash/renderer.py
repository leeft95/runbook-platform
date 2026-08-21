"""Static-first PDL to embeddable DashPage rendering."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from runbook.core.pdl.models import PDLManifest, PDLPlotRefBlock, PDLTableBlock, PDLTextBlock
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
    components = _build_components(manifest, extension, ctx, ids)

    def layout_factory() -> Any:
        from dash import html

        columns = manifest.page.columns or 1
        return html.Div(
            [
                html.H1(manifest.title),
                html.Div(
                    components,
                    style={
                        "display": "grid",
                        "gridTemplateColumns": f"repeat({columns}, minmax(0, 1fr))",
                        "gap": "16px",
                    },
                ),
            ]
        )

    def callback_registrar(app: Any) -> None:
        _register_callbacks(app, manifest, extension, definition, ctx, ids)

    return DashPage(layout_factory=layout_factory, callback_registrar=callback_registrar, namespace=namespace)


def _build_components(manifest: PDLManifest, extension: DashExtension | None, ctx: Any, ids: DashIds) -> list[Any]:
    import dash_ag_grid as dag
    from dash import dcc, html

    controls = _build_controls(extension, ctx, ids) if extension else []
    components: list[Any] = list(controls)
    for block in manifest.page.blocks:
        title = html.H2(block.title) if block.title else None
        if isinstance(block, PDLTextBlock):
            body: Any = dcc.Markdown(block.text) if block.format == "markdown" else html.Pre(block.text)
        elif isinstance(block, PDLPlotRefBlock):
            body = dcc.Graph(id=ids.block(block.name), figure=_read_json(ctx, block.ref))
        elif isinstance(block, PDLTableBlock):
            frame = _read_table(ctx, block.data_ref)
            schema = pq.read_schema(io.BytesIO(_read_bytes(ctx, block.data_ref)))
            body = dag.AgGrid(
                id=ids.block(block.name),
                rowData=_records(frame),
                columnDefs=build_ag_grid_column_defs(schema, block.columns),
                defaultColDef=ag_grid_default_col_def(),
                dashGridOptions={"sideBar": "columns"},
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
    from dash import dcc, html

    controls: list[Any] = []
    for control in extension.controls:
        label = html.Label(control.label or control.name, htmlFor=ids.control(control.name))
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
    if extension is None:
        return
    from dash import Input, Output

    blocks = {block.name: block for block in manifest.page.blocks}
    for declaration in extension.interactions:
        outputs = [Output(ids.block(name), _output_property(blocks[name])) for name in declaration.outputs]
        inputs = [Input(ids.control(name), _input_property(extension, name)) for name in declaration.inputs]
        handler = (definition.interaction_fns or {})[declaration.handler]

        def callback(*values: Any, _handler: Any = handler, _inputs: list[str] = declaration.inputs) -> list[Any]:
            state = dict(zip(_inputs, values, strict=True))
            result = _handler(ctx, state)
            if not isinstance(result, Mapping):
                raise TypeError(f"interaction {_handler.__name__!r} must return a mapping")
            return [_convert_output(blocks[name], result.get(name)) for name in declaration.outputs]

        if outputs:
            app.callback(outputs, inputs)(callback)


def _output_property(block: Any) -> str:
    if isinstance(block, PDLTextBlock):
        return "children"
    if isinstance(block, PDLPlotRefBlock):
        return "figure"
    if isinstance(block, PDLTableBlock):
        return "rowData"
    raise TypeError(f"unsupported interaction output block: {type(block)!r}")


def _input_property(extension: DashExtension, name: str) -> str:
    for control in extension.controls:
        if control.name == name:
            return "value"
    raise ValueError(f"unknown Dash input control: {name!r}")


def _convert_output(block: Any, value: Any) -> Any:
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
        return _records(value)
    raise TypeError(f"unsupported interaction output block: {type(block)!r}")


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _read_bytes(ctx: Any, ref: str) -> bytes:
    store = getattr(ctx, "_artifact_store", None) or getattr(ctx, "_store", None)
    if store is None:
        raise TypeError("Dash renderer context must expose an artifact store")
    prefix = str(getattr(ctx, "_artifact_prefix", "")).rstrip("/")
    key = ref if not prefix or ref.startswith(prefix + "/") else f"{prefix}/{ref}"
    return store.get(key)


def _read_json(ctx: Any, ref: str) -> Any:
    return json.loads(_read_bytes(ctx, ref).decode("utf-8"))


def _read_table(ctx: Any, ref: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(_read_bytes(ctx, ref)))


__all__ = ["render_dash_page"]
