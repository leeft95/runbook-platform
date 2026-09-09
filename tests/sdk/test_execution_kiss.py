from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import partial
from types import SimpleNamespace

import pandas as pd
import pytest
import runbook.sdk.execution as execution_module
from plotly.offline import get_plotlyjs_version
from runbook.core.data import DatasetFile
from runbook.core.pdl.models import PDLArtifacts, PDLManifest, PDLPage, PDLPageType, PDLTextBlock
from runbook.data import open_blob_store
from runbook.data.manifests import (
    build_manifest,
    build_snapshot,
    publish_manifests,
    resolve_snapshot,
    write_dataframe,
)
from runbook.sdk import ReportProfile, execute_report
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.layout import Report


def test_report_execution_is_shared_and_cache_is_type_stable(tmp_path, pointer_registry) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ref, digest = write_dataframe(store, "prices", pd.DataFrame({"price": [100.0, 101.0, 102.0]}))
    manifest, manifest_digest = build_manifest(
        dataset_id="prices",
        watermark=now,
        published_at=now,
        files=[DatasetFile(ref=ref, sha256=digest, partition={"date": "2026-01"})],
    )
    publish_manifests(
        store,
        [(manifest, manifest_digest)],
        pointer_registry=pointer_registry,
        source_id="prices_source",
        source_run_id="fixture",
    )
    snapshot = resolve_snapshot(store, {"prices": "prices"}, pointer_registry=pointer_registry)
    profile = ReportProfile(
        profile_id="vol_dev",
        report_id="vol_report",
        datasets={"prices": "prices"},
        params={"vol_window": 2},
    )
    run = partial(
        execute_report,
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version="test",
        reports_root="reports",
        generated_at=now,
        platform_version="0.0.1",
    )
    cold = run()
    warm = run()
    assert cold.artifact_id == warm.artifact_id
    assert cold.prefix == "reports/vol_report/date=2026-01-01/version=0.0.1/1"
    assert cold.prefix == warm.prefix
    assert store.get_json(f"{cold.prefix}/identity.json")["artifact_id"] == cold.artifact_id
    assert cold.cache_hits == {"returns": False, "vol": False}
    assert warm.cache_hits == {"returns": True, "vol": True}
    cache_files = list(tmp_path.joinpath(cold.prefix, "calculations").glob("*.meta.json"))
    assert {path.name for path in cache_files} == {"returns.meta.json", "vol.meta.json"}
    assert not tmp_path.joinpath("cache").exists()
    assert all(
        not re.search(r"[0-9a-f]{32,}", path.relative_to(tmp_path).as_posix())
        for path in tmp_path.joinpath("reports").rglob("*")
    )
    assert store.get(cold.stage3_ref) == store.get(warm.stage3_ref)
    assert store.get_json(cold.stage3_ref)["style"] is None
    stage4 = store.get_json(cold.stage4_ref)
    assert stage4["style"] == {
        "css_ref": "styles/grid.css",
        "source_key": "simple_grid",
        "source_type": "default",
    }
    assert b".rb-page" in store.get(f"{cold.prefix}/styles/grid.css")
    html = store.get(cold.html_ref)
    assert b"<!doctype html>" in html
    assert b"<style>" in html
    assert b".rb-page" in html
    assert b'<link rel="stylesheet" href="styles/grid.css">' not in html
    assert b'class="rb-page"' in html
    assert b"grid-row: 1 / span 1; grid-column: 1 / span 1;" in html
    plotly_cdn_url = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js".encode()
    assert html.count(plotly_cdn_url) == 1

    changed = run(profile=profile.model_copy(update={"title": "Changed title"}))
    assert changed.artifact_id != cold.artifact_id
    assert changed.prefix == "reports/vol_report/date=2026-01-01/version=0.0.1/2"


