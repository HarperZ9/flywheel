"""Gateway grammar helpers for native output validation."""
from __future__ import annotations

import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
REL = re.compile(r"(?!/)(?!.*(?:^|/)\.\.?(?:/|$))[A-Za-z0-9._/-]{1,240}\Z")
SCOPES = ("", "task", "goal", "session")


def _ref(value: object, kind: str) -> dict:
    if (type(value) is not dict or set(value) != {"kind", "path", "sha256"}
            or value.get("kind") != kind
            or type(value.get("path")) is not str
            or REL.fullmatch(value["path"]) is None
            or SHA.fullmatch(value.get("sha256", "")) is None):
        raise ValueError
    return value


def _dir(value: object) -> None:
    if (type(value) is not dict or set(value) != {"kind", "path"}
            or value.get("kind") != "workspace-dir"
            or type(value.get("path")) is not str
            or REL.fullmatch(value["path"]) is None):
        raise ValueError


def _artifact(value: object) -> None:
    if (type(value) is not dict or set(value) != {"kind", "path"}
            or value.get("kind") != "run-artifact"
            or type(value.get("path")) is not str
            or REL.fullmatch(value["path"]) is None):
        raise ValueError


def validate_output_check_operation(value: dict) -> None:
    contract = _ref(value.get("contract"), "workspace-file")
    answer = _ref(value.get("answer"), "workspace-file")
    for name in ("allow_commands", "strict", "json", "stream",
                 "verify_lean"):
        if name in value and type(value[name]) is not bool:
            raise ValueError
    if value.get("scope", "") not in SCOPES:
        raise ValueError
    if "subject" in value and (type(value["subject"]) is not str
                               or len(value["subject"]) > 160):
        raise ValueError
    if "base_dir" in value:
        _dir(value["base_dir"])
    for name in ("out", "report", "lean", "ledger"):
        if name in value:
            _artifact(value[name])
    if "lean_bin" in value:
        _ref(value["lean_bin"], "workspace-file")
    expected = [f"data_output_check.contract:{contract['sha256'][:32]}",
                f"data_output_check.answer:{answer['sha256'][:32]}"]
    if value.get("data_refs") != expected:
        raise ValueError


def output_check_destination(value: dict) -> dict:
    return {"kind": "output-check", "ref": value["contract"]["sha256"][:16]}


def output_check_scopes(value: dict) -> tuple[str, ...]:
    selected = set()
    if value.get("allow_commands") or value.get("verify_lean"):
        selected.add("exec")
    if (value.get("verify_lean")
            or any(name in value for name in ("out", "report", "lean", "ledger"))):
        selected.add("write")
    if value.get("scope", "") or value.get("subject", ""):
        selected.add("write")
    return tuple(scope for scope in ("write", "exec") if scope in selected)
