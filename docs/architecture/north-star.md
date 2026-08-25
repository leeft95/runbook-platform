# Platform architecture north star

This is the small, opinionated architecture for Runbook's generic control
plane. It describes the current repository and keeps the execution boundary
small enough for a later backend implementation.

## The boundary

Runbook is a snapshot-centric data-to-report framework. The platform should
know that a source or profile run exists, how it is queued, and how its state
is recorded. It should not contain source-specific acquisition, parser, or
report business logic.

```text
source config
    -> Stage 1 readiness and immutable raw bytes
    -> source-blind Stage 2 curation and prepared pointer update
    -> pinned dataset snapshot
    -> deterministic report execution
    -> canonical PDL manifest
        -> portable HTML artifact
        -> optional interactive DashPage
            -> standalone development preview
            -> future host-owned multi-page application
```

The package responsibilities are deliberately narrow:

```text
runbook-core       contracts, canonical identities, snapshots, PDL
runbook-data       acquisition, curation, manifests, pointers, datasets
runbook-sdk        profile validation, execution, caching, PDL, HTML, DashPage rendering
runbook-services   PostgreSQL control plane, queue, API, and Dash UI
runbook-worker     one-process-per-run source and report execution
```

PostgreSQL is authoritative for configuration revisions, current dataset
pointers, queued/running/terminal runs, outcomes, and identities. Blob storage
holds immutable raw and curated products, manifests, report artifacts, and
per-run log chunks. Historical run rows are not reused for reruns.

## Local control plane

`runbook-services serve` and `runbook-services run` are separate processes.
The runner holds a PostgreSQL advisory lock and repeats one explicit cycle:
schedule due sources, observe durable cancellation, poll/reconcile only local
`Popen` handles, release settled source dependencies, and dispatch eligible
queued work. PostgreSQL remains authoritative; `LocalProcessBackend` stores
only transient `run_id -> Popen` ownership, and `runbook-worker` is one process
per run. Capacity is enforced before spawn, FIFO is among eligible work, and
same-source source runs serialize without head-of-line blocking other sources.

`tick` is a bounded compatibility operation using this same cycle. Profiles
are pinned to immutable snapshots before dispatch. A multi-source profile waits
until all relevant producers settle, then generated identity includes profile
revision/hash and snapshot ID so dependency release is durable and idempotent.
Cancellation is a PostgreSQL intent: queued rows become terminal `cancelled`,
running rows are guarded-cancelled after the owning runner stops the local
process. Restart never adopts PIDs; unowned running rows become failed or
cancelled with an ownership-lost reason. SIGINT/SIGTERM stop new scheduling
and dispatch and cancel only locally owned workers.

The operations dashboard is an operational surface for the durable ledger. It
shows run status, provenance, elapsed time, and immutable worker log chunks.

Profile settlement is intentionally a small advancement barrier layered on the
existing run ledger and pointer registry. A complete current pointer set is
resolved and locked; the first automatic set establishes a baseline for the
exact profile revision/hash, and later sets must advance every producer. Slots
may differ, so a 07:00 A refresh and a 09:00 B refresh can settle one report.
This is not a calendar SLA, retry policy, DAG, or scheduler: future queued work
is ignored, failures leave the release marker unset, and identity keys make
reconciliation idempotent. Manual profile runs bypass the barrier and retain
immutable provenance and warnings.
Stage 2 emits progress checkpoints so a slow or failed curation run remains
diagnosable without a separate stage-state table.

Interactive reports remain outside the operations UI. The SDK's Dash renderer
consumes canonical PDL, emits namespaced embeddable pages, and registers
callbacks onto an application owned by the host. PDL contains no route or
navigation metadata. AG Grid handles table-native operations client-side;
plain Python interaction handlers update analytical outputs. Optional live
providers are injected capabilities addressed by logical names, never
credentials in PDL or profiles.

The local rules are:

- runs are snapshot-pinned and deterministic;
- reports never acquire sources or publish pointers;
- a missing append predecessor is a hard recovery error;
- a stale full-refresh predecessor is recoverable and replaced;
- cancellation and shutdown touch only locally owned workers; and
- local execution remains a small polling control plane, not a general DAG
  engine.

## Backend evolution

The local backend is intentionally the first `ExecutionBackend` implementation.
The next backend can be a Kubernetes Job/Pod backend with an immutable code
revision and independently bounded resources. Kubernetes is intentionally not
implemented here.
- **Repository split:** formalize a physical split between the generic
  platform/control plane and data/execution repositories after the package
  contracts are stable. Do not duplicate orchestration logic or introduce a
  cyclic dependency while doing so.

The intended progression is:

```text
one addressable local process per run
    -> execution-backend contract
    -> Kubernetes Job/Pod with pinned code revision
```

The same durable run contracts, log identity, config revision, snapshot, and
code-version fields should survive each step. A worker implementation may be
replaced; run history and dataset identities must remain stable.

## Guardrails

Prefer decisions that reduce coupling, keep PostgreSQL authoritative, keep
workers disposable, preserve deterministic reruns, and avoid infrastructure
that has no concrete operational need. Runbook is not intended to become a
general workflow engine with arbitrary user DAGs, an operator marketplace, or
an assortment of queueing systems.
