# runbook-services

PostgreSQL-backed configuration, run tracking, bounded local execution,
FastAPI endpoints, and the Runbook Operations UI.

Start the API/UI and polling runner as separate processes:

```bash
runbook-services db upgrade
runbook-services config import
runbook-services serve
runbook-services run --workers 2 --poll-interval 5
```

The UI is mounted at `/ui/`, API routes at `/api/v1`, and generated FastAPI
reference at `/docs`. Its pages are Overview, Profiles, Sources, Runs, and
System. They are operational views: health/triage, saved report profiles, data
sources and freshness, individual executions, and technical diagnostics.

Selecting a run opens the shared right-side drawer. It shows status and
timeline, Execution, Inputs & provenance, Outputs & artifacts, expandable Raw
details, and expandable Logs. Logs support refresh and copy-all. Historical
source outputs appear under Outputs as immutable dataset/manifest references.

The historical endpoint is
`POST /api/v1/sources/{source_id}/historical-runs` with inclusive
`start_date`/`end_date`. It uses the normal queue, pins the source revision,
does not update the production pointer, and does not trigger downstream
reports. Adapter support is checked by the worker; an unsupported adapter can
be queued before failing clearly. The checked-in `local_file` adapter is not
historical-capable.

PostgreSQL is the durable control-plane ledger. The shared `file:` or `s3://`
store retains immutable data, manifests, report artifacts, and worker logs.
`runbook-services tick` is the bounded compatibility/debugging cycle. The
service has no authentication and binds to loopback by default; secure it at
the deployment boundary before network exposure.

For the complete operator guide, see the [Operations
documentation](https://github.com/leeft95/runbook-platform/blob/main/docs/operations.md)
and [deployment guide](https://github.com/leeft95/runbook-platform/blob/main/docs/deployment.md).
