"""native_policy.py -- mechanical pre-tool policy enforcement for Flywheel.

Enforces standing safety and engineering rules directly on the tool boundary
(reads, writes, edits, patches, shell commands) instead of relying on prose
memory alone. Default rules stay portable; user- or workspace-specific rules
live in ~/.flywheel/policy.json and <workspace>/.flywheel/policy.json.

Set FLYWHEEL_POLICY_OFF=1 or POLICY_GUARD_OFF=1 to bypass for one command.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "flywheel.native-policy/v1"

_SECRET_NAMES = re.compile(
    r"(^|[\\/])(\.env(\.(?!example$)[^\\/\s]+)?|secrets\.json|credentials\.json|"
    r"id_rsa(\.pub)?|[^\\/\s]+\.(pem|key))$",
    re.IGNORECASE,
)
_FORCE_PUSH = re.compile(
    r"\bgit\s+push\b[^|;&]*(\s--force(-with-lease)?\b|\s-f\b|\s\+\S+:)"
)
_CHAINED_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
_PIPED_TEST = re.compile(
    r"\b(pytest|cargo\s+test|npm\s+test|ctest|node\s+--test)\b[^|]*\|\s*(tail|head|grep)\b"
)
_SKIP_ADD = re.compile(
    r"#\[ignore\]|@pytest\.mark\.(skip|xfail)|\bpytest\.skip\(|\b(it|test|describe)\.skip\(|"
    r"\.skip\(\s*['\"]|--skip[ =]|\bxit\(|\bxdescribe\(",
    re.IGNORECASE,
)
_ISSUE_LINK = re.compile(
    r"[\w.-]+/[\w.-]+#\d+|github\.com/[\w.-]+/[\w.-]+/issues/\d+",
    re.IGNORECASE,
)
_CODE_FILE = re.compile(
    r"\.(rs|py|js|mjs|cjs|ts|tsx|jsx|sh|ya?ml|toml|bld|c|cc|cpp|h|hpp|go|java|kt|cs|dart)$",
    re.IGNORECASE,
)

DEFAULT_POLICY: dict[str, Any] = {
    "schema": POLICY_SCHEMA,
    "block_secret_files": True,
    "block_force_push": True,
    "block_chained_merge": True,
    "block_piped_tests": True,
    "block_unlinked_skips": True,
    "deny_paths": [],
    "deny_terms_on_add": [],
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_policy(
    workspace: Path | None = None,
    flywheel_home: Path | None = None,
) -> dict[str, Any]:
    """Merge default policy with user (~/.flywheel/policy.json) and workspace overrides."""
    merged: dict[str, Any] = {
        **DEFAULT_POLICY,
        "deny_paths": [],
        "deny_terms_on_add": [],
    }
    home = flywheel_home or Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    sources = [home / "policy.json"]
    if workspace is not None:
        sources.append(Path(workspace) / ".flywheel" / "policy.json")
    for src in sources:
        if not src.is_file():
            continue
        raw = _read_json(src)
        for key in (
            "block_secret_files",
            "block_force_push",
            "block_chained_merge",
            "block_piped_tests",
            "block_unlinked_skips",
        ):
            if isinstance(raw.get(key), bool):
                merged[key] = raw[key]
        for list_key in ("deny_paths", "deny_terms_on_add"):
            extra = raw.get(list_key)
            if isinstance(extra, list):
                merged[list_key].extend(x for x in extra if isinstance(x, str) and x)
    return merged


def _deny(rule: str, reason: str, tool: str) -> dict[str, str]:
    return {"rule": rule, "reason": reason, "tool": tool}


def _check_paths(tool: str, args: dict[str, Any], policy: dict[str, Any]) -> dict[str, str] | None:
    path_blob = " ".join(
        str(args.get(k, "")) for k in ("path", "file_path", "pattern", "cmd", "command")
    )
    if policy.get("block_secret_files"):
        for key in ("path", "file_path"):
            val = str(args.get(key, "")).strip()
            if val and _SECRET_NAMES.search(val):
                return _deny("secret-file", f"access to secret-shaped path refused: {val}", tool)
    for pattern in policy.get("deny_paths", ()):
        if re.search(pattern, path_blob, re.IGNORECASE):
            return _deny("deny-path", f"path or command matches protected pattern: {pattern}", tool)
    return None


def _check_text(
    tool: str,
    path: str,
    new: str,
    old: str,
    policy: dict[str, Any],
) -> dict[str, str] | None:
    for term in policy.get("deny_terms_on_add", ()):
        rx = re.compile(term, re.IGNORECASE)
        if len(rx.findall(new)) > len(rx.findall(old)):
            return _deny("deny-term", f"change adds disallowed term matching {term!r}", tool)
    if policy.get("block_unlinked_skips") and _CODE_FILE.search(path or ""):
        added = len(_SKIP_ADD.findall(new)) > len(_SKIP_ADD.findall(old))
        if added and len(_ISSUE_LINK.findall(new)) <= len(_ISSUE_LINK.findall(old)):
            return _deny(
                "no-test-skipping",
                "adds a skipped or ignored test without an issue link (owner/repo#N)",
                tool,
            )
    return None


def _check_command(tool: str, cmd: str, policy: dict[str, Any]) -> dict[str, str] | None:
    compact = " ".join(cmd.split())
    if policy.get("block_force_push") and _FORCE_PUSH.search(compact):
        return _deny("no-force-push", "force pushes are blocked; push a new commit or revert", tool)
    if policy.get("block_chained_merge") and _CHAINED_MERGE.search(compact):
        before = _CHAINED_MERGE.split(compact)[0]
        steps = [s.strip() for s in re.split(r"&&|;|\|\|", before) if s.strip()]
        if any(not re.match(r"^(cd|pushd|set|export)\b", s) for s in steps):
            return _deny("no-chained-merge", "run gh pr merge as its own step after reading checks", tool)
    if (
        policy.get("block_piped_tests")
        and _PIPED_TEST.search(compact)
        and "pipefail" not in compact
        and "PIPESTATUS" not in compact
    ):
        return _deny(
            "pipes-swallow-exit-codes",
            "test runner piped to tail/head/grep without pipefail",
            tool,
        )
    for term in policy.get("deny_terms_on_add", ()):
        if re.search(term, compact, re.IGNORECASE) and re.search(
            r"\bgit\s+commit\b|\bgh\s+(pr|issue)\s+(create|edit|comment)\b", compact
        ):
            return _deny("deny-term", f"commit or PR text matches disallowed term {term!r}", tool)
    return None


def check_tool_call(
    name: str,
    args: dict[str, Any],
    *,
    workspace: Path | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Return a block dict if the tool call violates policy, else None."""
    if os.environ.get("FLYWHEEL_POLICY_OFF") == "1" or os.environ.get("POLICY_GUARD_OFF") == "1":
        return None
    active = policy if policy is not None else load_policy(workspace=workspace)
    hit = _check_paths(name, args, active)
    if hit is not None:
        return hit
    if name in ("write_file", "Write"):
        path = str(args.get("path") or args.get("file_path") or "")
        old = ""
        if workspace is not None and path:
            try:
                old = (Path(workspace) / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                old = ""
        return _check_text(name, path, str(args.get("content", "")), old, active)
    if name in ("edit_file", "Edit"):
        path = str(args.get("path") or args.get("file_path") or "")
        new = str(args.get("new") if "new" in args else args.get("new_string", ""))
        old = str(args.get("old") if "old" in args else args.get("old_string", ""))
        return _check_text(name, path, new, old, active)
    if name in ("apply_patch",):
        patch = str(args.get("patch", ""))
        added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        return _check_text(name, "patch.py", added, "", active)
    if name in ("run", "Bash", "PowerShell"):
        cmd = str(args.get("cmd") if "cmd" in args else args.get("command", ""))
        return _check_command(name, cmd, active)
    return None


def main(argv: list[str] | None = None) -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = str(data.get("tool_name") or data.get("name") or "")
    tool_input = data.get("tool_input") or data.get("args") or {}
    ws = data.get("workspace")
    hit = check_tool_call(tool, tool_input if isinstance(tool_input, dict) else {}, workspace=Path(ws) if ws else None)
    if hit is not None:
        print(f"Blocked by Flywheel policy [{hit['rule']}]: {hit['reason']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
