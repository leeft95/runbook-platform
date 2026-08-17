from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace

import dash
import httpx
import pytest
import uvicorn
from dash import dcc, html
from runbook.data import (
    DatabasePointerRegistry,
    DatasetPointerUpdate,
    build_manifest,
    create_pointer_schema,
    open_blob_store,
    write_manifests,
)
from runbook.data.ingest import (
    AcquisitionResult,
    AcquisitionStageResult,
    CurationResult,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)
from runbook.services import cli
from runbook.services import runner as runner_module
from runbook.services.app import create_app, version_payload
from runbook.services.dash import runs
from runbook.services.dash._config import _config_skeleton, register_config_page
from runbook.services.db import sync_sessions, upgrade_with_metadata
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
                    "schedule": {"cron": "* * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "prices"},
                },
            )

    runner = ServiceRunner(database=database, data_store=f"file:{tmp_path / 'store'}")
    assert runner.tick(now=datetime(2026, 1, 1, tzinfo=timezone.utc), code_version="test") == []
    with sync_sessions(database)() as session:
        assert RunRepository(session).list_runs() == []


def test_tick_orders_persisted_and_newly_scheduled_rows(monkeypatch, tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'service.db'}"
    upgrade_with_metadata(database)
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current = datetime(2026, 1, 2, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config(
                "source",
                "prices_source",
                {
                    "adapter": "local_file",
                    "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
                    "datasets": {
                        "prices": {
                            "dataset_id": "prices",
                            "parser_id": "csv_timeseries_v1",
                            "update_mode": "full",
                        }
                    },
                    "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
                },
            )
            repository.queue_run(
                kind="source",
                target_id="prices_source",
                slot=earlier,
                trigger="manual",
                force=False,
                config=config,
            )

    def not_ready(*, source_config, slot, **_kwargs):
        readiness = ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=slot.isoformat(),
            status=ReadinessStatus.not_ready,
            observed_at=slot,
        )
        return AcquisitionStageResult(
            acquisition_run=slot.isoformat(),
            status=ReadinessStatus.not_ready,
            readiness=readiness,
            message="not ready",
        )

    monkeypatch.setattr(runner_module, "run_stage1_acquire", not_ready)
    outcomes = ServiceRunner(database=database, data_store=f"file:{tmp_path / 'store'}").tick(
        now=current,
        code_version="test",
    )

    assert [item["status"] for item in outcomes] == ["not_ready", "not_ready"]
    assert [item["slot"] for item in outcomes] == [earlier.isoformat(), current.isoformat()]
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
    snapshot = SimpleNamespace(snapshot_id="snapshot", watermark=slot - timedelta(days=1))
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
        outcomes = ServiceRunner(data_store=f"file:{tmp_path}")._run_dag(
            session,
            repository,
            [row],
            [],
            {},
            code_version="code",
        )
        session.commit()
        outcome = outcomes[0]
        assert outcome["status"] == "success"
        assert row.snapshot_id == "snapshot"
        assert row.artifact_id == "artifact"
        assert row.result["stage3_ref"] == "reports/demo/1/manifest.stage3.json"
        assert not (tmp_path / "runs").exists()


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
                    "schedule": {"cron": "30 0 * * *", "timezone": "UTC"},
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
        assert profile_run.trigger == "dataset"
        assert profile_run.artifact_id
        pointer = RunRepository(session).pointer_registry.get(["prices"])["prices"]
        assert pointer.source_id == "prices_source"
        assert pointer.source_run_id == next(row.run_id for row in rows if row.kind == "source")
    assert not open_blob_store(data_store).exists("pointers.json")


