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

## ECM report migration coverage

Preview all the new templates and charts with synthetic data:

```bash
pixi run python scripts/preview_gallery.py --serve --port 8766
```

Open `http://127.0.0.1:8766/`. The gallery includes working companion-chart
links and a live HTML / native Dash / AG Grid comparison for every table.
Without `--serve`, it exports the gallery to `/tmp/runbook-gallery/index.html`.
Every preview card names its public template function.

## Named table templates

Import these from `runbook.core.table.templates`. They return the same
`{header: {"data": frame, "style": plan, "plots": figures}}` payload as the
general builders. Preset options can be overridden using the underlying
builder's keyword arguments. Data, dates, exclusions and benchmarks are supplied
by the caller; templates contain no fixture data or fixed report dates.

| Source report / reference | Public preset | Expected input / calculation |
| --- | --- | --- |
| `positioning/cot_cme.py`, `cot_ice.py`, `cot_macro.py` | `cot_cme_timeseries_table`, `cot_ice_timeseries_table`, `cot_macro_timeseries_table` | Dictionary of dated Long/Short frames; `runbook.core.cot.analysis` (52 observations) |
| Same reports, already calculated | `cot_cme_summary_table`, `cot_ice_summary_table`, `cot_macro_summary_table` | Existing `analysis` summary rows |
| `positioning/cot_ice_mifid.py`, `cot_euattf.py`, `cot_lme.py` | `cot_ice_mifid_timeseries_table`, `cot_euattf_timeseries_table`, `cot_lme_timeseries_table` | Dictionary of dated Long/Short frames; `analysis_mifid` (208 observations) |
| Same reports, already calculated | `cot_ice_mifid_summary_table`, `cot_euattf_summary_table`, `cot_lme_summary_table` | Existing `analysis_mifid` summary rows |
| CME / macro alerts | `cot_cme_position_change_table`, `cot_macro_position_change_table`; `cot_cme_position_divergence_table`, `cot_macro_position_divergence_table` | Summary rows screened by `position_change` / `position_divergence` |
| `oil/dashboard.py` | `oil_dashboard_table` | Daily prices; ten rows, 20-observation MA, linked seasonal charts |
| `oil/kpler_inventory.py`, `product_inventory.py` | `kpler_inventory_table`, `product_inventory_table` | Prepared daily stocks; 20-observation changes, three months, four quarters, QTD, Y-1/5Y; excludes 2020 |
| Consensus rows in those inventory reports | `kpler_inventory_consensus_table`, `product_inventory_consensus_table` | Monthly balances; Kpler global crude uses means, product consensus uses levels; three quarters; `aggregation_type="diff"` for US crude |
| `oil/russia_exports.py`, `opec_exports.py`, `clean_exports.py`, `oil_demand_centres.py` | `russia_exports_table`, `opec_exports_table`, `clean_exports_table`, `oil_demand_centres_table` | Prepared daily flows; 10/20-observation means, five months, 92-observation highlights, supplied quarter benchmark |
| `oil/oil_on_water.py` | `oil_on_water_table` | Prepared regional levels; 20-observation means, differences for `Total MTD Chg`, three quarters, QTD |
| `cross_cmds/futures_price_range.py` | `futures_price_range_table` | Calculated price-range rows; signed percentile bars, two-decimal prices/z-scores and optional group separators |
| Supplied EU power-stack reference | `eu_power_rollup_table` | One dated frame of levels or ratios; calendar roll-ups and linked history/seasonal plots |

Report names with identical calculations and defaults are aliases of one preset. Their
source paths are relative to `new_reports/`. `eu_power_rollup_table` comes from
the supplied reference, not a recovered report file. Each docstring states
which prepared data the report passes in: provider fetching, totals, participant
aggregation, units and any upstream smoothing remain the caller's responsibility.
This is a catalog of implemented presets, not a port of every custom table in
`new_reports`; some recovered report/helper sections are incomplete.

```python
from runbook.core.table.templates import kpler_inventory_table, russia_exports_table

inventory = kpler_inventory_table(
    stock_history, "Stocks", aggregation_columns={"Total (kbd)": "mean"}
)
flows = russia_exports_table(flow_history, "Flows", benchmark_quarter="2025Q4")
```

