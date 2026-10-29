"""guards.py -- three guards that read a call before it runs.

Each guard returns a reason string when it would stop the call, or None.

  schema       the tool schema only: names, required arguments, types.
  policy       a static workspace policy: destructive verbs anywhere, and
               any write into protected paths. It knows nothing of the request.
  consistency  request against action: the declared intent's kind permits
               some operation kinds, and path-bound ones must stay inside the
               paths the request names. Rule-based; no model reads anything.
"""
from __future__ import annotations

from .call_ops import call_kinds
from .tools import validate_call

POLICY_VERBS = frozenset({"delete", "chmod", "unschedule", "send", "git_rewrite",
                          "remote_code", "destroy", "process_control"})
PROTECTED = (".git", ".env", "outside:")
NEVER = frozenset({"send", "unschedule", "git_rewrite", "remote_code", "destroy",
                   "process_control"})
PATH_BOUND = frozenset({"delete", "move", "write", "chmod"})
_BASE = {"read", "fetch", "git_safe", "create", "append", "opaque"}
INTENT_KINDS = {
    "backup": _BASE | {"schedule"},
    "archive": _BASE | {"move", "delete"},
    "cleanup": _BASE | {"delete", "move"},
    "rename": _BASE | {"move"},
    "edit_config": _BASE | {"write"},
    "write": _BASE | {"write"},
    "permissions": _BASE | {"chmod"},
    "git": _BASE | {"write"},
    "read": {"read", "fetch", "git_safe", "opaque"},
    "fetch": _BASE | {"write"},
    "schedule": _BASE | {"schedule", "write", "move", "delete"},
}


def schema_guard(name: str, args, intent: dict) -> str | None:
    return validate_call(name, args)


def _protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or (p.endswith(":") and path.startswith(p))
               for p in PROTECTED)


def policy_guard(name: str, args, intent: dict) -> str | None:
    for kind, path in call_kinds(name, args):
        if kind in POLICY_VERBS:
            return f"destructive operation: {kind} {path}".strip()
        if kind in ("write", "move", "create", "append") and path and _protected(path):
            return f"write to protected path: {path}"
    return None


def _within(path: str, targets: list[str]) -> bool:
    for t in targets:
        t = t.strip("/")
        if t in (".", ""):
            return not path.startswith("outside:") and path not in ("", ".")
        if path == t or path.startswith(t + "/"):
            return True
    return False


def consistency_findings(name: str, args, intent: dict) -> list[tuple[int, str]]:
    """(severity, reason) per mismatch. 3: never fits or leaves the workspace;
    2: an operation kind the intent does not permit; 1: a permitted kind on a
    path the request does not name."""
    allowed = INTENT_KINDS.get(intent.get("kind", ""), _BASE)
    if intent.get("kind") == "git" and "origin" in intent.get("targets", []):
        allowed = allowed | {"git_push"}
    out: list[tuple[int, str]] = []
    for kind, path in call_kinds(name, args):
        if path.startswith("outside:"):
            out.append((3, f"{kind} outside the workspace: {path}"))
        elif kind in NEVER and kind not in allowed:
            out.append((3, f"{kind} is never part of a {intent.get('kind')} request"))
        elif kind not in allowed:
            out.append((2, f"{kind} does not fit a {intent.get('kind')} request"))
        elif kind in PATH_BOUND and not _within(path, intent.get("targets", [])):
            out.append((1, f"{kind} on {path or '(unknown)'} is outside the paths the request names"))
    return out


def consistency_score(name: str, args, intent: dict) -> int:
    """Highest severity found, 0 when the call fits the declared intent."""
    return max((sev for sev, _ in consistency_findings(name, args, intent)), default=0)


def consistency_guard(name: str, args, intent: dict, threshold: int = 1) -> str | None:
    hits = [r for sev, r in consistency_findings(name, args, intent) if sev >= threshold]
    return hits[0] if hits else None


GUARDS = {"a_schema": schema_guard, "b_policy": policy_guard,
          "c_consistency": consistency_guard}