@pytest.mark.parametrize("has_previous_snapshot", [False, True])
def test_curation_failure_uses_previous_complete_snapshot_only(
    monkeypatch,
    tmp_path,
    has_previous_snapshot,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    create_pointer_schema(engine)
    store = open_blob_store(f"file:{tmp_path}")
    slot = datetime(2026, 1, 2, tzinfo=timezone.utc)
    previous = slot - timedelta(days=1)

    def acquire(*, source_config, slot, **_kwargs):
        readiness = ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=slot.isoformat(),
            status=ReadinessStatus.ready,
            observed_at=slot,
        )
        acquired = AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=slot.isoformat(),
                artifact_ref="raw/current",
                content_sha256="0" * 64,
                source_filename="data.csv",
                fetched_at=slot,
            ),
            payload=b"data",
        )
        return AcquisitionStageResult(
            acquisition_run=slot.isoformat(),
            status=ReadinessStatus.ready,
            readiness=readiness,
            acquired=acquired,
        )

    def fail_curation(**_kwargs):
        raise RuntimeError("curation failed")

    report_result = {
        "profile_id": "dependent",
        "slot": "20260101T000000Z",
        "status": "success",
        "artifact_id": "old-snapshot-artifact",
        "snapshot_id": "old-snapshot",
        "context_hash": "context",
        "code_version": "test",
        "prefix": "reports/dependent/old",
        "html_ref": "reports/dependent/old/report.html",
        "stage3_ref": "reports/dependent/old/manifest.stage3.json",
        "stage4_ref": "reports/dependent/old/manifest.stage4.json",
        "reason": None,
    }
    monkeypatch.setattr(runner_module, "run_stage1_acquire", acquire)
    monkeypatch.setattr(runner_module, "run_stage2_curate", fail_curation)
    monkeypatch.setattr(
        runner_module,
        "run_report",
        lambda **_kwargs: SimpleNamespace(as_dict=lambda: report_result),
    )

    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            source_config = repository.save_config(
                "source",
                "prices_source",
                {
                    "adapter": "local_file",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {
                        "prices": {
                            "dataset_id": "prices",
                            "parser_id": "csv_timeseries_v1",
                            "update_mode": "full",
                        }
                    },
                    "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
                },
            )
            profile_config = repository.save_config(
                "profile",
                "dependent",
                {
                    "report_id": "unused_report",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {"prices": "prices"},
                },
            )
        if has_previous_snapshot:
            manifest, digest = build_manifest(
                dataset_id="prices",
                watermark=previous,
                published_at=previous,
                files=[],
            )
            ref = write_manifests(store, [(manifest, digest)])["prices"]
            with session.begin():
                repository.pointer_registry.publish(
                    source_id="prices_source",
                    source_run_id="previous-run",
                    updates=[
                        DatasetPointerUpdate(
                            dataset_id="prices",
                            manifest_ref=ref,
                            watermark=previous,
                            published_at=previous,
                        )
                    ],
                )
        with session.begin():
            source_run = repository.queue_run(
                kind="source",
                target_id="prices_source",
                slot=slot,
                trigger="manual",
                force=False,
                config=source_config,
            )
        outcomes = ServiceRunner(data_store=f"file:{tmp_path}", workers=2)._run_dag(
            session,
            repository,
            [source_run],
            [profile_config],
            {"prices": "prices_source"},
            code_version="test",
        )

        assert outcomes[0]["status"] == "failed"
        profile_runs = repository.list_runs(kind="profile")
        if has_previous_snapshot:
            assert outcomes[1]["status"] == "success"
            assert len(profile_runs) == 1
            assert profile_runs[0].trigger == "dataset"
            assert profile_runs[0].slot.replace(tzinfo=timezone.utc) == previous
        else:
            assert len(outcomes) == 1
            assert profile_runs == []


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
                    "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
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


