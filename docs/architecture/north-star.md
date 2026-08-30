# Platform architecture north star

For platform maintainers

Runbook separates report meaning from report presentation. Python report code
reads a pinned snapshot and creates a standard PDL manifest; renderers turn
that manifest into HTML or Dash. The service coordinates durable source/report
runs while workers perform the work. See [Deployment](../deployment.md) for
how these components are installed.

```text
source -> raw artifact -> curated dataset -> current pointer
                                      -> snapshot -> report code -> PDL
                                                               -> HTML table / plot pages
                                                               -> native Dash page / routes
```

## Package boundaries

```text
runbook-core       contracts, identities, snapshots, PDL, analyst helpers
runbook-data       acquisition, curation, manifests, pointers, datasets
runbook-sdk        report execution, caching, layout, PDL, HTML, Dash renderer
runbook-services   PostgreSQL control plane, queue, API, Operations UI
runbook-worker     one-process-per-run source and report execution
```

The dependency direction is intentionally one way: `runbook-data` depends on
core, `runbook-sdk` depends on core/data, services depends on core, and the
worker composes all four packages.

Reports are external templates selected by profile. They cannot acquire
sources or publish dataset pointers. PDL contains report meaning, layout,
artifact references, and semantic extensions; it excludes routes, navigation,
credentials, database connections, Dash IDs, and callbacks.

## Durable control plane

PostgreSQL is authoritative for configuration revisions, current dataset
pointers, queued/running/terminal runs, outcomes, and identities. The shared
blob store holds immutable raw and curated products, manifests, report
artifacts, calculation caches, and log chunks.

`runbook-services serve` owns the API and UI. `runbook-services run` holds one
advisory lock, schedules due sources, observes cancellation, reconciles local
worker ownership, releases ready profile dependencies, and dispatches queued
work. Each admitted run is one short-lived `runbook-worker` process. Capacity
is bounded before spawn and FIFO applies among eligible work. A runner restart
does not adopt old PIDs; unowned running rows are marked failed/cancelled with
an ownership-lost reason.

The bounded `tick` command uses one cycle for debugging or an external
scheduler. It is not a general workflow engine. Multi-source profile release
waits for each producer to advance from its automatic baseline; manual runs
pin latest pointers and persist a warning when they bypass that barrier.

## Data and report boundaries

Stage 1 checks/acquires raw bytes. Stage 2 reparses persisted bytes into
deterministic curated frames and commits a pointer only after all immutable
outputs are ready. Stage 3 resolves a snapshot and caches named calculations.
Stage 4 compiles `Report`/`Section`/`Grid`/`Row`/`Stack` to flat PDL and renders it. Historical
source runs use the ordinary queue but produce separate immutable outputs and
never advance production pointers.

Layout state is an SDK concern. Renderers receive compiled PDL, never layout
objects. The static HTML renderer is the compatibility baseline; the Dash
renderer consumes the same manifest and returns a host-embeddable namespaced
page. Ordinary tables are static HTML or native static Dash; AG Grid is an
explicit interactive opt-in. Semantic table links and deterministic generated
plot names are shared by both renderers. The report host owns Dash routes and
authentication. Optional live providers are injected at runtime and are not
serialized into profiles or PDL. The normal reporting path has no iframe,
`srcDoc`, or `postMessage` bridge.

## Guardrails

- pin runs to immutable snapshots and record code/config identity;
- keep PostgreSQL authoritative and workers disposable;
- keep credentials and source-specific logic outside PDL;
- reject missing append predecessors rather than guessing;
- preserve immutable data and manifests when recovering a failure; and
- use the smallest polling control plane that meets the operational need.
