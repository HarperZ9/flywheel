"""Candidate-prefix C/A/B experiment apparatus for local structured finalization."""
from __future__ import annotations
import hashlib, json, shutil, time
from pathlib import Path
from typing import Any, Callable

from .cross_harness_artifacts import canonical_sha256, materialize_response_envelope, snapshot_source_tree
from .cross_harness_oracles import OracleContext, evaluate_task_oracle
from .cross_harness_policy import SHARED_TOOL_POLICY
from .cross_harness_runtime_context import stage_runtime_context
from .cross_harness_types import AttemptRequest
from .endpoint_registry import BackendProposer
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate
from .observed_proposer import ObservedProposer
from .cross_harness_adapters import READ_ONLY_SYSTEM
from .router_agent import RouterAgent
from .structured_finalizer import _messages, local_structured_finalizer_factory
from .local_finalizer_schema import schema_for_task

FIXED_PARAMS = {
    "provider_role": "local_14b", "repetitions": 1, "temperature": 0.0, "seed": 0,
    "max_normal_invocations": 6, "max_finalizer_invocations": 1,
    "normal_output_tokens": 2048, "finalizer_output_tokens": 2048,
    "structured_final_output.max_output_tokens": 2048,
    "normal_invocation_timeout_seconds": 120, "normal_prefix_deadline_seconds": 720,
    "finalizer_invocation_timeout_seconds": 120, "represented_ab_total_deadline_seconds": 840,
    "finalizer_context_max_bytes": 65536, "normal_context_max_bytes": 131072,
    "raw_request_cap_bytes": 1048576, "raw_response_cap_bytes": 1048576,
    "raw_tool_trace_cap_bytes": 1048576, "row_field_cap_bytes": 65536,
    "cache_state": "warm_or_unknown_recorded",
}
ARMS = ("C", "A", "B")
ORDER_PLAN_SCHEMA = "harness.local-finalizer-candidate-prefix-order-plan/v1"
SYSTEMIC_FINALIZER_STATES = {
    "deadline_exhausted",
    "provider_json_invalid",
    "request_rejected",
    "timeout",
    "transport_error",
    "transport_timeout",
    "unavailable",
    "unsupported",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False) + "\n", encoding="utf-8", newline="")
    return path

def _task_arm_orders(tasks: list[dict[str, Any]], order_plan: dict[str, Any] | None) -> dict[str, list[str]]:
    ids = [task["task_id"] for task in tasks]
    if order_plan is None: return {task_id: list(ARMS) for task_id in ids}
    err = "order plan must name every task and each arm exactly once"
    orders = order_plan.get("orders") if isinstance(order_plan, dict) else None
    if not isinstance(order_plan, dict) or order_plan.get("schema") != ORDER_PLAN_SCHEMA or not isinstance(orders, dict) or set(orders) != set(ids):
        raise ValueError(err)
    task_sets = [task.get("task_set_id") for task in tasks]
    if not task_sets or any(not isinstance(item, str) or not item for item in task_sets) or len(set(task_sets)) != 1 or order_plan.get("task_set_id") != task_sets[0]: raise ValueError("order plan task_set_id must match unique task set")
    out = {}
    for task_id in ids:
        order = orders[task_id]
        if not isinstance(order, list) or len(order) != len(ARMS) or set(order) != set(ARMS): raise ValueError(err)
        out[task_id] = list(order)
    return out

def _copy_json(src: Path, dst: Path, drop) -> str:
    item = json.loads(src.read_text(encoding="utf-8"))
    visible = drop(json.loads(json.dumps(item)))
    _write_json(dst, visible)
    return _sha(dst.read_bytes())


