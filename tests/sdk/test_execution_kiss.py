from __future__ import annotations

from datetime import datetime, timezone
from functools import partial

import pandas as pd
from plotly.offline import get_plotlyjs_version
from runbook.core.data import DatasetFile
from runbook.data import open_blob_store
from runbook.data.manifests import (
    build_manifest,
    publish_manifests,
    resolve_snapshot,
    write_dataframe,
)
from runbook.sdk import ReportProfile, execute_report


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
