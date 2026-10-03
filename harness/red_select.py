"""red_select.py -- which test functions did a change add or edit?

A test is selected when it is new, or when its source (decorators included)
differs between the two versions of its file. Untouched tests in a touched file
are left out: the red check asks about the tests the change brought, not about
the suite. Standard library only.
"""
from __future__ import annotations

import ast


def _tests(source: str) -> dict:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test"):
            out[node.name] = ast.dump(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name.startswith("test"):
                    out[f"{node.name}::{item.name}"] = ast.dump(item)
    return out


def changed_tests(path: str, before: str, after: str) -> list:
    """Pytest node ids for tests that are new or edited in `after`."""
    old, new = _tests(before or ""), _tests(after or "")
    path = path.replace("\\", "/")
    return [f"{path}::{name}" for name, dump in new.items() if old.get(name) != dump]
