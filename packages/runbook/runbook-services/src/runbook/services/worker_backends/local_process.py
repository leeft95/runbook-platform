from __future__ import annotations

import subprocess
import sys

from .models import WorkerState


class LocalProcessBackend:
    def __init__(self, *, env: dict[str, str] | None = None) -> None:
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._env = env

    def submit(self, run_id: str) -> str:
        if run_id in self._processes:
            raise ValueError(f"run already owned by backend: {run_id}")

        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "runbook.worker",
                "--run-id",
                run_id,
            ],
            env=self._env,
        )

        self._processes[run_id] = process
        return f"local:{process.pid}"

    def poll(self, run_id: str) -> WorkerState:
        process = self._processes[run_id]
        exit_code = process.poll()

        return WorkerState(
            running=exit_code is None,
            exit_code=exit_code,
        )

    def cancel(self, run_id: str) -> None:
        process = self._processes[run_id]

        if process.poll() is not None:
            return

        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
                process.wait()
