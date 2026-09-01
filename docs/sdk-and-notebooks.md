# Research with the SDK in Jupyter

For analysts comfortable with Python and pandas

Use a notebook for exploration and a report module for repeatable delivery.
`RunbookClient` resolves curated data and gives you ordinary pandas and Plotly
objects. A report's `Ctx` is different: Runbook creates it only inside
`execute_report`, where `ctx.dataset`, `ctx.calc`, and `ctx.artifact` enforce
the report snapshot boundary.

```text
current pointer -> RunbookClient load -> Snapshot -> pandas research
                                      -> saved Snapshot/research record -> report
```

The Snapshot records immutable manifest references. Saving that Snapshot with
your research record lets another analyst reload the same curated files even
after the current pointer advances.

## Prerequisites and environment

The notebook kernel needs the installed Runbook packages and access to the
same PostgreSQL pointer database and data store as the source pipeline. Set
the required settings explicitly before starting the kernel:

```bash
export RUNBOOK_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/runbook"
export RUNBOOK_DATA_STORE_URI="file:.runbook"
export RUNBOOK_REPORTS_ROOT="reports"
export RUNBOOK_CODE_VERSION="research-2026-08-28"
# Optional: keep preview outputs separate from the shared data store.
export RUNBOOK_WORKSPACE_STORE_URI="file:.runbook-workspace"
```

`RUNBOOK_DATABASE_URL` points to PostgreSQL's current-pointer registry.
`RUNBOOK_DATA_STORE_URI` points to immutable raw/curated data and manifests.
`RUNBOOK_WORKSPACE_STORE_URI` is optional; when set, report preview writes
report artifacts and HTML there instead of mixing them with the data store.
`RUNBOOK_REPORTS_ROOT` is the directory containing report modules and defaults
to `reports` when passed to `create_client`. `RUNBOOK_CODE_VERSION` is the
identity recorded in report artifacts; use a stable release, commit, or
research label rather than an arbitrary changing value.

This repository does not provide Jupyter, `ipykernel`, or a `pixi run jupyter`
task. Use your organisation's notebook environment and kernel, with the
Runbook packages installed into that environment. In this repository, `pixi
install` and an SDK import check are useful environment checks, but they do
not launch Jupyter:

```bash
pixi install
pixi run python -c "from runbook.sdk import RunbookClient; print(RunbookClient)"
```

## Prototype a report directly from DataFrames

For a quick report iteration, pass ordinary pandas frames keyed by the report
aliases. The checked-in volatility report can run without PostgreSQL,
filesystem setup, S3, MinIO, or any other object-storage service:

```python
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from runbook.sdk import load_profiles, prototype_report


profile = load_profiles(Path("data/contract/report_profiles.json"))["volatility_demo"]
prices = pd.read_csv("data/fixtures/daily_prices.csv")
result = prototype_report(
    profile=profile,
    frames={"prices": prices},
    observed_at=datetime.now(timezone.utc),
)
print(result.html_ref)
```

Prototype mode freezes each frame into immutable in-memory Runbook dataset
payloads and manifests before executing the real report. Report code remains
transparent to the source: `ctx.dataset(alias)` reads the same snapshot-bound
data it would read in production. The intended progression is to acquire and
clean data in a notebook first, then add a SourceAdapter/parser later if the
prototype should move into the production ingestion path; the report itself
can remain unchanged.

Notebook-defined decorated calculations and `page(ctx)` are also supported;
move the same `ALIASES` and functions into a report module unchanged when
ready for production publication. For a runnable authoring flow, see
`notebooks/prototype_report.ipynb`.

## Construct a client and load profiles

The client accepts explicit values, so notebook setup is visible and easy to
audit. `load_profiles` reads a JSON file; it is not a service profile listing,
and `RunbookClient` has no `list_profiles` or blob-listing API.

