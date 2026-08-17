# Service operations

`runbook-services` is the PostgreSQL-backed control plane. PostgreSQL stores
validated configuration revisions, current dataset pointers, and the run
ledger. Blob storage retains immutable raw data, curated files, manifests,
and report artifacts.

## Configure the service

The default values are suitable for local development:

```text
RUNBOOK_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/runbook
RUNBOOK_DATA_STORE_URI=file:.runbook
RUNBOOK_REPORTS_ROOT=reports
```

Apply migrations and import source/profile configuration:

```bash
runbook-services db upgrade
runbook-services config import \
  --source-config data/contract/source_configs.json \
  --profiles data/contract/report_profiles.json \
  --reports-root reports
```

The config import validates source configs, profile dataset IDs, report
aliases, and report file discovery before writing revisions.

## Schedule ticks

Run one tick from an external scheduler such as cron:

```bash
runbook-services tick --workers 4
```

Each tick runs a bounded worker pool for source acquisition and curation,
then releases enabled reports whose complete dataset snapshots are ready.
Automatic report runs are dataset-triggered in v0.0.2; profile cron fields
remain accepted for configuration compatibility. Manual API-triggered runs
remain immediate.

## Serve the API and UI

Start the service locally with:

```bash
runbook-services serve
```

It binds to `127.0.0.1:8050` by default. `--reload` enables Uvicorn reload
for development only. The root endpoint returns versions, `/healthz` is a
process health check, `/readyz` checks database readiness, API routes are
under `/api/v1`, and the Dash UI is mounted at `/ui/`.

The service has no authentication. Keep the loopback binding or put the
service behind an authenticated, appropriately secured boundary before
exposing it to a network. See the repository [security policy](https://github.com/redcombojnr/runbook-platform/blob/main/SECURITY.md).

## Failure and recovery

Acquisition and curation outputs are immutable. A failed run does not advance
the pointer. Inspect the run ledger and logs, correct the source or parser
configuration, and trigger the source again. Do not delete curated revisions
to force a current view; the pointer and manifests provide the intended
recovery boundary.
