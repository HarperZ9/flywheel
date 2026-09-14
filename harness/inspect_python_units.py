from __future__ import annotations

import ast
import hashlib
import re

_TEST = re.compile(r"test_[A-Za-z0-9_]+\Z")


def enumerate_python_test_definitions(source: str) -> dict:
    if type(source) is not str:
        return _fault("parse_error")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _fault("parse_error")
    lines, starts = _physical_lines(source)
    definitions, nested = [], []
    top_nodes = set(tree.body)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _TEST.fullmatch(node.name):
            continue
        if node not in top_nodes:
            nested.append(node.name)
            continue
        try:
            start = starts[node.lineno - 1] + _byte_col_to_codepoints(
                lines[node.lineno - 1], node.col_offset)
            end = starts[node.end_lineno - 1] + _byte_col_to_codepoints(
                lines[node.end_lineno - 1], node.end_col_offset)
        except (IndexError, TypeError, ValueError):
            return _fault("parse_error")
        value = source[start:end]
        definitions.append({
            "unit_id": node.name.removeprefix("test_"),
            "name": node.name,
            "span": {"encoding": "json-string-codepoints-v1", "start": start, "end": end},
            "source_value": value,
            "source_value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        })
    names = [item["name"] for item in definitions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    return {
        "status": "unsupported" if nested else "ok",
        "definitions": definitions,
        "duplicate_definition_names": duplicates,
        "nested_definitions_unsupported": nested,
    }


def _fault(code: str) -> dict:
    return {"status": code, "definitions": [], "duplicate_definition_names": [],
            "nested_definitions_unsupported": []}


def _physical_lines(source: str) -> tuple[list[str], list[int]]:
    lines, starts, i, start = [], [], 0, 0
    while i < len(source):
        ch = source[i]
        if ch == "\r":
            end = i + 2 if i + 1 < len(source) and source[i + 1] == "\n" else i + 1
        elif ch == "\n":
            end = i + 1
        else:
            i += 1
            continue
        starts.append(start)
        lines.append(source[start:end])
        start, i = end, end
    starts.append(start)
    lines.append(source[start:])
    return lines, starts


def _byte_col_to_codepoints(line: str, byte_col: int) -> int:
    if type(byte_col) is not int or byte_col < 0:
        raise ValueError("invalid AST byte column")
    used = 0
    for index, ch in enumerate(line):
        if used == byte_col:
            return index
        used += len(ch.encode("utf-8"))
        if used > byte_col:
            raise ValueError("AST byte column splits a code point")
    if used == byte_col:
        return len(line)
    raise ValueError("AST byte column exceeds line")
