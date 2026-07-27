#!/usr/bin/env python3
"""writing_pysource.py -- the prose inside Python source, and nothing else.

Phase 1 recorded the gap this closes: pointing the linter at a .py file scored
its string DATA as prose, so the ban lists tripped their own linter. The prose
of a Python file is its docstrings and comments; string literals are payload.
Both scoring paths use this extraction: per-file scoring and --delta.

Standard library only.
"""
from __future__ import annotations

import ast
import io
import tokenize


def prose_of(source: str) -> str:
    """Docstrings and comments, joined with blank lines. Empty on a parse error,
    because unparseable source has no reliably identifiable prose."""
    parts: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if doc:
                parts.append(doc)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                parts.append(tok.string.lstrip("#").strip())
    except tokenize.TokenError:
        pass
    return "\n\n".join(p for p in parts if p)
