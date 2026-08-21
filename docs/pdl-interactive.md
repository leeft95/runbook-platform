# Interactive PDL reports

PDL is the canonical semantic report product. A report author writes ordinary
Python that produces one `pdl-core/0.1` JSON manifest. The manifest is useful
without an interactive runtime and can be rendered by multiple consumers:

```text
snapshot -> report code -> canonical PDL
                              |-> portable HTML
                              |-> optional pdl-dash/0.1 DashPage
                                      |-> standalone preview
                                      |-> host-owned multi-page app
```

## Semantic tables

`PDLTableBlock.columns` is optional. With no explicit columns, the SDK infers
roles from the physical Arrow schema: strings, dictionaries, and booleans are
dimensions; integers, floats, and decimals are measures with `sum`; dates and
timestamps are time fields with date/datetime formats. No name heuristic is
used. Explicit `column(...)` metadata overrides inference and rejects unknown
physical fields or duplicate declarations.

The supported renderer-neutral formats are `number`, `currency`, `percent`,
`date`, and `datetime`. They describe intent, not framework configuration.
There are no AG Grid names in core PDL.

## HTML fallback and AG Grid

HTML ignores extension namespaces it does not implement. A report with
`extensions.dash` still renders its summary, Plotly artifact, and static
Parquet-backed table as complete HTML. This is the required static-first
baseline.

The interactive renderer translates PDL semantics into AG Grid definitions.
Dimensions, identifiers, and time fields are groupable and pivotable; measures
are value-enabled with their declared aggregation. Numeric, date, and text
filters and typed display formatters are renderer-owned. Sorting, filtering,
column resize/reorder/visibility, grouping, pivoting, and aggregation happen
inside AG Grid on the client, without server callbacks or arbitrary
JavaScript supplied by a report.

## Controls and interactions

The SDK exposes a deliberately small `pdl-dash/0.1` extension:

- `select`, `multi_select`, `date_range`, and `toggle` controls;
- explicit options or `dataset_values(alias=..., column=...)` resolved from
  the pinned snapshot; and
- `interaction(handler=..., inputs=[...], outputs=[...])` declarations.

Report code registers a plain function with `@report.interaction(name)`. The
function receives `ctx` and JSON-compatible state. It returns output values
for existing PDL blocks: strings for text, Plotly figures/payloads for plots,
and dataframes for tables. The renderer owns component IDs and conversion.
It validates unique controls, known inputs/outputs, registered handlers,
duplicate output ownership, and the supported extension version before Dash
starts.

## Embedding and multipage composition

`render_dash_page(manifest, definition, ctx, namespace=...)` returns a
`DashPage`:

```python
page = render_dash_page(manifest, definition, ctx, namespace="pnl-explorer")
app.layout = page.layout()
page.register_callbacks(app)
```

The renderer never creates or owns the root app. A central `DashIds` helper
turns local names into namespaced IDs such as
`pdl-pnl-explorer-block-summary` and `pdl-pnl-explorer-control-book`. A host
can mount multiple pages in one app, even when their local PDL names overlap.
Routes, navigation, authentication, and page registration remain host-owned
and are absent from PDL.

The preview CLI uses this same contract. It is explicitly development-only,
defaults to `127.0.0.1`, and has no production lifecycle, session, or service
runner integration.

## Live capability boundary

Managed report data is immutable and snapshot-pinned. Optional live data is an
injected SDK protocol:

```python
source = ctx.live.sql("demo_pnl")
frame = source.query(
    "SELECT * FROM demo_live_pnl WHERE book = :book",
    {"book": "Alpha"},
)
```

The logical name is the report-facing contract. A runtime provider owns the
connection, credentials, and network details. If no provider is injected,
access fails with a capability-unavailable error. The public deterministic
SQLite provider demonstrates real parameter binding and records only safe
provenance: logical provider, query time/duration, query hash, and parameter
keys/types. It does not persist results, secrets, URLs, or audit rows.

## Security and stop line

Never put credentials, connection URLs, Python functions, dataframes, Dash
objects, routes, navigation, or arbitrary JavaScript in PDL or profile data.
Keep local preview on loopback and do not present it as authenticated hosting.

Production interactive hosting, stable public routes, authentication,
authorization, multi-user isolation, persisted dashboard state, durable live
query audit records, real external database integrations, and ServiceRunner
managed app lifecycle are Phase D work.
