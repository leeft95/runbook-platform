# Runbook

Runbook is a deterministic PDL-first data-to-report framework. It resolves
curated, immutable datasets into snapshot-pinned calculations and one
canonical report manifest that can render to HTML or an optional interactive
DashPage.

The documentation is organized around the work you need to do:

```{toctree}
:maxdepth: 2
:caption: Learn and build

getting-started
concepts
reports
pdl-interactive
data
source-adapters-and-curation
operations
architecture/north-star
repository-lineage
```

```{toctree}
:maxdepth: 2
:caption: Reference

cli
api
contributing
```

## The short version

Runbook separates source acquisition, data curation, report calculation, and
HTML rendering:

```text
source -> immutable raw artifact -> curated dataset -> snapshot -> report -> PDL -> HTML / DashPage
```

Reports read a resolved snapshot. They do not call source systems or choose
files directly. This makes a report run reproducible from its dataset
snapshot, report configuration, and code version.

## Build the documentation locally

With Pixi installed, build the site with warnings as errors:

```bash
pixi run docs
```

Preview the built site at <http://127.0.0.1:8765/>:

```bash
pixi run docs-serve
```

Alternatively, from a fresh Python 3.11 environment, install the documentation
dependencies and editable Runbook packages before running Sphinx directly:

```bash
python -m pip install -r docs/requirements.txt
python -m pip install -e packages/runbook/runbook-core \
  -e packages/runbook/runbook-data \
  -e packages/runbook/runbook-sdk \
  -e packages/runbook/runbook-services \
  -e packages/runbook/runbook-worker
sphinx-build -W --keep-going -b html docs docs/_build/html
```

The generated site is in `docs/_build/html/`. The same command runs in CI
for pull requests and is published to
<https://redcombojnr.github.io/runbook-platform/> from `main`.

## Packages

The repository is a small dependency chain:

```text
runbook-core -> runbook-data / runbook-sdk / runbook-services
runbook-sdk -> runbook-data
runbook-worker -> runbook-core / runbook-data / runbook-sdk / runbook-services
```

Use the package APIs documented in the reference section rather than relying
on private modules. The repository's [README](https://github.com/redcombojnr/runbook-platform/blob/main/README.md)
and [security policy](https://github.com/redcombojnr/runbook-platform/blob/main/SECURITY.md)
cover project-wide setup and reporting security issues.
