"""Run the opt-in PostgreSQL release tests against a disposable database."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    """Fail closed when no explicit disposable test database is configured."""
    database_url = os.environ.get("RUNBOOK_TEST_DATABASE_URL")
    if not database_url:
        print("RUNBOOK_TEST_DATABASE_URL is required for PostgreSQL release tests", file=sys.stderr)
        return 1
    environment = {**os.environ, "RUNBOOK_DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "postgres", "tests/postgres"],
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
