from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import pandas as pd
from runbook.core.snapshots import Snapshot
from runbook.data import (
    BlobStore,
    load_snapshot_dataset,
    open_blob_store,
    resolve_snapshot,
)
from runbook.sdk.execution import ReportResult, execute_report, resolve_code_version
from runbook.sdk.profiles import ReportProfile


class RunbookClient:
    def __init__(
        self,
        *,
        store: BlobStore,
        workspace_store: BlobStore | None = None,
        reports_root: str | Path = "reports",
    ):
        self.store = store
        self.workspace_store = workspace_store
        self.reports_root = Path(reports_root)

    def preview(self, profile: ReportProfile, *, code_version: str | None = None) -> ReportResult:
        """Execute a report against the latest snapshot without changing data pointers."""
        snapshot = resolve_snapshot(self.store, profile.datasets)
        return execute_report(
            store=self.workspace_store or self.store,
            data_store=self.store,
            profile=profile,
            snapshot=snapshot,
            code_version=resolve_code_version(code_version),
            reports_root=self.reports_root,
        )

    def load_datasets(
        self, bindings: Mapping[str, str], *, as_of: datetime | None = None
    ) -> tuple[dict[str, pd.DataFrame], Snapshot]:
        """Load all bound datasets from one latest or historical snapshot."""
        if not bindings:
            raise ValueError("load_datasets requires at least one dataset binding")
        snapshot = resolve_snapshot(self.store, dict(bindings), as_of=as_of)
        frames = {alias: load_snapshot_dataset(self.store, snapshot, alias) for alias in sorted(bindings)}
        return frames, snapshot

    def load_dataset(
        self, dataset_id: str, *, as_of: datetime | None = None, **filters: object
    ) -> tuple[pd.DataFrame, Snapshot]:
        """Load one dataset and optional partition filters from a pinned snapshot."""
        snapshot = resolve_snapshot(self.store, {"dataset": dataset_id}, as_of=as_of)
        frame = load_snapshot_dataset(self.store, snapshot, "dataset", filters=filters or None)
        return frame, snapshot


def create_client(
    *,
    store_uri: str | None = None,
    workspace_store_uri: str | None = None,
    reports_root: str | Path = "reports",
) -> RunbookClient:
    """Create an SDK client from explicit URIs or environment defaults."""
    data_uri = store_uri or os.environ.get("RUNBOOK_DATA_STORE_URI")
    workspace_uri = workspace_store_uri or os.environ.get("RUNBOOK_WORKSPACE_STORE_URI")
    workspace_store = open_blob_store(workspace_uri) if workspace_uri else None
    return RunbookClient(
        store=open_blob_store(data_uri),
        workspace_store=workspace_store,
        reports_root=reports_root,
    )
