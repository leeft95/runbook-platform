# runbook-services

PostgreSQL-backed configuration, run tracking, FastAPI endpoints, and a small
Dash operations UI for Runbook.

The API is served with `runbook-services serve`. `GET /` returns package
versions as JSON; the Dash UI is mounted at `/ui/` and API documentation is at
`/docs`.

After applying `runbook-services db upgrade`, schedule ticks from cron:

```bash
runbook-services tick --workers 4
```
PostgreSQL is the sole control-plane ledger for production runs and current
dataset pointers; blob storage retains immutable data and report artifacts.

A tick executes source acquisition and per-source curation in a bounded worker
pool, then releases enabled reports as their complete dataset snapshots become
ready. Manual profile runs remain immediate. Automatic profile runs are
dataset-triggered; profile cron fields are retained only for configuration
compatibility in v0.0.2.

The first v0.0.2 tick imports a legacy blob-store `pointers.json` only when the
database pointer table is empty. The legacy file is preserved but ignored
after import.

For local development, enable Uvicorn auto-reload with:

```bash
runbook-services serve --reload
```
