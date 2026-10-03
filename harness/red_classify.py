"""red_classify.py -- why did a test fail on the pre-change code?

Reads a pytest JUnit report and sorts each test into one class:

  red-assert          failed on an assertion the test itself made (`assert`,
                      `pytest.raises` that did not raise, `pytest.fail`). The
                      useful kind of red.
  red-missing-symbol  failed because a name the change adds does not exist yet
                      (ImportError, ModuleNotFoundError, AttributeError,
                      NameError, or an unexpected keyword argument naming a new
                      parameter). Expected for a new feature; never credited.
  red-error           any other exception, a fixture error, a collection error,
                      or an AssertionError raised inside the code under test.
  skipped             the test skipped itself; it checked nothing.
  green               passed on the pre-change code.

Standard library only. Pure functions over text; nothing here runs a test.
"""
from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

CLASSES = ("red-assert", "red-missing-symbol", "red-error", "skipped", "green",
           "indeterminate")
_LOCATION = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?P<exc>[A-Za-z_][\w.]*)\s*$")
_MISSING = (
    (re.compile(r"cannot import name '([^']+)'"), "ImportError"),
    (re.compile(r"No module named '([^']+)'"), "ModuleNotFoundError"),
    (re.compile(r"module '[^']+' has no attribute '([^']+)'"), "AttributeError"),
    (re.compile(r"type object '[^']+' has no attribute '([^']+)'"), "AttributeError"),
    (re.compile(r"'(?!NoneType)[^']+' object has no attribute '([^']+)'"), "AttributeError"),
    (re.compile(r"name '([^']+)' is not defined"), "NameError"),
    (re.compile(r"unexpected keyword argument '([^']+)'"), "TypeError"),
)
_ASSERT_TYPES = {"AssertionError", "Failed", "pytest.fail.Exception",
                 "_pytest.outcomes.Failed"}


def is_test_path(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    name = parts[-1] if parts else ""
    return (name.startswith("test_") or name.endswith("_test.py")
            or name == "conftest.py" or any(p in ("tests", "test") for p in parts[:-1]))


def defined_names(source: str) -> set:
    """Every name a Python source defines: functions, classes, parameters,
    assignment targets and attributes assigned through `self.`."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args
            out.update(a.arg for a in args.args + args.kwonlyargs + args.posonlyargs)
        elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Store):
            out.add(node.id if isinstance(node, ast.Name) else node.attr)
        elif isinstance(node, ast.alias):
            out.add((node.asname or node.name).split(".")[0])
    return out


def module_names(path: str) -> set:
    """Dotted module names a source path can be imported as (with and without src/)."""
    parts = list(PurePosixPath(path.replace("\\", "/")).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    out = {".".join(parts[i:]) for i in range(len(parts))}
    return {n for n in out if n}


def _location(text: str):
    for line in reversed((text or "").strip().splitlines()):
        match = _LOCATION.match(line.strip())
        if match:
            return match.group("path"), match.group("exc")
    return None, None


def _error_line(text: str, message: str) -> str:
    lines = [ln.strip()[1:].strip() for ln in (text or "").splitlines()
             if ln.strip().startswith("E ")]
    return lines[-1] if lines else (message or "")


def classify_failure(text: str, message: str, new_names: set) -> tuple:
    """(class, detail) for one failure or error element."""
    path, exc = _location(text)
    detail = _error_line(text, message)
    exc = exc or (detail.split(":", 1)[0] if ":" in detail else "")
    if exc in _ASSERT_TYPES or exc.endswith(".Failed"):
        if path is None or is_test_path(path):
            return "red-assert", detail
        return "red-error", "AssertionError raised inside the code under test: " + detail
    for pattern, kind in _MISSING:
        match = pattern.search(detail) or pattern.search(message or "")
        if match and (exc.endswith(kind) or kind in detail):
            name = match.group(1)
            leaves = {name, name.rsplit(".", 1)[-1]}
            if leaves & new_names:
                return "red-missing-symbol", detail
            if kind in ("ImportError", "ModuleNotFoundError", "NameError") and not new_names:
                return "red-missing-symbol", detail
            return "red-error", detail
    return "red-error", detail


def _node_key(classname: str, name: str) -> tuple:
    return classname or "", name.split("[", 1)[0]


def node_parts(node_id: str) -> tuple:
    """('tests.test_x' or 'tests.test_x.TestC', 'test_name') for a pytest node id."""
    file_part, _, rest = node_id.partition("::")
    module = ".".join(PurePosixPath(file_part.replace("\\", "/")).with_suffix("").parts)
    pieces = [p for p in rest.split("::") if p]
    name = pieces[-1].split("[", 1)[0] if pieces else ""
    classname = ".".join([module, *pieces[:-1]])
    return classname, name


def parse_junit(xml_text: str, new_names: set) -> dict:
    """{(classname, name): [ (class, detail) per parametrized case ]} plus
    {('<collection>', module): (class, detail)} for collection failures."""
    out: dict = {}
    root = ET.fromstring(xml_text)
    for case in root.iter("testcase"):
        key = _node_key(case.get("classname", ""), case.get("name", ""))
        result = ("green", "")
        for child in case:
            if child.tag in ("failure", "error"):
                if child.get("message") == "collection failure":
                    key = ("<collection>", case.get("name", ""))
                result = classify_failure(child.text or "", child.get("message") or "",
                                          new_names)
                break
            if child.tag == "skipped":
                result = ("skipped", child.get("message") or "")
        out.setdefault(key, []).append(result)
    return out


_RANK = {"red-assert": 0, "red-missing-symbol": 1, "red-error": 2, "skipped": 3, "green": 4}


def outcome_for(node_id: str, parsed: dict) -> tuple:
    """Fold a test's parametrized cases into one (class, detail). A missing
    report row means the file did not collect; its collection error decides."""
    classname, name = node_parts(node_id)
    rows = parsed.get((classname, name))
    if not rows:
        module = node_id.partition("::")[0].replace("\\", "/")
        module = ".".join(PurePosixPath(module).with_suffix("").parts)
        for (kind, mod), results in parsed.items():
            if kind == "<collection>" and (mod == module or module.endswith(mod)
                                           or mod.endswith(module)):
                return results[0]
        return "red-error", "the test was not collected or not reported"
    return min(rows, key=lambda r: _RANK.get(r[0], 9))
