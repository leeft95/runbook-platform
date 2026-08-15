# runbook-services

PostgreSQL-backed configuration, run tracking, FastAPI endpoints, and a small
Dash operations UI for Runbook.

The API is served with `runbook-services serve`. `GET /` returns package
versions as JSON; the Dash UI is mounted at `/ui/` and API documentation is at
`/docs`.

The service mode is externally scheduled. Run `runbook-services tick` from
cron after applying `runbook-services db upgrade`. PostgreSQL is the sole
control-plane ledger for production runs; blob storage retains immutable data
and report artifacts.

For local development, enable Uvicorn auto-reload with:

```bash
runbook-services serve --reload
```