The original generic presets remain available with their existing defaults:
`daily_prices_table`, `inventory_summary_table`, `flow_quarterly_table`,
`flow_monthly_table`, `monthly_consensus_table`, `mtd_inventory_table`,
`grouped_metrics_table` and `rollup_table_hst`. The forecast variation is
`rollup_table_fst`. The monthly-sum and true-MTD
gallery cards are explicitly generic examples: no matching
source report was found for those exact presets. In particular, the source
`oil_on_water.py` names a row **Total MTD Chg** but calculates a 20-observation
difference; it does not enable the builder's true month-to-date mode.

COT calculation-family names (`cot_analysis_*`, `cot_analysis_mifid_*`) remain
aliases of the report presets. `cot_timeseries_table` remains the generic
calculator and `cot_summary_table` the generic summary styler. Use
`summary_options` for shared calculation parameters and `asset_options` for
per-asset overrides. Summary presets preserve supplied scores and windows.
`futures_price_range_table` is the report preset for the signed data-bar preview.
It accepts the source report's calculated columns: `Current price vs history`,
`Current Price`, `Percentile of 10yr Range`, `Z-score of 10yr Range`,
`10yr Avg Price`, `10yr Max` and `10yr Min`. Use `history_years` for another
history horizon, and `separator_rows` for zero-based group boundaries.
Prices and scores retain two decimals; percentile bars span −1 to +1 and
display one decimal percent. All columns, including instrument names, are centered.
`Current price vs history` becomes the row index, replacing the input RangeIndex.
The template preserves calculated values; contract-history selection and
percentile calculations stay with the caller.

Its lower-level helper `grouped_metrics_table` remains available and accepts arbitrary pandas Index/MultiIndex axes,
`percentage_rows` as row positions, and `bar_columns` as actual column labels.

## Calendar roll-up table

`rollup_table_hst(df, params)` takes **one numeric time-series DataFrame** with
a unique `DatetimeIndex` and one column per input series. It returns one row
per series. `Latest` uses the final supplied row (after any `as_of` filter),
not a per-series last non-null observation. Input data is never modified or filled.

The **final input column supplies the total row**. For example, the power demo's
`Load` is total load, not an additional component. The template displays that row
as **Total**, with a top border and bold label and values in every renderer.
It uses the supplied series directly; it does not sum components or append a row.
Use `total_label="Load"` (or any other name) to override the label, or
`total_label=None` when the input has no total series. Linked plots use the same
label and supplied total data; `row_plot_links` selections accept the original
input column name.

```python
from runbook.core.table.templates import rollup_table_hst

params = ["Latest", "5d MA", "20d MA", "3m MA", "Y-1 20d MA", "5Y 20d MA"]
payload = rollup_table_hst(power_ts, params, header="EU power")["EU power"]

# Supply a time-series frame of ratios to reuse the template for power shares
# or thermal shares; formatting does not change the underlying numbers.
shares = rollup_table_hst(
    share_ts, params, header="EU power share", format_spec="{:.1%}"
)["EU power share"]
```

| Default column | Calculation |
| --- | --- |
| `Latest` | Exact final supplied row after `as_of` filtering, including missing values |
| `5d MA` | Mean of observations in the last five **calendar days** |
| `20d MA` | Mean of observations in the last twenty **calendar days** |
| `3m MA` | Mean of observations in the last three **calendar months** |
| `Y-1 20d MA` | Twenty-calendar-day mean ending on the corresponding date last year |
| `5Y 20d MA` | Equal-weight mean of the corresponding window means in the previous five calendar years |

Each window is `(anchor - window, anchor]`, where `anchor` is the timestamp
of the final supplied row after applying `as_of`. Calculations sort the data
and exclude rows later than that anchor, so unsorted inputs do not change the
meaning of Latest. Missing values are skipped; an all-missing
window remains missing. Historical windows with no data are omitted from the
five-year mean, without substituting older years. `exclude_years` removes
specified historical years. Leap-day anniversaries use February 28 in
non-leap years. Calendar offsets preserve local clock time across DST.

`params` selects and orders roll-ups. Other positive lengths work too, such as
`10d MA`, `6m MA`, `Y-2 20d MA` and `3Y 5d MA`. No completed-month/quarter
columns are added. The screenshot's separately supplied **Current Month Base**
is not inferred by this historical template; the forecast variation below
adds a calculated **Current Month** column.

