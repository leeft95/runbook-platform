# Building source adapters and curators

For adapter and parser developers

An adapter acquires raw bytes; a Stage 2 parser turns those persisted bytes into
curated DataFrames. The [Data guide](data.md) is the analyst-facing view. For
deployment of private adapters, see [Deployment](deployment.md).

## Installed extensions

`runbook-data` discovers out-of-tree integrations from trusted installed
packages. Adapter names are looked up in the `runbook.adapters` entry-point
group and parser names in `runbook.parsers`; the built-in names `http`,
`local_file`, and `csv_timeseries_v1` are reserved and cannot be shadowed.
Lookup is exact, and duplicate installed names fail clearly.

The complete package layout and entry-point metadata appear in [Private
extension adapters](#private-extension-adapters). The examples there use a
small authenticated JSON source and its parser; replace the package and
identifiers with those owned by your installation.

Historical source runs are an explicit adapter opt-in. A dual-mode adapter
accepts an optional immutable `HistoricalExecutionContext` in both hooks. The
context is `None` for a normal run; the worker supplies it for a historical
run. Its `start_date` and `end_date` are inclusive. The worker checks this
capability before acquisition begins; a request can therefore enter the normal
durable queue before an unsupported adapter is rejected with a source-specific
error. The control plane does not inspect plugin composition because its
installed extensions may differ from the worker's. A historical-capable adapter
must read both dates and bound its vendor request to that inclusive window
rather than silently ignoring the context.

`PreviousAcquisitionState` contains a conceptual `watermark` and JSON-safe
`metadata`. Runbook transports and serializes the state; the adapter owns the
meaning of metadata keys. Prior partition values are materialized under the
generic `metadata["partition_values"]` mapping with sorted lists. The model is
immutable, including nested JSON values, and serializes with Pydantic's JSON
mode.

Entry points are executable Python code. Runbook loads only packages already
installed in the trusted runtime environment. The same metadata lookup runs
in every fresh worker subprocess, so an editable-only parent-process
registration is not sufficient.

`runbook-data` has two extension points for bringing a new source into the
platform:

| Extension | Stage | Responsibility |
| --- | --- | --- |
| Source adapter | Stage 1 | Check whether a source is ready and acquire its raw bytes. |
| Stage 2 parser | Stage 2 | Validate persisted raw bytes and turn them into curated data frames. |

Most integrations need a parser but not a new adapter. Use the built-in
`http` adapter when a file can be downloaded over HTTP, or `local_file` when
the source is already on disk. Add an adapter only when the source needs a new
transport or acquisition workflow, such as authentication, pagination, or a
database query.

Keep the boundary strict:

```text
source system -> adapter -> immutable raw artifact -> parser -> curated dataset
```

Adapters must not apply business transformations. Parsers must not call the
source system. The ingest runner owns raw persistence, content hashes,
Parquet revisions, manifests, and pointer publication.

## Write an ingester: the `SourceAdapter` contract

“Ingester” is informal shorthand here; `SourceAdapter` is the public API. The
adapter validates configuration, checks readiness without consuming the vendor
payload, and acquires the raw bytes. The runner then persists those bytes
immutably, calls the configured Stage 2 parser, writes curated files and a
manifest, and publishes the dataset pointer for a normal run. Historical runs
follow the same acquisition and curation path but do not publish the
production pointer.

An adapter implements the
[`SourceAdapter`](https://github.com/redcombojnr/runbook-platform/blob/main/packages/runbook/runbook-data/src/runbook/data/ingest/adapters/base/contracts.py)
protocol:

```python
class SourceAdapter(Protocol):
    def validate(self, source_config: SourceConfig) -> None: ...
    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
        previous_state: PreviousAcquisitionState | None = None,
    ) -> ReadinessResult: ...
    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_watermarks: Mapping[str, datetime] | None = None,
        previous_state: PreviousAcquisitionState | None = None,
    ) -> AcquisitionResult: ...
```

The contract's `Mapping` is `collections.abc.Mapping`. `previous_state` and
`previous_watermarks` are optional compatibility inputs for incremental
adapters; an adapter can ignore them when each acquisition is complete.

An adapter that opts into historical runs additionally implements the
`HistoricalSourceAdapter` capability. `SourceAdapter` is the standard
ordinary-run contract; `HistoricalSourceAdapter` is an additional
historical/backfill capability, not its replacement. Both are valid contracts.
The public historical protocol requires the context keyword for a historical
invocation:

```python
class HistoricalSourceAdapter(Protocol):
    """Optional source capability for inclusive date-range acquisitions."""

    def validate(self, source_config: SourceConfig) -> None: ...

    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
        previous_state: PreviousAcquisitionState | None = None,
        execution_context: HistoricalExecutionContext,
    ) -> ReadinessResult: ...

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_watermarks: Mapping[str, datetime] | None = None,
        previous_state: PreviousAcquisitionState | None = None,
        execution_context: HistoricalExecutionContext,
    ) -> AcquisitionResult: ...
```

A concrete dual-mode adapter can support both contracts by making the
historical context optional. `None` means an ordinary run; a populated context
means an inclusive historical/backfill run:

```python
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from runbook.data.config import SourceConfig
from runbook.data.ingest.models import (
    AcquisitionResult,
    HistoricalExecutionContext,
    PreviousAcquisitionState,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)


def _status_for_http_code(code: int) -> ReadinessStatus:
    if code < 400:
        return ReadinessStatus.ready
    if code == 404 or (400 <= code < 500 and code not in {401, 403}):
        return ReadinessStatus.not_ready
    return ReadinessStatus.failed


@dataclass
class AuthenticatedJsonAdapter:
    """Acquire a vendor JSON export using a bearer token."""

    session: Any | None = None

    def validate(self, source_config: SourceConfig) -> None:
        url = source_config.params.get("url")
        token_env = source_config.params.get("token_env")
        parsed = urlsplit(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("authenticated_json requires a valid params.url")
        if not isinstance(token_env, str) or not token_env:
            raise ValueError("authenticated_json requires params.token_env")

    def _url(
        self,
        source_config: SourceConfig,
        execution_context: HistoricalExecutionContext | None,
    ) -> str:
        self.validate(source_config)
        base_url = str(source_config.params["url"])
        if execution_context is None:
            return base_url
        parsed = urlsplit(base_url)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.extend(
            [
                ("start_date", execution_context.start_date.isoformat()),
                ("end_date", execution_context.end_date.isoformat()),
            ]
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))

    def _headers(self, source_config: SourceConfig) -> dict[str, str]:
        token_env = str(source_config.params["token_env"])
        token = os.environ.get(token_env)
        if not token:
            raise RuntimeError(f"source credential is not set: {token_env}")
        return {"Authorization": f"Bearer {token}"}

    def _session(self) -> Any:
        return self.session if self.session is not None else requests.Session()

    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
        previous_state: PreviousAcquisitionState | None = None,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> ReadinessResult:
        del previous_state
        url = self._url(source_config, execution_context)
        response = self._session().get(
            url,
            headers=self._headers(source_config),
            timeout=30,
            stream=True,
        )
        try:
            code = int(response.status_code)
            status = _status_for_http_code(code)
            return ReadinessResult(
                source_id=source_config.source_id,
                acquisition_run=acquisition_run,
                status=status,
                observed_at=observed_at,
                remote_filename="orders.json",
                remote_locator=url,
                message=None if status is ReadinessStatus.ready else f"HTTP readiness status {code}",
            )
        finally:
            response.close()

    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_watermarks: Mapping[str, datetime] | None = None,
        previous_state: PreviousAcquisitionState | None = None,
        execution_context: HistoricalExecutionContext | None = None,
    ) -> AcquisitionResult:
        del previous_watermarks, previous_state
        url = self._url(source_config, execution_context)
        response = self._session().get(
            url,
            headers=self._headers(source_config),
            timeout=60,
            stream=True,
        )
        try:
            response.raise_for_status()
            return AcquisitionResult(
                record=RawArtifactRecord(
                    source_id=source_config.source_id,
                    acquisition_run=readiness.acquisition_run,
                    source_filename=readiness.remote_filename or "orders.json",
                    source_locator=url,
                    fetched_at=fetched_at,
                    content_type=response.headers.get("content-type"),
                ),
                payload=response.content,
            )
        finally:
            response.close()
```

With `execution_context=None`, this implements the standard `SourceAdapter`
ordinary-run contract. With a populated context, it implements the additional
`HistoricalSourceAdapter` capability and sends both inclusive dates. The runner
supplies the context only for a historical invocation; it never passes a
historical context to the parser.

The methods have distinct jobs:

- `validate` fails fast when required configuration is absent or malformed.
  It runs while source configuration is loaded and again before acquisition.
- `check` performs a cheap, non-destructive readiness check. Return `ready`
  only when `acquire` can proceed, `not_ready` when expected data is not yet
  available, and `failed` for authentication, server, or protocol failures.
  It may inspect persisted `previous_state` metadata, but Stage 1A must not
  download or parse the vendor business payload. The runner passes state only
  to compatible signatures, so ordinary-keyword checks remain supported.
- `acquire` reads the source and returns its raw payload. It may interpret the
  adapter-owned metadata in `previous_state` for an incremental request.

Return response bytes unchanged from `acquire`; do not set `artifact_ref` or
`content_sha256`, because the runner adds those fields after persistence and
verification. Keep credentials out of configuration, metadata, locators,
exception messages, and logs. Store a credential environment-variable name,
not the credential itself.

## Write a parser: the `Stage2Parser` contract

The parser is the curator. It implements the
[`Stage2Parser`](https://github.com/redcombojnr/runbook-platform/blob/main/packages/runbook/runbook-data/src/runbook/data/ingest/parsers/base/contracts.py)
call signature and returns one `CuratedFrame` for every produced partition:

```python
def parse_source(
    *,
    source_config: SourceConfig,
    dataset_alias: str,
    acquired: AcquisitionResult,
) -> list[CuratedFrame]: ...
```

The Stage 2 runner calls this function after reading the persisted raw artifact
back from immutable storage. Parse only `acquired.payload`; do not reopen
`source_locator` or make network calls. The parser should make these properties
explicit:

This complete parser decodes an orders export, produces one deterministic
`CuratedFrame` per year, and supplies merge keys for the configured `append`
publication mode:

```python
from __future__ import annotations

import json

import pandas as pd
from runbook.data.config import SourceConfig
from runbook.data.ingest.models import AcquisitionResult, CuratedFrame


def parse_orders_json(
    *,
    source_config: SourceConfig,
    dataset_alias: str,
    acquired: AcquisitionResult,
) -> list[CuratedFrame]:
    """Parse and partition a persisted orders export."""
    del source_config
    try:
        records = json.loads(acquired.payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("orders_json_v1 payload is not valid JSON") from exc
    if not isinstance(records, list) or not records:
        raise ValueError("orders_json_v1 requires a non-empty JSON list")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("orders_json_v1 requires every item to be an object")

    frame = pd.DataFrame.from_records(records)
    required = {"order_id", "updated_at", "amount"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"orders_json_v1 fields are missing: {missing}")
    if frame["order_id"].isna().any():
        raise ValueError("orders_json_v1 contains an order without order_id")

    frame = frame.copy()
    frame["order_id"] = frame["order_id"].astype(str)
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    if frame["amount"].isna().any():
        raise ValueError("orders_json_v1 contains an invalid amount")
    frame["updated_at"] = pd.to_datetime(frame["updated_at"], utc=True, errors="coerce")
    if frame["updated_at"].isna().any():
        raise ValueError("orders_json_v1 contains an invalid updated_at")

    frame = (
        frame.sort_values(["updated_at", "order_id"], kind="mergesort")
        .drop_duplicates("order_id", keep="last")
        .reset_index(drop=True)
    )
    batch_watermark = frame["updated_at"].max().to_pydatetime()
    frame["year"] = frame["updated_at"].dt.year.astype(str)

    outputs: list[CuratedFrame] = []
    for year, partition_frame in frame.groupby("year", sort=True):
        curated = (
            partition_frame.drop(columns="year")
            .sort_values(["updated_at", "order_id"], kind="mergesort")
            .reset_index(drop=True)
        )
        outputs.append(
            CuratedFrame(
                output_alias=dataset_alias,
                frame=curated,
                watermark=batch_watermark,
                partition={"year": str(year)},
                merge_keys=("order_id",),
            )
        )
    return outputs
```

- `output_alias` must match a key in `source_config.datasets`. Every
  configured alias must be produced.
- `frame` is the curated `pandas.DataFrame`. Normalize types, row order, and
  duplicate handling so identical inputs produce identical output.
- `watermark` is a timezone-aware business-data watermark, not the ingest
  time. For a partitioned append batch, use the batch watermark on every
  returned frame because no frame may regress behind the current dataset
  watermark.
- `partition` has exactly the configured `partition_keys`, in configured
  order. Values become path segments and cannot be empty, `.`, `..`, or
  contain `/`, `\`, or `=`. Emit at most one frame for each partition.
- `merge_keys` identifies rows for `append` publication. The keys must exist
  in both old and incoming frames; incoming rows win when keys collide.

For `full` publication, emit every partition that belongs in the new complete
view; omitted old partitions are removed from the new manifest. For `append`,
unchanged old partitions are retained and matching partitions are merged.
Append parsers must provide merge keys, and their watermark cannot move
backwards.

The built-in `csv_timeseries_v1` parser is registered by `runbook-data`; new
parser identifiers should be versioned when a schema or parsing change would
alter the meaning of already-published data. External parsers are ordinary
callables declared in the `runbook.parsers` entry-point group; they do not need
a public registration function.

## Private extension adapters

The smallest coherent private package for the example above is:

```text
orders-adapter/
├── pyproject.toml
└── src/orders_adapter/
    ├── __init__.py
    ├── adapters.py
    └── parsers.py
```

The adapter entry point is a zero-argument factory or callable (usually a
class) that returns an object implementing `validate`, `check`, and `acquire`.
This package's complete metadata is:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "runbook-orders-adapter"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pandas", "requests", "runbook-data"]

[project.entry-points."runbook.adapters"]
authenticated_json = "orders_adapter.adapters:AuthenticatedJsonAdapter"

[project.entry-points."runbook.parsers"]
orders_json_v1 = "orders_adapter.parsers:parse_orders_json"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["orders_adapter*"]
```

`requests` and `pandas` are direct dependencies because the private package
imports them; depending on `runbook-data` supplies the Runbook contracts and
registries. Install this package into the service environment and every fresh
worker environment. Runbook discovers the zero-argument entry point in each
process; importing it only in a parent process is not enough. Built-in adapter
and parser names are reserved, and duplicate or incompatible entry points
fail explicitly during configuration loading.

The repository's external-plugin tests exercise this install boundary by
building a wheel and discovering it in a fresh subprocess. Their fixture
identifiers are test-only evidence, not production adapter or parser names.

## Private extension parsers

The package registers `orders_json_v1` in the separate `runbook.parsers` group;
the entry point in the `pyproject.toml` above points to the complete
`parse_orders_json` implementation shown in [Write a parser: the
`Stage2Parser` contract](#write-a-parser-the-stage2parser-contract). The
callable receives only the persisted `AcquisitionResult` bytes. It does not
open `source_locator`, call a network, or receive `HistoricalExecutionContext`:
that context stops at the adapter boundary. Install the parser package
wherever parsing can run, including every fresh worker process, and let
`runbook-data` report unsupported or incompatible entry points clearly.

## Configure the source and dataset

The adapter and parser are joined in `data/contract/source_configs.json`. The
following `orders_api` map is illustrative, not a checked-in source; use the
same fields with identifiers and parameters owned by your installed package:

```json
{
  "orders_api": {
    "adapter": "authenticated_json",
    "enabled": true,
    "schedule": {"cron": "15 * * * *", "timezone": "UTC"},
    "datasets": {
      "orders": {
        "dataset_id": "orders",
        "schema_version": "v1",
        "partition_keys": ["year"],
        "parser_id": "orders_json_v1",
        "update_mode": "append"
      }
    },
    "params": {
      "url": "https://example.invalid/api/orders/export",
      "token_env": "ORDERS_API_TOKEN"
    }
  }
}
```

The source map key becomes `source_id`. The dataset map key (`orders`) is the
alias passed to the parser. `dataset_id` is the stable published identity used
by the SDK and reports. A source may bind several aliases and parsers to the
same acquired raw artifact, but each `dataset_id` may have only one producer
in a source-config file.

`load_source_configs` validates adapter and parser registration as well as the
configuration shape, so load the complete file in tests rather than only
constructing models directly.

## Test the integration

Cover each boundary separately before adding an end-to-end ingest test:

1. Adapter validation rejects missing parameters without accessing the
   source.
2. Readiness maps available, absent, and failed responses correctly and does
   not consume the response body.
3. Acquisition returns exact raw bytes and never leaks credentials into its
   record.
4. Parser tests use a hand-built `AcquisitionResult` and assert validation,
   types, ordering, deduplication, partitions, merge keys, and watermark.
5. An ingest test uses a temporary blob store, runs two publications, and
   verifies append or full-refresh behavior through the SDK.

For the network adapter, inject a fake `Session` into
`AuthenticatedJsonAdapter(session=...)`. Its fake `Response` should record the
URL, headers, timeout, and `stream` flag, return a status/body, implement
`raise_for_status`, and record `close()`. Call `check` and `acquire` once with
`execution_context=None` and once with a bounded context; assert that the
ordinary URL is unchanged, the historical URL has the inclusive
`start_date`/`end_date` query, the bearer header is present, and every response
is closed. This tests both modes without contacting a vendor. The custom
network adapter is not vendor-smoke-tested by this repository.

For the parser, build an exact `AcquisitionResult` with a
`RawArtifactRecord` (`source_id`, `acquisition_run`, `source_filename`, and
timezone-aware `fetched_at`) and JSON bytes containing two years plus a
duplicate `order_id`. Pass it to `parse_orders_json` and assert one frame per
year, UTC `updated_at`, the later duplicate winning, the batch watermark, the
`{"year": "2025"}`-shaped partitions, and `merge_keys == ("order_id",)`. This proves
the parser's deterministic contract without a source locator or network call.

The existing
[`tests/data/test_generic_ingest.py`](https://github.com/redcombojnr/runbook-platform/blob/main/tests/data/test_generic_ingest.py)
shows parser and end-to-end examples. The external-package boundary is covered
by [`tests/data/test_phasee_external_plugins.py`](https://github.com/redcombojnr/runbook-platform/blob/main/tests/data/test_phasee_external_plugins.py).
Run the focused checks with:

```bash
pixi run test tests/data/test_generic_ingest.py
pixi run test tests/data/test_phasee_external_plugins.py
pixi run lint
pixi run format-check
pixi run typecheck
```

Before merging, also verify that a repeated ingest of identical bytes reuses
the existing curated revision and that a parser failure leaves the database
pointer unchanged.

## Review checklist

- The adapter only checks readiness and acquires raw bytes.
- The parser uses only persisted raw bytes and produces deterministic frames.
- Credentials and sensitive URL parameters never enter configuration, logs,
  metadata, or stored locators.
- Dataset aliases, partition keys, update mode, merge keys, and watermark
  semantics agree.
- Source and parser identifiers are registered and validated by the complete
  source-config load.
- Raw artifacts, curated files, and manifests remain immutable; only the
  dataset pointer advances after successful publication.
