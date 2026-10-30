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

Table links are part of the renderer-neutral table contract. Use
`runbook.sdk.table_style.link_column`, `link_header`, and `link_index_header`
to declare report, URL, or generated-plot destinations; use
`TableLink(area="index", field=<row-label>, ...)` for a displayed row label.
Links are not raw HTML stored in DataFrames. HTML publishes linked plot pages,
while a host-owned Dash route resolver handles the same logical destinations.

### Bloomberg saved searches

`bsrch` uses the legacy core package's `ExcelGetGridRequest` with a `Domain`
and `BIKEY` override, returning a DataFrame with Bloomberg's column titles.
Pass the saved search key explicitly:

```python
from runbook.core.bloomberg import bbg

result = bbg.bsrch("IPD:DEX", bikey="your-saved-search-key")

# Reuse the same started synchronous blpapi.Session used for bdh/bref/etc.
result = bbg.bsrch("IPD:DEX", bikey="your-saved-search-key", session=session)
```

An omitted session uses the standard local Bloomberg connection and closes it
after the request. A supplied session is neither started nor stopped by this
helper; its authentication and lifecycle remain with the caller. The request
opens `//blp/exrsvc`, uses its own event queue, combines partial responses and
retains column names for empty results. Response waits use a 30-second timeout.
The migrated helper does not embed the old handler's host, application identity
or default saved-search key.

### Bloomberg live data

`bstream()` opens a dedicated Bloomberg streaming connection and closes it on
leaving the `with` block, including after an exception or an early loop exit:

```python
from runbook.core.bloomberg import bbg

with bbg.bstream() as live:
    subscriptions = {"EURUSD Curncy": {"fields": ["BID", "ASK"]}}
    status = live.subscribe(subscriptions, timeout=5)
    if any(result is not True for result in status.values()):
        raise RuntimeError(f"Subscription rejected: {status}")

    for update in live.events(timeout=30):
        print(update["correlationIds"], update["element"])
        break  # Remove this to keep consuming live updates.

    # Replace fields/options for the existing ticker correlation ID.
    status = live.resubscribe(
        {"EURUSD Curncy": {"fields": ["BID", "ASK", "LAST_PRICE"]}}, timeout=5
    )
    if any(result is not True for result in status.values()):
        raise RuntimeError(f"Resubscription rejected: {status}")
    live.unsubscribe({"EURUSD Curncy": {}}, timeout=5)
```

The yielded object is the installed `blp.BlpStream`, backed by `blpapi`.
`subscribe` and `resubscribe` return a dictionary keyed by correlation ID:
`True` for success, `False` for failure, or a list of invalid fields. Tickers
are the default correlation IDs. Subscription entries also accept `options`,
for example `{"interval": 1.0}`. Pass `host` and `port` to `bstream` for a
different Bloomberg connection (defaults: `localhost:8194`).

Events are raw message dictionaries, including `correlationIds`, `messageType`,
`timeReceived` and `element`. Field updates are incremental; maintain the latest
values per ticker if you need a complete quote. All timeouts above are in
seconds and raise `queue.Empty`; an idle market can therefore end this example
after 30 seconds. Omitting the event timeout waits indefinitely. Connection and
subscription status diagnostics are logged by `blp`, rather than yielded by
the data iterator. Consume events promptly: the underlying queue is unbounded.
This helper owns its session and does not reuse a historical-query session.

For a downstream service, `bsubscribe(ticker, field)` accepts a string or list
for each argument and subscribes once. Keep its context open across polling
cycles:

```python
def poll_bloomberg(tickers, fields, stop_event, handle_update):
    with bbg.bsubscribe(tickers, fields) as feed:
        while not stop_event.is_set():
            for update in feed.poll(max_events=1000):
                handle_update(update)
            stop_event.wait(0.1)
```

