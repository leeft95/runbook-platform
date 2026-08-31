# Platform Modification Guide

For developers changing Runbook itself

This is the short path from a platform change request to the owning contract,
its consumers, and the checks that protect it. Read only the pages involved in
your change; this guide is not an API reference or a class catalogue.

## Use the guide in this order

1. Read [Start here](00-start-here.md) for the vocabulary and package map.
2. Use the [system map](01-system-map.md) and [change map](03-change-map.md)
   to find the owning layer.
3. Read [Contracts and boundaries](04-contracts-and-boundaries.md) before
   editing a shared model or seam.
4. Open the relevant [subsystem guide](subsystems/core-and-pdl.md).
5. Run the focused checks in [Testing and validation](05-testing-and-validation.md),
   then the required full checks.
6. Use the [debugging playbook](06-debugging-playbook.md) when behavior is
   already wrong.

## Common journeys

| Need to change | Start here | Then follow |
| --- | --- | --- |
| Table styling or links | [Table system](subsystems/table-system.md) | [Contracts](04-contracts-and-boundaries.md) → HTML and Dash tests |
| Report layout | [Report authoring](subsystems/report-authoring.md) | layout model → compiler → PDL → renderers |
| PDL field or block | [Core and PDL](subsystems/core-and-pdl.md) | schema/version → SDK builder → both renderers |
| HTML output | [HTML rendering](subsystems/html-rendering.md) | PDL/artifact contracts → HTML tests |
| Dash controls or interactions | [Dash rendering](subsystems/dash-rendering.md) | public extension contract → Dash tests |
| Source acquisition or curation | [Data and snapshots](subsystems/data-and-snapshots.md) | [Adapters and extensions](subsystems/adapters-and-extensions.md) → data tests |
| Run lifecycle or release | [Services and control plane](subsystems/services-and-control-plane.md) | [Worker execution](subsystems/worker-execution.md) → service/Postgres tests |
| Worker behavior | [Worker execution](subsystems/worker-execution.md) | service boundary → worker tests |
| New adapter/parser | [Adapters and extensions](subsystems/adapters-and-extensions.md) | discovery → runtime composition → integration tests |

## Existing authoritative docs

The guide explains safe modification paths. Link to the existing docs for
usage and deployment detail: [architecture](../architecture/north-star.md),
[API](../api.md), [operations](../operations.md), [deployment](../deployment.md),
[source adapters](../source-adapters-and-curation.md), [Dash extensions](../dash-renderer-extensions.md),
[layout authoring](../maintaining-layout-authoring.md), [reports](../reports.md),
and [table templates](../table-templates.md).

```{toctree}
:maxdepth: 2
:caption: Guide pages

00-start-here
01-system-map
02-runtime-flows
03-change-map
03a-pdl-parameter-walkthrough
04-contracts-and-boundaries
05-testing-and-validation
06-debugging-playbook
subsystems/core-and-pdl
subsystems/table-system
subsystems/report-authoring
subsystems/html-rendering
subsystems/dash-rendering
subsystems/data-and-snapshots
subsystems/services-and-control-plane
subsystems/worker-execution
subsystems/adapters-and-extensions
```
