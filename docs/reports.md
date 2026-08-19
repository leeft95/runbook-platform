# Author and run reports

Reports are ordinary Python modules. They declare dataset aliases, register
named calculations, and return a PDL page manifest. The SDK runs the same
report code for preview and service execution.

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
