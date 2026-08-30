"""Static-first PDL to embeddable DashPage rendering."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote

import pandas as pd
import pyarrow as pa
from runbook.core.pdl.models import (
    PDLColumn,
    PDLColumnRole,
    PDLLinkBlock,
    PDLManifest,
    PDLPlotRefBlock,
    PDLTableBlock,
    PDLTextBlock,
)
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
from runbook.sdk.extensions.dash.page import DashPage, RouteResolver
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
    route_resolver: RouteResolver | None = None,
) -> DashPage:
    """Render a canonical PDL manifest into an embeddable, namespaced page."""
    pdl_extension = parse_dash_extension(manifest)
    validate_dash_manifest(manifest, pdl_extension, definition)
    ids = DashIds(namespace)
    components, bindings = _build_components(
        manifest,
        pdl_extension,
        ctx,
        ids,
        renderer_extension,
        route_resolver,
    )

    def plot_layout_factory(name: str) -> Any:
        """Build a native detail or aggregate page for one logical plot target."""
        return _build_plot_layout(manifest, ctx, name, ids)

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
        _register_callbacks(
            app,
            manifest,
            pdl_extension,
            definition,
            ctx,
            ids,
            bindings,
            route_resolver=route_resolver,
        )

    return DashPage(
        layout_factory=layout_factory,
        callback_registrar=callback_registrar,
        namespace=namespace,
        plot_layout_factory=plot_layout_factory,
    )


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
    route_resolver: RouteResolver | None,
) -> tuple[list[Any], dict[str, _ControlBinding]]:
    """Translate PDL blocks to Dash components and place them in the PDL grid."""
    from dash import dcc, html

    controls, bindings = _build_controls(extension, ctx, ids, renderer_extension) if extension else ([], {})
    plot_refs = _manifest_plot_refs(manifest)
    interactive_tables = (
        {output for declaration in extension.interactions for output in declaration.outputs} if extension else set()
    )
    control_block = next(
        (block for block in manifest.page.blocks if isinstance(block, PDLTableBlock)),
        next((block for block in manifest.page.blocks if not isinstance(block, PDLLinkBlock)), None),
    )
    if controls and control_block is None:
        raise ValueError("Dash controls require a non-link content block")
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
            body = _plot_component(ctx, block.ref, component_id=ids.block(block.name))
        elif isinstance(block, PDLLinkBlock):
            body = _dash_link(block.label, block.destination, route_resolver, ctx, plot_refs)
        elif isinstance(block, PDLTableBlock):
            frame = _read_table(ctx, block.data_ref)
            if block.name in interactive_tables:
                import dash_ag_grid as dag

                grid = _build_ag_grid(frame, block, ctx, route_resolver, plot_refs)
                body = dag.AgGrid(
                    id=ids.block(block.name),
                    rowData=grid.row_data,
                    columnDefs=grid.column_defs,
                    defaultColDef=ag_grid_default_col_def(),
                    dashGridOptions={"sideBar": "columns"},
                    style=grid.style,
                    # Phase C uses client-side grouping/pivot/value aggregation in
                    # local preview. Formatter functions use only Dash AG Grid's
                    # trusted preloaded d3 namespace; PDL has no JS escape hatch.
                    enableEnterpriseModules=True,
                )
            else:
                body = _build_native_table(frame, block, ids.block(block.name), ctx, route_resolver, plot_refs)
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
        if isinstance(block, PDLLinkBlock):
            block_content = body if wrapped is None else wrapped
            components.append(
                html.Div(
                    block_content,
                    id=ids.block(block.name) + "-container",
                    style=position,
                )
            )
            continue
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


def _build_native_table(
    frame: pd.DataFrame,
    block: PDLTableBlock,
    component_id: str,
    ctx: Any,
    route_resolver: RouteResolver | None = None,
    plot_refs: Mapping[str, str] | None = None,
) -> Any:
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
            index_header = _dash_link(index_header, resolved.index_header_link, route_resolver, ctx, plot_refs)
        header_cells.append(html.Th(index_header, style=dict(header_base)))
    for field in fields:
        style = dict(header_base)
        _apply_width(style, resolved.column_width_px.get(field))
        header = by_field[field].label or field
        if field in resolved.header_links:
            header = _dash_link(header, resolved.header_links[field], route_resolver, ctx, plot_refs)
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
                value = _dash_link(value, destination, route_resolver, ctx, plot_refs)
            row_cells.append(html.Td(value, style=cell_style))
        body_rows.append(html.Tr(row_cells))

    return html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)],
        id=component_id,
        style=table_style,
    )


@dataclass(frozen=True)
class _AGGridConfig:
    """Renderer-owned AG Grid properties derived from one resolved table."""

    row_data: list[dict[str, Any]]
    column_defs: list[dict[str, Any]]
    style: dict[str, str]


def _metadata_field(prefix: str, frame: pd.DataFrame) -> str:
    """Choose a deterministic row metadata field not present in analyst data."""
    fields = {str(field) for field in frame.columns}
    candidate = prefix
    while candidate in fields:
        candidate += "_"
    return candidate


def _build_ag_grid(
    frame: pd.DataFrame,
    block: PDLTableBlock,
    ctx: Any,
    route_resolver: RouteResolver | None,
    plot_refs: Mapping[str, str],
) -> _AGGridConfig:
    """Translate one resolved table into AG Grid props without re-evaluating rules."""
    schema = pa.Schema.from_pandas(frame, preserve_index=False)
    plan = _read_table_style(ctx, block)
    resolved = resolve_table_style(frame, plan)
    styles_field = _metadata_field("__runbook_styles__", frame)
    links_field = _metadata_field("__runbook_links__", frame) if resolved.links else None
    index_field = (
        _metadata_field("__runbook_index__", frame)
        if resolved.show_index and resolved.index_header_link is not None
        else None
    )
    header_links: dict[str, tuple[str, str]] = {}
    for field, destination in resolved.header_links.items():
        href = _destination_href(destination, route_resolver, ctx, plot_refs)
        if href is not None:
            header_links[field] = (href, destination.kind.value)
    index_header_link = None
    if resolved.index_header_link is not None:
        href = _destination_href(resolved.index_header_link, route_resolver, ctx, plot_refs)
        if href is not None:
            index_header_link = (href, resolved.index_header_link.kind.value)
    cell_link_kinds = {
        link.field: link.destination.kind.value
        for link in resolved.links
        if link.area == "cells" and link.field is not None
    }
    row_data = _records(
        frame,
        block.columns,
        resolved=resolved,
        styles_field=styles_field,
        links_field=links_field,
        index_field=index_field,
        route_resolver=route_resolver,
        ctx=ctx,
        plot_refs=plot_refs,
    )
    column_defs = build_ag_grid_column_defs(
        schema,
        block.columns,
        resolved=resolved,
        cell_style_field=styles_field,
        cell_links_field=links_field,
        cell_link_kinds=cell_link_kinds,
        header_links=header_links,
        index_field=index_field,
        index_header_link=index_header_link,
        index_header_name="" if frame.index.name is None else str(frame.index.name),
        na_rep=resolved.na_rep,
    )
    global_style = resolved.global_style
    return _AGGridConfig(
        row_data=row_data,
        column_defs=column_defs,
        style={
            "border": global_style.table_border,
            "fontFamily": global_style.font_family,
            "fontSize": global_style.font_size,
            "width": "100%",
        },
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


def _dash_link(
    display: Any,
    destination: TableLinkDestination,
    route_resolver: RouteResolver | None = None,
    ctx: Any | None = None,
    plot_refs: Mapping[str, str] | None = None,
) -> Any:
    """Build one native Dash link from resolved table semantics."""
    from dash import dcc, html

    if destination.kind == TableLinkKind.report:
        assert destination.value is not None
        route = _resolve_route(route_resolver, TableLinkKind.report.value, destination.value)
        if route is None:
            return _link_error(f"Unable to resolve report route for {destination.value!r}.")
        return dcc.Link(display, href=route)
    if destination.kind == TableLinkKind.plot:
        assert destination.value is not None
        plot_name = _plot_name(destination.value)
        if plot_refs is not None:
            error = _plot_link_error(ctx, plot_name, plot_refs)
            if error is not None:
                return _link_error(error)
        route = _resolve_route(route_resolver, TableLinkKind.plot.value, plot_name)
        if route is None:
            return _link_error(f"Unable to resolve plot route for {plot_name!r}.")
        return dcc.Link(display, href=route)
    if destination.kind == TableLinkKind.url:
        assert destination.value is not None
        return cast(Any, html.A)(
            display,
            href=destination.value,
            **{"data-runbook-link-kind": "url"},
        )
    return display


def _destination_href(
    destination: TableLinkDestination,
    route_resolver: RouteResolver | None,
    ctx: Any | None,
    plot_refs: Mapping[str, str] | None,
) -> str | None:
    """Resolve a semantic destination for renderer-owned AG Grid metadata."""
    if destination.value is None:
        return None
    if destination.kind == TableLinkKind.url:
        return destination.value
    value = _plot_name(destination.value) if destination.kind == TableLinkKind.plot else destination.value
    if destination.kind == TableLinkKind.plot and plot_refs is not None:
        if _plot_link_error(ctx, value, plot_refs) is not None:
            return None
    return _resolve_route(route_resolver, destination.kind.value, value)


def _resolve_route(route_resolver: RouteResolver | None, kind: str, value: str) -> str | None:
    """Resolve one logical destination without exposing artifact paths."""
    if route_resolver is not None:
        try:
            route = route_resolver(kind, value)
        except Exception:
            return None
        return route if isinstance(route, str) and route else None
    if any(part in {".", ".."} for part in value.split("/")):
        return None
    encoded = "/".join(quote(part, safe="") for part in value.split("/"))
    if kind == TableLinkKind.report.value:
        return f"/report/{encoded}"
    if kind == TableLinkKind.plot.value:
        return f"/plot/{encoded}"
    return None


def _link_error(message: str) -> Any:
    """Render an unresolved logical link as an accessible inline error."""
    from dash import html

    return html.Span(message, role="alert")


def _plot_link_error(ctx: Any | None, name: str, refs: Mapping[str, str]) -> str | None:
    """Validate a linked plot target before exposing a browser route."""
    if name.endswith("-plots"):
        prefix = f"{name[: -len('-plots')]}-"
        members = sorted(member for member in refs if member.startswith(prefix) and member != name)
        if not members:
            return f"No registered plots match aggregate target {name!r}."
    else:
        members = [name] if name in refs else []
        if not members:
            return f"Plot target {name!r} is not registered."
    if ctx is None:
        return None
    for member in members:
        try:
            _read_json(ctx, refs[member])
        except Exception:
            return f"Unable to load plot artifact {member!r}."
    return None


def _plot_name(ref: str) -> str:
    """Normalize a plot artifact reference or logical destination name."""
    name = str(ref)
    if name.startswith("plots/"):
        name = name[len("plots/") :]
    if name.endswith(".json"):
        name = name[: -len(".json")]
    return name


def _plot_error(message: str) -> Any:
    """Render a native plot-page error without leaking a storage exception."""
    from dash import html

    return html.Div(message, role="alert")


def _plot_component(ctx: Any, ref: str, *, component_id: str) -> Any:
    """Read one registered Plotly payload, rendering stale artifacts accessibly."""
    from dash import dcc

    try:
        payload = _read_json(ctx, ref)
    except Exception:
        return _plot_error(f"Unable to load plot artifact {_plot_name(ref)!r}.")
    return dcc.Graph(id=component_id, figure=payload)


def _manifest_plot_refs(manifest: PDLManifest) -> dict[str, str]:
    """Return logical plot names from the canonical manifest artifact set."""
    refs = list(manifest.artifacts.plots or ()) if manifest.artifacts is not None else []
    # Manually authored manifests from before runtime plot registration may not
    # have an artifacts section. Keep those inline plot refs usable as a small
    # compatibility fallback; executed manifests use artifacts.plots above.
    if not refs:
        refs = [block.ref for block in manifest.page.blocks if isinstance(block, PDLPlotRefBlock)]
    result: dict[str, str] = {}
    for ref in refs:
        name = _plot_name(ref)
        if name and name not in result:
            result[name] = ref
    return result


def _build_plot_layout(manifest: PDLManifest, ctx: Any, target: str, ids: DashIds) -> Any:
    """Build an individual or aggregate native Dash plot page."""
    from dash import dcc, html

    name = _plot_name(target)
    refs = _manifest_plot_refs(manifest)
    if name.endswith("-plots"):
        prefix = f"{name[: -len('-plots')]}-"
        members = sorted(member for member in refs if member.startswith(prefix) and member != name)
        if not members:
            return _plot_error(f"No registered plots match aggregate target {name!r}.")
        payloads: list[tuple[str, Any]] = []
        for member in members:
            try:
                payloads.append((member, _read_json(ctx, refs[member])))
            except Exception:
                return _plot_error(f"Unable to load plot artifact {member!r}.")
        graphs = [
            dcc.Graph(id=ids.block(f"plot-{index}"), figure=payload) for index, (_, payload) in enumerate(payloads)
        ]
        return html.Div([html.H1(name), *graphs])
    ref = refs.get(name)
    if ref is None:
        return _plot_error(f"Plot target {name!r} is not registered.")
    try:
        payload = _read_json(ctx, ref)
    except Exception:
        return _plot_error(f"Unable to load plot artifact {name!r}.")
    return html.Div([html.H1(name), dcc.Graph(id=ids.block("plot-detail"), figure=payload)])


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
    *,
    route_resolver: RouteResolver | None = None,
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
            route_resolver=route_resolver,
            plot_refs=_manifest_plot_refs(manifest),
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
    route_resolver: RouteResolver | None,
    plot_refs: Mapping[str, str],
) -> Any:
    """Create one isolated callback closure for one declared interaction."""

    def callback(*values: Any) -> list[Any]:
        """Convert ordinary Dash input values to JSON-like report state."""
        state = _state_from_values(bindings, list(input_names), values)
        result = handler(ctx, state)
        if not isinstance(result, Mapping):
            raise TypeError(f"interaction {handler.__name__!r} must return a mapping")
        return [
            _convert_output(
                output_blocks[name],
                result.get(name),
                ctx=ctx,
                route_resolver=route_resolver,
                plot_refs=plot_refs,
            )
            for name in output_names
        ]

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


def _convert_output(
    block: Any,
    value: Any,
    *,
    ctx: Any | None = None,
    route_resolver: RouteResolver | None = None,
    plot_refs: Mapping[str, str] | None = None,
) -> Any:
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
        if ctx is not None:
            return _build_ag_grid(
                value,
                block,
                ctx,
                route_resolver,
                {} if plot_refs is None else plot_refs,
            ).row_data
        return _records(value, block.columns)
    raise TypeError(f"unsupported interaction output block: {type(block)!r}")


def _records(
    frame: pd.DataFrame,
    columns: Sequence[PDLColumn] | None = None,
    *,
    resolved: Any | None = None,
    styles_field: str | None = None,
    links_field: str | None = None,
    index_field: str | None = None,
    route_resolver: RouteResolver | None = None,
    ctx: Any | None = None,
    plot_refs: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Convert a dataframe to JSON-safe AG Grid row records with PDL time types."""
    source = frame if resolved is None else frame.head(resolved.max_rows)
    schema = pa.Schema.from_pandas(source, preserve_index=False)
    semantics = merge_columns(schema, columns)
    normalized = source.copy()
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
    records = json.loads(normalized.to_json(orient="records", date_format="iso"))
    if resolved is None:
        return records

    result: list[dict[str, Any]] = []
    for row_pos, (record, index_value) in enumerate(zip(records, source.index, strict=True)):
        if row_pos in resolved.hidden_rows:
            continue
        if index_field is not None:
            record[index_field] = _display_scalar(index_value)
        if styles_field is not None:
            record[styles_field] = {
                semantic.field: _ag_cell_style(resolved, row_pos, semantic.field) for semantic in semantics
            }
        if links_field is not None:
            links: dict[str, str] = {}
            for (link_row, field), destination in resolved.cell_links.items():
                if link_row != row_pos:
                    continue
                href = _destination_href(destination, route_resolver, ctx, plot_refs)
                if href is not None:
                    links[field] = href
            record[links_field] = links
        result.append(record)
    return result


def _ag_cell_style(resolved: Any, row_pos: int, field: str) -> dict[str, str]:
    """Combine resolved base, sizing, and conditional CSS for one AG cell."""
    global_style = resolved.global_style
    style: dict[str, str] = {}
    if global_style.one_bg_color or row_pos % 2 == 0:
        style["backgroundColor"] = global_style.background_color
    _apply_width(style, resolved.column_width_px.get(field))
    _apply_width(style, resolved.row_width_px.get(row_pos))
    style.update(_dash_style(resolved.cell_css.get((row_pos, field), {})))
    return style


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
