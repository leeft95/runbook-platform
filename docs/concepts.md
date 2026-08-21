# Architecture and core concepts

Runbook has four bounded stages:

1. **Acquisition** checks a source and persists its bytes as an immutable raw
   artifact.
2. **Curation** reparses those stored bytes into immutable Parquet revisions
   and a complete content-addressed manifest.
3. **Calculation** resolves a dataset snapshot and evaluates report
   calculations lazily, with immutable cache entries.
4. **Rendering** turns the canonical PDL page manifest and its artifacts into
   HTML or an optional interactive DashPage.

The service plane coordinates these stages, while the blob store retains
immutable data and artifacts.

## Snapshots

A snapshot is the exact set of manifest references selected for a report or
SDK read. Its identity is derived from canonical resolved inputs. Once a run
has a snapshot, later pointer changes do not change that run's inputs.

Analyst reads can resolve a historical snapshot with an `as_of` timestamp.
Scheduled report execution resolves the latest available pointer and then
pins it for the complete run.

## Manifests and pointers

A manifest describes a complete dataset view: selected files, their hashes,
partitions, raw lineage, watermark, publication time, and predecessor. A
PostgreSQL dataset pointer identifies the current manifest and watermark.
Pointers advance only after all immutable outputs are ready.

Blob storage has no mutable current-state lookup. Always resolve a snapshot
and read the files selected by that snapshot; reading a curated directory or
glob can combine current and superseded revisions.

## Reports are external templates

Report Python files live under a caller-selected `--reports-root` (the
repository example uses `reports/`). A profile binds report aliases to stable
dataset IDs and supplies parameters, layout, and a title. The SDK validates
that the report's declared aliases match the profile before execution.

The dependency direction is deliberately one way:

```text
core <- data <- sdk <- platform <- services
```

Source adapters and parsers belong in `runbook-data`; reports should remain
dataset-first and must not make network calls.

## PDL is the report product

PDL (the `pdl-core/0.1` manifest) is the renderer-neutral report contract.
It is plain JSON describing title, snapshot identity, page layout, semantic
blocks, artifact references, and generic extension namespaces. A report with a
Dash extension is still a complete static report first: HTML renders its text,
plot, and table without loading Dash, while an interactive renderer enhances
the same blocks.

PDL deliberately excludes application concerns. Routes, navigation, Dash
components and IDs, AG Grid `columnDefs`, Python functions, dataframes,
database connections, credentials, and live providers belong to the SDK,
renderer, host, or runtime boundary.
