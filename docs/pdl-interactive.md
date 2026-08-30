# Interactive reports

For report authors

An interactive report is the same Runbook report with extra interaction
instructions that the Dash renderer understands. Make the report a valid static
report first:

```text
snapshot -> Python report -> PDL -> HTML (always valid)
                           \-> Dash page (optional enhancement)
```

The default Dash representation of a PDL table is a native static Dash table,
which is the peer of the HTML table renderer. AG Grid is reserved for an
explicit interactive-table declaration (as in `reports/pnl_explorer.py`), not
silently selected for every table. The normal reporting path has no iframe,
`srcDoc`, or HTML-injection bridge.

PDL says what the report means; the Dash renderer says how controls and
callbacks are presented. Report code does not need Dash callback context,
component IDs, or callback decorators.

## Semantic tables

Table columns can describe dimensions, identifiers, time fields, measures,
aggregations, and formats. HTML uses that metadata for a static table; the Dash
renderer uses it to configure client-side sorting, filtering, grouping,
pivoting, and aggregation.

```python
from runbook.sdk import column, currency, date, percent

columns = [
    column("date", role="time", format=date()),
    column("book", role="dimension"),
    column("pnl", role="measure", aggregation="sum", format=currency("GBP")),
    column("return", role="measure", aggregation="avg", format=percent()),
]
```

The supported renderer-neutral formats are `number`, `currency`, `percent`,
`date`, and `datetime`. Core PDL does not contain AG Grid configuration or
JavaScript. The Dash renderer creates its own typed definitions and generated
formatters.

## Controls and interactions

The public `pdl-dash/0.1` extension provides `select`, `multi_select`,
`date_range`, and `toggle` controls. Options can be explicit or resolved from
the pinned snapshot with `dataset_values(alias=..., column=...)`. A handler is
a plain function registered by name:

```python
from runbook.sdk import report
from runbook.sdk.extensions.dash import dashboard, dataset_values, interaction, multi_select


@report.interaction("filter_dashboard")
def filter_dashboard(ctx, state):
    frame = ctx.calc("positions")
    books = state.get("book", [])
    if books:
        frame = frame[frame["book"].isin(books)]
    return {"positions": frame}
```

The report extension declares which controls feed the handler and which named
blocks receive its outputs. Handlers receive JSON-compatible state and return
strings, Plotly figures/payloads, or DataFrames for existing text, plot, and
table blocks. The renderer owns IDs, output conversion, and callback
registration.

See `reports/pnl_explorer.py` for a complete static-first example using
`dashboard(...)`, `multi_select(...)`, `select(...)`, `date_range(...)`, and an
interaction that updates summary, chart, and table blocks.

Table cell and header links are also semantic PDL metadata. Use the table link
helpers and generated plot names; do not author raw `<a>` tags in DataFrames.
HTML emits linked plot documents, while Dash resolves the same logical report
and plot destinations through the host-owned route resolver.

## Static fallback and live data

HTML ignores an unrecognised extension namespace but still renders the report's
text, plots, and tables. This is the compatibility baseline: an interactive
report must remain useful as static HTML.

Managed report data is snapshot-pinned. Optional live data is an injected
runtime capability, not a profile credential:

```python
source = ctx.live.sql("demo_pnl")
frame = source.query(
    "SELECT * FROM demo_live_pnl WHERE book = :book",
    {"book": "Alpha"},
)
```

The provider owns connections, credentials, and network details. If no provider
is injected, the capability is unavailable. Never put credentials, URLs,
Python functions, DataFrames, Dash objects, routes, or arbitrary JavaScript in
PDL or profile data.

## Embedding a Dash page

`render_dash_page(...)` returns an embeddable `DashPage`; it does not create a
root app. A private report host owns routes, navigation, and authentication:

```python
page = render_dash_page(
    manifest,
    definition,
    ctx,
    namespace="pnl-explorer",
)
app.layout = page.layout()
page.register_callbacks(app)
```

For plot destinations, the host can route `/plot/<name>` to
`page.plot_layout(name)` and route report destinations to its own report page
registry. This keeps navigation outside canonical PDL and lets multiple
namespaced pages share one Dash application.

Namespaces keep IDs distinct when a host mounts more than one report. The
development CLI can serve the same page:

```bash
runbook-preview interactive pnl_explorer_demo --demo-live \
  --host 127.0.0.1 --port 8051
```

This is a local preview process, not the Operations service. For trusted host
presentation customisation, see [Dash renderer extensions](dash-renderer-extensions.md)
and [Deployment](deployment.md).
