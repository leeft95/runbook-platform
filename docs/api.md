# API reference

For integrators

The service API is FastAPI under `/api/v1`. Configuration and run responses
include revisions, hashes, status, and durable provenance. The service has no
authentication; put it behind the deployment's authenticated boundary.

## Health and version routes

| Method and route | Request | Response |
| --- | --- | --- |
| `GET /` | none | `{ "ui_version": "..." }` |
| `GET /healthz` | none | `{ "status": "ok" }` |
| `GET /readyz` | none | `{ "status": "ready" }`; `503` when PostgreSQL is unavailable |

## Configuration routes

| Method and route | Request | Response |
| --- | --- | --- |
| `GET /api/v1/sources` | none | list of latest source `ConfigView` objects |
| `GET /api/v1/sources/{source_id}` | none | one `ConfigView`; `404` if unknown |
| `PUT /api/v1/sources/{source_id}` | `{"config": {...}, "expected_revision": 3}` | saved `ConfigView`; `409` on revision conflict, `422` on invalid config |
| `GET /api/v1/profiles` | none | list of latest profile `ConfigView` objects |
| `GET /api/v1/profiles/{profile_id}` | none | one `ConfigView`; `404` if unknown |
| `PUT /api/v1/profiles/{profile_id}` | same `ConfigWrite` body | saved `ConfigView`; `409`/`422` as above |

`ConfigView` contains `kind`, `config_id`, `revision`, `config_hash`, the
validated `config` object, and `created_at`. Configuration writes create a new
revision; `expected_revision` is optional but recommended for optimistic
concurrency.

## Queue routes

| Method and route | Request body | Behavior |
| --- | --- | --- |
| `POST /api/v1/sources/{source_id}/runs` | optional `slot` (timezone-aware ISO datetime) and `force` boolean | queues a manual source run, returns `202 RunView` |
| `POST /api/v1/profiles/{profile_id}/runs` | same optional `RunRequest` | queues a manual profile run, returns `202 RunView` |
| `POST /api/v1/sources/{source_id}/historical-runs` | required inclusive ISO `start_date` and `end_date` only | queues a historical source run, returns `202 RunView` |
| `POST /api/v1/runs/{run_id}/cancel` | none | records durable cancellation intent, returns `202 RunView` |

For example:

```bash
curl -X POST http://127.0.0.1:8050/api/v1/sources/prices/historical-runs \
  -H 'content-type: application/json' \
  -d '{"start_date":"2026-01-01","end_date":"2026-01-31"}'
```

Historical requests pin the persisted source revision/hash, use the ordinary
queue, and never update the production pointer or automatically trigger
reports. Adapter capability is checked by the worker, so an unsupported source
may be queued before it fails clearly. There are no arbitrary temporary source
parameter overrides.

## Run routes and payload

| Method and route | Query/body | Response |
| --- | --- | --- |
| `GET /api/v1/runs` | optional `kind`, `target_id`, `status`, `limit` (1–500; default 100) | recent `RunView` list |
| `GET /api/v1/runs/{run_id}` | none | one `RunView`; `404` if unknown |

`RunView` includes `run_id`, `kind` (`source` or `profile`), `target_id`,
`mode` (`normal` or `historical`), inclusive `start_date`/`end_date` when
historical, `slot`, `trigger`, `force`, `config_revision`, `config_hash`,
`status`, optional `worker_id` and `cancel_requested_at`, `snapshot_id`,
`context_hash`, `code_version`, report artifact IDs/references, `result`,
failure `reason`, and requested/started/finished/updated timestamps.

For a successful historical source run, `result.datasets` maps dataset IDs to
immutable manifest refs and `result.pointer_updates` records output watermark
and publication timestamps. Copy those refs from the Operations run drawer;
clients should not infer object-store paths.

## Python API

The following autodoc sections expose supported modules. Private modules are
intentionally omitted.

For analyst-facing client, Snapshot, and workspace examples, see [Research
with the SDK in Jupyter](sdk-and-notebooks.md).

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
             table_style_json, table_style_payload,
             table_with_linked_plots_monthly

.. automodule:: runbook.core.plotting.line
   :members: plot_line

.. automodule:: runbook.core.plotting.bar
   :members: plot_bar, plot_bar_forecast

.. automodule:: runbook.core.plotting.mixed
   :members: plot_mixed

.. automodule:: runbook.core.plotting.seasonal
   :members: plot_seasonal, plot_cot
```

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

.. automodule:: runbook.sdk.extensions.dash.renderer
   :members: render_dash_page

.. automodule:: runbook.sdk.extensions.dash.renderer_extensions
   :members: DashRendererExtension
```

```{eval-rst}
.. automodule:: runbook.services.schedule
   :members: latest_due_slot

.. automodule:: runbook.worker.execution
   :members: execute_run, wait_for_claim

.. automodule:: runbook.services.app
   :members: create_app, version_payload

.. automodule:: runbook.services.cli
   :members: main

.. automodule:: runbook.services.db
   :members: async_engine, async_sessions, sync_engine, sync_sessions,
             tick_lock, upgrade_with_metadata
```

Historical adapter context and `OperationsBrand` composition are explained in
[source adapters](source-adapters-and-curation.md) and [Deployment](deployment.md).