def test_readable_calculations_keep_types_and_report_revision_isolation(tmp_path) -> None:
    store = open_blob_store(f"file:{tmp_path}")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = build_snapshot({}, watermark=now)
    profile = ReportProfile(profile_id="cache", report_id="cache_demo", datasets={"source": "source"})
    values = {
        "settings": {"nested": [1, True, "readable"]},
        "nothing": None,
        "prices": pd.Series([1.0, 2.0], name="price", index=pd.Index(["a", "b"], name="asset")),
        "summary": pd.DataFrame({"total": [3.0]}),
    }
    calls: list[str] = []

    def calculate(ctx, *, name):
        calls.append(name)
        return values[name]

    def page(ctx):
        assert ctx.calc("settings") == values["settings"]
        assert ctx.calc("nothing") is None
        pd.testing.assert_series_equal(ctx.calc("prices"), values["prices"])
        pd.testing.assert_frame_equal(ctx.calc("summary"), values["summary"])
        layout = Report("Cache types")
        with layout.grid(columns=1) as grid:
            grid.text("ok")
        return layout

    run = partial(
        execute_report,
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version="first",
        generated_at=now,
        platform_version="0.0.1",
        _definition=ReportDefinition(["source"], {name: partial(calculate, name=name) for name in values}, page),
    )
    cold = run()
    warm = run()
    assert cold.prefix == warm.prefix == "reports/cache_demo/date=2026-01-01/version=0.0.1/1"
    assert cold.cache_hits == dict.fromkeys(values, False)
    assert warm.cache_hits == dict.fromkeys(values, True)
    assert calls == list(values)
    assert {path.name for path in tmp_path.joinpath(cold.prefix, "calculations").iterdir()} == {
        "settings.meta.json",
        "settings.json",
        "nothing.meta.json",
        "prices.meta.json",
        "prices.parquet",
        "summary.meta.json",
        "summary.parquet",
    }
    changes = [
        ({"profile": profile.model_copy(update={"params": {"window": 2}})}, "date=2026-01-01/version=0.0.1/2"),
        ({"snapshot": build_snapshot({}, watermark=now + timedelta(seconds=1))}, "date=2026-01-01/version=0.0.1/3"),
        ({"code_version": "second"}, "date=2026-01-01/version=0.0.1/4"),
        ({"generated_at": now + timedelta(days=1)}, "date=2026-01-02/version=0.0.1/1"),
        ({"platform_version": "0.0.2"}, "date=2026-01-01/version=0.0.2/1"),
    ]
    for kwargs, suffix in changes:
        changed = run(**kwargs)
        assert changed.prefix == f"reports/cache_demo/{suffix}"
        assert changed.cache_hits == dict.fromkeys(values, False)
        assert run(**kwargs).cache_hits == dict.fromkeys(values, True)
    assert len(calls) == len(values) * (len(changes) + 1)

    original = store.get(f"{cold.prefix}/calculations/settings.json")
    values["settings"] = {"changed": True}
    with pytest.raises(IOError, match="immutable blob conflict.*calculations/settings.json"):
        run(use_cache=False)
    assert store.get(f"{cold.prefix}/calculations/settings.json") == original


def test_execute_report_reconciles_registered_plot_refs_into_stage3_manifest(tmp_path, monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = open_blob_store(f"file:{tmp_path}")
    source_manifest = PDLManifest(
        schema_version="pdl-core/0.2",
        title="Plot refs",
        snapshot_id="source",
        as_of=now,
        page=PDLPage(
            page_type=PDLPageType.grid,
            rows=1,
            columns=1,
            blocks=[PDLTextBlock(name="summary", text="ok", row=1, col=1)],
        ),
        artifacts=PDLArtifacts(
            plots=["plots/existing.json"],
            tables=["tables/existing.parquet"],
            files=["styles/existing.json"],
        ),
    )

    def page(ctx):
        ctx.artifact.plot({"data": [], "layout": {"title": {"text": "z"}}}, name="z")
        ctx.artifact.plot({"data": [], "layout": {"title": {"text": "a"}}}, name="a")
        return source_manifest

    definition = ReportDefinition(["source"], {}, page, {})
    monkeypatch.setattr(execution_module, "resolve_report_path", lambda *_args: "reports/demo.py")
    monkeypatch.setattr(execution_module, "load_report_module", lambda _path: SimpleNamespace())
    monkeypatch.setattr(execution_module, "discover_report_definition", lambda _module: definition)

    result = execute_report(
        store=store,
        profile=ReportProfile(profile_id="plot-refs", report_id="demo", datasets={"source": "source"}),
        snapshot=SimpleNamespace(snapshot_id="snapshot", watermark=now, warnings=()),
        code_version="test",
        reports_root="reports",
        generated_at=now,
        platform_version="0.0.1",
    )

    persisted = store.get_json(result.stage3_ref)
    assert persisted["schema_version"] == "pdl-core/0.2"
    assert persisted["artifacts"] == {
        "plots": ["plots/a.json", "plots/existing.json", "plots/z.json"],
        "tables": ["tables/existing.parquet"],
        "files": ["styles/existing.json"],
    }
