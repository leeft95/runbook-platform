# Testing and validation

Use the smallest focused test first, then the checks that cover every changed
boundary. The repository's `pixi.toml` tasks are authoritative; `pytest.ini`
excludes `tests/postgres` from the default suite.

## Standard checks

```bash
pixi run test
pixi run lint
pixi run format-check
pixi run typecheck
pixi run docs
```

For PostgreSQL lifecycle and real worker coverage, provide a local test
database and run:

```bash
RUNBOOK_TEST_DATABASE_URL=<local-test-database> pixi run test-postgres
```

`pre-commit run --all-files` is an optional final check when hooks are
available. `pixi run docs` is `sphinx-build -W --keep-going -b html docs
docs/_build/html`, so broken internal links, invalid directives, and warnings
fail the build.

## Modification matrix

| Change | Focused tests | Full validation |
| --- | --- | --- |
| Core model/schema | `tests/core/pdl/`, table model/spec tests | test + lint + typecheck + docs |
| Table style or links | `tests/core/table/test_generate.py`, `tests/sdk/test_table_style_sdk.py` | HTML/Dash parity tests + full suite |
| PDL/layout | `tests/sdk/test_layout.py`, `test_pdl_multipage.py`, `test_phasec_acceptance.py` | full suite + docs |
| HTML/Dash renderer | `tests/sdk/test_html_bundle.py`, `test_pdl_interactive.py`, `test_dash_renderer_extensions.py`, `test_dash_navigation.py` | full suite + lint/typecheck |
| Worker/services lifecycle | `tests/services/test_worker_boundary.py`, `test_service_lifecycle.py`, `test_cancellation.py`, `test_addressable_runs.py` | full suite + PostgreSQL suite |
| Downstream profile release | `tests/services/test_staggered_settlement.py`, `test_service_lifecycle.py`; `tests/postgres/test_phaseb_e2e.py` | full suite + PostgreSQL suite |
| Adapter/parser | `tests/data/test_generic_ingest.py`, `test_phasee_external_plugins.py` | relevant Postgres/external-plugin tests + full suite |
| Docs only | `pixi run docs` | docs + lint + format-check |

## Cold-start scenarios

### New renderer-neutral table formatting option

Owner: `TableStylePlan`/resolver in `runbook-core`; consumers: persisted table
artifact, `PDLTableBlock`, HTML, native Dash, and AG Grid translation where
interactive; contract: `table-style/0.2`; tests: core generation, SDK style,
HTML/Dash table tests. Add no renderer-specific copy.

### Downstream profile does not release

Owner: `runbook-services` `ServiceRunner._release_dependencies`; consumers:
durable source success rows, producer provenance/pointers, profile snapshots,
profile worker runs, and Operations UI; contract: producer run identity,
settled snapshot, and `dependencies_released_at`; tests:
`test_staggered_settlement.py`, service lifecycle tests, and PostgreSQL phase B
tests. The worker executes a released profile but is not the release authority.

## Golden examples

The checked-in reports are architecture regression examples rather than a
second API surface:

- `reports/vol_report.py` exercises table styling, plots, layout, and HTML/Dash
  parity (`tests/sdk/test_layout.py`).
- `reports/linked_table_report.py` exercises semantic table/plot links and
  linked-page publication (`tests/sdk/test_linked_table_report.py`,
  `test_dash_navigation.py`).
- `reports/pnl_explorer.py` exercises interactive controls and table output
  (`tests/sdk/test_phasec_acceptance.py`, `test_pdl_interactive.py`).
- `reports/market_dashboard.py` exercises layout and a renderer extension
  (`tests/sdk/test_layout.py`).
- `reports/snapshot_report.py` covers snapshot-driven report execution.

Private COA/ETF reports are not in this repository; validate those as a
downstream integration against the public contracts.