def build_nonleaky_overlay(source_root: Path, out_dir: Path) -> list[dict[str, Any]]:
    """Write visible and hidden fixtures for the two leaky semantic tasks."""
    source_root, out_dir = Path(source_root), Path(out_dir)
    if out_dir.exists():
        raise ValueError("overlay output already exists")
    specs = [
        ("lfh-015-evidence-bound-nonleaky", "agt-015-evidence-bound-reporting",
         "evidence-bound-claims-v1.json", lambda d: {**d, "claims": [
             {k: v for k, v in row.items() if k != "supported_by"}
             for row in d.get("claims", [])]}),
        ("lfh-016-source-contradiction-nonleaky", "agt-016-source-contradiction-detection",
         "source-contradiction-records-v1.json", lambda d: {k: v for k, v in d.items()
             if k not in {"contradiction_pairs", "reconcilable_pairs"}}),
    ]
    rows = []
    base = source_root / "benchmarks" / "fixtures" / "cross-harness"
    for task_id, base_task_id, name, scrub in specs:
        src = base / name
        visible_rel = f"visible/{task_id}.json"
        oracle_rel = f"oracle/{task_id}.json"
        visible_hash = _copy_json(src, out_dir / visible_rel, scrub)
        oracle = json.loads(src.read_text(encoding="utf-8"))
        _write_json(out_dir / oracle_rel, oracle)
        rows.append({"task_id": task_id, "base_task_id": base_task_id,
                     "visible_fixture": visible_rel, "oracle_fixture": oracle_rel,
                     "visible_input_sha256s": {visible_rel: visible_hash},
                     "oracle_input_sha256s": {oracle_rel: _sha((out_dir / oracle_rel).read_bytes())}})
    return rows


def _policy(task: dict[str, Any], mode: str, params: dict[str, Any]) -> dict[str, Any]:
    policy = dict(SHARED_TOOL_POLICY)
    policy.update({"max_steps": params["max_normal_invocations"],
                   "max_output_tokens": params["normal_output_tokens"]})
    if mode:
        policy["structured_final_output"] = {"enabled": True, "format_mode": mode,
            "schema": schema_for_task(task) if mode == "schema" else None,
            "max_output_tokens": params["finalizer_output_tokens"],
            "context_max_bytes": params["finalizer_context_max_bytes"],
            "retain_private_finalizer_payloads": True}
    return policy


def arm_request_shapes(task: dict[str, Any], ctx: dict[str, Any], params: dict[str, Any]):
    schema = schema_for_task(task)
    cfg = {"system": "Return only the requested final artifact envelope.", "schema": schema,
           "max_output_tokens": params["finalizer_output_tokens"]}
    base = {"messages": _messages(ctx, cfg), "max_output_tokens": params["finalizer_output_tokens"],
            "seed": params["seed"], "temperature": params["temperature"]}
    return {**base, "schema": schema}, {**base, "format": schema}


def score_arm_text(task: dict[str, Any], arm: str, text: str, attempt: Path, candidate: dict[str, Any]):
    try:
        raw, artifacts = materialize_response_envelope(text, task["expected_artifacts"], attempt)
    except ValueError as exc:
        return "malformed", [str(exc)]
    receipt = attempt / "provider-receipt.json"
    _write_json(receipt, {"arm": arm, "candidate_sha256": candidate.get("candidate_sha256", "")})
    visible = dict(task.get("visible_input_sha256s", task.get("input_sha256s", {})))
    core = {"workspace_root": str(candidate["workspace_root"]), "attempt_dir": str(attempt),
            "oracle_root": str(candidate.get("oracle_root", candidate["workspace_root"])),
            "raw_prompt_sha256": task.get("raw_prompt_sha256", ""),
            "tool_policy_sha256": canonical_sha256(candidate.get("tool_policy", {})),
            "raw_artifact_sha256": _sha(raw.read_bytes()), "receipt_sha256": _sha(receipt.read_bytes()),
            "orthogonal_states": {"execution_state": "returned", "oracle_state": "not_run", "receipt_state": "not_emitted"}}
    oracle = evaluate_task_oracle(OracleContext(task["task_id"], dict(task.get("oracle", {})), raw,
        artifacts, visible, core, visible_input_sha256s=visible,
        oracle_input_sha256s=dict(task.get("oracle_input_sha256s", task.get("input_sha256s", {})))))
    return oracle.state, oracle.failure_codes


def _row(task, arm, candidate, finalizer_state, oracle_state, codes, calls, req_hash="", order_index=0, order_hash=""):
    return {"schema": "harness.local-finalizer-candidate-prefix-row/v1", "task_id": task["task_id"],
            "arm": arm, "candidate_sha256": candidate.get("candidate_sha256", ""),
            "candidate_state": candidate.get("candidate_state", ""), "finalizer_state": finalizer_state,
            "oracle_state": oracle_state, "failure_codes": list(codes),
            "model_calls_after_prefix": calls, "request_body_sha256": req_hash,
            "arm_order_index": order_index, "task_arm_order_sha256": order_hash,
            "primary_outcome": "completed" if oracle_state == "pass" else "not_completed"}


