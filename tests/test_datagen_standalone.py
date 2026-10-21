"""The generator must not import anything from src/.

This is a Critical Constraint from the brief. Belt-and-braces: ruff's
flake8-tidy-imports rule in pyproject.toml also enforces it, but a test
means CI catches it even if someone runs tests without lint.
"""
from __future__ import annotations

import ast
import pathlib

DATAGEN_ROOT = pathlib.Path(__file__).parent.parent / "tools" / "datagen"


def _iter_imports(py_source: str):
    tree = ast.parse(py_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                yield n.name
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                yield node.module


def test_datagen_does_not_import_from_src() -> None:
    offenders: list[tuple[str, str]] = []
    for py in DATAGEN_ROOT.rglob("*.py"):
        for mod in _iter_imports(py.read_text()):
            if mod == "src" or mod.startswith("src."):
                offenders.append((str(py.relative_to(DATAGEN_ROOT.parent.parent)), mod))
    assert not offenders, (
        "tools/datagen must be standalone. Offending imports:\n  "
        + "\n  ".join(f"{f} imports {m}" for f, m in offenders)
    )
