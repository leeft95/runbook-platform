# Platform architecture north star

This is the small, opinionated direction for Runbook's generic control plane.
It is adapted from the platform north-star planning note while describing the
current repository and explicitly separating Phase A from future Phase B work.

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
    -> HTML artifact
```

The package responsibilities are deliberately narrow:

```text
runbook-core       contracts, canonical identities, snapshots, PDL
runbook-data       acquisition, curation, manifests, pointers, datasets
runbook-sdk        profile validation, execution, caching, HTML rendering
runbook-platform   small scheduling and snapshot-pinned helpers
runbook-services   PostgreSQL control plane, queue, API, and Dash UI
```

PostgreSQL is authoritative for configuration revisions, current dataset
pointers, queued/running/terminal runs, outcomes, and identities. Blob storage
holds immutable raw and curated products, manifests, report artifacts, and
per-run log chunks. Historical run rows are not reused for reruns.

## Phase A: current platform

The current service is externally scheduled. A tick recovers stale rows,
processes queued manual work, queues the latest due source slots, executes
distinct sources in a bounded local process pool, commits successful pointer
updates, and releases profiles whose dataset watermark is ready. Profiles are
manual or dataset-triggered; only source schedules create scheduled roots.

The operations dashboard is an operational surface for the durable ledger. It
shows run status, provenance, elapsed time, and immutable worker log chunks.
Stage 2 emits progress checkpoints so a slow or failed curation run remains
diagnosable without a separate stage-state table.

The Phase A rules are:

- runs are snapshot-pinned and deterministic;
- reports never acquire sources or publish pointers;
- a missing append predecessor is a hard recovery error;
- a stale full-refresh predecessor is recoverable and replaced;
- a KeyboardInterrupt fails only runs started by that invocation, commits
  before executor shutdown, and leaves queued/unrelated rows untouched; and
- local execution is bounded to the tick and is not a daemon or general DAG
  engine.

## Phase B: future evolution

The following are intentionally future Phase B work, not requirements hidden
inside the Phase A implementation:

- **Addressable workers:** introduce a small worker contract and a stable
  `worker_id`, with one independently observable worker per run. The current
  bounded process pool is a Phase A implementation detail.
- **Cancellation:** add a first-class `cancelled` state and cancel one run
  without killing the service or unrelated work.
- **Long-lived reconciliation:** evolve the externally scheduled tick toward a
  continuously reconciling service only when operations require it; preserve
  PostgreSQL as the source of truth and keep executor capacity honest.
- **Execution backends and Kubernetes:** add the smallest backend interface
  needed by the service, then a Kubernetes Job/Pod backend with an immutable
  code revision and independently bounded resources. Kubernetes is not part
  of Phase A.
- **Repository split:** formalize a physical split between the generic
  platform/control plane and data/execution repositories after the package
  contracts are stable. Do not duplicate orchestration logic or introduce a
  cyclic dependency while doing so.

When Phase B begins, a useful progression is:

```text
bounded local pool
    -> one addressable local process per run
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
