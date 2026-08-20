from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from runbook.services.db import sync_engine, sync_sessions, tick_lock
from runbook.services.repository import RunRepository
from sqlalchemy import inspect, text

pytestmark = pytest.mark.postgres


def _database() -> str:
    value = os.environ.get("RUNBOOK_TEST_DATABASE_URL")
    if not value:
        pytest.fail("RUNBOOK_TEST_DATABASE_URL is required for PostgreSQL release tests")
        raise AssertionError("unreachable")
    return value


def _upgrade(database: str) -> None:
    migrations = Path("packages/runbook/runbook-services/src/runbook/services/migrations").resolve()
    config = Config(str(migrations / "alembic.ini"))
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", database)
    command.upgrade(config, "head")


def test_postgres_head_and_advisory_lock_without_dropping_database() -> None:
    database = _database()
    _upgrade(database)
    engine = sync_engine(database)
    identity = f"phaseb-{uuid4().hex}"
    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0003_addressable_workers"
        )
        columns = {column["name"] for column in inspect(connection).get_columns("runs")}
        assert {"worker_id", "cancel_requested_at", "snapshot_payload", "dependencies_released_at"} <= columns
        connection.execute(
            text(
                "INSERT INTO config_revisions "
                "(kind, config_id, revision, payload, config_hash, created_at) "
                "VALUES ('profile', :identity, 1, CAST(:payload AS jsonb), :hash, now())"
            ),
            {"identity": identity, "payload": '{"report_id":"demo","datasets":{"prices":"prices"}}', "hash": identity},
        )

    with engine.connect() as first, engine.connect() as second:
        assert first.execute(text("SELECT pg_try_advisory_lock(hashtext('phaseb-release-test'))")).scalar_one()
        try:
            assert not second.execute(text("SELECT pg_try_advisory_lock(hashtext('phaseb-release-test'))")).scalar_one()
        finally:
            first.execute(text("SELECT pg_advisory_unlock(hashtext('phaseb-release-test'))"))

    with tick_lock(engine) as acquired:
        assert acquired


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {url}")


def _request_cancel(url: str) -> dict:
    request = Request(url, method="POST")
    with urlopen(request, timeout=5) as response:
        assert response.status == 202
        import json

        return json.loads(response.read())


