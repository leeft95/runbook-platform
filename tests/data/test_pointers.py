from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from runbook.data import (
    DatabasePointerRegistry,
    DatasetPointerUpdate,
    build_manifest,
    create_pointer_schema,
    open_blob_store,
    resolve_snapshot,
    write_manifests,
)
from sqlalchemy import create_engine


def _update(dataset_id: str, ref: str, stamp: datetime) -> DatasetPointerUpdate:
    return DatasetPointerUpdate(
        dataset_id=dataset_id,
        manifest_ref=ref,
        watermark=stamp,
        published_at=stamp,
    )


def test_pointer_publication_is_atomic_and_source_owned(pointer_registry) -> None:
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pointer_registry.publish(
        source_id="source_a",
        source_run_id="run_a",
        updates=[_update("prices", "prices-v1", stamp), _update("volume", "volume-v1", stamp)],
    )

    with pytest.raises(ValueError, match="prices=source_a"):
        pointer_registry.publish(
            source_id="source_b",
            source_run_id="run_b",
            updates=[_update("new_data", "new-v1", stamp), _update("prices", "prices-v2", stamp)],
        )

    assert set(pointer_registry.all()) == {"prices", "volume"}
    assert pointer_registry.get(["prices"])["prices"].manifest_ref == "prices-v1"


def test_pointer_publication_validates_every_update_before_writing() -> None:
    engine = create_engine("sqlite://")
    create_pointer_schema(engine)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    invalid = datetime(2026, 1, 2)

    with engine.connect() as connection:
        registry = DatabasePointerRegistry(connection)
        with pytest.raises(ValueError, match="timezone-aware"):
            registry.publish(
                source_id="source_a",
                source_run_id="run_a",
                updates=[_update("prices", "prices-v1", stamp), _update("volume", "volume-v1", invalid)],
            )
        connection.commit()

    assert DatabasePointerRegistry(engine).all() == {}


def test_snapshot_uses_database_pointer_and_manifest_history(tmp_path, pointer_registry) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_time = first_time + timedelta(days=1)
    first, first_digest = build_manifest(
        dataset_id="prices",
        watermark=first_time,
        published_at=first_time,
        files=[],
    )
    first_ref = write_manifests(store, [(first, first_digest)])["prices"]
    second, second_digest = build_manifest(
        dataset_id="prices",
        watermark=second_time,
        published_at=second_time,
        previous=first_ref,
        files=[],
    )
    second_ref = write_manifests(store, [(second, second_digest)])["prices"]
    pointer_registry.publish(
        source_id="prices_source",
        source_run_id="run-2",
        updates=[_update("prices", second_ref, second_time)],
    )
    store.put_json("pointers.json", {"prices": "invalid-stale-ref"})

    latest = resolve_snapshot(store, {"prices": "prices"}, pointer_registry=pointer_registry)
    historical = resolve_snapshot(
        store,
        {"prices": "prices"},
        pointer_registry=pointer_registry,
        as_of=first_time,
    )

    assert latest.datasets == {"prices": second_ref}
    assert latest.watermark == second_time
    assert historical.datasets == {"prices": first_ref}
    assert historical.watermark == first_time
