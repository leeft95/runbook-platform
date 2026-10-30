# Composable report layouts

For report authors

`Report` is the whole page, `Section` is a named part of the page, and `Grid`,
`Row`, and `Stack` compose text, tables, plots, images, and links:

```text
Python artifacts -> Report / Section / Grid / Row / Stack -> PDL -> HTML or Dash
```

Layout placement is renderer-neutral: ordinary tables remain HTML tables or
native static Dash tables, and semantic cell/header links remain intact. A
report host owns Dash navigation; AG Grid is an explicit interactive-table
choice rather than a layout default.

```python
from runbook.sdk.layout import Link, Report, Row


def build(ctx):
    layout = Report("Crude Oil Weekly")
    with layout.section("Regional balances") as section:
        with section.grid(columns=2) as grid:
            for region in ["North", "South", "West"]:
                table_ref = ctx.artifact.table(build_table(ctx, region), name=f"{region.lower()}-balance")
                plot_ref = ctx.artifact.plot(build_plot(ctx, region), name=f"{region.lower()}-history")
                grid.table(table_ref, title=f"{region} balance")
                grid.plot(plot_ref, title=f"{region} history")
    return layout
```

## Images

Use `image(src, alt=...)` or the `.image(...)` helper on a Grid, Row, or Stack:

```python
from pathlib import Path
from runbook.sdk.layout import Report, image

layout = Report("Market overview", children=[
    image(Path(__file__).parent / "assets" / "chart.png",
          alt="Oil inventories by month", title="Inventories"),
    image("https://example.com/logo.png", alt="Company logo"),
])
```

Local PNG, JPEG, GIF, and WebP files are read when the block is created and
embedded as data URLs. The persisted report and exported HTML do not need the
original file or an image-serving endpoint. String paths work too; relative
paths resolve against the authoring process's working directory. Use a `Path`
relative to `__file__` for assets shipped with a report. Base64 raster data URLs
are also accepted. Embedded SVG is not supported.

Hosted HTTP(S) URLs are retained and loaded by the viewer's browser; report
generation does not download them. The viewer must be able to reach the URL.
Images preserve their aspect ratio and shrink to fit their layout cell in both
HTML and Dash. `alt` is required; use `alt=""` for a purely decorative image.
The usual `name`, `title`, `row_span`, and `col_span` options apply.

Images compile to `pdl-core/0.2` image blocks with `src` or `ref`, and `alt`; lower-level
authors can use `runbook.sdk.ui.image(name=..., src=..., alt=..., row=..., col=...)`.
They are static report content, not Dash interaction outputs. Inline data-image
support varies between email clients; this does not add CID email attachments.

### Stored images (file or S3)

Register image bytes alongside your table and plot artifacts:

```python
image_ref = ctx.artifact.image(chart_png_bytes, name="inventory-chart")
grid.image(ref=image_ref, alt="Oil inventories by month")
```

This returns `images/inventory-chart.png` (the extension is detected from the
bytes) and publishes the bytes immutably under the report artifact prefix.
Image references are listed in the manifest's `artifacts.files`. The same code
uses the configured file or S3 BlobStore, just like tables and plots.

For an image already in that report's artifact store:

```python
grid.image(ref="images/inventory-chart.png", alt="Oil inventories by month")
```

`ref` is a BlobStore key relative to the report prefix, not a filesystem path
or an `s3://` URL. An already-prefixed key for the same report also works.
For a store configured as `s3://bucket/base`, a report with prefix
`reports/example/revision` reads
`s3://bucket/base/reports/example/revision/images/inventory-chart.png`.
Use `src` for local files or hosted URLs, and `ref` for stored artifacts; supply
exactly one. Renderers fetch stored bytes using the platform's storage access
and embed them in the rendered image. S3 objects need not be public, and the
exported HTML remains portable. Invalid image bytes or missing stored images
fail rendering rather than silently publishing a broken image.

If the source image lives elsewhere in an existing data store, load its bytes
through that BlobStore and register a report-local immutable copy:

```python
from runbook.core import open_blob_store

source_store = open_blob_store("s3://my-data-bucket")
ref = ctx.artifact.image(source_store.get("images/inventory-chart.png"), name="inventory-chart")
grid.image(ref=ref, alt="Oil inventories by month")
```

You normally do not calculate row or column coordinates. `Grid` places peer
blocks first-fit from left to right and then top to bottom. Use `Row` when the
side-by-side relationship matters, and `Stack` when blocks belong together
vertically:

