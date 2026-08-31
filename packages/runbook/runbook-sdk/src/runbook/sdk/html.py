from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape

import pandas as pd
import plotly.io as pio
from plotly.utils import PlotlyJSONEncoder
from runbook.core import BlobStore
from runbook.core.pdl.models import PDLLinkBlock, PDLManifest, PDLTableBlock
from runbook.core.table import TableStylePlan, link_anchor, render_table_html
from runbook.core.table.models import TableLinkKind

DEFAULT_GRID_CSS_REF = "styles/grid.css"
DEFAULT_GRID_CSS = """.rb-page {
  display: grid;
  grid-template-columns: repeat(var(--rb-columns, 1), minmax(0, 1fr));
  gap: 16px;
}

.rb-block {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}

.rb-warnings {
  border: 2px solid #b45309;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
  background: #fff7ed;
  color: #7c2d12;
}

.rb-block table {
  width: 100%;
  border-collapse: collapse;
}

.rb-table-content-width table {
  width: auto;
}

.rb-table-explicit-width table {
  width: var(--rb-table-width);
}

.rb-block td,
.rb-block th {
  border: 1px solid #eee;
  padding: 4px 6px;
}
"""


@dataclass(frozen=True)
class RenderedHtmlReport:
    """Rendered report HTML and any linked plot pages."""

    main: str
    linked_pages: dict[str, str]


def _key(prefix: str, ref: str) -> str:
    """Resolve a relative PDL reference beneath an artifact prefix."""
    return ref if ref.startswith(prefix + "/") else f"{prefix}/{ref}"


def render_html(store: BlobStore, manifest: PDLManifest, prefix: str) -> str:
    """Render html."""
    page = manifest.page
    blocks: list[str] = []
    include_plotlyjs: bool | str = "cdn"
    for index, block in enumerate(page.blocks):
        title = f"<h2>{escape(block.title)}</h2>" if block.title else ""
        if block.type == "text":
            body = "" if block.text == "" and block.title else f"<pre>{escape(block.text)}</pre>"
        elif block.type == "link":
            body = link_anchor(escape(block.label), block.destination)
        elif block.type == "table":
            if block.html_ref:
                body = store.get(_key(prefix, block.html_ref)).decode("utf-8")
            else:
                data_ref = _key(prefix, block.data_ref)
                import io

                frame = pd.read_parquet(io.BytesIO(store.get(data_ref)))
                style_plan = (
                    TableStylePlan.model_validate(store.get_json(_key(prefix, block.style_ref)))
                    if block.style_ref
                    else None
                )
                if style_plan is not None or block.links:
                    plan = style_plan or TableStylePlan()
                    by_target = {(link.area, link.field): link for link in plan.links or ()}
                    for link in block.links or ():
                        by_target[(link.area, link.field)] = link
                    style_payload = plan.model_dump(mode="python", exclude_none=True)
                    style_payload["schema_version"] = "table-style/0.2"
                    style_payload["links"] = [
                        link.model_dump(mode="python", exclude_none=True) for link in by_target.values()
                    ]
                    plan = TableStylePlan.model_validate(style_payload)
                    body = render_table_html(frame, plan, table_class="runbook-table")
                else:
                    body = frame.to_html(index=True, border=0, classes="runbook-table")
        elif block.type == "plot_ref":
            payload = json.loads(store.get(_key(prefix, block.ref)).decode("utf-8"))
            body = pio.from_json(json.dumps(payload, sort_keys=True)).to_html(
                include_plotlyjs=include_plotlyjs,
                full_html=False,
                div_id=f"plot-{index}",
            )
            include_plotlyjs = False
        else:
            raise ValueError(f"unsupported PDL block type: {block.type!r}")
        position = f"grid-row: {block.row} / span {block.row_span}; grid-column: {block.col} / span {block.col_span};"

        block_classes = ["rb-block"]
        table_width = None

        if isinstance(block, PDLTableBlock):
            if block.width == "content":
                block_classes.append("rb-table-content-width")
            elif block.width != "fill":
                block_classes.append("rb-table-explicit-width")
                table_width = block.width

        classes = " ".join(block_classes)
        if table_width is not None:
            position += f" --rb-table-width: {escape(table_width)};"

        blocks.append(f'<section class="{classes}" style="{position}">{title}{body}</section>')
    css = ""
    if manifest.style:
        css = re.sub(
            r"</style",
            r"<\/style",
            store.get(_key(prefix, manifest.style.css_ref)).decode("utf-8"),
            flags=re.IGNORECASE,
        )
        css = f"<style>{css}</style>"
    columns = page.columns or 1
    warnings = "".join(f"<li>{escape(warning)}</li>" for warning in manifest.warnings)
    warning_markup = (
        '<aside class="rb-warnings" role="alert" '
        'style="border:2px solid #b45309;border-radius:8px;padding:10px 14px;'
        'margin-bottom:16px;background:#fff7ed;color:#7c2d12;">'
        f"<strong>Warnings</strong><ul>{warnings}</ul></aside>"
        if warnings
        else ""
    )
    report_title = escape(manifest.title)
    report_as_of = escape(manifest.as_of.isoformat())
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + report_title
        + "</title>"
        + css
        + f'</head><body><header><h1>{report_title}</h1><p>As of: {report_as_of}</p></header>{warning_markup}<main class="rb-page" style="--rb-columns: {columns};">'
        + "".join(blocks)
        + "</main></body></html>"
    )


