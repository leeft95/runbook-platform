# runbook-data

`runbook-data` provides Runbook's generic data boundary:

- HTTP and local-file source acquisition;
- source-blind Stage 2 curation;
- deterministic CSV time-series parsing;
- immutable Parquet revisions and complete dataset manifests;
- snapshot resolution and verified dataset loading;
- local filesystem storage, with optional S3 support.

Use the repository's Pixi environment when working from source:

```bash
pixi install
```

The base distribution supports local files. Its optional `s3` extra adds
`boto3` for S3-backed stores.

The default store is `file:.runbook`. Override it with
`RUNBOOK_DATA_STORE_URI` or an explicit URI:

```python
from runbook.data import open_blob_store

local = open_blob_store("file:/path/to/store")
s3 = open_blob_store("s3://bucket/prefix")
```

Use `runbook.sdk.create_client()` for application and notebook reads. Do not
glob curated Parquet directories: immutable older revisions remain beside the
files selected by the current manifest.

See the repository's [data guide](https://github.com/redcombojnr/runbook-platform/blob/main/docs/data.md)
for the synthetic quickstart, source configuration, update modes, storage
layout, and historical reads. To add a source capability or parser, follow the
[source adapter and curation guide](https://github.com/redcombojnr/runbook-platform/blob/main/docs/source-adapters-and-curation.md).
