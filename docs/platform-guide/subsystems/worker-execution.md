# Worker execution

## Purpose

The worker is the composition root for one durable run. It executes source
ingestion or a report in a fresh subprocess, captures logs, and writes a
terminal result only while it still owns the claimed row.

## Owns

- `worker/execution.py::execute_run`, `_source`, `_report`, and claim
  handshake.
- Runtime wiring for core/data/SDK/services, config validation, normal-source
  outcome handoff to service pointer publication, and worker log capture.
- `services/worker_backends/local_process.py`: one process per run and bounded
  poll/cancel behavior (the backend itself is services-owned).

## Does not own

The worker does not schedule, queue, define config revisions, resolve
downstream release, or own the API/UI. It follows service state and cannot
claim a row before the service commits its worker ID.

## Start here

- `packages/runbook/runbook-worker/src/runbook/worker/execution.py`
- `packages/runbook/runbook-services/src/runbook/services/worker_backends/local_process.py`
- `packages/runbook/runbook-services/src/runbook/services/runner.py::_dispatch`
- `tests/services/test_worker_boundary.py`
- [Post-publish email delivery](../../email-delivery.md)

## Data/control flow

```{mermaid}
sequenceDiagram
    participant S as Service
    participant W as Worker
    participant DB as PostgreSQL
    participant Store as Shared store
    S->>W: spawn with run ID
    W->>DB: wait for committed local claim
    W->>DB: load + validate pinned config
    W->>Store: execute source or report
    W->>DB: finish_owned outcome
    S->>DB: poll/reconcile
```

## Public contracts

The worker receives only a durable run ID and environment configuration. The
claim is `local:<pid>`; `wait_for_claim` rejects terminal/cancelled rows. Source
normal runs publish pointer updates guarded by expected source-run IDs;
historical runs skip production publication. Report runs validate pinned
snapshot payload and code/config identity before `execute_report`.
After a report result is published, an optional configured email sender consumes
the existing HTML artifact. Delivery failure is recorded separately while the
report remains successful; `--deliver-run-id` retries only that metadata path.

If a worker exits without a terminal outcome, the owning runner records a
failure; if ownership is lost after restart, the new runner reconciles the row
as failed/cancelled. Logs are immutable/bounded store artifacts referenced by
the outcome.

## Common modifications

Add runtime composition in `worker/execution.py` only when service/data/SDK
contracts are already correct. Change claim or terminal rules in services
repository and test both sides. Keep source and report branches returning JSON
outcomes with stable status/reason/ref fields.

## Consumers

`LocalProcessBackend` launches workers; `ServiceRunner` polls/reconciles them;
service run drawer and API expose their persisted outcomes. Data/SDK execute
the branch-specific work.

## Tests

- `tests/services/test_worker_boundary.py`
- `tests/services/test_worker_execution.py`
- `tests/services/test_addressable_runs.py`
- `tests/services/test_worker_backends.py`
- `tests/services/test_service_lifecycle.py`
- `tests/postgres/test_phaseb_e2e.py`

## Common mistakes

- Letting a worker resolve a fresh profile snapshot after dispatch.
- Publishing historical pointers or downstream profiles.
- Writing a terminal outcome without ownership/cancellation guards.
- Passing secrets or source overrides on the worker command line.
