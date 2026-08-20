# Python API reference

The pages below document supported user-facing modules. Private implementation
modules are intentionally omitted; their behavior is covered by the guides
and may change without notice.

## Core

```{eval-rst}
.. automodule:: runbook.core.data
   :members:
   :exclude-members: BlobStore, DatasetBinding, ReportProfile, ScheduleSpec,
                     SourceConfig, load_profiles, load_source_configs, open_blob_store

.. automodule:: runbook.core.keying
   :members: build_context_hash

.. automodule:: runbook.core.table
   :members: highlight, highlight_on_key, highlight_on_range, highlight_zscore,
             normalize_table_style, render_table_html, table_style_hash,
             table_style_json, table_style_payload

.. automodule:: runbook.core.plotting.line
   :members: plot_line
```

## Data and ingest

```{eval-rst}
.. automodule:: runbook.data
   :members:
   :no-index:

.. automodule:: runbook.data.config
   :members:
   :no-index:

.. automodule:: runbook.data.ingest
   :members:
   :no-index:

.. automodule:: runbook.data.ingest.adapters
   :members:

.. automodule:: runbook.data.ingest.parsers
   :members:
```

The extension protocols are described in {doc}`source-adapters-and-curation`.

## SDK

```{eval-rst}
.. automodule:: runbook.sdk.authoring
   :members: RequiredAliases, required_aliases, report

.. automodule:: runbook.sdk.client
   :members:

.. automodule:: runbook.sdk.context
   :members: Ctx

.. automodule:: runbook.sdk.execution
   :members: ReportResult, execute_report, load_report_module, resolve_code_version

.. automodule:: runbook.sdk.profiles
   :members: ReportProfile, load_profiles, resolve_report_path
   :no-index:

.. automodule:: runbook.sdk.ui
   :members: flex_grid, grid, manifest, plot, table, text
```

## Platform helpers

Runs are durable PostgreSQL records. The API returns `worker_id` and
`cancel_requested_at`; the dashboard derives its `cancelling` display state.
`POST
/api/v1/runs/{run_id}/cancel` returns HTTP 202 and changes queued runs to
`cancelled`; for running rows it only records cancellation intent. The API
never reaches into the polling runner's local process registry.

```{eval-rst}
.. automodule:: runbook.services.schedule
   :members: latest_due_slot

.. automodule:: runbook.worker.execution
   :members: execute_run, wait_for_claim
```

## Service entry points

```{eval-rst}
.. automodule:: runbook.services.app
   :members: create_app, version_payload

.. automodule:: runbook.services.cli
   :members: main

.. automodule:: runbook.services.db
   :members: async_engine, async_sessions, sync_engine, sync_sessions,
             tick_lock, upgrade_with_metadata
```
