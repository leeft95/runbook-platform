# Table system

## Purpose

The table system turns a DataFrame and a canonical style plan into deterministic
semantics that all report renderers can consume. Links are declarations, never
raw HTML embedded in a DataFrame.

## Owns

- `TableStylePlan`, formats, sizing, visibility, rules/conditions/targets, and
  `TableLink` models in `core/table/models.py`.
- `normalize_table_style`, `resolve_table_style`, and `render_table_html` in
  `core/table/builder.py`.
- SDK style/link helpers in `sdk/table_style.py` and table artifact creation.
- Dash translation: native static tables by default and AG Grid only when a
  table is explicitly interactive in `sdk/extensions/dash/renderer.py` and
  `tables.py`.

## Does not own

The table layer does not own report layout, source data acquisition, routes, or
AG Grid as a shared semantic contract. AG Grid options stay in the Dash
renderer; Operations UI AG Grid in `runbook-services` is a separate subsystem.

## Start here

- `packages/runbook/runbook-core/src/runbook/core/table/models.py`
  (`TableStylePlan`, `ResolvedTableStyle`, link contracts).
- `packages/runbook/runbook-core/src/runbook/core/table/builder.py`
  (`resolve_table_style`, `render_table_html`).
- `packages/runbook/runbook-sdk/src/runbook/sdk/extensions/dash/renderer.py`
  (`_build_native_table`, `_build_ag_grid`).

## Data/control flow

```{mermaid}
flowchart TB
    plan[TableStylePlan] --> resolve[resolve_table_style]
    frame[DataFrame] --> resolve
    resolve --> artifact[Table artifact refs]
    artifact --> pdl[PDLTableBlock]
    pdl --> html[render_table_html / HTML]
    pdl --> native[Dash native static table]
    pdl --> ag[Dash AG Grid opt-in]
```

## Public contracts

`table-style/0.2` is the current schema. Legacy `table-style/0.1` remains
valid for no-link payloads and rejects links. Formats include number, percent,
date, and string; rules target all/columns/rows and resolve against the
concrete frame. `ResolvedTableStyle` is the renderer-neutral result: visible
fields/rows, CSS, formats, sizing, and semantic cell/header/index links.

`TableArtifactRef` carries immutable data/style/HTML refs into `PDLTableBlock`.
Report/URL/plot links are resolved semantically: HTML uses `/report/<id>`, a
URL, or `plots/<name>.html`; Dash uses the host route resolver. Shared links
and formatting must remain parity-safe across renderers.

## Common modifications

For a new renderer-neutral option, change the core model/resolver, persist it
through the table artifact/PDL path, then update HTML/native Dash/AG Grid
consumers as applicable. For a Dash-only behavior, change the Dash translation
without adding it to `TableStylePlan`. For linked tables, use schema `0.2` and
test generated plot names and host navigation.

## Consumers

SDK artifact APIs produce table refs; PDL compiler carries them; HTML and SDK
Dash consume them. Golden reports include `reports/vol_report.py` and
`reports/linked_table_report.py`.

## Tests

- `tests/core/table/test_generate.py` and `test_spec_json.py`
- `tests/core/table/test_predefined_helpers.py`, `test_predefined_plot_links.py`
- `tests/sdk/test_table_style_sdk.py`
- `tests/sdk/test_pdl_interactive.py`
- `tests/sdk/test_dash_navigation.py`, `test_linked_table_report.py`

## Common mistakes

- Implementing a shared style option only in AG Grid.
- Storing `<a>` tags in DataFrames instead of declaring `TableLink`.
- Forgetting that `0.1` cannot carry links.
- Assuming native Dash tables are AG Grid; interactivity is explicit opt-in.

