# Core and PDL

## Purpose

`runbook-core` holds the shared semantic vocabulary. PDL is the versioned,
JSON-compatible manifest that carries report meaning and layout from SDK
execution to renderers.

## Owns

- `core/pdl/models.py`: `PDLManifest`, `PDLPage`, `PDLTableBlock`, plot/text/
  link blocks, semantic column metadata, warnings, and extensions.
- `core/pdl/spec.json` (`pdl-core/0.1`) and `spec-0.2.json` (linked content).
- Renderer-neutral table semantics in `core/table/models.py`, artifact refs,
  snapshots, and deterministic helpers.

## Does not own

PDL does not own data acquisition, layout authoring objects, database/queue
state, routes, navigation, credentials, Dash IDs/callbacks, `srcDoc`,
`postMessage`, or private vendor presentation.

## Start here

- `packages/runbook/runbook-core/src/runbook/core/pdl/models.py` — models and
  schema-version validation.
- `packages/runbook/runbook-core/src/runbook/core/pdl/spec.json` and
  `spec-0.2.json` — serialized contract.
- `packages/runbook/runbook-sdk/src/runbook/sdk/layout/compiler.py` — producer.

## Data/control flow

```{mermaid}
flowchart LR
    layout[SDK layout] --> compiler[compile_layout]
    compiler --> manifest[PDLManifest]
    manifest --> html[HTML]
    manifest --> dash[Dash]
    manifest --> extension[Public extension hooks]
```

## Public contracts

`PDLManifest` has a schema version, title, snapshot ID, `as_of`, page, optional
styles/artifacts/warnings, and semantic extensions. Pages contain typed blocks
with validated names and coordinates. A linked table or standalone link cannot
be declared under `pdl-core/0.1`; use `pdl-core/0.2`. Keep `extensions` as
declarative capability metadata, not executable callbacks or host state.

Table blocks point to immutable `data_ref`/`style_ref`/`html_ref` artifacts;
renderers read them rather than recomputing report logic. Schema changes must
update the matching JSON schema, producer, both renderers, and tests.

## Common modifications

To add a field, trace model → JSON schema/version → layout/compiler or builder
→ HTML → Dash → extension handling. To add a block, update the union and every
renderer dispatch path. If only a renderer needs a feature, keep it outside
PDL. See [Contracts](../04-contracts-and-boundaries.md).

## Consumers

`sdk/layout/compiler.py` produces manifests; `sdk/html.py` and
`sdk/extensions/dash/renderer.py` consume them. `worker/execution.py` persists
the resulting report outcome, and private hosts may consume the public Dash
extension seam.

## Tests

- `tests/core/pdl/test_link_block.py`
- `tests/core/pdl/test_table_block.py`
- `tests/sdk/test_layout.py`
- `tests/sdk/test_pdl_multipage.py`
- `tests/sdk/test_phasec_acceptance.py`

## Common mistakes

- Putting a Dash route, callback, or database connection into PDL.
- Changing `0.1` semantics instead of adding or selecting `0.2`.
- Updating HTML but not Dash (or vice versa).
- Treating PDL as a calculation cache rather than a manifest of named refs.

