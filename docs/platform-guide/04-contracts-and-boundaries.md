# Contracts and boundaries

A contract change is deliberate when it changes serialized meaning, ownership,
or the call shape between packages. Identify its producer, all consumers, and
compatibility tests before editing.

| Contract | Represents | Producer | Consumers | Version/change rule |
| --- | --- | --- | --- | --- |
| `pdl-core/0.1`, `pdl-core/0.2` | renderer-neutral report title, page/block layout, artifact refs, semantic links and extensions | SDK layout/compiler and core PDL models | HTML renderer, SDK Dash renderer, host extensions | Add a compatible field only with consumer coverage; linked table/standalone links require `0.2`; preserve `0.1` for no-link manifests. |
| `table-style/0.1`, `table-style/0.2` | canonical formats, sizing, visibility, conditional rules, global style and semantic links | `TableStylePlan` and `resolve_table_style` | HTML, native Dash, AG Grid translation | `0.1` is legacy and rejects links; renderer-neutral semantics belong in core. |
| `SourceAdapter` / historical adapter | readiness and acquisition call shapes plus immutable acquisition results | `runbook-data` protocol and adapter registry | Stage 1 runner and worker | Preserve keyword-compatible methods; historical support is explicit and optional. |
| `Stage2Parser` | source-blind raw-byte to curated-frame call shape | parser registry | Stage 2 curation | Keep parser independent of source-specific transport; output aliases must match config. |
| dataset manifest | immutable files, hashes, watermarks, and provenance | data Stage 2 curation (`data/manifests.py`) | standalone `data/pointers.py` helpers and the service pointer registry | Never overwrite immutable refs; curation returns updates only after files/manifests are ready. |
| production pointer/snapshot | PostgreSQL current selection and the exact manifest/provenance set used by a production run | `services/pointers.py`, wired by `RunRepository.pointer_registry`; the production worker publishes after `finish_owned` | service runner release/pinning, worker normal-source publication, and SDK/report execution | Publication is source-owned by the service seam and compare-and-set guarded; historical runs never publish production pointers. |
| service/worker boundary | durable run state and one committed worker owner | services repository/runner | worker handshake and local backend | Worker only executes after claim and terminal writes require ownership; queue policy remains in services. |
| artifact refs | named reproducible tables, plots, files, PDL and HTML bundle outputs | SDK artifact registry/execution | renderers, service run results, clients | Keep names and refs stable within a report execution; do not infer object-store paths. |

## PDL must stay renderer-neutral

PDL models in `core/pdl/models.py` contain report meaning, layout, artifact
references, warnings, and semantic extensions. They intentionally exclude
routes, navigation, credentials, database connections, Dash component IDs,
callbacks, `srcDoc`, and `postMessage`. A Dash-only behavior belongs in the
Dash renderer or public extension contract; an Operations UI behavior belongs
in services.

## Public and private ownership

Public Runbook owns semantic report contracts, PDL, table semantics, rendering
and runtime extension contracts, and shared artifact behavior. Private
integration code may own firm/vendor adapters, private reports, branding/theme,
catalogue/navigation, and a trusted presentation extension. There is no private
COA implementation in this repository; treat it as an external downstream
integration.

If private code exists only because public Runbook lacked a capability, check
the current public seam before adding another private copy. Public extension
seams are `DashRendererExtension` and the adapter/parser protocols plus entry
point groups.

## Contract change checklist

1. Identify the owner and list every current consumer.
2. Decide whether the serialized schema/version remains compatible.
3. Keep shared semantics out of renderer-specific or private code.
4. Update focused producer, consumer, and parity tests.
5. Run the full checks and inspect generated PDL/artifact refs where relevant.

The detailed field lists remain in the [API reference](../api.md),
[interactive report guide](../pdl-interactive.md), and [source adapter
guide](../source-adapters-and-curation.md).