def _plot_name(ref: str) -> str:
    """Resolve a runtime plot reference to its semantic name."""
    if ref.startswith("plots/"):
        ref = ref[len("plots/") :]
        if ref.endswith(".json"):
            ref = ref[: -len(".json")]
    return ref


def _named_plot_jsons(plot_jsons: Mapping[str, object] | object) -> dict[str, object]:
    """Normalize runtime plot payloads to semantic names."""
    values = getattr(plot_jsons, "plot_jsons", plot_jsons)
    if not isinstance(values, Mapping):
        raise TypeError("render_html_bundle expects a mapping of named Plotly JSON payloads")
    result: dict[str, object] = {}
    for ref, payload in values.items():
        name = _plot_name(str(ref))
        if not name:
            raise ValueError(f"plot payload has an empty semantic name: {ref!r}")
        if name in result:
            raise ValueError(f"duplicate plot payload semantic name: {name!r}")
        result[name] = payload
    return result


def _linked_plot_targets(manifest: PDLManifest) -> tuple[set[str], set[str]]:
    """Collect individual and aggregate plot destinations from report links."""
    individual: set[str] = set()
    aggregates: set[str] = set()
    for block in manifest.page.blocks:
        if isinstance(block, PDLLinkBlock):
            destination = block.destination
            if destination.kind == TableLinkKind.plot:
                assert destination.value is not None
                target = _plot_name(destination.value)
                (aggregates if target.endswith("-plots") else individual).add(target)
            continue
        if not isinstance(block, PDLTableBlock):
            continue
        for link in block.links or ():
            destination = link.destination
            if destination.kind != TableLinkKind.plot:
                continue
            assert destination.value is not None
            target = _plot_name(destination.value)
            if link.area == "index_header" and target.endswith("-plots"):
                aggregates.add(target)
            else:
                individual.add(target)
    return individual, aggregates


def _render_linked_plot_page(title: str, names: list[str], plot_jsons: Mapping[str, object]) -> str:
    """Render one standalone plot document."""
    include_plotlyjs: bool | str = "cdn"
    plots: list[str] = []
    for index, name in enumerate(names):
        payload = plot_jsons[name]
        plots.append(
            pio.from_json(json.dumps(payload, cls=PlotlyJSONEncoder, sort_keys=True)).to_html(
                include_plotlyjs=include_plotlyjs,
                full_html=False,
                div_id=f"plot-{index}",
            )
        )
        include_plotlyjs = False
    escaped_title = escape(title)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + escaped_title
        + "</title></head><body><h1>"
        + escaped_title
        + "</h1><main>"
        + "".join(plots)
        + "</main></body></html>"
    )


def render_html_bundle(
    store: BlobStore,
    manifest: PDLManifest,
    prefix: str,
    plot_jsons: Mapping[str, object] | object,
) -> RenderedHtmlReport:
    """Render the main report and linked plot documents."""
    named_plot_jsons = _named_plot_jsons(plot_jsons)
    individual, aggregates = _linked_plot_targets(manifest)
    linked_pages: dict[str, str] = {}

    for target in sorted(individual):
        if target not in named_plot_jsons:
            raise ValueError(f"plot link destination is missing from registered payloads: {target!r}")
        linked_pages[target] = _render_linked_plot_page(target, [target], named_plot_jsons)

    for target in sorted(aggregates):
        table_slug = target[: -len("-plots")]
        members = sorted(name for name in named_plot_jsons if name.startswith(f"{table_slug}-") and name != target)
        if not members:
            raise ValueError(f"aggregate plot link has no matching registered members: {target!r}")
        linked_pages[target] = _render_linked_plot_page(target, members, named_plot_jsons)

    return RenderedHtmlReport(
        main=render_html(store, manifest, prefix),
        linked_pages={name: linked_pages[name] for name in sorted(linked_pages)},
    )
