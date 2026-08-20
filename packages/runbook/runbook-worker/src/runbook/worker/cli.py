from __future__ import annotations

import argparse


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="runbook-worker",
        description="Execute one Runbook run.",
    )
    result.add_argument("--run-id", required=True)
    return result


def main() -> int:
    args = parser().parse_args()

    # Execution is wired in during Phase B Day 5.
    print(f"runbook-worker run_id={args.run_id}")
    return 0
