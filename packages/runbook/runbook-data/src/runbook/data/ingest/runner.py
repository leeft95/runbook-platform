"""Canonical source ingest entrypoint for the simplified orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from loguru import logger
from runbook.core.utils.hashing import sha256_bytes
from runbook.data.config import SourceConfig, load_source_configs
from runbook.data.ingest.adapters import get_adapter
from runbook.data.ingest.models import (
    AcquisitionStageResult,
    IngestRequest,
    IngestResult,
    ReadinessStatus,
)
from runbook.data.ingest.runners import run_stage2_curate
from runbook.data.manifests import load_manifest
from runbook.data.pipeline import slot_key
from runbook.data.pointers import DatabasePointerRegistry, DatasetPointer, open_pointer_registry
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


def load_previous_append_state(
    store: BlobStore,
    config: SourceConfig,
    pointers: dict[str, DatasetPointer],
) -> tuple[dict[str, datetime], dict[str, set[str]]]:
    """Load append state and reject pointers whose manifests disappeared."""
    watermarks: dict[str, datetime] = {}
    tickers: dict[str, set[str]] = {}
    for alias, binding in config.datasets.items():
        if binding.update_mode != "append":
            continue
        pointer = pointers.get(binding.dataset_id)
        if pointer is None:
            continue
        if not store.exists(pointer.manifest_ref):
            raise RuntimeError(
                "append dataset pointer references missing manifest: "
                f"dataset_id={binding.dataset_id!r} "
                f"manifest_ref={pointer.manifest_ref!r} "
                f"source_run_id={pointer.source_run_id!r}"
            )
        manifest = load_manifest(
            store,
            pointer.manifest_ref,
            expected_dataset_id=binding.dataset_id,
        )
        watermarks[alias] = manifest.watermark
        values = {
            item.partition["ticker"]
            for item in manifest.files
            if "ticker" in item.partition
        }
        if values:
            tickers[alias] = values
    return watermarks, tickers


def run_stage1_acquire(
    *,
    source_config: SourceConfig,
    slot: datetime,
    store: BlobStore,
    previous_watermarks: dict[str, datetime] | None = None,
) -> AcquisitionStageResult:
    """Check readiness, acquire bytes, and persist one immutable raw artifact."""
    config = source_config
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
        return AcquisitionStageResult(
            acquisition_run=run,
            status=readiness.status,
            readiness=readiness,
            message=readiness.message or "source is not ready",
        )

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
        previous_watermarks=previous_watermarks or {},
    )
    raw_sha = sha256_bytes(acquired.payload)
    raw_ref = f"raw/{config.source_id}/{run}/sha256={raw_sha}/source{PurePosixPath(acquired.record.source_filename).suffix or '.bin'}"
    store.put_immutable(raw_ref, acquired.payload)
    persisted = store.get(raw_ref)
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
    return AcquisitionStageResult(
        acquisition_run=run,
        status=ReadinessStatus.ready,
        readiness=readiness,
        acquired=acquired,
        message="source acquired",
    )


def run_ingest(
    request: IngestRequest | None = None,
    *,
    store: BlobStore | None = None,
    pointer_registry: DatabasePointerRegistry | None = None,
) -> IngestResult:
    """Run acquisition and curation sequentially, publishing pointers to PostgreSQL."""
    resolved = request or IngestRequest()
    config = _source_config(resolved)
    slot = resolved.run_time or datetime.now(timezone.utc)
    if slot.tzinfo is None:
        raise ValueError("ingest run_time must be timezone-aware")
    slot = slot.astimezone(timezone.utc)
    blob_store = store or open_blob_store(resolved.store_uri)
    pointers = pointer_registry or open_pointer_registry()
    current = pointers.get(binding.dataset_id for binding in config.datasets.values())
    previous_watermarks, _previous_tickers = load_previous_append_state(
        blob_store,
        config,
        current,
    )
    acquisition = run_stage1_acquire(
        source_config=config,
        slot=slot,
        store=blob_store,
        previous_watermarks=previous_watermarks,
    )
    if acquisition.status is not ReadinessStatus.ready:
        return IngestResult(
            source_id=config.source_id,
            acquisition_run=acquisition.acquisition_run,
            status=acquisition.status,
            readiness=acquisition.readiness,
            message=acquisition.message,
        )
    if acquisition.acquired is None:  # pragma: no cover - guarded by the stage contract
        raise RuntimeError("ready acquisition did not return a payload")
    logger.info(
        "stage=2 curate source={} slot={} datasets={}",
        config.source_id,
        acquisition.acquisition_run,
        sorted(config.datasets),
    )
    curated = run_stage2_curate(
        store=blob_store,
        source_config=config,
        acquired=acquisition.acquired,
        published_at=slot,
        previous_pointers=current,
    )
    pointers.publish(
        source_id=config.source_id,
        source_run_id=acquisition.acquisition_run,
        updates=curated.pointer_updates,
        updated_at=slot,
    )
    logger.info(
        "stage=2 complete source={} slot={} datasets={}",
        config.source_id,
        acquisition.acquisition_run,
        sorted(curated.datasets),
    )
    return IngestResult(
        source_id=config.source_id,
        acquisition_run=acquisition.acquisition_run,
        status=ReadinessStatus.ready,
        readiness=acquisition.readiness,
        raw_record=acquisition.acquired.record,
        datasets=curated.datasets,
        message="ingest completed",
    )


__all__ = ["load_previous_append_state", "run_ingest", "run_stage1_acquire"]
