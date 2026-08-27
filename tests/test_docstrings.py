"""Keep production callables documented without importing the packages."""

from __future__ import annotations

import ast
from pathlib import Path


def _decorator_name(decorator: ast.expr) -> str:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _is_protocol(node: ast.ClassDef) -> bool:
    return any(
        (base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else "") == "Protocol"
        for base in node.bases
    )


def _is_stub(node: ast.FunctionDef | ast.AsyncFunctionDef, parent: ast.AST | None) -> bool:
    return (
        isinstance(parent, ast.ClassDef)
        and _is_protocol(parent)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and node.body[0].value.value is Ellipsis
    )


def _has_control_flow(node: ast.AST) -> bool:
    return any(
        isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match))
        for child in ast.walk(node)
    )


def _missing(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents: dict[ast.AST, ast.AST] = {}
    for ancestor in ast.walk(tree):
        for child in ast.iter_child_nodes(ancestor):
            parents[child] = ancestor
    missing: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("__") or ast.get_docstring(node):
            continue
        if any(_decorator_name(item) in {"field_validator", "model_validator"} for item in node.decorator_list):
            continue
        parent = parents.get(node)
        if _is_stub(node, parent):
            continue
        if not isinstance(parent, (ast.Module, ast.ClassDef)) and len(node.body) <= 1 and not _has_control_flow(node):
            continue
        missing.append(f"{path}:{node.lineno}:{node.name}")
    return missing


def test_runtime_callables_have_docstrings() -> None:
    roots = [Path("packages"), Path("reports")]
    missing = [
        entry
        for root in roots
        for path in root.rglob("*.py")
        if "build" not in path.parts and "dist" not in path.parts
        for entry in _missing(path)
    ]
    assert not missing, "Missing callable docstrings:\n" + "\n".join(missing)
