# Deployment guide

For platform owners and operators

This guide describes a small, repeatable internal deployment. It does not
require Kubernetes, Docker, or a cloud platform. Runbook's production database
is PostgreSQL; its durable data store is a shared file store or S3-compatible
store.

## What gets deployed?

```text
Users -> Runbook service -> PostgreSQL
                    |
                    +-- durable queue -> Runbook worker -> shared data store

report/private packages + adapters + renderer extension + assets
```

- The **service** owns the API, Operations UI, configuration, and run
  submission.
- A **worker** claims queued source/report runs, executes them, writes logs,
  and participates in cancellation/reconciliation.
- **PostgreSQL** stores configuration revisions, dataset pointers, and the run
  ledger.
- The shared **data store** holds raw data, curated datasets/manifests, report
  artifacts, and worker log chunks.
- A deployed report/private runtime supplies report code, private adapters,
  and optional presentation code.

The service and every worker must use the same database, data-store URI, report
runtime/package versions, and report root.

## Minimum production setup

The smallest sensible setup is one PostgreSQL database, one service process,
one or more worker processes, one durable shared store, and one exact set of
public/private report packages. Add workers only for independent queued work;
Runbook still serializes source runs for the same source.

## Configuration

Set these environment variables in the service and worker runtime as shown:

| Setting | Controls | Required | Applies to |
| --- | --- | --- | --- |
| `RUNBOOK_DATABASE_URL` | PostgreSQL connection, for example `postgresql+psycopg://runbook:***@db/runbook` | yes | service and worker |
| `RUNBOOK_DATA_STORE_URI` | shared blob store, `file:/srv/runbook-data` or `s3://bucket/prefix` | yes in production | service and worker |
| `RUNBOOK_REPORTS_ROOT` | installed report templates, normally `/srv/runbook/reports` | when not `reports` | worker and config/runtime composition |
| `RUNBOOK_CODE_VERSION` | immutable code identity recorded on report runs | recommended | worker/runner and preview |
| `RUNBOOK_LOG_LEVEL` | logging verbosity (`INFO` by default) | no | processes that configure SDK logging |

The S3 implementation also reads `S3_ENDPOINT_URL` and
`AWS_DEFAULT_REGION` (default `us-east-1`). Credentials come from the normal
AWS SDK environment/credential chain, not from reports or profiles. Only
`file:` and `s3://` store URIs are supported.

The service CLI can override relevant settings with `--database`, `--store`,
`--reports-root`, and `--code-version` where that command supports them. The
worker command receives only a durable run ID and reads its configuration from
the database; do not pass secrets or source parameters on its command line.

## PostgreSQL and migrations

PostgreSQL is the production control-plane database. On a fresh database, or
before starting a new application version, run the actual migration command:

```bash
runbook-services db upgrade
```

Then import validated source/profile configuration:

```bash
runbook-services config import \
  --source-config data/contract/source_configs.json \
  --profiles data/contract/report_profiles.json
```

For an upgrade, back up PostgreSQL, deploy the exact package set, run
`runbook-services db upgrade`, and only then start service and workers. A
migration failure is a stop condition: keep the old runtime available for
recovery, inspect the migration error, and do not start workers against a
partly upgraded schema. SQLite remains useful for tests/development, not as a
production control plane.

## Durable data storage

The store contains immutable raw artifacts, curated Parquet revisions,
dataset manifests, report HTML/PDL/artifacts, calculation cache entries, and
worker logs. Service and worker processes must be able to read and write the
same durable location. A local path is suitable for one host; use a shared
durable filesystem or S3-compatible object store when processes are split
across hosts.

Do not read a curated directory as “latest”: resolve a dataset pointer and
snapshot instead. See [Data](data.md).

## Start the service and workers

The service binds to loopback by default and serves the API, health endpoints,
and Operations UI:

```bash
runbook-services serve --host 0.0.0.0 --port 8050
```

The long-lived runner claims work and starts one worker process per admitted
run:

```bash
runbook-services run --workers 4 --poll-interval 5
```

The low-level worker entry point is available when a scheduler or runner needs
to launch a specific durable row:

```bash
runbook-worker --run-id RUN_ID
```

Use `runbook-services tick --workers 1` only for a bounded/debugging cycle.
`runbook-services serve` has no authentication; retain loopback binding or put
it behind an authenticated boundary before exposing it to users. Verify
startup with `GET /healthz`, then `GET /readyz` to check PostgreSQL. The UI is
at `/ui/` and API routes are under `/api/v1`.

## Reports and private packages

Deploy private code as dependencies of the runtime that imports public Runbook
packages:

```text
public Runbook packages
        + private adapters
        + private reports
        + private renderer extension
        + deployment assets
```

