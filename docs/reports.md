# Author and run reports

For report authors

The normal authoring path is composable Python:

```text
dataset -> calculation -> artifact -> Report / Section / Grid -> PDL -> HTML or Dash
```

A report module declares aliases, registers calculations, and exposes one
`@report.page` function. The SDK runs the same module for preview and service
execution.

For exploratory client loads before authoring a report, see [Research with the
SDK in Jupyter](sdk-and-notebooks.md).

## A complete report pattern

```python
import pandas as pd

from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.layout import Report


ALIASES = required_aliases(prices="prices")


@report.calc("returns")
def returns(ctx) -> pd.DataFrame:
    frame = ctx.dataset(ALIASES.prices).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").set_index("timestamp")
    return frame["close"].astype(float).pct_change(fill_method=None).to_frame("returns")


@report.page
def page(ctx):
    frame = ctx.calc("returns")
    figure = plot_line(frame, title="Returns")
    plot_ref = ctx.artifact.plot(figure, name="returns")
    table_ref = ctx.artifact.table(frame.reset_index(), name="returns-table")

    layout = Report("Returns")
    with layout.section("Summary") as section:
        section.text(f"Rows: {len(frame)}")
        with section.grid(columns=2) as grid:
            grid.plot(plot_ref, title="Returns")
            grid.table(table_ref, title="Data")
    return layout
```

The important boundary is that `ctx.dataset` reads the run's pinned snapshot;
it does not call an API or open a file chosen by the report. `ctx.calc` runs a
named calculation once, and `ctx.artifact` stores a figure/table and returns a
reference. The layout only decides where those references appear.

## Aliases, parameters, and calculations

Aliases are the report's local names. `required_aliases(prices="prices")`
declares that the profile must bind `prices`; the profile maps it to a stable
dataset ID. `ctx.get_params(Model)` validates optional profile parameters with
a Pydantic model or dataclass. A calculation can call another calculation, but
must return a deterministic value such as a DataFrame, Series, JSON value, or
`None`.

```python
from dataclasses import dataclass


@dataclass
class Params:
    window: int = 20


@report.calc("volatility")
def volatility(ctx):
    params = ctx.get_params(Params)
    return ctx.calc("returns").rolling(params.window).std()
```

Calculations are cached using report identity, snapshot, code version, and
context hash. Do not mutate `ctx.config`, snapshot inputs, or cached outputs.

## Profiles and preview

A profile binds aliases to dataset IDs and supplies optional parameters:

```json
{
  "returns_demo": {
    "report_id": "returns_report",
    "title": "Returns demo",
    "enabled": true,
    "datasets": {"prices": "demo_daily_prices"},
    "params": {"window": 20}
  }
}
```

Preview one profile after its dataset pointer exists:

```bash
runbook-preview returns_demo --output preview/returns.html
```

Preview resolves and pins the latest pointers but does not advance them. The
service pins the same kind of immutable snapshot before dispatching a report
run. See [Data and snapshots](data.md) and [Operations](operations.md).

## Layout links

Use [Composable report layouts](composable-report-layouts.md) for grids,
spans, naming, and placement. Use [Plotting helpers](plotting-helpers.md) and
[Table templates](table-templates.md) when a common chart or summary table is
already available. See [Interactive reports](pdl-interactive.md) for controls
and [Dash renderer extensions](dash-renderer-extensions.md) for trusted host
customisation.

## Reports cookbook

These recipes show how the public helpers compose in a report. The focused
helper references explain each function separately; this section shows the
data-to-layout boundary in a realistic report.

### Complex plotting: range volatility

