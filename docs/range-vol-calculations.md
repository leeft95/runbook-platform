# Range-Vol calculations

`runbook.core.timeseries.range_vol` contains the data-only calculations migrated
from `market_scan_helpers/processing_utils.py` and the AM Range-Vol report.
It requires pandas/NumPy inputs and has no Bloomberg, cache, plotting, email or
filesystem dependencies. Inputs are copied; dated calculations take an explicit
`as_of` so historical runs are repeatable.

This migrates calculations, not the complete AM/PM/gas report scripts. Data
loading, ticker eligibility, contract discovery, alert routing, report tables
and plot links stay with the caller.

## Gallery examples

Run the gallery for six calculated tables and four charts using reproducible
synthetic observations:

```sh
pixi run python scripts/preview_gallery.py --serve --port 8766
```

Open `http://127.0.0.1:8766/gallery/index.html#range-vol-metrics`. The examples
cover range/volume/FOM, Sharpe/KPI/trend, signals, divergence, fly switches and
weighted metrics. Charts show the migrated ECM EMAs and ATR, latest Fisher
reference levels, same-time cumulative volume and KPI comparisons. Each card
shows the calculation calls and uses the public table/plot builders. Every
table has an **HTML / native Dash** comparison link, including AG Grid.

These are calculation examples; they do not claim to reproduce the full source
report's presentation. Without `--serve`, the gallery exports to
`/tmp/runbook-gallery/index.html`.

## Inputs and first calculation

Price frames use a unique, non-missing `DatetimeIndex`, with these fields:

| Input | Fields |
| --- | --- |
| Daily price | `PX_LAST`; optional `PX_OPEN`, `PX_HIGH`, `PX_LOW`, `3MTH_IMPVOL_100.0%MNY_DF` |
| Weekly/monthly price | `PX_LAST`; optional `PX_HIGH`, `PX_LOW` |
| Intraday price | `close` for changes/KPI/VWAP delta; `volume` for volume calculations |
| Daily volume | `VOLUME` |
| Post-close price | `FUT_PX`, `PX_SETTLE` |

Frames are sorted chronologically. Price preparation keeps the recovered
report's fill rules and requires more than 30 daily observations. It returns
`None` if daily history is too short or `PX_LAST` is absent. Weekly/monthly
frames are optional; missing frames produce empty series. Supply period labels
that also occur in the daily index for Fisher calculations. The helper does not
resample prices or move missing period labels to other sessions.

```python
from runbook.core.timeseries import range_vol

prices = range_vol.prepare_price_data(daily, weekly, monthly)
if prices is None:
    raise ValueError("Need more than 30 daily observations and PX_LAST")

changes = range_vol.calculate_price_changes(prices["closep"], "FLAT", intraday)
ranges = range_vol.calculate_range_metrics(
    prices["highp"], prices["lowp"], prices["closep"], as_of="2026-10-13"
)
sharpe = range_vol.calculate_sharpe_ratios(
    changes["daily_price_chg"], changes["intraday_price_chg"],
    instr="CMD", chg_type="FLAT",
)
kpi = range_vol.calculate_kpi(
    prices["closep"], prices["imp_vol"], changes["daily_price_chg"], "FLAT"
)
momentum = range_vol.calculate_moving_average_signals(prices["closep"])

# Numeric values/flags can feed any Runbook table or report builder.
metrics = {**ranges, **sharpe, **kpi, **momentum}
```

`FLAT` means fractional price changes; `SPRD` means absolute differences.
Implied volatility is supplied in percentage points: `25` means 25% annual
volatility. Missing implied volatility falls back to the report's
30-observation realized-volatility estimate.

## Available helpers

| Calculation | Functions |
| --- | --- |
| Price inputs and changes | `prepare_price_data`, `calculate_price_changes`, `calculate_post_close` |
| EMA and range spikes | `calculate_exponential_moving_average`, `calculate_range_metrics` |
| Sharpe ratios and classification | `calculate_sharpe_ratios`, `calculate_sharpe_3d_cob`, `classify_sharpe_signal` |
| Price and stochastic flags | `calculate_three_day_trend`, `calculate_current_price_range`, `calculate_stochastic` |
| Fisher bands and signals | `calculate_fisher_indicators`, `determine_fisher_signals`, `get_simple_fisher_signals` |
| Momentum, KPI and combined signals | `calculate_moving_average_signals`, `calculate_kpi`, `calculate_trend_index`, `determine_combined_signals`, `calculate_signal_flag` |
| FOM event calculations | `parse_fom_date`, `calculate_fom_metrics`, `calculate_fom_vwap` |
| Volume and contract rolls | `calculate_cumulative_volume`, `adjust_volume_for_roll`, `calculate_volume_spikes` |
| AM report cross-instrument calculations | `calculate_divergence`, `calculate_fly_switches`, `calculate_weighted_risk_index` |

Fisher crossing signals return `(fish, fish1, fishlt, fishlt1, counter,
counter1)`; simple prior-period signals return `(fish2, fishlt2, counter2)`.
The `1` suffix denotes the preceding daily observation. Fisher here means the
report's typical-price bands, not the oscillator also called Fisher transform.