Each series name links to a figure with its **full base history**, **seasonal
base data**, and **seasonal rolling averages** for the requested windows.
Historical summary columns reuse their base window's seasonal panel. The
heading links to all generated figures, with the ordinary `plot_names` and
`all_plots_name` payload fields. These figures use the same calendar-average
calculation as the table. `row_plot_links=False` and `all_plots_link=False`
disable links; the generated figures remain available in `plots`.

Columns are centered by default. **Every moving-average column**, including
historical references, uses the general linked table's z-score highlighting.
`Latest` itself is excluded. The signal is Latest minus the displayed column's
mean, divided by its reference sample standard deviation:

- Current MAs use observations in that column's calendar window.
- `Y-1` (or `Y-N`) uses observations in the matching window of that prior year.
- `5Y` (or `NY`) uses the prior yearly window averages, giving each available
  year equal weight and respecting `exclude_years`.

By default, above +1/+2 SD is light green/green; below -1/-2 SD is orange/red.
Set `std_limits=(1.5, 2.5)` to move those bands to ±1.5/±2.5 SD for every
highlighted average column. Both limits must be finite and positive, with the
mild limit smaller than the strong limit. Comparisons are strict: a value
exactly on a limit does not trigger that band. This changes only highlighting,
not the averages or standard deviations used in the calculations.

```python
payload = rollup_table_hst(power_ts, std_limits=(1.5, 2.5))["Roll-up"]
# The report preset accepts the same option:
# eu_power_rollup_table(power_ts, std_limits=(1.5, 2.5))
```

Missing or zero dispersion produces no z-score highlight. Rules work on underlying
numeric values, regardless of whether they display as prices, volumes,
percentages or other numeric formats. Hidden helper columns carry the statistics.
Use `highlight_columns` to select a subset of current/historical MA columns,
or `highlight_columns=[]` to disable bands. `Latest` cannot be selected.
Negative numbers continue to use the shared red-text rule.

Use `format_spec` for precision or percentages,
`rules` for additional shared `TableRule` overrides, `footer`
for a custom note, and `plot_options` for seasonal chart settings. Roll-ups have
no footer by default.

## Forecast roll-up table

`rollup_table_fst(df, df_hst=None, params=None)` is the variation for a
time-series DataFrame containing forecasts. It keeps the historical template's
formats, total row, links, calendar windows and configurable `std_limits`.

All values are calculated from **`df`**. The optional **`df_hst`** selects the
Latest date using the index of its final supplied row. If it is `None` or empty,
the final supplied row of **`df`** selects that date. `Latest` reads the exact
matching row in `df`, including missing values; a missing date stays missing.
Historical values are not merged into `df`. Every moving average and prior-year
comparison is anchored to this same Latest date, excluding later observations
from its window.

The default columns, in order, are **Current Month**, **Latest**, **5d MA**,
**20d MA**, **3m MA**, **Y-1 20d MA**, and **5Y 20d MA**. `params` selects and
orders them, with the same customizable MA windows as `rollup_table_hst`.

**Current Month** averages all supplied observations in today's calendar month,
including future dates in that month. This month is independent of the Latest
date. `today` optionally fixes the current date for a reproducible report;
otherwise the date is read in `df`'s timezone. It does not change the Latest
date or the MA anchor. Missing observations are skipped without filling.

```python
from runbook.core.table import rollup_table_fst

payload = rollup_table_fst(
    forecast_ts,
    df_hst=historical_ts,  # Optional; otherwise use forecast_ts's final row date.
    header="EU power forecast",
    std_limits=(1.5, 2.5),
    format_spec="{:,.1f}",
)["EU power forecast"]
```

For example, if `today="2025-07-10"` and the last `df_hst` row is dated June 20,
Current Month uses all supplied July observations, while Latest and every MA
reference June 20. The linked history and seasonal charts retain all supplied
data, including forecasts after that date.

Current Month also receives z-score highlighting, comparing Latest with the
month's mean and sample standard deviation. `std_limits` applies to it and
all MA columns. `highlight_columns` can select average columns or disable
highlighting with `[]`; Latest itself remains excluded.

## Calendar balance tables

