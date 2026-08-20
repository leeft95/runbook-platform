from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import dash
import dash_ag_grid as dag
import httpx
import pytest
import uvicorn
from runbook.data import (
    DatabasePointerRegistry,
    DatasetPointerUpdate,
    build_manifest,
    create_pointer_schema,
    open_blob_store,
    write_manifests,
)
from runbook.services import cli
from runbook.services.app import create_app, version_payload
from runbook.services.dash import runs
from runbook.services.dash._config import _profile_new_row, _source_new_row, register_config_page
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.logging import RunLogIdentity, read_log_tail
from runbook.services.models import Base
from runbook.services.repository import ConflictError, RunRepository
from runbook.services.runner import ServiceRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _threaded_runner(**kwargs) -> ServiceRunner:
    """Use threads only for tests that monkeypatch worker callables."""
    return ServiceRunner(
        executor_factory=lambda workers: ThreadPoolExecutor(max_workers=workers),
        **kwargs,
    )


def test_root_version_endpoint_and_dash_mount() -> None:
    app = create_app(database="postgresql+psycopg://postgres:postgres@localhost:5432/runbook")
    assert "/api/v1/sources" in app.openapi()["paths"]
    assert "/api/v1/profiles/{profile_id}/runs" in app.openapi()["paths"]
    pages = [page for module, page in dash.page_registry.items() if module.startswith("runbook.services.dash.")]
    assert {page["path"] for page in pages if page["path_template"] is None} == {
        "/",
        "/profiles",
        "/runs",
        "/sources",
    }
    assert {page["path_template"] for page in pages if page["path_template"]} == {
        "/runs/<run_id>",
        "/runs/<run_id>/logs",
    }
    detail_page, _ = dash._pages._path_to_page("runs/example")
    logs_page, _ = dash._pages._path_to_page("runs/example/logs")
    assert detail_page["module"].endswith(".run_detail")
    assert logs_page["module"].endswith(".run_logs")

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
            assert (await client.get("/ui/sources")).status_code == 200
            assert (await client.get("/ui/runs/example")).status_code == 200
            assert (await client.get("/ui/runs/example/logs")).status_code == 200
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


def test_config_pages_use_grid_editors() -> None:
    create_app(database="postgresql+psycopg://postgres:postgres@localhost:5432/runbook")

    expected = {"runbook.services.dash.sources": "source", "runbook.services.dash.profiles": "profile"}
    for module, kind in expected.items():
        children = dash.page_registry[module]["layout"].children
        components = {component.id: component for component in children if getattr(component, "id", None)}
        prefix = f"runbook-ui-{kind}s"
        assert isinstance(components[f"{prefix}-grid"], dag.AgGrid)
        for button in ("new", "validate", "save", "run", "disable", "refresh"):
            assert f"{prefix}-{button}" in str(dash.page_registry[module]["layout"])

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
    assert "runbook-ui-sources-grid.rowData" in callback_keys
    assert "runbook-ui-sources-result.children" in callback_keys
    assert "runbook-ui-profiles-grid.rowData" in callback_keys
    assert "runbook-ui-profiles-result.children" in callback_keys
    assert "runbook-ui-runs-url.pathname" not in callback_keys
    assert not any(
        any(item["id"] == "runbook-ui-runs-grid" and item["property"] == "cellClicked" for item in callback["inputs"])
        for callback in callback_app.callback_map.values()
    )
    assert "runbook-ui-runs-run-id.options" not in callback_keys
    run_page = dash.page_registry["runbook.services.dash.runs"]["layout"]
    grid = next(child for child in run_page.children if getattr(child, "id", None) == "runbook-ui-runs-grid")
    assert grid.columnDefs[0] == {
        "field": "run_link",
        "headerName": "Run ID",
        "cellRenderer": "markdown",
        "filter": "agTextColumnFilter",
    }
    serialized = runs._run_row(
        SimpleNamespace(
            run_id="run-1",
            kind="source",
            target_id="source-1",
            status="success",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            reason=None,
            snapshot_id=None,
            context_hash=None,
            code_version=None,
            artifact_id=None,
        )
    )
    assert serialized["run_id"] == "run-1"
    assert serialized["run_link"] == "[run-1](/ui/runs/run-1)"


