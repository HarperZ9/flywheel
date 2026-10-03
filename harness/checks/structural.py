"""structural.py -- schema, AST and state-machine checks.

Each function takes (subject, spec) and returns (verdict, code, reason).
"""
from __future__ import annotations

import ast
import re

from ..integrity import scan_reward_hacking
from .receipt import FAIL, PASS, UNVERIFIABLE

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool,
          "null": type(None)}


def _type_ok(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _bounds(value, schema: dict, path: str) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path}: {value} is below minimum {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path}: {value} is above maximum {schema['maximum']}"
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            return f"{path}: shorter than minLength {schema['minLength']}"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{path}: longer than maxLength {schema['maxLength']}"
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            return f"{path}: does not match pattern {schema['pattern']}"
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            return f"{path}: fewer than minItems {schema['minItems']}"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{path}: more than maxItems {schema['maxItems']}"
    return None


def _object(value: dict, schema: dict, path: str) -> str | None:
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in value:
            return f"{path}: missing required field {key!r}"
    if schema.get("additionalProperties") is False:
        extra = sorted(set(value) - set(props))
        if extra:
            return f"{path}: unexpected field {extra[0]!r}"
    for key, sub in props.items():
        if key in value:
            err = _validate(value[key], sub, f"{path}.{key}")
            if err:
                return err
    return None


def _validate(value, schema: dict, path: str = "$") -> str | None:
    """First violation of a JSON Schema subset, or None."""
    types = schema.get("type")
    if types is not None:
        names = types if isinstance(types, list) else [types]
        if not any(_type_ok(value, n) for n in names):
            return f"{path}: expected {'/'.join(names)}, got {type(value).__name__}"
    if "const" in schema and value != schema["const"]:
        return f"{path}: expected the constant {schema['const']!r}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: {value!r} is not one of {schema['enum']}"
    err = _bounds(value, schema, path)
    if err:
        return err
    if isinstance(value, dict):
        return _object(value, schema, path)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            err = _validate(item, schema["items"], f"{path}[{i}]")
            if err:
                return err
    return None


def schema_check(subject, spec: dict) -> tuple[str, str, str]:
    """spec: {"schema": {...}} using type, required, properties,
    additionalProperties, enum, const, items, min/max bounds and pattern."""
    schema = spec.get("schema")
    if not isinstance(schema, dict):
        return UNVERIFIABLE, "no_schema", "the spec carries no schema"
    err = _validate(subject, schema)
    return (FAIL, "schema_violation", err) if err else (PASS, "conforms", "matches the schema")


def _names(tree: ast.AST) -> tuple[set, set, set]:
    defs, calls, imports = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return defs, calls, imports


def ast_check(subject, spec: dict) -> tuple[str, str, str]:
    """subject: Python source. spec: require_defs, forbid_calls, forbid_imports,
    reward_hacking (default True: integrity.scan_reward_hacking flags fail)."""
    if not isinstance(subject, str) or not subject.strip():
        return FAIL, "empty", "no source to parse"
    try:
        tree = ast.parse(subject)
    except SyntaxError as exc:
        return FAIL, "unparseable", f"not valid Python: {exc.msg} (line {exc.lineno})"
    defs, calls, imports = _names(tree)
    for name in spec.get("require_defs", []):
        if name not in defs:
            return FAIL, "missing_def", f"does not define {name!r}"
    for name in spec.get("forbid_calls", []):
        if name in calls:
            return FAIL, "forbidden_call", f"calls {name}()"
    for name in spec.get("forbid_imports", []):
        if name in imports:
            return FAIL, "forbidden_import", f"imports {name}"
    if spec.get("reward_hacking", True):
        flags = scan_reward_hacking(subject)
        if flags:
            return FAIL, f"reward_hacking:{flags[0].kind}", flags[0].detail
    return PASS, "conforms", "parses and meets the structural rules"


def fsm_check(subject, spec: dict) -> tuple[str, str, str]:
    """subject: a list of events. spec: start, transitions {state: {event: next}},
    accept (list of final states)."""
    transitions = spec.get("transitions")
    start = spec.get("start")
    if not isinstance(transitions, dict) or start not in transitions:
        return UNVERIFIABLE, "no_machine", "the spec has no start state in its transitions"
    if not isinstance(subject, list):
        return FAIL, "not_a_trace", "the subject is not a list of events"
    state = start
    for i, event in enumerate(subject):
        nxt = transitions.get(state, {}).get(event)
        if nxt is None:
            return FAIL, "illegal_transition", f"event {i} {event!r} is not allowed in {state!r}"
        state = nxt
    if state not in spec.get("accept", []):
        return FAIL, "not_accepting", f"the trace ends in {state!r}, not a final state"
    return PASS, "accepted", f"the trace ends in final state {state!r}"
