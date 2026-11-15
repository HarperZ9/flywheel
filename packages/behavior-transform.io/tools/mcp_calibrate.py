#!/usr/bin/env python3
"""
mcp_calibrate â€” MCP server output calibration helper.

Closes the MCP_OUT gap in the container ecosystem. Import this module in
any WARDEN MCP server and call calibrate() on response text before
returning it to the harness. The model then receives calibrated consulting-
register language â€” consistent with every other channel in the ecosystem.

Architecture note
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MCP tool responses are the one channel where PreToolUse hooks cannot
intercept (the tool runs server-side before the hook fires). PostToolUse
fires after the fact but cannot modify the response the model sees.
Calibration must happen at the source â€” inside the MCP server itself.

Usage (in each MCP server's tool handler)
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from mcp_calibrate import calibrate, calibrate_response

    # Plain text response:
    return calibrate(text)

    # Dict response (auto-extracts text fields):
    return calibrate_response(response_dict)

    # Batch (list of strings):
    from mcp_calibrate import calibrate_batch
    return calibrate_batch(items)

Thread safety: the substitution table is built once and cached; safe for
concurrent use inside async MCP servers.

Performance: ~0.1 ms per 1 KB of text for the vocabulary pass. The full
calibration is vocabulary-only. Call calibrate_deep(text) for any
future extended-pass work.
"""
from __future__ import annotations

import copy
import importlib.util
import re
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from io_state import set_env_mode, split_io_toggles, transforms_enabled

_TOOLS_ROOT = Path(__file__).resolve().parent
_VOCAB_CANDIDATES = [
    _TOOLS_ROOT / "vocabulary_map.py",
]

_lock   = threading.Lock()
_subs:  list[tuple[re.Pattern, str, str]] | None = None
_loaded = False


def _load() -> list[tuple[re.Pattern, str, str]]:
    global _subs, _loaded
    with _lock:
        if _loaded:
            return _subs or []
        _subs = _build_subs(_load_vm())
        _loaded = True
        return _subs or []


def _load_vm() -> dict:
    for p in _VOCAB_CANDIDATES:
        if not p.is_file():
            continue
        spec = importlib.util.spec_from_file_location("_vm_mcp", p)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_vm_mcp"] = mod
        try:
            spec.loader.exec_module(mod)
            return mod.__dict__
        except Exception:
            sys.modules.pop("_vm_mcp", None)
    return {}


def _build_subs(vm: dict) -> list[tuple[re.Pattern, str, str]]:
    calibrations = vm.get("CALIBRATIONS", ())
    keep = {k.lower() for k in (vm.get("KEEP_TERMS", None) or [])}
    candidates: list[tuple[str, str, str]] = []
    for c in calibrations:
        original = getattr(c, "original", None)
        calibrated_form = getattr(c, "calibrated", None)
        severity = (getattr(c, "severity", "") or "").lower()
        if not isinstance(original, str) or not isinstance(calibrated_form, str):
            continue
        if original.lower() in keep:
            continue
        tier = (
            "T1" if severity in ("tier1", "tier_1", "t1") else
            "T2" if severity in ("tier2", "tier_2", "t2") else
            severity.upper() or "??"
        )
        candidates.append((original, calibrated_form, tier))
    candidates.sort(key=lambda t: len(t[0]), reverse=True)
    return [
        (re.compile(r"\b" + re.escape(src) + r"\b", re.IGNORECASE), dst, tier)
        for src, dst, tier in candidates
    ]


def _apply(text: str, subs: list) -> tuple[str, Counter]:
    counter: Counter = Counter()
    for pat, dst, tier in subs:
        def _repl(m: re.Match, _d: str = dst, _t: str = tier) -> str:
            counter[_t] += 1
            return _d
        text = pat.sub(_repl, text)
    return text, counter


def calibrate(text: str) -> str:
    """Calibrate a plain text string. Returns consulting-register form."""
    if not transforms_enabled():
        return text
    if not text:
        return text
    subs = _load()
    if not subs:
        return text
    calibrated, _ = _apply(text, subs)
    return calibrated


def calibrate_with_counts(text: str) -> tuple[str, Counter]:
    """Calibrate and return (calibrated_text, substitution_counter)."""
    if not transforms_enabled():
        return text, Counter()
    if not text:
        return text, Counter()
    subs = _load()
    if not subs:
        return text, Counter()
    return _apply(text, subs)


