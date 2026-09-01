"""In-memory helpers for prototyping reports from pandas frames."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

import pandas as pd
from runbook.core import BlobStore, DatasetFile, ReportProfile, Snapshot
from runbook.data.manifests import build_manifest, build_snapshot, write_dataframe, write_manifests
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.execution import ReportResult, execute_report


class _MemoryStore(BlobStore):
    """Small dict-backed BlobStore for one prototype execution."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    @staticmethod
    def _normalize(key: str) -> str:
        """Validate and normalize a relative object key."""
        normalized = str(PurePosixPath(key))
        if normalized.startswith("/") or normalized.startswith("../") or normalized == ".." or "/../" in normalized:
            raise ValueError(f"invalid blob key: {key!r}")
        return normalized

    def exists(self, key: str) -> bool:
        """Return whether an object exists in memory."""
        return self._normalize(key) in self._objects

    def get(self, key: str) -> bytes:
        """Read one complete in-memory object."""
        normalized = self._normalize(key)
        try:
            return self._objects[normalized]
        except KeyError as exc:
            raise FileNotFoundError(normalized) from exc

    def put_immutable(self, key: str, payload: bytes) -> str:
        """Create an object once, accepting identical retries."""
        normalized = self._normalize(key)
        existing = self._objects.get(normalized)
        if existing is not None:
            if existing != payload:
                raise IOError(f"immutable blob conflict: {normalized}")
            return normalized
        self._objects[normalized] = payload
        return normalized

    def get_json(self, key: str) -> Any:
        """Read a JSON object from memory."""
        return json.loads(self.get(key).decode())


def snapshot_from_frames(
    frames: Mapping[str, pd.DataFrame],
    *,
    observed_at: datetime,
    report_id: str = "prototype",
    _store: BlobStore | None = None,
) -> Snapshot:
    """Freeze alias-keyed DataFrames into immutable in-memory manifests."""
    store = _store if _store is not None else _MemoryStore()
    prepared: list[tuple[Any, str]] = []
    dataset_ids: dict[str, str] = {}
    for alias in sorted(frames):
        dataset_id = f"{report_id}_{alias}"
        ref, digest = write_dataframe(store, dataset_id, frames[alias])
        manifest, manifest_digest = build_manifest(
            dataset_id=dataset_id,
            watermark=observed_at,
            published_at=observed_at,
            files=[DatasetFile(ref=ref, sha256=digest)],
        )
        prepared.append((manifest, manifest_digest))
        dataset_ids[alias] = dataset_id
    manifest_refs = write_manifests(store, prepared)
    return build_snapshot(
        {alias: manifest_refs[dataset_ids[alias]] for alias in sorted(dataset_ids)},
        watermark=observed_at,
    )


def prototype_report(
    *,
    profile: ReportProfile,
    frames: Mapping[str, pd.DataFrame],
    calculations: Mapping[str, Callable[..., Any]] | None = None,
    page: Callable[..., Any] | None = None,
    observed_at: datetime | None = None,
    code_version: str = "prototype",
) -> ReportResult:
    """Execute a real report directly from alias-keyed pandas DataFrames."""
    expected = set(profile.datasets)
    actual = set(frames)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"frames aliases do not match profile datasets: missing={missing}, extra={extra}")
    if (calculations is None) != (page is None):
        raise ValueError("calculations and page must be provided together")
    definition: ReportDefinition | None = None
    if calculations is not None and page is not None:
        if not isinstance(calculations, Mapping):
            raise TypeError("calculations must be a mapping")
        if not calculations:
            raise ValueError("calculations must not be empty")
        if not callable(page):
            raise TypeError("page must be callable")
        if any(not callable(function) for function in calculations.values()):
            raise TypeError("all calculations must be callable")
        definition = ReportDefinition(
            aliases=sorted(profile.datasets),
            calc_fns=dict(calculations),
            page_fn=page,
        )

    observed = observed_at or datetime.now(timezone.utc)
    store = _MemoryStore()
    snapshot = snapshot_from_frames(
        frames,
        observed_at=observed,
        report_id=profile.report_id,
        _store=store,
    )
    return execute_report(
        store=store,
        data_store=store,
        profile=profile,
        snapshot=snapshot,
        code_version=code_version,
        generated_at=observed,
        _definition=definition,
    )


__all__ = ["prototype_report", "snapshot_from_frames"]
