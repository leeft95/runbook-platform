"""Canonical source ingest entrypoint for the simplified orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from loguru import logger
from runbook.core.utils.hashing import sha256_bytes
from runbook.data.config import SourceConfig, load_source_configs
from runbook.data.ingest.adapters import get_adapter
from runbook.data.ingest.models import (
    IngestRequest,
    IngestResult,
    ReadinessStatus,
)
from runbook.data.ingest.runners import run_stage2_curate
from runbook.data.manifests import load_manifest
from runbook.data.pipeline import slot_key
from runbook.data.store import BlobStore, open_blob_store


def _source_config(request: IngestRequest) -> SourceConfig:
    """Handle source config."""
    if request.source_config is not None:
        return request.source_config
    if not request.source:
        raise ValueError("ingest requires source or source_config")
    configs = load_source_configs(request.source_config_file)
    try:
        return configs[request.source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {request.source!r}") from exc


def _previous_state(store: BlobStore, config: SourceConfig) -> dict[str, datetime]:
    """Handle previous state."""
    pointers = store.get_json("pointers.json") if store.exists("pointers.json") else {}
    watermarks: dict[str, datetime] = {}
    for alias, binding in config.datasets.items():
        if binding.update_mode != "append":
            continue
        ref = pointers.get(binding.dataset_id)
        if not isinstance(ref, str):
            continue
        manifest = load_manifest(store, ref, expected_dataset_id=binding.dataset_id)
        watermarks[alias] = manifest.watermark
    return watermarks


def run_ingest(
    request: IngestRequest | None = None,
    *,
    store: BlobStore | None = None,
) -> IngestResult:
    """Run ingest."""
    resolved = request or IngestRequest()
    config = _source_config(resolved)
    slot = resolved.run_time or datetime.now(timezone.utc)
    if slot.tzinfo is None:
        raise ValueError("ingest run_time must be timezone-aware")
    slot = slot.astimezone(timezone.utc)
    run = slot_key(slot)
    adapter = get_adapter(config)
    logger.info("stage=1A readiness source={} slot={}", config.source_id, run)
    readiness = adapter.check(
        source_config=config,
        acquisition_run=run,
        observed_at=slot,
    )
    logger.info(
        "stage=1A readiness source={} slot={} status={}",
        config.source_id,
        run,
        readiness.status.value,
    )
    if readiness.status is not ReadinessStatus.ready:
        return IngestResult(
            source_id=config.source_id,
            acquisition_run=run,
            status=readiness.status,
            readiness=readiness,
            message=readiness.message or "source is not ready",
        )

    blob_store = store or open_blob_store(resolved.store_uri)
    previous_watermarks = _previous_state(blob_store, config)
    logger.info(
        "stage=1B acquire source={} slot={} adapter={}",
        config.source_id,
        run,
        config.adapter,
    )
    acquired = adapter.acquire(
        source_config=config,
        readiness=readiness,
        fetched_at=slot,
        previous_watermarks=previous_watermarks,
    )
    raw_sha = sha256_bytes(acquired.payload)
    raw_ref = f"raw/{config.source_id}/{run}/sha256={raw_sha}/source{PurePosixPath(acquired.record.source_filename).suffix or '.bin'}"
    blob_store.put_immutable(raw_ref, acquired.payload)
    persisted = blob_store.get(raw_ref)
    if sha256_bytes(persisted) != raw_sha:
        raise IOError(f"raw blob verification failed: {raw_ref}")
    acquired = acquired.model_copy(
        update={
            "record": acquired.record.model_copy(
                update={
                    "artifact_ref": raw_ref,
                    "content_sha256": raw_sha,
                }
            )
        }
    )
    logger.info(
        "stage=1B persisted source={} slot={} raw_ref={} bytes={}",
        config.source_id,
        run,
        raw_ref,
        len(acquired.payload),
    )

    logger.info(
        "stage=2 curate source={} slot={} datasets={}",
        config.source_id,
        run,
        sorted(config.datasets),
    )
    datasets = run_stage2_curate(
        store=blob_store,
        source_config=config,
        acquired=acquired,
        published_at=slot,
    )
    logger.info(
        "stage=2 complete source={} slot={} datasets={}",
        config.source_id,
        run,
        sorted(datasets),
    )
    return IngestResult(
        source_id=config.source_id,
        acquisition_run=run,
        status=ReadinessStatus.ready,
        readiness=readiness,
        raw_record=acquired.record,
        datasets=datasets,
        message="ingest completed",
    )


__all__ = ["run_ingest"]
