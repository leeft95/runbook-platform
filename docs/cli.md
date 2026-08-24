# CLI reference

The workspace installs the report preview, service, and per-run worker
commands.

## `runbook-preview`

Render one report profile against the latest available dataset snapshot:

```text
runbook-preview PROFILE_ID [--profiles PATH] [--reports-root PATH]
                   [--store URI] [--database URL]
                   [--code-version VALUE] [--output PATH]
                   [--log-level LEVEL]

runbook-preview interactive PROFILE_ID [--profiles PATH] [--reports-root PATH]
                   [--store URI] [--database URL]
                   [--code-version VALUE] [--host HOST] [--port PORT]
                   [--demo-live] [--log-level LEVEL]
```

Defaults are `data/contract/report_profiles.json`, `reports`, and the
configured data/database URIs. `--output` writes the resulting HTML locally;
without it, the command prints the result metadata as JSON.

The `interactive` form is development-only. It builds the same canonical PDL,
composes its `DashPage` into one temporary host-owned Dash app, and binds to
`127.0.0.1:8051` unless changed. `--demo-live` injects the deterministic
in-memory SQLite provider used by the public PnL example. No service runner,
production routing, authentication, or durable interactive state is involved.

## `runbook-services`

The service command groups database, configuration, scheduling, and server
operations:

```text
runbook-services [--database URL] db upgrade
runbook-services [--database URL] config import [--source-config PATH]
                                      [--profiles PATH] [--reports-root PATH]
runbook-services [--database URL] config export --output-dir PATH
runbook-services [--database URL] tick [--now ISO] [--store URI]
                                      [--reports-root PATH]
                                      [--code-version VALUE] [--workers N]
runbook-services [--database URL] run [--store URI] [--reports-root PATH]
                                      [--code-version VALUE] [--workers N]
                                      [--poll-interval SECONDS]
runbook-services [--database URL] serve [--host HOST] [--port PORT]
                                      [--store URI] [--reports-root PATH]
                                      [--reload]
runbook-worker --run-id RUN_ID
```

`run` requires `--workers >= 1` and `--poll-interval > 0`; it runs until
SIGINT/SIGTERM and exits cleanly if another runner holds the advisory lock.
`tick` uses the same reconciliation cycle and exits once locally owned work is
idle. `--now` must be an ISO timestamp with a timezone. `--reload` is for local
development. Run `runbook-services COMMAND --help` for argparse's current
option descriptions.

The config-import `--reports-root` option is retained as a deprecated no-op for
v0.2.1 compatibility. Workers, rather than config import, validate report
aliases and module discovery.

`runbook-worker` accepts only a durable run ID; it loads its pinned
configuration and snapshot from PostgreSQL. The service never serializes
source-specific execution state into the worker command. `pixi run
test-postgres` runs the opt-in PostgreSQL release gate and requires
`RUNBOOK_TEST_DATABASE_URL` to name a disposable database.
