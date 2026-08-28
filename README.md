# Runbook Platform

Runbook is a deterministic PDL-first data-to-report framework. Curated
immutable datasets are resolved into snapshot-pinned report execution, cached
calculations, and one canonical plain-JSON report manifest (PDL). That
manifest renders as portable HTML and, when enabled, as an embeddable
interactive DashPage.

Analysts normally compose `Report`, `Section`, and `Grid` objects with ordinary
Python loops. The SDK compiles that layout to canonical PDL before HTML or
Dash rendering; raw PDL remains an escape hatch for unusual cases. See
[Composable report layouts](docs/composable-report-layouts.md).

## Packages

- `runbook-core`: pure contracts, hashing, analysis, tables, and plots.
- `runbook-data`: generic HTTP/local-file ingestion, curation, manifests,
  snapshots, and local/S3 blob storage.
- `runbook-sdk`: report authoring, deterministic execution, preview, caching,
  PDL/HTML rendering, and the optional `pdl-dash/0.1` interactive extension.
- `runbook-services`: the PostgreSQL control plane, local polling runner,
  worker diagnostics, and a Dash operations UI.
- `runbook-worker`: one-process-per-run source and report execution.

The package DAG is `core -> data/sdk/services`; the SDK retains its
developer-facing `sdk -> data` edge, and `worker` composes core, data, SDK, and
services at the per-run process boundary. Services never imports worker code.
Reports are external templates selected with `--reports-root`; they do not
call source systems. PDL remains renderer-neutral: Dash IDs, AG Grid column
definitions, routes, credentials, and callback functions never enter the
core manifest.

## Install and test

This repository uses Pixi with Python 3.11:

```bash
pixi run test
pixi run lint
pixi run format-check
```

The default blob store is `file:.runbook`. Set `RUNBOOK_DATA_STORE_URI` or
pass `--store file:/path` or `--store s3://bucket/prefix` explicitly. Install
the optional S3 dependency with `runbook-data[s3]` when S3 is needed.

The checked-in synthetic source configurations and CSV fixtures exercise the
generic local-file adapter and `csv_timeseries_v1` parser. The parser requires
`params.timestamp_column`, normalizes timestamps to UTC, and uses that column
as the deterministic append key and watermark.

## Documentation

- [Runbook documentation site](https://redcombojnr.github.io/runbook-platform/)
- [Composable report layouts](docs/composable-report-layouts.md): ordinary Python, grids, spans, and compilation.
- [Data guide](docs/data.md): ingest the synthetic fixtures, configure sources,
  understand manifests, and load current or historical datasets.
- [PDL interactive reports](docs/pdl-interactive.md): semantic tables, HTML
  fallback, DashPage composition, interactions, and optional live data.
- [Source adapter and curation guide](docs/source-adapters-and-curation.md): add
  acquisition capabilities and deterministic Stage 2 parsers.
- [Service operations](packages/runbook/runbook-services/README.md): configure
  PostgreSQL, run bounded ticks, inspect the dashboard and worker logs, use
  the API, and launch the operations UI.
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md).

## Services

Production control uses PostgreSQL for configuration revisions, current
dataset pointers, and the run ledger. Apply migrations, import validated
configs, then run the API/UI and polling runner as separate processes:

```bash
runbook-services db upgrade
runbook-services config import
runbook-services serve
runbook-services run --workers 4 --poll-interval 5
```

`runbook-services tick` remains a bounded compatibility/debugging cycle. The
long-lived runner schedules due sources, dispatches at most `--workers`
addressable `runbook-worker` processes, polls them non-blockingly, and releases
settled profile snapshots. For multi-source profiles, a dataset-triggered
snapshot advances only when every configured producer has a current valid
pointer from a different successful source run than that profile revision's
latest automatic baseline. The first complete snapshot establishes that
baseline; producer slots need not match (for example, A at 07:00 and B at
09:00). PostgreSQL is the durable FIFO-among-eligible queue;
same-source source runs serialize while unrelated sources continue. Excess
work stays queued, and `POST /api/v1/runs/{run_id}/cancel` records durable
cancellation intent. The local backend owns only its transient `Popen`
handles; restart treats unowned running rows as failed/cancelled orphans.
Repeated reconciliation is idempotent by profile revision/hash and snapshot
identity. Queued or running future source work does not block a complete
current pointer set, while failed, cancelled, not-ready, or pointerless
producers leave the dependency release marker unset. Manual profile runs pin
the latest pointers at dispatch time and carry immutable provenance and a prominent
warning that the barrier was bypassed; they never establish an automatic
baseline.

`runbook-services serve` binds to `127.0.0.1` by default and has no
authentication. Do not expose it directly to an untrusted network; place it
behind an authenticated, appropriately secured boundary.

Source detail pages can queue one-off historical runs for research, report
development, historical validation, and reproducible bounded source
acquisition. The user-facing `start_date` and `end_date` are inclusive. These
runs pin the persisted source revision and hash, use the normal durable queue
and worker path, and retain immutable output manifests and provenance. Open a
completed run to inspect and copy its complete manifest refs from the shared
drawer. Historical runs do not create temporary revisions, update the current
pointer, or release downstream scheduled reports. Historical capability is an
explicit adapter opt-in checked by the worker before acquisition; a request
may be queued before an unsupported adapter is rejected. Arbitrary temporary
source-parameter overrides are intentionally outside the v0.3.1 contract.

## License

Copyright 2026 redcombojnr and contributors.

Licensed under the Apache License, Version 2.0. See `LICENSE`.
