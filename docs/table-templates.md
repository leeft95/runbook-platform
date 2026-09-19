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

For v0.3.2, an ordinary report table renders as an HTML table in the HTML
renderer and as a native static Dash table in the Dash renderer. AG Grid is an
explicit opt-in for interactive table output; it is not the default table
representation.

The flagship template, `table_with_linked_plots_monthly`, creates a monthly
summary and one seasonal chart for each input column. It returns a mapping of
the requested header to a payload with:

```text
data  -> the display DataFrame
style -> a serializable table style plan
plots -> a list of Plotly Figures
```

The display DataFrame retains its meaningful index and names it with the
requested `header`; this is the visible index header used by aggregate plot
links.

## Complete report integration

The helper expects a DataFrame indexed by dates. Its default 20-observation
moving average needs enough rows for the input series; pass
`moving_average_window=None` when that companion smoothing is not wanted. The
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
    moving_average_window=20,
    moving_average_type=MovingAvgModes.SIMPLE,
    aggregation_type=None,
    columns_filter=None,
    aggregation_columns=None,
    highlighting_rules=None,
    benchmark_month=None,
    benchmark_quarter=None,
    fill_na=None,
    na_rep="-",
    row_plot_links=True,
    all_plots_link=True,
)
```

Use keyword arguments so the code remains readable.
The template returns a serializable style payload; `ctx.artifact.table` turns
it into the immutable table data/style/HTML artifacts consumed by renderers.
For `name="monthly-summary"`, these are `tables/monthly-summary.parquet`,
`styles/monthly-summary.json`, and `tables/monthly-summary.html` inside the
report revision. Reusing the name accepts identical content; use another name
for different data, style, or rendered HTML. `table_style_hash` remains
available for metadata and comparisons, but is not part of artifact filenames.

### Semantic links and plot pages

Never put raw `<a>` markup in a DataFrame. Declare links in the table style
plan with semantic destinations instead:

```python
from runbook.sdk.table_style import link_column

style = {
    "links": [
        link_column("price", report_id_from="detail_report"),
        link_column("source", url_from="source_url"),
    ]
}
```

`general_table_with_link` and `table_with_linked_plots_monthly` can derive
stable plot names. In the general table, `column_plot_links=True` links
rendered column headers to individual pages, and `all_plots_link=True` links
the index header to the deterministic aggregate page. The monthly template's
`row_plot_links` selects original input series names and links the displayed
label column cells, even when the table headings are periods; its
`all_plots_link=True` links that label column's header. A filtered-out series
has no row link; aggregation labels such as `Brent [MA]` are used as the
displayed cell value.

For example, link every input series or select only one while keeping the
aggregate link:

```python
from runbook.core.table import table_with_linked_plots_monthly

all_series = table_with_linked_plots_monthly(raw_df, header="Monthly", row_plot_links=True, all_plots_link=True)
one_series = table_with_linked_plots_monthly(raw_df, header="Monthly", row_plot_links=["Brent"], all_plots_link=True)
```
The HTML execution bundle publishes those linked pages under
`plots/<name>.html`, and the Dash renderer exposes the same logical names to
the host's route resolver.

For a manually built table, declare a cell link on the label column and keep
the plot destination in a hidden helper column:

```python
import pandas as pd
from runbook.core.table import (
    TableLink,
    TableLinkDestination,
    TableLinkKind,
    TableStylePlan,
    render_table_html,
)

frame = pd.DataFrame(
    {
        "Asset": ["Brent", "WTI"],
        "value": [10, 20],
        "_plot_link": ["asset-brent", None],
    }
)
style = TableStylePlan(
    links=[
        TableLink(
            area="cells",
            field="Asset",
            destination=TableLinkDestination(kind=TableLinkKind.plot, value_field="_plot_link"),
        )
    ],
    options={"show_index": False, "hidden_columns": ["_plot_link"]},
)
html = render_table_html(frame, style)
```

The cell's `field` is the displayed label and `value_field` points to the
hidden destination column. Use `area="header"` on `Asset` separately when
the label-column heading should link to an aggregate plot page. The monthly
template applies this same cell-link shape automatically.

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
