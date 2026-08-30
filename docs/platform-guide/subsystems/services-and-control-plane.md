# Services and control plane

## Purpose

`runbook-services` is the PostgreSQL-backed authority for configuration
revisions, current pointers, durable run state, queue admission, cancellation,
reconciliation, downstream release, API, and Operations UI.

## Owns

- `models/entities.py`: `ConfigRevision` and `Run` durable state.
- `repository.py`: immutable config writes, run queue/claim/terminal state,
  pointer access, cancellation, and release queries.
- `runner.py`: one lock-protected schedule → reconcile → release → dispatch
  cycle and bounded local worker capacity.
- `app.py`, routers, and `dash/`: API and Operations UI projections.

## Does not own

Services do not execute source/report code, define PDL/table semantics, or own
private adapter/report implementation. The Operations UI's Dash/AG Grid is not
the SDK report renderer.

## Start here

- `packages/runbook/runbook-services/src/runbook/services/repository.py`
- `packages/runbook/runbook-services/src/runbook/services/runner.py`
- `packages/runbook/runbook-services/src/runbook/services/pointers.py`
- `packages/runbook/runbook-services/src/runbook/services/models/entities.py`
- `packages/runbook/runbook-services/src/runbook/services/app.py`
- `packages/runbook/runbook-services/src/runbook/services/worker_backend.py`

## Data/control flow

```{mermaid}
flowchart LR
    request[API/UI request] --> db[(PostgreSQL Run row)]
    db --> runner[ServiceRunner cycle]
    runner --> backend[LocalProcessBackend]
    backend --> worker[One worker process]
    worker --> outcome[Guarded terminal outcome]
    outcome --> db
    db --> release[Profile dependency release]
```

## Public contracts

Configuration revisions are immutable and runs pin revision/hash. `Run` stores
mode, dates, slot, trigger, status, worker ownership, snapshot/provenance,
result, reason, and timestamps. `ExecutionBackend` is submit/poll/cancel;
`RunRepository.claim` and `finish_owned` require the committed worker owner.
Queued work is FIFO with same-source serialization and bounded capacity.

Dependency release is service-owned: successful normal source roots are matched
to configured producers, settled snapshots are pinned, and profiles queue only
after producer advancement beyond the latest automatic baseline. The source
row is marked with `dependencies_released_at` only when all affected profiles
are represented. Historical sources are excluded.

## Common modifications

For status, queue, cancellation, or release behavior, change repository/runner
first and update worker integration tests. For API/UI display, follow the same
durable model into schemas/projections. Keep the worker an executor, not a
second source of lifecycle truth.

## Consumers

API clients and Operations UI submit/read runs; runner launches the worker;
worker handshakes and writes outcomes; `services/pointers.py` provides the
production pointer/snapshot seam used for release inputs. Data-owned pointer
helpers remain for standalone ingestion/client flows.

## Tests

- `tests/services/test_services.py`
- `tests/services/test_service_lifecycle.py`
- `tests/services/test_cancellation.py`, `test_addressable_runs.py`
- `tests/services/test_staggered_settlement.py`
- `tests/services/test_worker_boundary.py`
- `tests/postgres/test_phaseb_e2e.py`

## Common mistakes

- Making the worker decide queue or downstream release policy.
- Treating a historical success as a production pointer update.
- Updating UI labels without changing durable state or its tests.
- Assuming runner restart adopts an old PID; unowned runs are reconciled.
