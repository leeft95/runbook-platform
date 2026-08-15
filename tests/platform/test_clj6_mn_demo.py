from __future__ import annotations

from datetime import datetime, timezone

from runbook.data import load_source_configs, open_blob_store, resolve_snapshot
from runbook.platform.report_run import run_report
from runbook.platform.source_run import run_source
from runbook.sdk import RunbookClient, load_profiles


class _ReadOnlyBlobStore:
    """Expose data-store reads while rejecting preview writes."""

    def __init__(self, store):
        self._store = store

    def get(self, key):
        return self._store.get(key)

    def get_json(self, key):
        return self._store.get_json(key)

    def exists(self, key):
        return self._store.exists(key)

    def put(self, *_args, **_kwargs):
        raise AssertionError("preview wrote to the data store")

    def put_json(self, *_args, **_kwargs):
        raise AssertionError("preview wrote to the data store")

    def put_immutable(self, *_args, **_kwargs):
        raise AssertionError("preview wrote to the data store")


def test_synthetic_demo_proves_source_to_html_flow(tmp_path) -> None:
    """Prove two fixture sources feed two deterministic report outputs."""
    data_store = open_blob_store(f"file:{tmp_path / 'data'}")
    workspace_store = open_blob_store(f"file:{tmp_path / 'workspace'}")
    slot = datetime(2026, 1, 4, 10, tzinfo=timezone.utc)

    sources = load_source_configs("data/contract/source_configs.json")
    for source_id in ("demo_daily_prices", "demo_intraday_bars"):
        outcome = run_source(
            store=data_store,
            config=sources[source_id],
            slot=slot,
        )
        assert outcome.status == "success"

    profiles = load_profiles("data/contract/report_profiles.json")
    snapshot_profile = profiles["timeseries_snapshot_demo"]
    volatility_profile = profiles["volatility_demo"]
    assert snapshot_profile.enabled
    assert volatility_profile.enabled
    assert snapshot_profile.datasets["daily_prices"] == volatility_profile.datasets["prices"]

    production_results = {}
    for profile in (snapshot_profile, volatility_profile):
        outcome = run_report(
            store=data_store,
            profile=profile,
            slot=slot,
            code_version="demo",
        )
        assert outcome.status == "success"
        production_results[profile.profile_id] = outcome.as_dict()
        assert not data_store.exists(f"runs/reports/{profile.profile_id}")

    pointers_before = data_store.get_json("pointers.json")
    client = RunbookClient(
        store=_ReadOnlyBlobStore(data_store),
        workspace_store=workspace_store,
    )
    cold_hits = {}
    warm_hits = {}
    for profile in (snapshot_profile, volatility_profile):
        cold = client.preview(profile, code_version="demo")
        warm = client.preview(profile, code_version="demo")
        cold_hits[profile.profile_id] = cold.cache_hits
        warm_hits[profile.profile_id] = warm.cache_hits

        production = production_results[profile.profile_id]
        assert data_store.get(production["stage3_ref"]) == workspace_store.get(cold.stage3_ref)
        assert data_store.get(production["html_ref"]) == workspace_store.get(cold.html_ref)
        assert workspace_store.exists(cold.stage3_ref)
        assert workspace_store.exists(cold.html_ref)
        assert b"<!doctype html>" in workspace_store.get(cold.html_ref)

    assert data_store.get_json("pointers.json") == pointers_before
    assert cold_hits["timeseries_snapshot_demo"] == {
        "comparison": False,
        "daily_returns": False,
        "intraday_daily": False,
    }
    assert warm_hits["timeseries_snapshot_demo"] == {
        "comparison": True,
        "daily_returns": True,
    }
    assert cold_hits["volatility_demo"] == {"returns": False, "vol": False}
    assert warm_hits["volatility_demo"] == {"returns": True, "vol": True}

    snapshot = resolve_snapshot(data_store, snapshot_profile.datasets)
    volatility_snapshot = resolve_snapshot(data_store, volatility_profile.datasets)
    assert set(snapshot.datasets) == {"daily_prices", "intraday_bars"}
    assert volatility_snapshot.datasets["prices"] == snapshot.datasets["daily_prices"]
