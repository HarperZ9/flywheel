"""Typed diagnostics for malformed cross-harness model output."""
from __future__ import annotations

import json
from typing import Any

from harness.cross_harness_artifacts import _declared_names, _safe_artifact_name


class _DuplicateJsonKey(ValueError):
    pass


def _diagnostic_pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def diagnose_output_failure(output_text: str, declared_names: list[str], usage: dict[str, Any],
                            policy: dict[str, Any]) -> dict[str, Any]:
    diagnostics = _diagnose_envelope(output_text, declared_names)
    runtime: dict[str, Any] = {}
    max_output_tokens = policy.get("max_output_tokens")
    per_call = usage.get("per_call") if isinstance(usage, dict) else None
    last_call = per_call[-1] if isinstance(per_call, list) and per_call and isinstance(per_call[-1], dict) else None
    eval_count = last_call.get("eval_count") if isinstance(last_call, dict) else None
    if type(max_output_tokens) is int and type(eval_count) is int and eval_count == max_output_tokens:
        diagnostics["codes"] = sorted(set(diagnostics.get("codes", [])) | {"length_cap_reached"})
        runtime["length_cap_reached"] = {"status": "observed", "last_eval_count": eval_count,
                                          "max_output_tokens": max_output_tokens,
                                          "does_not_prove": ["truncation"]}
    diagnostics["runtime"] = runtime
    return diagnostics


def _base(codes: set[str] | None = None) -> dict[str, Any]:
    return {"schema": "harness.cross-harness-output-diagnostics/v1", "codes": sorted(codes or set()),
            "parser": {"status": "not_checked"}, "artifact_comparison": {"status": "not_checked"}}


def _diagnose_envelope(output_text: str, declared_names: list[str]) -> dict[str, Any]:
    codes = {"markdown_fence_at_start"} if output_text.lstrip().startswith("```") else set()
    diagnostics = _base(codes)
    try:
        names = _declared_names(declared_names)
    except ValueError as exc:
        diagnostics.update(codes=sorted(codes | {"declared_artifacts_invalid"}),
                           declared_artifacts={"status": "invalid", "error_type": type(exc).__name__})
        return diagnostics
    diagnostics["declared_artifacts"] = {"status": "valid", "names": list(names)}
    try:
        envelope = json.loads(output_text, object_pairs_hook=_diagnostic_pairs)
    except json.JSONDecodeError as exc:
        diagnostics.update(codes=sorted(codes | {"json_parse_error"}),
                           parser={"status": "json_decode_error", "error_type": type(exc).__name__,
                                   "line": exc.lineno, "column": exc.colno, "position": exc.pos})
        return diagnostics
    except _DuplicateJsonKey:
        diagnostics.update(codes=sorted(codes | {"duplicate_key_rejected"}),
                           parser={"status": "duplicate_key_rejected", "error_type": "ValueError"})
        return diagnostics
    except ValueError as exc:
        diagnostics.update(codes=sorted(codes | {"json_value_error"}),
                           parser={"status": "json_value_error", "error_type": type(exc).__name__})
        return diagnostics
    diagnostics["parser"] = {"status": "parsed"}
    if not isinstance(envelope, dict) or set(envelope) != {"artifacts"} or not isinstance(envelope.get("artifacts"), dict):
        diagnostics.update(codes=sorted(codes | {"artifact_envelope_shape_invalid"}),
                           artifact_comparison={"status": "shape_invalid"})
        return diagnostics
    return _artifact_comparison(diagnostics, codes, names, envelope["artifacts"])


def _artifact_comparison(diagnostics: dict[str, Any], codes: set[str], names: list[str], artifacts: dict[str, Any]) -> dict[str, Any]:
    actual_names = []
    for name in artifacts:
        try:
            _safe_artifact_name(name, "artifact name")
        except ValueError:
            diagnostics.update(codes=sorted(codes | {"artifact_name_invalid"}),
                               artifact_comparison={"status": "invalid_artifact_name"})
            return diagnostics
        actual_names.append(name)
    missing, extra_count = sorted(set(names) - set(actual_names)), len(set(actual_names) - set(names))
    comparison = {"status": "matched" if not missing and not extra_count else "mismatch",
                  "missing_declared_artifacts": missing, "extra_artifact_count": extra_count}
    if missing or extra_count: codes.add("artifact_set_mismatch")
    if missing: codes.add("missing_declared_artifact")
    if extra_count: codes.add("extra_artifact")
    diagnostics["artifact_comparison"] = comparison
    if not missing and not extra_count:
        _diagnose_value_types(codes, comparison, names, artifacts)
    diagnostics["codes"] = sorted(codes)
    return diagnostics


def _diagnose_value_types(codes: set[str], comparison: dict[str, Any], names: list[str], artifacts: dict[str, Any]) -> None:
    for name in names:
        value = artifacts[name]
        if (name.endswith(".md") and not isinstance(value, str)) or (not name.endswith(".md") and not isinstance(value, dict)):
            codes.add("artifact_value_type_mismatch")
            comparison.update(status="value_type_mismatch", mismatched_artifacts=[name])
            return
        if name.endswith(".md"):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                codes.add("artifact_encoding_failed")
                comparison.update(status="encoding_failed", mismatched_artifacts=[name],
                                  encoding_error_type=type(exc).__name__)
                return
        else:
            try:
                json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            except UnicodeEncodeError as exc:
                codes.add("artifact_encoding_failed")
                comparison.update(status="encoding_failed", mismatched_artifacts=[name],
                                  encoding_error_type=type(exc).__name__)
                return
            except (TypeError, ValueError) as exc:
                codes.add("artifact_serialization_failed")
                comparison.update(status="serialization_failed", mismatched_artifacts=[name],
                                  serialization_error_type=type(exc).__name__)
                return
