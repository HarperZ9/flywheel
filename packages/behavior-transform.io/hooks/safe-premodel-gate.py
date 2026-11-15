#!/usr/bin/env python3
"""safe-input-output-gate - local input/output gate.

Runs local checks for UserPromptSubmit and PostToolUse events.

Results are handled locally. No extra context is emitted.

UserPromptSubmit:
  - Runs the local classifier.
  - Runs the local text helper.
  - Blocks with an opaque reason if the policy gate returns block=True.
  - Runs token optimization for large prompts (fail-open).
  - Otherwise exits silently.

PostToolUse:
  - Classifies tool output and runs the local text helper.
  - Always advisory-only; tool results cannot be recalled.
  - Exits silently.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parents[1] / "tools"


def _tool(name: str) -> Path | None:
    p = _tools_path() / name
    if p.is_file():
        return p
    return None


_MAX_CHARS = 8_000
_TIMEOUT   = 30


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _token_payload(text: str) -> dict | None:
    if os.environ.get("PREFIRE_TOKEN_OPTIMIZE", "1").strip().lower() in {
        "0", "false", "off",
    }:
        return None
    tools = _tools_path()
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        from token_optimizer import hook_payload_for_prompt
        return hook_payload_for_prompt(
            text,
            mode=os.environ.get("PREFIRE_TOKEN_OPTIMIZE_MODE", "context"),
            max_output_chars=_env_int("PREFIRE_TOKEN_OPTIMIZE_MAX_OUTPUT_CHARS", 3000),
            min_chars=_env_int("PREFIRE_TOKEN_OPTIMIZE_MIN_CHARS", 2000),
            min_savings_ratio=_env_float("PREFIRE_TOKEN_OPTIMIZE_MIN_SAVINGS", 0.20),
        )
    except Exception:
        return None


def _run_classify(text: str) -> tuple[dict | None, int]:
    tool = _tool("safe_classify.py")
    if tool is None:
        return None, -1
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "--no-archive"],
            input=text.encode("utf-8", "replace"),
            capture_output=True,
            timeout=_TIMEOUT,
            cwd=str(Path.home()),
        )
        if proc.stdout:
            try:
                return json.loads(proc.stdout.decode("utf-8", "replace")), proc.returncode
            except json.JSONDecodeError:
                pass
        return None, proc.returncode
    except (subprocess.SubprocessError, OSError):
        return None, -1


def _run_text_helper(text: str) -> None:
    tool = _tool("safe_text_helper.py")
    if tool is None:
        return
    try:
        subprocess.run(
            [sys.executable, str(tool), "--json"],
            input=text.encode("utf-8", "replace"),
            capture_output=True,
            timeout=_TIMEOUT,
            cwd=str(Path.home()),
        )
    except (subprocess.SubprocessError, OSError):
        pass


def _extract_text(tool_response) -> str:
    if tool_response is None:
        return ""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, (list, tuple)):
        return "\n".join(str(i) for i in tool_response)
    if isinstance(tool_response, dict):
        for key in ("output", "content", "stdout", "text", "result"):
            val = tool_response.get(key)
            if isinstance(val, str):
                return val
            if isinstance(val, list):
                return "\n".join(str(v) for v in val)
        return json.dumps(tool_response, ensure_ascii=False)
    return str(tool_response)


def main() -> int:
    import os as _cr_os, sys as _cr_sys
    _cr_sys.path.insert(0, _cr_os.path.dirname(_cr_os.path.abspath(__file__)))
    try:
        from _warden_cleanroom import cleanroom_active as _cr_active
        if _cr_active("safe-premodel-gate")[0]:
            return 0
    except Exception:
        pass

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    event = data.get("hook_event_name", "")

    if event == "UserPromptSubmit":
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return 0

        text_slice = prompt[:_MAX_CHARS]
        classify_result, _ = _run_classify(text_slice)
        _run_text_helper(text_slice)

        if classify_result and classify_result.get("policy", {}).get("block"):
            sys.stdout.write(
                json.dumps({"decision": "block", "reason": "Request cannot be processed."})
                + "\n"
            )
            return 0

        token_payload = _token_payload(prompt)
        if token_payload:
            sys.stdout.write(json.dumps(token_payload) + "\n")
        return 0

    if event == "PostToolUse":
        raw_text = _extract_text(data.get("tool_response"))
        if not raw_text.strip():
            return 0

        text_slice = raw_text[:_MAX_CHARS]
        _run_classify(text_slice)
        _run_text_helper(text_slice)
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f"safe-premodel-gate: {exc}\n")
        sys.exit(0)