```python
import os
from pathlib import Path

from runbook.sdk import create_client, load_profiles


DATA_STORE_URI = os.environ["RUNBOOK_DATA_STORE_URI"]
DATABASE_URL = os.environ["RUNBOOK_DATABASE_URL"]
WORKSPACE_STORE_URI = os.environ.get("RUNBOOK_WORKSPACE_STORE_URI")
REPORTS_ROOT = Path(os.environ.get("RUNBOOK_REPORTS_ROOT", "reports"))
CODE_VERSION = os.environ["RUNBOOK_CODE_VERSION"]

client = create_client(
    store_uri=DATA_STORE_URI,
    database_url=DATABASE_URL,
    workspace_store_uri=WORKSPACE_STORE_URI,
    reports_root=REPORTS_ROOT,
)
profiles = load_profiles(Path("data/contract/report_profiles.json"))
profile = profiles["volatility_demo"]

pointers = client.pointer_registry.all()
dataset_id = profile.datasets["prices"]
if dataset_id not in pointers:
    raise RuntimeError(f"no current pointer exists for {dataset_id!r}")
print(pointers[dataset_id].manifest_ref)
```

`profile.datasets` maps the report's local alias (`prices`) to the stable
dataset ID (`demo_daily_prices`). `pointer_registry.all()` returns current
database pointers keyed by dataset ID; it does not list historical manifests.

## Load a current snapshot

`client.load_datasets` resolves the profile bindings, verifies the selected
manifests and Parquet hashes, and returns both frames and the `Snapshot` that
identifies them. Copy the frames before notebook transformations:

```python
import pandas as pd


frames, snapshot = client.load_datasets(profile.datasets)
prices = frames["prices"].copy()
assert isinstance(prices, pd.DataFrame)
print(snapshot.snapshot_id, snapshot.watermark, prices.shape)
```

The dictionary key is the report alias, not the dataset ID. A missing current
pointer is an ingestion/operations issue; the notebook does not create one.

For a point-in-time read, pass a timezone-aware `as_of` cutoff:

```python
from datetime import datetime, timezone


cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
historical_frames, historical_snapshot = client.load_datasets(
    profile.datasets,
    as_of=cutoff,
)
```

`as_of` selects the newest manifest whose publication time is at or before
the cutoff. It is not a row-level timestamp filter and does not change the
current pointer.

## Save and reload a reproducible input

Save the Snapshot JSON beside the notebook output or research record:

```python
from pathlib import Path


snapshot_path = Path("research/volatility_snapshot.json")
snapshot_path.parent.mkdir(parents=True, exist_ok=True)
snapshot_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
```

Reloading from the saved Snapshot uses the immutable data store directly. It
does not consult the current pointer again:

```python
from runbook.core import Snapshot
from runbook.data import load_manifest, load_snapshot_dataset, open_blob_store


data_store = open_blob_store(DATA_STORE_URI)
saved_snapshot = Snapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
manifest_ref = saved_snapshot.datasets["prices"]
manifest = load_manifest(
    data_store,
    manifest_ref,
    expected_dataset_id=profile.datasets["prices"],
)
prices_again = load_snapshot_dataset(data_store, saved_snapshot, "prices")
assert manifest.dataset_id == "demo_daily_prices"
assert not prices_again.empty
```

`load_manifest` verifies a content-addressed manifest digest and
`load_snapshot_dataset` verifies each referenced file hash while reading it.
The `expected_dataset_id` check prevents an alias from being paired with the
wrong dataset. Keep the Snapshot JSON, research record, and notebook output
together; the underlying manifest and data objects remain immutable.

## Ordinary notebook research

Notebook calculations are ordinary pandas code. Make timestamp normalization
and ordering explicit so the result can be moved into a report unchanged:

```python
prices["timestamp"] = pd.to_datetime(prices["timestamp"], utc=True, errors="raise")
prices = prices.sort_values("timestamp", kind="mergesort").set_index("timestamp")
returns = prices["close"].astype(float).pct_change(fill_method=None).rename("returns").to_frame()
```

