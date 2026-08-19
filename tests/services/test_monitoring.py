from __future__ import annotations

import asyncio
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from loguru import logger
from runbook.data import create_pointer_schema, open_blob_store
from runbook.data.ingest import (
    AcquisitionResult,
    AcquisitionStageResult,
    CurationResult,
    RawArtifactRecord,
    ReadinessResult,
    ReadinessStatus,
)
from runbook.data.pointers import DatasetPointer, DatasetPointerUpdate
from runbook.services import runner as runner_module
from runbook.services.dash.dashboard import _attention_table, _elapsed
from runbook.services.dash.run_logs import _bounded_log, _run_id_from_path
from runbook.services.logging import (
    RunLogIdentity,
    capture_worker_logs,
    read_log_tail,
    run_log_prefix,
    write_failure_log,
)
from runbook.services.models import Base
from runbook.services.repository import AsyncRunRepository, RunRepository
from runbook.services.runner import ServiceRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class _FailingExecutor:
    """Minimal executor for parent-side submission and broken-pool tests."""

    def __init__(self, *, submit_error: bool):
        self.submit_error = submit_error

    def __enter__(self):
        """Enter the fake executor context."""
        return self

    def __exit__(self, *_args):
        """Leave the fake executor context."""
        return None

    def submit(self, *_args, **_kwargs):
        """Raise during submission or return an already broken future."""
        if self.submit_error:
            raise RuntimeError("process startup failed")
        future: Future = Future()
        future.set_exception(BrokenProcessPool("worker terminated"))
        return future


def _identity(kind: str = "source") -> RunLogIdentity:
    return RunLogIdentity(
        run_id="run-1",
        kind=kind,
        target_id="source-1" if kind == "source" else "profile-1",
        slot=datetime(2026, 1, 2, 3, tzinfo=timezone.utc),
        report_id="report-1" if kind != "source" else None,
    )


def test_worker_logs_batch_and_keep_cursor_manifest_and_prefix(tmp_path: Path) -> None:
    store_uri = f"file:{tmp_path / 'logs'}"
    identity = _identity()
    with capture_worker_logs(store_uri, identity):
        logger.debug("hidden debug record")
        logger.info("visible info record")

        # Residual output is live after the periodic flusher runs.
        import time

        time.sleep(2.1)
        store = open_blob_store(store_uri)
        assert store.exists(f"{run_log_prefix(identity)}part=000001.log")

        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("unexpected failure")
    store = open_blob_store(store_uri)
    tail = read_log_tail(store, identity)
    assert tail["complete"] is True
    assert tail["next_part"] >= 1
    assert "visible info record" in tail["text"]
    assert "hidden debug record" not in tail["text"]
    assert "Traceback" in tail["text"]
    assert "RuntimeError: boom" in tail["text"]
    assert read_log_tail(store, identity, after_part=tail["next_part"])["text"] == ""
    assert read_log_tail(store, _identity("profile"))["text"] == ""


def test_worker_log_reserves_exception_space_after_ordinary_saturation(
    tmp_path: Path,
) -> None:
    from runbook.services.logging import _Capture

    identity = _identity()
    store_uri = f"file:{tmp_path / 'logs'}"
    capture = _Capture(open_blob_store(store_uri), identity)
    capture.add(b"ordinary\n" * 20_000, exception=False)
    capture.write_exception(RuntimeError("reserved traceback"))
    log_ref = capture.finish()
    manifest = open_blob_store(store_uri).get_json(log_ref)
    text = read_log_tail(open_blob_store(store_uri), identity)["text"]
    assert manifest["bytes"] <= 128 * 1024
    assert manifest["ordinary_truncated"] is True
    assert manifest["exception_truncated"] is False
    assert "[runbook log truncated]" in text
    assert "RuntimeError: reserved traceback" in text


def test_worker_log_batches_many_small_records(tmp_path: Path) -> None:
    from runbook.services.logging import _Capture

    identity = _identity()
    store_uri = f"file:{tmp_path / 'logs'}"
    capture = _Capture(open_blob_store(store_uri), identity)
    for _ in range(1_000):
        capture.add(b"small record\n", exception=False)
    manifest = open_blob_store(store_uri).get_json(capture.finish())
    assert len(manifest["parts"]) == 1


