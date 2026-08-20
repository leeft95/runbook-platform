import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from runbook.services.worker_backends import WorkerState
from runbook.services.worker_backends.local_process import LocalProcessBackend


def test_submit_starts_worker_process():
    fake_process = MagicMock()
    fake_process.pid = 12345

    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        return_value=fake_process,
    ) as popen:
        backend = LocalProcessBackend()

        worker_id = backend.submit("run-123")

    assert worker_id == "local:12345"

    args, kwargs = popen.call_args
    assert args[0] == [
        sys.executable,
        "-m",
        "runbook.worker",
        "--run-id",
        "run-123",
    ]
    assert kwargs["env"]["PATH"]


def test_poll_reports_running():
    fake_process = MagicMock()
    fake_process.pid = 12345
    fake_process.poll.return_value = None

    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        return_value=fake_process,
    ):
        backend = LocalProcessBackend()
        backend.submit("run-123")

        state = backend.poll("run-123")

    assert state.running is True
    assert state.exit_code is None


def test_poll_reports_exit_code():
    fake_process = MagicMock()
    fake_process.pid = 12345
    fake_process.poll.return_value = 0

    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        return_value=fake_process,
    ):
        backend = LocalProcessBackend()
        backend.submit("run-123")

        state = backend.poll("run-123")

    assert state.running is False
    assert state.exit_code == 0
    with pytest.raises(KeyError):
        backend.poll("run-123")


def test_cancel_terminates_worker():
    fake_process = MagicMock()
    fake_process.pid = 12345
    fake_process.poll.return_value = None

    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        return_value=fake_process,
    ):
        backend = LocalProcessBackend()
        backend.submit("run-123")

        backend.cancel("run-123")

    fake_process.terminate.assert_called_once()
    fake_process.wait.assert_called_once_with(timeout=5)
    with pytest.raises(KeyError):
        backend.cancel("run-123")


def test_cancel_kills_after_timeout():
    fake_process = MagicMock()
    fake_process.pid = 12345

    # First poll: still alive.
    # Second poll after timeout: still alive.
    fake_process.poll.return_value = None
    fake_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="runbook-worker", timeout=5),
        None,
    ]

    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        return_value=fake_process,
    ):
        backend = LocalProcessBackend()
        backend.submit("run-123")

        backend.cancel("run-123")

    fake_process.terminate.assert_called_once()
    fake_process.kill.assert_called_once()


def test_duplicate_submission_is_rejected():
    fake_process = MagicMock(pid=12345)
    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        return_value=fake_process,
    ):
        backend = LocalProcessBackend()
        backend.submit("run-123")
        with pytest.raises(ValueError, match="already owned"):
            backend.submit("run-123")


def test_cancel_does_not_touch_other_processes():
    first = MagicMock(pid=1)
    second = MagicMock(pid=2)
    first.poll.return_value = None
    second.poll.return_value = None
    with patch(
        "runbook.services.worker_backends.local_process.subprocess.Popen",
        side_effect=[first, second],
    ):
        backend = LocalProcessBackend()
        backend.submit("first")
        backend.submit("second")
        backend.cancel("first")
        assert backend.poll("second").running

    first.terminate.assert_called_once()
    second.terminate.assert_not_called()


def test_worker_state_contract_is_nonblocking() -> None:
    assert WorkerState(running=True).running
    assert WorkerState(running=False, exit_code=0).exit_code == 0
