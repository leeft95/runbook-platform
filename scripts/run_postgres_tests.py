"""Run the opt-in PostgreSQL release tests against a disposable database."""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy.engine import make_url


def validate_database_url(value: str) -> str:
    """Reject only the known vendor database used by demo data.

    Other database names are intentionally allowed so CI can provide its own
    disposable database without requiring a particular naming convention.
    """
    try:
        database = make_url(value).database
    except Exception as exc:
        raise ValueError("RUNBOOK_TEST_DATABASE_URL is not a valid SQLAlchemy URL") from exc
    if database == "runbook":
        raise ValueError("PostgreSQL release tests must not use vendor database 'runbook'")
    return value


def main() -> int:
    """Fail closed when no explicit disposable test database is configured."""
    database_url = os.environ.get("RUNBOOK_TEST_DATABASE_URL")
    if not database_url:
        print("RUNBOOK_TEST_DATABASE_URL is required for PostgreSQL release tests", file=sys.stderr)
        return 1
    try:
        database_url = validate_database_url(database_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    environment = {**os.environ, "RUNBOOK_DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "postgres", "tests/postgres"],
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
