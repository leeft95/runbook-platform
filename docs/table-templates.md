# Table templates

For report authors

For an end-to-end report recipe, see the [Reports
cookbook](reports.md#reports-cookbook).

Runbook has three related pieces:

```text
table style helper -> changes how one table looks
table template     -> transforms data, builds style rules, may build plots
layout             -> decides where the finished artifacts appear
```

The flagship template, `table_with_linked_plots_monthly`, creates a monthly
summary and one seasonal chart for each input column. It returns a mapping of
the requested header to a payload with:

```text
data  -> the display DataFrame
style -> a serializable table style plan
plots -> a list of Plotly Figures
```

## Complete report integration

The helper expects a DataFrame indexed by dates. Its default 20-observation
moving average needs enough rows for the input series; pass
`moving_averge_window=None` when that companion smoothing is not wanted. The
helper output is not yet a Runbook artifact: store each part explicitly, then
place the references in a layout.

```python
from runbook.core.table import table_with_linked_plots_monthly
from runbook.sdk.layout import Report


def build(ctx, raw_prices):
    result = table_with_linked_plots_monthly(raw_prices, header="Month")
    payload = result["Month"]

    table_ref = ctx.artifact.table(
        payload["data"],
        name="monthly-summary",
        style=payload["style"],
    )
    plot_refs = [
        ctx.artifact.plot(figure, name=f"monthly-seasonal-{index}") for index, figure in enumerate(payload["plots"])
    ]

    layout = Report("Monthly summary")
    with layout.section("Summary") as section:
        with section.grid(columns=1) as table_grid:
            table_grid.table(table_ref, title="Monthly summary")
        with section.grid(columns=2) as grid:
            for plot_ref in plot_refs:
                grid.plot(plot_ref)
    return layout
```

In a `@report.page`, call the function with `raw_prices=ctx.calc("prices")`
or another calculation result. The helper's exact parameters are:

```python
from runbook.core.timeseries.analysis import MovingAvgModes

table_with_linked_plots_monthly(
    raw_df,
    header,
    moving_averge_window=20,
    moving_average_type=MovingAvgModes.SIMPLE,
    aggregation_type=None,
    columns_filter=None,
    aggregation_columns=None,
    highlighting_rules=None,
    benchmark_month=None,
    benchmark_quater=None,
    fill_na=None,
    na_rep="-",
)
```

The spellings `moving_averge_window` and `benchmark_quater` are the current
public parameter names. Use keyword arguments so the code remains readable.
The template returns a serializable style payload; `ctx.artifact.table` turns
it into the immutable table data/style/HTML artifacts consumed by renderers.

## Style helpers

For a table you already have, use the style helpers or a `table_style` plan,
then pass it to `ctx.artifact.table`:

```python
from runbook.sdk.table_style import format_percent, table_style

style = table_style(
    key="returns-v1",
    formats=[format_percent("returns", digits=2)],
    max_rows=100,
)
table_ref = ctx.artifact.table(frame, name="returns", style=style)
```

`highlight`, `highlight_on_key`, `highlight_on_range`, and `highlight_zscore`
are available from `runbook.core.table` for reusable rule construction. A
style changes presentation only; a template such as the monthly helper also
calculates the table and companion plots.

## Choosing the right layer

- Use a style helper when the DataFrame and its shape are already right.
- Use `table_with_linked_plots_monthly` for the standard monthly summary and
  seasonal companion figures.
- Use `Report`/`Section`/`Grid` to position the finished table and plots; do
  not put layout coordinates into the template.

The static HTML renderer displays the table and plots. Interactive reports can
add semantic column metadata; see [Interactive reports](pdl-interactive.md).
