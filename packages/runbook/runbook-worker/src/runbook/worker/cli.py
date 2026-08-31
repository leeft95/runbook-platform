from __future__ import annotations

import argparse


def parser() -> argparse.ArgumentParser:
    """Build the worker command-line parser."""
    result = argparse.ArgumentParser(
        prog="runbook-worker",
        description="Execute one Runbook run.",
    )
    run_ids = result.add_mutually_exclusive_group(required=True)
    run_ids.add_argument("--run-id")
    run_ids.add_argument("--deliver-run-id")
    result.add_argument("--force", action="store_true", help="Resend an already-sent delivery")
    return result


def main() -> int:
    """Execute one durable run and return its process status."""
    args = parser().parse_args()

    from .execution import deliver_existing_report, execute_run

    if args.force and args.deliver_run_id is None:
        parser().error("--force is only valid with --deliver-run-id")
    try:
        return (
            deliver_existing_report(args.deliver_run_id, force=args.force)
            if args.deliver_run_id is not None
            else execute_run(args.run_id)
        )
    except ValueError as exc:
        print(f"runbook-worker: {exc}")
        return 2