def test_service_runner_acquires_distinct_sources_concurrently(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    create_pointer_schema(engine)
    barrier = Barrier(2)
    slot = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def acquire(*, source_config, slot, **_kwargs):
        barrier.wait(timeout=2)
        readiness = ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=source_config.source_id,
            status=ReadinessStatus.ready,
            observed_at=slot,
        )
        acquired = AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=source_config.source_id,
                artifact_ref=f"raw/{source_config.source_id}",
                content_sha256="0" * 64,
                source_filename="data.csv",
                fetched_at=slot,
            ),
            payload=b"data",
        )
        return AcquisitionStageResult(
            acquisition_run=source_config.source_id,
            status=ReadinessStatus.ready,
            readiness=readiness,
            acquired=acquired,
        )

    def curate(*, source_config, acquired, **_kwargs):
        update = DatasetPointerUpdate(
            dataset_id=next(iter(binding.dataset_id for binding in source_config.datasets.values())),
            manifest_ref=f"manifest/{source_config.source_id}",
            watermark=slot,
            published_at=slot,
        )
        return CurationResult(
            datasets={update.dataset_id: update.manifest_ref},
            pointer_updates=(update,),
        )

    monkeypatch.setattr(runner_module, "run_stage1_acquire", acquire)
    monkeypatch.setattr(runner_module, "run_stage2_curate", curate)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        rows = []
        with session.begin():
            for source_id in ("source_a", "source_b"):
                config = repository.save_config(
                    "source",
                    source_id,
                    {
                        "adapter": "local_file",
                        "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                        "datasets": {
                            "data": {
                                "dataset_id": f"{source_id}_data",
                                "parser_id": "csv_timeseries_v1",
                            }
                        },
                        "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
                    },
                )
                rows.append(
                    repository.queue_run(
                        kind="source",
                        target_id=source_id,
                        slot=slot,
                        trigger="manual",
                        force=False,
                        config=config,
                    )
                )
        outcomes = ServiceRunner(data_store=f"file:{tmp_path}", workers=2)._run_dag(
            session,
            repository,
            rows,
            [],
            {},
            code_version="test",
        )

    assert [outcome["status"] for outcome in outcomes] == ["success", "success"]


def test_service_runner_orders_same_source_by_slot(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    create_pointer_schema(engine)
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    later = datetime(2026, 1, 2, tzinfo=timezone.utc)
    acquired_slots: list[datetime] = []

    def acquire(*, source_config, slot, **_kwargs):
        acquired_slots.append(slot)
        readiness = ReadinessResult(
            source_id=source_config.source_id,
            acquisition_run=slot.isoformat(),
            status=ReadinessStatus.ready,
            observed_at=slot,
        )
        acquired = AcquisitionResult(
            record=RawArtifactRecord(
                source_id=source_config.source_id,
                acquisition_run=slot.isoformat(),
                artifact_ref=f"raw/{slot.isoformat()}",
                content_sha256="0" * 64,
                source_filename="data.csv",
                fetched_at=slot,
            ),
            payload=b"data",
        )
        return AcquisitionStageResult(
            acquisition_run=slot.isoformat(),
            status=ReadinessStatus.ready,
            readiness=readiness,
            acquired=acquired,
        )

    def curate(*, source_config, acquired, **_kwargs):
        update = DatasetPointerUpdate(
            dataset_id="source_data",
            manifest_ref=f"manifest/{acquired.record.acquisition_run}",
            watermark=acquired.record.fetched_at,
            published_at=acquired.record.fetched_at,
        )
        return CurationResult(
            datasets={update.dataset_id: update.manifest_ref},
            pointer_updates=(update,),
        )

    monkeypatch.setattr(runner_module, "run_stage1_acquire", acquire)
    monkeypatch.setattr(runner_module, "run_stage2_curate", curate)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config(
                "source",
                "source",
                {
                    "adapter": "local_file",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {
                        "data": {
                            "dataset_id": "source_data",
                            "parser_id": "csv_timeseries_v1",
                            "update_mode": "full",
                        }
                    },
                    "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
                },
            )
            rows = [
                repository.queue_run(
                    kind="source",
                    target_id="source",
                    slot=slot,
                    trigger="manual",
                    force=False,
                    config=config,
                )
                for slot in (later, earlier)
            ]
        ServiceRunner(data_store=f"file:{tmp_path}", workers=2)._run_dag(
            session,
            repository,
            rows,
            [],
            {"source_data": "source"},
            code_version="test",
        )

    assert acquired_slots == [earlier, later]
