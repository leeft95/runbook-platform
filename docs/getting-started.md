# Getting started

For report authors

Runbook reports are ordinary Python. A report declares the datasets it expects,
defines named calculations, creates Plotly/table artifacts, and returns a
`Report` layout. Start with the composable API; raw PDL is an advanced escape
hatch covered in [reports](reports.md).

## Your first report

This small report reads a pinned dataset, calculates returns, stores a Plotly
figure as an artifact, and places it in a named section and grid:

Save it as `reports/returns_report.py`. The filename matches the
`report_id: "returns_report"` used by the profile below.

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

    layout = Report("Returns")
    with layout.section("Summary") as section:
        section.text(f"Rows: {len(frame)}")
        with section.grid(columns=1) as grid:
            grid.plot(plot_ref, title="Returns")
    return layout
```

The flow is:

1. `required_aliases` says the report needs a dataset alias called `prices`.
2. `ctx.dataset(...)` reads that alias from the run's immutable snapshot.
3. `@report.calc` names a reusable calculation; `ctx.calc` evaluates it once.
4. `plot_line` returns a normal Plotly figure.
5. `ctx.artifact.plot` stores that figure and returns its report reference.
6. `Report`, `Section`, and `Grid` place the artifact without coordinates.

Tables use the same path: create a pandas frame, call
`ctx.artifact.table(frame, name="...", style=...)`, and pass the returned
table reference to `grid.table(...)`. See [plotting helpers](plotting-helpers.md)
and [table templates](table-templates.md).

## Set up a local profile

A profile connects the report alias to a stable curated dataset ID:

Add this map entry to
`data/contract/report_profiles.json` (or in another profile file passed to
`config import`):

```json
{
  "returns_demo": {
    "report_id": "returns_report",
    "title": "Returns demo",
    "enabled": true,
    "datasets": {"prices": "demo_daily_prices"}
  }
}
```

The checked-in examples use `data/contract/report_profiles.json` and report
modules under `reports/`. A source run must publish the dataset pointer before
a report can read it. Profiles are validated at import and again when the
worker loads the report.

## Publish the demo dataset first

`config import` stores and validates configuration; it does not acquire data
or create a dataset pointer. From the repository root, use separate terminals
for the service, runner, and request:

```bash
# Terminal 1: initialize PostgreSQL and import source/profile configuration
runbook-services db upgrade
runbook-services config import \
  --source-config data/contract/source_configs.json \
  --profiles data/contract/report_profiles.json

# Terminal 2: serve the API and Operations UI
runbook-services serve

# Terminal 3: keep claiming queued work
runbook-services run --workers 1 --poll-interval 1
```

In a fourth terminal, submit the checked-in `demo_daily_prices` source. The
`local_file` adapter reads `data/fixtures/daily_prices.csv`, curates it as
`demo_daily_prices`, and the successful run advances that dataset's production
pointer:

```bash
curl -sS -X POST http://127.0.0.1:8050/api/v1/sources/demo_daily_prices/runs \
  -H 'content-type: application/json' \
  -d '{}'
```

Copy the returned `run_id`, then poll its status until it is
`"status":"success"` before previewing. A queued response alone is not
enough; a failed run does not create or advance the pointer:

```bash
curl -sS http://127.0.0.1:8050/api/v1/runs/RUN_ID
```

The request is an ordinary normal source run, not a historical run. The
Operations UI's Sources and Runs pages show the same lifecycle and logs.

## Preview the result

Once the source run reports `"status":"success"`, run the profile and copy
its static HTML to a local path:

```bash
runbook-preview returns_demo --output preview/report.html
```

The command resolves the latest pointers, pins a snapshot for that preview,
and does not advance production pointers. Open `preview/report.html` in a
browser. For a full service workflow, see [Operations](operations.md); for
installation and startup order, see [Deployment](deployment.md).

The repository's `reports/market_dashboard.py`, `reports/vol_report.py`, and
`reports/pnl_explorer.py` are useful next examples. `snapshot_report.py` shows
the lower-level PDL builder escape hatch.

## Environment

The repository uses Python 3.11 and Pixi:

```bash
pixi install
pixi run test
```

The default local blob store is `file:.runbook`. Set
`RUNBOOK_DATA_STORE_URI` or pass a `file:`/`s3://` URI when needed. PostgreSQL
is configured with `RUNBOOK_DATABASE_URL`. See [Data](data.md) for the
source-to-snapshot lifecycle and [CLI](cli.md) for all command flags.
