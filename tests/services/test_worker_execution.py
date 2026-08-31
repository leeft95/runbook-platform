from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import runbook.worker.execution as worker_execution
from runbook.core import ReportProfile
from runbook.sdk.execution import ReportResult
from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository
from runbook.worker.execution import deliver_existing_report, execute_run


def _source_payload(path: str, *, update_mode: str = "full") -> dict:
    return {
        "adapter": "local_file",
        "enabled": False,
        "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
        "datasets": {
            "prices": {
                "dataset_id": "worker_prices",
                "parser_id": "csv_timeseries_v1",
                "update_mode": update_mode,
            }
        },
        "params": {"local_path": path, "timestamp_column": "timestamp"},
    }


def _report_row(tmp_path: Path, *, delivery: bool = False) -> tuple[object, ReportProfile, str]:
    """Build an in-memory worker report row for post-publication tests."""
    profile = ReportProfile(
        profile_id="worker_profile",
        report_id="worker_report",
        datasets={"data": "data"},
        delivery={"email": {"provider": "company", "to": ["person@example.test"]}} if delivery else None,
    )
    snapshot_id = "a" * 64
    row = type(
        "ReportRow",
        (),
        {
            "snapshot_payload": {
                "snapshot_id": snapshot_id,
                "watermark": "2026-01-01T00:00:00Z",
                "datasets": {"data": "data"},
            },
            "snapshot_id": snapshot_id,
            "code_version": "test",
        },
    )()
    return row, profile, f"file:{tmp_path / 'store'}"


def _report_result() -> ReportResult:
    """Return stable report-result fields for retry reconstruction tests."""
    return ReportResult(
        report_id="worker_report",
        artifact_id="artifact",
        snapshot_id="snapshot",
        context_hash="context",
        code_version="code",
        prefix="reports/worker_report/1",
        html_ref="reports/worker_report/1/report.html",
        stage3_ref="reports/worker_report/1/manifest.stage3.json",
        stage4_ref="reports/worker_report/1/manifest.stage4.json",
    )


def test_report_worker_delivers_only_after_published_result_and_keeps_success(tmp_path: Path, monkeypatch) -> None:
    row, profile, store_uri = _report_row(tmp_path, delivery=True)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)
    published = _report_result()
    calls: list[str] = []

    def fake_execute_report(**kwargs):
        calls.append("execute")
        kwargs["store"].put_immutable(published.html_ref, b"<html>published</html>")
        return published

    def fake_delivery(**kwargs):
        assert kwargs["store"].get(published.html_ref) == b"<html>published</html>"
        calls.append("delivery")
        return {
            "status": "failed",
            "provider": "company",
            "attempts": 1,
            "attempted_at": "now",
            "error": "RuntimeError",
        }

    monkeypatch.setattr(worker_execution, "execute_report", fake_execute_report)
    monkeypatch.setattr(worker_execution, "attempt_report_email_delivery", fake_delivery)
    outcome = worker_execution._report(
        row,
        profile,
        worker_execution.RunLogIdentity(
            run_id="run",
            kind="profile",
            target_id=profile.profile_id,
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            report_id=profile.report_id,
        ),
    )
    assert calls == ["execute", "delivery"]
    assert outcome["status"] == "success"
    assert outcome["delivery"]["email"]["status"] == "failed"


