import subprocess
import sys
from unittest.mock import MagicMock, patch

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

    popen.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "runbook.worker",
            "--run-id",
            "run-123",
        ],
        env=None,
    )


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


# submit command contains runbook.worker + run_id
# returned worker_id is local:<pid>
# poll with None means running
# poll with 0 means stopped successfully
# poll with non-zero means stopped
# cancel calls terminate
# cancel waits five seconds
# timeout calls kill
# already exited process is not terminated
# only requested run_id is touched
# duplicate local submission is rejected
