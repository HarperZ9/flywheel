"""Policy, observation, and reseating-valve authority gate for model-as-operator control."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

VALID_VERBS = ("read_file", "write_file", "run_command", "mcp_call", "ui_action")
MUTATING_VERBS = frozenset(("write_file", "run_command", "mcp_call", "ui_action"))
GateDecision = Literal["ALLOW", "DENY", "NEEDS_HUMAN"]

_DESTRUCTIVE_CMD_RE = re.compile(
    r"(?i)\b(rm\s+-rf|del\s+/f|format\b|mkfs\b|dd\s+if=|shutdown\b|reboot\b|reg\s+delete|remove-item\s+-recurse)\b"
)
_BYPASS_RE = re.compile(
    r"(?i)\b(bypass[_\s-]?(auth|captcha|permission|sandbox)|solve[_\s-]?captcha|turnstile|recaptcha|hcaptcha)\b"
)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return {"__bytes_b64__": base64.b64encode(obj).decode("ascii")}
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def canonical_bytes(obj: object) -> bytes:
    """Serialize any JSON-compatible value to deterministic canonical UTF-8 bytes."""
    return json.dumps(_json_safe(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_prefixed(data: bytes) -> str:
    """Return a sha256:<hex> digest string for raw bytes."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalize_virtual_path(raw: str) -> str:
    """Normalize a path string with POSIX separators and collapsed segments."""
    cleaned = raw.replace("\\", "/").strip()
    if not cleaned:
        return ""
    parts: list[str] = []
    prefix = ""
    if len(cleaned) >= 2 and cleaned[1] == ":":
        prefix = cleaned[:2].lower()
        cleaned = cleaned[2:]
    elif cleaned.startswith("/"):
        prefix = "/"
    for seg in cleaned.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append("..")
        else:
            parts.append(seg)
    joined = "/".join(parts)
    if prefix == "/":
        return "/" + joined
    if prefix:
        return f"{prefix}/{joined}" if joined else f"{prefix}/"
    return joined


def _fold_case(norm_posix: str) -> str:
    return norm_posix.lower() if os.name == "nt" else norm_posix


def path_within_roots(target: str, roots: tuple[str, ...]) -> bool:
    """Return True if target lies inside at least one normalized allowed root."""
    if not target or not roots:
        return False
    norm_target = normalize_virtual_path(target)
    if norm_target == ".." or norm_target.startswith("../") or "/../" in norm_target:
        return False
    t_case = _fold_case(norm_target)
    for root in roots:
        norm_root = normalize_virtual_path(root).rstrip("/")
        if not norm_root:
            continue
        r_case = _fold_case(norm_root)
        if t_case == r_case or t_case.startswith(r_case + "/"):
            return True
    return False


def _hits_protected(target: str, protected: tuple[str, ...]) -> bool:
    if not target or not protected:
        return False
    norm_t = _fold_case(normalize_virtual_path(target).rstrip("/"))
    for raw in protected:
        norm_p = _fold_case(normalize_virtual_path(raw).rstrip("/"))
        if norm_p and (norm_t == norm_p or norm_t.startswith(norm_p + "/")):
            return True
    return False


@dataclass(frozen=True)
class WorkstationObservation:
    """Deterministic snapshot of workstation state relevant to an operator step."""

    cwd: str
    processes: tuple[dict[str, Any], ...]
    file_digests: dict[str, str]
    active_surface: dict[str, Any]
    obs_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cwd": self.cwd, "processes": list(self.processes),
            "file_digests": dict(sorted(self.file_digests.items())),
            "active_surface": dict(self.active_surface), "obs_sha256": self.obs_sha256,
        }


def build_observation(
    *, cwd: str, processes: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    file_digests: dict[str, str] | None = None, active_surface: dict[str, Any] | None = None,
) -> WorkstationObservation:
    """Construct a WorkstationObservation with a deterministic obs_sha256 digest."""
    norm_cwd = normalize_virtual_path(cwd)
    sorted_procs = tuple(sorted((dict(p) for p in processes), key=lambda p: (str(p.get("name", "")), int(p.get("pid", 0)))))
    sorted_files = dict(sorted((normalize_virtual_path(k), str(v)) for k, v in (file_digests or {}).items()))
    surface = dict(active_surface or {})
    payload = {"cwd": norm_cwd, "processes": list(sorted_procs), "file_digests": sorted_files, "active_surface": surface}
    return WorkstationObservation(
        cwd=norm_cwd, processes=sorted_procs, file_digests=sorted_files,
        active_surface=surface, obs_sha256=sha256_prefixed(canonical_bytes(payload)),
    )


@dataclass(frozen=True)
class OperatorAction:
    """Structured single-step workstation action proposed by an operator model."""

    verb: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    destructive: bool = False
    expected_post: dict[str, Any] | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verb": self.verb, "target": self.target, "params": _json_safe(self.params),
            "destructive": self.destructive,
            "expected_post": _json_safe(self.expected_post) if self.expected_post is not None else None,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class AuthorityGrant:
    """Explicit scoped permission grant governing an OperatorSession."""

    allowed_roots: tuple[str, ...]
    allowed_verbs: tuple[str, ...] = VALID_VERBS
    max_steps: int = 32
    max_mutations: int = 16
    require_human_for_destructive: bool = True
    allowed_commands: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()

    def normalized_roots(self) -> tuple[str, ...]:
        return tuple(normalize_virtual_path(str(Path(r))) if os.path.isabs(r) else normalize_virtual_path(r) for r in self.allowed_roots)


