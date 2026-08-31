# CLI reference

For operators and report authors

The command-line tools cover local preview, service setup, queueing, and the
per-run worker. Run `COMMAND --help` for parser-generated help.

## `runbook-preview`

Use this when developing or checking one report profile. It resolves the
latest dataset pointers, pins a snapshot, and writes static HTML:

```bash
runbook-preview PROFILE_ID --output preview/report.html
```

Linked plot pages, when present, are exported beside it under `plots/`.

Options:

```text
--profiles PATH       profile JSON (default data/contract/report_profiles.json)
--reports-root PATH   report modules (default reports)
--store URI           file: or s3:// data store
--database URL        PostgreSQL pointer registry
--code-version VALUE  recorded code identity (or RUNBOOK_CODE_VERSION)
--output PATH         copy generated HTML bundle locally
--log-level LEVEL     DEBUG, INFO, WARNING, or ERROR
```

Preview does not advance dataset pointers. Use the interactive development
preview when a profile enables its Dash extension:

For notebook exploration and an exact-pinned Python preview, see [Research with
the SDK in Jupyter](sdk-and-notebooks.md).

```bash
runbook-preview interactive pnl_explorer_demo --demo-live \
  --host 127.0.0.1 --port 8051
```

`interactive` additionally accepts `--host`, `--port`, and `--demo-live`.
It serves the current report and its linked plot pages in a temporary
host-owned Dash app on loopback. Cross-report navigation requires a reporting
host or portal; single-report preview does not support it. This is not the
Operations service and has no production authentication or durable interactive
state.

## `runbook-services`

All service commands accept the global `--database URL` before the subcommand.

### Initialize or upgrade the database

Use this before the first service start and before starting a new application
version:

```bash
runbook-services db upgrade
```

This applies PostgreSQL migrations. Import validated source/profile revisions:

```bash
runbook-services config import \
  --source-config data/contract/source_configs.json \
  --profiles data/contract/report_profiles.json
```

`config import` also accepts `--reports-root`; it is a retained deprecated
no-op for compatibility, not report validation. To export current revisions:

```bash
runbook-services config export --output-dir /tmp/runbook-config
```

### Run queued work

For a bounded/debugging cycle:

```bash
runbook-services tick --workers 1
```

For continuous operation:

```bash
runbook-services run --workers 4 --poll-interval 5
```

`tick` accepts `--now ISO`, `--store URI`, `--reports-root PATH`,
`--code-version VALUE`, and `--workers N`. `run` accepts `--store URI`,
`--reports-root PATH`, `--code-version VALUE`, `--workers N` (at least 1), and
`--poll-interval SECONDS` (greater than 0). PostgreSQL remains the durable
queue; excess work stays queued and same-source runs are serialized.

### Serve the API and Operations UI

```bash
runbook-services serve --host 127.0.0.1 --port 8050
```

`serve` accepts `--host`, `--port`, `--store`, `--reports-root`, and
`--reload`. `--reload` is for development only. The service exposes `/healthz`,
`/readyz`, `/api/v1`, and `/ui/`; it has no built-in authentication.

## `runbook-worker`

The runner normally launches this command itself. Use it when an external
scheduler must execute a particular durable run row:

```bash
runbook-worker --run-id RUN_ID
```

The normal execution form accepts `--run-id`. The worker reads its pinned config and
snapshot from PostgreSQL and gets `RUNBOOK_DATABASE_URL`,
`RUNBOOK_DATA_STORE_URI`, and `RUNBOOK_REPORTS_ROOT` from its environment.

To retry email delivery from an existing successful profile run without
rerunning report generation, use `--deliver-run-id RUN_ID`. Add `--force` only
for an intentional resend. See [post-publish email delivery](email-delivery.md).

## Environment defaults

```text
RUNBOOK_DATABASE_URL    PostgreSQL control plane
RUNBOOK_DATA_STORE_URI  file:.runbook unless overridden
RUNBOOK_REPORTS_ROOT    reports unless overridden
RUNBOOK_CODE_VERSION    required for report identity when Git metadata is absent
RUNBOOK_REPORTS_BASE_URL deployment-level dashboard host for email links
```

`file:` and `s3://` are the supported store forms. See [Deployment](deployment.md)
for production composition and [API](api.md) for route payloads.
