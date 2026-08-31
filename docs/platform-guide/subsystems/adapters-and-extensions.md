# Adapters and extensions

## Purpose

Runbook exposes narrow public seams for source acquisition/parsing and report
Dash presentation. Private integrations implement those seams in their own
packages and runtime; this repository contains no private vendor or COA code.

## Owns

- `SourceAdapter` and optional `HistoricalSourceAdapter` protocols in
  `data/ingest/adapters/base/contracts.py`.
- `Stage2Parser` in `data/ingest/parsers/base/contracts.py`.
- Entry-point discovery and compatibility checks in
  `data/ingest/discovery.py`, `adapters/__init__.py`, and `parsers/__init__.py`.
- Public `DashRendererExtension` in
  `sdk/extensions/dash/renderer_extensions.py`.

## Does not own

An adapter does not publish pointers or orchestrate reports; a parser does not
know transport details. A renderer extension does not own PDL traversal, public
IDs, callback semantics, host routing, authentication, or Operations branding.

## Start here

- `packages/runbook/runbook-data/src/runbook/data/ingest/adapters/base/contracts.py`
- `packages/runbook/runbook-data/src/runbook/data/ingest/parsers/base/contracts.py`
- `packages/runbook/runbook-data/src/runbook/data/ingest/discovery.py`
- `packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer_extensions.py`
- `docs/source-adapters-and-curation.md`, `docs/dash-renderer-extensions.md`
- [Email delivery integrator guide](../../email-delivery-integrator-guide.md)

## Data/control flow

```{mermaid}
flowchart LR
    config[Source config] --> discover[Entry-point discovery]
    discover --> adapter[SourceAdapter]
    adapter --> acquire[AcquisitionResult]
    acquire --> parser[Stage2Parser]
    parser --> dataset[Curated dataset]
    pdl[PDL + Dash host] --> extension[DashRendererExtension]
```

## Public contracts

Adapter factories are zero-argument entry points in `runbook.adapters`; built-in
`http` and `local_file` names are reserved. `validate`, `check`, and `acquire`
must accept the public keyword contract and previous state/watermarks. An
adapter is historical-capable only when both stage-1 methods explicitly accept
`HistoricalExecutionContext`.

Parser callables are entry points in `runbook.parsers`, must accept
`source_config`, `dataset_alias`, and `acquired`, and return configured
`CuratedFrame` values. Duplicate or incompatible names fail clearly; external
entry points cannot shadow built-ins.

`DashRendererExtension` can wrap page/control/block output and provide trusted
custom control bindings. Keep private components and vendor routes in the host
composition root; pass only declarative manifest/runtime values through the
public seam.

## Common modifications

For an adapter, implement the protocol in a private package, register an entry
point, and test fresh-process discovery. For a parser, preserve source-blind
deterministic output and partition/merge requirements. For report presentation,
use `DashRendererExtension`; do not fork the renderer or add private fields to
PDL. For Operations UI branding, use `OperationsBrand` in services instead.
For email delivery, implement a private sender package and register the
`runbook.email_senders` entry point; transport settings remain deployment-owned.

## Consumers

Stage 1/2 data runners and worker execution consume adapters/parsers. SDK Dash
rendering consumes the renderer extension; private hosts consume the rendered
page and own routes/assets.

## Tests

- `tests/data/test_generic_ingest.py`
- `tests/data/test_phasee_external_plugins.py`
- `tests/data/test_historical_source_jobs.py`
- `tests/postgres/test_phasee_external_plugins.py`
- `tests/sdk/test_dash_renderer_extensions.py`
- `tests/sdk/test_live.py`

## Common mistakes

- Registering an adapter that only accepts positional/private arguments.
- Treating parser code as an adapter or reading source-specific HTTP state in
  Stage 2.
- Shadowing built-in entry-point names.
- Adding vendor routes, credentials, or private components to PDL.
