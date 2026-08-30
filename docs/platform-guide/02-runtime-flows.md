# Runtime flows

These are the flows worth tracing when a platform change behaves unexpectedly.

## Profile/report execution

The service owns the durable request and snapshot pinning. The worker owns
execution. The renderer only consumes artifacts and PDL.

```{mermaid}
sequenceDiagram
    participant C as Client/UI
    participant S as Service runner
    participant W as Worker
    participant D as Snapshot/data store
    participant R as Report code
    participant P as PDL/renderers
    C->>S: queue profile run
    S->>D: resolve and persist snapshot
    S->>W: spawn and commit claim
    W->>D: read pinned snapshot
    W->>R: execute report
    R->>D: write calculations/artifacts
    R->>P: compile PDL
    P->>D: publish HTML/manifest artifacts
    S->>C: durable outcome and refs
```

Start at `services/runner.py::_pin_profile` for snapshot pinning, then
`worker/execution.py::_report`, `sdk/execution.py::execute_report`, and
`sdk/html.py::render_html_bundle` for the report path. The worker does not
resolve a new snapshot after dispatch.

## Source execution

```{mermaid}
flowchart LR
    request[Source run row] --> worker[worker/execution.py::_source]
    worker --> acquire[run_stage1_acquire]
    acquire --> raw[Immutable raw artifact]
    raw --> curate[run_stage2_curate]
    curate --> result[Curation result + pointer updates]
    result --> finish[services repository finish_owned]
    finish --> pointer[services/pointers.py production publication]
    pointer --> profile[Eligible profile release]
```

The production worker path is `worker/execution.py::_source`:
`run_stage1_acquire` calls adapter `validate`, `check`, and `acquire`; then
`run_stage2_curate` reparses persisted raw bytes via `get_parser`, verifies all
configured outputs, writes immutable files/manifests, and returns pointer
updates. The worker writes its terminal result with `finish_owned`; only then
does the normal source path publish updates through the service-owned
`services/pointers.py` registry. Historical execution supplies
`HistoricalExecutionContext`, starts without production pointers, writes
separate outputs, and intentionally skips pointer publication.

`data/ingest/runner.py::run_ingest` remains a separate standalone sequential
ingestion entry point. It uses `data/pointers.py` and publishes its own updates;
it is not the production worker path.

## Report authoring and build

```{mermaid}
flowchart LR
    fn[Report function] --> ctx[Ctx.calc / ctx.dataset]
    ctx --> artifact[ctx.artifact: named data/plot/file]
    artifact --> model[Report / Section / Grid]
    model --> compiler[compile_layout]
    compiler --> pdl[PDLManifest]
```

The SDK's `Ctx` reads a snapshot and registers calculations. Artifact APIs
materialize reproducible outputs; layout decides presentation. The compiler
flattens layout nodes to PDL coordinates. Use `reports/vol_report.py`,
`reports/linked_table_report.py`, or `reports/pnl_explorer.py` as compact
architecture examples.

## Rendering

```{mermaid}
flowchart TB
    pdl[PDLManifest] --> html[HTML renderer\nsdk/html.py]
    pdl --> dash[SDK Dash renderer\nsdk/extensions/dash/renderer.py]
    dash --> native[Native static table\ndefault]
    dash --> grid[AG Grid\nexplicit interactive opt-in]
```

Both renderers consume PDL and persisted artifacts. Shared table semantics are
resolved by core; native Dash uses the resolved style directly. AG Grid gets a
renderer-specific column definition and client-side interaction behavior.
HTML publishes linked plot pages under `plots/`; Dash uses a host-provided
route resolver. Neither renderer changes PDL into routes or private UI state.

## Historical execution

Historical source runs are a separate safety path, not a retroactive update to
production. `HistoricalRunRequest` stores an inclusive range and the pinned
source revision. The worker checks for the adapter's historical capability,
uses no current pointers, and stores output refs in the run result. It never
advances a production pointer or automatically releases a downstream profile.
See [Data and snapshots](subsystems/data-and-snapshots.md).
