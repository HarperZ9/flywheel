#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pysource -- the prose inside Python source, and nothing else.

Pointing the detector at a .py file scores its string data and identifiers as
prose, so the ban lists trip their own linter. The prose of a Python file is its
docstrings and comments; everything else is payload. This extracts that prose
while preserving line numbers, so a finding still points at the real source line.

Standard library only. Lineage: the flywheel writing_lint `pysource.py`, extended
to keep line positions.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize

_DECOR = re.compile(r"^\s*[-=~*_#]{2,}\s*")
_DECOR_END = re.compile(r"\s*[-=~*_#]{2,}\s*$")
_HAS_WORD = re.compile(r"[A-Za-z]{2,}")


def _clean_comment(text: str) -> str:
    """Comment prose without its ASCII decoration. A banner of dashes is not
    prose, and a `# --- Section ---` label is the words between the dashes."""
    text = text.strip()
    if not _HAS_WORD.search(text):
        return ""
    text = _DECOR.sub("", text)
    text = _DECOR_END.sub("", text)
    return text.strip()


def python_prose_lines(source: str):
    """Return a list the same length as source's lines, holding only docstring and
    comment text at their original line numbers and blank everywhere else."""
    src_lines = source.splitlines()
    out = [""] * len(src_lines)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc = body[0]
                end = doc.end_lineno or doc.lineno
                for ln in range(doc.lineno, end + 1):
                    if 1 <= ln <= len(src_lines):
                        # keep the raw line so offsets stay meaningful; the triple
                        # quotes are harmless to the detector.
                        out[ln - 1] = src_lines[ln - 1]
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                ln = tok.start[0]
                if 1 <= ln <= len(src_lines):
                    out[ln - 1] = _clean_comment(tok.string.lstrip("#"))
    except (tokenize.TokenError, IndentationError):
        pass
    return out


def prose_of(source: str) -> str:
    """Docstrings and comments as one prose string, line numbers preserved by
    blanking the non-prose lines."""
    return "\n".join(python_prose_lines(source))
