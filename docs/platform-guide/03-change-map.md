# Change map

Start with developer intent. The owner is the first row's **Start here**;
follow every consumer before changing a shared contract.

| If you need to change... | Start here | Follow through | Main contract | Key tests |
| --- | --- | --- | --- | --- |
| Table styling, formatting, rules, or links | `core/table/models.py`, `core/table/builder.py` | table artifact → PDL table → HTML + SDK Dash; AG Grid only for interactive output | `table-style/0.2` (legacy `0.1` remains no-link) and `TableArtifactRef` | `tests/core/table/test_generate.py`, `tests/sdk/test_table_style_sdk.py`, `tests/sdk/test_pdl_interactive.py`, `tests/sdk/test_dash_navigation.py` |
| Report layout | `sdk/layout/models.py`, `sdk/layout/builder.py` | `layout/compiler.py` → PDL coordinates → both renderers | layout node constraints and PDL page/grid | `tests/sdk/test_layout.py` |
| PDL model or field | `core/pdl/models.py` + `pdl/spec.json` / `spec-0.2.json` | SDK builder/compiler → HTML → Dash → extension handling | `pdl-core/0.1` or `pdl-core/0.2` schema | `tests/core/pdl/`, `tests/sdk/test_phasec_acceptance.py`, `tests/sdk/test_pdl_multipage.py` |
| HTML rendering or publishing | `sdk/html.py` | artifact reads → table/plot/link rendering → bundle refs | PDL/artifact refs and semantic links | `tests/sdk/test_html_bundle.py`, `tests/sdk/test_standalone_link.py` |
| Dash report output | `sdk/extensions/dash/renderer.py` | PDL → controls/callbacks → native table or AG Grid → route resolver | PDL interaction/extension semantics; `DashRendererExtension` | `tests/sdk/test_pdl_interactive.py`, `tests/sdk/test_dash_renderer_extensions.py`, `tests/sdk/test_dash_navigation.py` |
| Source acquisition | `worker/execution.py::_source`, `data/ingest/runner.py::run_stage1_acquire`, adapter contracts | adapter discovery → Stage 1 → raw artifact → Stage 2 parser | `SourceAdapter` / historical capability | `tests/data/test_generic_ingest.py`, `tests/data/test_historical_source_jobs.py` |
| Curation and manifests | `data/ingest/runners/stage2.py`, `data/manifests.py` | immutable files → manifest → worker result → `services/pointers.py` → production snapshot | dataset manifest and service-owned pointer/snapshot contract; `data/pointers.py` only for standalone ingestion/client flows | `tests/data/test_pointers.py`, `tests/data/test_generic_ingest.py`, `tests/sdk/test_client_workspace.py`, `tests/services/test_staggered_settlement.py` |
| Run lifecycle/cancellation | `services/repository.py`, `services/runner.py` | durable row → local backend → worker → reconciliation | `Run`, `RunView`, `ExecutionBackend` | `tests/services/test_service_lifecycle.py`, `test_cancellation.py`, `tests/services/test_addressable_runs.py` |
| Downstream profile release | `services/runner.py::_release_dependencies` | producer success → provenance/barrier → pinned profile snapshot → worker | producer run identity and `dependencies_released_at` | `tests/services/test_staggered_settlement.py`, `tests/services/test_service_lifecycle.py`, `tests/postgres/test_phaseb_e2e.py` |
| Worker execution | `worker/execution.py` | committed claim → config validation → `_source` or `_report` → guarded terminal write | ownership and `finish_owned` | `tests/services/test_worker_boundary.py`, `test_worker_execution.py`, `tests/services/test_addressable_runs.py` |
| Adapter/parser extension | `data/ingest/discovery.py`, adapter/parser registries | entry point → signature validation → runtime composition | `runbook.adapters`, `runbook.parsers`, `Stage2Parser` | `tests/data/test_phasee_external_plugins.py`, `tests/postgres/test_phasee_external_plugins.py` |

## Required change journeys

### Change table semantics

