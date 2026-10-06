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
| compare seasonal columns beside ordinary history | `plot_seasonal_grid` | Named seasonal DataFrames and optional history | Plotly `Figure` |
| build a Commitment of Traders panel | `plot_cot` | DataFrame with a `DatetimeIndex`, panel columns, and titles | Plotly `Figure` |
| show COT price, volume and OI | `plot_cot_market` | Named OHLC DataFrames with optional volume/OI/holdings | Plotly `Figure` |
| fit price/position changes | `plot_regression` / `plot_price_vs_position` | Paired changes / dated position and price levels | Plotly `Figure` |
| combine explicit trace specifications | `plot_mixed` | `GraphlyTraceSpec` list and optional shared DataFrame | Plotly `Figure` |

The public functions are imported from their implementation modules:

```python
from runbook.sdk import plot_line
from runbook.core.plotting.bar import plot_bar, plot_bar_forecast
from runbook.core.plotting.mixed import plot_mixed
from runbook.core.plotting.seasonal import plot_cot, plot_seasonal, plot_seasonal_grid
from runbook.core.plotting.cot import plot_cot_market
from runbook.core.plotting.regression import plot_regression, plot_price_vs_position
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

Line, scatter, seasonal, COT, and mixed line/bar charts let Plotly choose
datetime tick spacing and formatting from the date range and available axis
width. Narrow plots can show fewer labels, and zooming recalculates the spacing.
There is no fixed daily-tick override or point-count cutoff. Overlaid traces
and shared x-axes use their combined date range; independent subplots adapt
separately. Pass `dtick` and/or `tickformat`
in any helper to override these defaults. For example, `dtick="M1", tickformat="%b"`
requests monthly ticks with month-name labels.
Bar-only datetime axes instead label each distinct bar timestamp, including
forecast bars. Labels use month/year for inferred monthly or quarterly data,
years for yearly data, and dates for daily or weekly data. Missing bars do not
add ticks. Shared bar-only axes combine their dates; mixed line/bar axes retain
automatic ticks across the full timeline. Bars and points at the same timestamp
share the same position on the datetime axis. An explicit `dtick` overrides the
per-bar ticks, and `tickformat` overrides their formatting.
To include weekends and holidays on calendar-day charts, use
`use_rangebreaks=False`.

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

For ECM's selected-single-bar highlighting, pass `highlight_only=True` to
`plot_bar_forecast`. Only the exact `forecast_from` index value receives the
forecast color/pattern; observations after it keep the history style. The
selected value must exist in the index.

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

For a July–June contract cycle, overlay each cycle using its starting year as
the legend label (`2025` means July 2025 through June 2026):

```python
seasonality = plot_seasonal(
    gas_curve[["price"]],
    frequency="M",
    start_month=7,
    end_month=6,
    over_year=True,
    dash_from=pd.Timestamp("2026-03-01"),
    show_legend=True,
)
```

Monthly, weekly (`frequency="W"`), and business-day (`frequency="B"`) windows
include their final month-end date, including June 30 in this example. A cutoff
that starts the next cycle remains exclusive, so adjacent years do not overlap.
Other explicit cutoffs, such as July 1 or July 15, also remain exclusive.
`dash_from` compares
the original observation dates: March–June 2026 is dashed on the `2025` curve,
and later cycles are entirely dashed. Missing months keep their calendar positions.

`B` uses Monday–Friday observations; `W` keeps the last observation in each calendar
week. Both support the same contract-cycle and forecast arguments as the monthly
example. Weekly alignment uses local calendar dates across daylight-saving changes.
Seasonal plots do not hide holidays by default because their x-axis dates are
artificial; `holiday_countries` can explicitly enable holiday breaks.

The flags separate **which lines appear** from **how they are calculated**:

| Argument | Effect |
|---|---|
| `vs_average=True` (default) | Adds current-year differences from the previous available year and the mean of up to five previous available years. |
| `ytd=True` | Adds the current-year cumulative line. |
| `ytd_cum_sum=True` | Independently adds cumulative comparisons against both historical benchmarks. |
| `five_year=False` | Hides both `Cur Yr vs 5y Avg` and `Cum Cur Yr vs 5y Avg`, keeping previous-year comparisons in both subplots. Defaults to `True`. |
| `ytd_diff=True` | Uses `.diff().cumsum()` instead of `.cumsum()` for every cumulative line. Does not enable any line or panel by itself. |
| `df_ytd=True` | Applies `.cumsum()` to every seasonal year before any panel calculations. Combining this with cumulative flags applies another accumulation. |

`ytd` and `ytd_cum_sum` default to `False`. Enabling both puts all three
cumulative lines in one panel. With `ytd=False, ytd_cum_sum=True`, only the two
cumulative comparisons appear. With both disabled, `ytd_diff=True` has no effect.
Use the exact argument `ytd_cum_sum`; `ytd_cum` is not a supported alias.
To show only previous-year comparisons in both subplots, use
`plot_seasonal(df, ytd_cum_sum=True, five_year=False)`.

For cumulative comparisons, each year is accumulated separately, then the
historical cumulative series are averaged or subtracted. Missing values retain
pandas' default behavior; accumulating the differences between years can give
different results when observations are missing. With complete data,
`.diff().cumsum()` measures change from the first value, leaving the first point
missing; it does not calculate percentage returns.

Panels appear in order: seasonal years, comparisons, cumulative lines, all on
their primary y-axes. Disabling `vs_average` moves the cumulative panel directly
under the seasonal plot. Comparisons use the years remaining after
`exclude_years`; with no history, comparison lines are omitted, while `ytd=True`
can still show the current-year cumulative line.

```python
# Seasonal plot plus cumulative changes relative to both historical benchmarks.
seasonality = plot_seasonal(
    prices[["brent"]],
    vs_average=False,
    ytd=False,
    ytd_cum_sum=True,
    ytd_diff=True,
)
```

`plot_seasonal` applies `start` before transforming the data, accepts an
explicit `current_year`, and honors `x_axis_title`, `y_axis_title`,
`y1_axis_title` (comparisons), and `y2_axis_title` (cumulative). The corresponding
`y_axis_reversed`, `y1_axis_reversed`, and `y2_axis_reversed` flags follow the
panel meaning even when the middle panel is omitted. Unrecognized keyword
arguments raise an error rather than silently doing nothing.

For multiple seasonal columns or a seasonal/history composite:

```python
comparison = plot_seasonal_grid(
    {"Brent": prices[["brent"]], "WTI": prices[["wti"]]},
    history=prices[["brent", "wti"]],
    title="Seasonality and price history",
    ytd_cum_sum=True,
    exclude_years=[2020],
)
```

Each named frame contributes its selected series. Seasonal options are
forwarded to `plot_seasonal`; matching traces share legend controls. The
optional history column spans the figure height and keeps actual dates on
its own axis. `history_first=True` places it on the left.

`plot_cot` defaults to two rows and three columns. Supply any non-empty list
of panel specifications and one `plot_titles` entry per specification. Its
input must contain the named main, price, and open-interest columns:

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

The OI band uses the previous five available years. Pass `history_years=None`
for all historical years, or another positive lookback. Short-position values
retain their observation dates; they are not reversed along the time axis.
For a single seasonal position/price panel, use
`columns=[["Net", "PX_LAST"]], plot_titles=["Net"], rows=1`. Two-row panels
require the OI field, with an optional fourth internal/CTA field.

### COT price and regression figures

`plot_cot_market({"Brent": brent, "WTI": wti}, cot_start="2025-06-24")`
combines candlesticks with optional volume bars and OI or holdings lines.
It uses `PX_OPEN`, `PX_HIGH`, `PX_LOW`, `PX_LAST`, `VOLUME`,
`FUT_AGGTE_OPEN_INT`, and `HOLDINGS` by default; column parameters allow other
names. Price fields are required, and missing/all-zero optional fields are
omitted. If both OI and holdings are supplied, holdings get a separate third
row so their units remain independent. `cot_start` shows 76 days of prior
history by default and shades the following seven days; `lookback_days` and
`highlight=False` control those choices. These helpers never fetch market data.

```python
regression = plot_regression(changes, x="Net position change", y="Price change", title="Price vs positioning")
beta = regression.layout.meta["regression"]["beta"]

# Or derive changes directly from dated Net and PX_LAST levels.
weekly = plot_price_vs_position(position_data, periods=1, highlight_length=4)
four_week = plot_price_vs_position(position_data, periods=4, as_of="2025-06-24")
```

`plot_regression` defaults to an OLS fit through the origin, matching the COT
reports. Set `constant=True` to fit an intercept. Without explicit names, its
first column is y and second is x. It drops missing/non-finite pairs together,
sorts dated observations, highlights the latest 8/3/1 observations, and draws
the fit with ±2 residual-standard-deviation lines in sorted x order. The bands
describe residual dispersion, not confidence intervals. Numeric `alpha`,
`beta`, `r_squared`, `residual_std`, `observations`, and `constant` are stored
under `figure.layout.meta["regression"]` for report text.

`plot_price_vs_position` calculates position differences and percentage-point
price returns over `periods` paired observations; `is_spread=True` uses price
differences instead. Older points are grouped by year, the previous selected
observations are highlighted separately, and the latest point is distinct.
Neither helper fills missing observations. Insufficient pairs or constant x
values raise an explanatory error.

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
