from __future__ import annotations

import pytest

from scripts import run_postgres_tests
from scripts.run_postgres_tests import validate_database_url


def test_validate_database_url_rejects_vendor_database_without_connecting() -> None:
    with pytest.raises(ValueError, match="vendor database 'runbook'"):
        validate_database_url("postgresql+psycopg://postgres:postgres@localhost:5432/runbook")


def test_validate_database_url_allows_disposable_ci_database_names() -> None:
    value = "postgresql+psycopg://postgres:postgres@localhost:5432/ci_runbook_42"
    assert validate_database_url(value) == value


def test_main_rejects_vendor_database_before_invoking_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNBOOK_TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/runbook")

    def fail_if_invoked(*_args, **_kwargs):
        raise AssertionError("pytest subprocess must not run for the vendor database")

    monkeypatch.setattr(run_postgres_tests.subprocess, "run", fail_if_invoked)
    assert run_postgres_tests.main() == 1
