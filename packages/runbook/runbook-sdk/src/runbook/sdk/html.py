from __future__ import annotations

import json
from html import escape

import pandas as pd
import plotly.io as pio
from runbook.core import BlobStore
from runbook.core.pdl.models import PDLManifest

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
    css_link = f'<link rel="stylesheet" href="{escape(manifest.style.css_ref, quote=True)}">' if manifest.style else ""
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
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + escape(manifest.title)
        + "</title>"
        + css_link
        + f'</head><body>{warning_markup}<main class="rb-page" style="--rb-columns: {columns};">'
        + "".join(blocks)
        + "</main></body></html>"
    )
