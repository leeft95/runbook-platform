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
v0.2.1 compatibility; report aliases and report module discovery are validated
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

### Staggered multi-source settlement

Profile releases are based on advancement, not an exact shared clock slot. The
runner validates and locks every current pointer, verifies its manifest, and
requires the pointer's source run to be a durable success for the configured
producer. All aliases owned by one producer must use one source run; multiple
successful attempts coalesce to the run represented by the current pointer.

The first complete automatic pointer set is accepted as that profile revision's
baseline. Later releases require every producer to advance to a different
successful source run. For example, A0/B0 establishes a baseline, A1 at 07:00
waits while B is still B0, and B1 at 09:00 releases the A1/B1 snapshot. Queued
or running future work is ignored. Failed, cancelled, not-ready, invalid, or
pointerless work leaves `dependencies_released_at` null. A source row may be
reconciled repeatedly; the profile identity key means only one pinned run is
queued, including when multiple source rows observe the same snapshot.

Automatic baselines are scoped to the exact profile revision and config hash,
and include runs in any lifecycle state. Legacy baselines without producer
provenance fall back to per-producer manifest-reference comparison. A new
revision starts with no baseline. Manual profile actions use the latest
pointers without waiting for advancement, require confirmation in the UI, and
persist immutable provenance plus warnings listing non-advanced producers (or
that no baseline was available). Manual runs never become baselines.
This advancement rule is not a calendar/SLA guarantee and does not add a DAG,
retry policy, or cross-run scheduler; operators must diagnose and rerun failed
source work through the existing controls.

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

Click a run to inspect status, lifecycle timing, provenance, outputs, actions,
and logs in the shared run drawer. Selecting any run row opens it without
changing the underlying page. Its metadata and log panes scroll independently.
Use the drawer controls for manual log refresh, copy-all, and durable
cancellation of queued/running runs.

The local process backend is the first `ExecutionBackend` implementation;
Kubernetes is the next backend direction. No retries, priority queue,
heartbeat, broker, or PID adoption is performed.

### One-off historical source runs

Historical runs support research, report development, historical validation,
and reproducible bounded source acquisition. From a source detail page, choose
**Run historical job**, enter the required inclusive `start_date` and
`end_date`, review the pinned source revision and hash, and submit. The request
is persisted as an ordinary `source` run (`mode=historical`) in the normal
durable queue, so existing serialization, worker ownership, cancellation,
restart reconciliation, logs, and status lifecycle apply.

Historical execution uses the existing source definition at its latest
persisted revision when submitted. It records the base revision/hash and
immutable inclusive date range on the run; it never creates a temporary source
configuration revision. Successful runs expose their immutable curated
datasets and complete manifest refs in the run result and shared run drawer,
where each ref can be copied for analysis. The current production dataset
pointer is not updated and downstream scheduled report dependencies are not
released.

Historical support is an explicit adapter opt-in. The worker validates that
the adapter accepts the historical execution context before acquisition
begins. A request may enter the normal durable queue before an unsupported
adapter is rejected, because service and worker runtimes may not have the same
installed plugin composition; the control plane does not inspect plugin
composition. Unsupported requests fail with a source-specific message while
remaining in the normal run lifecycle. Arbitrary temporary source-parameter
overrides are intentionally not part of the v0.3.1 historical-run contract;
only the source, inclusive date range, and pinned revision/hash are supported.

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