`period_table` builds monthly, quarterly, seasonal, summer, winter and annual
tables from one dated DataFrame. The named templates below are predefined
wrappers around that shared calculation and style builder. Import them from
`runbook.core.table` or `runbook.core.table.templates`.

| Level table | Absolute YoY difference table | Period / row labels |
| --- | --- | --- |
| `monthly_table` | `monthly_table_yoy` | Calendar months, e.g. `Apr26` |
| `quarterly_table` | `quarterly_table_yoy` | Calendar quarters, e.g. `Q2 2026` |
| `seasonal_table` | `seasonal_table_yoy` | Both summers and winters, in chronological order |
| `summer_table` | `summer_table_yoy` | April–October, e.g. `Sum19` |
| `winter_table` | `winter_table_yoy` | November–March, e.g. `Win19` for Nov 2019–Mar 2020 |
| `annual_table` | `annual_table_yoy` | Calendar years, e.g. `2026` |

All numeric columns are averaged directly from the supplied observations;
non-numeric columns are ignored. Quarters, seasons and years are not averages
of monthly averages. Partial periods are included, missing values skipped,
and missing periods are not filled. Dates are parsed and sorted on a copy;
timezone removal preserves local clock time. Duplicate or missing dates are
rejected, including duplicates introduced by parsing or timezone removal.

YoY means the current period's mean minus the **same period one calendar year
earlier**, in the original units. Winter is compared with winter, summer with
summer, and quarter with the same quarter. A missing prior period produces a
missing difference, displayed as `-`; another available period is never
substituted. Date selection is an upstream responsibility: the templates use
all supplied observations. Prior-year comparisons require the corresponding
history in the supplied frame.

```python
from runbook.core.table import monthly_table, monthly_table_yoy, winter_table, period_table

options = dict(column_formats={"NATL_GS": "{:.2f}"})
monthly = monthly_table(g, **options)["Monthly"]
monthly_yoy = monthly_table_yoy(g, **options)["Monthly YoY"]
winter = winter_table(g, **options)["Winter"]

# The shared builder produces the same payload as quarterly_table_yoy(g, ...).
quarterly_yoy = period_table(g, period="quarterly", yoy=True, **options)["Quarterly YoY"]
```

All columns are centered. **Negative values are red in every level and YoY
table.** Monthly, quarterly and seasonal tables alternate blue/white rows;
annual tables use solid blue, matching the reference. The period label is
the first visible column, with no extra index-name row. No total row is added.

The shared options include `header`, `format_spec` (default `"{:,.0f}"`),
`column_formats` for per-column formats, `column_width`/`index_width` (85 pixels
each), and `rules` for additional style overrides. Formatting leaves numeric
values intact. Each template returns `{header: {"data": frame, "style": plan,
"plots": []}}`, usable in HTML, native Dash and AG Grid. All twelve templates
have examples in the preview gallery.

## Shared migration builders

The recovered ECM core and report callers use the following capabilities.
Runbook provides them through shared models and dataset-first helpers:

| ECM capability | Runbook implementation |
| --- | --- |
| COT summary calculations, rank/threshold highlights, section boundaries, hidden signals, linked asset names | `cot_summary`, `cot_position_changes`, `cot_position_divergence`, and `cot_summary_table` |
| Custom numeric formats by row/cell, grouped axes, in-cell bars | `TableRowFormat`, pandas MultiIndex inputs, and `TableAction(data_bar=...)` across HTML, native Dash, and AG Grid |
| Inventory `table_format1`, monthly consensus, flow `table_format2`, month/quarter benchmarks | Options on `table_with_linked_plots_monthly` |
| Daily linked tables with MA/comparison charts, footer, and label widths | `general_table_with_link` |
| Regression/price-position charts, flexible COT and OHLC panels, seasonal/history composites, single-bar highlights | [Plotting helpers](plotting-helpers.md) |

These are migration building blocks, not a drop-in replacement for ECM's
Windows-file/report APIs. Reports still supply their datasets, instrument
mappings, contract multipliers, participant definitions, and artifact layout.
The recovered reports contain photo-transcription gaps, so validation uses
explicit calculation fixtures and rendered examples rather than claiming a
complete live-report comparison. Known date-order, four-interval, price-return,
and missing-history errors are corrected rather than copied.

