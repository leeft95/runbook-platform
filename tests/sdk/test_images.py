import base64
import json
import io
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import jsonschema
import pytest
from runbook.core.pdl.models import PDLImageBlock, PDLManifest
from runbook.core.report_artifacts import ArtifactRegistry
from runbook.data import open_blob_store
from runbook.data.manifests import build_snapshot
from runbook.sdk import ui
from runbook.sdk import ReportProfile, execute_report
from runbook.sdk.discovery import ReportDefinition
from runbook.sdk.extensions.dash.renderer import render_dash_page
from runbook.sdk.html import render_html
from runbook.sdk.layout import Grid, Report, Row, Stack, compile_layout, image

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


def _ctx():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(snapshot=SimpleNamespace(snapshot_id="snapshot", as_of=now), config={}, report_id="images")


class Images(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.images = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))


def _walk(component):
    yield component
    children = getattr(component, "children", [])
    for child in children if isinstance(children, (tuple, list)) else [children]:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def test_local_and_hosted_images_survive_manifest_and_both_renderers(tmp_path):
    path = tmp_path / "chart.png"
    path.write_bytes(PNG)
    alt = 'Price chart <daily> "quoted" & labelled'
    url = "https://example.test/chart.png?width=640&height=480"
    layout = Report(
        "Images",
        children=[
            image(path, alt=alt, name="local", title="Price chart"),
            image(url, alt="Hosted chart", name="hosted"),
        ],
    )
    path.unlink()  # The report must not depend on the author's filesystem.
    manifest = compile_layout(_ctx(), layout)
    assert manifest.schema_version == "pdl-core/0.2"
    payload = manifest.model_dump(mode="json", exclude_none=True)
    schema = json.loads(Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json").read_text())
    jsonschema.validate(payload, schema)
    restored = PDLManifest.model_validate_json(manifest.model_dump_json())
    assert base64.b64decode(restored.page.blocks[0].src.split(",", 1)[1]) == PNG
    store = Mock()
    html = render_html(store, restored, "report")
    images = Images(html).images
    assert len(images) == 2
    assert images[0]["alt"] == alt
    assert images[1]["src"] == url
    assert 'alt="Price chart &lt;daily&gt; &quot;quoted&quot; &amp; labelled"' in html
    assert "max-width:100%" in images[0]["style"]
    store.get.assert_not_called()
    definition = ReportDefinition([], {}, lambda _: restored, {})
    page = render_dash_page(restored, definition, _ctx(), namespace="images").layout()
    dash_images = [node for node in _walk(page) if type(node).__name__ == "Img"]
    assert [(node.src, node.alt) for node in dash_images] == [(item["src"], item["alt"]) for item in images]
    assert all(node.style["maxWidth"] == "100%" for node in dash_images)
    assert dash_images[0].id != dash_images[1].id
    payload["schema_version"] = "pdl-core/0.1"
    with pytest.raises(ValueError, match="pdl-core/0.1 does not support"):
        PDLManifest.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


@pytest.mark.parametrize("container", [Grid, Row, Stack])
def test_image_container_convenience_and_spans(container):
    group = container()
    group.image("https://example.test/logo.png", alt="", row_span=2, name="logo")
    manifest = compile_layout(_ctx(), Report("Images", children=[group]))
    block = manifest.page.blocks[0]
    assert isinstance(block, PDLImageBlock)
    assert block.row_span == 2
    assert block.alt == ""


@pytest.mark.parametrize(
    "src",
    [
        "javascript:alert(1)",
        "file:///tmp/image.png",
        "//example.test/image.png",
        "relative.png",
        "https://example.test/space image.png",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "data:image/png;base64,not-base64",
        "data:image/png;base64,aGVsbG8=",
        "data:image/jpeg;base64," + base64.b64encode(PNG).decode(),
    ],
)
def test_persisted_image_rejects_invalid_sources(src):
    with pytest.raises(ValueError):
        PDLImageBlock(name="bad", row=1, col=1, src=src, alt="description")


def test_image_requires_alt_and_rejects_unknown_local_format(tmp_path):
    with pytest.raises(TypeError):
        image("https://example.test/image.png")
    with pytest.raises(TypeError, match="alt"):
        image("https://example.test/image.png", alt=None)
    path = tmp_path / "image.png"
    path.write_text("<html>not an image</html>")
    with pytest.raises(ValueError, match="PNG, JPEG, GIF, or WebP"):
        ui.image(name="bad", src=path, alt="bad", row=1, col=1)
    path.write_bytes(PNG)
    assert ui.image(name="local", src=str(path), alt="local", row=1, col=1).src.startswith("data:image/png;base64,")


def test_image_report_publishes_portable_html(tmp_path):
    path = tmp_path / "chart.png"
    path.write_bytes(PNG)
    store = open_blob_store(f"file:{tmp_path / 'store'}")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = execute_report(
        store=store,
        profile=ReportProfile(profile_id="images", report_id="images", datasets={"source": "source"}),
        snapshot=build_snapshot({}, watermark=now),
        code_version="test-images",
        generated_at=now,
        platform_version="0.0.1",
        _definition=ReportDefinition(["source"], {}, lambda _: Report("Images", children=[image(path, alt="Chart")])),
    )
    path.unlink()
    published = Images(store.get(result.html_ref).decode()).images
    assert base64.b64decode(published[0]["src"].split(",", 1)[1]) == PNG
    stage3 = PDLManifest.model_validate(store.get_json(result.stage3_ref))
    assert stage3.page.blocks[0].src == published[0]["src"]


def test_registered_image_is_published_under_images(tmp_path):
    store = open_blob_store(f"file:{tmp_path / 'store'}")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def page(ctx):
        ref = ctx.artifact.image(PNG, name="chart")
        assert ref == "images/chart.png"
        return Report("Stored image", children=[image(ref=ref, alt="Chart")])

    result = execute_report(
        store=store,
        profile=ReportProfile(profile_id="images", report_id="images", datasets={"source": "source"}),
        snapshot=build_snapshot({}, watermark=now),
        code_version="stored-images",
        generated_at=now,
        platform_version="0.0.1",
        _definition=ReportDefinition(["source"], {}, page),
    )
    assert store.get(f"{result.prefix}/images/chart.png") == PNG
    payload = store.get_json(result.stage3_ref)
    schema = json.loads(Path("packages/runbook/runbook-core/src/runbook/core/pdl/spec-0.2.json").read_text())
    jsonschema.validate(payload, schema)
    manifest = PDLManifest.model_validate(payload)
    assert manifest.page.blocks[0].ref == "images/chart.png"
    assert manifest.page.blocks[0].src is None
    assert manifest.artifacts.files == ["images/chart.png"]
    html = store.get(result.html_ref).decode()
    assert base64.b64decode(Images(html).images[0]["src"].split(",", 1)[1]) == PNG
    ctx = _ctx()
    ctx._artifact_store = store
    ctx._artifact_prefix = result.prefix
    definition = ReportDefinition([], {}, lambda _: manifest, {})
    dash = render_dash_page(manifest, definition, ctx, namespace="stored").layout()
    rendered = next(node for node in _walk(dash) if type(node).__name__ == "Img")
    assert rendered.src == Images(html).images[0]["src"]


@pytest.mark.parametrize("prefixed", [False, True])
def test_s3_image_uses_store_bucket_and_prefix_in_both_renderers(monkeypatch, prefixed):
    client = Mock()
    client.get_object.side_effect = lambda **_: {"Body": io.BytesIO(PNG)}
    boto3 = ModuleType("boto3")
    boto3.client = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    store = open_blob_store("s3://private-reports/base")
    prefix = "reports/example/revision"
    ref = f"{prefix}/images/chart.png" if prefixed else "images/chart.png"
    manifest = compile_layout(_ctx(), Report("Stored", children=[image(ref=ref, alt="Stored chart")]))
    html = render_html(store, manifest, prefix)
    ctx = _ctx()
    ctx._artifact_store = store
    ctx._artifact_prefix = prefix
    definition = ReportDefinition([], {}, lambda _: manifest, {})
    page = render_dash_page(manifest, definition, ctx, namespace="s3-image").layout()
    rendered = next(node for node in _walk(page) if type(node).__name__ == "Img")
    assert rendered.src == Images(html).images[0]["src"]
    assert client.get_object.call_count == 2
    for request in client.get_object.call_args_list:
        assert request.kwargs == {"Bucket": "private-reports", "Key": f"base/{prefix}/images/chart.png"}


def test_image_artifact_duplicate_and_invalid_bytes():
    registry = ArtifactRegistry(table_ref_resolver=lambda _: "unused", table_writer=lambda *_: None)
    assert registry.image(PNG, name="chart") == registry.image(PNG, name="chart")
    assert registry.payloads().image_bytes == {"images/chart.png": PNG}
    with pytest.raises(ValueError, match="Duplicate image"):
        registry.image(PNG + b"different", name="chart")
    with pytest.raises(ValueError, match="PNG, JPEG"):
        registry.image(b"not an image", name="bad")
    with pytest.raises(TypeError, match="image bytes"):
        registry.image("images/chart.png", name="bad")


@pytest.mark.parametrize(
    "ref",
    [
        "../images/a.png",
        "images/../a.png",
        "/images/a.png",
        "images//a.png",
        "s3://bucket/images/a.png",
        "tables/a.png",
        "images/a.png?x=1",
    ],
)
def test_image_ref_rejects_unsafe_or_non_image_paths(ref):
    with pytest.raises(ValueError, match="Image ref"):
        image(ref=ref, alt="invalid")


@pytest.mark.parametrize("sources", [{}, {"src": "https://example.test/a.png", "ref": "images/a.png"}])
def test_image_requires_exactly_one_source(sources):
    with pytest.raises(ValueError, match="exactly one"):
        PDLImageBlock(name="bad", row=1, col=1, alt="invalid", **sources)


def test_missing_stored_image_fails_rendering(tmp_path):
    manifest = compile_layout(_ctx(), Report("Missing", children=[image(ref="images/missing.png", alt="missing")]))
    with pytest.raises(FileNotFoundError):
        render_html(open_blob_store(f"file:{tmp_path}"), manifest, "report")
