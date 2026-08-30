# Start here

Runbook is a Python-native reporting platform. A source produces immutable
curated data; a report reads a pinned snapshot, calculates ordinary Python
objects, writes named artifacts, and compiles a renderer-neutral report
manifest (PDL). HTML and Dash render the same manifest. Services coordinate
durable work while a disposable worker executes one run.

```{mermaid}
flowchart LR
    source[Source] --> data[Curated dataset]
    data --> snapshot[Snapshot]
    snapshot --> calc[Python calculations]
    calc --> artifacts[Named artifacts]
    artifacts --> layout[Report / Section / Grid]
    layout --> pdl[PDL manifest]
    pdl --> html[HTML renderer]
    pdl --> dash[Dash renderer]
```

The practical rule is:

> Change the lowest shared layer that correctly owns the concept, then follow
> its consumers outward.

## Packages

| Package | Owns | Does not own | Start with |
| --- | --- | --- | --- |
| `runbook-core` | shared semantic contracts, PDL, snapshots, table semantics, deterministic helpers | Dash, workers, service orchestration, source acquisition | `packages/runbook/runbook-core/src/runbook/core/pdl/models.py`, `table/models.py` |
| `runbook-data` | source acquisition, parsers, immutable datasets/manifests, plus standalone pointer/snapshot helpers | report layout/rendering or service queue policy | `data/ingest/runner.py`, `data/manifests.py`, `data/pointers.py` |
| `runbook-sdk` | report authoring, calculation/artifact context, layout compilation, HTML and Dash rendering | durable scheduling, pointer ownership, private vendor code | `sdk/context.py`, `sdk/layout/compiler.py`, `sdk/execution.py` |
| `runbook-services` | PostgreSQL control plane, config revisions, production pointers/snapshots, queue/lifecycle, API and Operations UI | executing report/source code or owning PDL semantics | `services/repository.py`, `services/pointers.py`, `services/runner.py` |
| `runbook-worker` | composition root for one source/report run and subprocess-safe execution | queue policy, config ownership, production pointer policy | `worker/execution.py` |

Use the [system map](01-system-map.md) for the dependency direction and the
[change map](03-change-map.md) for a modification-specific route.

## One run, end to end

Normal source work is acquired and curated, then the service publishes pointer
updates. A profile run resolves pointers into a snapshot before dispatch; the
worker executes the report against that exact snapshot and writes report
artifacts and PDL. Historical source work uses the normal queue but separate
immutable outputs and never advances production pointers or releases profiles.

For current operational commands and environment settings, see
[Deployment](../deployment.md). For semantic details, continue to
[Runtime flows](02-runtime-flows.md).
