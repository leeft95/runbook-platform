from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository

from scripts.run_postgres_tests import validate_database_url
from tests.data.test_phasee_external_plugins import _build_isolated_site, _runtime_proof_prefix

pytestmark = pytest.mark.postgres


def _database() -> str:
    value = os.environ.get("RUNBOOK_TEST_DATABASE_URL")
    if not value:
        pytest.fail("RUNBOOK_TEST_DATABASE_URL is required for PostgreSQL release tests")
        raise AssertionError("unreachable")
    return validate_database_url(value)


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


def _launch_worker(database: str, store_uri: str, run_id: str, isolated_site: Path) -> subprocess.Popen[str]:
    script = (
        _runtime_proof_prefix(isolated_site)
        + """
import os
import runpy
import sys
os.environ["RUNBOOK_DATABASE_URL"] = r"__DATABASE__"
os.environ["RUNBOOK_DATA_STORE_URI"] = r"__STORE__"
sys.argv = ["runbook-worker", "--run-id", r"__RUN_ID__"]
try:
    runpy.run_module("runbook.worker", run_name="__main__")
except SystemExit as exc:
    exit_code = exc.code if isinstance(exc.code, int) else 1
else:
    exit_code = 0
print(json.dumps({"exit_code": exit_code, "pid": os.getpid(), "proof": runtime_proof()}))
raise SystemExit(exit_code)
""".replace("__DATABASE__", database)
        .replace("__STORE__", store_uri)
        .replace("__RUN_ID__", run_id)
    )
    process: subprocess.Popen[str] = subprocess.Popen(
        [sys.executable, "-I", "-c", script],
        cwd=isolated_site.parent,
        env={},
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
    isolated_site = _build_isolated_site(tmp_path)
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

    first_worker = _launch_worker(database, store_uri, first.run_id, isolated_site)
    first_stdout, first_stderr = first_worker.communicate(timeout=30)
    if first_worker.returncode != 0:
        with sync_sessions(database)() as session:
            saved = RunRepository(session).get_run(first.run_id)
            raise AssertionError(
                f"worker failed pid={first_worker.pid} row_status={saved.status if saved else None} "
                f"row_worker={saved.worker_id if saved else None}: {first_stdout}{first_stderr}"
            )
    assert first_worker.returncode == 0, first_stdout + first_stderr
    first_info = json.loads(first_stdout.strip().splitlines()[-1])
    assert first_info["exit_code"] == 0
    assert set(first_info["proof"]["distributions"]) == {
        "runbook-core",
        "runbook-data",
        "runbook-sdk",
        "runbook-services",
        "runbook-worker",
        "runbook-test-external-plugin",
    }

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

    second_worker = _launch_worker(database, store_uri, second.run_id, isolated_site)
    second_stdout, second_stderr = second_worker.communicate(timeout=30)
    assert second_worker.returncode == 0, second_stdout + second_stderr
    second_info = json.loads(second_stdout.strip().splitlines()[-1])
    assert second_info["exit_code"] == 0

    observed = json.loads(state_path.read_text(encoding="utf-8"))
    assert observed["watermark"] == {"prices": "2026-01-01T00:00:00Z"}
    assert observed["metadata"] == {"partition_values": {"prices": {"bucket": ["all"]}}}
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        saved = repository.get_run(second.run_id)
        assert saved is not None and saved.status == "success"
        pointer = repository.pointer_registry.get([f"{source_id}-prices"])[f"{source_id}-prices"]
        assert pointer.source_run_id == second.run_id