`plot_line` returns a normal Plotly `Figure`; it does not write a report
artifact in a notebook:

```python
from runbook.sdk import plot_line


returns_figure = plot_line(
    data=returns,
    title="Daily returns",
    show_legend=False,
    use_rangebreaks=True,
)
returns_figure.show()
```

The checked-in `demo_pnl_explorer` shape can also feed the monthly table
helper. Its fixture has only twelve rows, so use the supported
`moving_averge_window=None` value rather than asking for a 20-day window that
the small fixture cannot satisfy:

```python
from runbook.core.table import table_with_linked_plots_monthly
from runbook.core.timeseries.analysis import AggregationModes


pnl_profile = profiles["pnl_explorer_demo"]
pnl_frames, _ = client.load_datasets(pnl_profile.datasets)
pnl = pnl_frames["pnl"].copy()
pnl["date"] = pd.to_datetime(pnl["date"], utc=True, errors="raise")
book_series = pnl.pivot_table(
    index="date",
    columns="book",
    values="pnl",
    aggfunc="sum",
).sort_index()
monthly = table_with_linked_plots_monthly(
    raw_df=book_series,
    header="Book",
    moving_averge_window=None,
    aggregation_type=AggregationModes.DIFF,
    highlighting_rules={"window": 5},
    benchmark_quater=None,
    na_rep="-",
)["Book"]

monthly["data"].head()
monthly["style"]
monthly["plots"][0].show()
```

The helper returns a mapping keyed by `header`. Its `data` is the display
DataFrame, `style` is a serializable style plan, and `plots` contains one
Plotly figure per selected input column. None of these notebook values is
stored automatically; use `ctx.artifact` only inside a report.

## Record the research explicitly

Manual notebook work does not automatically create a Runbook run, report
artifacts, or captured execution provenance. Write a small explicit JSON
record when the result needs to be handed off:

```python
import json


research_record = {
    "profile_id": profile.profile_id,
    "report_id": profile.report_id,
    "parameters": dict(profile.params),
    "snapshot": {
        "snapshot_id": snapshot.snapshot_id,
        "as_of": snapshot.as_of.isoformat() if snapshot.as_of is not None else None,
        "datasets": dict(snapshot.datasets),
    },
    "manifests": dict(snapshot.datasets),
    "watermark": snapshot.watermark.isoformat(),
    "code_version": CODE_VERSION,
}
research_path = Path("research/volatility_record.json")
research_path.write_text(json.dumps(research_record, indent=2, sort_keys=True), encoding="utf-8")
```

The `manifests` map is alias-to-manifest-reference, while the nested
`datasets` map is the same Snapshot identity. Keep the record with the saved
Snapshot and any figures/tables exported from the notebook.

## Transition to a report

When an exploration becomes a repeatable deliverable, move the deterministic
calculation and artifact boundary into a report module. Save this complete
file as `reports/price_research.py`:

