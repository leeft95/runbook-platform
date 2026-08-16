# Building source adapters and curators

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

## Build a source adapter

An adapter implements the
[`SourceAdapter`](../packages/runbook/runbook-data/src/runbook/data/ingest/adapters/base/contracts.py)
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
    ) -> ReadinessResult: ...
    def acquire(
        self,
        *,
        source_config: SourceConfig,
        readiness: ReadinessResult,
        fetched_at: datetime,
        previous_watermarks: Mapping[str, datetime] | None = None,
    ) -> AcquisitionResult: ...
```

The methods have distinct jobs:

- `validate` fails fast when required configuration is absent or malformed.
  It runs while source configuration is loaded and again before acquisition.
- `check` performs a cheap, non-destructive readiness check. Return `ready`
  only when `acquire` can proceed, `not_ready` when expected data is not yet
  available, and `failed` for authentication, server, or protocol failures.
- `acquire` reads the source and returns its raw payload. It may use
  `previous_watermarks` for an incremental source request, keyed by dataset
  alias.

For example, an authenticated JSON download could be implemented in
`ingest/adapters/authenticated_json.py`:

```python
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from runbook.data.config import SourceConfig
from runbook.data.ingest.models import (
    AcquisitionResult,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)


@dataclass
class AuthenticatedJsonAdapter:
    session: Any | None = None

    def validate(self, source_config: SourceConfig) -> None:
        for key in ("url", "token_env"):
            value = source_config.params.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"authenticated_json requires params.{key}")

    def _headers(self, source_config: SourceConfig) -> dict[str, str]:
        token_env = source_config.params["token_env"]
        token = os.environ.get(token_env)
        if not token:
            raise RuntimeError(f"source credential is not set: {token_env}")
        return {"Authorization": f"Bearer {token}"}

    def check(
        self,
        *,
        source_config: SourceConfig,
        acquisition_run: str,
        observed_at: datetime,
    ) -> ReadinessResult:
        self.validate(source_config)
        url = source_config.params["url"]
        response = (self.session or requests.Session()).get(
            url,
            headers=self._headers(source_config),
            timeout=30,
            stream=True,
        )
        try:
            status = (
                ReadinessStatus.ready
                if response.status_code < 400
                else ReadinessStatus.not_ready
                if response.status_code == 404
                else ReadinessStatus.failed
            )
            return ReadinessResult(
                source_id=source_config.source_id,
                acquisition_run=acquisition_run,
                status=status,
                observed_at=observed_at,
                remote_filename="orders.json",
                remote_locator=url,
                message=None if status is ReadinessStatus.ready else "export is unavailable",
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
    ) -> AcquisitionResult:
        del previous_watermarks  # This source always returns a complete export.
        url = source_config.params["url"]
        response = (self.session or requests.Session()).get(
            url,
            headers=self._headers(source_config),
            timeout=60,
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

Return the response bytes unchanged. Do not set `artifact_ref` or
`content_sha256`; the runner fills those fields after it has persisted and
verified the payload.

Configuration, metadata, locators, exception messages, and logs must not
contain credentials. Store the name of a credential environment variable in
source configuration, as above, rather than the credential itself. Strip
sensitive URL query parameters before storing or logging a locator.

### Register the adapter

Adapters are currently registered in
[`ingest/adapters/__init__.py`](../packages/runbook/runbook-data/src/runbook/data/ingest/adapters/__init__.py).
Import the implementation and add its stable identifier to `_ADAPTERS`:

```python
from runbook.data.ingest.adapters.authenticated_json import (
    AuthenticatedJsonAdapter,
)

_ADAPTERS: dict[str, AdapterType] = {
    "authenticated_json": AuthenticatedJsonAdapter,
    "http": HttpAdapter,
    "local_file": LocalFileAdapter,
}
```

There is no runtime plugin or entry-point registration API at present. A new
adapter is therefore an in-tree `runbook-data` change.

## Build a Stage 2 parser

The parser is the curator. It implements the
[`Stage2Parser`](../packages/runbook/runbook-data/src/runbook/data/ingest/parsers/base/contracts.py)
call signature and returns one `CuratedFrame` for every produced partition:

```python
def parse_source(
    *,
    source_config: SourceConfig,
    dataset_alias: str,
    acquired: AcquisitionResult,
) -> list[CuratedFrame]: ...
```

The runner replaces `acquired.payload` with bytes read back from immutable
raw storage before calling the parser. Parse only that payload; do not reopen
`source_locator` or make network calls.

This example parses an order export and partitions it by year:

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
    del source_config  # Use this when parsing depends on declared params.
    try:
        records = json.loads(acquired.payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("orders_json_v1 payload is not valid JSON") from exc
    if not isinstance(records, list) or not records:
        raise ValueError("orders_json_v1 requires at least one order")

    frame = pd.DataFrame.from_records(records)
    required = {"order_id", "updated_at", "amount"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"orders_json_v1 fields are missing: {missing}")

    frame = frame.copy()
    frame["order_id"] = frame["order_id"].astype(str)
    frame["updated_at"] = pd.to_datetime(frame["updated_at"], utc=True, errors="coerce")
    if frame["updated_at"].isna().any():
        raise ValueError("orders_json_v1 contains an invalid updated_at")

    frame = (
        frame.sort_values(["updated_at", "order_id"], kind="mergesort")
        .drop_duplicates("order_id", keep="last")
        .reset_index(drop=True)
    )
    batch_watermark = frame["updated_at"].max().to_pydatetime()
    frame["year"] = frame["updated_at"].dt.year

    outputs: list[CuratedFrame] = []
    for year, partition_frame in frame.groupby("year", sort=True):
        curated = partition_frame.drop(columns="year").sort_values("order_id", kind="mergesort").reset_index(drop=True)
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

A parser should make these properties explicit:

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

### Register the parser

Parsers are registered in
[`ingest/parsers/__init__.py`](../packages/runbook/runbook-data/src/runbook/data/ingest/parsers/__init__.py):

```python
from runbook.data.ingest.parsers.orders_json import parse_orders_json

_PARSERS: dict[str, Stage2Parser] = {
    "csv_timeseries_v1": parse_csv_timeseries,
    "orders_json_v1": parse_orders_json,
}
```

Version the parser identifier when a parsing or schema change would alter the
meaning of already-published data.

## Configure the source and dataset

The adapter and parser are joined in `data/contract/source_configs.json`:

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

The existing
[`tests/data/test_generic_ingest.py`](../tests/data/test_generic_ingest.py)
shows parser and end-to-end examples. Run the focused checks with:

```bash
pixi run test tests/data/test_generic_ingest.py
pixi run lint
pixi run format-check
pixi run typecheck
```

Before merging, also verify that a repeated ingest of identical bytes reuses
the existing curated revision and that a parser failure leaves
`pointers.json` unchanged.

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
