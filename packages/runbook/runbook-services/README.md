# runbook-services

PostgreSQL-backed configuration, run tracking, bounded local process
execution, FastAPI endpoints, and the Dash operations UI for Runbook.

The API is served with `runbook-services serve`. `GET /` returns package
versions as JSON; the main operations dashboard is mounted at `/ui/` and API
documentation is at `/docs`. The operations journey is profile-first:

```text
/ui/                    overview and triage
/ui/profiles            profile catalogue and configuration management
/ui/profiles/<id>       profile state, dependent sources, and run history
/ui/sources             source catalogue and configuration management
/ui/sources/<id>        source outputs, freshness, dependants, and runs
/ui/runs                secondary all-runs triage
/ui/system              factual service/repository state
```

Selecting a run in any operational grid opens the shared right-side run
drawer. Metadata and logs scroll independently; logs support manual refresh,
copy-all, and incomplete/truncated state reporting. Closing the drawer keeps
the underlying profile or source page in place. Configuration editing remains
available from the `Configuration management` action on the profile/source
catalogues. This control-plane UI is separate from the PDL report host.

The dashboard shows run status, elapsed time, provenance, and immutable worker
diagnostics stored as small chunks in the configured blob store rather than
PostgreSQL. The legacy run detail/log routes remain available for compatibility;
the drawer is the canonical inspection surface.

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