def test_report_worker_without_delivery_does_not_discover_and_failures_do_not_send(tmp_path: Path, monkeypatch) -> None:
    row, profile, store_uri = _report_row(tmp_path)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)
    monkeypatch.setattr(
        "runbook.sdk.delivery.email.load_email_sender",
        lambda *_args: pytest.fail("discovery occurred"),
    )
    monkeypatch.setattr(worker_execution, "execute_report", lambda **_kwargs: _report_result())
    assert (
        worker_execution._report(
            row,
            profile,
            worker_execution.RunLogIdentity(
                run_id="run",
                kind="profile",
                target_id=profile.profile_id,
                slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )["status"]
        == "success"
    )

    calls: list[str] = []
    monkeypatch.setattr(worker_execution, "attempt_report_email_delivery", lambda **_kwargs: calls.append("send"))
    monkeypatch.setattr(
        worker_execution,
        "execute_report",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("no pointer exists")),
    )
    configured = profile.model_copy(update={"delivery": {"email": {"provider": "company", "to": ["a@example.test"]}}})
    assert (
        worker_execution._report(
            row,
            configured,
            worker_execution.RunLogIdentity(
                run_id="run",
                kind="profile",
                target_id=profile.profile_id,
                slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )["status"]
        == "waiting"
    )
    assert calls == []
    monkeypatch.setattr(
        worker_execution,
        "execute_report",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("execution failed")),
    )
    assert (
        worker_execution._report(
            row,
            configured,
            worker_execution.RunLogIdentity(
                run_id="run",
                kind="profile",
                target_id=profile.profile_id,
                slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )["status"]
        == "failed"
    )
    assert calls == []


def _successful_profile_run(tmp_path: Path):
    """Create a successful profile run with a failed delivery attempt."""
    database = f"sqlite:///{tmp_path / 'retry.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config(
            "profile",
            "retry_profile",
            {
                "report_id": "worker_report",
                "datasets": {"data": "data"},
                "delivery": {"email": {"provider": "company", "to": ["first@example.test"]}},
            },
        )
        row = repository.queue_run(
            kind="profile",
            target_id="retry_profile",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        result = _report_result().model_dump(mode="json")
        result.update(
            {
                "status": "success",
                "delivery": {
                    "email": {
                        "status": "failed",
                        "provider": "company",
                        "attempts": 1,
                        "attempted_at": "before",
                    }
                },
            }
        )
        row.status = "success"
        row.result = result
        row.artifact_id = result["artifact_id"]
        row.snapshot_id = result["snapshot_id"]
        row.context_hash = result["context_hash"]
        row.code_version = result["code_version"]
        session.commit()
        run_id = row.run_id
        identity = {
            "status": row.status,
            "artifact_id": row.artifact_id,
            "snapshot_id": row.snapshot_id,
            "context_hash": row.context_hash,
            "code_version": row.code_version,
            "html_ref": result["html_ref"],
        }
    return database, store_uri, run_id, config, identity


def test_delivery_retry_uses_pinned_config_and_never_executes_report(tmp_path: Path, monkeypatch) -> None:
    database, store_uri, run_id, config, identity = _successful_profile_run(tmp_path)
    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)
    with sync_sessions(database)() as session:
        newer = RunRepository(session).save_config(
            "profile",
            "retry_profile",
            {
                "report_id": "worker_report",
                "datasets": {"data": "data"},
                "delivery": {"email": {"provider": "company", "to": ["new@example.test"]}},
            },
        )
        assert newer.revision > config.revision
        session.commit()

    calls: list[object] = []

    def fake_delivery(**kwargs):
        calls.append(kwargs["profile"].delivery.email.to)
        assert kwargs["result"].html_ref == identity["html_ref"]
        assert kwargs["result"].artifact_id == identity["artifact_id"]
        assert kwargs["result"].snapshot_id == identity["snapshot_id"]
        assert kwargs["previous"]["email"]["attempts"] == 1
        return {"status": "sent", "provider": "company", "attempts": 2, "attempted_at": "after"}

    monkeypatch.setattr(worker_execution, "attempt_report_email_delivery", fake_delivery)
    monkeypatch.setattr(worker_execution, "execute_report", lambda **_kwargs: pytest.fail("report was rerun"))
    assert deliver_existing_report(run_id) == 0
    assert calls == [("first@example.test",)]
    with sync_sessions(database)() as session:
        saved = RunRepository(session).get_run(run_id)
        assert saved is not None
        assert saved.status == identity["status"] == "success"
        assert saved.result["delivery"]["email"]["attempts"] == 2
        assert saved.result["html_ref"] == identity["html_ref"]


def test_delivery_retry_guards_sent_and_force_resends(tmp_path: Path, monkeypatch) -> None:
    database, store_uri, run_id, _config, _identity = _successful_profile_run(tmp_path)
    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)
    attempts: list[int] = []

    def fake_delivery(**kwargs):
        previous = kwargs["previous"]["email"]["attempts"]
        attempts.append(previous)
        return {"status": "sent", "provider": "company", "attempts": previous + 1, "attempted_at": "now"}

    monkeypatch.setattr(worker_execution, "attempt_report_email_delivery", fake_delivery)
    assert deliver_existing_report(run_id) == 0
    with pytest.raises(ValueError, match="already sent"):
        deliver_existing_report(run_id)
    assert deliver_existing_report(run_id, force=True) == 0
    assert attempts == [1, 2]


def test_delivery_retry_rejects_malformed_report_result(tmp_path: Path, monkeypatch) -> None:
    database, _store_uri, run_id, _config, _identity = _successful_profile_run(tmp_path)
    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    with sync_sessions(database)() as session:
        row = RunRepository(session).get_run(run_id)
        assert row is not None
        row.result = {"status": "success"}
        session.commit()
    with pytest.raises(ValueError):
        deliver_existing_report(run_id)


@pytest.mark.parametrize("kind,status", [("source", "success"), ("profile", "failed")])
def test_delivery_retry_rejects_invalid_run_kind_or_status(tmp_path: Path, monkeypatch, kind: str, status: str) -> None:
    database, _store_uri, run_id, _config, _identity = _successful_profile_run(tmp_path)
    with sync_sessions(database)() as session:
        row = RunRepository(session).get_run(run_id)
        assert row is not None
        row.kind = kind
        row.status = status
        session.commit()
    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    with pytest.raises(ValueError, match="successful profile run"):
        deliver_existing_report(run_id)


def test_real_worker_source_success_and_pointer_failure_roll_back_together(tmp_path: Path, monkeypatch) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    store_uri = f"file:{tmp_path / 'store'}"
    source = tmp_path / "prices.csv"
    source.write_text("timestamp,close\n2026-01-01T00:00:00Z,100\n", encoding="utf-8")
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("source", "worker_prices", _source_payload(str(source)))
        row = repository.queue_run(
            kind="source",
            target_id="worker_prices",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        assert repository.claim(row.run_id, f"local:{os.getpid()}")
        session.commit()

    monkeypatch.setenv("RUNBOOK_DATABASE_URL", database)
    monkeypatch.setenv("RUNBOOK_DATA_STORE_URI", store_uri)

    def fail_publication(*_args, **_kwargs):
        raise RuntimeError("injected pointer publication failure")

    monkeypatch.setattr("runbook.services.pointers.DatabasePointerRegistry.publish", fail_publication)
    with pytest.raises(RuntimeError, match="injected pointer publication failure"):
        execute_run(row.run_id)

    with sync_sessions(database)() as session:
        saved = RunRepository(session).get_run(row.run_id)
        assert saved is not None and saved.status == "running"
        assert RunRepository(session).pointer_registry.all() == {}
