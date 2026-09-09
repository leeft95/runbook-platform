from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import runbook.sdk.prototype as prototype_module
from runbook.core import ReportProfile, Snapshot
from runbook.data.manifests import load_manifest, load_snapshot_dataset, write_manifests
from runbook.sdk import prototype_report, report, required_aliases, snapshot_from_frames
from runbook.sdk.layout import Report
from runbook.sdk.prototype import _MemoryStore


def test_snapshot_from_frames_freezes_exact_aliases_and_is_deterministic() -> None:
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = pd.DataFrame({"timestamp": ["2026-01-01T00:00:00Z"], "close": [100.0]})
    frames = {"prices": prices}
    original = prices.copy(deep=True)

    first = snapshot_from_frames(frames, observed_at=observed, report_id="vol_report")
    second = snapshot_from_frames(frames, observed_at=observed, report_id="vol_report")

    assert first.snapshot_id == second.snapshot_id
    assert first.as_of is None
    assert first.watermark == observed
    assert set(first.datasets) == {"prices"}
    store = _MemoryStore()
    saved = snapshot_from_frames(frames, observed_at=observed, report_id="vol_report", _store=store)
    manifest_ref = next(key for key in store._objects if "/manifests/" in key)
    assert manifest_ref == "curated/vol_report_prices/manifests/2026-01-01T00-00-00.000000Z/1.json"
    assert set(store._objects) == {manifest_ref, "curated/vol_report_prices/version=v1/1.parquet"}
    assert snapshot_from_frames(frames, observed_at=observed, report_id="vol_report", _store=store) == saved
    restored = Snapshot.model_validate_json(saved.model_dump_json())
    assert restored == saved
    pd.testing.assert_frame_equal(load_snapshot_dataset(store, restored, "prices"), original)
    manifest = load_manifest(store, manifest_ref, expected_dataset_id="vol_report_prices")
    assert manifest.watermark == observed
    assert manifest.published_at == observed
    with pytest.raises(IOError, match="immutable blob conflict"):
        store.put_immutable(manifest_ref, b"different")
    store._objects[manifest_ref] = store.get(manifest_ref) + b" "
    with pytest.raises(IOError, match="manifest digest verification failed"):
        load_snapshot_dataset(store, restored, "prices")
    pd.testing.assert_frame_equal(prices, original)


def test_snapshot_from_frames_changes_when_a_frame_changes() -> None:
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    original = pd.DataFrame({"value": [1, 2]})
    changed = original.copy()
    changed.loc[1, "value"] = 3

    first = snapshot_from_frames({"values": original}, observed_at=observed, report_id="demo")
    second = snapshot_from_frames({"values": changed}, observed_at=observed, report_id="demo")

    assert first.snapshot_id != second.snapshot_id
    assert first.datasets == second.datasets
    assert first.manifest_sha256 != second.manifest_sha256


def test_snapshot_from_frames_reuses_parquet_revisions_and_separates_publications() -> None:
    store = _MemoryStore()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frames = {"values": pd.DataFrame({"value": [1]})}
    first = snapshot_from_frames(frames, observed_at=now, report_id="demo", _store=store)
    changed = snapshot_from_frames(
        {"values": pd.DataFrame({"value": [2]})},
        observed_at=now,
        report_id="demo",
        _store=store,
    )
    later = snapshot_from_frames(frames, observed_at=now + timedelta(microseconds=1), report_id="demo", _store=store)
    assert first.datasets["values"] == "curated/demo_values/manifests/2026-01-01T00-00-00.000000Z/1.json"
    assert changed.datasets["values"] == "curated/demo_values/manifests/2026-01-01T00-00-00.000000Z/2.json"
    assert later.datasets["values"] == "curated/demo_values/manifests/2026-01-01T00-00-00.000001Z/1.json"
    assert load_snapshot_dataset(store, first, "values")["value"].tolist() == [1]
    assert load_snapshot_dataset(store, changed, "values")["value"].tolist() == [2]
    assert load_snapshot_dataset(store, later, "values")["value"].tolist() == [1]


