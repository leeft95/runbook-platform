# Core concepts

For report authors

Runbook separates data collection from report authoring. The vocabulary below
lets an analyst follow a dataset from its source to a published report:

```text
source -> source run -> curated dataset -> current pointer -> snapshot
                                                            -> report run
```

## The words you need

**Source** — where raw data comes from: a file, HTTP endpoint, or a private
provider such as Bloomberg. A source configuration says how to acquire and
parse it. Bloomberg is not bundled with Runbook; any Bloomberg option in a
deployment represents a private or external adapter.

**Source run** — one execution of a source. It checks/acquires raw bytes,
curates them, and may publish a new dataset version.

**Curated dataset** — cleaned, structured data produced by a successful source
run and ready for a report. Reports use the stable `dataset_id`, not a source
file path.

**Dataset pointer** — Runbook's current reference to the production version of
a dataset. It advances only after immutable files and a complete manifest are
ready.

**Snapshot** — a frozen list of exact dataset manifest references for one read
or report run. If prices change tomorrow, a report made today still points to
the same snapshot.

**Profile** — saved report configuration: the report module, its dataset alias
bindings, parameters, layout options, and enabled state.

**Calculation** — a named Python function registered with `@report.calc`.
Runbook evaluates it lazily once per report run and can reuse its immutable
cache entry.

**Artifact** — a stored report output such as a Plotly figure or a pandas table.
`ctx.artifact.plot(...)` and `ctx.artifact.table(...)` return references that a
layout can place.

**Report** — the page an analyst composes from text, tables, and plots. A
`Section` names a part of the page and a `Grid` places blocks side by side.

**PDL** — Runbook's standard description of a finished report. It records the
meaning, layout, snapshot, and artifact references without tying them to one
renderer. Most authors never need to construct PDL directly.

**Renderer** — the component that turns PDL into a presentation. Runbook ships
static HTML and an optional interactive Dash renderer.

**Run** — one execution of a source or report. The Operations UI records its
status, timing, inputs, outputs, provenance, and logs.

## A practical example

Suppose a private market adapter fetches prices at 09:00:

1. The source run stores raw bytes and produces `market_prices`.
2. The dataset pointer identifies the newly published manifest.
3. A 09:05 profile run resolves that pointer into a snapshot.
4. A calculation reads the snapshot with `ctx.dataset("prices")`.
5. Report code writes a table and Plotly figure as artifacts and composes a
   `Report`.
6. PDL records the report; HTML or Dash renders it.

The 09:05 report remains reproducible even after the pointer moves at 10:00.
Historical source runs create separate immutable outputs and do not move the
production pointer; see [Data](data.md) and [Operations](operations.md).

## What crosses each boundary

```text
data source       raw bytes and source provenance
curation          immutable Parquet files and a complete manifest
snapshot          exact dataset references for this run
report code       calculations and artifact creation
PDL               renderer-neutral report meaning and layout
HTML / Dash       the final static or interactive presentation
```

Reports never acquire sources or choose files directly. This keeps an ordinary
report portable and makes the data behind it inspectable.

For the implementation detail behind layout compilation, see
[Composable report layouts](composable-report-layouts.md). For the lower-level
PDL escape hatch, see [Reports](reports.md).
