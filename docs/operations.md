# Service operations

`runbook-services` is the PostgreSQL-backed control plane. PostgreSQL stores
validated configuration revisions, current dataset pointers, and the run
ledger. Blob storage retains immutable raw data, curated files, manifests,
report artifacts, and per-run worker log chunks.

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
  --reports-root reports  # retained deprecated compatibility option
```

The config import validates source configs and profile dataset IDs before
writing revisions. `--reports-root` is retained as a deprecated no-op for
v0.2.0 compatibility; report aliases and report module discovery are validated
by the worker at execution time, where the configured report root is available.

## Polling runner and compatibility tick

Run the API/UI and long-lived polling runner as separate processes:

```bash
runbook-services run --workers 4 --poll-interval 5
```

The runner holds one PostgreSQL advisory lock for its lifetime and cycles in
schedule, cancellation, poll/reconcile, dependency release, and dispatch order.
Each run maps to one short-lived `runbook-worker` process. `LocalProcessBackend`
owns only its in-memory `run_id -> Popen` handles; PostgreSQL owns run status,
worker identity, cancellation timestamps, and pinned snapshots. Capacity is
checked before spawning, dispatch is FIFO among eligible work, and source runs
for one source remain serialized without blocking unrelated sources. `tick`
uses this same cycle, drains locally owned work, and exits for debugging.

Cancel a queued or running run through the API. Queued cancellation is terminal
immediately; running cancellation records intent and the polling runner
terminates only its locally owned process before guarded cancellation. A runner
restart never adopts PIDs: unowned running rows become failed or cancelled with
`worker ownership lost / runner restarted`. SIGINT/SIGTERM stop scheduling and
dispatch, then cancel only local workers with bounded termination.

## Serve the API and UI

Start the service locally with:

```bash
runbook-services serve
```

It binds to `127.0.0.1:8050` by default. `--reload` enables Uvicorn reload
for development only. The root endpoint returns versions, `/healthz` is a
process health check, `/readyz` checks database readiness, API routes are
under `/api/v1`, and the Dash UI is mounted at `/ui/`.

The dashboard provides run history, provenance, status, and links to the
immutable worker logs. The service has no authentication. Keep the loopback
binding or put the service behind an authenticated, appropriately secured
boundary before exposing it to a network. See the repository [security
policy](https://github.com/redcombojnr/runbook-platform/blob/main/SECURITY.md).

### Operations UI navigation

The UI is a profile-first operational surface, separate from the PDL report
host:

```text
/ui/                    overview and triage
/ui/profiles            profile catalogue and configuration management
/ui/profiles/<id>       profile state, sources, and run history
/ui/sources             source catalogue and configuration management
/ui/sources/<id>        source outputs, freshness, dependants, and runs
/ui/runs                secondary global run triage
/ui/system              factual service/repository state
```

Selecting any run row opens one shared right-side drawer without changing the
underlying page. Its metadata and log panes scroll independently. Use the
drawer controls for manual log refresh, copy-all, and durable cancellation of
queued/running runs.

The local process backend is the first `ExecutionBackend` implementation;
Kubernetes is the next backend direction. No retries, priority queue,
heartbeat, broker, or PID adoption is performed.

For deterministic local source checks, run `python scripts/demo_http_server.py`
and enable one of the optional `demo_http_*` configurations. The server uses
only checked-in CSV fixtures and exposes CSV, slow, 404, and 500 routes. The
standard suite uses SQLite and must have zero skips. The PostgreSQL release
suite is explicit: use
`RUNBOOK_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/runbook-platform-demo`
for the disposable release database and run `pixi run test-postgres`. The
harness fails immediately when the URL is absent or names the vendor database
`runbook`; arbitrary disposable CI database names remain supported.

## Failure and recovery

Acquisition and curation outputs are immutable. A failed run does not advance
the pointer. Inspect the run ledger and logs, correct the source or parser
configuration, and trigger the source again. Do not delete curated revisions
to force a current view; the pointer and manifests provide the intended
recovery boundary.
