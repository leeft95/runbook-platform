# Runbook

```{image} _static/RunbookLogo_transparent.png
:alt: Runbook logo
:width: 420px
:align: center
```

Runbook is a Python-native reporting platform that turns curated data into
reproducible static and interactive reports. You write ordinary Python for
calculations, tables, and plots; Runbook records the exact data used, stores
the outputs, and renders the report as HTML or Dash.

## Follow the analyst journey

```text
choose data -> calculate -> create artifacts -> compose a report -> preview
       -> understand snapshots -> operate source/report runs
```

Read in this order if Runbook is new to you:

```{toctree}
:maxdepth: 2
:caption: Learn and build

getting-started
sdk-and-notebooks
concepts
reports
composable-report-layouts
plotting-helpers
table-templates
data
operations
pdl-interactive
```

The [first report](getting-started.md) is the best starting point. After
authoring, follow [Data](data.md) and [Operations](operations.md) to understand
snapshots and runs, then [Interactive reports](pdl-interactive.md) when you
need controls. Deployment, renderer extensions, adapter development, API, CLI,
and architecture are advanced/reference material.

## Cookbook

Use the [Reports cookbook](reports.md#reports-cookbook) for composed plotting
and monthly-table recipes, the [ingestion cookbook](source-adapters-and-curation.md#write-an-ingester-the-sourceadapter-contract)
for adapter/parser and private-extension contracts, and the [Operations
guide](operations.md#general-usage) for everyday UI work and failure
diagnosis. The focused [Plotting helpers](plotting-helpers.md) and [Table
templates](table-templates.md) pages remain the API details behind those
recipes.

```{toctree}
:maxdepth: 2
:caption: Reference

deployment
dash-renderer-extensions
source-adapters-and-curation
architecture/north-star
maintaining-layout-authoring
repository-lineage
cli
api
contributing
```

## The platform model

```text
source -> curated dataset -> snapshot -> Python report -> PDL -> HTML / Dash
```

A source produces a curated dataset. A snapshot freezes the exact dataset
versions for one report run. Python report code creates calculations and
artifacts, and the renderer turns the resulting standard report definition
into HTML or an interactive Dash page.

## Build and preview the docs

With Pixi installed:

```bash
pixi run docs
pixi run docs-serve
```

The generated site is `docs/_build/html/`. The build uses warnings as errors.
The repository also has `pixi run test`, `pixi run lint`,
`pixi run format-check`, and `pixi run typecheck` tasks.

## Package boundaries

```text
runbook-core -> runbook-data / runbook-sdk / runbook-services
runbook-sdk  -> runbook-data
runbook-worker -> runbook-core / runbook-data / runbook-sdk / runbook-services
```

Use the public APIs in the guides and [API reference](api.md). The
[repository README](https://github.com/leeft95/runbook-platform/blob/main/README.md)
and [security policy](https://github.com/leeft95/runbook-platform/blob/main/SECURITY.md)
cover project-wide setup and reporting security issues.