The numerical EMA is the recovered ECM implementation: a seeded recursion,
followed by a normalized finite exponential kernel. It deliberately differs
from `analysis.calculate_moving_average`; substituting the latter changes
crossing dates and range spikes. Short inputs retain leading missing values.

## Date and window conventions

- `chg_5d` compares the latest value with the fifth-from-last observation
  (four intervals), preserving the source label and calculation.
- Sharpe `22d` uses the preceding 22 daily returns, excluding the latest row,
  with sample standard deviation and a `sqrt(22)` multiplier.
- Intraday Sharpe uses windows bounded by the supplied daily dates, with
  `mean / std * sqrt(n)` after dropping the window's first return. It needs
  more than ten observations before that drop. FI/SPRD sign inversion applies
  to COB values, not the live value. `upload` indicates a finite live metric;
  the helper performs no upload.
- ATR is the five-observation ECM EMA of true range. Range spikes divide by
  the preceding ATR. The prior-day range and volume metrics retain the source's
  separate rules for current, stale and future-dated final daily rows.
- Other moving windows use observations, not calendar days. These conventions
  are independent of the calendar-day roll-up table templates.
- Date-only boundaries use the input index's timezone. Prepare session labels
  and market close conventions upstream. Helpers do not trim all inputs at
  `as_of`; it controls each report formula's date rules. For a historical run,
  supply data available at that point.

## Provider-dependent calculations now take data

Pass the selected FOM date directly, rather than a comments table and ticker:

```python
flag, zscore, date_label = range_vol.calculate_fom_metrics(
    "2026-10-01 - 2026-10-05", changes["daily_price_chg"],
    prices["highp"], prices["lowp"], prices["closep"], as_of="2026-10-13",
)
vwap, delta = range_vol.calculate_fom_vwap(provider_vwap, intraday)
```

FOM intervals sum changes and use interval high/low extrema. Single dates use
the first observation on/after the date. The standard deviation comes from the
preceding 20 returns. `provider_vwap` is the already-fetched value of the
source's `EQY_WEIGHTED_AVG_PX`; the helper returns it and the latest-close delta
without approximating VWAP from bar closes.

For volume-enabled instruments, calculate same-time cumulative volumes and
optionally supply the prior contract and its roll boundary:

```python
previous_volume = range_vol.calculate_cumulative_volume(previous_contract_intraday)
volume = range_vol.calculate_volume_spikes(
    intraday, daily, as_of="2026-10-13 12:00",
    previous_volume=previous_volume, roll_date="2026-10-09",
)
```

Omit both `previous_volume` and `roll_date` if there is no roll adjustment.
Each sample uses a ten-minute grid and that input's final clock time. Align both
contracts to the same session cutoff upstream. Missing bars contribute zero;
weekends and zero-volume days are excluded. The previous contract replaces
observations before a recent roll boundary. Missing replacement dates stay
missing. Live ratios compare the latest same-time sample against the preceding
5/20-session means, excluding the current session from the denominator.

For the GXA-specific intraday KPI, pass `generic_name="GXA Index"`, intraday
prices and `as_of`. This preserves the recovered code's midnight cutoff, even
though an original report comment mentioned a different close time.

## AM report extras

`calculate_divergence(spread, flat, as_of=...)` accepts aligned price series and
returns the last settled moves plus 3/8-observation divergence ratios. Use
`scale=0.42` for the report's XB/HO versus CO conversion. Its JKM/TTF case uses
`invert_spread=True, min_move_zscore=1.5`, after upstream alignment. Screen for
negative divergence ratios in the caller, as the report does.

`calculate_fly_switches(spreads)` takes ordered adjacent-spread columns and
returns flies whose latest two values changed sign, including moves to/from
zero. `calculate_weighted_risk_index(metrics, weights)` takes instrument rows
and numeric metric columns. Set `normalize=True` for the report's component
groups; the overall index uses raw weights. Entirely missing metrics remain
missing instead of becoming zero.

## Migration checks and source limits

The source checkout contains code recovered from screenshots. Its transcription
notes identify inferred portions of OHLC filling, FOM intervals, some Fisher
conditions and volume roll handling. The migration follows that recovered code;
it is not evidence of parity with an independently verified deployed report.

Tests pin source-derived EMA/KPI outputs and signal dates, and exercise window
boundaries, formatting-independent numeric outputs, missing data, timezone
boundaries and volume rolls. A migration-time comparison also matched the
recovered EMA, ATR, stochastic and momentum functions across 220 input prefixes.
The previous-period simple Fisher counter rule intentionally retains the
source's comparison against current `fml`.

Public signatures have changed where the source mixed calculation and I/O:
redundant frames, ticker tuples, output directories and plot keys are removed.
Malformed inputs raise rather than being silently swallowed. Missing samples
produce missing metrics or no signal. These helpers are therefore a data-only
API, not drop-in replacements for the old report orchestrator.
