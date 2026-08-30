# Report authoring

## Purpose

The SDK lets report modules use ordinary Python for calculations and compose a
small layout tree. It records outputs as named artifacts and compiles layout to
PDL for rendering.

## Owns

- `sdk/authoring.py`: `report.calc`, `report.page`, and interaction decorators.
- `sdk/context.py`: `Ctx.dataset`, `Ctx.calc`, params, live resolution, and
  artifact context.
- `sdk/layout/builder.py`: `Report`, `Section`, `Grid`, `Row`, `Stack`, and
  block helpers (`table`, `plot`, `text`, `Link`).
- `sdk/layout/compiler.py`: validation, placement, and PDL lowering.

## Does not own

Report code does not acquire sources, mutate production pointers, schedule
runs, choose host routes, or add renderer-specific coordinates. Core helpers
return analytical objects; artifact APIs make outputs reproducible; layout
decides presentation.

## Start here

- `packages/runbook/runbook-sdk/src/runbook/sdk/context.py` (`Ctx`)
- `packages/runbook/runbook-sdk/src/runbook/sdk/authoring.py`
- `packages/runbook/runbook-sdk/src/runbook/sdk/layout/builder.py`
- `packages/runbook/runbook-sdk/src/runbook/sdk/layout/compiler.py`
- `reports/vol_report.py` and `reports/linked_table_report.py`

## Data/control flow

```{mermaid}
flowchart LR
    snapshot[Pinned Snapshot] --> ctx[Ctx.dataset / Ctx.calc]
    ctx --> artifact[ctx.artifact]
    artifact --> tree[Report / Section / Grid]
    tree --> compiler[compile_layout]
    compiler --> pdl[Renderer-neutral PDL]
```

## Public contracts

`Ctx` reads only the run's snapshot and names calculation/cache entries. Table,
plot, and file artifacts are named and persisted before layout references them.
Layout nodes enforce composition and span constraints; `compile_layout` emits
flat PDL page/block coordinates and validates names and bounds.

Interactions are declarative (`report.interaction`) and become PDL controls;
native Dash callbacks are not report authoring API. Standalone links and table
links use semantic destinations.

## Common modifications

Change calculations or artifact shape in the report module/context path. Change
placement in `layout/models.py`/`builder.py`, then verify compiler output. Add
a semantic report feature to core PDL only when both renderers can consume it;
otherwise use a renderer extension seam.

## Consumers

`sdk/execution.py` loads the report module, runs calculations, compiles layout,
and builds report artifacts. HTML and Dash consume the compiled PDL. Worker
execution supplies the pinned snapshot and report root.

## Tests

- `tests/sdk/test_execution_kiss.py`
- `tests/sdk/test_layout.py`
- `tests/sdk/test_pdl_interactive.py`, `test_pdl_multipage.py`
- `tests/sdk/test_standalone_link.py`, `test_linked_table_report.py`

## Common mistakes

- Putting layout coordinates in calculation helpers.
- Reading a pointer or source file directly instead of `Ctx.dataset`.
- Registering native Dash callbacks in report modules.
- Creating an artifact but not referencing it through layout/PDL.

