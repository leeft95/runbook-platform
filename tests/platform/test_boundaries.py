from pathlib import Path


def test_platform_is_orchestration_only() -> None:
    root = Path("packages/runbook/runbook-platform/src/runbook/platform")
    files = list(root.rglob("*.py"))
    assert {path.name for path in files} >= {"schedule.py", "source_run.py", "report_run.py"}
    assert not {path.name for path in files} & {"cli.py", "tick.py"}
    assert not any(
        path.parts[-2:] in [("platform", "data"), ("platform", "ingest"), ("platform", "runtime")] for path in files
    )
    forbidden = ("pandas", "requests", "plotly", "psycopg")
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert not any(f"import {name}" in source or f"from {name}" in source for name in forbidden)
