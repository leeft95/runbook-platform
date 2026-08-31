from __future__ import annotations

from datetime import datetime, timezone

from runbook.services.db import sync_sessions, upgrade_with_metadata
from runbook.services.repository import RunRepository
from sqlalchemy.dialects import postgresql


def _profile_payload() -> dict[str, object]:
    """Return a minimal profile payload with delivery enabled."""
    return {
        "report_id": "report",
        "datasets": {"data": "data"},
        "delivery": {"email": {"provider": "company", "to": ["person@example.test"]}},
    }


def test_update_report_delivery_only_mutates_result_delivery(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config("profile", "profile", _profile_payload())
        row = repository.queue_run(
            kind="profile",
            target_id="profile",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        row.status = "success"
        row.result = {
            "status": "success",
            "artifact_id": "artifact",
            "snapshot_id": "snapshot",
            "context_hash": "context",
            "code_version": "code",
            "html_ref": "reports/report.html",
        }
        row.finished_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        before = {
            "status": row.status,
            "finished_at": row.finished_at,
            "artifact_id": row.artifact_id,
            "snapshot_id": row.snapshot_id,
            "context_hash": row.context_hash,
            "code_version": row.code_version,
        }
        assert repository.update_report_delivery(
            row.run_id,
            delivery={"status": "sent", "provider": "company", "attempts": 1},
        )
        session.commit()
        saved = repository.get_run(row.run_id)
        assert saved is not None
        assert saved.result["delivery"]["email"]["status"] == "sent"
        assert {key: getattr(saved, key) for key in before if key != "finished_at"} == {
            key: value for key, value in before.items() if key != "finished_at"
        }
        assert saved.finished_at == before["finished_at"].replace(tzinfo=None)

        row.status = "failed"
        session.commit()
        assert not repository.update_report_delivery(row.run_id, delivery={"status": "sent"})


def test_update_report_delivery_rejects_non_profile_rows(tmp_path) -> None:
    database = f"sqlite:///{tmp_path / 'runs.db'}"
    upgrade_with_metadata(database)
    with sync_sessions(database)() as session:
        repository = RunRepository(session)
        config = repository.save_config(
            "source",
            "source",
            {
                "adapter": "local_file",
                "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                "datasets": {
                    "data": {
                        "dataset_id": "data",
                        "parser_id": "csv_timeseries_v1",
                        "update_mode": "full",
                    }
                },
                "params": {"local_path": "unused.csv", "timestamp_column": "timestamp"},
            },
        )
        row = repository.queue_run(
            kind="source",
            target_id="source",
            slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
            trigger="manual",
            force=True,
            config=config,
        )
        row.status = "success"
        row.result = {"status": "success"}
        session.commit()
        assert not repository.update_report_delivery(row.run_id, delivery={"status": "sent"})


def test_report_retry_lookup_uses_row_lock() -> None:
    class SessionSpy:
        def scalar(self, statement):
            self.statement = statement
            return None

    session = SessionSpy()
    assert RunRepository(session).get_run_for_update("run") is None  # type: ignore[arg-type]
    statement = session.statement
    assert statement._for_update_arg is not None
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
