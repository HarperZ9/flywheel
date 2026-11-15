"""mcp_request.py -- argument checking and the request binding for relay's MCP runs.

Kept apart from local_mcp so the transport module stays within the size gate.
``request_binding`` is where the launch grants meet one call: it narrows write
and exec, confines the run's root to the launch root, and refuses a shell the
run was not granted, before any agent starts.
"""
from __future__ import annotations

import hashlib
import os

from .mcp_grants import SURFACE_EXEC_REFUSED, StartGrants, launch_root, narrow, run_root
from .mcp_paths import protected_paths


class MCPInputError(ValueError):
    """Typed user/request error returned as JSON instead of an opaque traceback."""

    def __init__(self, code: str, message: str, *, request_binding: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.request_binding = request_binding


def as_bool(args: dict, name: str) -> bool:
    val = args.get(name, False)
    if type(val) is bool:
        return val
    raise MCPInputError("INVALID_ARGUMENT", f"{name} must be a boolean")


def as_opt_bool(args: dict, name: str) -> bool | None:
    return as_bool(args, name) if name in args else None


def as_int(args: dict, name: str, default: int) -> int:
    val = args.get(name, default)
    if type(val) is not int:
        raise MCPInputError("INVALID_ARGUMENT", f"{name} must be an integer")
    if val < 0:
        raise MCPInputError("INVALID_ARGUMENT", f"{name} must be non-negative")
    return val


def as_str(args: dict, name: str, default: str = "", *, required: bool = False) -> str:
    if name not in args:
        if required:
            raise MCPInputError("INVALID_ARGUMENT", f"{name} is required")
        return default
    val = args[name]
    if type(val) is str:
        return val
    raise MCPInputError("INVALID_ARGUMENT", f"{name} must be a string")


def cli_tier_profiles() -> dict[str, str | None]:
    """{tier name: isolation profile} for the online tiers that start an agent CLI
    (codex exec, claude -p). Those CLIs carry their own tools, so a tier among them
    needs the exec grant, and one whose profile is unproven also needs the launch
    to name it in RELAY_ALLOW_EXEC_CLI."""
    from .endpoints import PROVIDERS
    return {f"{p}-{mode}": spec["cli"].get("profile") for p, spec in PROVIDERS.items()
            if spec.get("cli") for mode in ("plan", "max")}


def refuse_cli_tier(prefer: str, exec_ok: bool, binding: dict | None = None) -> None:
    from .child_env import EXEC_CLI_ENV, cli_allowed
    tiers = cli_tier_profiles()
    if prefer not in tiers:
        return
    if not exec_ok:
        raise MCPInputError("EXEC_NOT_GRANTED",
                            f"backend {prefer!r} starts an agentic CLI with its own shell, and "
                            "this call has no exec grant", request_binding=binding)
    if not cli_allowed(tiers[prefer]):
        raise MCPInputError("EXEC_NOT_GRANTED",
                            f"backend {prefer!r} starts a CLI whose isolation profile is not "
                            f"proven; the launch must name it in {EXEC_CLI_ENV}",
                            request_binding=binding)


def _shortfall(requested_write, requested_exec, write: bool, exec_: bool) -> list[str]:
    asked = (("write", requested_write, write), ("exec", requested_exec, exec_))
    return [name for name, want, got in asked if want is True and not got]


def request_binding(args: dict, grants: StartGrants) -> dict:
    goal = as_str(args, "goal", required=True)
    requested_root = as_str(args, "root") if "root" in args else None
    check = as_str(args, "check", "")
    test_cmd = as_str(args, "test_cmd", "")
    requested_write = as_opt_bool(args, "allow_write")
    requested_exec = as_opt_bool(args, "allow_exec")
    write, exec_ = narrow(grants, requested_write, requested_exec)
    root, inside = run_root(grants, requested_root)
    binding = {
        "schema": "relay.mcp-run-request/v2",
        "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "root": root,
        "requested_root": requested_root,
        "granted_root": launch_root(grants),
        "backend": as_str(args, "backend", "auto") or "auto",
        "model": as_str(args, "model", ""),
        "allow_write": write,
        "allow_exec": exec_,
        "requested_allow_write": requested_write,
        "requested_allow_exec": requested_exec,
        "granted_allow_write": grants.allow_write,
        "granted_allow_exec": grants.allow_exec,
        "remote_exec_refused": SURFACE_EXEC_REFUSED.get(),
        "grant_shortfall": _shortfall(requested_write, requested_exec, write, exec_),
        "online": as_bool(args, "online"),
        "max_steps": as_int(args, "max_steps", 6),
        "max_tokens": as_int(args, "max_tokens", 512),
        "compact_budget": as_int(args, "compact_budget", 0),
        "check_present": bool(check),
        "test_cmd_present": bool(test_cmd),
        # the server's own files the run's file tools refuse (see mcp_paths)
        "protected": protected_paths(os.environ).as_dict(),
    }
    if check:
        binding["check_sha256"] = hashlib.sha256(check.encode("utf-8")).hexdigest()
    if test_cmd:
        binding["test_cmd_sha256"] = hashlib.sha256(test_cmd.encode("utf-8")).hexdigest()
    if not inside:
        raise MCPInputError("ROOT_NOT_GRANTED",
                            "root resolves outside the root this server was launched with "
                            "(set --root or RELAY_MCP_ROOT at launch to widen it)",
                            request_binding=binding)
    if check and not exec_:
        # check runs through a shell outside the tool gate. Over MCP the caller is
        # not the operator, so without this run's exec it would be an exec bypass.
        raise MCPInputError("EXEC_NOT_GRANTED",
                            "check runs a shell command and this run has no exec grant "
                            "(start the server with --allow-exec or RELAY_ALLOW_EXEC=1)",
                            request_binding=binding)
    return binding


def observed_route(r: dict) -> dict:
    ledger = r.get("ledger")
    for entry in reversed(getattr(ledger, "entries", [])):
        if getattr(entry, "kind", None) != "assistant":
            continue
        meta = getattr(entry, "meta", {}) or {}
        receipt = meta.get("receipt") if isinstance(meta, dict) else {}
        if not isinstance(receipt, dict):
            receipt = {}
        return {"backend": meta.get("backend"), "model_ref": receipt.get("model_ref"),
                "receipt_id": receipt.get("receipt_id"),
                "source": "last_witnessed_assistant", "seq": getattr(entry, "seq", None)}
    return {"backend": None, "model_ref": None, "receipt_id": None,
            "source": "no_witnessed_assistant", "seq": None}


def run_projection(r: dict, binding: dict | None = None) -> dict:
    # verified is the honest composite (chain + re-derivable receipts + a real final
    # answer), never the self-confirming in-memory chain check alone.
    out = {"final": r["final"], "steps": r["steps"], "verified": r["verified"],
           "final_answer": r["final_answer"], "chain_ok": r["chain_ok"],
           "checkpoint": r["checkpoint"], "accepted": r.get("accepted"),
           "check_passed": r.get("check_passed"), "observed_route": observed_route(r),
           # the intent/scope audit (claimed_history + any declared drift/scope).
           "intent_audit": r.get("intent_audit", {"findings": [], "critical": 0, "warnings": 0})}
    if "note" in r:
        out["note"] = r["note"]
    if binding is not None:
        out["request_binding"] = binding
    return out
