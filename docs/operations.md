# Operations UI

For operators

The Operations UI is the user-facing control plane for source and report runs.
It answers what is healthy, what is running, what failed, what data was used,
and what a run produced. PostgreSQL stores configuration revisions, dataset
pointers, and the durable run ledger; the shared data store retains immutable
outputs and logs.

For installation, startup, backups, and networking, see
[Deployment](deployment.md). For the data model, see [Data](data.md).

## Configure and start

The default local settings are:

```text
RUNBOOK_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/runbook
RUNBOOK_DATA_STORE_URI=file:.runbook
RUNBOOK_REPORTS_ROOT=reports
```

Initialize the schema, import validated configuration, then start the service
and polling runner as separate processes:

```bash
runbook-services db upgrade
runbook-services config import \
  --source-config data/contract/source_configs.json \
  --profiles data/contract/report_profiles.json
runbook-services serve
runbook-services run --workers 4 --poll-interval 5
```

The service listens on `127.0.0.1:8050` by default. `/healthz` checks the
process, `/readyz` checks PostgreSQL, API routes are under `/api/v1`, and the UI
is under `/ui/`. There is no built-in authentication; keep loopback binding or
place the service behind an authenticated boundary.

The runner uses PostgreSQL as the queue, launches one `runbook-worker` per
admitted run, and leaves excess work queued. Independent work can run in
parallel, while source runs for one source are serialized. Cancellation is
durable intent: queued work becomes cancelled, and a running worker is stopped
only by its owning runner.

## General usage

Use the navigation under `/ui/` according to the task, rather than treating
every page as a configuration editor:

- **Overview** (`/ui/`) answers “what needs attention?” It shows the current
  **Queued** and **Running** metrics, previous-24-hour **Succeeded**, **Failed**,
  and **Waiting / not ready** metrics, the **Active operations** and attention
  grids, and current **Dataset pointers**. It refreshes automatically every
  five seconds; use **Refresh** for an immediate update.

```{figure} _static/operations/overview.png
:alt: Operations Overview showing run metrics, attention grids, and dataset pointers
:width: 100%

The Overview page groups current run health, attention items, and dataset pointers.
```

- **Profiles** (`/ui/profiles`) is the report catalogue. Use **Search**,
  **Status**, **Availability**, and **Refresh** to find a profile, then select
  its row for profile detail. Detail shows dependent sources, latest snapshot,
  last successful run, snapshot-as-of time, and run history. Use **Configuration
  management** when changing the saved profile; a profile does not have an
  independent schedule.
- **Sources** (`/ui/sources`) is the acquisition catalogue. The same **Search**,
  **Status**, **Availability**, and **Refresh** controls filter sources. Select
  a source for detail (`/ui/sources/{source_id}`), where **Configuration**,
  **Refresh**, and **Run historical job** are available alongside outputs,
  current pointers, dependent profiles, and source run history.

```{figure} _static/operations/source-detail.png
:alt: Source detail page showing configuration, refresh, historical job, outputs, and pointers
:width: 100%

Source detail keeps acquisition configuration and its published outputs together.
```

- **Runs** (`/ui/runs`) is the execution search. Filter by **Type**, **Status**,
  **Name / target**, or **Search**, select one row to inspect it, and use
  **Cancel run** only while it is queued or running. The action is disabled for
  terminal runs or after cancellation has already been requested.

```{figure} _static/operations/runs.png
:alt: Runs page showing filters and a table of recent operations
:width: 100%

Use Runs to filter and select an operation for the drawer.
```

- **System** (`/ui/system`) gives bounded repository summaries: **Profiles**,
  **Sources**, **Recent runs**, **Current pointers**, and status counts. Use
  **Refresh** when checking a suspected service or database problem.

Overview, detail pages, and Runs also have automatic polling in addition to
their manual **Refresh** controls. A source or profile detail page refreshes
every 30 seconds; Runs refreshes every five seconds. The run drawer polls an
open active run separately.

## Track a run

Click any run row to open the shared right-side run drawer. Read it in this
order:

1. **Status and timeline** — what state the run is in, when it was requested,
   started, and finished, and how long it took.
2. **Execution** — source/profile, mode, trigger, pinned revision, adapter or
   report details, and whether a production pointer update was attempted.
3. **Inputs & provenance** — run/config hashes, snapshot and dataset manifests,
   producer/source run IDs, code version, worker, and submitted time.
4. **Outputs & artifacts** — immutable dataset/manifest references for source
   runs, or report artifact and stage-manifest references for report runs.
5. **Raw details** — an expandable technical section for uncommon ledger
   metadata.
6. **Logs** — an expandable section with manual refresh and copy-all controls.

```{figure} _static/operations/run-drawer.png
:alt: Run drawer showing operational status and lifecycle, part of Execution, and expanded Logs with Refresh logs
:width: 720px

The run drawer shows operational status and lifecycle, part of Execution, and expanded Logs with Refresh logs.
```

Failures display their persisted reason before the technical details. For a
historical source run, Outputs is where you copy the immutable manifest refs;
do not inspect object-store paths manually. The drawer's cancel action records
the durable cancellation request for a queued or running run.