For v0.3.2, an ordinary report table renders as an HTML table in the HTML
renderer and as a native static Dash table in the Dash renderer. AG Grid is an
explicit opt-in for interactive table output; it is not the default table
representation.

All columns are centered by default in HTML, native Dash, and AG Grid.
Explicit `TableAction(text_align="left")` or `text_align="right"` rules override
the default for selected cells. Header alignment uses
`TableGlobalStyle.header_text_align`, which also defaults to `"center"`.

The flagship template, `table_with_linked_plots_monthly`, creates a monthly
summary and one seasonal chart for each input column. It returns a mapping of
the requested header to a payload with:

```text
data  -> the display DataFrame
style -> a serializable table style plan
plots -> a list of Plotly Figures
```

The display DataFrame has a label column named with the requested `header`.
This column carries row plot links; its heading carries the aggregate plot link.

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
    windows=(10, 20),
    history_months=5,
    history_quarters=0,
    include_qtd=False,
    comparison_years=None,
    exclude_years=None,
    input_frequency="D",
    as_of=None,
    smooth=None,
    mtd=False,
)
```

Use keyword arguments so the code remains readable.

### Inventory and flow summary variants

The same template covers ECM's `table_format1` inventory tables and
`table_format2` flow tables. For an inventory table with mixed stock changes
and flow averages:

```python
payload = table_with_linked_plots_monthly(
    inventory,
    "Inventory",
    aggregation_type="diff",
    aggregation_columns={"Flow": "mean"},
    windows=(20,),
    history_months=3,
    history_quarters=4,
    include_qtd=True,
    comparison_years=5,
    exclude_years=[2020],
    highlighting_rules={"seasonal": 5},
    row_plot_links=True,
)["Inventory"]
```

Windows count observations for daily inputs. Monthly consensus inputs use
`input_frequency="M", windows=(1,), moving_average_window=None`; one input
row is allowed per calendar month, and missing months are inserted before
calculations. The column heading uses `m` instead of `d`. Aggregation accepts
`diff`/`change`, `sum`, `mean`/`ma`, and `None`/`level`/`last`; per-column
overrides are annotated on the row label. Level mode uses the latest value.
Calendar changes use consecutive period-end levels, averages use available
observations, and sums keep wholly missing periods missing.

`history_months` and `history_quarters` show completed calendar periods in
reverse order. `include_qtd` adds the current partial quarter. `comparison_years`
adds the actual prior calendar year's same-date rolling value and the mean of
the requested number of available prior years, respecting `exclude_years`.
An excluded or absent prior year remains missing. These comparisons do not
depend on enabling highlight rules.

`benchmark_month` compares the first window with that month's aggregate;
`benchmark_quarter` compares the last window with the equally weighted mean of
the three monthly aggregates. Missing benchmark periods remain missing. Set
only one benchmark. `smooth` averages stock levels before rolling differences;
it does not change calendar aggregates. `mtd=True` instead measures each DIFF
rolling average from its prior calendar month-end, including historical
observations used for highlighting. This applies consistently to the default
mode and overrides; headings explicitly say `MTD basis`. It cannot be combined
with `smooth`.

`as_of` filters before filling, smoothing, statistics, and plots. An optional
input `_last_update` metadata column is carried as a hidden output field.
Short histories produce missing rolling measures and an explanatory empty
companion chart when the smoothing window cannot be computed.

### Daily linked tables

`general_table_with_link` accepts chart selections per column or tuple of
columns. Values can be `"line"`, `"seasonal"`, `"seasonal_mva"`, a positive
integer for a line chart with that moving-average window, or a dated DataFrame
to overlay on a secondary axis. Comparison data is sorted and forward-aligned
to the primary dates without borrowing future observations. Chart options do
not change the table's moving-average summary calculation.

`footer` is plain text rendered in HTML, native Dash, and AG Grid;
`title_column_width` controls the index column. These also work on custom
tables through `TableStyleOptions(footer=...)`,
`TableSizing(index_width_px=...)`, or SDK
`table_style(footer=..., index_width_px=...)`.
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

## Mixed formats within a column

Use `format.rows` when a report mixes levels, percentages or dates in the same
column. A `TableRowFormat` selects a row by index label or original position;
its optional `columns` list limits the override to particular cells. Column
formats override the global default, then row overrides apply in list order.
The last matching override wins. Hidden rows and `max_rows` do not renumber
positions. Formats change display only: numeric values stay numeric in Parquet
artifacts and in AG Grid sorting/filtering.

```python
from runbook.sdk.table_style import format_number, format_row, table_style