```text
Peers?                              -> Grid
Side-by-side relationship matters? -> Row
Multiple pieces belong together?   -> Stack
```

```python
with layout.grid(columns=2) as grid:
    grid.table(table_ref)
    grid.plot(plot_ref)

with layout.row(columns=2) as row:
    row.table(table_ref)
    row.plot(plot_ref)

with layout.stack() as stack:
    stack.table(table_ref)
    stack.text("Notes")
```

`Stack` can occupy one `Row` slot. This is useful when a table and optional
detail link belong beside a plot:

```python
with layout.row(columns=2) as row:
    with row.stack() as left:
        left.table(returns_ref, name="returns_table", title="Returns")
        if detail_report:
            left.add(Link("View details ->", report=detail_report))
    row.plot(returns_plot_ref, name="returns_plot", title="Returns Plot")
```

`Row` children use one declared slot each; a direct block stretches to the
row's physical height when another slot contains a taller stack. `col_span`
remains a Grid feature; existing `row_span` is supported in Rows and Stacks.

For Grid-only spans, use:

```python
with layout.grid(columns=12) as grid:
    grid.plot(plot_ref, col_span=8, row_span=2)
    grid.text("Commentary", col_span=4)
```

`Report` and `Section` also support `add`, `extend`, and `heading`; `Grid`,
`Row`, and `Stack` support `add`, `extend`, and their block helpers. Functional
`report(...)`, `section(...)`, `grid(...)`, `row(...)`, and `stack(...)` helpers
accept lists, tuples, and generators when context managers are inconvenient.

## Grid rules

- A grid is a flat collection of blocks. Nested grids are rejected; use two
  sibling grids or sections instead.
- The default high-level page width is `max_columns = 12`.
- Different grids are normalized to one page-wide track count using the least
  common multiple (LCM) of their column counts. LCM is never silently rounded.
- If the LCM exceeds the limit, explicitly increase
  `ctx.config["layout"]["max_columns"]` for an intentionally wide report.
- Empty grids and sections are omitted; a completely empty report is invalid.
- Explicit block names are useful for interactive outputs. Generated names are
  stable for insertion order, and duplicate names fail clearly.

Blocks added directly to a `Report` or `Section` are full width. Use a `Grid`
when automatic peer placement or horizontal spans are needed. Layout objects
do not read data, serialize figures, or import Dash; compilation happens after
the report returns. Layout composition lowers to flat PDL coordinates, so
renderers do not need to know about Row or Stack.

## Functional composition

```python
from runbook.sdk.layout import grid, report, section, table

blocks = [table(ctx.artifact.table(make_table(item), name=f"item-{item}"), title=item) for item in items]
return report("Inventory", sections=[section("Items", grid(blocks, columns=2))])
```

## Ordinary Python composition

> Runbook composition uses normal Python. Use functions, loops, and conditionals to build reusable report structures instead of introducing another templating or layout DSL.

Populate a Stack with a loop:

```python
with layout.stack() as stack:
    for spec in report_specs:
        stack.table(spec.table_ref, name=spec.table_name, title=spec.title)
        stack.plot(spec.plot_ref, name=spec.plot_name, title=f"{spec.title} Plot")
```

Generate repeated Rows with a loop:

```python
for spec in report_specs:
    with layout.row(columns=2) as row:
        row.table(spec.table_ref, name=spec.table_name, title=spec.title)
        row.plot(spec.plot_ref, name=spec.plot_name, title=f"{spec.title} Plot")
```

A helper can return a composable Row or Stack:

```python
def build_market_row(spec):
    row = Row(columns=2)
    with row.stack() as left:
        left.table(spec.table_ref, name=spec.table_name, title=spec.title)
        if spec.detail_report:
            left.add(Link("View details ->", report=spec.detail_report))
    row.plot(spec.plot_ref, name=spec.plot_name, title=f"{spec.title} Plot")
    return row


for spec in report_specs:
    layout.add(build_market_row(spec))
```

Or a helper can populate a supplied Stack/Row:

```python
def add_market_summary(stack, spec):
    stack.table(spec.table_ref, name=spec.table_name, title=spec.title)
    if spec.detail_report:
        stack.add(Link("View details ->", report=spec.detail_report))


with layout.stack() as stack:
    for spec in report_specs:
        add_market_summary(stack, spec)
```

Both styles are ordinary Python; use whichever keeps the report definition
easiest to read.

Use this API before dropping to the lower-level PDL constructors. The advanced
escape hatch is documented in [Reports](reports.md).