def _wait_row(database: str, run_id: str, statuses: set[str], *, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with sync_sessions(database)() as session:
            row = RunRepository(session).get_run(run_id)
            if row is not None and row.status in statuses:
                return row
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for run {run_id} to reach {statuses}")


def _wait_target(database: str, kind: str, target_id: str, statuses: set[str], *, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with sync_sessions(database)() as session:
            rows = RunRepository(session).list_runs(kind=kind, target_id=target_id)
            row = next((item for item in rows if item.status in statuses), None)
            if row is not None:
                return row
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {kind}/{target_id} to reach {statuses}")


def _queue(repository: RunRepository, config, *, slot: datetime):
    row = repository.queue_run(
        kind="source",
        target_id=config.config_id,
        slot=slot,
        trigger="manual",
        force=True,
        config=config,
    )
    return row.run_id


def _source_payload(dataset_id: str, *, adapter: str = "local_file", url: str | None = None) -> dict:
    params = {"timestamp_column": "timestamp"}
    if adapter == "local_file":
        params["local_path"] = str(Path("data/fixtures/daily_prices.csv").resolve())
    else:
        assert url is not None
        params["url"] = url
    return {
        "adapter": adapter,
        "enabled": False,
        "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
        "datasets": {
            "prices": {
                "dataset_id": dataset_id,
                "parser_id": "csv_timeseries_v1",
                "update_mode": "full",
            }
        },
        "params": params,
    }


def _stop_process(process: subprocess.Popen, signum: int = signal.SIGTERM) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signum)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_postgres_process_lifecycle_queue_cancellation_and_restart(tmp_path: Path) -> None:
    """Exercise the durable PostgreSQL control plane through separate processes."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-process-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    reports_root = str(Path("reports").resolve())
    serve_port = _free_port()
    fixture_port = _free_port()
    processes: list[subprocess.Popen] = []
    source_ids = {
        "main": f"{identity}-main",
        "fast": f"{identity}-fast",
        "slow": f"{identity}-slow",
    }
    dataset_ids = {key: f"{value}-dataset" for key, value in source_ids.items()}
    try:
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            configs = {
                key: repository.save_config("source", source_id, _source_payload(dataset_ids[key]))
                for key, source_id in source_ids.items()
                if key != "slow"
            }
            configs["slow"] = repository.save_config(
                "source",
                source_ids["slow"],
                _source_payload(
                    dataset_ids["slow"], adapter="http", url=f"http://127.0.0.1:{fixture_port}/slow.csv?delay=5"
                ),
            )
            profile = repository.save_config(
                "profile",
                f"{identity}-profile",
                {
                    "report_id": "vol_report",
                    "enabled": True,
                    "datasets": {"prices": dataset_ids["main"]},
                    "params": {"price_col": "close", "vol_window": 2},
                },
            )
            # Keep the refresh slot at or before the checked-in fixture watermark
            # so dependency settlement is legitimately releasable.
            stamp = datetime(2026, 1, 25, tzinfo=timezone.utc)
            main_run = _queue(repository, configs["main"], slot=stamp)
            session.commit()

        python = sys.executable
        environment = {**os.environ, "RUNBOOK_DATABASE_URL": database, "PYTHONUNBUFFERED": "1"}
        fixture = subprocess.Popen(
            [python, "scripts/demo_http_server.py", "--host", "127.0.0.1", "--port", str(fixture_port)],
            cwd=Path.cwd(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(fixture)
        _wait_http(f"http://127.0.0.1:{fixture_port}/healthz")

        serve = subprocess.Popen(
            [
                python,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(serve_port),
                "--store",
                store_uri,
                "--reports-root",
                reports_root,
            ],
            cwd=Path.cwd(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(serve)
        _wait_http(f"http://127.0.0.1:{serve_port}/healthz")
        _wait_http(f"http://127.0.0.1:{serve_port}/readyz")

        runner = subprocess.Popen(
            [
                python,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--store",
                store_uri,
                "--reports-root",
                reports_root,
                "--workers",
                "2",
                "--poll-interval",
                "0.1",
                "--code-version",
                identity,
            ],
            cwd=Path.cwd(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(runner)
        main = _wait_row(database, main_run, {"success"})
        assert main.worker_id and main.worker_id.startswith("local:")
        assert main.result and main.result.get("pointer_updates")
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            pointer = repository.pointer_registry.get([dataset_ids["main"]])[dataset_ids["main"]]
            assert pointer.source_run_id == main.run_id

        profile_run = _wait_target(database, "profile", profile.config_id, {"success"})
        assert profile_run.snapshot_id and profile_run.snapshot_payload
        assert profile_run.context_hash == profile_run.result.get("context_hash")
        assert profile_run.code_version == identity
        with sync_sessions(database)() as session:
            profile_runs = [
                row for row in RunRepository(session).list_runs(kind="profile") if row.target_id == profile.config_id
            ]
            assert len(profile_runs) == 1

        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            slow_run = _queue(
                repository,
                configs["slow"],
                slot=stamp + timedelta(minutes=1),
            )
            fast_run = _queue(
                repository,
                configs["fast"],
                slot=stamp + timedelta(minutes=1),
            )
            same_source_next = _queue(
                repository,
                configs["slow"],
                slot=stamp + timedelta(minutes=2),
            )
            session.commit()

        slow = _wait_row(database, slow_run, {"running"})
        assert slow.status == "running"
        assert urlopen(f"http://127.0.0.1:{serve_port}/healthz", timeout=5).status == 200
        fast = _wait_row(database, fast_run, {"success"})
        assert fast.status == "success"
        with sync_sessions(database)() as session:
            assert RunRepository(session).get_run(same_source_next).status == "queued"
        cancelled = _request_cancel(f"http://127.0.0.1:{serve_port}/api/v1/runs/{slow_run}/cancel")
        assert cancelled["status"] == "running"
        _wait_row(database, slow_run, {"cancelled"})
        _wait_row(database, same_source_next, {"success", "failed"}, timeout=60.0)

        second_runner = subprocess.Popen(
            [
                python,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--workers",
                "1",
                "--poll-interval",
                "0.1",
            ],
            cwd=Path.cwd(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(second_runner)
        output, error = second_runner.communicate(timeout=15)
        assert second_runner.returncode == 0, error
        assert '"status":"skipped"' in output

        runner.send_signal(signal.SIGINT)
        runner.wait(timeout=15)
        assert runner.returncode == 0

        runner_again = subprocess.Popen(
            [
                python,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--workers",
                "1",
                "--poll-interval",
                "0.1",
            ],
            cwd=Path.cwd(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(runner_again)
        time.sleep(0.5)
        runner_again.send_signal(signal.SIGTERM)
        runner_again.wait(timeout=15)
        assert runner_again.returncode == 0
        with tick_lock(sync_engine(database)) as acquired:
            assert acquired

        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            orphan = repository.queue_run(
                kind="source",
                target_id=source_ids["fast"],
                slot=stamp + timedelta(minutes=3),
                trigger="manual",
                force=True,
                config=configs["fast"],
            )
            assert repository.claim(orphan.run_id, "local:orphaned-process")
            session.commit()
            orphan_id = orphan.run_id
        restart = subprocess.run(
            [
                python,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "tick",
                "--now",
                (stamp + timedelta(minutes=3)).isoformat(),
                "--workers",
                "1",
            ],
            cwd=Path.cwd(),
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert restart.returncode == 0, restart.stderr
        orphan_row = _wait_row(database, orphan_id, {"failed"})
        assert orphan_row.reason == "worker ownership lost / runner restarted"
    finally:
        for process in reversed(processes):
            _stop_process(process)
