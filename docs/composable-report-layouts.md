# Composable report layouts

Report authors compose ordinary Python into a renderer-neutral layout:

```text
ordinary Python -> Report / Section / Grid -> pdl-core/0.1 -> HTML or Dash
```

The high-level API is available from `runbook.sdk.layout`:

```python
from runbook.sdk.layout import Report


def build(ctx):
    page = Report("Crude Oil Weekly")
    with page.section("Regional Balances") as balances:
        with balances.grid(columns=2) as items:
            for region in ["North", "South", "West"]:
                table_ref = ctx.artifact.table(build_table(ctx, region), name=f"{region.lower()}-balance")
                plot_ref = ctx.artifact.plot(build_plot(ctx, region), name=f"{region.lower()}-history")
                items.table(table_ref, title=f"{region} balance")
                items.plot(plot_ref, title=f"{region} history")
    return page
```

`ctx.artifact.table(...)` returns the table reference accepted by `table(...)`,
and `ctx.artifact.plot(...)` returns the string reference accepted by
`plot(...)`. Layout objects do not read data, serialize figures, or know about
Dash. The execution boundary compiles the returned `Report` to the existing
PDL manifest before any renderer starts.

## Functional composition

The same plain dataclasses can be built without context managers. Lists, tuples,
and generators are ordinary Python inputs:

```python
from runbook.sdk.layout import grid, report, section, table

blocks = [table(ctx.artifact.table(make_table(item), name=f"item-{item}"), title=item) for item in items]
return report("Inventory", sections=[section("Items", grid(blocks, columns=2))])
```

`Report` and `Section` provide `add`, `extend`, and `heading`; `Grid` provides
`add`, `extend`, `table`, `plot`, and `text`. There are no row or column
coordinates in normal authoring. Placement is stable first-fit, left-to-right
and then top-to-bottom. `col_span` and `row_span` are optional, and invalid
spans fail before rendering.

Non-empty logical grids share one PDL page width. Their column counts are
combined with `math.lcm`; each local position is scaled into those tracks. The
default `layout.max_columns` limit is 12. A larger LCM requires explicitly
setting `ctx.config['layout']['max_columns']` for an ultrawide report; it is
never silently rounded.

Empty grids and sections are omitted. A completely empty report is an error.
Block names are stable for insertion order; explicit names remain the right
choice for interactive outputs and duplicate names fail clearly.

## Choosing an API level

Use the highest-level layout API that solves the report. Drop to raw PDL only
when the builder cannot express a requirement. Do not introduce a new
abstraction until at least two concrete reports need it.

The low-level `runbook.sdk.ui` constructors and `pdl-core/0.1` models remain
supported as an escape hatch for framework tests and unusual layouts.