These are sections in one progressive-disclosure drawer, not Overview/Inputs/
Outputs/Logs tabs. Select a row in Overview, Profiles detail, Sources detail, or
Runs to open it. For a direct URL, use `/ui/runs/{run_id}` for the full detail
page or `/ui/runs/{run_id}/logs` for the live bounded log page. In the drawer,
expand **Logs**, use **Refresh logs** to fetch new chunks, and use the copy
control (labelled **Copy all logs**) when handing the captured text to another
operator. **Raw details** is collapsed and is only needed for uncommon ledger
metadata.

From a profile's run history, select a report run to open the same drawer. This
view focuses on the report outputs and technical details:

```{figure} _static/operations/profile-drawer-detail.png
:alt: Report run drawer opened from profile run history, showing Outputs and artifacts with HTML and manifests plus Raw details
:width: 675px

The report run drawer shows Outputs and artifacts, including HTML and manifests, plus Raw details.
```

For a historical source run, check the completion summary and then
**Inputs & provenance** for the inclusive range, base source revision, config
hash, **No overrides**, and pointer-update state. **Outputs** contains the
produced immutable dataset manifest references, while the summary says
**Production pointer: Unchanged**. A historical run never replaces the current
production pointer, even when it succeeds.

Cancellation is durable but has two visible timings: cancelling a queued run
terminalizes it before a worker starts; cancelling a running run first records
the request and shows **Cancelling**, then its owning runner stops and
terminalizes that worker. Do not expect the running case to disappear
immediately or assume that another runner owns the process.

## Diagnose failures

Start with the status and reason in the run drawer, then inspect the named
section in this compact order:

| Symptom | Inspect | Action |
| --- | --- | --- |
| **Queued** for longer than expected | Status/timeline, worker column, and Overview **Active operations** | Confirm the polling runner is connected to the same PostgreSQL database; check its process and shared data-store setting. |
| **Running** too long | **Execution**, **Inputs & provenance**, and refreshed **Logs** | Check the owning runner/worker, database connectivity, and shared store; inspect the last log event before submitting another run. |
| **Cancelling** | Cancellation requested time, timeline, and **Logs** | Wait for the owning runner to stop and reconcile the worker; a running cancellation is not an instant terminal transition. |
| **Failed** | The drawer's **Failure** reason first, then **Execution**, **Inputs & provenance**, and **Logs** | Correct the source, parser, report, or profile configuration and submit a new run; a failed source run does not advance its production pointer. |
| **Waiting** or **Not ready** | Status reason, dependent source state, and current **Dataset pointers** | Refresh the dependency/source, make the expected data ready, or resolve the queue condition; do not treat waiting as a successful publication. |
| Success but **missing outputs** | **Outputs & artifacts**, run result, and the shared data store | Confirm the run is truly successful and that service and runner use the same store; do not manufacture artifact or manifest paths. |
| Successful source run but **no pointer** | Source **Outputs**, Overview **Dataset pointers**, mode, and run status | A normal successful source run should publish; a historical run intentionally leaves the production pointer unchanged. Check runner/database state before retrying. |
| **Logs unavailable** or incomplete | Drawer log status, direct `/ui/runs/{run_id}/logs` page, run slot, and shared store | Check the same data-store URI and runner ownership. Logs can be bounded or incomplete after worker termination; the persisted run reason and metadata remain authoritative. |
| Unsure whether to cancel | Current status and **Cancel run** availability | Cancel queued work when it should not run; for running work expect **Cancelling** and eventual runner reconciliation. Terminal runs cannot be cancelled. |

The service and runner must share PostgreSQL for the queue and the same durable
data-store URI for manifests, artifacts, and logs. If both are healthy but a
run remains unresolved, preserve the run ID and captured reason/logs for the
next operator rather than deleting revisions or replaying from an object-store
path.

## Historical source runs

Historical runs fetch a specific past date range for research, report
development, validation, or reproducible bounded acquisition. They do not
replace today's production data.

From **Sources**:

```text
choose source -> Run historical job -> inclusive start/end -> review
             -> submit -> normal queue -> inspect Outputs and Logs
```

The request is `POST /api/v1/sources/{source_id}/historical-runs` with only
`start_date` and `end_date`. Both dates are inclusive. Runbook pins the source
revision and hash at submission, keeps the request in the normal queue and run
lifecycle, and produces separate immutable dataset/manifest outputs. It does
not create a temporary source revision, advance the production pointer, or
automatically trigger downstream reports.

Historical support is checked by the adapter in the worker. A request can be
queued before an unsupported adapter is rejected; the run then fails clearly in
the normal lifecycle. The checked-in `local_file` adapter is not
historical-capable. Arbitrary temporary source-parameter overrides are not part
of this feature.

## Operations branding

Deployment owners can supply an `OperationsBrand` in a private Python
composition root; ordinary analysts do not configure it:

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

The deployment serves the asset URLs. Brand colours affect identity accents;
Runbook retains semantic status colours for success, failure, warning, running,
queued, and cancelled. See [Deployment](deployment.md) for asset placement and
the distinct report renderer extension seam.

## Recovery

Acquisition and curation outputs are immutable. A failed run does not advance a
dataset pointer. Inspect Execution, Inputs & provenance, and Logs; correct the
source/parser/report configuration; then submit a new run. Do not delete
curated revisions to force a current view.
