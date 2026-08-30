"""Static-first PDL to embeddable DashPage rendering."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd
import pyarrow as pa
from runbook.core.pdl.models import PDLColumn, PDLColumnRole, PDLManifest, PDLPlotRefBlock, PDLTableBlock, PDLTextBlock
from runbook.core.table import (
    TableFormatDate,
    TableLinkDestination,
    TableLinkKind,
    TableStylePlan,
    format_table_value,
    resolve_table_style,
)
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash.ids import DashIds
from runbook.sdk.extensions.dash.models import (
    DashControl,
    DashDateRange,
    DashExtension,
    DashMultiSelect,
    DashSelect,
    DashToggle,
    DatasetValues,
)
from runbook.sdk.extensions.dash.page import DashPage
from runbook.sdk.extensions.dash.renderer_extensions import DashRenderedControl, DashRendererExtension
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
    renderer_extension: DashRendererExtension | None = None,
) -> DashPage:
    """Render a canonical PDL manifest into an embeddable, namespaced page."""
    pdl_extension = parse_dash_extension(manifest)
    validate_dash_manifest(manifest, pdl_extension, definition)
    ids = DashIds(namespace)
    components, bindings = _build_components(manifest, pdl_extension, ctx, ids, renderer_extension)

    def layout_factory() -> Any:
        """Build the page layout without creating or owning a Dash app."""
        from dash import html

        columns = manifest.page.columns or 1
        content = html.Div(
            [
                html.Header([html.H1(manifest.title), html.P(f"As of: {manifest.as_of.isoformat()}")]),
                _warning_component(manifest),
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
        if renderer_extension is None:
            return content
        wrapped = renderer_extension.wrap_page(content, manifest=manifest, namespace=namespace)
        return content if wrapped is None else wrapped

    def callback_registrar(app: Any) -> None:
        """Register this page's callbacks on the host-owned app."""
        _register_callbacks(app, manifest, pdl_extension, definition, ctx, ids, bindings)

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


def _build_components(
    manifest: PDLManifest,
    extension: DashExtension | None,
    ctx: Any,
    ids: DashIds,
    renderer_extension: DashRendererExtension | None,
) -> tuple[list[Any], dict[str, _ControlBinding]]:
    """Translate PDL blocks to Dash components and place them in the PDL grid."""
    from dash import dcc, html

    controls, bindings = _build_controls(extension, ctx, ids, renderer_extension) if extension else ([], {})
    interactive_tables = (
        {output for declaration in extension.interactions for output in declaration.outputs} if extension else set()
    )
    control_block = next(
        (block for block in manifest.page.blocks if isinstance(block, PDLTableBlock)),
        next(iter(manifest.page.blocks), None),
    )
    components: list[Any] = []
    for block in manifest.page.blocks:
        title = html.H2(block.title) if block.title else None
        body: Any
        if isinstance(block, PDLTextBlock):
            if block.text == "" and block.title:
                body = None
            else:
                body = (
                    dcc.Markdown(block.text, id=ids.block(block.name))
                    if block.format == "markdown"
                    else html.Pre(block.text, id=ids.block(block.name))
                )
        elif isinstance(block, PDLPlotRefBlock):
            body = dcc.Graph(id=ids.block(block.name), figure=_read_json(ctx, block.ref))
        elif isinstance(block, PDLTableBlock):
            frame = _read_table(ctx, block.data_ref)
            if block.name in interactive_tables:
                import dash_ag_grid as dag

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
                body = _build_native_table(frame, block, ids.block(block.name), ctx)
        else:
            raise ValueError(f"unsupported PDL block type: {block.type!r}")
        if controls and block is control_block:
            body = html.Div([*controls, body])
        position = {
            "gridRow": f"{block.row} / span {block.row_span}",
            "gridColumn": f"{block.col} / span {block.col_span}",
        }
        wrapped = None
        if renderer_extension is not None:
            wrapped = renderer_extension.wrap_block(
                body,
                block=block,
                title=title,
                namespace=ids.namespace,
            )
        block_content = _wrap_default_block(title, body) if wrapped is None else wrapped
        block_children: Any = block_content if wrapped is None else [block_content]
        components.append(
            html.Section(
                block_children,
                id=ids.block(block.name) + "-container",
                style=position,
            )
        )
    return components, bindings


