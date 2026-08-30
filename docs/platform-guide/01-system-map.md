# System map

This is the repository-backed component map for release 0.3.2. The service's
Dash/AG Grid pages are the Operations UI; they are separate from the SDK's
report Dash renderer.

```{mermaid}
flowchart TB
    core[runbook-core\ncontracts, PDL, tables, snapshots]
    data[runbook-data\ningest, manifests, standalone helpers]
    sdk[runbook-sdk\nauthoring, layout, HTML, Dash]
    services[runbook-services\nPostgreSQL, production pointers/snapshots, API/UI]
    worker[runbook-worker\ncomposition root, one run]
    data --> core
    sdk --> core
    sdk --> data
    services --> core
    worker --> core
    worker --> data
    worker --> sdk
    worker --> services
```

## Component responsibilities

### `runbook-core`

- **Owns:** `PDLManifest`, page/block models and versions;
  `TableStylePlan`/`ResolvedTableStyle`; `Snapshot`; artifact and data
  contracts; deterministic analysis/table/plot helpers.
- **Does not own:** Dash IDs/callbacks, HTTP routes, credentials, source
  adapters, queue state, subprocesses, or private catalogue/branding.
- **Entry points:** `core/pdl/models.py`, `core/table/models.py`,
  `core/table/builder.py`, `core/data.py`.
- **Consumers:** SDK builders/renderers, standalone data snapshot resolution,
  worker, and services models.

### `runbook-data`

- **Owns:** Stage 1 adapter readiness/acquisition, Stage 2 source-blind
  parsing/curation, immutable raw/curated outputs, manifests, plus
  standalone-ingestion pointer/snapshot helpers.
- **Does not own:** report layout, PDL rendering, worker dispatch, or service
  lifecycle policy.
- **Entry points:** `data/ingest/runner.py`, `data/ingest/runners/stage2.py`,
  `data/ingest/adapters/__init__.py`, `data/ingest/parsers/__init__.py`,
  `data/manifests.py`, `data/pointers.py`.
- **Consumers:** worker execution and the standalone SDK client; production
  pointer publication and profile snapshot pinning use the services seam.

### `runbook-sdk`

- **Owns:** report decorators and calculation context, artifact registry,
  `Report`/`Section`/`Grid` layout, compiler, execution, HTML and report Dash
  rendering.
- **Does not own:** source acquisition, mutable production pointers, durable
  queueing, or Operations UI routes.
- **Entry points:** `sdk/authoring.py`, `sdk/context.py`, `sdk/layout/`,
  `sdk/execution.py`, `sdk/html.py`, `sdk/extensions/dash/renderer.py`.
- **Consumers:** report modules and worker; private hosts may inject a
  `DashRendererExtension`.

### `runbook-services`

- **Owns:** immutable config revisions, durable run ledger, queue admission,
  cancellation/reconciliation, dependency release, API and Operations UI.
- **Does not own:** source/report execution, PDL model semantics, or private
  adapter implementation.
- **Entry points:** `services/repository.py`, `services/runner.py`,
  `services/pointers.py`, `services/app.py`, `services/worker_backend.py`,
  `services/models/entities.py`.
- **Consumers:** service clients, Operations UI, local worker backend, and the
  worker's repository handshake.

### `runbook-worker`

- **Owns:** fresh-process execution and composition of data/SDK/services;
  worker claim handshake, source/report dispatch, and terminal outcome writes.
- **Does not own:** scheduling, source ownership, production pointer policy, or
  UI.
- **Entry point:** `worker/execution.py` (`execute_run`, `_source`, `_report`).
- **Consumers:** `runbook-services`' local process backend.

## Boundary rules

`runbook-data` imports core; SDK imports core and data; services imports core;
worker composes all four. Core must not import Dash or worker. PDL remains
renderer-neutral: no routes, navigation, credentials, database connections,
Dash IDs, callbacks, or private endpoints. Report authors create calculations,
artifacts, and layout; they do not acquire sources or publish pointers.

The public SDK report renderer and the services Operations UI may both use Dash
and AG Grid, but they have different ownership and tests. See
[Contracts and boundaries](04-contracts-and-boundaries.md).
