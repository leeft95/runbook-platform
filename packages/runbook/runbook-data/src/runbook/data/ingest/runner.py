"""Canonical source ingest entrypoint for the simplified orchestrator."""

from __future__ import annotations

import inspect
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, cast

from loguru import logger
from runbook.core.utils.hashing import sha256_bytes
from runbook.data.config import SourceConfig, load_source_configs
from runbook.data.ingest.adapters import HistoricalSourceAdapter, get_adapter
from runbook.data.ingest.models import (
    AcquisitionStageResult,
    HistoricalExecutionContext,
    IngestRequest,
    IngestResult,
    PreviousAcquisitionState,
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


def load_previous_acquisition_state(
    store: BlobStore,
    config: SourceConfig,
    pointers: dict[str, DatasetPointer],
) -> PreviousAcquisitionState | None:
    """Load generic append state and reject pointers whose manifests disappeared."""
    watermarks: dict[str, datetime] = {}
    partition_values: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    found = False
    for alias, binding in config.datasets.items():
        if binding.update_mode != "append":
            continue
        pointer = pointers.get(binding.dataset_id)
        if pointer is None:
            continue
        found = True
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
        for item in manifest.files:
            for key, value in item.partition.items():
                partition_values[alias][key].add(value)
    if not found:
        return None
    metadata = (
        {
            "partition_values": {
                alias: {key: sorted(values) for key, values in sorted(by_key.items())}
                for alias, by_key in sorted(partition_values.items())
            }
        }
        if partition_values
        else {}
    )
    return PreviousAcquisitionState(
        watermark={alias: watermarks[alias] for alias in sorted(watermarks)} or None,
        metadata=metadata,
    )


def run_stage1_acquire(
    *,
    source_config: SourceConfig,
    slot: datetime,
    store: BlobStore,
    previous_watermarks: dict[str, datetime] | None = None,
    previous_state: PreviousAcquisitionState | None = None,
    execution_context: HistoricalExecutionContext | None = None,
) -> AcquisitionStageResult:
    """Check readiness, acquire bytes, and persist one immutable raw artifact."""
    config = source_config
    if slot.tzinfo is None:
        raise ValueError("ingest run_time must be timezone-aware")
    slot = slot.astimezone(timezone.utc)
    run = slot_key(slot)
    adapter = get_adapter(config)
    historical_adapter: HistoricalSourceAdapter | None = None
    if execution_context is not None:
        # A historical request is an explicit adapter opt-in.  Requiring both
        # stage-1 hooks to accept the immutable context keeps unsupported
        # adapters from making a normal acquisition before failing.
        historical_adapter = cast(HistoricalSourceAdapter, adapter)
        try:
            check_signature = inspect.signature(historical_adapter.check)
            historical_acquire_signature = inspect.signature(historical_adapter.acquire)
            check_context = check_signature.parameters.get("execution_context")
            acquire_context = historical_acquire_signature.parameters.get("execution_context")
            if check_context is None or acquire_context is None:
                raise TypeError("historical execution context is not explicitly supported")
            check_signature.bind(
                source_config=config,
                acquisition_run=run,
                observed_at=slot,
                execution_context=execution_context,
            )
            historical_acquire_signature.bind(
                source_config=config,
                readiness=object(),
                fetched_at=slot,
                execution_context=execution_context,
            )
        except (TypeError, ValueError):
            raise ValueError(f"Source '{config.source_id}' does not support historical date-range execution.") from None
    state = previous_state
    if state is None and previous_watermarks:
        state = PreviousAcquisitionState(watermark=previous_watermarks)
    logger.info("stage=1A readiness source={} slot={}", config.source_id, run)
    check_method = historical_adapter.check if historical_adapter is not None else adapter.check
    check_kwargs: dict[str, Any] = {
        "source_config": config,
        "acquisition_run": run,
        "observed_at": slot,
    }
    if execution_context is not None:
        check_kwargs["execution_context"] = execution_context
    try:
        check_signature = inspect.signature(check_method)
    except (TypeError, ValueError):
        pass
    else:
        previous_state_parameter = check_signature.parameters.get("previous_state")
        if previous_state_parameter is not None and previous_state_parameter.kind in {
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }:
            check_kwargs["previous_state"] = state
    readiness = check_method(**check_kwargs)
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
    acquire_signature: inspect.Signature
    try:
        acquire_method = historical_adapter.acquire if historical_adapter is not None else adapter.acquire
        acquire_signature = inspect.signature(acquire_method)
    except (TypeError, ValueError) as exc:  # pragma: no cover - registry rejects these adapters
        raise ValueError(f"adapter acquire signature is not inspectable: {exc}") from None
    acquire_kwargs: dict[str, Any] = {
        "source_config": config,
        "readiness": readiness,
        "fetched_at": slot,
    }
    if execution_context is not None:
        acquire_kwargs["execution_context"] = execution_context
    accepts_previous_state = True
    try:
        acquire_signature.bind(**acquire_kwargs, previous_state=state)
    except TypeError:
        accepts_previous_state = False
    accepts_previous_watermarks = True
    try:
        acquire_signature.bind(**acquire_kwargs, previous_watermarks=state.watermark if state is not None else {})
    except TypeError:
        accepts_previous_watermarks = False
    if accepts_previous_state and accepts_previous_watermarks:
        try:
            acquire_signature.bind(
                **acquire_kwargs,
                previous_state=state,
                previous_watermarks=state.watermark if state is not None else {},
            )
        except TypeError:
            accepts_previous_state = True
            accepts_previous_watermarks = False
    if accepts_previous_state:
        acquire_kwargs["previous_state"] = state
    if accepts_previous_watermarks:
        acquire_kwargs["previous_watermarks"] = (
            state.watermark if state is not None and isinstance(state.watermark, dict) else previous_watermarks or {}
        )
    acquired = acquire_method(**acquire_kwargs)
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
    if resolved.execution_context is not None:
        current = {}
    previous_state = load_previous_acquisition_state(
        blob_store,
        config,
        current,
    )
    acquisition = run_stage1_acquire(
        source_config=config,
        slot=slot,
        store=blob_store,
        previous_state=previous_state,
        execution_context=resolved.execution_context,
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
    if resolved.execution_context is None:
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


__all__ = [
    "load_previous_acquisition_state",
    "run_ingest",
    "run_stage1_acquire",
]
