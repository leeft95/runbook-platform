# Data and snapshots

## Purpose

`runbook-data` acquires raw source bytes and deterministically curates immutable
datasets/manifests. Its pointer/snapshot helpers support standalone ingestion
and SDK-client flows; production pointer publication and profile snapshot
pinning use the service-owned control-plane seam.

## Owns

- Stage 1 adapter checks/acquisition and previous acquisition state.
- Stage 2 source-blind parsing, partition validation, append/full updates, and
  immutable manifests.
- Standalone pointer publication and snapshot-resolution helpers in
  `data/pointers.py` and `data/manifests.py`.

## Does not own

Data does not own report code/layout/rendering, service queue policy, worker
subprocess ownership, or private vendor behavior beyond public adapter seams.

## Start here

- `packages/runbook/runbook-data/src/runbook/data/ingest/runner.py`
- `packages/runbook/runbook-data/src/runbook/data/ingest/runners/stage2.py`
- `packages/runbook/runbook-data/src/runbook/data/manifests.py`
- `packages/runbook/runbook-data/src/runbook/data/pointers.py`
- `packages/runbook/runbook-services/src/runbook/services/pointers.py` —
  production pointer registry and snapshot seam.
- `packages/runbook/runbook-core/src/runbook/core/data.py`

## Data/control flow

```{mermaid}
flowchart LR
    adapter[Adapter] --> raw[Immutable raw artifact]
    raw --> parser[Source-blind parser]
    parser --> files[Curated immutable files]
    files --> manifest[Dataset manifest]
    manifest --> standalone[Standalone data pointer/snapshot helpers]
    manifest --> result[Worker curation result]
    result --> production[services/pointers.py\nproduction control plane]
    standalone --> snapshot[Snapshot]
    production --> snapshot
    snapshot --> report[SDK report]
```

## Public contracts

Stage 1 validates readiness and persists a digest-checked raw artifact. Stage 2
must return configured dataset aliases, validates partition keys, and writes
immutable Parquet/manifests before a caller publishes pointer updates. Append datasets require
explicit merge keys and reject missing predecessors; full datasets can recover
from a missing prior manifest. A pointer is mutable selection state, not the
dataset itself.

The production worker calls `run_stage1_acquire` then `run_stage2_curate`; after
the worker's durable `finish_owned` outcome, `services/pointers.py` publishes
normal source updates. `data/ingest/runner.py::run_ingest` is the separate
standalone path that publishes through `data/pointers.py`. The service-owned
`resolve_snapshot` records exact manifest refs, IDs, watermarks, and producer
provenance for production profile runs; data's equivalent helper serves
standalone/client flows. Reports must read a pinned snapshot, not a curated
directory or current pointer at render time. Historical source runs use
`HistoricalExecutionContext`, no production pointers, and separate outputs.

## Common modifications

Change source behavior in adapters/protocols; change parsing in parser seams;
change publication/partition logic in Stage 2/manifests; change production
selection in `services/pointers.py` and the service runner together. Change
standalone ingestion selection in `data/pointers.py` only for that direct path.
For historical behavior, update capability checks and worker/service tests
without changing normal pointer semantics.

## Consumers

Workers execute ingestion; services/pointers.py publishes production pointers
and pins profile snapshots; SDK context reads the pinned snapshot. The
standalone SDK client and `run_ingest` use data-owned pointer helpers. Reports
consume aliases bound by profile configuration.

## Tests

- `tests/data/test_generic_ingest.py`
- `tests/data/test_pointers.py`
- `tests/data/test_historical_source_jobs.py`
- `tests/sdk/test_client_workspace.py`, `test_snapshot_warnings.py`
- `tests/postgres/test_phaseb_e2e.py` for real lifecycle coverage

## Common mistakes

- Treating a pointer or directory as the immutable input.
- Publishing before all manifest/files are ready.
- Merging historical output with current production state.
- Guessing a missing append predecessor or object-store path.
