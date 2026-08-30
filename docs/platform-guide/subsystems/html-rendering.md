# HTML rendering

## Purpose

The HTML renderer is the compatibility baseline. It consumes a PDL manifest and
immutable artifact refs, producing a self-contained report bundle plus linked
plot pages where declared.

## Owns

- `sdk/html.py::render_html` and `render_html_bundle`.
- HTML traversal for text, tables, plots, semantic links, styles, warnings,
  and bundle publishing.
- `core.table.render_table_html` integration and deterministic plot page names.

## Does not own

HTML does not calculate report values, acquire data, resolve service routes, or
define shared PDL/table semantics. It does not need a Dash runtime.

## Start here

- `packages/runbook/runbook-sdk/src/runbook/sdk/html.py`
- `packages/runbook/runbook-sdk/src/runbook/sdk/execution.py`
- `tests/sdk/test_html_bundle.py`

## Data/control flow

```{mermaid}
flowchart LR
    pdl[PDLManifest] --> render[render_html]
    refs[Immutable artifact refs] --> render
    render --> main[Report HTML]
    render --> pages[Linked plot pages]
    render --> bundle[HTML bundle refs]
```

## Public contracts

Table blocks use `data_ref`, optional persisted style/HTML refs, and semantic
links. Plot refs resolve named persisted JSON; linked plot pages are published
under `plots/<name>.html`. Snapshot warnings render outside the author grid.
Unknown extensions must degrade safely while preserving complete content.

## Common modifications

For shared behavior start at core/PDL or the table resolver and update Dash
too. For HTML-only output, update traversal/publishing in `html.py` and the
bundle tests. Preserve escaping and deterministic names; missing artifact or
link targets should remain visible as an accessible error, not silently point
elsewhere.

## Consumers

`execute_report` invokes HTML bundle rendering, and service run results expose
the resulting artifact refs. Analysts and report hosts consume the published
HTML; Dash does not consume generated HTML.

## Tests

- `tests/sdk/test_html_bundle.py`
- `tests/sdk/test_standalone_link.py`
- `tests/sdk/test_snapshot_warnings.py`
- `tests/sdk/test_linked_table_report.py`

## Common mistakes

- Fixing HTML output while leaving the shared PDL/table contract wrong.
- Inferring artifact paths instead of reading refs from the manifest.
- Publishing every plot when only linked plots belong in the bundle.
- Escaping away semantic links or trusting raw DataFrame HTML.
