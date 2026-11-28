# SPDX-License-Identifier: MIT
"""Low-level fail-closed primitive guards for gpu_shader_520_gate."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
PREFIXED_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")

REQUIRED_GPU_TARGETS = frozenset({"wgsl", "hlsl", "msl", "spirv", "glsl"})
REQUIRED_VALIDATORS = (
    "dxc",
    "glslang",
    "spirv_val_direct",
    "spirv_val_glsl",
    "spirv_val_naga",
    "naga_wgsl",
    "naga_msl31",
    "msl_spec",
)
REQUIRED_RLVR_ARTIFACTS = (
    "jfc3p_14b_oracle_v14_mit.jsonl",
    "train_rlvr_v14.jsonl",
    "eval_rlvr_v14.jsonl",
    "JFC3P_14B_Oracle_v14_Colab_H100_Ready.ipynb",
)


class Gpu520GateError(ValueError):
    """Raised when a GPU 520, RLVR v14, or Paper #8 manifest fails parsing."""


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load a UTF-8 JSON object from disk, rejecting non-dict payloads."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Gpu520GateError(f"{label}: unreadable JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise Gpu520GateError(f"{label}: expected JSON object")
    return raw


def require_dict(obj: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    val = obj.get(key)
    if not isinstance(val, dict):
        raise Gpu520GateError(f"{label}: missing or non-object field '{key}'")
    return val


def require_list(obj: dict[str, Any], key: str, label: str) -> list[Any]:
    val = obj.get(key)
    if not isinstance(val, list) or not val:
        raise Gpu520GateError(f"{label}: missing or empty list '{key}'")
    return val


def require_str(obj: dict[str, Any], key: str, label: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise Gpu520GateError(f"{label}: missing or empty string '{key}'")
    return val


def require_bool(obj: dict[str, Any], key: str, label: str) -> bool:
    val = obj.get(key)
    if not isinstance(val, bool):
        raise Gpu520GateError(f"{label}: field '{key}' must be boolean")
    return val


def require_int(obj: dict[str, Any], key: str, label: str, *, minimum: int = 0) -> int:
    val = obj.get(key)
    if isinstance(val, bool) or not isinstance(val, int):
        raise Gpu520GateError(f"{label}: field '{key}' must be integer")
    if val < minimum:
        raise Gpu520GateError(f"{label}: field '{key}' ({val}) < {minimum}")
    return val


def require_hex_64(obj: dict[str, Any], key: str, label: str) -> str:
    val = require_str(obj, key, label)
    if not HEX_64_RE.match(val):
        raise Gpu520GateError(f"{label}: invalid 64-hex '{key}'")
    return val


def require_prefixed_sha256(obj: dict[str, Any], key: str, label: str) -> str:
    val = require_str(obj, key, label)
    if not PREFIXED_SHA256_RE.match(val):
        raise Gpu520GateError(f"{label}: invalid prefixed sha256 '{key}'")
    return val


def require_str_tuple(obj: dict[str, Any], key: str, label: str) -> tuple[str, ...]:
    vals = require_list(obj, key, label)
    out: list[str] = []
    for item in vals:
        if not isinstance(item, str) or not item.strip():
            raise Gpu520GateError(f"{label}: non-string entry in '{key}'")
        out.append(item)
    return tuple(out)
