from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _alembic(database: str) -> Config:
    migrations = Path("packages/runbook/runbook-services/src/runbook/services/migrations").resolve()
    config = Config(str(migrations / "alembic.ini"))
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", database)
    return config


def test_sqlite_0002_to_head_preserves_run_config_and_pointer_state(tmp_path: Path) -> None:
    database = f"sqlite:///{tmp_path / 'migration.db'}"
    command.upgrade(_alembic(database), "0002_dataset_pointers")
    engine = create_engine(database)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO config_revisions "
                "(kind, config_id, revision, payload, config_hash, created_at) "
                "VALUES (:kind, :config_id, :revision, :payload, :config_hash, :created_at)"
            ),
            {
                "kind": "source",
                "config_id": "demo",
                "revision": 1,
                "payload": '{"adapter":"local_file"}',
                "config_hash": "hash-demo",
                "created_at": stamp,
            },
        )
        connection.execute(
            text(
                "INSERT INTO runs "
                "(run_id, kind, target_id, slot, trigger, force, config_revision, config_hash, status, "
                "identity_key, requested_at, updated_at) "
                "VALUES (:run_id, 'source', 'demo', :slot, 'manual', 0, 1, 'hash-demo', 'queued', "
                ":identity_key, :requested_at, :updated_at)"
            ),
            {
                "run_id": "run-demo",
                "slot": stamp,
                "identity_key": "source:demo:slot",
                "requested_at": stamp,
                "updated_at": stamp,
            },
        )
        connection.execute(
            text(
                "INSERT INTO dataset_pointers "
                "(dataset_id, source_id, manifest_ref, watermark, published_at, source_run_id, updated_at) "
                "VALUES ('prices', 'demo', 'curated/prices/manifests/sha256=demo.json', :stamp, :stamp, "
                "'run-demo', :stamp)"
            ),
            {"stamp": stamp},
        )

    command.upgrade(_alembic(database), "head")
    with engine.connect() as connection:
        runs = (
            connection.execute(text("SELECT run_id, status, config_hash, mode, start_date, end_date FROM runs"))
            .mappings()
            .all()
        )
        configs = connection.execute(text("SELECT config_id, revision FROM config_revisions")).mappings().all()
        pointers = connection.execute(text("SELECT dataset_id, source_run_id FROM dataset_pointers")).mappings().all()
        columns = {column["name"] for column in inspect(connection).get_columns("runs")}
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert runs == [
        {
            "run_id": "run-demo",
            "status": "queued",
            "config_hash": "hash-demo",
            "mode": "normal",
            "start_date": None,
            "end_date": None,
        }
    ]
    assert configs == [{"config_id": "demo", "revision": 1}]
    assert pointers == [{"dataset_id": "prices", "source_run_id": "run-demo"}]
    assert {
        "worker_id",
        "cancel_requested_at",
        "snapshot_payload",
        "dependencies_released_at",
        "mode",
        "start_date",
        "end_date",
    } <= columns
    assert head == "0004_historical_source_runs"

    command.downgrade(_alembic(database), "0003_addressable_workers")
    with engine.connect() as connection:
        downgraded_columns = {column["name"] for column in inspect(connection).get_columns("runs")}
        downgraded_runs = connection.execute(text("SELECT run_id, status, config_hash FROM runs")).mappings().all()
        downgraded_head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert {"mode", "start_date", "end_date"}.isdisjoint(downgraded_columns)
    assert downgraded_runs == [{"run_id": "run-demo", "status": "queued", "config_hash": "hash-demo"}]
    assert downgraded_head == "0003_addressable_workers"

    command.upgrade(_alembic(database), "head")
    with engine.connect() as connection:
        upgraded_columns = {column["name"] for column in inspect(connection).get_columns("runs")}
        upgraded_head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert {"mode", "start_date", "end_date"} <= upgraded_columns
    assert upgraded_head == "0004_historical_source_runs"
