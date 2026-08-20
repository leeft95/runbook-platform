# Getting started

Runbook development uses Python 3.11 and Pixi. The repository's normal test
and lint commands are:

```bash
pixi run test
pixi run lint
pixi run format-check
```

The editable packages are already declared in `pixi.toml`, so `pixi install`
sets up the local development environment.

## Run the example report

The checked-in fixtures and reports demonstrate the full flow. First make
sure PostgreSQL is available, then apply the service schema and import the
validated configuration:

```bash
runbook-services db upgrade
runbook-services config import
```

The default data store is `file:.runbook`. It can be changed with
`RUNBOOK_DATA_STORE_URI` or an explicit `--store file:/path` or
`--store s3://bucket/prefix` argument. S3 support is optional; install
`runbook-data[s3]` when using it.

Run one externally scheduled service tick:

```bash
runbook-services tick --workers 4
```

For a local report preview, use the SDK command with a profile from
`data/contract/report_profiles.json`:

```bash
runbook-preview PROFILE_ID --output preview/report.html
```

The preview resolves the latest dataset pointers and writes the generated
HTML to the requested path. See {doc}`reports` for the report authoring
contract and {doc}`operations` for production service setup.

## Repository layout

| Path | Purpose |
| --- | --- |
| `packages/runbook/runbook-core` | Contracts, deterministic utilities, tables, and plots. |
| `packages/runbook/runbook-data` | Acquisition, curation, manifests, pointers, and blob storage. |
| `packages/runbook/runbook-sdk` | Report authoring, execution, preview, and HTML rendering. |
| `packages/runbook/runbook-worker` | One-process-per-run source and report execution. |
| `packages/runbook/runbook-services` | PostgreSQL control plane, API, CLI, and operations UI. |
| `reports/` | External report templates selected by profile. |
| `data/contract/` | Source and report profile configuration. |