`bsubscribe` restricts requested fields to `BID`, `ASK`, and `LAST_PRICE`.
Discover these through `list(bbg.BloombergSubscriptionField)` and pass either
enum members or their exact uppercase strings. This is the helper's supported
quote-field subset, not the complete Bloomberg catalogue. Unsupported names,
comma-separated strings, and malformed inputs raise `ValueError` before any
connection opens; repeated fields are requested once. `PX_LAST` is rejected
with a hint to use `LAST_PRICE` for streaming, consistent with Bloomberg's
[Core Developer Guide](https://data.bloomberglp.com/professional/sites/10/2017/03/BLPAPI-Core-Developer-Guide.pdf).
Extending the supported set requires updating the enum after verifying a live
field. Allowed fields may still be unavailable for a ticker or entitlement;
Bloomberg's subscription acknowledgements remain authoritative and any field
rejection fails startup. The low-level `bstream` retains its native field API.

`poll()` returns up to `max_events` raw messages in arrival order without
waiting for new data. An idle poll returns `[]`; later polls continue to work.
It consumes updates once, preserves incremental fields and timestamps, and
leaves excess queued messages for the next call. Use one polling consumer per
feed and keep up with incoming traffic; this does not bound the underlying
queue or persist messages for replay. Application processing failures require
application-owned recovery.

The `timeout` argument to `bsubscribe` bounds each subscription acknowledgement
wait in seconds (default 5). Failed securities, rejected fields, or missing
status entries fail context entry; acknowledgement timeout raises `TimeoutError`.
An internally created session closes on exit, including startup rejection and consumer exceptions;
polling after exit raises `RuntimeError`. `options`, `host`, and `port` are
forwarded to the subscription/connection. The downstream service owns scheduling
and shutdown. An empty batch does not prove connection health: ongoing session
and subscription status diagnostics still use `blp` logging.

To reuse a caller-owned, already started **synchronous** `blpapi.Session`:

```python
with bbg.bsubscribe(["EURUSD Curncy"], ["BID", "ASK"], session=session) as feed:
    updates = feed.poll()  # Call repeatedly from your service loop.
# session is still running; only this context's subscriptions were cancelled.
```

The supplied session must be exclusively available to this feed until context
exit: no other event consumer, outstanding request, or subscription may share
its event stream. Authentication, start and stop remain caller-owned; `host`
and `port` are ignored. Each subscription gets a unique internal correlation
ID, mapped back to ticker names in returned updates. Updates received during
startup are retained for polling. `timeout` bounds the total acknowledgement
wait in this mode. Rejection, timeout, or a consumer exception cancels the
helper's subscriptions without stopping the session. Asynchronous sessions
with an existing callback are not supported by this path.

Borrowed-session polling uses `tryNextEvent()` and also processes subscription
status: rejection/termination raises `RuntimeError`, and connection-down or
session-terminated messages raise `ConnectionError`. A poll processes at most
1,000 native events as well as respecting its message batch limit.

#### Streaming OHLC bars

Pass `bar_size` in minutes to subscribe to `//blp/mktbar`. Market bars require
`LAST_PRICE` and an integer interval from 1 to 1,440 minutes. These are
trade-based bars. The same `poll()` API works with an owned session or a passed
started synchronous session:

```python
with bbg.bsubscribe(
    ["IBM US Equity"], "LAST_PRICE", bar_size=5, session=session
) as feed:
    for update in feed.poll():  # Repeat on each downstream service cycle.
        ticker = update["correlationIds"][0]
        kind = update["messageType"]
        payload = update["element"][kind]
        handle_bar_event(ticker, kind, payload)
```

Omit `session` to create an automatically managed connection. Returned
correlation IDs remain the original tickers, even though the subscription
topics are fully qualified market-bar topics. `options` may contain
`start_time` and `end_time` (Bloomberg `hh:mm` strings). Set the interval through
the `bar_size` argument, not the `options` dictionary.

The raw payload follows [Appendix A.4 of Bloomberg's Developer Guide](https://data.bloomberglp.com/professional/sites/4/blpapi-developers-guide-2.54.pdf#page=198):

| Message type | Handling |
| --- | --- |
| `MarketBarStart` | Initialize the bar, including `OPEN`, `HIGH`, `LOW`, `CLOSE`, volume, and timestamps. |
| `MarketBarUpdate` | Merge changed fields into the current bar. |
| `MarketBarIntervalEnd` | Finalize the accumulated bar; this timestamp marker is not an OHLC snapshot. |
| `MarketBarEnd` | Marks the end of the subscription's configured bar window. |

All four event types reach `poll()` in both session modes. Accumulating OHLC
state by ticker and `DATE_TIME` belongs to the consumer. A new subscription
does not backfill earlier bars or guarantee an immediate initial bar.
The low-level `bstream(service="//blp/mktbar")` also preserves all four types;
its callers must provide fully qualified market-bar topics themselves.

Bloomberg's [Session developer reference](https://bloomberg.github.io/blpapi-docs/python/3.26.9/_autosummary/blpapi.Session.html)
distinguishes synchronous event polling from asynchronous callbacks. `BlpStream`
uses callbacks and a queue; the default owned-session path polls that queue through `events(timeout=0)`
instead of calling `Session.nextEvent()` on an asynchronous session.

```{eval-rst}
.. automodule:: runbook.core.data
   :members:
   :exclude-members: BlobStore, DatasetBinding, ReportProfile, ScheduleSpec,
                     SourceConfig, load_profiles, load_source_configs, open_blob_store

.. automodule:: runbook.core.keying
   :members: build_context_hash

.. automodule:: runbook.core.bloomberg.bbg
   :members: BBGReturnTypes, IntradayEventType, bdh, bref, bdib, bbulkref, bql, bsrch, bstream, bsubscribe, BloombergSubscription, BloombergSubscriptionField

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
   :members: plot_seasonal, plot_cot, plot_seasonal_grid

.. automodule:: runbook.core.plotting.cot
   :members: plot_cot_market

.. automodule:: runbook.core.plotting.regression
   :members: plot_regression, plot_price_vs_position

.. automodule:: runbook.core.plotting.templates
   :members:

.. automodule:: runbook.core.table.templates.reports
   :members:

.. automodule:: runbook.core.cot
   :members:

.. automodule:: runbook.core.table.templates.rollup
   :members: rollup_table_hst, rollup_table_fcst

.. automodule:: runbook.core.table.templates.periods
   :members:

.. automodule:: runbook.core.timeseries.rollup
   :members: calendar_moving_average

.. automodule:: runbook.core.timeseries.range_vol
   :members:
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