style = table_style(
    formats=[
        format_number("Latest", digits=0, thousands=True),
        format_row(
            {"mode": "label", "value": "% OI"},
            "{:.2%}",
            columns=["Latest", "Change"],
        ),
        format_row(
            {"mode": "position", "value": 3},
            "{:.1f}",
            columns=["Latest"],
        ),
    ],
    na_rep="-",
)
table_ref = ctx.artifact.table(frame, name="inventory", style=style)
```

The same plan works in HTML, native Dash and AG Grid. Row overrides require
`table-style/0.2`; existing plans without overrides retain their previous payload.

## Grouped table headers and row indexes

Tables accept pandas `MultiIndex` columns and indexes. HTML and native Dash
preserve contiguous column spans and row spans; AG Grid uses nested column
groups and separate index-level fields. Parent labels are never merged across
different parents or noncontiguous groups. Parquet artifacts retain the original
axes rather than storing flattened display strings.

Style plans and PDL use string field keys. Reference a complete MultiIndex
column with `str(column_tuple)`, including in formats, rules, sizing, hidden
columns and links. Row references accept complete tuple labels (JSON arrays
after serialization); positional references work unchanged. Header and index
links attach to the corresponding leaf label.

```python
from runbook.core.table import TableStylePlan

latest = str(("January", "Latest"))
signal = str(("January", "_signal"))
plan = TableStylePlan.model_validate(
    {
        "format": {
            "columns": {latest: "{:,.1f}"},
            "rows": [
                {
                    "row_ref": {"mode": "label", "value": ("Europe", "Returns")},
                    "columns": [latest],
                    "spec": "{:.2%}",
                }
            ],
        },
        "options": {"hidden_columns": [signal]},
    }
)
```

## In-cell data bars

Add `TableAction(data_bar=TableDataBar(...))` to an ordinary rule, or use the
SDK action builder. This reproduces the signed bars in price-range tables:

```python
from runbook.sdk.table_style import action, format_percent, rule, table_style, target_columns

style = table_style(
    formats=[format_percent("Percentile of 10yr Range", digits=1)],
    rules=[
        rule(
            "range_bar",
            target_columns(["Percentile of 10yr Range"]),
            action=action(data_bar={"vmin": -1, "vmax": 1}),
        )
    ],
)
```

Bars use the same resolved CSS in HTML, native Dash and AG Grid, without
changing the displayed number or its numeric sorting. Values outside explicit
bounds have clipped bars and retain their actual numeric labels. Missing or
non-finite values have no bar. Omitted bounds are inferred separately for each
target column from finite values within `max_rows`, before hiding rows or
applying conditions. Client-side filtering retains that scale.

`align="mid"` draws from zero proportionally within the range, from the left
for positive-only data, and from the right for negative-only data.
`align="zero"` places zero at the center using a symmetric range; `left` and
`right` use fixed edges. `positive_color` and `negative_color` customize the
palette. Bars compose with row formats, borders, text colors and background
highlights, and require `table-style/0.2`.

## Choosing the right layer

- Use a style helper when the DataFrame and its shape are already right.
- Use `table_with_linked_plots_monthly` for the standard monthly summary and
  seasonal companion figures.
- Use `Report`/`Section`/`Grid` to position the finished table and plots; do
  not put layout coordinates into the template.

The static HTML renderer displays the table and plots. Interactive reports can
add semantic column metadata; see [Interactive reports](pdl-interactive.md).

## COT tables from existing summary data

The report presets map directly to the ECM calculation families:

| ECM quant helper | Runbook table presets | Reports in `new_reports/positioning` | Input / defaults |
| --- | --- | --- | --- |
| `cot.analysis` | `cot_cme_summary_table`, `cot_cme_timeseries_table` | `cot_cme.py`, `cot_ice.py`, `cot_macro.py`; `cot_cme_monday.py` calls CME/macro | Summary: `Net Position (MM)`, optional `Net Position (NC)`. Time series: 52-observation position scores. |
| `cot.analysis_mifid` | `cot_ice_mifid_summary_table`, `cot_ice_mifid_timeseries_table` | `cot_ice_mifid.py`, `cot_euattf.py`, `cot_lme.py` | Summary: `Net Position`. Time series: 208-observation position scores. |
| `cot.position_change` | `cot_cme_position_change_table` | `cot_cme.py:update_cme`, `cot_macro.py:update_macro` | Summary rows with `net change z score` and `4w delta change z score`; threshold defaults to 1.5. |
| `cot.position_divergence` | `cot_cme_position_divergence_table` | `cot_cme.py:update_cme`, `cot_macro.py:update_macro` | Summary rows with `Weekly Delta Change` and `Weekly Price Change`; selects opposite signs. |

The analysis summary presets use the first column as the instrument label,
matching ECM's date-range heading. Both accept `label_column` and
`position_column` overrides. CME/ICE dealer reports use the standard
`analysis` calculation with `header="Swap Dealers Net Position"`; macro uses
`header="Speculators Net Position"`. The calculation family determines the
preset, rather than the exchange name alone.

`cot_summary_table` supplies their shared presentation through the
`TableStylePlan`, `TableRule`, formatting, sizing, and semantic-link models.
It accepts already-calculated summaries; it does not require new COT analytics
or access any data provider. The same plan works in HTML and native Dash tables.

```python
from runbook.core.table import TableStylePlan, render_table_html
from runbook.core.table.templates import cot_cme_summary_table

