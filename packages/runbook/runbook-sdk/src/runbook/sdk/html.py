from __future__ import annotations

import json
import re
from html import escape

import pandas as pd
import plotly.io as pio
from runbook.core import BlobStore
from runbook.core.pdl.models import PDLManifest
from runbook.core.table import TableStylePlan, render_table_html

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

.rb-block td,
.rb-block th {
  border: 1px solid #eee;
  padding: 4px 6px;
}
"""


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
                if block.links or (style_plan is not None and style_plan.links):
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
        blocks.append(f'<section class="rb-block" style="{position}">{title}{body}</section>')
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
