from __future__ import annotations

import sys

import pytest
from runbook.worker import cli


def test_worker_cli_run_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["--run-id", "one", "--deliver-run-id", "two"])


def test_worker_cli_dispatches_delivery_and_rejects_force_for_normal_runs(monkeypatch) -> None:
    delivered: list[tuple[str, bool]] = []
    executed: list[str] = []

    def fake_delivery(run_id: str, *, force: bool) -> int:
        delivered.append((run_id, force))
        return 7

    def fake_execute(run_id: str) -> int:
        executed.append(run_id)
        return 8

    monkeypatch.setattr(
        "runbook.worker.execution.deliver_existing_report",
        fake_delivery,
    )
    monkeypatch.setattr("runbook.worker.execution.execute_run", fake_execute)

    monkeypatch.setattr(sys, "argv", ["runbook-worker", "--deliver-run-id", "delivery", "--force"])
    assert cli.main() == 7
    assert delivered == [("delivery", True)]
    assert executed == []

    monkeypatch.setattr(sys, "argv", ["runbook-worker", "--run-id", "normal"])
    assert cli.main() == 8
    assert executed == ["normal"]

    monkeypatch.setattr(sys, "argv", ["runbook-worker", "--run-id", "normal", "--force"])
    with pytest.raises(SystemExit):
        cli.main()
    assert delivered == [("delivery", True)]
