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
PostgreSQL. Selecting a run ID opens the shared inspection drawer, which is the
canonical inspection surface.

Source detail pages also support one-off historical source runs. The required
inclusive date range and latest persisted source revision are recorded on an
ordinary queued source run; no temporary config revision is created. Historical
outputs remain immutable and addressable by their run provenance, while current
dataset pointers and downstream scheduled report dependencies are unchanged.

The API/UI and polling runner are separate long-lived processes. After applying
`runbook-services db upgrade`, start `runbook-services serve` and
`runbook-services run --workers 2 --poll-interval 5`. The compatibility
`runbook-services tick` command uses the same bounded local process execution
and drains locally owned work before exiting. PostgreSQL is the sole
control-plane ledger for production runs; blob storage retains immutable data,
manifests, report artifacts, and worker logs. Profiles are manual or
dataset-triggered; only source schedules create scheduled roots.

Dataset-triggered multi-source profiles use advancement settlement. A complete
current pointer set establishes the baseline for the exact profile revision;
later snapshots require every producer to use a different successful source
run, even when producer slots differ. Future queued work is ignored, failed or
invalid pointers do not release dependencies, and repeated ticks are
identity-idempotent. Profile manual actions pin latest pointers after
confirmation, record producer provenance, and display an immutable barrier
bypass warning; they never establish an automatic baseline.

For local development, enable Uvicorn auto-reload with:

```bash
runbook-services serve --reload
```
