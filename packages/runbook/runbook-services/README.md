# runbook-services

PostgreSQL-backed configuration, run tracking, FastAPI endpoints, and a small
Dash operations UI for Runbook.

The API is served with `runbook-services serve`. `GET /` returns package
versions as JSON; the main operations dashboard is mounted at `/ui/` and API
documentation is at `/docs`. The dashboard links to filterable run history,
run provenance, and a pop-out diagnostic log viewer. Source and profile
configuration management remain available at `/ui/sources` and `/ui/profiles`.

Worker diagnostics are stored as small immutable, run-scoped chunks in the
configured blob store rather than PostgreSQL. The log page polls only newly
available chunks and stops after observing the terminal manifest.

The service mode is externally scheduled. Run `runbook-services tick` from
cron after applying `runbook-services db upgrade`. PostgreSQL is the sole
control-plane ledger for production runs; blob storage retains immutable data
and report artifacts.

For local development, enable Uvicorn auto-reload with:

```bash
runbook-services serve --reload
```