def test_failure_log_resumes_partial_worker_log_and_marks_it_incomplete(
    tmp_path: Path,
) -> None:
    from runbook.services.logging import _Capture

    identity = _identity()
    store_uri = f"file:{tmp_path / 'logs'}"
    crashed = _Capture(open_blob_store(store_uri), identity)
    crashed.add(b"worker output\n" * 2_000, exception=False)
    assert open_blob_store(store_uri).exists(f"{run_log_prefix(identity)}part=000001.log")

    write_failure_log(store_uri, identity, RuntimeError("process terminated"), incomplete=True)
    tail = read_log_tail(open_blob_store(store_uri), identity)
    assert tail["terminal"] is True
    assert tail["complete"] is False
    assert tail["incomplete"] is True
    assert "worker output" in tail["text"]
    assert "RuntimeError: process terminated" in tail["text"]


def test_log_routes_extract_run_id_and_bound_utf8_buffer() -> None:
    assert _run_id_from_path("/ui/runs/abc123/logs") == "abc123"
    assert _run_id_from_path("/ui/runs/abc123/logs/") == "abc123"
    assert _run_id_from_path("/ui/logs") is None
    assert len(_bounded_log("£" * (128 * 1024)).encode("utf-8")) <= 128 * 1024


def test_log_prefix_encodes_unsafe_identity_segments() -> None:
    identity = RunLogIdentity(
        run_id="../run/id",
        kind="source",
        target_id="../source/id",
        slot=datetime(2026, 1, 2, 3, tzinfo=timezone.utc),
    )
    prefix = run_log_prefix(identity)
    assert "../" not in prefix
    assert "/id/" not in prefix


def test_source_worker_returns_only_compact_serializable_result(monkeypatch, tmp_path: Path) -> None:
    slot = datetime(2026, 1, 2, 3, tzinfo=timezone.utc)
    source_payload = {
        "source_id": "source-1",
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
    }
    readiness = ReadinessResult(
        source_id="source-1",
        acquisition_run="acq-1",
        status=ReadinessStatus.ready,
        observed_at=slot,
    )
    acquired = AcquisitionResult(
        record=RawArtifactRecord(
            source_id="source-1",
            acquisition_run="acq-1",
            source_filename="prices.csv",
            fetched_at=slot,
        ),
        payload=b"raw payload",
    )
    update = DatasetPointerUpdate(
        dataset_id="prices",
        manifest_ref="manifests/prices.json",
        watermark=slot,
        published_at=slot,
    )

    def acquire(**_kwargs):
        return AcquisitionStageResult(
            acquisition_run="acq-1",
            status=ReadinessStatus.ready,
            readiness=readiness,
            acquired=acquired,
        )

    def curate(*, acquired, **_kwargs):
        assert acquired.payload == b"raw payload"
        return CurationResult(datasets={"prices": "prices-v1"}, pointer_updates=(update,))

    monkeypatch.setattr(runner_module, "run_stage1_acquire", acquire)
    monkeypatch.setattr(runner_module, "run_stage2_curate", curate)
    previous = DatasetPointer(
        dataset_id="prices",
        source_id="source-1",
        manifest_ref="manifests/old.json",
        watermark=slot,
        published_at=slot,
        source_run_id="old-run",
        updated_at=slot,
    )
    result = runner_module._source_worker(
        source_payload,
        slot.isoformat(),
        f"file:{tmp_path / 'store'}",
        {"prices": slot.isoformat()},
        {"prices": {name: value.isoformat() if isinstance(value, datetime) else value for name, value in previous.__dict__.items()}},
        {
            "run_id": "run-1",
            "kind": "source",
            "target_id": "source-1",
            "slot": slot.isoformat(),
        },
    )
    assert result["status"] == "success"
    assert result["datasets"] == {"prices": "prices-v1"}
    assert result["pointer_updates"][0]["watermark"] == slot.isoformat()
    assert all(value is not acquired.payload for value in result.values())
    assert "payload" not in result