Keep exact package/build versions together and set `RUNBOOK_CODE_VERSION` to a
known immutable value. Do not fork or copy the public repository to add
private adapters or report code. The worker's `RUNBOOK_REPORTS_ROOT` must point
to the deployed reports directory.

## Operations branding

Branding customises the Operations UI identity without replacing Runbook's
pages. It is supplied by a private Python composition root; there is no
branding option on `runbook-services serve`:

```python
from runbook.services.app import create_app
from runbook.services.dash import OperationsBrand

brand = OperationsBrand(
    name="Company",
    logo_src="/assets/company-logo.svg",
    favicon_src="/assets/company-favicon.ico",
    primary="#0f766e",
    primary_hover="#115e59",
    primary_soft="#ccfbf1",
)

app = create_app(operations_brand=brand)
```

Arrange for the deployment web server to serve those asset URLs. Do not copy
private files into an installed public package directory. `primary`,
`primary_hover`, and `primary_soft` brand navigation, links, and accents;
Runbook still owns semantic colours such as green success and red failure.
The same seam is described from an operator's perspective in
[Operations](operations.md).

## Report renderer extensions

This is a separate seam from Operations branding:

```text
OperationsBrand       -> control-plane UI identity
DashRendererExtension -> rendered report presentation
```

A private report host injects a trusted `DashRendererExtension` into
`render_dash_page(...)` or `compose_report_page(...,
renderer_extension=extension)`. The extension can add report chrome, providers,
components, and styles. Public Runbook retains PDL traversal, artifact reads,
interaction decoding, callback registration, IDs, and namespacing. See [Dash
renderer extensions](dash-renderer-extensions.md).

## Startup and upgrade order

1. Provision PostgreSQL and durable shared storage.
2. Install the exact public/private package set and report files.
3. Set runtime environment and secret-manager bindings.
4. Run `runbook-services db upgrade`.
5. Import or verify source/profile configuration.
6. Start the service and check `/healthz` and `/readyz`.
7. Start `runbook-services run` workers.
8. Open the Operations UI and run the go-live smoke test below.

For an upgrade, back up first, record the deployed code version, stop or drain
workers as appropriate for your process manager, deploy packages, run the
migration, start the service, then start workers. Runbook does not promise
zero-downtime upgrades.

## Backups, secrets, and networking

Back up PostgreSQL, the durable data store, private report/adapter source, and
deployment configuration. A database-only backup cannot restore immutable
datasets and report artifacts. Test that a database backup and corresponding
store backup can be restored together.

Keep database, object-store, and private-adapter credentials in the runtime
environment or organisation secret manager. They do not belong in report code,
committed source configuration, PDL manifests, branding fields, or logs.

Allow users to reach the service port (8050 by default), service/workers to
reach PostgreSQL, and service/workers to reach the shared store. Private
adapters may need vendor-specific network access. Protect the service with the
organisation's authentication boundary; the built-in service is not an
authentication layer.

## Production smoke test

Run this after a fresh install and every upgrade:

1. Open `/ui/` and confirm the System page is healthy.
2. Submit a normal source run; confirm a worker claims and completes it.
3. Confirm its production dataset pointer advances.
4. Run a profile and open the rendered output.
5. Submit a historical source run with an installed adapter that supports
   historical ranges.
6. Confirm its immutable dataset/manifest outputs appear in the run drawer.
7. Confirm the production pointer is unchanged and no downstream report was
   automatically triggered.
8. Inspect source and report logs in the expandable Logs section.

The checked-in `local_file` adapter is not historical-capable, so it is useful
for a normal local smoke but cannot prove a successful historical smoke. A
private or external compatible adapter is required for step 5; an unsupported
adapter should fail clearly in the normal queued run lifecycle.

## Troubleshooting

| Symptom | Check first |
| --- | --- |
| Service starts but UI cannot load data | `/readyz`, `RUNBOOK_DATABASE_URL`, and database network/credentials. |
| Worker never claims jobs | `runbook-services run` is running, it shares the database, and another runner does not hold the advisory lock. |
| Source run fails immediately | Open the run drawer's Execution and Logs sections; check adapter/parser package availability and configuration. |
| Report says no pointer exists | The source run has not published the dataset, or the profile dataset ID/alias is wrong. |
| Logs are unavailable | Service and worker share `RUNBOOK_DATA_STORE_URI`; inspect the run's log reference and store permissions. |
| Branding logo does not load | The asset URL in `OperationsBrand.logo_src` is reachable from the browser; the app does not upload the asset. |
| Migration failed | Stop startup, preserve the database backup, inspect the migration error, and resolve it before retrying. |
