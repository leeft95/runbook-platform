from __future__ import annotations

from typing import Protocol

from .worker_backends.models import WorkerState


class ExecutionBackend(Protocol):
    def submit(self, run_id: str) -> str: ...

    def poll(self, run_id: str) -> WorkerState: ...

    def cancel(self, run_id: str) -> None: ...
