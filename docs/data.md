# Data guide

`runbook-data` turns source bytes into immutable datasets that reports and
notebooks can resolve by snapshot. It owns source configuration, acquisition,
Stage 2 parsing, Parquet revisions, complete dataset manifests, and the
PostgreSQL current-pointer registry.

Reports do not call source systems or select files directly.

## Lifecycle

```text
source config
    -> Stage 1A readiness check
    -> Stage 1B raw acquisition
    -> immutable raw artifact
    -> Stage 2 parser
    -> immutable curated Parquet revisions
    -> complete content-addressed manifest
    -> PostgreSQL dataset pointer
    -> snapshot-pinned SDK read or report run
```

Stage 2 reparses the persisted raw bytes; it never calls the source. A
successful publication writes the immutable outputs before advancing the
dataset pointer. Stage 3 calculations and Stage 4 rendering consume only the
curated files selected by a snapshot.

## Try the synthetic datasets

The repository includes two local CSV fixtures and matching source configs.
Run one source directly for local development:

```python
from datetime import datetime, timezone

from runbook.data import load_source_configs, open_blob_store, open_pointer_registry
from runbook.data.ingest import IngestRequest, run_ingest

configs = load_source_configs("data/contract/source_configs.json")
store = open_blob_store("file:.runbook")
pointers = open_pointer_registry("postgresql+psycopg://postgres:postgres@localhost:5432/runbook")

result = run_ingest(
    IngestRequest(
        source_config=configs["demo_daily_prices"],
        run_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
    ),
    store=store,
    pointer_registry=pointers,
)
print(result.datasets)
```

This produces an immutable raw CSV, a curated Parquet revision, and a manifest,
then advances the dataset pointer in PostgreSQL. Production source runs should
be initiated by `runbook-services` so pointer publication and the run outcome
commit atomically.

Load the published dataset through the SDK:

```python
from runbook.sdk import create_client

frame, snapshot = create_client(
    store_uri="file:.runbook",
    database_url="postgresql+psycopg://postgres:postgres@localhost:5432/runbook",
).load_dataset("demo_daily_prices")

print(frame.tail())
print(snapshot.snapshot_id)
print(snapshot.watermark)
```

## Source configuration

`data/contract/source_configs.json` is a strict JSON object keyed by
`source_id`. The checked-in daily fixture is configured as:

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

The identifiers have different jobs:

| Field | Meaning |
| --- | --- |
| Source map key | Scheduled source identity. |
| `adapter` | Reusable acquisition capability. |
| Dataset map key | Source-local alias connecting acquired content to a parser. |
| `parser_id` | Stage 2 business-content parser. |
| `dataset_id` | Stable curated dataset identity used by report profiles and SDK reads. |

One source may produce multiple datasets, and multiple reports may reuse one
dataset. A source-config file may declare only one producer for each
`dataset_id`.

### Built-in adapters

`local_file` checks and reads `params.local_path`. Use it for owned fixtures,
exports, and local development.

`http` performs a streaming readiness GET and then downloads the raw response.
It accepts these locator parameters, using the first populated value:

- readiness: `readiness_url_template`, `readiness_url`,
  `download_url_template`, `download_url`, or `url`;
- download: `download_url_template`, `download_url`, `url`,
  `readiness_url_template`, or `readiness_url`;
- optional output name: `filename_template`.

Templates may use `acquisition_run`, `slot`, `observed_at`, `year`, `month`,
`month_name`, and `full_month_english`.

### Built-in CSV parser

`csv_timeseries_v1` is an unpartitioned time-series parser. Set
`params.timestamp_column` to the CSV column containing the observation time.
The parser:

- requires at least one row and the configured timestamp column;
- parses timestamps as UTC and rejects invalid values;
- stably sorts rows by timestamp;
- keeps the last row when the payload repeats a timestamp;
- uses the timestamp as both the append merge key and dataset watermark.

Use a different parser when the raw content needs different validation,
partitioning, or business semantics. Keep source calls in adapters and parsing
in Stage 2. See [Building source adapters and
curators](source-adapters-and-curation.md) for the extension contracts,
registration steps, examples, and test checklist.

## Append and full publication

Every dataset binding chooses an update mode:

| Mode | Result |
| --- | --- |
| `append` | Retains unchanged partitions and merges matching partitions using parser-declared row keys. Incoming rows win on duplicate keys. |
| `full` | Replaces the complete current view with only the partitions emitted by this run. |

`append` is the default. It requires merge keys and rejects a watermark older
than the current manifest. Neither mode overwrites existing curated files.
Identical bytes reuse a revision; changed data creates the next numeric
revision and a new manifest.

## Storage and manifests

File and S3 stores share the same logical layout:

```text
raw/<source>/<slot>/sha256=<hash>/source.<ext>
curated/<dataset>/version=<schema>/<partition...>/<revision>.parquet
curated/<dataset>/manifests/sha256=<hash>.json
```

A manifest is a complete dataset view. It records selected file references,
file hashes, partitions, raw lineage, the dataset watermark, publication time,
and the preceding manifest. PostgreSQL stores the current manifest reference,
watermark, owning source, and source run for each dataset. Blob storage has no
mutable pointer state.

Curated directories are storage locations, not query interfaces. Older
revisions remain present, so reading a directory or glob can combine current
and superseded data. Always resolve a snapshot and read its selected files
through the SDK.

The default store is `file:.runbook`. Set `RUNBOOK_DATA_STORE_URI` or pass an
explicit `file:` or `s3://` URI. S3 support requires the optional dependency:

```bash
pip install "runbook-data[s3]"
```

## Current, filtered, and historical reads

`load_dataset` resolves the latest manifest and returns its exact snapshot:

```python
frame, snapshot = create_client().load_dataset("demo_daily_prices")
```

For partitioned datasets, keyword arguments filter manifest partitions before
files are read. Filter values may be scalars or collections:

```python
frame, snapshot = create_client().load_dataset(
    "your_partitioned_dataset",
    year=2026,
    region=["emea", "americas"],
)
```

Load several datasets under one snapshot by assigning local aliases:

```python
frames, snapshot = create_client().load_datasets(
    {
        "daily_prices": "demo_daily_prices",
        "intraday_bars": "demo_intraday_bars",
    }
)
```

Historical analyst reads use a timezone-aware `as_of` timestamp:

```python
from datetime import datetime, timezone

frame, snapshot = create_client().load_dataset(
    "demo_daily_prices",
    as_of=datetime(2026, 8, 1, tzinfo=timezone.utc),
)
```

The resolver walks manifest history and selects the newest publication at or
before `as_of`. Scheduled report execution remains latest-only and
snapshot-pinned.

## Data invariants

- Raw artifacts, curated files, and manifests are immutable.
- Manifests are complete dataset views and are content-addressed.
- Dataset pointers advance only after the new outputs are ready.
- Snapshot identity is SHA-256 over canonical resolved inputs. When present,
  immutable producer provenance (producer ID, successful source run ID, slot,
  and aliases) and warnings are included deterministically; legacy empty
  metadata retains its historical identity.
- Source acquisition belongs to Stage 1; business parsing belongs to Stage 2.
- Reports and renderers never call source systems.

Service-pinned snapshots preserve the exact pointer and producer evidence used
for dispatch. Report execution copies immutable snapshot warnings into both
PDL manifests; report-authored warnings cannot remove them. This keeps a manual
barrier bypass visible in static HTML and interactive Dash output.
