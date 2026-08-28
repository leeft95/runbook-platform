# Data and snapshots

For report authors

Runbook keeps data collection, curation, and report reads separate. The
analyst-facing lifecycle is:

```text
source -> source run -> curated dataset -> current pointer -> snapshot -> report run
```

## The lifecycle in plain English

- A **source** is a file, HTTP endpoint, or private provider that supplies raw
  data.
- A source run stores the raw response and cleans it into a **curated dataset**
  with a stable dataset ID.
- The **current pointer** records which immutable manifest is production's
  current version.
- A report resolves the pointer into a **snapshot**, a frozen list of exact
  manifests. Later pointer changes cannot alter that report's inputs.

For example, a private market source publishes prices at 09:00. A report
starting at 09:05 freezes that 09:00 manifest. If prices update at 10:00, the
09:05 report still refers to its original snapshot.

## Read data in a report

Report code uses its declared alias, not a source file path:

```python
from runbook.sdk import report, required_aliases

ALIASES = required_aliases(prices="prices")


@report.calc("prices")
def prices(ctx):
    return ctx.dataset(ALIASES.prices)
```

The profile binds `prices` to a stable curated dataset ID. `ctx.dataset` reads
the immutable snapshot selected for the run. See [Reports](reports.md).

## The checked-in demo source

The repository includes a local CSV fixture and source configuration at
`data/contract/source_configs.json`:

```json
{
  "demo_daily_prices": {
    "adapter": "local_file",
    "enabled": true,
    "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
    "datasets": {
      "prices": {
        "dataset_id": "demo_daily_prices",
        "schema_version": "v1",
        "partition_keys": [],
        "parser_id": "csv_timeseries_v1",
        "update_mode": "full"
      }
    },
    "params": {
      "local_path": "data/fixtures/daily_prices.csv",
      "timestamp_column": "timestamp"
    }
  }
}
```

`local_file` reads an owned file. `http` performs a readiness GET and then
streams the configured URL. The `csv_timeseries_v1` parser requires the
configured timestamp column, normalizes it to UTC, stably sorts rows, and uses
timestamps as the watermark and append key. For custom acquisition or parsing,
see [Source adapters and curation](source-adapters-and-curation.md).

## Current and historical reads

The SDK client resolves the latest pointer by default:

```python
from runbook.sdk import create_client

frame, snapshot = create_client(
    store_uri="file:.runbook",
    database_url="postgresql+psycopg://postgres:postgres@localhost:5432/runbook",
).load_dataset("demo_daily_prices")
```

For a reproducible point-in-time read, pass a timezone-aware `as_of` value:

```python
from datetime import datetime, timezone

frame, snapshot = create_client().load_dataset(
    "demo_daily_prices",
    as_of=datetime(2026, 8, 1, tzinfo=timezone.utc),
)
```

You can load several datasets under local aliases or filter partitioned data;
see the [API reference](api.md) for the client methods. Always resolve a
snapshot rather than reading a curated directory or glob: old immutable
revisions remain stored beside current ones.

## Historical source jobs

An Operations user can request a bounded past range from a source's detail
page. Dates are inclusive:

```text
Sources -> choose source -> Run historical job -> start/end -> review -> submit
       -> normal queue -> run details -> Outputs and immutable manifest refs
```

The request pins the source revision/hash and uses the normal source-run queue.
On success it creates separate immutable datasets and manifests. It does not
change the standing source configuration, advance the production pointer, or
automatically trigger downstream reports. Copy the manifest references from
the run drawer's Outputs section; do not inspect object storage manually.

Historical capability is an explicit adapter decision checked before
acquisition. An unsupported adapter can enter the queue and then fail clearly
in the worker. The checked-in `local_file` adapter is not historical-capable;
successful historical smoke tests require a private/external compatible
adapter. The v0.3.1 request supports only the inclusive date range, not
temporary arbitrary parameter overrides. See [Operations](operations.md) and
[API](api.md).

## Storage and manifests

The supported stores are `file:` and `s3://`:

```text
raw/<source>/<slot>/sha256=<hash>/source.<ext>
curated/<dataset>/version=<schema>/<partition>/<revision>.parquet
curated/<dataset>/manifests/sha256=<hash>.json
```

Blob storage contains immutable raw artifacts, curated files, manifests,
report artifacts, and worker logs. A manifest records the complete selected
file set, hashes, partitions, source lineage, watermark, publication time, and
predecessor. PostgreSQL stores the mutable current pointer and run ledger.

Use `RUNBOOK_DATA_STORE_URI` or an explicit store URI; the local default is
`file:.runbook`. S3 uses `S3_ENDPOINT_URL` and `AWS_DEFAULT_REGION` (default
`us-east-1`) and needs the optional S3 dependency. See
[Deployment](deployment.md) for durable/shared storage requirements.

Analysts who need pandas exploration and saved Snapshot JSON can start with
[Research with the SDK in Jupyter](sdk-and-notebooks.md).

## Append and full updates

Each dataset binding chooses an update mode. `append` retains unchanged
partitions and merges incoming rows using parser-declared keys; `full` replaces
the complete current view with the partitions emitted by that run. Neither mode
overwrites immutable files. Pointers advance only after all new outputs are
ready.

## Invariants

- Raw artifacts, curated files, and manifests are immutable.
- A snapshot identity is derived from its resolved dataset manifests and
  producer provenance.
- Reports and renderers never acquire source data.
- A failed source run does not advance its dataset pointer.
- Report manifests retain snapshot warnings, including a manual profile run
  that bypassed an automatic dependency barrier.