def test_snapshot_from_frames_normalizes_offset_watermark() -> None:
    observed = datetime(2026, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    store = _MemoryStore()

    snapshot = snapshot_from_frames(
        {"values": pd.DataFrame({"value": [1]})},
        observed_at=observed,
        report_id="demo",
        _store=store,
    )

    manifest_ref = next(key for key in store._objects if "/manifests/" in key)
    manifest = load_manifest(store, manifest_ref, expected_dataset_id="demo_values")
    expected = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert snapshot.watermark == expected
    assert manifest.watermark == expected
    assert manifest.published_at == expected
    assert manifest_ref == "curated/demo_values/manifests/2026-01-01T00-00-00.000000Z/1.json"


def test_prototype_report_requires_exact_profile_aliases() -> None:
    profile = ReportProfile(profile_id="demo", report_id="vol_report", datasets={"prices": "prices"})
    with pytest.raises(ValueError, match=r"missing=\['prices'\], extra=\['other'\]"):
        prototype_report(profile=profile, frames={"other": pd.DataFrame()})


def test_prototype_report_executes_real_report_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    profile = ReportProfile(
        profile_id="volatility_demo",
        report_id="vol_report",
        datasets={"prices": "demo_daily_prices"},
        params={"price_col": "close", "vol_window": 2},
    )
    prices = pd.read_csv(Path("data/fixtures/daily_prices.csv"))
    before = profile.model_dump(mode="json")
    stores: list[_MemoryStore] = []

    class CapturedStore(_MemoryStore):
        def __init__(self) -> None:
            super().__init__()
            stores.append(self)

    monkeypatch.setattr(prototype_module, "_MemoryStore", CapturedStore)
    result = prototype_report(profile=profile, frames={"prices": prices}, observed_at=observed)

    assert len(stores) == 1
    store = stores[0]
    assert store.exists(result.stage3_ref)
    assert store.exists(result.stage4_ref)
    assert store.exists(result.html_ref)
    assert result.snapshot_id
    assert profile.model_dump(mode="json") == before


def test_prototype_report_executes_supplied_notebook_definition_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    profile = ReportProfile(
        profile_id="notebook_demo",
        report_id="notebook_only_report",
        datasets={"prices": "demo_prices"},
        title="Notebook Demo",
    )
    prices = pd.DataFrame({"value": [1.0, 2.0]})
    aliases = required_aliases(prices="prices")

    @report.calc("returns")
    def returns(ctx):
        return ctx.dataset(aliases.prices).assign(returns=lambda frame: frame["value"].pct_change())

    @report.page
    def page(ctx):
        frame = ctx.calc("returns")
        table_ref = ctx.artifact.table(frame, name="returns")
        layout = Report("Notebook Demo")
        with layout.row(columns=1) as row:
            row.table(table_ref, name="returns_table", title="Returns")
        return layout

    stores: list[_MemoryStore] = []

    class CapturedStore(_MemoryStore):
        def __init__(self) -> None:
            super().__init__()
            stores.append(self)

    monkeypatch.setattr(prototype_module, "_MemoryStore", CapturedStore)
    result = prototype_report(
        profile=profile,
        frames={"prices": prices},
        calculations={"returns": returns},
        page=page,
        observed_at=observed,
    )

    assert result.cache_hits == {"returns": False}
    assert len(stores) == 1
    store = stores[0]
    assert store.exists(result.stage3_ref)
    assert store.exists(result.stage4_ref)
    assert store.exists(result.html_ref)
    assert "Notebook Demo" in store.get(result.html_ref).decode()
    assert set(store._objects) == {
        "curated/notebook_only_report_prices/version=v1/1.parquet",
        "curated/notebook_only_report_prices/manifests/2026-01-01T00-00-00.000000Z/1.json",
        *(
            f"{result.prefix}/{name}"
            for name in (
                "identity.json",
                "calculations/returns.parquet",
                "calculations/returns.meta.json",
                "tables/returns.parquet",
                "manifest.stage3.json",
                "manifest.stage4.json",
                "styles/grid.css",
                "report.html",
            )
        ),
    }


@pytest.mark.parametrize("alias", ["../prices", "prices/other", "prices\\other"])
def test_snapshot_from_frames_rejects_unsafe_names(alias: str) -> None:
    with pytest.raises(ValueError, match="invalid dataset id"):
        snapshot_from_frames({alias: pd.DataFrame()}, observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    "ref",
    [
        "curated/other/manifests/1.json",
        "curated/demo_values/manifests/../1.json",
        "curated/demo_values/manifests/..\\1.json",
        "/curated/demo_values/manifests/1.json",
    ],
)
def test_readable_manifest_refs_reject_wrong_dataset_and_traversal(ref: str) -> None:
    store = _MemoryStore()
    saved = snapshot_from_frames(
        {"values": pd.DataFrame({"value": [1]})},
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        report_id="demo",
        _store=store,
    )
    manifest = load_manifest(store, saved.datasets["values"])
    with pytest.raises(ValueError, match="invalid manifest reference"):
        write_manifests(store, [(manifest, saved.manifest_sha256["values"])], refs={"demo_values": ref})


@pytest.mark.parametrize("digests", [{"values": "invalid"}, {"unknown": "a" * 64}])
def test_snapshot_rejects_invalid_manifest_verification_metadata(digests) -> None:
    saved = snapshot_from_frames(
        {"values": pd.DataFrame({"value": [1]})},
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError):
        Snapshot.model_validate({**saved.model_dump(), "manifest_sha256": digests})


@pytest.mark.parametrize(
    ("calculations", "page", "error"),
    [
        ({"returns": lambda _ctx: None}, None, ValueError),
        (None, lambda _ctx: None, ValueError),
        ({}, lambda _ctx: None, ValueError),
        ({"returns": object()}, lambda _ctx: None, TypeError),
        ({"returns": lambda _ctx: None}, object(), TypeError),
    ],
)
def test_prototype_report_rejects_invalid_notebook_callables(calculations, page, error) -> None:
    profile = ReportProfile(profile_id="demo", report_id="vol_report", datasets={"prices": "prices"})
    with pytest.raises(error):
        prototype_report(
            profile=profile,
            frames={"prices": pd.DataFrame({"price": [1.0]})},
            calculations=calculations,
            page=page,
        )


def test_prototype_report_rejects_non_mapping_calculations() -> None:
    profile = ReportProfile(profile_id="demo", report_id="vol_report", datasets={"prices": "prices"})
    with pytest.raises(TypeError, match="calculations must be a mapping"):
        prototype_report(
            profile=profile,
            frames={"prices": pd.DataFrame({"price": [1.0]})},
            calculations=[lambda _ctx: None],
            page=lambda _ctx: None,
        )