TEXT_KEYS: frozenset[str] = frozenset({
    # Original set
    "content", "text", "output", "result",
    "message", "description", "summary", "body",
    # Extended â€” richer MCP response context
    "data", "response", "value", "error", "details", "info", "raw",
    "stdout", "stderr", "metadata", "context", "title",
    "label", "annotation", "note", "reason", "cause", "hint",
})

_MCP_CONTENT_KEYS: frozenset[str] = frozenset({
    "text",
    "description",
    "name",
    "title",
    "label",
    "annotations",
    "mimeType",
})


def calibrate_response(response: Any, extra_keys: "frozenset[str] | None" = None) -> Any:
    """
    Calibrate a dict-shaped MCP tool response in-place.

    Recursively calibrates string values under TEXT_KEYS (module-level constant).
    Pass extra_keys to calibrate additional fields without mutating the default set.
    Other keys are left untouched. Lists of strings are calibrated element-wise.
    """
    if not transforms_enabled():
        return response
    active_keys = TEXT_KEYS if extra_keys is None else TEXT_KEYS | extra_keys
    if isinstance(response, str):
        return calibrate(response)
    if isinstance(response, list):
        return calibrate_batch(response)
    if isinstance(response, dict):
        out = {}
        for k, v in response.items():
            if k in active_keys:
                if isinstance(v, str):
                    out[k] = calibrate(v)
                elif isinstance(v, list):
                    out[k] = calibrate_batch(v)
                elif isinstance(v, dict):
                    out[k] = calibrate_response(v, extra_keys)
                else:
                    out[k] = v
            else:
                out[k] = v
        return out
    return response


def _calibrate_all_strings(value: Any) -> Any:
    if isinstance(value, str):
        return calibrate(value)
    if isinstance(value, list):
        return [_calibrate_all_strings(item) for item in value]
    if isinstance(value, dict):
        return {k: _calibrate_all_strings(v) for k, v in value.items()}
    return value


def calibrate_jsonrpc_request(request: dict) -> dict:
    """
    Return a calibrated copy of an MCP JSON-RPC request.

    The outbound request side calibrates operator-provided string arguments
    without changing protocol structure, ids, tool names, or numeric values.
    """
    if not transforms_enabled():
        return request
    out = copy.deepcopy(request)
    method = out.get("method")
    params = out.get("params")
    if not isinstance(params, dict):
        return out

    if method == "tools/call":
        arguments = params.get("arguments")
        if isinstance(arguments, dict):
            params["arguments"] = _calibrate_all_strings(arguments)
        return out

    if method == "prompts/get":
        for key, value in list(params.items()):
            if key != "name":
                params[key] = _calibrate_all_strings(value)
    return out


def calibrate_jsonrpc_response(response: dict) -> dict:
    """
    Return a calibrated copy of an MCP JSON-RPC response.

    Text content blocks are calibrated directly. Other JSON-RPC result shapes
    fall back to key-based MCP content calibration. Binary-ish fields such as
    image data are intentionally preserved.
    """
    if not transforms_enabled():
        return response
    out = copy.deepcopy(response)

    error = out.get("error")
    if isinstance(error, dict):
        out["error"] = calibrate_response(error, _MCP_CONTENT_KEYS)
        return out

    result = out.get("result")
    if not isinstance(result, dict):
        return out

    content = result.get("content")
    if isinstance(content, list):
        next_content = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                next_item = dict(item)
                next_item["text"] = calibrate(item["text"])
                next_content.append(next_item)
            else:
                next_content.append(copy.deepcopy(item))
        result["content"] = next_content
        return out

    out["result"] = calibrate_response(result, _MCP_CONTENT_KEYS)
    return out


def calibrate_batch(items: list[Any]) -> list[Any]:
    """Calibrate each string in a list; non-strings passed through."""
    if not transforms_enabled():
        return items
    subs = _load()
    if not subs:
        return items
    result = []
    for item in items:
        if isinstance(item, str):
            cal, _ = _apply(item, subs)
            result.append(cal)
        elif isinstance(item, dict):
            result.append(calibrate_response(item))
        else:
            result.append(item)
    return result


def calibrate_deep(text: str, server_name: str = "") -> str:
    """Semantic modulation pass -- vocabulary calibration only."""
    return calibrate(text, server_name=server_name)