payload = cot_cme_summary_table(
    cot_summary_frame,
    header="Speculators Net Position (Managed money)",
    group_column="Group",  # caller-supplied instrument groups, hidden in output
    plot_links={"Brent Fut": "cot-brent", "Brent Fut+Opt": "cot-brent"},
)["Speculators Net Position (Managed money)"]

plan = TableStylePlan.model_validate(payload["style"])
html = render_table_html(payload["data"], plan)
# Or persist the very same data and plan inside a report:
table_ref = ctx.artifact.table(payload["data"], name="cot", style=plan)
```

Omit `group_column` or `plot_links` when unused. Plot link values must name
artifacts/pages that the report publishes. The template keeps values numeric;
it returns data, style and an empty `plots` list, without writing files or
creating companion figures. `position_label` optionally changes the displayed
net-position heading for dealers or investment funds. Optional
`Net Position (NC)` appears beside the instrument label.

The model rules preserve the COT conventions:

- Instrument labels and net/OI use hidden percentile-rank thresholds.
- Weekly and four-week moves use their supplied score columns and thresholds.
- Long/short percentiles and the combined net signal have separate rules.
- Percentages, integer positions, two-decimal prices/scores, negative red text,
  bold change columns and column-group borders use ordinary table models.
- A separator follows each contiguous `group_column` group; hidden signal and
  link fields never appear as display columns.

The template selects measures by column name, so adding noncommercial positions
or reordering the input does not shift highlighting onto the wrong measure. You can customize
the returned plan with the ordinary models before rendering:

```python
from runbook.core.table import TableAction, TableRule, TableTarget

plan.rules.append(
    TableRule(
        id="total_row",
        target=TableTarget(scope="rows", positions=[0]),
        action=TableAction(font_weight="bold", border_top="2px solid black"),
    )
)
```

Run the synthetic example without a provider connection:

```bash
pixi run python scripts/preview_cot_table.py --output-dir /tmp/runbook-cot-preview
```

This writes `index.html` and the reusable `style.json` from
`data/fixtures/cot/summary.csv`. The fixture contains no production data.

For new calculations, `runbook.core.cot` supplies `prepare_cot_data`,
`cot_summary`, `position_change` and `position_divergence`. Inputs use
`Long`, `Short`, optional `OI`, `PX_LAST`, `VWAP`, `Internal` and paired
`NC Long`/`NC Short` columns. Providers and participant aggregation remain with
the caller. `as_of` pins the data cutoff; the default uses the latest supplied
observation, never today's date. Position scaling and contract values are
explicit arguments.

To calculate directly from normalized observations, choose the ECM family:

```python
from runbook.core.table.templates import (
    cot_cme_timeseries_table,
    cot_ice_mifid_timeseries_table,
)

