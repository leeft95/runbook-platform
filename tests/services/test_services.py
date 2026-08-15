from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import dash
import httpx
import uvicorn
from dash import dcc, html
from runbook.services import cli
from runbook.services import runner as runner_module
from runbook.services.app import create_app, version_payload
from runbook.services.dash import runs
from runbook.services.dash._config import _config_skeleton, register_config_page
from runbook.services.models import Base
from runbook.services.repository import ConflictError, RunRepository
from runbook.services.runner import ServiceRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_root_version_endpoint_and_dash_mount() -> None:
    app = create_app(database="postgresql+psycopg://postgres:postgres@localhost:5432/runbook")
    assert "/api/v1/sources" in app.openapi()["paths"]
    assert "/api/v1/profiles/{profile_id}/runs" in app.openapi()["paths"]
    assert {
        page["path"] for module, page in dash.page_registry.items() if module.startswith("runbook.services.dash.")
    } == {"/", "/profiles", "/runs"}

    async def check_routes() -> None:
        startup = asyncio.Event()
        shutdown = asyncio.Event()
        events: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        await events.put({"type": "lifespan.startup"})

        async def receive() -> dict[str, str]:
            return await events.get()

        async def send(message: dict[str, str]) -> None:
            if message["type"] == "lifespan.startup.complete":
                startup.set()
            elif message["type"] == "lifespan.shutdown.complete":
                shutdown.set()

        lifespan = asyncio.create_task(
            app(
                {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}},
                receive,
                send,
            )
        )
        await startup.wait()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/")
            assert response.json() == version_payload()
            assert (await client.get("/ui/")).status_code == 200
            assert (await client.get("/ui/profiles")).status_code == 200
            assert (await client.get("/ui/runs")).status_code == 200
            assert (await client.get("/docs")).status_code == 200
        await events.put({"type": "lifespan.shutdown"})
        await shutdown.wait()
        await lifespan

    asyncio.run(check_routes())


