# runbook-services

PostgreSQL-backed configuration, run tracking, bounded local process
execution, FastAPI endpoints, and a small Dash operations UI for Runbook.

The API is served with `runbook-services serve`. `GET /` returns package
versions as JSON; the main operations dashboard is mounted at `/ui/` and API
documentation is at `/docs`. The dashboard links to filterable run history,
run provenance, and a pop-out diagnostic log viewer. Source and profile
configuration management remain available at `/ui/sources` and `/ui/profiles`.

The dashboard shows run status, elapsed time, provenance, and links to a
run-scoped log page. Worker diagnostics are stored as small immutable chunks
in the configured blob store rather than PostgreSQL. The log page polls only
newly available chunks and stops after observing the terminal manifest.

The API/UI and polling runner are separate long-lived processes. After applying
`runbook-services db upgrade`, start `runbook-services serve` and
`runbook-services run --workers 2 --poll-interval 5`. The compatibility
`runbook-services tick` command uses the same bounded local process execution
and drains locally owned work before exiting. PostgreSQL is the sole
control-plane ledger for production runs; blob storage retains immutable data,
manifests, report artifacts, and worker logs. Profiles are manual or
dataset-triggered; only source schedules create scheduled roots.

For local development, enable Uvicorn auto-reload with:

```bash
runbook-services serve --reload
```