```python
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field
from runbook.sdk import plot_line, report, required_aliases
from runbook.sdk.layout import Report


ALIASES = required_aliases(prices="prices")


class Params(BaseModel):
    price_col: str = "close"
    vol_window: int = Field(default=20, gt=1)


@report.calc("returns")
def returns(ctx) -> pd.DataFrame:
    params = ctx.get_params(Params)
    frame = ctx.dataset(ALIASES.prices).copy()
    if "timestamp" not in frame.columns:
        raise ValueError("prices dataset requires a timestamp column")
    if params.price_col not in frame.columns:
        raise ValueError(f"price column is missing: {params.price_col!r}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp", kind="mergesort").set_index("timestamp")
    return frame[params.price_col].astype(float).pct_change(fill_method=None).rename("returns").to_frame()


@report.calc("vol")
def volatility(ctx) -> pd.DataFrame:
    params = ctx.get_params(Params)
    values = ctx.calc("returns")["returns"]
    result = values.rolling(window=params.vol_window, min_periods=params.vol_window).std(ddof=0)
    return result.mul(260.0**0.5).rename("vol").to_frame()


@report.page
def page(ctx):
    returns_frame = ctx.calc("returns")
    vol_frame = ctx.calc("vol")
    returns_plot = plot_line(data=returns_frame, title="Returns", use_rangebreaks=True)
    vol_plot = plot_line(data=vol_frame, title="Annualized volatility", use_rangebreaks=True)

    returns_table = returns_frame.reset_index()
    returns_table["timestamp"] = returns_table["timestamp"].astype(str)
    vol_table = vol_frame.reset_index()
    vol_table["timestamp"] = vol_table["timestamp"].astype(str)
    returns_plot_ref = ctx.artifact.plot(returns_plot, name="returns")
    vol_plot_ref = ctx.artifact.plot(vol_plot, name="volatility")
    returns_table_ref = ctx.artifact.table(returns_table, name="returns-table")
    vol_table_ref = ctx.artifact.table(vol_table, name="volatility-table")

    layout = Report("Price research")
    with layout.section("Charts") as charts:
        with charts.grid(columns=2) as chart_grid:
            chart_grid.plot(returns_plot_ref, title="Returns")
            chart_grid.plot(vol_plot_ref, title="Annualized volatility")
    with layout.section("Data") as data:
        with data.grid(columns=2) as table_grid:
            table_grid.table(returns_table_ref, title="Returns data")
            table_grid.table(vol_table_ref, title="Volatility data")
    return layout
```

Add the matching profile entry to your profile JSON:

```json
{
  "price_research_demo": {
    "report_id": "price_research",
    "title": "Price research",
    "enabled": true,
    "datasets": {"prices": "demo_daily_prices"},
    "params": {"price_col": "close", "vol_window": 20}
  }
}
```

For a normal current-pointer preview, load that profile and ask the client to
resolve the latest pointer. The result's HTML is in the optional workspace
store when one was configured:

```python
import os
from pathlib import Path

from runbook.sdk import create_client, load_profiles


data_uri = os.environ["RUNBOOK_DATA_STORE_URI"]
workspace_uri = os.environ.get("RUNBOOK_WORKSPACE_STORE_URI")
reports_root = Path(os.environ.get("RUNBOOK_REPORTS_ROOT", "reports"))
client = create_client(
    store_uri=data_uri,
    database_url=os.environ["RUNBOOK_DATABASE_URL"],
    workspace_store_uri=workspace_uri,
    reports_root=reports_root,
)
profile = load_profiles(Path("data/contract/report_profiles.json"))["price_research_demo"]
result = client.preview(profile, code_version=os.environ["RUNBOOK_CODE_VERSION"])
output_store = client.workspace_store or client.store
html = output_store.get(result.html_ref).decode("utf-8")
output_path = Path("preview/price_research.html")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(html, encoding="utf-8")
print(result.snapshot_id, output_path)
```

`RunbookClient.preview` always resolves current pointers and creates a new
snapshot for that preview. It does not accept a saved Snapshot. The preview
does not advance any production pointer.

## Advanced: execute against an exact saved Snapshot

Use the lower-level `execute_report` call only when the saved Snapshot itself
is the requirement. This call accepts the data store, workspace store,
profile, exact Snapshot, code identity, and report root explicitly:

```python
import os
from pathlib import Path

from runbook.core import Snapshot
from runbook.data import open_blob_store
from runbook.sdk import execute_report, load_profiles


data_uri = os.environ["RUNBOOK_DATA_STORE_URI"]
workspace_uri = os.environ.get("RUNBOOK_WORKSPACE_STORE_URI")
data_store = open_blob_store(data_uri)
workspace_store = open_blob_store(workspace_uri or data_uri)
saved_snapshot = Snapshot.model_validate_json(Path("research/volatility_snapshot.json").read_text(encoding="utf-8"))
profile = load_profiles(Path("data/contract/report_profiles.json"))["price_research_demo"]
result = execute_report(
    store=workspace_store,
    data_store=data_store,
    profile=profile,
    snapshot=saved_snapshot,
    code_version=os.environ["RUNBOOK_CODE_VERSION"],
    reports_root=Path(os.environ.get("RUNBOOK_REPORTS_ROOT", "reports")),
)
html = workspace_store.get(result.html_ref).decode("utf-8")
Path("preview/price_research-pinned.html").write_text(html, encoding="utf-8")
```