def _ineligible_state(candidate: dict[str, Any]) -> str:
    text = " ".join(str(candidate.get(key, "")) for key in ("candidate_state", "selected_text", "failure_detail", "note")).lower()
    if "max_step" in text or "max steps" in text: return "max_steps_not_eligible"
    if "exec" in text and "denied" in text: return "exec_denied_not_eligible"
    if "criteria" in text and ("fail" in text or "failing" in text): return "criteria_failed_not_eligible"
    if "test" in text and ("fail" in text or "denied" in text): return "criteria_failed_not_eligible"
    return "candidate_not_eligible"


def run_candidate_prefix_experiment(tasks: list[dict[str, Any]], run_root: Path, params: dict[str, Any], *,
                                     candidate_runner: Callable, finalizer_runner: Callable,
                                     score_runner: Callable = score_arm_text,
                                     order_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    run_root = Path(run_root)
    if run_root.exists(): raise ValueError("run root already exists")
    task_arm_orders = _task_arm_orders(tasks, order_plan)
    order_hash = canonical_sha256(task_arm_orders)
    run_root.mkdir(parents=True)
    manifest = {"schema": "harness.local-finalizer-candidate-prefix-manifest/v1",
                "arms": list(ARMS), "params": params,
                "tasks": [task["task_id"] for task in tasks],
                "task_arm_orders": task_arm_orders, "task_arm_order_sha256": order_hash}
    _write_json(run_root / "pre-run-manifest.json", manifest)
    rows = []
    stopped_finalizer_arms: dict[str, str] = {}
    for task in tasks:
        prefix_dir = run_root / task["task_id"] / "candidate-prefix"
        try:
            candidate = candidate_runner(task, params, prefix_dir)
            candidate.setdefault("candidate_sha256", _sha(str(candidate.get("selected_text", "")).encode()))
        except Exception as exc:
            candidate = {"state": "upstream_candidate_unavailable", "candidate_state": "upstream_candidate_unavailable",
                         "candidate_sha256": "", "failure_detail": type(exc).__name__}
        for order_index, arm in enumerate(task_arm_orders[task["task_id"]]):
            attempt = run_root / task["task_id"] / arm
            def row(finalizer_state, oracle_state, codes, calls, req_hash=""):
                return _row(task, arm, candidate, finalizer_state, oracle_state, codes, calls,
                            req_hash, order_index, order_hash)
            if candidate.get("state") != "returned":
                rows.append(row("upstream_candidate_unavailable", "not_run", [], 0)); continue
            if not candidate.get("eligible", True):
                state = _ineligible_state(candidate)
                rows.append(row(state, "not_run", [state], 0)); continue
            if arm == "C":
                state, codes = score_runner(task, arm, candidate["selected_text"], attempt, candidate)
                rows.append(row("not_invoked", state, codes, 0)); continue
            if arm in stopped_finalizer_arms:
                rows.append(row("not_started_after_systemic_finalizer_block",
                                "not_run", [stopped_finalizer_arms[arm]], 0)); continue
            try:
                out = finalizer_runner(arm, task, candidate, params, attempt)
            except Exception as exc:
                finalizer_state = type(exc).__name__
                stopped_finalizer_arms[arm] = finalizer_state
                rows.append(row(finalizer_state, "not_run", [], 1)); continue
            fstate = str(out.get("state", "returned"))
            if fstate in SYSTEMIC_FINALIZER_STATES:
                stopped_finalizer_arms[arm] = fstate
            if fstate == "returned" and isinstance(out.get("selected_text"), str):
                state, codes = score_runner(task, arm, out["selected_text"], attempt, candidate)
            else:
                state, codes = "not_run", []
            rows.append(row(fstate, state, codes, 1, str(out.get("request_body_sha256", ""))))
    summary = {"schema": "harness.local-finalizer-candidate-prefix-run/v1", "denominator": len(tasks) * 3,
               "rows": rows, "params_sha256": canonical_sha256(params),
               "task_arm_orders": task_arm_orders, "task_arm_order_sha256": order_hash}
    _write_json(run_root / "rows.json", rows)
    _write_json(run_root / "run-summary.json", summary)
    return summary


class LocalCandidatePrefixRunner:
    def __init__(self, adapter, source_root: Path, params: dict[str, Any]):
        self.adapter, self.source_root, self.params = adapter, Path(source_root), params

    def _workspace(self, task: dict[str, Any], attempt: Path, tool_policy_sha256: str = ""):
        workspace = attempt / "workspace"; workspace.mkdir(parents=True)
        for rel, src in task.get("visible_sources", {}).items():
            target = workspace / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, target)
        observed = {rel: _sha((workspace / rel).read_bytes()) for rel in task.get("visible_sources", {})}
        expected = dict(task.get("visible_input_sha256s", task.get("input_sha256s", {})))
        if observed != expected:
            raise ValueError("visible input hash mismatch")
        row = {"task_id": task["task_id"], "raw_prompt_sha256": task["raw_prompt_sha256"],
               "tool_policy_sha256": tool_policy_sha256}
        context, _ = stage_runtime_context(workspace, attempt, task, row, observed)
        return workspace, observed, context

    def candidate(self, task: dict[str, Any], params: dict[str, Any], out_dir: Path):
        policy = _policy(task, "", params)
        workspace, observed, _ = self._workspace(task, out_dir, canonical_sha256(policy))
        req = AttemptRequest("local-finalizer-heldout", "candidate-prefix", task.get("task_set_id", ""),
            task["task_id"], task["prompt"], task["raw_prompt_sha256"], self.adapter.role,
            "local_endpoint", self.adapter.adapter_id, task.get("model_id", "flywheel-local-coder-14b"),
            self.adapter.profile["model_ref"], workspace, snapshot_source_tree(workspace)["sha256"],
            observed, policy, canonical_sha256(policy), 1, params["cache_state"],
            params["normal_prefix_deadline_seconds"], out_dir)
        availability = self.adapter.availability(req)
        if not availability.available:
            raise RuntimeError(getattr(availability, "failure_class", "unavailable") or "unavailable")
        backend = self.adapter.backend_factory(self.adapter.profile, params["normal_invocation_timeout_seconds"])
        proposer = BackendProposer(backend, model_ref="", extract=False); proposer.usage_event_source = "local_endpoint_inner"
        tracked = ObservedProposer(proposer, params["normal_prefix_deadline_seconds"], time.monotonic,
                                   True, params["max_normal_invocations"])
        agent = RouterAgent(model=req.model_id, proposer=tracked, system=READ_ONLY_SYSTEM,
                            max_tokens=params["normal_output_tokens"])
        captured = []
        def capture(ctx): captured.append(dict(ctx)); return {"state": "candidate_captured", "selected_text": ctx["candidate_text"]}
        result = run_agent(agent, req.prompt, ToolExecutor(root=str(workspace), gate=ToolGate(False, False, False), external={}),
                           SessionLedger(), max_steps=params["max_normal_invocations"], finalize_candidate=capture)
        ctx = captured[0] if captured else {}
        state = ctx.get("candidate_state") or ("max_steps_reached" if str(result.get("final", "")).startswith("[max_steps") else "not_eligible")
        return {"state": "returned", "eligible": bool(captured), "selected_text": result["final"],
                "context": ctx, "candidate_state": state,
                "candidate_sha256": _sha(result["final"].encode()), "normal_call_count": tracked.calls,
                "workspace_root": workspace, "oracle_root": task.get("oracle_root", workspace),
                "tool_policy": policy}

    def finalizer(self, arm: str, task: dict[str, Any], candidate: dict[str, Any], params: dict[str, Any], out_dir: Path):
        mode = "unconstrained" if arm == "A" else "schema"
        policy = _policy(task, mode, params)
        req = AttemptRequest("local-finalizer-heldout", arm, task.get("task_set_id", ""), task["task_id"],
            task["prompt"], task["raw_prompt_sha256"], self.adapter.role, "local_endpoint", self.adapter.adapter_id,
            task.get("model_id", "flywheel-local-coder-14b"), self.adapter.profile["model_ref"],
            Path(candidate["workspace_root"]), "", task.get("visible_input_sha256s", {}), policy,
            canonical_sha256(policy), 1, params["cache_state"], params["finalizer_invocation_timeout_seconds"], out_dir)
        factory, _, _ = local_structured_finalizer_factory(self.adapter.profile, req)
        backend = self.adapter.backend_factory(self.adapter.profile, params["finalizer_invocation_timeout_seconds"])
        proposer = BackendProposer(backend, model_ref="", extract=False)
        tracked = ObservedProposer(proposer, params["finalizer_invocation_timeout_seconds"], time.monotonic,
                                   True, candidate.get("normal_call_count", 0) + 1)
        tracked.calls = candidate.get("normal_call_count", 0)
        finalize, resource = factory(tracked)
        result = finalize(candidate["context"])
        if isinstance(resource, dict):
            result = {**result, "resource": resource}
        _write_json(out_dir / "structured-finalizer-result.json", result)
        return {**result, "request_body_sha256": result.get("evidence", {}).get("request_body_sha256", "")}