def test_new_config_rows_are_complete_and_disabled() -> None:
    source = _source_new_row()
    assert source["config_id"] == ""
    assert source["enabled"] is False
    assert source["adapter"] == ""
    assert source["schedule"] == {"cron": "0 0 * * *", "timezone": "UTC"}
    assert source["datasets"] == {}
    assert source["params"] == {}
    assert source["revision"] is None
    assert source["_new"] is True
    assert source["_status"] == "draft"
    assert source["_row_key"].startswith("draft:")

    profile = _profile_new_row()
    assert profile["config_id"] == ""
    assert profile["enabled"] is False
    assert profile["report_id"] == ""
    assert profile["title"] == ""
    assert profile["datasets"] == {}
    assert profile["params"] == {}
    assert profile["layout"] == {}
    assert profile["extensions"] == {}
    assert profile["revision"] is None
    assert profile["_new"] is True
    assert profile["_status"] == "draft"
    assert profile["_row_key"].startswith("draft:")
    assert "schedule" not in profile


def test_service_runner_validates_workers_and_ignores_profile_cron(tmp_path) -> None:
    with pytest.raises(ValueError, match="workers must be at least 1"):
        ServiceRunner(workers=0)

    database = f"sqlite:///{tmp_path / 'service.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        with session.begin():
            RunRepository(session).save_config(
                "profile",
                "scheduled_profile",
                {
                    "report_id": "unused_report",
                    "enabled": True,
                    "datasets": {"prices": "prices"},
                },
            )

    runner = ServiceRunner(database=database, data_store=f"file:{tmp_path / 'store'}")
    assert runner.tick(now=datetime(2026, 1, 1, tzinfo=timezone.utc), code_version="test") == []
    with sync_sessions(database)() as session:
        assert RunRepository(session).list_runs() == []


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
                    "title": "Demo",
                    "report_id": "demo_report",
                    "datasets": {"prices": "demo_prices"},
                },
            )
        assert first.revision == 1
        with session.begin():
            same = repository.save_config(
                "profile",
                "demo",
                {
                    "title": "Demo",
                    "report_id": "demo_report",
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
                    "title": "Demo 2",
                    "report_id": "demo_report",
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
                        "title": "Demo 2",
                        "report_id": "demo_report",
                        "datasets": {"prices": "demo_prices"},
                    },
                    expected_revision=99,
                )
        except ConflictError:
            pass
        else:
            raise AssertionError("stale revision was accepted")


def test_source_config_rejects_conflicting_and_published_dataset_ownership() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    create_pointer_schema(engine)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def payload(dataset_id: str) -> dict:
        return {
            "adapter": "local_file",
            "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
            "datasets": {
                "data": {
                    "dataset_id": dataset_id,
                    "parser_id": "csv_timeseries_v1",
                }
            },
            "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
        }

    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            source = repository.save_config("source", "source_a", payload("prices"))
        with pytest.raises(ConflictError, match="configured producer 'source_a'"):
            with session.begin():
                repository.save_config("source", "source_b", payload("prices"))
        assert repository.latest_config("source", "source_b") is None
        session.rollback()

        with session.begin():
            repository.pointer_registry.publish(
                source_id="source_a",
                source_run_id="run-a",
                updates=[
                    DatasetPointerUpdate(
                        dataset_id="prices",
                        manifest_ref="prices-v1",
                        watermark=stamp,
                        published_at=stamp,
                    )
                ],
            )
        with pytest.raises(ConflictError, match="cannot be removed"):
            with session.begin():
                repository.save_config(
                    "source",
                    "source_a",
                    payload("volume"),
                    expected_revision=source.revision,
                )


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