@dataclass(frozen=True)
class _ControlBinding:
    """Capture a control's callback properties and native value decoder."""

    component_id: str
    input_properties: tuple[str, ...]
    decode: Callable[[tuple[Any, ...]], Any]


def _vanilla_binding(control: Any, component_id: str) -> _ControlBinding:
    """Capture the public component's native callback contract."""
    properties: tuple[str, ...]
    if isinstance(control, DashDateRange):
        properties = ("start_date", "end_date")
        decode = _date_range_state
    else:
        properties = ("value",)
        decode = _identity
    return _ControlBinding(component_id, properties, decode)


def _custom_binding(control: DashControl, component_id: str, rendered: DashRenderedControl) -> _ControlBinding:
    """Validate and normalize an explicit custom component binding."""
    control_name = control.name
    properties = tuple(rendered.input_properties)
    if not properties:
        raise ValueError(f"Custom Dash control {control_name!r} has no input properties.")
    if len(set(properties)) != len(properties):
        raise ValueError(f"Custom Dash control {control_name!r} defines duplicate input properties.")
    base_decoder = rendered.decode
    if base_decoder is None:
        if len(properties) != 1:
            raise ValueError(f"Custom Dash control {control_name!r} defines multiple input properties but no decoder.")
        base_decoder = _identity
    decode: Callable[[tuple[Any, ...]], Any] = base_decoder
    if isinstance(control, DashDateRange):

        def decode_date_range(values: tuple[Any, ...]) -> Any:
            """Validate and normalize a custom date-range logical value."""
            result = base_decoder(values)
            if not isinstance(result, Mapping) or set(result) != {"start_date", "end_date"}:
                raise ValueError(
                    f"Custom Dash control {control_name!r} decoder must return a mapping with exactly "
                    "'start_date' and 'end_date'."
                )
            return dict(result)

        decode = decode_date_range
    elif isinstance(control, DashToggle):

        def decode_toggle(values: tuple[Any, ...]) -> Any:
            """Validate a custom toggle logical value."""
            result = base_decoder(values)
            if not isinstance(result, list) or (result != [] and not (len(result) == 1 and result[0] is True)):
                raise ValueError(f"Custom Dash control {control_name!r} decoder must return [] or [True].")
            return result

        decode = decode_toggle
    return _ControlBinding(component_id, properties, decode)


def _identity(values: tuple[Any, ...]) -> Any:
    """Decode a single native property without changing its value."""
    return values[0]


def _date_range_state(values: tuple[Any, ...]) -> dict[str, Any]:
    """Decode the vanilla date-range properties into logical control state."""
    return {"start_date": values[0], "end_date": values[1]}


