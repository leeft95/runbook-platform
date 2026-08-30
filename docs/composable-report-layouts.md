# Composable report layouts

For report authors

`Report` is the whole page, `Section` is a named part of the page, and `Grid`,
`Row`, and `Stack` compose finished text, table, plot, and link artifacts:

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
