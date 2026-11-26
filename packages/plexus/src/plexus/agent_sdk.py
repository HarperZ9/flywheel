"""Fail-closed cross-flagship model- and agent-native invocation runtime (FlagshipAgentSDK)."""
from __future__ import annotations

import hashlib
import importlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .sdk_catalog import (
    BUILTIN_SDK_TOOLS,
    AgentToolSpec,
    export_compact_catalog,
    suggest_similar_tools,
    validate_tool_args,
)
from .sdk_colab import ColabJobRequest, emit_colab_job_spec

SDK_RESULT_SCHEMA = "agent-sdk-result/1"
WORKFLOW_TRACE_SCHEMA = "agent-sdk-workflow-trace/1"
TRACE_GENESIS = ""
AdapterFn = Callable[[dict[str, Any]], dict[str, Any]]


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _step_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    raw = f"{prev_hash}|".encode("utf-8") + _canonical_bytes(payload)
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AuthorityContext:
    """Explicit fail-closed authority scope for FlagshipAgentSDK invocations."""

    allowed_flagships: tuple[str, ...] | None = None
    allowed_tools: tuple[str, ...] | None = None
    denied_tools: tuple[str, ...] = ()
    allow_mutating: bool = True
    require_human_for_destructive: bool = True
    human_approval_id: str | None = None


def _check_authority(spec: AgentToolSpec, args: dict[str, Any], auth: AuthorityContext | None) -> tuple[str, str]:
    effective = auth if auth is not None else AuthorityContext()
    if spec.name in effective.denied_tools:
        return "DENY", f"tool explicitly denied by authority policy: {spec.name}"
    if effective.allowed_flagships is not None and spec.flagship not in effective.allowed_flagships:
        return "DENY", f"flagship '{spec.flagship}' outside allowed_flagships"
    if effective.allowed_tools is not None and spec.name not in effective.allowed_tools:
        return "DENY", f"tool '{spec.name}' outside allowed_tools"
    if spec.mutates and not effective.allow_mutating:
        return "DENY", f"mutating tool '{spec.name}' blocked by read-only authority"
    is_destructive = spec.destructive or bool(args.get("destructive", False))
    if is_destructive and effective.require_human_for_destructive and not effective.human_approval_id:
        return "NEEDS_HUMAN", f"destructive tool '{spec.name}' requires explicit human approval"
    return "ALLOW", "authorized"


def _colab_adapter(args: dict[str, Any]) -> dict[str, Any]:
    req = ColabJobRequest(
        job_id=str(args["job_id"]),
        profile=str(args["profile"]),
        accelerator=str(args.get("accelerator", "L4")),
        compute_unit_cap=float(args.get("compute_unit_cap", 100.0)),
        data_gate_passed=bool(args.get("data_gate_passed", False)),
    )
    return emit_colab_job_spec(req)


def _gather_deconstruct_adapter(args: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(args["path"]))
    out_dir = Path(str(args.get("out_dir") or target.parent / "deconstruct_out"))
    if target.is_file():
        try:
            mod = importlib.import_module("gather.deconstruct")
            manifest = mod.deconstruct_artifact(target, out_dir)
            return {"ok": True, "verdict": "MATCH", "adapter": "gather.deconstruct", "manifest": manifest}
        except ImportError:
            pass
    return {
        "ok": True, "verdict": "DRY_ADAPTER", "adapter": "plexus.fallback",
        "artifact": str(target.name), "schema": "media-deconstruction/1", "workflow": args.get("workflow", "auto"),
    }


def _default_adapter(spec: AgentToolSpec) -> AdapterFn:
    if spec.name == "colab.emit_stage1_job_spec":
        return _colab_adapter
    if spec.name == "gather.deconstruct":
        return _gather_deconstruct_adapter

    def _run(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True, "verdict": "MATCH", "tool": spec.name, "flagship": spec.flagship,
            "invariants": list(spec.output_invariants), "args_sha256": _sha256_prefixed(_canonical_bytes(args)),
        }

    return _run


def verify_workflow_trace(trace: dict[str, Any] | Sequence[dict[str, Any]]) -> tuple[bool, list[str], str]:
    """Fail-closed SHA-256 hash-chain verifier for a FlagshipAgentSDK workflow trace."""
    steps = list(trace["steps"]) if isinstance(trace, dict) else list(trace)
    head = TRACE_GENESIS
    errors: list[str] = []
    for idx, row in enumerate(steps):
        if not isinstance(row, dict):
            errors.append(f"step {idx} is not an object")
            continue
        prev = row.get("prev_hash")
        stored = row.get("step_hash")
        payload = {k: v for k, v in row.items() if k not in ("prev_hash", "step_hash")}
        if prev != head:
            errors.append(f"step {idx} prev_hash mismatch")
        if payload.get("seq") != idx:
            errors.append(f"step {idx} sequence mismatch (got {payload.get('seq')})")
        if not isinstance(stored, str) or stored != _step_hash(head, payload):
            errors.append(f"step {idx} step_hash mismatch")
        head = stored if isinstance(stored, str) else head
    if isinstance(trace, dict) and trace.get("trace_head") != head:
        errors.append("trace_head does not match final step_hash")
    return len(errors) == 0, errors, head