def _build_controls(
    extension: DashExtension,
    ctx: Any,
    ids: DashIds,
    renderer_extension: DashRendererExtension | None,
) -> tuple[list[Any], dict[str, _ControlBinding]]:
    """Translate the small supported control set to Dash inputs."""
    from dash import dcc, html

    controls: list[Any] = []
    bindings: dict[str, _ControlBinding] = {}
    for control in extension.controls:
        component_id = ids.control(control.name)
        options = _options(control.options, ctx) if isinstance(control, (DashSelect, DashMultiSelect)) else None
        rendered = (
            renderer_extension.render_control(control, component_id=component_id, options=options)
            if renderer_extension is not None
            else None
        )
        if isinstance(rendered, DashRenderedControl):
            widget = rendered.component
            bindings[control.name] = _custom_binding(control, component_id, rendered)
        elif rendered is None:
            widget = None
            bindings[control.name] = _vanilla_binding(control, component_id)
        else:
            widget = rendered
            bindings[control.name] = _vanilla_binding(control, component_id)
        if widget is None:
            if isinstance(control, DashSelect):
                widget = dcc.Dropdown(
                    id=component_id,
                    options=options,
                    value=control.value,
                    clearable=True,
                )
            elif isinstance(control, DashMultiSelect):
                widget = dcc.Dropdown(
                    id=component_id,
                    options=options,
                    value=control.value,
                    multi=True,
                    clearable=True,
                )
            elif isinstance(control, DashDateRange):
                widget = dcc.DatePickerRange(
                    id=component_id,
                    start_date=control.start_date,
                    end_date=control.end_date,
                )
            elif isinstance(control, DashToggle):
                widget = dcc.Checklist(
                    id=component_id,
                    options=[{"label": control.label or control.name, "value": True}],
                    value=[True] if control.value else [],
                )
            else:
                raise ValueError(f"unsupported Dash control: {type(control)!r}")
        label = html.Label(control.label or control.name, htmlFor=component_id)
        controls.append(html.Div([label, widget], className="runbook-control"))
    return controls, bindings


def _wrap_default_block(title: Any | None, body: Any) -> list[Any]:
    """Preserve the vanilla block's title/body structure."""
    return [item for item in (title, body) if item is not None]


def _build_native_table(frame: pd.DataFrame, block: PDLTableBlock, component_id: str, ctx: Any) -> Any:
    """Build a static Dash table from resolved renderer-neutral table semantics."""
    from dash import html

    schema = pa.Schema.from_pandas(frame, preserve_index=False)
    semantics = merge_columns(schema, block.columns)
    plan = _read_table_style(ctx, block)
    resolved = resolve_table_style(frame, plan)
    by_field = {semantic.field: semantic for semantic in semantics}
    fields = [field for field in resolved.visible_columns if field in by_field and not by_field[field].hidden]
    visible = frame.head(resolved.max_rows)
    global_style = resolved.global_style
    table_style = {
        "border": global_style.table_border,
        "borderCollapse": "collapse",
        "fontFamily": global_style.font_family,
        "fontSize": global_style.font_size,
        "width": "100%",
    }
    header_base = {
        "borderBottom": global_style.header_border_bottom,
        "fontFamily": global_style.font_family,
        "fontSize": global_style.font_size,
        "textAlign": global_style.header_text_align,
    }

    header_cells: list[Any] = []
    if resolved.show_index:
        index_header: Any = "" if frame.index.name is None else str(frame.index.name)
        if resolved.index_header_link is not None:
            index_header = _dash_link(index_header, resolved.index_header_link)
        header_cells.append(html.Th(index_header, style=dict(header_base)))
    for field in fields:
        style = dict(header_base)
        _apply_width(style, resolved.column_width_px.get(field))
        header = by_field[field].label or field
        if field in resolved.header_links:
            header = _dash_link(header, resolved.header_links[field])
        header_cells.append(html.Th(header, style=style))

    body_rows: list[Any] = []
    for row_pos, (index_value, row) in enumerate(
        zip(visible.index, visible.itertuples(index=False, name=None), strict=True)
    ):
        if row_pos in resolved.hidden_rows:
            continue
        row_cells: list[Any] = []
        row_style = resolved.row_width_px.get(row_pos)
        if resolved.show_index:
            index_cell_style: dict[str, Any] = {}
            _apply_base_row_style(index_cell_style, row_pos, global_style.one_bg_color, global_style.background_color)
            _apply_width(index_cell_style, row_style)
            row_cells.append(html.Th(_display_scalar(index_value), style=index_cell_style))
        values = dict(zip((str(column) for column in visible.columns), row, strict=True))
        for field in fields:
            cell_style: dict[str, Any] = {}
            _apply_base_row_style(cell_style, row_pos, global_style.one_bg_color, global_style.background_color)
            _apply_width(cell_style, resolved.column_width_px.get(field))
            _apply_width(cell_style, row_style)
            cell_style.update(_dash_style(resolved.cell_css.get((row_pos, field), {})))
            value = _display_value(values[field], by_field[field], resolved)
            destination = resolved.cell_links.get((row_pos, field))
            if destination is not None:
                value = _dash_link(value, destination)
            row_cells.append(html.Td(value, style=cell_style))
        body_rows.append(html.Tr(row_cells))

    return html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)],
        id=component_id,
        style=table_style,
    )