```{mermaid}
flowchart LR
    plan[TableStylePlan\nSTART HERE] --> resolver[resolve_table_style\nPUBLIC CONTRACT]
    resolver --> artifact[table artifact\nDO NOT DUPLICATE HERE]
    artifact --> pdl[PDLTableBlock\nPUBLIC CONTRACT]
    pdl --> html[HTML renderer]
    pdl --> dash[Dash renderer\nRENDERER-SPECIFIC]
    dash --> ag[AG Grid only when interactive opt-in]
```

Change the core plan/resolver when semantics change. Update the PDL table
contract if the persisted meaning changes, then test HTML and native Dash
parity. AG Grid may translate the resolved semantics, but must not become the
owner of a renderer-neutral option.

### Change standard roll-up calculations

Own shared statistics in `core/table/templates/rollup.py::_rollup_table`.
`rollup_table_fcst` supplies the timezone-normalized report date; Current Month
averages tomorrow through month-end and stays missing (`-`) at month-end.
Keep Latest, other averages and full companion plot inputs unchanged.
The optional Current Month z-score still uses whole-month averages.
Both `core.table` and `core.table.templates` export this forecast entry point;
`scripts/preview_gallery.py` and `scripts/preview_rollup_options.py` consume it.
The other shared caller, `rollup_table_hst`, also backs Reports' thin
`eu_power_rollup_table` wrapper and has no Current Month column. Do not duplicate
forecast calculations in Reports. See [table templates](../table-templates.md)
and `tests/core/table/test_rollup_template.py`, plus plot-link and SDK renderer
coverage in `test_predefined_plot_links.py` and `test_row_format_renderers.py`.

### Change seasonal chart dates and labels

Own seasonal defaults in `core/plotting/seasonal.py::plot_seasonal`.
`timeseries/transforms.py::ts_by_year` maps values and source-row identities
through the same seasonal slots. Original dates reach Graphly through
`PlotlyPlotDef.series_styles` as Plotly `customdata`, including forecast splits.
Do not reconstruct calendar years from season names. Shared axes keep month-only
labels; derived comparisons/cumulative traces use year-free seasonal hovers.
Explicit tick formats and hover templates take precedence. Follow native
wrappers in `plotting/templates.py`, `plot_seasonal_grid`, and table companion
plots; keep ordinary history axes unchanged. See [plotting helpers](../plotting-helpers.md)
and `tests/core/plotting/test_seasonal.py`, `test_datetime_ticks.py`, and
`test_report_plots.py` for coverage.

### Add a PDL field or block

Trace `core/pdl/models.py` → the matching JSON schema (`spec.json` or
`spec-0.2.json`) → SDK builder/compiler → `sdk/html.py` → SDK Dash renderer →
extension behavior and tests. Decide whether the field is schema-compatible;
linked content requires `pdl-core/0.2`. Keep routes, callback IDs, credentials,
and host configuration out of the manifest.

### Change layout behavior

Trace `Report`/`Section`/`Grid` in `sdk/layout/builder.py` → layout dataclasses
→ `compile_layout` → PDL coordinates → both renderers. Do not put HTML or Dash
coordinates into report helper functions or core models.

### Change an adapter or parser

Trace the protocol → entry-point discovery and signature checks → worker/data
composition → `AcquisitionResult`/`CuratedFrame` → immutable dataset and
snapshot. Built-in names are reserved; external names cannot shadow them.

### Change run lifecycle or historical behavior

Trace service repository state and runner cycle → worker backend/claim → worker
outcome → reconciliation/release. For historical source behavior, follow
`HistoricalRunRequest` → `HistoricalExecutionContext` separately; it never
publishes a production pointer or releases downstream reports.

### Change Dash controls or presentation

Trace declarative PDL extension semantics → public callback/runtime handling →
`DashRendererExtension` → private host presentation. Operations UI branding
(`OperationsBrand`) is a services seam, not a report renderer seam.

> **Worked example:** follow the [PDL parameter walkthrough](03a-pdl-parameter-walkthrough.md)
> for a junior-executable, repository-backed change journey through
> `table(width=...)`, from artifact registration to persisted PDL, HTML, Dash,
> AG Grid fallback, tests, and a golden report.
