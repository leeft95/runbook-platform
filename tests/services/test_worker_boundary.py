from __future__ import annotations

import ast
from pathlib import Path

import tomllib


def _imports(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def test_control_plane_has_no_execution_package_imports() -> None:
    imports = _imports(Path("packages/runbook/runbook-services/src/runbook/services"))
    forbidden = ("runbook.data", "runbook.sdk", "runbook.worker", "runbook.platform")
    assert not any(name == prefix or name.startswith(prefix + ".") for name in imports for prefix in forbidden)


def test_reusable_packages_do_not_import_services() -> None:
    for package in ("runbook-core", "runbook-data", "runbook-sdk"):
        imports = _imports(Path("packages/runbook") / package / "src")
        assert not any(name == "runbook.services" or name.startswith("runbook.services.") for name in imports)


def test_worker_is_the_only_control_plane_composition_root() -> None:
    imports = _imports(Path("packages/runbook/runbook-worker/src"))
    assert any(name == "runbook.services" or name.startswith("runbook.services.") for name in imports)
    assert any(name == "runbook.data" or name.startswith("runbook.data.") for name in imports)
    assert any(name == "runbook.sdk" or name.startswith("runbook.sdk.") for name in imports)
    assert not any(name == "runbook.platform" or name.startswith("runbook.platform.") for name in imports)


def test_distribution_metadata_matches_the_runtime_dag() -> None:
    dependencies = {}
    for package in ("runbook-core", "runbook-data", "runbook-sdk", "runbook-services", "runbook-worker"):
        payload = tomllib.loads((Path("packages/runbook") / package / "pyproject.toml").read_text())
        dependencies[package] = set(payload["project"].get("dependencies", []))
    assert not any(item.startswith("runbook-") for item in dependencies["runbook-core"])
    assert "runbook-core" in dependencies["runbook-data"]
    assert {"runbook-core", "runbook-data"} <= dependencies["runbook-sdk"]
    assert dependencies["runbook-services"] & {"runbook-data", "runbook-sdk", "runbook-worker"} == set()
    assert {"runbook-core", "runbook-data", "runbook-sdk", "runbook-services"} <= dependencies["runbook-worker"]


def test_process_pool_executor_is_not_present() -> None:
    root = Path("packages/runbook")
    assert not any("ProcessPoolExecutor" in path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
