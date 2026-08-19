from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from runbook.core.data import DatasetFile
from runbook.core.utils.hashing import sha256_bytes
from runbook.data import open_blob_store
from runbook.data.manifests import build_manifest, publish_manifests
from runbook.sdk import ReportProfile, create_client
from runbook.sdk.client import RunbookClient


class ReadOnlyBlobStore:
    def __init__(self, store):
        self._store = store

    def get(self, key):
        return self._store.get(key)

    def exists(self, key):
        return self._store.exists(key)

    def get_json(self, key):
        return self._store.get_json(key)

    def put(self, *_args, **_kwargs):
        raise AssertionError("analyst preview wrote to the shared data store")

    def put_json(self, *_args, **_kwargs):
        raise AssertionError("analyst preview wrote to the shared data store")


def _publish_demo_data(store, pointer_registry, now: datetime) -> None:
    daily = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, tz="UTC"),
            "open": [70.0, 70.5, 71.0],
            "high": [70.5, 71.0, 71.5],
            "low": [69.5, 70.0, 70.5],
            "close": [70.0, 70.5, 71.0],
        }
    )
    intraday = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="min", tz="UTC"),
            "open": [70.0, 70.1, 70.2],
            "high": [70.1, 70.2, 70.3],
            "low": [69.9, 70.0, 70.1],
            "close": [70.1, 70.2, 70.3],
            "volume": [10, 11, 12],
            "event_count": [1, 1, 1],
            "value": [701, 772, 843],
        }
    )
    prepared = []
    for dataset_id, frame, alias in (
        ("demo_daily_prices", daily, "daily_prices"),
        ("demo_intraday_bars", intraday, "intraday_bars"),
    ):
        ref = f"curated/{dataset_id}/version=v1/1.parquet"
        payload = frame.to_parquet(index=True)
        digest = sha256_bytes(payload)
        store.put(ref, payload)
        manifest, manifest_digest = build_manifest(
            dataset_id=dataset_id,
            watermark=now,
            published_at=now,
            files=[DatasetFile(ref=ref, sha256=digest, partition={})],
        )
        prepared.append((manifest, manifest_digest))
    publish_manifests(
        store,
        prepared,
        pointer_registry=pointer_registry,
        source_id="demo_source",
        source_run_id="fixture",
    )


def test_client_loads_one_snapshot_and_previews_into_workspace(tmp_path, pointer_registry) -> None:
    data_store = open_blob_store(f"file:{tmp_path / 'data'}")
    workspace_store = open_blob_store(f"file:{tmp_path / 'workspace'}")
    now = datetime(2025, 1, 2, tzinfo=timezone.utc)
    _publish_demo_data(data_store, pointer_registry, now)
    client = RunbookClient(
        store=ReadOnlyBlobStore(data_store),
        pointer_registry=pointer_registry,
        workspace_store=workspace_store,
    )

    frames, snapshot = client.load_datasets(
        {
            "daily_prices": "demo_daily_prices",
            "intraday_bars": "demo_intraday_bars",
        },
        as_of=now,
    )
    assert set(snapshot.datasets) == {"daily_prices", "intraday_bars"}
    assert frames["daily_prices"].shape == (3, 5)
    assert frames["intraday_bars"].shape == (3, 8)

    profile = ReportProfile(
        profile_id="timeseries_snapshot_demo",
        report_id="snapshot_report",
        datasets={
            "daily_prices": "demo_daily_prices",
            "intraday_bars": "demo_intraday_bars",
        },
        params={"lookback_days": 60},
    )
    cold = client.preview(profile, code_version="test")
    warm = client.preview(profile, code_version="test")
    assert cold.cache_hits == {
        "comparison": False,
        "daily_returns": False,
        "intraday_daily": False,
    }
    assert warm.cache_hits == {"comparison": True, "daily_returns": True}
    assert workspace_store.exists(cold.stage3_ref)
    assert workspace_store.exists(cold.html_ref)
    assert not data_store.exists(cold.stage3_ref)
    assert not data_store.exists(cold.html_ref)


def test_client_load_dataset_filters_manifest_partitions(tmp_path, pointer_registry) -> None:
    store = open_blob_store(f"file:{tmp_path / 'data'}")
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    files = []
    for series, close in (("energy", 10.0), ("metals", 20.0)):
        frame = pd.DataFrame({"timestamp": [now], "series": [series], "close": [close]})
        ref = f"curated/market_assets/version=v2/year=2026/series={series}/1.parquet"
        payload = frame.to_parquet(index=True)
        digest = sha256_bytes(payload)
        store.put(ref, payload)
        files.append(DatasetFile(ref=ref, sha256=digest, partition={"year": "2026", "series": series}))
    manifest, digest = build_manifest(dataset_id="market_assets", watermark=now, published_at=now, files=files)
    publish_manifests(
        store,
        [(manifest, digest)],
        pointer_registry=pointer_registry,
        source_id="market_source",
        source_run_id="fixture",
    )

    client = RunbookClient(store=ReadOnlyBlobStore(store), pointer_registry=pointer_registry)
    frame, snapshot = client.load_dataset("market_assets", series="energy", year=2026)

    assert snapshot.as_of is None
    assert frame["series"].tolist() == ["energy"]
    assert frame["close"].tolist() == [10.0]

    frame, _ = client.load_dataset("market_assets", series=["energy", "metals"])
    assert set(frame["series"]) == {"energy", "metals"}


def test_create_client_reads_jupyterhub_store_environment(monkeypatch, tmp_path) -> None:
    data_uri = f"file:{tmp_path / 'data'}"
    workspace_uri = f"file:{tmp_path / 'workspace'}"
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", data_uri)
    monkeypatch.setenv("RUNBOOK_WORKSPACE_STORE_URI", workspace_uri)

    client = create_client()

    assert client.store.root == open_blob_store(data_uri).root
    assert client.workspace_store is not None
    assert client.workspace_store.root == open_blob_store(workspace_uri).root
