# CLI reference

The SDK and service packages install two commands.

## `runbook-preview`

Render one report profile against the latest available dataset snapshot:

```text
runbook-preview PROFILE_ID [--profiles PATH] [--reports-root PATH]
                   [--store URI] [--database URL]
                   [--code-version VALUE] [--output PATH]
                   [--log-level LEVEL]
```

Defaults are `data/contract/report_profiles.json`, `reports`, and the
configured data/database URIs. `--output` writes the resulting HTML locally;
without it, the command prints the result metadata as JSON.

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
runbook-services [--database URL] serve [--host HOST] [--port PORT]
                                      [--store URI] [--reports-root PATH]
                                      [--reload]
```

`--now` must be an ISO timestamp with a timezone. `--reload` is for local
development. Run `runbook-services COMMAND --help` for argparse's current
option descriptions.
