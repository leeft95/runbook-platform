from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerState:
    running: bool
    exit_code: int | None = None
