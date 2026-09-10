"""Shape validation for untrusted review inputs, without running log actions."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def read_doc(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("unsafe_or_oversized_evidence")
    def reject_constant(value: str) -> None:
        raise ValueError("nonfinite_json")
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    doc = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
    _validate_scalars(doc)
    if not isinstance(doc, dict):
        raise ValueError("object_required")
    return doc


def _validate_scalars(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_json")
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif isinstance(value, dict):
        for key, child in value.items():
            _validate_scalars(key)
            _validate_scalars(child)
    elif isinstance(value, list):
        for child in value:
            _validate_scalars(child)


def _rows(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(row, dict) for row in value)


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(row, str) for row in value)


def valid_doc(name: str, doc: dict[str, Any]) -> bool:
    if name.startswith("domain-state"):
        tables = doc.get("tables")
        return (isinstance(tables, dict)
                and all(_rows(tables.get(key)) for key in ("incident", "sys_attachment"))
                and all(isinstance(row.get("work_notes", []), list) and isinstance(row.get("state"), str) for row in tables["incident"]))
    if name == "action-log.json":
        rows = doc.get("events")
        return (_rows(rows) and all(isinstance(row.get("event"), dict)
                and isinstance(row["event"].get("mutation"), dict) for row in rows))
    if name == "receipt.json":
        cases = doc.get("cases")
        return (_rows(cases) and bool(cases) and isinstance(doc.get("calibration"), dict)
                and all(isinstance(row.get("case_id"), str)
                        and isinstance(row.get("passed"), bool)
                        and _strings(row.get("failure_codes", [])) for row in cases))
    if name == "source-basis.json":
        entries = doc.get("entries", [])
        return (_rows(entries) and all(_strings(row.get("used_for", []))
                and all(isinstance(row.get(key), str) for key in ("id", "retrieved_at_utc", "body_sha256"))
                and isinstance(row.get("body_stored"), bool) for row in entries))
    if name == "calibration-receipt.json":
        rows = doc.get("case_results")
        return (_rows(rows) and bool(rows) and type(doc.get("false_accepts")) is int
                and all(_strings(row.get("failure_codes", [])) for row in rows))
    return True
