"""Source-blind Stage 2 curation and manifest publication."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from runbook.core.data import DatasetFile, DatasetManifest
from runbook.core.utils.hashing import canonical_json, sha256_bytes
from runbook.data.config import DatasetBinding, SourceConfig
from runbook.data.ingest.models import (
    AcquisitionResult,
    CuratedFrame,
    CurationResult,
)
from runbook.data.ingest.parsers import get_parser
from runbook.data.manifests import (
    build_manifest,
    load_manifest,
    read_dataframe,
    write_dataframe,
    write_manifests,
)
from runbook.data.pointers import DatasetPointer, DatasetPointerUpdate
from runbook.data.store import BlobStore


def _curate_frames(source_config: SourceConfig, acquired: AcquisitionResult) -> list[CuratedFrame]:
    """Run each configured source-blind parser against persisted raw bytes."""
    frames: list[CuratedFrame] = []
    for alias, binding in source_config.datasets.items():
        parser = get_parser(binding.parser_id)
        frames.extend(
            parser(
                source_config=source_config,
                dataset_alias=alias,
                acquired=acquired,
            )
        )
    return frames


def _validate_partition(binding: DatasetBinding, partition: dict[str, str]) -> dict[str, str]:
    """Validate and restrict parser partition fields to configured keys."""
    if binding.partition_keys:
        actual = tuple(partition)
        if actual != binding.partition_keys:
            raise ValueError(f"partition keys do not match configuration: expected={binding.partition_keys}, actual={actual}")
    return {key: partition[key] for key in binding.partition_keys} if binding.partition_keys else dict(partition)


def _append_frame(store: BlobStore, frame: CuratedFrame, prior: DatasetFile | None) -> CuratedFrame:
    """Merge an append frame by its explicitly declared deterministic keys."""
    if prior is None:
        if not frame.merge_keys:
            raise ValueError(f"append dataset {frame.output_alias!r} requires merge_keys")
        return frame
    if not frame.merge_keys:
        raise ValueError(f"append dataset {frame.output_alias!r} requires merge_keys")
    previous = read_dataframe(store, prior.ref, expected_sha256=prior.sha256)
    missing = [key for key in frame.merge_keys if key not in previous.columns or key not in frame.frame.columns]
    if missing:
        raise ValueError(f"append merge keys are missing: {missing}")
    merged = pd.concat([previous, frame.frame], ignore_index=True)
    merged = merged.drop_duplicates(list(frame.merge_keys), keep="last").sort_values(list(frame.merge_keys), kind="mergesort").reset_index(drop=True)
    return CuratedFrame(frame.output_alias, merged, frame.watermark, frame.partition, frame.merge_keys)


def run_stage2_curate(
    *,
    store: BlobStore,
    source_config: SourceConfig,
    acquired: AcquisitionResult,
    published_at: datetime | None = None,
    previous_pointers: dict[str, DatasetPointer] | None = None,
) -> CurationResult:
    """Curate persisted raw bytes and return immutable manifest pointer updates."""
    logger.info(
        "stage=2 start source={} slot={} datasets={}",
        source_config.source_id,
        acquired.record.acquisition_run,
        sorted(source_config.datasets),
    )
    published_value = published_at or acquired.record.fetched_at
    if published_value.tzinfo is None:
        raise ValueError("Stage 2 publication time must be timezone-aware")
    published = published_value.astimezone(timezone.utc)
    if not acquired.record.artifact_ref or not acquired.record.content_sha256:
        raise ValueError("Stage 2 requires a persisted raw artifact reference and digest")
    persisted = store.get(acquired.record.artifact_ref)
    if sha256_bytes(persisted) != acquired.record.content_sha256:
        raise IOError(f"raw blob verification failed: {acquired.record.artifact_ref}")
    logger.info(
        "stage=2 raw verified source={} slot={} ref={}",
        source_config.source_id,
        acquired.record.acquisition_run,
        acquired.record.artifact_ref,
    )
    persisted_acquired = acquired.model_copy(update={"payload": persisted})
    frames = _curate_frames(source_config, persisted_acquired)
    logger.info(
        "stage=2 parsed source={} slot={} frames={}",
        source_config.source_id,
        acquired.record.acquisition_run,
        len(frames),
    )
    expected = set(source_config.datasets)
    actual = {frame.output_alias for frame in frames}
    if actual != expected:
        raise ValueError(f"source outputs do not match config: expected={sorted(expected)}, actual={sorted(actual)}")

    pointers = dict(previous_pointers or {})
    bindings_by_dataset = {
        binding.dataset_id: binding
        for binding in source_config.datasets.values()
    }
    previous_manifests: dict[str, DatasetManifest] = {}

    for dataset_id, pointer in pointers.items():
        logger.info(
            "stage=2 loading previous manifest dataset={} ref={}",
            dataset_id,
            pointer.manifest_ref,
        )
        binding = bindings_by_dataset.get(dataset_id)
        if binding is None:
            continue

        if not store.exists(pointer.manifest_ref):
            if binding.update_mode == "append":
                raise RuntimeError(
                    "append dataset pointer references missing manifest: "
                    f"dataset_id={dataset_id!r} "
                    f"manifest_ref={pointer.manifest_ref!r} "
                    f"source_run_id={pointer.source_run_id!r}"
                )

            logger.warning(
                "ignoring missing previous manifest for full refresh "
                "dataset={} manifest_ref={} source_run_id={}",
                dataset_id,
                pointer.manifest_ref,
                pointer.source_run_id,
            )
            continue

        previous_manifests[dataset_id] = load_manifest(
            store,
            pointer.manifest_ref,
            expected_dataset_id=dataset_id,
        )
    files_by_dataset: dict[str, list[DatasetFile]] = defaultdict(list)
    frame_by_dataset: dict[str, list[CuratedFrame]] = defaultdict(list)
    initialized_datasets: set[str] = set()
    seen_partitions: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

    # Validate every frame before writing anything so a malformed later dataset
    # cannot publish a partial pointer update.
    normalized_frames: list[
        tuple[
            CuratedFrame,
            DatasetBinding,
            str,
            DatasetFile | None,
            dict[str, str],
            DatasetManifest | None,
        ]
    ] = []
    incoming_watermarks: dict[str, datetime] = {}

    for frame in frames:
        binding = source_config.datasets[frame.output_alias]
        dataset_id = binding.dataset_id
        partition = _validate_partition(binding, frame.partition)
        partition_identity = (dataset_id, tuple(partition.items()))
        if partition_identity in seen_partitions:
            raise ValueError(f"duplicate curated partition: {dataset_id!r} {partition!r}")
        seen_partitions.add(partition_identity)
        previous = previous_manifests.get(dataset_id)
        prior = next((item for item in previous.files if item.partition == partition), None) if previous else None
        if binding.update_mode == "append":
            if not frame.merge_keys:
                raise ValueError(f"append dataset {dataset_id!r} requires merge_keys")
            previous_watermark = previous.watermark if previous else None
            if previous_watermark is not None and frame.watermark < previous_watermark:
                raise ValueError(f"append watermark regressed for dataset {dataset_id!r}")
            frame = _append_frame(store, frame, prior)
        normalized_frames.append((frame, binding, dataset_id, prior, partition, previous))
        incoming_watermarks[dataset_id] = max(incoming_watermarks.get(dataset_id, frame.watermark), frame.watermark)

    for frame, binding, dataset_id, prior, partition, previous in normalized_frames:
        logger.info(
            "stage=2 writing dataset={} partition={} rows={}",
            dataset_id,
            partition,
            len(frame.frame),
        )
        file_ref, file_sha = write_dataframe(
            store,
            dataset_id,
            frame.frame,
            partition=partition,
            schema_version=binding.schema_version,
            previous=prior,
        )
        logger.info(
            "stage=2 wrote dataset={} partition={} ref={}",
            dataset_id,
            partition,
            file_ref,
        )
        if dataset_id not in initialized_datasets:
            # Full refreshes replace the dataset; append runs retain prior
            # partitions. This also lets a partition-key change converge the
            # manifest without carrying the old layout forward.
            if previous and binding.update_mode == "append":
                files_by_dataset[dataset_id].extend(previous.files)
            initialized_datasets.add(dataset_id)
        files_by_dataset[dataset_id] = [item for item in files_by_dataset[dataset_id] if item.partition != partition]
        files_by_dataset[dataset_id].append(
            DatasetFile(
                ref=file_ref,
                sha256=file_sha,
                partition=partition,
                lineage={
                    "source_id": source_config.source_id,
                    "slot": acquired.record.acquisition_run,
                    "raw_ref": acquired.record.artifact_ref,
                    "raw_sha256": acquired.record.content_sha256,
                },
            )
        )
        frame_by_dataset[dataset_id].append(frame)

    prepared: list[tuple[DatasetManifest, str]] = []
    result: dict[str, str] = {}
    for dataset_id in frame_by_dataset:
        previous = previous_manifests.get(dataset_id)
        watermark = max(
            incoming_watermarks[dataset_id],
            previous.watermark if previous else incoming_watermarks[dataset_id],
        )
        current_files = tuple(
            sorted(
                files_by_dataset[dataset_id],
                key=lambda item: (canonical_json(item.partition), item.ref),
            )
        )
        if previous and watermark == previous.watermark and tuple(previous.files) == current_files:
            result[dataset_id] = pointers[dataset_id].manifest_ref
            continue
        manifest, digest = build_manifest(
            dataset_id=dataset_id,
            watermark=watermark,
            published_at=published,
            previous=pointers[dataset_id].manifest_ref if previous else None,
            files=files_by_dataset[dataset_id],
        )
        ref = f"curated/{dataset_id}/manifests/sha256={digest}.json"
        result[dataset_id] = ref
        if not previous or manifest.model_dump(mode="json") != previous.model_dump(mode="json"):
            prepared.append((manifest, digest))
    write_manifests(store, prepared)
    manifests_by_id = {manifest.dataset_id: manifest for manifest, _digest in prepared}
    updates: list[DatasetPointerUpdate] = []
    for dataset_id, ref in sorted(result.items()):
        manifest = manifests_by_id.get(dataset_id) or previous_manifests[dataset_id]
        updates.append(
            DatasetPointerUpdate(
                dataset_id=dataset_id,
                manifest_ref=ref,
                watermark=manifest.watermark,
                published_at=manifest.published_at,
            )
        )
    logger.info(
        "stage=2 published source={} slot={} manifests={} reused={}",
        source_config.source_id,
        acquired.record.acquisition_run,
        sorted(result),
        len(result) - len(prepared),
    )
    return CurationResult(
        datasets=result,
        pointer_updates=tuple(updates),
    )


__all__ = ["run_stage2_curate"]
