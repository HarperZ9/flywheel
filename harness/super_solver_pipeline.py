"""Unified Flywheel + Rowan Super Solver end-to-end verification pipeline.

Composes four verified harness subsystems with zero duplication:
1. Rowan unified provider router (local/subscription/api + AVTR-4R budget valve)
2. TracePress/LOTUS streaming trace compression + injection guard + 2-stage sanitizer
3. Deterministic AST f64_oracle + Three-Plate Plate B + stale-cache replay guard
4. Chained canonical sealing (flywheel.rowan-route-receipt/v1 + engine-receipt/1)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .evidence_json import canonical_bytes
from .gateway_secret_boundary import validate_no_raw_secrets
from .rowan_provider_router import EndpointProfile, RoutePolicy, RouteRequest, plan_rowan_route, verify_route_receipt
from .three_plate_oracle import run_plate_b
from .trace_layers import TraceLayerStream, TraceStep
from .verifier_sanitizer import TaskRolloutRecord, sanitize_verifier_and_tasks, verify_sanitizer_receipt

PIPELINE_SCHEMA = "flywheel.super-solver-receipt/v1"
ENGINE_RECEIPT_SCHEMA = "engine-receipt/1"
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions"),
    re.compile(r"(?i)override\s+system\s+prompt"),
    re.compile(r"(?i)(?:force|mark|set)\s+verdict\s*(?:=|to|as)\s*(?:match|pass)"),
    re.compile(r"(?i)bypass\s+(?:the\s+)?oracle"),
    re.compile(r"(?is)<\s*system\s*>.*?<\s*/\s*system\s*>"),
    re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069]"),
)
_SAFE_BIN: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_SAFE_UN: dict[type, Callable[[float], float]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_SAFE_FN: dict[str, Callable[..., float]] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
    "exp": math.exp, "log": math.log, "abs": abs, "pow": math.pow,
}
_SAFE_CONST: dict[str, float] = {"pi": math.pi, "e": math.e, "g0": 9.80665}


@dataclass(frozen=True)
class SuperSolverTask:
    task_id: str
    route_request: RouteRequest
    endpoints: tuple[EndpointProfile, ...]
    trace_steps: tuple[TraceStep, ...]
    candidate_output: str
    policy: RoutePolicy = RoutePolicy()
    rollouts: tuple[TaskRolloutRecord, ...] = (
        TaskRolloutRecord("calibration_a", (True, False, True, False)),
    )
    max_budget_usd: float = 0.50
    max_est_tokens: int = 520
    numeric_expr: str = ""
    claimed_numeric: float | None = None
    numeric_rel_tol: float = 1e-6
    cache_context_sha256: str = ""
    cache_age_seconds: int = 0
    max_cache_age_seconds: int = 900


def _eval_f64_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_f64_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in _SAFE_CONST:
        return _SAFE_CONST[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UN:
        return _SAFE_UN[type(node.op)](_eval_f64_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BIN:
        return _SAFE_BIN[type(node.op)](_eval_f64_node(node.left), _eval_f64_node(node.right))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SAFE_FN and not node.keywords:
        return float(_SAFE_FN[node.func.id](*[_eval_f64_node(a) for a in node.args]))
    raise ValueError(f"disallowed f64 AST node: {type(node).__name__}")


def eval_f64_oracle(expr: str) -> float:
    """Evaluate a pure IEEE-754 expression via strict AST whitelist."""
    val = _eval_f64_node(ast.parse(expr.strip(), mode="eval"))
    if not math.isfinite(val):
        raise ValueError("non-finite f64_oracle result")
    return val


def sanitize_trace_text(text: str) -> tuple[str, list[str]]:
    """Strip adversarial prompt-injection payloads before any verifier reads text."""
    hits: list[str] = []
    cleaned = text
    for idx, pat in enumerate(_INJECTION_PATTERNS):
        if pat.search(cleaned):
            hits.append(f"injection_pat_{idx}")
            cleaned = pat.sub("[REDACTED_INJECTION]", cleaned)
    return cleaned, hits


def _verify_numeric_stage(task: SuperSolverTask) -> tuple[dict[str, Any], list[str]]:
    faults: list[str] = []
    if task.claimed_numeric is None and not task.numeric_expr.strip():
        return {"checked": False, "ok": True}, faults
    if task.claimed_numeric is None or not task.numeric_expr.strip():
        faults.append("unverified_numeric_claim")
        return {"checked": True, "ok": False, "reason": "missing_expr_or_claim"}, faults
    try:
        exact = eval_f64_oracle(task.numeric_expr)
    except Exception:
        faults.append("unverified_numeric_claim")
        return {"checked": True, "ok": False, "reason": "invalid_f64_expr"}, faults
    ok = math.isclose(float(task.claimed_numeric), exact, rel_tol=task.numeric_rel_tol, abs_tol=1e-9)
    if not ok:
        faults.append("unverified_numeric_claim")
    return {"checked": True, "ok": ok, "exact": exact, "claimed": float(task.claimed_numeric)}, faults


def _check_cache_freshness(task: SuperSolverTask, expected_ctx_sha: str) -> tuple[dict[str, Any], list[str]]:
    if not task.cache_context_sha256:
        return {"replayed": False, "fresh": True}, []
    fresh = (
        task.cache_context_sha256 == expected_ctx_sha
        and 0 <= task.cache_age_seconds <= task.max_cache_age_seconds
    )
    faults = [] if fresh else ["stale_cache_replay"]
    return {
        "replayed": True, "fresh": fresh,
        "cache_age_seconds": task.cache_age_seconds,
        "max_cache_age_seconds": task.max_cache_age_seconds,
    }, faults


def _build_engine_receipt(task_id: str, verdict: str, claim_body: dict[str, Any]) -> dict[str, Any]:
    claim_sha = "sha256:" + hashlib.sha256(canonical_bytes(claim_body)).hexdigest()
    env = {
        "schema": ENGINE_RECEIPT_SCHEMA, "engine": "flywheel-super-solver",
        "flagship": "flywheel", "task_id": task_id, "verdict": verdict, "claim_sha256": claim_sha,
    }
    env["envelope_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(env)).hexdigest()
    return env


def _run_trace_and_sanitizer(
    task: SuperSolverTask, grade_fn: Callable[[str], bool],
) -> tuple[dict[str, Any], dict[str, Any], str, list[str]]:
    faults: list[str] = []
    stream = TraceLayerStream(cost_budget_usd=task.max_budget_usd)
    inj_hits: list[str] = []
    for step in task.trace_steps:
        clean_sum, hits = sanitize_trace_text(step.summary)
        inj_hits.extend(hits)
        stream.append(TraceStep(
            step.trace_id, step.step_idx, step.role, step.tokens_in, step.tokens_out,
            step.latency_ms, step.chars_out, step.oracle_verdict, step.self_score, clean_sum, step.cost_usd,
        ))
    clean_out, out_hits = sanitize_trace_text(task.candidate_output)
    if inj_hits or out_hits:
        faults.append("prompt_injection_in_trace")
    trace_summary = stream.reduce_summary()
    if trace_summary["total_cost_usd"] > task.max_budget_usd:
        faults.append("budget_cap_breach")
    sanitizer = sanitize_verifier_and_tasks(f"super-solver:{task.task_id}", grade_fn, task.rollouts)
    if sanitizer["verdict"] != "MATCH":
        faults.append("leaky_verifier_or_zero_variance")
    return trace_summary, sanitizer, clean_out, faults


def _assemble_receipt(
    task: SuperSolverTask, verdict: str, faults: list[str], route_rcpt: dict[str, Any],
    trace_summary: dict[str, Any], san_rcpt: dict[str, Any], oracle_payload: dict[str, Any],
) -> dict[str, Any]:
    oracle_sha = "sha256:" + hashlib.sha256(canonical_bytes(oracle_payload)).hexdigest()
    claim_body = {
        "task_id": task.task_id, "route_receipt_sha256": route_rcpt["receipt_sha256"],
        "trace_layer_sha256": trace_summary["layer_sha256"],
        "sanitizer_receipt_sha256": san_rcpt["receipt_sha256"],
        "oracle_sha256": oracle_sha, "faults": faults,
    }
    body: dict[str, Any] = {
        "schema": PIPELINE_SCHEMA, "task_id": task.task_id, "verdict": verdict, "faults": faults,
        "route_receipt": route_rcpt, "trace_layer": trace_summary, "sanitizer_receipt": san_rcpt,
        "oracle": oracle_payload, "oracle_sha256": oracle_sha,
        "engine_receipt": _build_engine_receipt(task.task_id, verdict, claim_body),
    }
    body["receipt_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def run_super_solver(task: SuperSolverTask, *, grade_fn: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """Execute all 4 Super Solver stages fail-closed and return a chained receipt."""
    faults: list[str] = []
    route_rcpt = plan_rowan_route(task.route_request, task.endpoints, task.policy)
    if route_rcpt["avtr"]["est_tokens"] > task.max_est_tokens:
        faults.append("budget_cap_breach")
    if route_rcpt["route_status"] != "planned":
        faults.append("provider_outage_no_route")

    def _default_grade(out: str) -> bool:
        return bool(out.strip()) and out.strip() == task.candidate_output.strip() and "PASS" not in out

    trace_summary, san_rcpt, clean_out, s2_faults = _run_trace_and_sanitizer(task, grade_fn or _default_grade)
    faults.extend(s2_faults)
    expected_ctx_sha = "sha256:" + hashlib.sha256(
        canonical_bytes({"task_id": task.task_id, "route_sha": route_rcpt["receipt_sha256"]}),
    ).hexdigest()
    cache_check, cache_faults = _check_cache_freshness(task, expected_ctx_sha)
    num_check, num_faults = _verify_numeric_stage(task)
    plate_b = run_plate_b({"claim_or_code": clean_out})
    faults.extend(cache_faults + num_faults + ([] if plate_b.passed else plate_b.defects))
    dedup_faults = sorted(set(faults))
    verdict = "MATCH" if not dedup_faults else ("UNVERIFIABLE" if dedup_faults == ["provider_outage_no_route"] else "DRIFT")
    oracle_payload = {
        "numeric": num_check, "cache": cache_check, "plate_b_pass": plate_b.passed,
        "plate_b_defects": plate_b.defects,
        "failover_used": bool(route_rcpt["skipped_endpoints"] and route_rcpt["selected"]),
    }
    return _assemble_receipt(task, verdict, dedup_faults, route_rcpt, trace_summary, san_rcpt, oracle_payload)


def verify_super_solver_receipt(receipt: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Offline pure-stdlib verifier checking every link in the receipt chain."""
    errors: list[str] = []
    if not isinstance(receipt, Mapping) or receipt.get("schema") != PIPELINE_SCHEMA:
        return False, ["invalid_schema"]
    try:
        validate_no_raw_secrets(dict(receipt))
    except Exception:
        errors.append("raw_secret_present")
    if not verify_route_receipt(receipt.get("route_receipt", {})):
        errors.append("forged_route_receipt")
    if not verify_sanitizer_receipt(receipt.get("sanitizer_receipt", {})):
        errors.append("forged_sanitizer_receipt")
    trace = receipt.get("trace_layer") or {}
    t_body = {k: v for k, v in trace.items() if k != "layer_sha256"}
    if trace.get("layer_sha256") != "sha256:" + hashlib.sha256(canonical_bytes(t_body)).hexdigest():
        errors.append("forged_trace_layer")
    oracle_sha = "sha256:" + hashlib.sha256(canonical_bytes(receipt.get("oracle", {}))).hexdigest()
    if receipt.get("oracle_sha256") != oracle_sha:
        errors.append("forged_oracle_payload")
    claim_body = {
        "task_id": receipt.get("task_id"),
        "route_receipt_sha256": (receipt.get("route_receipt") or {}).get("receipt_sha256"),
        "trace_layer_sha256": trace.get("layer_sha256"),
        "sanitizer_receipt_sha256": (receipt.get("sanitizer_receipt") or {}).get("receipt_sha256"),
        "oracle_sha256": oracle_sha,
        "faults": receipt.get("faults"),
    }
    expected_env = _build_engine_receipt(str(receipt.get("task_id", "")), str(receipt.get("verdict", "")), claim_body)
    if receipt.get("engine_receipt") != expected_env:
        errors.append("forged_engine_receipt")
    top_body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    if receipt.get("receipt_sha256") != "sha256:" + hashlib.sha256(canonical_bytes(top_body)).hexdigest():
        errors.append("forged_top_receipt")
    return (len(errors) == 0), errors


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for `flywheel super-solver`."""
    ap = argparse.ArgumentParser(prog="flywheel super-solver", description="Run or verify the Super Solver pipeline.")
    ap.add_argument("--bench", action="store_true", help="Run the 6-fault-class adversarial benchmark.")
    ap.add_argument("--verify", type=Path, help="Verify a saved super-solver receipt JSON offline.")
    ap.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.verify is not None:
        data = json.loads(args.verify.read_text(encoding="utf-8"))
        ok, errs = verify_super_solver_receipt(data)
        print(json.dumps({"ok": ok, "verdict": data.get("verdict"), "errors": errs}, indent=2))
        return 0 if (ok and data.get("verdict") == "MATCH") else 1
    from .super_solver_bench import run_adversarial_benchmark
    report = run_adversarial_benchmark()
    print(json.dumps(report, indent=2 if args.json else None, sort_keys=True))
    return 0 if report["all_passed"] else 1