cme = cot_cme_timeseries_table(
    {"Brent Fut": brent_positions},
    summary_options={"contract_value": 1000},
)
mifid = cot_ice_mifid_timeseries_table(
    {"TTF Fut+Opt": ttf_positions},
    summary_options={"contract_value": 1000},
)
```

These presets use `cot_summary` with 52- or 208-observation position-score
windows. Both retain 52-observation price-score/rank windows and 260-observation
percentile history. `summary_options` overrides these defaults;
`asset_options` takes precedence per asset. The standard preset displays
`Net Position (MM)` and `Weekly Delta Change in $m`; MiFID uses `Net Position`
and `Weekly Delta Change in $/EUR m`. These are the corresponding ECM summary
column names; currency conversion remains the caller's responsibility.

Both time-series presets follow the report pipeline: calculate one analysis
row per supplied instrument/contract type, concatenate in mapping order, then
pass the result through the matching `*_summary_table`. The calculations live
in `runbook.core.cot`, independent of table styling. You can call them directly:

```python
from runbook.core.cot import analysis, analysis_mifid
from runbook.core.table.templates import cot_cme_summary_table

observations = {
    "Brent Fut": brent_futures_df,
    "Brent Fut+Opt": brent_combined_df,
    "WTI Fut": wti_futures_df,
    "WTI Fut+Opt": wti_combined_df,
}
groups = {name: name.split()[0] for name in observations}
summary = analysis(
    observations,
    summary_options={"contract_value": 1000},
    asset_groups=groups,
)
tables = cot_cme_summary_table(summary, group_column="Group")
# analysis_mifid(observations, ...) produces the MiFID summary DataFrame.
```

This two-step path and `cot_cme_timeseries_table(observations, ...)`
produce the same table when given the same calculation and style options.
`runbook.core.cot.position_change` and `position_divergence` also work on
summary DataFrames. The existing lower-level `timeseries.cot` functions remain
available. Each input frame needs `Long`/`Short`; supply `OI`, `PX_LAST`, `VWAP`,
`Internal` and paired `NC Long`/`NC Short` for the corresponding report measures.
`Internal` is the model estimate's placeholder name in input frames and plots.
Its weekly change is `Internal Change` in calculated summaries. Existing ECM
summaries containing `CTA Change` are displayed as `Internal Change` too.
Override `internal_change_label` on a table or `internal_label` on a COT plot
when a final display name is available; the input column remains `Internal`.

The first row's
observation date supplies the common `dd-Mon to dd-Mon` week heading, matching
`cot_cme.update_oil`; each row retains its own hidden `_last_update`. Override
`label_column` for a different heading. Supply separate time series for
`"Brent Fut"`, `"Brent Fut+Opt"`, `"WTI Fut"`, `"WTI Fut+Opt"` to reproduce
those four report rows. Rows are not inferred or duplicated from a single series.
`asset_groups={"Brent Fut": "Brent", "Brent Fut+Opt": "Brent", ...}` adds
the same group separators as a summary's `Group` column. Supply one group
per asset; `group_column` overrides the metadata-column name. `plot_links`
works identically on both paths. The gallery uses the same four instruments
per pair and verifies equal data, styles and rendered tables.

The standard preset retains a supplied NC pair separately. For MiFID's
additional venue positions (`long1`/`short1` in ECM), combine them into `Long`
and `Short` before calling; `NC Long`/`NC Short` always represent a separate
noncommercial series. Contract normalization is explicit, e.g.
`asset_options={"NG ICE": {"position_scale": 0.25}}`.

The old public names remain compatibility aliases:
`cot_table` → `cot_summary_table`, `cot_observations_table` →
`cot_timeseries_table`, and `cot_position_changes_table` →
`cot_position_change_table`. Their original generic defaults are retained.
The named calculation presets use Runbook's normalized inputs and the
calculation corrections below; they do not fetch data or recreate ECM's
ticker-specific acquisition logic.

`cot_summary` uses four observation intervals for four-week changes and the
previous price for weekly returns. Position scores retain ECM's uncentered
change/standard-deviation convention; price scores are centered. The default
position dispersion window is 52 observations; pass `change_window=208` for
the MiFID convention. Percentile history excludes the latest value. Insufficient
history or zero denominators remain missing instead of becoming infinite or
zero. Alert subsets have no instrument or row-number exclusions; apply those
report-specific selections before building the table.