The checked-in [`reports/vol_report.py`](https://github.com/redcombojnr/runbook-platform/blob/main/reports/vol_report.py)
is the canonical plotting example. It reads the `prices` alias, sorts an
immutable timestamp column, calculates returns and rolling annualized
volatility, then stores two figures and styled tables before composing the
page:

```python
import pandas as pd

from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.layout import Report
from runbook.sdk.table_style import (
    action,
    condition,
    format_percent,
    rhs_literal,
    rule,
    table_style,
    target_columns,
)


ALIASES = required_aliases(prices="prices")


@report.calc("returns")
def returns(ctx):
    frame = ctx.dataset(ALIASES.prices).copy()
    params = ctx.config.get("params", {})
    price_col = str(params.get("price_col", "price"))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp", kind="mergesort").set_index("timestamp")
    return frame[price_col].astype(float).pct_change(fill_method=None).rename("returns").to_frame()


@report.calc("vol")
def volatility(ctx):
    returns = ctx.calc("returns")["returns"]
    window = int(ctx.config.get("params", {}).get("vol_window", 20))
    value = returns.rolling(window=window).std(ddof=0).mul(260.0**0.5)
    return value.rename("vol").to_frame()


@report.page
def page(ctx):
    returns = ctx.calc("returns")
    vol = ctx.calc("vol")
    options = ctx.config.get("layout", {})
    width = int(options.get("plot_width", 1000))
    height = int(options.get("plot_height", 450))
    returns_plot = plot_line(
        data=returns,
        title="Returns",
        width=width,
        height=height,
        show_legend=False,
        use_rangebreaks=True,
    )
    vol_plot = plot_line(
        data=vol,
        title="Volatility",
        width=width,
        height=height,
        show_legend=False,
        use_rangebreaks=True,
        series_styles={"vol": {"line": {"color": "#2A6F9E"}}},
    )

    def display(frame):
        table = frame.reset_index()
        table["timestamp"] = table["timestamp"].astype(str)
        return table

    returns_style = table_style(
        key="returns_style_v1",
        formats=[format_percent("returns", digits=2)],
        rules=[
            rule(
                "neg_returns_red",
                target_columns(["returns"]),
                condition("lt", rhs=rhs_literal(0)),
                action(text_color="#B00020", font_weight="600"),
            )
        ],
        max_rows=100,
        na_rep="-",
    )
    vol_style = table_style(
        key="vol_style_v1",
        formats=[format_percent("vol", digits=2)],
        rules=[
            rule(
                "high_vol_yellow",
                target_columns(["vol"]),
                condition("gt", rhs=rhs_literal(0.3)),
                action(background_color="#FFF3CD"),
            )
        ],
        max_rows=100,
        na_rep="-",
    )
    returns_table = ctx.artifact.table(display(returns), name="returns", style=returns_style)
    vol_table = ctx.artifact.table(display(vol), name="vol", style=vol_style)
    returns_ref = ctx.artifact.plot(returns_plot, name="returns-plot")
    vol_ref = ctx.artifact.plot(vol_plot, name="vol-plot")

    layout = Report("Range volatility")
    with layout.section("Summary") as section:
        with section.grid(columns=2) as grid:
            grid.plot(returns_ref, title="Returns")
            grid.table(returns_table, title="Returns data")
            grid.plot(vol_ref, title="Volatility")
            grid.table(vol_table, title="Volatility data")
    return layout
```

The profile supplies `price_col="close"` for the checked-in demo dataset. The
execution order is snapshot → named calculations → Plotly/table values →
immutable artifact references → `Report`/`Section`/`Grid`; the report never
acquires data itself. For seasonal, forecast, or multi-trace panels, use
`plot_seasonal`, `plot_bar_forecast`, or `plot_mixed` with
`GraphlyTraceSpec` as documented in [Plotting helpers](plotting-helpers.md).

### Complex tables: monthly commodities

The monthly template is useful when a curated, date-indexed calculation has
one column per commodity. The following uses the same 260-day Brent/WTI shape
covered by `tests/core/table/test_predefined_monthly.py`; the dataset alias and
profile binding are illustrative, while every helper call is public:

```python
import pandas as pd

from runbook.core.table import table_with_linked_plots_monthly
from runbook.core.timeseries.analysis import AggregationModes, MovingAvgModes
from runbook.sdk import report, required_aliases
from runbook.sdk.layout import Report


ALIASES = required_aliases(commodities="commodities")


@report.calc("commodity_prices")
def commodity_prices(ctx):
    frame = ctx.dataset(ALIASES.commodities).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame.sort_values("timestamp", kind="mergesort").set_index("timestamp")[["Brent", "WTI"]]


@report.page
def page(ctx):
    monthly = table_with_linked_plots_monthly(
        raw_df=ctx.calc("commodity_prices"),
        header="Commodity",
        moving_averge_window=20,
        moving_average_type=MovingAvgModes.SIMPLE,
        aggregation_type=AggregationModes.DIFF,
        aggregation_columns={"Brent": AggregationModes.MA, "WTI": AggregationModes.SUM},
        highlighting_rules={"window": 5},
        benchmark_quater=None,
        na_rep="-",
    )["Commodity"]
    table_ref = ctx.artifact.table(
        monthly["data"],
        name="commodity-monthly",
        style=monthly["style"],
    )
    plot_refs = [
        ctx.artifact.plot(figure, name=f"commodity-seasonal-{index}") for index, figure in enumerate(monthly["plots"])
    ]

    layout = Report("Monthly commodities")
    with layout.section("Summary") as section:
        with section.grid(columns=1) as table_grid:
            table_grid.table(table_ref, title="Monthly commodity summary")
        with section.grid(columns=2) as plot_grid:
            for plot_ref in plot_refs:
                plot_grid.plot(plot_ref)
    return layout
```

The result is keyed by the `header` (`"Commodity"`). Its `data` is the
display DataFrame, `style` is a serializable style plan, and `plots` contains
one Plotly figure per input column. `ctx.artifact.table` and
`ctx.artifact.plot` make those values immutable report artifacts; the layout
only positions their references. The public spelling `moving_averge_window`
is intentionally preserved, as is `benchmark_quater` when a quarterly
benchmark is needed. See [Table templates](table-templates.md) for the full
parameter list and style/template/layout distinction.

## Lower-level PDL builders

Most reports should use `Report`, `Section`, and `Grid`. Runbook also exposes
lower-level PDL builders when the composable API cannot express a particular
layout. This path remains supported; it is an advanced escape hatch, not the
onboarding path and not deprecated:

```python
from runbook.sdk.ui import flex_grid, manifest, plot, text


return manifest(
    ctx,
    page=flex_grid(
        rows=2,
        columns=1,
        blocks=[
            text(name="summary", text="Summary", row=1, col=1),
            plot(name="returns", ref=plot_ref, row=2, col=1),
        ],
    ),
)
```

Use explicit names for PDL blocks used by interactions. A lower-level builder
still produces the same renderer-neutral manifest and must preserve the same
snapshot/artifact boundary.

## Report execution rules

Report code is evaluated against immutable input data. A report cannot publish
dataset pointers, acquire sources, or put credentials in PDL. A successful run
stores stage manifests, HTML, artifacts, and calculation-cache metadata. A
failed run leaves the source and production dataset state unchanged.

## Golden report spec

The canonical checked-in report is
[`reports/vol_report.py`](https://github.com/redcombojnr/runbook-platform/blob/main/reports/vol_report.py).
Its contract is the `volatility_demo` profile over the `demo_daily_prices`
source:

| Requirement | Canonical value |
| --- | --- |
| Source | `demo_daily_prices` (`local_file`, `data/fixtures/daily_prices.csv`) |
| Profile | `volatility_demo` |
| Report module | `reports/vol_report.py` (`report_id: vol_report`) |
| Required alias | `prices` |
| Parameters | `price_col: close`, `vol_window: 20` |

The operational invariant is: a successful source run publishes the source
pointer; the report run pins that pointer into an immutable snapshot; named
calculations produce returns and volatility; plots and tables become immutable
artifacts; and the renderer writes the baseline static HTML and manifests.
Preview follows the same snapshot boundary but never advances the production
pointer. Run the exact source-publication sequence in
[Getting started](getting-started.md#publish-the-demo-dataset-first) before
previewing or running a profile; configuration import alone does not create a
pointer.

The run identity includes the report, snapshot, code version, and context hash,
so a changed report or execution context cannot silently reuse an unrelated
calculation result. Dash interactivity is an optional enhancement over the
same report definition, not a requirement for the HTML baseline. If the
composable API cannot express a layout, use the supported advanced [PDL
builders](#lower-level-pdl-builders) escape hatch after this spec.
