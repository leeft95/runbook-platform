from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from runbook.core.keying import build_context_hash
from runbook.data import (
    DatasetPointerUpdate,
    build_manifest,
    load_manifest,
    open_blob_store,
    resolve_snapshot,
    write_manifests,
)
from runbook.services.db import sync_engine, sync_sessions, tick_lock
from runbook.services.logging import RunLogIdentity, read_log_tail
from runbook.services.repository import RunRepository
from runbook.services.runner import ServiceRunner
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import sessionmaker

from scripts.run_postgres_tests import validate_database_url

pytestmark = pytest.mark.postgres
RELEASE_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/runbook-platform-demo"


def _validated_database(value: str) -> str:
    """Reject the vendor demo database while allowing disposable CI names."""
    return validate_database_url(value)


def _database() -> str:
    value = os.environ.get("RUNBOOK_TEST_DATABASE_URL")
    if not value:
        pytest.fail("RUNBOOK_TEST_DATABASE_URL is required for PostgreSQL release tests")
        raise AssertionError("unreachable")
    try:
        return _validated_database(value)
    except ValueError as exc:
        pytest.fail(str(exc))
        raise AssertionError("unreachable")


def test_postgres_harness_rejects_vendor_database_url() -> None:
    with pytest.raises(ValueError, match="vendor database 'runbook'"):
        _validated_database("postgresql+psycopg://postgres:postgres@localhost:5432/runbook")
    assert _validated_database(RELEASE_DATABASE_URL) == RELEASE_DATABASE_URL


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


def _stop_orphan_pid(pid: int | None) -> None:
    """Terminate and best-effort reap a worker orphaned by a killed runner."""
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            waited_pid, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            waited_pid = 0
        if waited_pid == pid:
            return
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


def _worker_environment(database: str, store_uri: str, reports_root: str | None = None) -> dict[str, str]:
    """Build the minimal environment inherited by a real worker process."""
    environment = {**os.environ, "RUNBOOK_DATABASE_URL": database, "RUNBOOK_DATA_STORE_URI": store_uri}
    if reports_root is not None:
        environment["RUNBOOK_REPORTS_ROOT"] = reports_root
    return environment


