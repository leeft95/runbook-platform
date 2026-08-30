# Composable report layouts

For report authors

`Report` is the whole page, `Section` is a named part of the page, and `Grid`
places finished text, table, and plot artifacts side by side:

```text
Python artifacts -> Report / Section / Grid -> PDL -> HTML or Dash
```

Layout placement is renderer-neutral: ordinary tables remain HTML tables or
native static Dash tables, and semantic cell/header links remain intact. A
report host owns Dash navigation; AG Grid is an explicit interactive-table
choice rather than a layout default.

```python
from runbook.sdk.layout import Report


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

You normally do not calculate row or column coordinates. `Grid` places blocks
first-fit from left to right and then top to bottom. `col_span` and `row_span`
let a block occupy more than one track:

```python
with layout.grid(columns=12) as grid:
    grid.plot(plot_ref, col_span=8, row_span=2)
    grid.text("Commentary", col_span=4)
```

`Report` and `Section` also support `add`, `extend`, and `heading`; `Grid`
supports `add`, `extend`, `table`, `plot`, and `text`. Functional
`report(...)`, `section(...)`, and `grid(...)` helpers accept lists, tuples,
and generators when context managers are inconvenient.

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
when horizontal placement or spans are needed. Layout objects do not read
data, serialize figures, or import Dash; compilation happens after the report
returns.

## Functional composition

```python
from runbook.sdk.layout import grid, report, section, table

blocks = [table(ctx.artifact.table(make_table(item), name=f"item-{item}"), title=item) for item in items]
return report("Inventory", sections=[section("Items", grid(blocks, columns=2))])
```

Use this API before dropping to the lower-level PDL constructors. The advanced
escape hatch is documented in [Reports](reports.md).