def _read_table_style(ctx: Any, block: PDLTableBlock) -> TableStylePlan:
    """Read one persisted style plan, or use the resolver defaults."""
    if block.style_ref:
        plan = TableStylePlan.model_validate(_read_json(ctx, block.style_ref))
    elif block.style_key:
        plan = TableStylePlan(style_key=block.style_key)
    else:
        plan = TableStylePlan()
    if not block.links:
        return plan

    # Artifact refs may carry links separately from a persisted style. The
    # block declaration wins for the same target while preserving style links.
    by_target = {(link.area, link.field): link for link in plan.links or ()}
    for link in block.links:
        by_target[(link.area, link.field)] = link
    links = list(by_target.values())
    payload = plan.model_dump(mode="python", exclude_none=True)
    payload["schema_version"] = "table-style/0.2"
    payload["links"] = [link.model_dump(mode="python", exclude_none=True) for link in links]
    return TableStylePlan.model_validate(payload)


def _dash_link(display: Any, destination: TableLinkDestination) -> Any:
    """Build one native Dash link from resolved table semantics."""
    from dash import dcc, html

    if destination.kind == TableLinkKind.report:
        assert destination.value is not None
        return dcc.Link(
            display,
            href=f"/report/{destination.value}",
        )
    if destination.kind == TableLinkKind.url:
        assert destination.value is not None
        return cast(Any, html.A)(
            display,
            href=destination.value,
            **{"data-runbook-link-kind": "url"},
        )
    return display


def _apply_width(style: dict[str, Any], width: int | None) -> None:
    """Apply resolver width semantics to a Dash style mapping."""
    if width is not None:
        value = f"{width}px"
        style.update({"width": value, "minWidth": value})


def _apply_base_row_style(style: dict[str, Any], row_pos: int, one_bg_color: bool, background_color: str) -> None:
    """Apply the same alternating background rule as the HTML renderer."""
    if one_bg_color or row_pos % 2 == 0:
        style["backgroundColor"] = background_color


def _dash_style(css: Mapping[str, str]) -> dict[str, str]:
    """Convert resolver CSS property names to React/Dash style names."""
    result: dict[str, str] = {}
    for name, value in css.items():
        parts = name.split("-")
        key = parts[0] + "".join(part.capitalize() for part in parts[1:])
        result[key] = value
    return result


def _display_value(value: Any, semantic: PDLColumn, resolved: Any) -> Any:
    """Format a table value with style-plan formats taking precedence."""
    if _is_null_scalar(value):
        return _display_scalar(format_table_value(value, na_rep=resolved.na_rep))
    spec = resolved.formats.get(semantic.field)
    if spec is not None:
        return _display_scalar(format_table_value(value, spec, na_rep=resolved.na_rep))
    if resolved.precision is not None or resolved.thousands is not None:
        return _display_scalar(
            format_table_value(
                value,
                na_rep=resolved.na_rep,
                precision=resolved.precision,
                thousands=resolved.thousands,
            )
        )
    if semantic.format is None and resolved.links:
        return _display_scalar(format_table_value(value, na_rep=resolved.na_rep, default=True))
    return _format_pdl_value(value, semantic.format)


