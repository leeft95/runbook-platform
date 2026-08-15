from __future__ import annotations

import argparse
import json
from pathlib import Path

from runbook.data import open_blob_store, resolve_snapshot
from runbook.sdk.execution import execute_report, resolve_code_version
from runbook.sdk.logging import configure_logging
from runbook.sdk.profiles import load_profiles


def main(argv: list[str] | None = None) -> int:
    """Render one profile against the latest snapshot for preview."""
    parser = argparse.ArgumentParser(prog="runbook-preview")
    parser.add_argument("profile_id")
    parser.add_argument("--profiles", default="data/contract/report_profiles.json")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--store", default=None)
    parser.add_argument("--code-version", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level: DEBUG, INFO, WARNING, or ERROR (default: RUNBOOK_LOG_LEVEL or INFO)",
    )
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    profile = load_profiles(args.profiles).get(args.profile_id)
    if profile is None:
        parser.error(f"unknown profile: {args.profile_id}")
    store = open_blob_store(args.store)
    snapshot = resolve_snapshot(store, profile.datasets)
    result = execute_report(
        store=store,
        profile=profile,
        snapshot=snapshot,
        code_version=resolve_code_version(args.code_version),
        reports_root=args.reports_root,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(store.get(result.html_ref))
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