@dataclass(frozen=True)
class GateVerdict:
    """Decision returned by AuthorityGate before any actuation occurs."""

    decision: GateDecision
    reason: str
    valve_tripped: bool = False
    mutates: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"decision": self.decision, "reason": self.reason, "valve_tripped": self.valve_tripped, "mutates": self.mutates}


def _looks_like_bypass(action: OperatorAction) -> bool:
    blob = f"{action.target} {action.rationale} {canonical_bytes(action.params).decode('utf-8')}"
    return bool(_BYPASS_RE.search(blob))


def _looks_destructive(action: OperatorAction) -> bool:
    if action.destructive:
        return True
    if action.verb == "run_command":
        cmd = " ".join(str(x) for x in action.params.get("argv", [])) or str(action.params.get("command", ""))
        return bool(_DESTRUCTIVE_CMD_RE.search(cmd))
    if action.verb in ("mcp_call", "ui_action"):
        op = str(action.params.get("operation", action.params.get("action", ""))).lower()
        return any(tok in op for tok in ("delete", "drop", "wipe", "purge", "terminate", "uninstall"))
    return False


class AuthorityGate:
    """Fail-closed authority gate with an automatic reseating-valve budget stop."""

    def __init__(self, grant: AuthorityGrant) -> None:
        self.grant = grant
        self._roots = grant.normalized_roots()
        self.steps_used = 0
        self.mutations_used = 0
        self.valve_tripped = False
        self.reseat_count = 0

    def evaluate(self, action: OperatorAction, *, human_approval_id: str | None = None) -> GateVerdict:
        """Evaluate an OperatorAction and return ALLOW, DENY, or NEEDS_HUMAN."""
        mutates = action.verb in MUTATING_VERBS
        if self.valve_tripped:
            return GateVerdict("DENY", "reseating valve tripped: human reseat required", True, mutates)
        if self.steps_used >= self.grant.max_steps:
            self.valve_tripped = True
            return GateVerdict("DENY", f"step budget exhausted ({self.steps_used}/{self.grant.max_steps})", True, mutates)
        if mutates and self.mutations_used >= self.grant.max_mutations:
            self.valve_tripped = True
            return GateVerdict("DENY", f"mutation budget exhausted ({self.mutations_used}/{self.grant.max_mutations})", True, mutates)
        if action.verb not in VALID_VERBS or action.verb not in self.grant.allowed_verbs:
            return GateVerdict("DENY", f"verb not authorized: {action.verb}", False, mutates)
        if _looks_like_bypass(action):
            return GateVerdict("DENY", "security boundary bypass or anti-bot circumvention is forbidden", False, mutates)
        scope_err = self._check_scope(action)
        if scope_err is not None:
            return GateVerdict("DENY", scope_err, False, mutates)
        if _looks_destructive(action) and self.grant.require_human_for_destructive and not human_approval_id:
            return GateVerdict("NEEDS_HUMAN", "destructive action requires explicit human approval", False, mutates)
        return GateVerdict("ALLOW", "authorized within grant scope and budget", False, mutates)

    def _check_scope(self, action: OperatorAction) -> str | None:
        if action.verb in ("read_file", "write_file"):
            if not path_within_roots(action.target, self._roots):
                return f"path outside allowed_roots: {action.target}"
            if action.verb == "write_file" and _hits_protected(action.target, self.grant.protected_paths):
                return f"target hits protected authority path: {action.target}"
        elif action.verb == "run_command":
            if action.target and not path_within_roots(action.target, self._roots):
                return f"command cwd outside allowed_roots: {action.target}"
            argv = list(action.params.get("argv", []))
            if self.grant.allowed_commands and (not argv or str(argv[0]) not in self.grant.allowed_commands):
                return f"command executable not in allowed_commands: {argv[0] if argv else ''}"
        return None

    def record_execution(self, action: OperatorAction) -> None:
        """Advance step and mutation counters after an ALLOW decision executes."""
        self.steps_used += 1
        if action.verb in MUTATING_VERBS:
            self.mutations_used += 1

    def reseat(self, *, extra_steps: int = 0, extra_mutations: int = 0) -> None:
        """Reseat the budget valve explicitly and optionally extend grant ceilings."""
        self.valve_tripped = False
        self.reseat_count += 1
        if extra_steps > 0 or extra_mutations > 0:
            self.grant = AuthorityGrant(
                allowed_roots=self.grant.allowed_roots,
                allowed_verbs=self.grant.allowed_verbs,
                max_steps=self.grant.max_steps + extra_steps,
                max_mutations=self.grant.max_mutations + extra_mutations,
                require_human_for_destructive=self.grant.require_human_for_destructive,
                allowed_commands=self.grant.allowed_commands,
                protected_paths=self.grant.protected_paths,
            )