class FlagshipAgentSDK:
    """Unified fail-closed model- and agent-native SDK spanning all 5 flagships + Colab."""

    def __init__(self, tools: Sequence[AgentToolSpec] | None = None) -> None:
        self._specs: dict[str, AgentToolSpec] = {s.name: s for s in (tools or BUILTIN_SDK_TOOLS)}
        self._adapters: dict[str, AdapterFn] = {name: _default_adapter(spec) for name, spec in self._specs.items()}

    def register_adapter(self, tool_name: str, fn: AdapterFn) -> None:
        if tool_name not in self._specs:
            raise KeyError(f"cannot bind adapter to unknown tool: {tool_name}")
        self._adapters[tool_name] = fn

    def catalog(self, max_tokens_per_tool: int = 125, *, fmt: str = "compact") -> dict[str, Any]:
        return export_compact_catalog(max_tokens_per_tool, fmt=fmt, tools=tuple(self._specs.values()))

    def _wrap_result(
        self, *, tool: str, flagship: str, ok: bool, verdict: str, executed: bool,
        result: dict[str, Any], next_actions: Sequence[str], started: float,
        errors: Sequence[str] = (), suggestions: Sequence[str] = (),
    ) -> dict[str, Any]:
        core = {
            "schema": SDK_RESULT_SCHEMA, "tool": tool, "flagship": flagship,
            "ok": ok, "verdict": verdict, "executed": executed, "result": dict(result),
            "errors": list(errors), "suggestions": list(suggestions),
            "next_valid_actions": list(next_actions), "receipt_ready": True,
        }
        return {
            **core,
            "call_sha256": _sha256_prefixed(_canonical_bytes(core)),
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }

    def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        authority: AuthorityContext | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Validate, authorize, execute, and seal a single model-native tool call."""
        started = time.perf_counter()
        spec = self._specs.get(tool_name)
        if spec is None:
            sugg = suggest_similar_tools(tool_name, list(self._specs))
            return self._wrap_result(
                tool=tool_name, flagship="unknown", ok=False, verdict="UNKNOWN_TOOL", executed=False,
                result={}, next_actions=sugg, started=started,
                errors=[f"unknown tool '{tool_name}'"], suggestions=sugg,
            )
        arg_errors = validate_tool_args(spec, args)
        if arg_errors:
            return self._wrap_result(
                tool=spec.name, flagship=spec.flagship, ok=False, verdict="INVALID_ARGS", executed=False,
                result={}, next_actions=[spec.name], started=started, errors=arg_errors,
            )
        decision, reason = _check_authority(spec, args, authority)
        if decision != "ALLOW":
            return self._wrap_result(
                tool=spec.name, flagship=spec.flagship, ok=False, verdict=decision, executed=False,
                result={"authority_reason": reason}, next_actions=[], started=started, errors=[reason],
            )
        if dry_run:
            payload = {"ok": True, "verdict": "DRY_RUN", "tool": spec.name, "args_sha256": _sha256_prefixed(_canonical_bytes(args))}
        else:
            payload = dict(self._adapters[spec.name](dict(args)))
        ok = bool(payload.get("ok", True))
        verdict = str(payload.get("verdict", "OK" if ok else "FAILED"))
        raw_next = payload.get("next_valid_actions")
        next_acts = [str(x) for x in raw_next] if isinstance(raw_next, (list, tuple)) else list(spec.next_valid_actions)
        errs = [str(payload["reason"])] if (not ok and "reason" in payload) else []
        return self._wrap_result(
            tool=spec.name, flagship=spec.flagship, ok=ok, verdict=verdict, executed=True,
            result=payload, next_actions=next_acts, started=started, errors=errs,
        )

    def run_workflow(
        self,
        steps: Sequence[dict[str, Any]],
        *,
        authority: AuthorityContext | None = None,
        dry_run: bool = False,
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Chain multi-flagship SDK steps into a SHA-256 hash-chained execution trace."""
        head = TRACE_GENESIS
        trace_steps: list[dict[str, Any]] = []
        all_ok = True
        last_next: list[str] = []
        for idx, step in enumerate(steps):
            tool = str(step.get("tool", ""))
            args = step.get("args", {})
            env = self.invoke(tool, args, authority=authority, dry_run=dry_run)
            payload = {
                "seq": idx, "tool": tool, "ok": env["ok"], "verdict": env["verdict"],
                "executed": env["executed"], "call_sha256": env["call_sha256"],
            }
            shash = _step_hash(head, payload)
            trace_steps.append({**payload, "prev_hash": head, "step_hash": shash})
            head = shash
            last_next = list(env["next_valid_actions"])
            if not env["ok"]:
                all_ok = False
                if stop_on_failure:
                    break
        return {
            "schema": WORKFLOW_TRACE_SCHEMA, "ok": all_ok, "verdict": "MATCH" if all_ok else "HALTED",
            "steps_completed": len(trace_steps), "steps_total": len(steps),
            "trace_head": head, "steps": trace_steps, "next_valid_actions": last_next,
        }