def _launch_worker(
    database: str,
    store_uri: str,
    run_id: str,
    *,
    reports_root: str | Path | None = None,
) -> subprocess.Popen:
    """Start a worker process, then persist its exact local claim."""
    process = subprocess.Popen(
        [sys.executable, "-m", "runbook.worker", "--run-id", run_id],
        cwd=Path.cwd(),
        env=_worker_environment(database, store_uri, str(reports_root) if reports_root is not None else None),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            assert repository.claim(run_id, f"local:{process.pid}")
            session.commit()
    except BaseException:
        _stop_process(process)
        raise
    return process


@contextmanager
def _worker_process(
    database: str,
    store_uri: str,
    run_id: str,
    *,
    reports_root: str | Path | None = None,
):
    """Own one worker subprocess and always reap it on test failure."""
    process = _launch_worker(database, store_uri, run_id, reports_root=reports_root)
    try:
        yield process
    finally:
        _stop_process(process)


def _wait_worker(database: str, run_id: str, process: subprocess.Popen, *, timeout: float = 30.0):
    """Wait for a worker process and return its durable row."""
    process.wait(timeout=timeout)
    return _wait_row(database, run_id, {"success", "failed", "cancelled", "not_ready", "waiting"}, timeout=timeout)


def _save_and_queue_source(repository: RunRepository, source_id: str, payload: dict, *, slot: datetime):
    """Save one source revision and queue one explicit run."""
    config = repository.save_config("source", source_id, payload)
    row = repository.queue_run(
        kind="source",
        target_id=source_id,
        slot=slot,
        trigger="manual",
        force=True,
        config=config,
    )
    return config, row


def _write_report_module(
    reports_root: Path,
    report_id: str,
    *,
    title: str,
    log_marker: str = "",
    aliases: tuple[str, ...] = ("prices",),
) -> Path:
    """Write a tiny valid report module for subprocess import tests."""
    reports_root.mkdir(parents=True, exist_ok=True)
    module = reports_root / f"{report_id}.py"
    alias_payload = ", ".join(f"{alias}='{alias}'" for alias in aliases)
    first_alias = aliases[0]
    module.write_text(
        "\n".join(
            [
                "from loguru import logger",
                "from runbook.sdk import report, required_aliases",
                "from runbook.sdk.ui import grid, manifest, text",
                f"ALIASES = required_aliases({alias_payload})",
                f"logger.info({log_marker!r})" if log_marker else "",
                "@report.calc('value')",
                "def value(ctx):",
                f"    return ctx.dataset(ALIASES.{first_alias})",
                "@report.page",
                "def page(ctx):",
                f"    return manifest(ctx, title={title!r}, page=grid(rows=1, columns=1, blocks=[text(name='summary', text={title!r}, row=1, col=1)]))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return module


def _queue_profile_with_snapshot(
    repository: RunRepository,
    profile_id: str,
    report_id: str,
    snapshot,
    *,
    code_version: str,
    datasets: dict[str, str] | None = None,
):
    """Queue a manually pinned profile run without runner-side pointer resolution."""
    profile = repository.save_config(
        "profile",
        profile_id,
        {"report_id": report_id, "datasets": datasets or {"prices": "worker-prices"}},
    )
    row = repository.queue_run(
        kind="profile",
        target_id=profile_id,
        slot=snapshot.watermark,
        trigger="manual",
        force=True,
        config=profile,
        snapshot_id=snapshot.snapshot_id,
        snapshot_payload=snapshot.model_dump(mode="json"),
        context_hash=build_context_hash(profile.payload),
        code_version=code_version,
    )
    return profile, row


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
        queued_cancelled = _request_cancel(f"http://127.0.0.1:{serve_port}/api/v1/runs/{same_source_next}/cancel")
        assert queued_cancelled["status"] == "cancelled"
        _wait_row(database, same_source_next, {"cancelled"})
        cancelled = _request_cancel(f"http://127.0.0.1:{serve_port}/api/v1/runs/{slow_run}/cancel")
        assert cancelled["status"] == "running"
        _wait_row(database, slow_run, {"cancelled"})

        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            rerun = _queue(
                repository,
                configs["slow"],
                slot=stamp + timedelta(minutes=3),
            )
            session.commit()
        rerun_row = _wait_row(database, rerun, {"success"}, timeout=60.0)
        assert rerun_row.result and rerun_row.result.get("pointer_updates")

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


@pytest.mark.parametrize(
    ("case", "url", "expected"),
    [
        ("not-ready", "/missing.csv", "not_ready"),
        ("http-failure", "/failure.csv", "failed"),
        ("acquisition-failure", "/failure.csv", "failed"),
    ],
)
def test_postgres_real_worker_readiness_and_http_failures(tmp_path: Path, case: str, url: str, expected: str) -> None:
    """Real workers persist not-ready and HTTP acquisition outcomes durably."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-worker-{case}-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    fixture_port = _free_port()
    fixture = subprocess.Popen(
        [sys.executable, "scripts/demo_http_server.py", "--host", "127.0.0.1", "--port", str(fixture_port)],
        cwd=Path.cwd(),
        env={**os.environ, "RUNBOOK_DATABASE_URL": database},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http(f"http://127.0.0.1:{fixture_port}/healthz")
        payload = _source_payload(
            f"{identity}-dataset",
            adapter="http",
            url=f"http://127.0.0.1:{fixture_port}{url}",
        )
        if case == "acquisition-failure":
            payload["params"]["readiness_url"] = f"http://127.0.0.1:{fixture_port}/daily_prices.csv"
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            _config, row = _save_and_queue_source(
                repository, identity, payload, slot=datetime(2026, 1, 25, tzinfo=timezone.utc)
            )
            session.commit()
        with _worker_process(database, store_uri, row.run_id) as process:
            saved = _wait_worker(database, row.run_id, process)
            assert saved.status == expected
            if expected == "not_ready":
                assert saved.reason and "readiness" in saved.reason
            else:
                assert saved.reason and "500" in saved.reason
            assert saved.worker_id == f"local:{process.pid}"
            assert saved.result and saved.result.get("log_ref")
        with sync_sessions(database)() as session:
            assert RunRepository(session).pointer_registry.get([payload["datasets"]["prices"]["dataset_id"]]) == {}
    finally:
        _stop_process(fixture)


def test_postgres_real_worker_source_success_stage2_diagnostics_and_pointer(tmp_path: Path) -> None:
    """A real source worker publishes its dataset and Stage 2 diagnostics."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-worker-success-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    source_path = str(Path("data/fixtures/daily_prices.csv").resolve())
    payload = _source_payload(f"{identity}-dataset")
    payload["params"]["local_path"] = source_path
    slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        _config, row = _save_and_queue_source(repository, identity, payload, slot=slot)
        session.commit()
    with _worker_process(database, store_uri, row.run_id) as process:
        saved = _wait_worker(database, row.run_id, process)
        assert saved.status == "success"
    with sync_sessions(database)() as session:
        pointer = RunRepository(session).pointer_registry.get([payload["datasets"]["prices"]["dataset_id"]])[
            payload["datasets"]["prices"]["dataset_id"]
        ]
        assert pointer.source_run_id == row.run_id
    tail = read_log_tail(
        open_blob_store(store_uri),
        RunLogIdentity(row.run_id, "source", identity, slot),
    )
    assert tail["complete"] is True
    assert "stage=2 raw verified" in tail["text"]
    assert "stage=2 published" in tail["text"]


def test_postgres_real_worker_stale_append_pointer_recovers_with_full_refresh(tmp_path: Path) -> None:
    """An append pointer with missing history fails, then a full refresh recovers."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-worker-append-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    source_path = str(Path("data/fixtures/daily_prices.csv").resolve())
    append_payload = _source_payload(f"{identity}-dataset")
    append_payload["datasets"]["prices"]["update_mode"] = "append"
    append_payload["params"]["local_path"] = source_path
    full_payload = _source_payload(f"{identity}-dataset")
    full_payload["params"]["local_path"] = source_path
    first_slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config, row = _save_and_queue_source(repository, identity, append_payload, slot=first_slot)
        repository.pointer_registry.publish(
            source_id=identity,
            source_run_id="stale-append-run",
            updates=[
                DatasetPointerUpdate(
                    f"{identity}-dataset",
                    "curated/missing-append-manifest.json",
                    first_slot,
                    first_slot,
                )
            ],
        )
        session.commit()
    with _worker_process(database, store_uri, row.run_id) as failed_process:
        failed = _wait_worker(database, row.run_id, failed_process)
        assert failed.status == "failed"
        assert "append dataset pointer references missing manifest" in (failed.reason or "")
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        full_config = repository.save_config("source", identity, full_payload, expected_revision=config.revision)
        recovered = repository.queue_run(
            kind="source",
            target_id=identity,
            slot=first_slot + timedelta(days=1),
            trigger="manual",
            force=True,
            config=full_config,
        )
        session.commit()
    with _worker_process(database, store_uri, recovered.run_id) as recovered_process:
        saved = _wait_worker(database, recovered.run_id, recovered_process)
        assert saved.status == "success"
    with sync_sessions(database)() as session:
        pointer = RunRepository(session).pointer_registry.get([f"{identity}-dataset"])[f"{identity}-dataset"]
        assert pointer.source_run_id == recovered.run_id


def test_postgres_real_workers_atomic_publication_race_rolls_back_loser(tmp_path: Path) -> None:
    """Concurrent same-generation workers leave one pointer and roll back the loser."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-worker-race-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    fixture_port = _free_port()
    fixture = subprocess.Popen(
        [sys.executable, "scripts/demo_http_server.py", "--host", "127.0.0.1", "--port", str(fixture_port)],
        cwd=Path.cwd(),
        env={**os.environ, "RUNBOOK_DATABASE_URL": database},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    processes: list[subprocess.Popen] = []
    try:
        _wait_http(f"http://127.0.0.1:{fixture_port}/healthz")
        payload = _source_payload(
            f"{identity}-dataset",
            adapter="http",
            url=f"http://127.0.0.1:{fixture_port}/slow.csv?delay=5",
        )
        slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            config = repository.save_config("source", identity, payload)
            first = repository.queue_run(
                kind="source", target_id=identity, slot=slot, trigger="manual", force=True, config=config
            )
            second = repository.queue_run(
                kind="source", target_id=identity, slot=slot, trigger="manual", force=True, config=config
            )
            session.commit()
        for row in (first, second):
            process = _launch_worker(database, store_uri, row.run_id)
            processes.append(process)
        for process in processes:
            process.wait(timeout=30)
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            rows = [repository.get_run(first.run_id), repository.get_run(second.run_id)]
            success = [row for row in rows if row is not None and row.status == "success"]
            rolled_back = [row for row in rows if row is not None and row.status == "running"]
            assert len(success) == 1
            assert len(rolled_back) == 1
            pointer = repository.pointer_registry.get([f"{identity}-dataset"])[f"{identity}-dataset"]
            assert pointer.source_run_id == success[0].run_id
            repository.reconcile_orphan(rolled_back[0].run_id, reason="publication race loser")
            session.commit()
        with sync_sessions(database)() as session:
            assert RunRepository(session).get_run(rolled_back[0].run_id).status == "failed"
    finally:
        for process in reversed(processes):
            _stop_process(process)
        _stop_process(fixture)


def test_postgres_real_runner_enforces_two_worker_processes(tmp_path: Path) -> None:
    """The service admits two slow runs concurrently as two real worker PIDs."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-process-count-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    fixture_port = _free_port()
    fixture = subprocess.Popen(
        [sys.executable, "scripts/demo_http_server.py", "--host", "127.0.0.1", "--port", str(fixture_port)],
        cwd=Path.cwd(),
        env={**os.environ, "RUNBOOK_DATABASE_URL": database},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    runner: subprocess.Popen | None = None
    try:
        _wait_http(f"http://127.0.0.1:{fixture_port}/healthz")
        slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
        configs: list[tuple[str, str]] = []
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            for suffix in ("a", "b"):
                source_id = f"{identity}-{suffix}"
                dataset_id = f"{source_id}-dataset"
                payload = _source_payload(
                    dataset_id,
                    adapter="http",
                    url=f"http://127.0.0.1:{fixture_port}/slow.csv?delay=5",
                )
                config = repository.save_config("source", source_id, payload)
                repository.queue_run(
                    kind="source", target_id=source_id, slot=slot, trigger="manual", force=True, config=config
                )
                configs.append((source_id, dataset_id))
            session.commit()
        runner = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--store",
                store_uri,
                "--workers",
                "2",
                "--poll-interval",
                "0.1",
            ],
            cwd=Path.cwd(),
            env=_worker_environment(database, store_uri),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        rows = []
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            for source_id, _dataset_id in configs:
                rows.append(next(row for row in repository.list_runs(kind="source", target_id=source_id)))
        running = [_wait_row(database, row.run_id, {"running"}) for row in rows]
        worker_ids = {row.worker_id for row in running}
        assert len(worker_ids) == 2
        assert all(worker_id and worker_id.startswith("local:") for worker_id in worker_ids)
        assert all(Path(f"/proc/{worker_id.removeprefix('local:')}").exists() for worker_id in worker_ids)
    finally:
        if runner is not None:
            _stop_process(runner)
        _stop_process(fixture)


def test_postgres_real_worker_crash_and_runner_restart_reconcile_orphan(tmp_path: Path) -> None:
    """A killed worker is reconciled, and a killed runner leaves no adopted PID."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-crash-restart-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    fixture_port = _free_port()
    fixture = subprocess.Popen(
        [sys.executable, "scripts/demo_http_server.py", "--host", "127.0.0.1", "--port", str(fixture_port)],
        cwd=Path.cwd(),
        env={**os.environ, "RUNBOOK_DATABASE_URL": database},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    runner: subprocess.Popen | None = None
    crashed_runner: subprocess.Popen | None = None
    orphan_worker_pid: int | None = None
    try:
        _wait_http(f"http://127.0.0.1:{fixture_port}/healthz")
        payload = _source_payload(
            f"{identity}-dataset",
            adapter="http",
            url=f"http://127.0.0.1:{fixture_port}/slow.csv?delay=5",
        )
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            config = repository.save_config("source", identity, payload)
            first = repository.queue_run(
                kind="source",
                target_id=identity,
                slot=datetime(2026, 1, 25, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
            )
            session.commit()
        runner = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--store",
                store_uri,
                "--workers",
                "1",
                "--poll-interval",
                "0.1",
            ],
            cwd=Path.cwd(),
            env=_worker_environment(database, store_uri),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        running = _wait_row(database, first.run_id, {"running"})
        assert running.worker_id
        os.kill(int(running.worker_id.removeprefix("local:")), signal.SIGKILL)
        crashed = _wait_row(database, first.run_id, {"failed"})
        assert crashed.reason == "worker exited without terminal outcome"
        _stop_process(runner)
        runner = None

        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            second = repository.queue_run(
                kind="source",
                target_id=identity,
                slot=datetime(2026, 1, 26, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
            )
            session.commit()
        crashed_runner = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--store",
                store_uri,
                "--workers",
                "1",
                "--poll-interval",
                "0.1",
            ],
            cwd=Path.cwd(),
            env=_worker_environment(database, store_uri),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        running_again = _wait_row(database, second.run_id, {"running"})
        assert running_again.worker_id
        orphan_worker_pid = int(running_again.worker_id.removeprefix("local:"))
        os.kill(crashed_runner.pid, signal.SIGKILL)
        crashed_runner.wait(timeout=15)
        crashed_runner = None
        restart = subprocess.run(
            [
                sys.executable,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "tick",
                "--store",
                store_uri,
                "--workers",
                "1",
            ],
            cwd=Path.cwd(),
            env=_worker_environment(database, store_uri),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert restart.returncode == 0, restart.stderr
        orphan = _wait_row(database, second.run_id, {"failed"})
        assert orphan.reason == "worker ownership lost / runner restarted"
    finally:
        _stop_orphan_pid(orphan_worker_pid)
        if runner is not None:
            _stop_process(runner)
        if crashed_runner is not None:
            _stop_process(crashed_runner, signal.SIGKILL)
        _stop_process(fixture)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM], ids=["sigint", "sigterm"])
def test_postgres_runner_signal_cancels_active_worker(tmp_path: Path, signum: int) -> None:
    """Both supported termination signals cancel an active owned worker."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-signal-{signum}-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    fixture_port = _free_port()
    fixture = subprocess.Popen(
        [sys.executable, "scripts/demo_http_server.py", "--host", "127.0.0.1", "--port", str(fixture_port)],
        cwd=Path.cwd(),
        env={**os.environ, "RUNBOOK_DATABASE_URL": database},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    runner: subprocess.Popen | None = None
    try:
        _wait_http(f"http://127.0.0.1:{fixture_port}/healthz")
        payload = _source_payload(
            f"{identity}-dataset",
            adapter="http",
            url=f"http://127.0.0.1:{fixture_port}/slow.csv?delay=5",
        )
        with sync_sessions(database)() as session:
            repository = RunRepository(session)
            config = repository.save_config("source", identity, payload)
            row = repository.queue_run(
                kind="source",
                target_id=identity,
                slot=datetime(2026, 1, 25, tzinfo=timezone.utc),
                trigger="manual",
                force=True,
                config=config,
            )
            session.commit()
        runner = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runbook.services.cli",
                "--database",
                database,
                "run",
                "--store",
                store_uri,
                "--workers",
                "1",
                "--poll-interval",
                "0.1",
            ],
            cwd=Path.cwd(),
            env=_worker_environment(database, store_uri),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_row(database, row.run_id, {"running"})
        runner.send_signal(signum)
        runner.wait(timeout=15)
        assert runner.returncode == 0
        cancelled = _wait_row(database, row.run_id, {"cancelled"})
        assert cancelled.cancel_requested_at is not None
        with sync_sessions(database)() as session:
            assert RunRepository(session).pointer_registry.get([f"{identity}-dataset"]) == {}
    finally:
        if runner is not None:
            _stop_process(runner)
        _stop_process(fixture)


def test_postgres_two_source_durable_settlement_releases_one_profile(tmp_path: Path) -> None:
    """Two real source workers settle one exact generation before one profile run."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-two-source-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    reports_root = tmp_path / "reports"
    _write_report_module(reports_root, f"{identity}_report", title="two-source", aliases=("prices", "other"))
    slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_configs = []
        for suffix in ("a", "b"):
            source_id = f"{identity}-{suffix}"
            dataset_id = f"{source_id}-dataset"
            payload = _source_payload(dataset_id)
            config = repository.save_config("source", source_id, payload)
            repository.queue_run(
                kind="source", target_id=source_id, slot=slot, trigger="manual", force=True, config=config
            )
            source_configs.append((source_id, dataset_id))
        profile = repository.save_config(
            "profile",
            f"{identity}-profile",
            {
                "report_id": f"{identity}_report",
                "datasets": {"prices": source_configs[0][1], "other": source_configs[1][1]},
            },
        )
        session.commit()
    runner = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "runbook.services.cli",
            "--database",
            database,
            "run",
            "--store",
            store_uri,
            "--reports-root",
            str(reports_root),
            "--workers",
            "2",
            "--poll-interval",
            "0.1",
        ],
        cwd=Path.cwd(),
        env=_worker_environment(database, store_uri, str(reports_root)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for source_id, _dataset_id in source_configs:
            _wait_target(database, "source", source_id, {"success"})
        profile_row = _wait_target(database, "profile", profile.config_id, {"success"})
        assert profile_row.snapshot_payload and profile_row.snapshot_id
        assert set(profile_row.snapshot_payload["datasets"]) == {"prices", "other"}
        with sync_sessions(database)() as session:
            rows = RunRepository(session).list_runs(kind="profile", target_id=profile.config_id)
            assert len(rows) == 1
    finally:
        _stop_process(runner)


def test_postgres_runner_rejects_pointer_overwritten_by_newer_generation(tmp_path: Path) -> None:
    """A newer A pointer cannot combine with an older B generation."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-generation-overwrite-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    reports_root = tmp_path / "reports"
    report_id = f"{identity}_report"
    _write_report_module(reports_root, report_id, title="generation overwrite", aliases=("a", "b"))
    slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    newer_slot = slot + timedelta(days=1)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config_a = repository.save_config("source", f"{identity}-a", _source_payload(f"{identity}-a-dataset"))
        config_b = repository.save_config("source", f"{identity}-b", _source_payload(f"{identity}-b-dataset"))
        profile = repository.save_config(
            "profile",
            f"{identity}-profile",
            {
                "report_id": report_id,
                "datasets": {"a": f"{identity}-a-dataset", "b": f"{identity}-b-dataset"},
            },
        )
        a_old = repository.queue_run(
            kind="source", target_id=config_a.config_id, slot=slot, trigger="manual", force=True, config=config_a
        )
        session.commit()
    with _worker_process(database, store_uri, a_old.run_id) as process:
        assert _wait_worker(database, a_old.run_id, process).status == "success"
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        a_old_pointer = repository.pointer_registry.get([f"{identity}-a-dataset"])[f"{identity}-a-dataset"]

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        a_new = repository.queue_run(
            kind="source",
            target_id=config_a.config_id,
            slot=newer_slot,
            trigger="manual",
            force=True,
            config=config_a,
        )
        session.commit()
    with _worker_process(database, store_uri, a_new.run_id) as process:
        assert _wait_worker(database, a_new.run_id, process).status == "success"

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        b_old = repository.queue_run(
            kind="source", target_id=config_b.config_id, slot=slot, trigger="manual", force=True, config=config_b
        )
        session.commit()
    with _worker_process(database, store_uri, b_old.run_id) as process:
        assert _wait_worker(database, b_old.run_id, process).status == "success"

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        b_old_pointer = repository.pointer_registry.get([f"{identity}-b-dataset"])[f"{identity}-b-dataset"]
    first_tick = subprocess.run(
        [
            sys.executable,
            "-m",
            "runbook.services.cli",
            "--database",
            database,
            "tick",
            "--store",
            store_uri,
            "--reports-root",
            str(reports_root),
            "--workers",
            "1",
            "--code-version",
            "generation-overwrite",
        ],
        cwd=Path.cwd(),
        env=_worker_environment(database, store_uri, str(reports_root)),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert first_tick.returncode == 0, first_tick.stderr
    with sync_sessions(database)() as session:
        assert RunRepository(session).list_runs(kind="profile", target_id=profile.config_id) == []

        repository = RunRepository(session)
        repository.pointer_registry.publish(
            source_id=f"{identity}-a",
            source_run_id=a_old.run_id,
            updates=[
                DatasetPointerUpdate(
                    f"{identity}-a-dataset",
                    a_old_pointer.manifest_ref,
                    a_old_pointer.watermark,
                    a_old_pointer.published_at,
                )
            ],
        )
        session.commit()
    second_tick = subprocess.run(
        [
            sys.executable,
            "-m",
            "runbook.services.cli",
            "--database",
            database,
            "tick",
            "--store",
            store_uri,
            "--reports-root",
            str(reports_root),
            "--workers",
            "1",
            "--code-version",
            "generation-overwrite",
        ],
        cwd=Path.cwd(),
        env=_worker_environment(database, store_uri, str(reports_root)),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert second_tick.returncode == 0, second_tick.stderr
    with sync_sessions(database)() as session:
        rows = RunRepository(session).list_runs(kind="profile", target_id=profile.config_id)
        assert len(rows) == 1
        assert rows[0].status == "success"
        assert rows[0].snapshot_payload["datasets"] == {
            "a": a_old_pointer.manifest_ref,
            "b": b_old_pointer.manifest_ref,
        }


def test_postgres_multi_dataset_future_publication_races_release_without_deadlock(tmp_path: Path) -> None:
    """Canonical pointer locking survives a future two-dataset publication race."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-pointer-lock-order-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    source_id = f"{identity}-source"
    dataset_ids = (f"{identity}-a", f"{identity}-b")
    slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    future_slot = slot + timedelta(days=1)
    store = open_blob_store(store_uri)
    manifests: dict[str, dict[str, str]] = {}
    for generation, watermark in (("old", slot), ("new", future_slot)):
        built = []
        for dataset_id in dataset_ids:
            manifest, digest = build_manifest(
                dataset_id=dataset_id,
                watermark=watermark,
                published_at=watermark,
                files=[],
            )
            built.append((manifest, digest))
        manifests[generation] = write_manifests(store, built)

    payload = _source_payload(dataset_ids[0])
    payload["datasets"]["other"] = {
        "dataset_id": dataset_ids[1],
        "parser_id": "csv_timeseries_v1",
        "update_mode": "full",
    }
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        source_config = repository.save_config("source", source_id, payload)
        profile_config = repository.save_config(
            "profile",
            f"{identity}-profile",
            {"report_id": f"{identity}-report", "datasets": {"a": dataset_ids[0], "b": dataset_ids[1]}},
        )
        settled = repository.queue_run(
            kind="source", target_id=source_id, slot=slot, trigger="manual", force=True, config=source_config
        )
        future = repository.queue_run(
            kind="source", target_id=source_id, slot=future_slot, trigger="manual", force=True, config=source_config
        )
        repository.mark_running(settled)
        repository.finish(settled, status="success")
        repository.pointer_registry.publish(
            source_id=source_id,
            source_run_id=settled.run_id,
            updates=[
                DatasetPointerUpdate(
                    dataset_id,
                    manifests["old"][dataset_id],
                    slot,
                    slot,
                )
                for dataset_id in reversed(dataset_ids)
            ],
        )
        session.commit()

    release_first_locked = threading.Event()
    release_continue = threading.Event()
    release_done = threading.Event()
    publication_started = threading.Event()
    first_update = threading.Event()
    allow_publication_continue = threading.Event()
    errors: list[BaseException] = []
    first_update_dataset: list[str | None] = []
    publisher_engine = sync_engine(database)

    def after_pointer_update(_connection, _cursor, statement, parameters, _context, _executemany) -> None:
        """Pause after the publication's first row update to expose lock order."""
        if first_update.is_set() or not statement.lstrip().upper().startswith("UPDATE DATASET_POINTERS"):
            return
        target = parameters.get("dataset_id_1") if isinstance(parameters, dict) else None
        first_update_dataset.append(target)
        first_update.set()
        if not allow_publication_continue.wait(timeout=8):
            raise RuntimeError("publication coordination timed out")

    event.listen(publisher_engine, "after_cursor_execute", after_pointer_update)
    publisher_sessions = sessionmaker(publisher_engine, expire_on_commit=False)

    def release() -> None:
        try:
            runner = ServiceRunner(database=database, data_store=store_uri, workers=1, poll_interval=0.1)
            with sync_sessions(database)() as session:
                session.execute(text("SET LOCAL lock_timeout = '6000ms'"))
                session.execute(text("SET LOCAL statement_timeout = '12000ms'"))
                session.execute(
                    text("SELECT dataset_id FROM dataset_pointers WHERE dataset_id = :dataset_id FOR UPDATE"),
                    {"dataset_id": dataset_ids[0]},
                )
                release_first_locked.set()
                if not release_continue.wait(timeout=5):
                    raise RuntimeError("release coordination timed out")
                repository = RunRepository(session)
                source_configs = repository.list_latest_configs("source")
                profile_configs = repository.list_latest_configs("profile", enabled_only=True)
                runner._release_dependencies(
                    repository,
                    source_configs,
                    profile_configs,
                    runner._producer_map(source_configs),
                    "pointer-lock-order",
                )
                session.commit()
        except BaseException as exc:
            errors.append(exc)
        finally:
            release_done.set()

    def publish_future() -> None:
        try:
            with publisher_sessions() as session:
                session.execute(text("SET LOCAL lock_timeout = '6000ms'"))
                session.execute(text("SET LOCAL statement_timeout = '12000ms'"))
                publication_started.set()
                repository = RunRepository(session)
                repository.pointer_registry.publish(
                    source_id=source_id,
                    source_run_id=future.run_id,
                    updates=[
                        DatasetPointerUpdate(
                            dataset_id,
                            manifests["new"][dataset_id],
                            future_slot,
                            future_slot,
                        )
                        for dataset_id in reversed(dataset_ids)
                    ],
                )
                session.commit()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=release, daemon=True), threading.Thread(target=publish_future, daemon=True)]
    try:
        threads[0].start()
        assert release_first_locked.wait(timeout=5), "release did not acquire its first pointer lock"
        threads[1].start()
        assert publication_started.wait(timeout=5), "publication did not start"
        # The old insertion-order publication updates B first while release
        # holds A.  Letting release continue at that exact point deterministically
        # exercises the former deadlock.  Canonical publication blocks on A,
        # reaches no update, and release completes before publication proceeds.
        first_update_seen = first_update.wait(timeout=3)
        release_continue.set()
        assert release_done.wait(timeout=8), "release transaction exceeded its bound"
        allow_publication_continue.set()
        if not first_update_seen:
            assert first_update.wait(timeout=8), "publication did not reach its first update"
        for thread in threads:
            thread.join(timeout=8)
        assert all(not thread.is_alive() for thread in threads), "pointer publication/release deadlocked"
    finally:
        release_continue.set()
        allow_publication_continue.set()
        for thread in threads:
            thread.join(timeout=2)
        event.remove(publisher_engine, "after_cursor_execute", after_pointer_update)
        publisher_engine.dispose()

    assert errors == []
    assert first_update_dataset == [dataset_ids[0]]

    with sync_sessions(database)() as session:
        pointers = RunRepository(session).pointer_registry.get(dataset_ids)
        assert {dataset_id: pointer.source_run_id for dataset_id, pointer in pointers.items()} == {
            dataset_id: future.run_id for dataset_id in dataset_ids
        }
        assert {dataset_id: pointer.manifest_ref for dataset_id, pointer in pointers.items()} == {
            dataset_id: manifests["new"][dataset_id] for dataset_id in dataset_ids
        }
        rows = RunRepository(session).list_runs(kind="profile", target_id=profile_config.config_id)
        assert len(rows) == 1
        assert rows[0].status == "queued"
        assert rows[0].snapshot_payload["datasets"] == {
            "a": manifests["old"][dataset_ids[0]],
            "b": manifests["old"][dataset_ids[1]],
        }


def _prepare_profile_snapshot(database: str, store_uri: str, identity: str, slot: datetime):
    """Run one real source worker and return its immutable current snapshot."""
    payload = _source_payload(f"{identity}-dataset")
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config, row = _save_and_queue_source(repository, identity, payload, slot=slot)
        session.commit()
    with _worker_process(database, store_uri, row.run_id) as process:
        saved = _wait_worker(database, row.run_id, process)
        assert saved.status == "success"
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        pointer = repository.pointer_registry.get([f"{identity}-dataset"])[f"{identity}-dataset"]
        snapshot = resolve_snapshot(
            open_blob_store(store_uri), {"prices": f"{identity}-dataset"}, pointer_registry=repository.pointer_registry
        )
    return config, row, pointer, snapshot


def test_postgres_report_worker_uses_pinned_snapshot_after_pointer_mutation(tmp_path: Path) -> None:
    """A pointer update after queueing cannot replace a profile's pinned snapshot."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-pinned-pointer-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    reports_root = tmp_path / "reports"
    slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    _config, _source_row, pointer, snapshot = _prepare_profile_snapshot(database, store_uri, identity, slot)
    report_id = f"{identity}_report"
    _write_report_module(reports_root, report_id, title="pinned snapshot")
    store = open_blob_store(store_uri)
    old_manifest = load_manifest(store, pointer.manifest_ref, expected_dataset_id=f"{identity}-dataset")
    newer_manifest, digest = build_manifest(
        dataset_id=f"{identity}-dataset",
        watermark=slot + timedelta(days=1),
        published_at=slot + timedelta(days=1),
        files=old_manifest.files,
    )
    newer_ref = write_manifests(store, [(newer_manifest, digest)])[f"{identity}-dataset"]
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        repository.pointer_registry.publish(
            source_id=identity,
            source_run_id="newer-pointer-run",
            updates=[
                DatasetPointerUpdate(
                    f"{identity}-dataset",
                    newer_ref,
                    slot + timedelta(days=1),
                    slot + timedelta(days=1),
                )
            ],
        )
        _profile, profile_row = _queue_profile_with_snapshot(
            repository,
            f"{identity}-profile",
            report_id,
            snapshot,
            code_version="pinned",
            datasets={"prices": f"{identity}-dataset"},
        )
        session.commit()
    with _worker_process(database, store_uri, profile_row.run_id, reports_root=reports_root) as process:
        saved = _wait_worker(database, profile_row.run_id, process)
        assert saved.status == "success"
        assert saved.snapshot_id == snapshot.snapshot_id
        assert saved.result and saved.result["snapshot"]["snapshot_id"] == snapshot.snapshot_id
    with sync_sessions(database)() as session:
        pointer_after = RunRepository(session).pointer_registry.get([f"{identity}-dataset"])[f"{identity}-dataset"]
        assert pointer_after.source_run_id == "newer-pointer-run"


def test_postgres_report_subprocesses_fresh_imports_and_large_worker_logs(tmp_path: Path) -> None:
    """Separate report workers import modified code freshly and persist >16KB logs."""
    database = _database()
    _upgrade(database)
    identity = f"phaseb-fresh-report-{uuid4().hex}"
    store_uri = f"file:{tmp_path / 'store'}"
    reports_root = tmp_path / "reports"
    report_id = f"{identity}_report"
    slot = datetime(2026, 1, 25, tzinfo=timezone.utc)
    _config, _source_row, _pointer, snapshot = _prepare_profile_snapshot(database, store_uri, identity, slot)
    store = open_blob_store(store_uri)
    module = _write_report_module(
        reports_root,
        report_id,
        title="VERSION_ONE",
        log_marker="large-worker-log-" + ("x" * (17 * 1024)),
    )
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        _profile, first = _queue_profile_with_snapshot(
            repository,
            f"{identity}-profile-one",
            report_id,
            snapshot,
            code_version="v1",
            datasets={"prices": f"{identity}-dataset"},
        )
        session.commit()
    with _worker_process(database, store_uri, first.run_id, reports_root=str(reports_root)) as first_process:
        first_saved = _wait_worker(database, first.run_id, first_process)
        assert first_saved.status == "success"
        assert first_saved.result and first_saved.result.get("html_ref")
        assert b"VERSION_ONE" in store.get(first_saved.result["html_ref"])
    first_log = read_log_tail(
        store,
        RunLogIdentity(first.run_id, "profile", f"{identity}-profile-one", slot, report_id=report_id),
    )
    assert first_log["manifest"]["bytes"] > 16 * 1024
    assert "large-worker-log" in first_log["text"]

    module.write_text(module.read_text(encoding="utf-8").replace("VERSION_ONE", "VERSION_TWO"), encoding="utf-8")
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        _profile, second = _queue_profile_with_snapshot(
            repository,
            f"{identity}-profile-two",
            report_id,
            snapshot,
            code_version="v2",
            datasets={"prices": f"{identity}-dataset"},
        )
        session.commit()
    with _worker_process(database, store_uri, second.run_id, reports_root=str(reports_root)) as second_process:
        second_saved = _wait_worker(database, second.run_id, second_process)
        assert second_saved.status == "success"
        assert second_saved.result and second_saved.result.get("html_ref")
        assert b"VERSION_TWO" in store.get(second_saved.result["html_ref"])