def test_corrupt_source_manifest_gets_parent_failure_log(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    create_pointer_schema(engine)
    slot = datetime(2026, 1, 2, 3, tzinfo=timezone.utc)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        repository = RunRepository(session)
        with session.begin():
            config = repository.save_config(
                "source",
                "source-1",
                {
                    "adapter": "local_file",
                    "schedule": {"cron": "0 * * * *", "timezone": "UTC"},
                    "datasets": {
                        "prices": {
                            "dataset_id": "prices",
                            "parser_id": "csv_timeseries_v1",
                            "update_mode": "append",
                        }
                    },
                    "params": {
                        "local_path": "unused.csv",
                        "timestamp_column": "timestamp",
                    },
                },
            )
            repository.pointer_registry.publish(
                source_id="source-1",
                source_run_id="old-run",
                updates=[
                    DatasetPointerUpdate(
                        dataset_id="prices",
                        manifest_ref="manifests/corrupt.json",
                        watermark=slot,
                        published_at=slot,
                    )
                ],
            )
            row = repository.queue_run(
                kind="source",
                target_id="source-1",
                slot=slot,
                trigger="manual",
                force=False,
                config=config,
            )
        outcomes = ServiceRunner(data_store=f"file:{tmp_path / 'store'}")._run_dag(session, repository, [row], [], {}, code_version="test")
        session.commit()
        assert outcomes[0]["status"] == "failed"
        run_id = row.run_id
        log_ref = outcomes[0]["log_ref"]

    identity = RunLogIdentity(run_id, "source", "source-1", slot)
    assert log_ref == f"{run_log_prefix(identity)}manifest.json"
    tail = read_log_tail(open_blob_store(f"file:{tmp_path / 'store'}"), identity)
    assert tail["complete"] is True
    assert "corrupt.json" in tail["text"]


def test_process_startup_and_broken_pool_get_parent_failure_logs(
    tmp_path: Path,
) -> None:
    slot = datetime(2026, 1, 2, 3, tzinfo=timezone.utc)
    for submit_error in (True, False):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        create_pointer_schema(engine)
        store_uri = f"file:{tmp_path / str(submit_error)}"
        with sessionmaker(engine, expire_on_commit=False)() as session:
            repository = RunRepository(session)
            with session.begin():
                config = repository.save_config(
                    "source",
                    "source-1",
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
                        "params": {
                            "local_path": "unused.csv",
                            "timestamp_column": "timestamp",
                        },
                    },
                )
                row = repository.queue_run(
                    kind="source",
                    target_id="source-1",
                    slot=slot,
                    trigger="manual",
                    force=False,
                    config=config,
                )
            outcomes = ServiceRunner(
                data_store=store_uri,
                executor_factory=lambda _workers: _FailingExecutor(submit_error=submit_error),
            )._run_dag(session, repository, [row], [], {}, code_version="test")
            session.commit()

        tail = read_log_tail(
            open_blob_store(store_uri),
            RunLogIdentity(row.run_id, "source", "source-1", slot),
        )
        assert outcomes[0]["status"] == "failed"
        assert tail["terminal"] is True
        assert tail["incomplete"] is (not submit_error)
        assert ("process startup failed" if submit_error else "worker terminated") in tail["text"]


class _AsyncResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _AsyncSession:
    async def execute(self, _query):
        return _AsyncResult([("queued", 4), ("running", 2)])

    async def scalars(self, _query):
        return _AsyncResult([])


def test_dashboard_repository_queries_and_elapsed_serialization() -> None:
    now = datetime(2026, 1, 2, 3, tzinfo=timezone.utc)
    repository = AsyncRunRepository(_AsyncSession())
    counts = asyncio.run(repository.status_counts({"queued", "running"}, since=now))
    assert counts == {"queued": 4, "running": 2}
    assert asyncio.run(repository.list_active_runs()) == []
    assert asyncio.run(repository.list_attention_runs(now)) == []
    row = SimpleNamespace(
        requested_at=datetime(2026, 1, 2, 2, 59, tzinfo=timezone.utc),
        started_at=None,
    )
    assert _elapsed(row, now) == "0:01:00"

    finished = datetime(2026, 1, 2, 3, 1, tzinfo=timezone.utc)
    table = _attention_table(
        [
            SimpleNamespace(
                run_id="run-2",
                kind="profile",
                target_id="profile-1",
                status="failed",
                finished_at=finished,
                updated_at=now,
                requested_at=now,
                reason="boom",
            )
        ]
    )
    assert [cell.children for cell in table.children[0].children.children] == [
        "Run",
        "Kind",
        "Target",
        "Status",
        "Finished (UTC)",
        "Reason",
    ]
    assert table.children[1].children[0].children[4].children == finished.isoformat()
    empty = _attention_table([])
    assert empty.children[1].children[0].children[0].colSpan == 6
