# Plotting helpers

For report authors

For end-to-end combinations of these helpers, see the [Reports
cookbook](reports.md#reports-cookbook).

Runbook's plotting helpers return ordinary Plotly `Figure` objects. Build the
figure from a pandas DataFrame, store it with `ctx.artifact.plot`, and place
the returned reference in a `Report` layout:

```python
from runbook.sdk import plot_line
from runbook.sdk.layout import Report

figure = plot_line(frame[["price"]], title="Price")
plot_ref = ctx.artifact.plot(figure, name="price")
layout = Report("Prices")
with layout.section("Summary") as section:
    with section.grid(columns=1) as grid:
        grid.plot(plot_ref, title="Price")
```

## Which helper should I use?

| I want to... | Use | Input | Returns |
| --- | --- | --- | --- |
| show one or more time series | `plot_line` | DataFrame, or `dict[str, DataFrame]` for subplots | Plotly `Figure` |
| show categories or bars | `plot_bar` | DataFrame, Series, or named DataFrames | Plotly `Figure` |
| separate history and forecast bars | `plot_bar_forecast` | DataFrame, Series, or named DataFrames plus `forecast_from` | Plotly `Figure` |
| compare values by year/season | `plot_seasonal` | DataFrame with a `DatetimeIndex` | Plotly `Figure` |
| build a Commitment of Traders panel | `plot_cot` | DataFrame with a `DatetimeIndex`, panel columns, and titles | Plotly `Figure` |
| combine explicit trace specifications | `plot_mixed` | `GraphlyTraceSpec` list and optional shared DataFrame | Plotly `Figure` |

The public functions are imported from their implementation modules:

```python
from runbook.sdk import plot_line
from runbook.core.plotting.bar import plot_bar, plot_bar_forecast
from runbook.core.plotting.mixed import plot_mixed
from runbook.core.plotting.seasonal import plot_cot, plot_seasonal
```

## Line and bar charts

`plot_line` accepts a DataFrame (each column is a series) or a mapping of
subplot names to DataFrames. It accepts optional `rows` and `cols` for
subplots. `plot_bar` accepts a DataFrame, Series, or mapping and has the same
subplot options:

```python
line = plot_line(frame[["brent", "wti"]], title="Prices", show_legend=True)
bars = plot_bar(frame[["volume"]], title="Volume")

line_ref = ctx.artifact.plot(line, name="prices")
bars_ref = ctx.artifact.plot(bars, name="volume")
with layout.section("Market") as section:
    with section.grid(columns=2) as grid:
        grid.plot(line_ref)
        grid.plot(bars_ref)
```

Use `plot_bar_forecast` when one monotonically indexed single-series DataFrame
must be split at a date or other comparable `forecast_from` value:

```python
import pandas as pd

forecast = plot_bar_forecast(
    frame[["demand"]],
    forecast_from=pd.Timestamp("2026-07-01"),
    title="Demand and forecast",
)
forecast_ref = ctx.artifact.plot(forecast, name="demand-forecast")
with layout.section("Forecast") as section:
    with section.grid(columns=1) as grid:
        grid.plot(forecast_ref)
```

The result of every helper is a Plotly figure; no helper writes to Runbook
storage until `ctx.artifact.plot(...)` is called.

## Seasonal charts

`plot_seasonal` expects a DataFrame indexed by timestamps. It reshapes values
by year and can add comparisons, YTD panels, and an optional forecast cutoff:

```python
seasonality = plot_seasonal(
    prices[["brent"]],
    column="brent",
    title="Brent seasonality",
    vs_average=True,
)
seasonality_ref = ctx.artifact.plot(seasonality, name="brent-seasonality")
with section.grid(columns=1) as grid:
    grid.plot(seasonality_ref)
```

`plot_cot` creates a fixed two-row, three-panel COT figure. Its input must have
the named main, price, and open-interest columns required by each panel, and
`plot_titles` must contain exactly three titles:

```python
cot = plot_cot(
    cot_frame,
    columns=None,  # uses Net/Long/Short defaults
    title="COT",
    plot_titles=["Net", "Long", "Short"],
)
cot_ref = ctx.artifact.plot(cot, name="cot")
with section.grid(columns=1) as grid:
    grid.plot(cot_ref, title="Commitment of Traders")
```

## Mixed figures

`plot_mixed` is the lower-level plotting helper for explicit trace types and
subplot placement. Each `GraphlyTraceSpec` supplies a DataFrame, row, column,
and plot type:

```python
import pandas as pd
from runbook.core.plotting.graphly import GraphlyTraceSpec, PlotType
from runbook.core.plotting.mixed import plot_mixed

specs = [
    GraphlyTraceSpec(data=frame[["price"]], plot_type=PlotType.line, row=1, col=1),
    GraphlyTraceSpec(data=frame[["volume"]], plot_type=PlotType.bar, row=2, col=1),
]
mixed = plot_mixed(specs, n_rows=2, n_cols=1, title="Price and volume")
mixed_ref = ctx.artifact.plot(mixed, name="price-volume")
with section.grid(columns=1) as grid:
    grid.plot(mixed_ref)
```

Use `plot_mixed` when the line/bar/seasonal helpers do not describe the
figure. Otherwise prefer the smallest helper that matches the analysis.
