from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository

from scripts.run_postgres_tests import validate_database_url

pytestmark = pytest.mark.postgres


def _database() -> str:
    value = os.environ.get("RUNBOOK_TEST_DATABASE_URL")
    if not value:
        pytest.fail("RUNBOOK_TEST_DATABASE_URL is required for PostgreSQL release tests")
        raise AssertionError("unreachable")
    return validate_database_url(value)


def _build_external_fixture(tmp_path: Path) -> Path:
    fixture = Path("tests/fixtures/external_plugin").resolve()
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--wheel", "--outdir", str(wheel_dir), str(fixture)],
        check=True,
        capture_output=True,
        text=True,
    )
    installed = tmp_path / "installed"
    installed.mkdir()
    with zipfile.ZipFile(next(wheel_dir.glob("*.whl"))) as wheel:
        wheel.extractall(installed)
    return installed


def _source_payload(source_id: str, state_path: Path) -> dict:
    return {
        "adapter": "test_external",
        "enabled": False,
        "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
        "datasets": {
            "prices": {
                "dataset_id": f"{source_id}-prices",
                "parser_id": "test_external_v1",
                "update_mode": "append",
            }
        },
        "params": {"external_state_path": str(state_path)},
    }


def _launch_worker(database: str, store_uri: str, run_id: str, installed: Path) -> subprocess.Popen[str]:
    python_path = os.pathsep.join(filter(None, [str(installed), os.environ.get("PYTHONPATH", "")]))
    process: subprocess.Popen[str] = subprocess.Popen(
        [sys.executable, "-m", "runbook.worker", "--run-id", run_id],
        cwd=Path.cwd(),
        env={
            **os.environ,
            "PYTHONPATH": python_path,
            "RUNBOOK_DATABASE_URL": database,
            "RUNBOOK_DATA_STORE_URI": store_uri,
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with sync_sessions(database)() as session:
            assert RunRepository(session).claim(run_id, f"local:{process.pid}")
            session.commit()
    except BaseException:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
        raise
    return process


def test_external_adapter_parser_and_previous_state_survive_worker_subprocess(tmp_path: Path) -> None:
    database = _database()
    upgrade_with_metadata(database)
    installed = _build_external_fixture(tmp_path)
    source_id = f"phase-e-{uuid4().hex}"
    state_path = tmp_path / "previous-state.json"
    store_uri = f"file:{tmp_path / 'store'}"
    payload = _source_payload(source_id, state_path)
    first_slot = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("source", source_id, payload)
        first = repository.queue_run(
            kind="source",
            target_id=source_id,
            slot=first_slot,
            trigger="manual",
            force=True,
            config=config,
        )
        session.commit()

    first_worker = _launch_worker(database, store_uri, first.run_id, installed)
    first_stdout, first_stderr = first_worker.communicate(timeout=30)
    assert first_worker.returncode == 0, first_stdout + first_stderr

    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        first_saved = repository.get_run(first.run_id)
        assert first_saved is not None and first_saved.status == "success"
        second = repository.queue_run(
            kind="source",
            target_id=source_id,
            slot=first_slot + timedelta(days=1),
            trigger="manual",
            force=True,
            config=config,
        )
        session.commit()

    second_worker = _launch_worker(database, store_uri, second.run_id, installed)
    second_stdout, second_stderr = second_worker.communicate(timeout=30)
    assert second_worker.returncode == 0, second_stdout + second_stderr

    observed = json.loads(state_path.read_text(encoding="utf-8"))
    assert observed["watermark"] == {"prices": "2026-01-01T00:00:00Z"}
    assert observed["metadata"] == {"partition_values": {"prices": {"bucket": ["all"]}}}
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        saved = repository.get_run(second.run_id)
        assert saved is not None and saved.status == "success"
        pointer = repository.pointer_registry.get([f"{source_id}-prices"])[f"{source_id}-prices"]
        assert pointer.source_run_id == second.run_id
