from __future__ import annotations

import argparse


def parser() -> argparse.ArgumentParser:
    """Build the worker command-line parser."""
    result = argparse.ArgumentParser(
        prog="runbook-worker",
        description="Execute one Runbook run.",
    )
    result.add_argument("--run-id", required=True)
    return result


def main() -> int:
    """Execute one durable run and return its process status."""
    args = parser().parse_args()

    from .execution import execute_run

    return execute_run(args.run_id)