def test_service_runner_fans_out_ready_dataset_to_report(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'service.db'}"
    data_store = f"file:{tmp_path / 'store'}"
    source_file = tmp_path / "prices.csv"
    source_file.write_text(
        "timestamp,close\n2026-01-01T00:00:00Z,100\n2026-01-02T00:00:00Z,102\n",
        encoding="utf-8",
    )
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            repository.save_config(
                "source",
                "prices_source",
                {
                    "adapter": "local_file",
                    "enabled": True,
                    "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
                    "datasets": {
                        "prices": {
                            "dataset_id": "prices",
                            "parser_id": "csv_timeseries_v1",
                            "update_mode": "full",
                        }
                    },
                    "params": {"local_path": str(source_file), "timestamp_column": "timestamp"},
                },
            )
            repository.save_config(
                "profile",
                "volatility",
                {
                    "report_id": "vol_report",
                    "enabled": True,
                    "datasets": {"prices": "prices"},
                    "params": {"price_col": "close", "vol_window": 2},
                },
            )

    outcomes = ServiceRunner(
        database=database,
        data_store=data_store,
        report_root="reports",
        workers=2,
    ).tick(now=datetime(2026, 1, 2, tzinfo=timezone.utc), code_version="test")

    assert [(item["kind"], item["status"]) for item in outcomes] == [
        ("source", "success"),
        ("profile", "success"),
    ]
    with sync_sessions(database)() as session:
        rows = RunRepository(session).list_runs(limit=10)
        profile_run = next(row for row in rows if row.kind == "profile")
        source_run = next(row for row in rows if row.kind == "source")
        assert profile_run.trigger == "dataset"
        assert profile_run.artifact_id
        assert profile_run.result["snapshot"]["snapshot_id"] == profile_run.snapshot_id
        assert profile_run.result["snapshot"]["datasets"]["prices"]
        pointer = RunRepository(session).pointer_registry.get(["prices"])["prices"]
        assert pointer.source_id == "prices_source"
        assert pointer.source_run_id == source_run.run_id
        assert read_log_tail(
            open_blob_store(data_store),
            RunLogIdentity(
                source_run.run_id,
                "source",
                source_run.target_id,
                source_run.slot.replace(tzinfo=timezone.utc),
            ),
        )["complete"]
        assert read_log_tail(
            open_blob_store(data_store),
            RunLogIdentity(
                profile_run.run_id,
                "profile",
                profile_run.target_id,
                profile_run.slot.replace(tzinfo=timezone.utc),
                report_id="vol_report",
            ),
        )["complete"]
    assert not open_blob_store(data_store).exists("pointers.json")


def test_service_runner_imports_legacy_pointers_once(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'service.db'}"
    data_store = open_blob_store(f"file:{tmp_path / 'store'}")
    upgrade_with_metadata(database)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    manifest, digest = build_manifest(dataset_id="prices", watermark=stamp, published_at=stamp, files=[])
    ref = write_manifests(data_store, [(manifest, digest)])["prices"]
    data_store.put_json("pointers.json", {"prices": ref})
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            repository.save_config(
                "source",
                "prices_source",
                {
                    "adapter": "local_file",
                    "enabled": False,
                    "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
                    "datasets": {
                        "prices": {
                            "dataset_id": "prices",
                            "parser_id": "csv_timeseries_v1",
                            "update_mode": "full",
                        }
                    },
                    "params": {
                        "local_path": "unused.csv",
                        "timestamp_column": "timestamp",
                    },
                },
            )

    runner = ServiceRunner(database=database, data_store=f"file:{tmp_path / 'store'}")
    assert runner.tick(now=stamp, code_version="test") == []
    assert runner.tick(now=stamp, code_version="test") == []
    registry = DatabasePointerRegistry(create_engine(database))
    pointer = registry.get(["prices"])["prices"]
    assert pointer.manifest_ref == ref
    assert pointer.source_id == "prices_source"
    assert pointer.source_run_id == "legacy-pointer-import"
    assert data_store.get_json("pointers.json") == {"prices": ref}
