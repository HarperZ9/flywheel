"""Structured command extraction KV source branches."""
from __future__ import annotations

from typing import Any

from harness.cross_harness_kv_source_common import _answered, _cwd, _ensure_flags, _field, _fields, _join, _row_by_id, _str_field


def _kv_sta_001(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    schema = _fields(rows, "tool-schema:run_model_endpoint_gate")
    request = _fields(rows, "operator-request:gate-32b")
    paths = _fields(rows, "path-contract:temp-only")
    flags = [
        "--profile-artifact",
        "--models",
        "--backends",
        "--prompt",
        "--timeout-seconds",
        "--max-tokens",
        "--seed",
        "--out",
        "--markdown-out",
        "--run-id",
    ]
    _ensure_flags(_field(schema, "allowed_args"), flags, "endpoint_gate_schema_does_not_admit_expected_flags")
    root = _str_field(paths, "root")
    return _answered(
        task_id,
        {
            "argv": [
                "python",
                _str_field(schema, "script"),
                "--profile-artifact",
                _join(root, _field(paths, "profile")),
                "--models",
                _field(request, "model"),
                "--backends",
                _field(request, "backend"),
                "--prompt",
                _field(request, "prompt"),
                "--timeout-seconds",
                _field(request, "timeout_seconds"),
                "--max-tokens",
                _field(request, "max_tokens"),
                "--seed",
                _field(request, "seed"),
                "--out",
                _join(root, _field(paths, "out")),
                "--markdown-out",
                _join(root, _field(paths, "markdown_out")),
                "--run-id",
                _field(request, "run_id"),
            ],
            "cwd": _cwd(paths),
        },
        [
            "tool-schema:run_model_endpoint_gate",
            "operator-request:gate-32b",
            "path-contract:temp-only",
        ],
    )


def _kv_sta_002(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    schema = _fields(rows, "tool-schema:run_agentic_task_set_manifest")
    request = _fields(rows, "operator-request:manifest-kv")
    paths = _fields(rows, "path-contract:temp-only")
    flags = [
        "--task-set",
        "--adapter",
        "--artifact-dir",
        "--provider-roles",
        "--out",
        "--markdown-out",
        "--run-id",
    ]
    _ensure_flags(_field(schema, "allowed_args"), flags, "manifest_schema_does_not_admit_expected_flags")
    root = _str_field(paths, "root")
    return _answered(
        task_id,
        {
            "argv": [
                "python",
                _str_field(schema, "script"),
                "--task-set",
                _join(root, _field(paths, "task_set")),
                "--adapter",
                _join(root, _field(paths, "adapter")),
                "--artifact-dir",
                _join(root, _field(paths, "artifact_dir")),
                "--provider-roles",
                _field(request, "provider_roles"),
                "--out",
                _join(root, _field(paths, "out")),
                "--markdown-out",
                _join(root, _field(paths, "markdown_out")),
                "--run-id",
                _field(request, "run_id"),
            ],
            "cwd": _cwd(paths),
        },
        [
            "tool-schema:run_agentic_task_set_manifest",
            "operator-request:manifest-kv",
            "path-contract:temp-only",
        ],
    )


DERIVERS = {
    "kv-sta-001-endpoint-gate-argv": _kv_sta_001,
    "kv-sta-002-manifest-argv": _kv_sta_002,
}