This exact-pinned path does not consult current pointers. The report module
still runs against `saved_snapshot`, and the workspace store receives the
immutable report artifacts and HTML.

## Boundaries and security

- Do not construct `Ctx` manually. Runbook creates it inside
  `execute_report`; use ordinary pandas objects in a notebook.
- `ctx.dataset`, `ctx.calc`, and `ctx.artifact` are report-only APIs. A
  notebook can call `client.load_datasets` and use the returned frames, but
  it does not get automatic artifact or provenance capture.
- `client.load_dataset(dataset_id, **filters)` applies filters to manifest
  partition keys. It is not an arbitrary pandas row-filter or SQL connector;
  filter the copied DataFrame explicitly for row-level exploration.
- The supported data stores are `file:` and `s3://`. S3 needs the optional
  `boto3` installation plus `S3_ENDPOINT_URL` when using an endpoint and
  `AWS_DEFAULT_REGION` when a non-default region is required.
- Keep database, object-store, and vendor credentials in environment variables
  or a secret manager. Do not put secrets in profile parameters, Snapshot
  JSON, research records, source locators, or notebooks committed to source
  control.
- Use `RUNBOOK_WORKSPACE_STORE_URI` for preview isolation. Keep report
  artifacts and HTML out of the shared data store when the notebook is only
  exploratory.
- The deterministic demo live providers are test/demo composition helpers,
  not generic notebook connectors. Managed notebook data remains
  snapshot-backed.
- Reports are static-first. Dash interactivity is an optional renderer
  enhancement over the same report definition; it is not required for a
  reproducible notebook-to-HTML path.

## Troubleshooting

| Symptom | Check | Action |
| --- | --- | --- |
| No current pointer | `client.pointer_registry.all()` and the source run status | Publish a successful source run; configuration import alone does not create a pointer. |
| Database connection error | `RUNBOOK_DATABASE_URL`, PostgreSQL reachability, and migrations | Use the same URL as the service/runner and run `runbook-services db upgrade`. |
| Manifest or file missing | `snapshot.datasets`, `load_manifest`, and the data-store URI | Use the matching `RUNBOOK_DATA_STORE_URI`; do not rebuild object keys or glob curated files. |
| Unexpected `as_of` result | Timezone-aware cutoff and manifest `published_at` | Remember `as_of` chooses manifest history; it does not filter rows by timestamp. |
| S3 access failure | `boto3`, bucket URI, credentials, endpoint, and region | Install the organisation-approved S3 extra in the notebook environment and verify the S3 settings. |
| Report not discovered | `RUNBOOK_REPORTS_ROOT`, `report_id`, and `<report_id>.py` | Put the module below the configured root and reload the profile file. |
| Code-version error | `RUNBOOK_CODE_VERSION` or Git metadata | Set a stable valid code identity explicitly in the notebook kernel. |
| `ctx` is missing | Notebook code trying to call `ctx.dataset` or `ctx.artifact` | Move that code into a report module; notebooks use `RunbookClient` and pandas. |
| Preview output missing | `client.workspace_store`, `result.html_ref`, and workspace URI | Read HTML from `client.workspace_store or client.store`; confirm the workspace store is writable. |

## Next steps

- [Data and snapshots](data.md) for pointers, manifests, historical reads, and
  storage.
- [Report authoring](reports.md), [Plotting helpers](plotting-helpers.md), and
  [Table templates](table-templates.md) for repeatable report composition.
- [Interactive reports](pdl-interactive.md) for optional Dash controls.
- [API reference](api.md) and [CLI reference](cli.md) for service and preview
  operations.
