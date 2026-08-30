# Debugging playbook

Start with the durable identity (run ID, snapshot ID, manifest ref, artifact
ref, or PDL schema) and trace toward the owner. Keep the first failing layer
in focus; a renderer symptom is often a data, artifact, or contract problem.

| Symptom | Trace first | Likely owner and next check |
| --- | --- | --- |
| Report values are wrong | production pointer/snapshot → calculation cache → artifact | `services/pointers.py` for production pinning (`data/manifests.py` only for standalone flows), then `sdk/context.py` and report code; do not start in HTML/Dash. |
| HTML wrong but Dash correct | PDL/table artifact → `sdk/html.py` | Compare shared refs and `render_table_html`; then inspect HTML bundle publishing. |
| HTML and Dash tables are both wrong | `TableStylePlan` → `resolve_table_style` → `PDLTableBlock` | Fix core semantics and run core plus both renderer tests. |
| Layout overlaps or blocks disappear | layout builder → `sdk/layout/compiler.py` → PDL rows/columns | Read compiler validation and `tests/sdk/test_layout.py`; do not add renderer offsets. |
| PDL field/block missing | model/schema → builder/compiler → renderer dispatch | Check `pdl/spec*.json`, schema version, HTML, Dash, and extension handling. |
| Run never starts | queue row → `eligible_queued_runs` → claim → local backend | Check service DB/store settings, runner lock/capacity, then worker claim handshake. |
| Run is stuck running | worker ownership → logs → poll/reconciliation | `services/runner.py` owns reconciliation; an orphan becomes failed/cancelled with an ownership-lost reason. |
| Downstream profile does not release | successful normal source → pointer/provenance → settled snapshot → release marker | Inspect `_release_dependencies`, producer generations, config revision/hash, and `dependencies_released_at`. Historical rows are intentionally excluded. |
| Source data is missing | adapter discovery → readiness/acquisition → raw ref → parser → manifest | Check `SourceAdapter`, `Stage2Parser`, persisted raw digest, partition/append predecessor, then pointer publication. |
| Historical source fails | run mode/date range → adapter capability | The worker requires explicit historical `check`/`acquire` context support; `local_file` is not historical-capable. |
| Dash control does not react | PDL interaction declarations → IDs/bindings → callback registration | Check `sdk/extensions/dash/renderer.py` and `DashRendererExtension`; keep host routes outside PDL. |
| Links work in HTML but not Dash | semantic link destination → route resolver | HTML uses `plots/<name>.html`; Dash needs the host `RouteResolver` for report/plot destinations. |

## Durable evidence to preserve

For service failures capture the run ID, status/reason, config revision/hash,
snapshot/context identity, worker ID, output refs, and bounded logs from the
Operations run drawer. For data failures preserve source run ID, raw artifact
digest, manifest ref, pointer state, and parser/partition error. Never repair a
missing immutable object by guessing a path or deleting a revision.

## Boundary checks

If a proposed fix imports a higher-level package into core/data, adds a route
to PDL, or makes a report author publish pointers, stop and return to the
[system map](01-system-map.md) and [contracts](04-contracts-and-boundaries.md).
The smallest safe fix changes the owner and updates its consumers/tests.