def _format_pdl_value(value: Any, spec: Any) -> str:
    """Preserve the existing PDL column display formats for native tables."""
    if spec is None:
        return _display_scalar(value)
    kind = spec.kind
    if kind == "number":
        try:
            number = float(value)
        except Exception:
            return str(value)
        decimals = getattr(spec, "decimals", None)
        return format(number, ",g") if decimals is None else f"{number:,.{decimals}f}"
    if kind == "currency":
        symbols = {"GBP": "£", "USD": "$", "EUR": "€", "JPY": "¥"}
        code = str(spec.currency).upper()
        try:
            number = float(value)
        except Exception:
            return str(value)
        decimals = getattr(spec, "decimals", None)
        number_text = format(number, ",g") if decimals is None else f"{number:,.{decimals}f}"
        return f"{symbols.get(code, code + ' ')}{number_text}"
    if kind == "percent":
        try:
            number = float(value)
        except Exception:
            return str(value)
        decimals = getattr(spec, "decimals", None)
        return f"{number * 100:.{2 if decimals is None else decimals}f}%"
    if kind == "date":
        return _display_scalar(format_table_value(value, TableFormatDate(pattern="%b %-d, %Y")))
    if kind == "datetime":
        return _display_scalar(format_table_value(value, TableFormatDate(pattern="%b %-d, %Y %H:%M")))
    return _display_scalar(value)


def _display_scalar(value: Any) -> str:
    """Return a Dash-safe textual scalar."""
    return str(value)


def _is_null_scalar(value: Any) -> bool:
    """Check pandas scalar nulls without treating list-like values as null."""
    result = pd.isna(value)
    return isinstance(result, bool) and result


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
    bindings: Mapping[str, _ControlBinding],
) -> None:
    """Bind declared plain-Python interactions to host Dash callbacks."""
    if extension is None:
        return
    from dash import Input, Output

    blocks = {block.name: block for block in manifest.page.blocks}
    for declaration in extension.interactions:
        outputs = [Output(ids.block(name), _output_property(blocks[name])) for name in declaration.outputs]
        inputs = _input_specs(bindings, declaration.inputs, Input)
        handler = (definition.interaction_fns or {})[declaration.handler]

        callback = _make_callback(
            ctx=ctx,
            handler=handler,
            input_names=tuple(declaration.inputs),
            output_names=tuple(declaration.outputs),
            output_blocks={name: blocks[name] for name in declaration.outputs},
            bindings=bindings,
        )

        if outputs:
            app.callback(outputs, inputs)(callback)


def _make_callback(
    *,
    ctx: Any,
    handler: Any,
    input_names: tuple[str, ...],
    output_names: tuple[str, ...],
    output_blocks: Mapping[str, Any],
    bindings: Mapping[str, _ControlBinding],
) -> Any:
    """Create one isolated callback closure for one declared interaction."""

    def callback(*values: Any) -> list[Any]:
        """Convert ordinary Dash input values to JSON-like report state."""
        state = _state_from_values(bindings, list(input_names), values)
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


def _input_specs(bindings: Mapping[str, _ControlBinding], names: list[str], input_type: Any) -> list[Any]:
    """Expand logical controls into native Dash input properties."""
    inputs: list[Any] = []
    for name in names:
        binding = bindings.get(name)
        if binding is None:
            raise ValueError(f"unknown Dash input control: {name!r}")
        inputs.extend(input_type(binding.component_id, property_name) for property_name in binding.input_properties)
    return inputs


def _state_from_values(
    bindings: Mapping[str, _ControlBinding], names: list[str], values: tuple[Any, ...]
) -> dict[str, Any]:
    """Reassemble expanded native inputs into logical interaction state."""
    state: dict[str, Any] = {}
    cursor = 0
    for name in names:
        binding = bindings.get(name)
        if binding is None:
            raise ValueError(f"unknown Dash input control: {name!r}")
        count = len(binding.input_properties)
        state[name] = binding.decode(tuple(values[cursor : cursor + count]))
        cursor += count
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
