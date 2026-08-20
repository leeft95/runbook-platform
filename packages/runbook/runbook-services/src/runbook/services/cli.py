from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runbook.core import load_profiles, load_source_configs

from .config import database_url
from .db import sync_sessions, upgrade_with_metadata
from .repository import RunRepository
from .runner import ServiceRunner


def _time(value: str | None) -> datetime | None:
    """Parse an ISO timestamp with an explicit timezone."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _config_payload(model: Any) -> dict[str, Any]:
    """Serialize a validated config without its map identifier."""
    payload = model.model_dump(mode="json")
    payload.pop("source_id", None)
    payload.pop("profile_id", None)
    return payload


def import_configs(args: argparse.Namespace) -> dict[str, int]:
    """Validate and import JSON configurations into PostgreSQL."""
    sources = load_source_configs(args.source_config)
    profiles = load_profiles(args.profiles)
    known_datasets = {binding.dataset_id for source in sources.values() for binding in source.datasets.values()}
    for profile in profiles.values():
        unknown = set(profile.datasets.values()) - known_datasets
        if unknown:
            raise ValueError(f"profile {profile.profile_id!r} references unknown datasets: {sorted(unknown)}")
    with sync_sessions(args.database)() as session:
        repository = RunRepository(session)
        with session.begin():
            for config in sources.values():
                repository.save_config("source", config.source_id, _config_payload(config))
            for profile in profiles.values():
                repository.save_config("profile", profile.profile_id, _config_payload(profile))
    return {"sources": len(sources), "profiles": len(profiles)}


def export_configs(args: argparse.Namespace) -> dict[str, str]:
    """Export current database revisions as deterministic JSON maps."""
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with sync_sessions(args.database)() as session:
        repository = RunRepository(session)
        sources = repository.list_latest_configs("source")
        profiles = repository.list_latest_configs("profile")
    source_payload = {row.config_id: row.payload for row in sorted(sources, key=lambda item: item.config_id)}
    profile_payload = {row.config_id: row.payload for row in sorted(profiles, key=lambda item: item.config_id)}
    source_file = output / "source_configs.json"
    profile_file = output / "report_profiles.json"
    source_file.write_text(json.dumps(source_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    profile_file.write_text(json.dumps(profile_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"source_config": str(source_file), "profiles": str(profile_file)}


def upgrade(args: argparse.Namespace) -> dict[str, str]:
    """Apply database migrations or metadata fallback."""
    try:
        from alembic import command
        from alembic.config import Config

        migrations = Path(__file__).with_name("migrations")
        config = Config(str(migrations / "alembic.ini"))
        config.set_main_option("script_location", str(migrations))
        config.set_main_option("sqlalchemy.url", database_url(args.database))
        command.upgrade(config, "head")
    except ImportError:
        upgrade_with_metadata(args.database)
    return {"status": "ready", "database": database_url(args.database)}


def main(argv: list[str] | None = None) -> int:
    """Dispatch the runbook-services command line interface."""
    parser = argparse.ArgumentParser(prog="runbook-services")
    parser.add_argument("--database", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade")
    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_import = config_sub.add_parser("import")
    config_import.add_argument("--source-config", default="data/contract/source_configs.json")
    config_import.add_argument("--profiles", default="data/contract/report_profiles.json")
    config_import.add_argument(
        "--reports-root",
        default=None,
        help="Deprecated compatibility option; report validation is performed by workers.",
    )
    config_sub.add_parser("export").add_argument("--output-dir", required=True)
    tick = sub.add_parser("tick")
    tick.add_argument("--now")
    tick.add_argument("--store", default=None)
    tick.add_argument("--reports-root", default=None)
    tick.add_argument("--code-version", default=None)
    tick.add_argument("--workers", type=int, default=4)
    run = sub.add_parser("run")
    run.add_argument("--store", default=None)
    run.add_argument("--reports-root", default=None)
    run.add_argument("--code-version", default=None)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--poll-interval", type=float, default=5.0)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8050)
    serve.add_argument("--store", default=None)
    serve.add_argument("--reports-root", default=None)
    serve.add_argument(
        "--reload", action="store_true", help="Reload the service when source files change (development only)."
    )
    args = parser.parse_args(argv)
    result: dict[str, Any]
    try:
        if args.command == "db":
            result = upgrade(args)
        elif args.command == "config" and args.config_command == "import":
            result = import_configs(args)
        elif args.command == "config":
            result = export_configs(args)
        elif args.command == "tick":
            result = {
                "outcomes": ServiceRunner(
                    database=args.database,
                    data_store=args.store,
                    report_root=args.reports_root,
                    workers=args.workers,
                ).tick(now=_time(args.now), code_version=args.code_version)
            }
        elif args.command == "run":
            if args.workers < 1:
                raise ValueError("workers must be at least 1")
            if args.poll_interval <= 0:
                raise ValueError("poll interval must be greater than 0")
            result = ServiceRunner(
                database=args.database,
                data_store=args.store,
                report_root=args.reports_root,
                workers=args.workers,
                poll_interval=args.poll_interval,
            ).run(code_version=args.code_version)
        else:
            import uvicorn

            from .app import create_app

            if args.reload:
                for name, value in {
                    "RUNBOOK_DATABASE_URL": args.database,
                    "RUNBOOK_DATA_STORE_URI": args.store,
                    "RUNBOOK_REPORTS_ROOT": args.reports_root,
                }.items():
                    if value is not None:
                        os.environ[name] = value
                uvicorn.run(
                    "runbook.services.app:create_app",
                    factory=True,
                    host=args.host,
                    port=args.port,
                    reload=True,
                )
            else:
                uvicorn.run(
                    create_app(
                        database=args.database,
                        data_store=args.store,
                        report_root=args.reports_root,
                    ),
                    host=args.host,
                    port=args.port,
                )
            return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