def test_serve_reload_uses_uvicorn_factory(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert (
        cli.main(
            [
                "--database",
                "sqlite:///test.db",
                "serve",
                "--reload",
                "--store",
                "file:.runbook-test",
                "--reports-root",
                "reports-test",
            ]
        )
        == 0
    )
    assert captured == {
        "app": "runbook.services.app:create_app",
        "factory": True,
        "host": "127.0.0.1",
        "port": 8050,
        "reload": True,
    }


def test_id_selectors_are_database_backed_dropdowns() -> None:
    create_app(database="postgresql+psycopg://postgres:postgres@localhost:5432/runbook")

    expected = {
        "runbook.services.dash.sources": [
            "runbook-ui-sources-config-id",
            "runbook-ui-sources-revision",
            "runbook-ui-sources-trigger-id",
        ],
        "runbook.services.dash.profiles": [
            "runbook-ui-profiles-config-id",
            "runbook-ui-profiles-revision",
            "runbook-ui-profiles-trigger-id",
        ],
        "runbook.services.dash.runs": ["runbook-ui-runs-run-id"],
    }
    for module, component_ids in expected.items():
        children = dash.page_registry[module]["layout"].children
        components = {component.id: component for component in children if getattr(component, "id", None)}
        for component_id in component_ids:
            assert isinstance(components[component_id], dcc.Dropdown)
            assert components[component_id].options == []
        if module.endswith(("sources", "profiles")):
            kind = module.rsplit(".", 1)[-1][:-1]
            assert isinstance(components[f"runbook-ui-{kind}s-new"], html.Button)

    callback_app = dash.Dash(__name__, use_pages=True, pages_folder="")
    register_config_page(
        callback_app,
        None,
        module="tests.services.dropdown_sources",
        kind="source",
        path="/dropdown-sources",
        name="Sources",
        order=10,
    )
    register_config_page(
        callback_app,
        None,
        module="tests.services.dropdown_profiles",
        kind="profile",
        path="/dropdown-profiles",
        name="Profiles",
        order=11,
    )
    runs.register(callback_app, None)
    callback_keys = "\n".join(callback_app.callback_map)
    assert "runbook-ui-sources-config-id.options" in callback_keys
    assert "runbook-ui-sources-trigger-id.options" in callback_keys
    assert "runbook-ui-sources-revision.options" in callback_keys
    assert "runbook-ui-sources-revision.value" in callback_keys
    assert "runbook-ui-profiles-config-id.options" in callback_keys
    assert "runbook-ui-profiles-trigger-id.options" in callback_keys
    assert "runbook-ui-profiles-revision.options" in callback_keys
    assert "runbook-ui-profiles-revision.value" in callback_keys
    assert "runbook-ui-runs-run-id.options" in callback_keys


def test_new_config_skeletons_are_complete_and_disabled() -> None:
    source = _config_skeleton("source")
    assert source == {
        "source_id": "",
        "enabled": False,
        "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
        "adapter": "",
        "datasets": {
            "dataset_alias": {
                "dataset_id": "",
                "schema_version": "v1",
                "partition_keys": [],
                "parser_id": "",
                "update_mode": "append",
            }
        },
        "params": {},
    }
    assert _config_skeleton("profile") == {
        "profile_id": "",
        "enabled": False,
        "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
        "report_id": "",
        "title": "",
        "datasets": {"dataset_alias": ""},
        "params": {},
        "layout": {},
        "extensions": {},
    }


def test_config_revisions_are_immutable_and_compare_and_swap() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            first = repository.save_config(
                "profile",
                "demo",
                {
                    "report_id": "demo_report",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "demo_prices"},
                },
            )
        assert first.revision == 1
        with session.begin():
            same = repository.save_config(
                "profile",
                "demo",
                {
                    "report_id": "demo_report",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "demo_prices"},
                },
                expected_revision=1,
            )
        assert same.revision == 1
        with session.begin():
            second = repository.save_config(
                "profile",
                "demo",
                {
                    "report_id": "demo_report",
                    "schedule": {"cron": "15 * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "demo_prices"},
                },
                expected_revision=1,
            )
        assert second.revision == 2
        assert [row.revision for row in repository.list_config_revisions("profile", "demo")] == [2, 1]
        session.rollback()
        try:
            with session.begin():
                repository.save_config(
                    "profile",
                    "demo",
                    {
                        "report_id": "demo_report",
                        "schedule": {"cron": "15 * * * *", "timezone": "UTC"},
                        "datasets": {"prices": "demo_prices"},
                    },
                    expected_revision=99,
                )
        except ConflictError:
            pass
        else:
            raise AssertionError("stale revision was accepted")


def test_run_queue_reuses_active_identity() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config(
                "profile",
                "demo",
                {
                    "report_id": "demo_report",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "demo_prices"},
                },
            )
        with session.begin():
            first = repository.queue_run(
                kind="profile",
                target_id="demo",
                slot=slot,
                trigger="manual",
                force=False,
                config=config,
            )
        with session.begin():
            second = repository.queue_run(
                kind="profile",
                target_id="demo",
                slot=slot,
                trigger="manual",
                force=False,
                config=config,
            )
        assert second.run_id == first.run_id


def test_service_runner_persists_report_artifact_references(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = SimpleNamespace(snapshot_id="snapshot", watermark=slot)
    result = {
        "profile_id": "demo",
        "slot": "20260101T000000Z",
        "status": "success",
        "artifact_id": "artifact",
        "snapshot_id": "snapshot",
        "context_hash": "context",
        "code_version": "code",
        "prefix": "reports/demo/1",
        "html_ref": "reports/demo/1/report.html",
        "stage3_ref": "reports/demo/1/manifest.stage3.json",
        "stage4_ref": "reports/demo/1/manifest.stage4.json",
        "reason": None,
    }
    monkeypatch.setattr(runner_module, "resolve_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(runner_module, "resolve_code_version", lambda *_args, **_kwargs: "code")
    monkeypatch.setattr(runner_module, "run_report", lambda **_kwargs: SimpleNamespace(as_dict=lambda: result))
    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config(
                "profile",
                "demo",
                {
                    "report_id": "demo_report",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "demo_prices"},
                },
            )
        with session.begin():
            row = repository.queue_run(
                kind="profile",
                target_id="demo",
                slot=slot,
                trigger="manual",
                force=False,
                config=config,
            )
        outcome = ServiceRunner(data_store=f"file:{tmp_path}")._execute(
            session,
            repository,
            row,
            code_version="code",
        )
        session.commit()
        assert outcome["status"] == "success"
        assert row.snapshot_id == "snapshot"
        assert row.artifact_id == "artifact"
        assert row.result["stage3_ref"] == "reports/demo/1/manifest.stage3.json"
        assert not (tmp_path / "runs").exists()
