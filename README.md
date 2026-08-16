# Runbook Platform

Runbook is a deterministic data-to-report framework. Curated immutable
datasets are resolved into snapshot-pinned report execution, cached
calculations, and HTML artifacts.

## Packages

- `runbook-core`: pure contracts, hashing, analysis, tables, and plots.
- `runbook-data`: generic HTTP/local-file ingestion, curation, manifests,
  snapshots, and local/S3 blob storage.
- `runbook-sdk`: report authoring, deterministic execution, preview, caching,
  and HTML rendering.
- `runbook-platform`: scheduling and snapshot-pinned execution helpers.
- `runbook-services`: PostgreSQL configuration/run control and a Dash UI.

The dependency direction is `core <- data <- sdk <- platform <- services`.
Reports are external templates selected with `--reports-root`; they do not
call source systems.

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

- [Data guide](docs/data.md): ingest the synthetic fixtures, configure sources,
  understand manifests, and load current or historical datasets.
- [Source adapter and curation guide](docs/source-adapters-and-curation.md): add
  acquisition capabilities and deterministic Stage 2 parsers.
- [Service operations](packages/runbook/runbook-services/README.md): configure
  PostgreSQL, run ticks, use the API, and launch the operations UI.
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md).

## Services

Production control uses PostgreSQL for configuration revisions and the run
ledger. Apply migrations, import validated configs, and invoke one externally
scheduled tick process:

```bash
runbook-services db upgrade
runbook-services config import
runbook-services tick
```

`runbook-services serve` binds to `127.0.0.1` by default and has no
authentication. Do not expose it directly to an untrusted network; place it
behind an authenticated, appropriately secured boundary.

## License

Copyright 2026 redcombojnr and contributors.

Licensed under the Apache License, Version 2.0. See `LICENSE`.
