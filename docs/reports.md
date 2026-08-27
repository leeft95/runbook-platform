# Author and run reports

Reports are ordinary Python modules. They declare dataset aliases, register
named calculations, and return a `Report` layout. The SDK compiles that
layout to one canonical PDL manifest and runs the same report code for preview
and service execution. Raw PDL remains available when the high-level API
cannot express a requirement.

## Compose a page

Use `Report`, `Section`, and `Grid` from `runbook.sdk.layout`. Add blocks in
ordinary loops; do not calculate row or column coordinates:

```python
from runbook.sdk.layout import Report

page = Report("Weekly prices")
with page.section("Markets") as markets:
    with markets.grid(columns=2) as cards:
        for symbol in symbols:
            cards.table(ctx.artifact.table(make_table(symbol), name=symbol), title=symbol)
            cards.plot(ctx.artifact.plot(make_chart(symbol), name=f"{symbol}-plot"), title=symbol)
return page
```

`Report`/`Section` support `add`, `extend`, and `heading`; `Grid` supports
`add`, `extend`, `table`, `plot`, and `text`. The functional helpers
`report`, `section`, and `grid` accept the same plain lists, tuples, and
generators. Empty grids and sections are omitted, and names are deterministic.

## Declare aliases and calculations

Use the public SDK helpers:

```python
import pandas as pd
from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.ui import flex_grid, manifest, plot, text

ALIASES = required_aliases(prices="prices")


@report.calc("returns")
def returns(ctx) -> pd.DataFrame:
    frame = ctx.dataset(ALIASES.prices).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp", kind="mergesort").set_index("timestamp")
    return frame["price"].astype(float).pct_change(fill_method=None).to_frame("returns")


@report.page
def page(ctx):
    frame = ctx.calc("returns")
    plot_ref = ctx.artifact.plot(plot_line(frame, title="Returns"), name="returns")
    return manifest(
        ctx,
        page=flex_grid(
            rows=2,
            columns=1,
            blocks=[
                text(name="summary", text=f"Rows: {len(frame)}", row=1, col=1),
                plot(name="returns_plot", ref=plot_ref, row=2, col=1),
            ],
        ),
    )
```

The repository's `reports/vol_report.py` and `reports/snapshot_report.py`
show complete pages using tables, plots, layouts, and Pydantic parameters.
The example above is intentionally small; in a real page use `plot(...)` or
`table(...)` blocks in a `grid(...)`/`flex_grid(...)` page.

## Report context

`Ctx` is the report's read-only boundary:

- `ctx.dataset(alias)` reads one dataset from the pinned snapshot.
- `ctx.get_params(Model)` validates profile parameters with Pydantic or a
  dataclass.
- `ctx.calc(name)` evaluates a registered calculation once and reuses its
  immutable cache entry.
- `ctx.artifact.plot(...)` and `ctx.artifact.table(...)` register report
  artifacts under the run's immutable artifact prefix.

Do not mutate `ctx.config`, its context hash, or snapshot inputs. The SDK
checks for configuration mutation before publishing a report.

## Profiles

Profiles are JSON objects keyed by `profile_id`. A profile contains a
`report_id` and at least one dataset binding, optional `params` and
`layout`, and an `enabled` flag. Dataset map keys are the aliases used by the
report; values are stable curated dataset IDs.

```json
{
  "volatility_demo": {
    "report_id": "vol_report",
    "title": "Synthetic Volatility Demo",
    "enabled": true,
    "datasets": {"prices": "demo_daily_prices"},
    "params": {"price_col": "close", "vol_window": 20},
    "layout": {"plot_width": 700, "plot_height": 360}
  }
}
```

`load_profiles(...)` validates profiles. The service additionally verifies
that each report file exists and that its declared aliases exactly match the
profile bindings.

## Preview

`runbook-preview` executes one profile against the latest resolved snapshot.
Use `--code-version` when Git metadata is unavailable, or set
`RUNBOOK_CODE_VERSION`. Use `--output` to copy the generated HTML from blob
storage to a local file. Preview does not advance dataset pointers.

Service execution pins one immutable snapshot before dispatch. Its optional
producer provenance records each producer, successful source run, slot, and
profile aliases. Snapshot warnings are authoritative and are rendered above
the report grid in HTML and Dash; report code cannot suppress them. Automatic
snapshots have no warnings. Manual profile runs deliberately bypass the
multi-source advancement barrier and therefore retain a visible warning.

## Interactive PDL reports

The page function returns one canonical PDL manifest. The same manifest is the
input to static HTML and optional interactive rendering; do not maintain a
second Dash-only report definition.

Install the optional Dash dependencies when developing interactive reports:

```bash
pip install -e 'packages/runbook/runbook-sdk[dash]'
```

Semantic table metadata is optional and overrides deterministic Arrow schema
inference:

```python
from runbook.sdk import column, currency, percent
from runbook.sdk.ui import table

table(
    name="positions",
    ref=ctx.artifact.table(frame, name="positions"),
    row=2,
    col=1,
    col_span=12,
    columns=[
        column("book", role="dimension"),
        column("pnl", role="measure", aggregation="sum", format=currency("GBP")),
        column("return", role="measure", aggregation="avg", format=percent(2)),
    ],
)
```

Strings, dictionaries, booleans, numbers, dates, and timestamps receive
deterministic default roles. Explicit columns are validated against the
physical schema. HTML renders a static table; Dash translates the same
semantics to AG Grid. Sorting, filtering, resizing, reordering, visibility,
grouping, pivoting, and value aggregation stay client-side and require no
Python callback.

Report-level updates use plain Python handlers:

```python
@report.interaction("filter_dashboard")
def filter_dashboard(ctx, state):
    frame = ctx.calc("pnl")
    return {"summary": "...", "chart": figure, "positions": frame}
```

The `pdl-dash/0.1` extension declares controls and maps logical inputs and
outputs to a registered handler. Report code never imports Dash callback
types, component IDs, or callback context. The renderer validates unique
controls, known inputs/outputs, registered handlers, duplicate output
ownership, and the supported extension version before Dash starts.

`render_dash_page(...)` returns an embeddable `DashPage` with separate
`layout()` and `register_callbacks(app)` methods. The host owns the root Dash
application and routing. Each page receives a safe namespace, so two pages may
both use local names such as `summary` and `book` in one app. The interactive
preview composes this same page object into a temporary app; it is
development-only and binds to `127.0.0.1` by default.

## Optional live data

Managed data remains immutable and snapshot-backed through `ctx.dataset(...)`.
An injected live capability is separate:

```python
rows = ctx.live.sql("logical_name").query(
    "SELECT * FROM positions WHERE book = :book",
    {"book": state.get("book")},
)
```

Only logical source names belong in report code. Providers, credentials, and
network configuration stay in runtime composition. Without an injected
provider, `ctx.live.sql(...)` raises a clear capability-unavailable error.
The public SQLite demo captures only logical provider name, query time and
duration, query hash, and safe parameter metadata; it never serializes
results, credentials, or connection URLs.
