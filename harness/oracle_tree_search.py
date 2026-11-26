"""Execution-Oracle-Guided PUCT Verification Tree Search (Wave 26B).

Replaces noisy LLM-as-a-judge Process Reward Models (PRMs) with hard
deterministic execution oracles (AST f64_oracle, Three-Plate Plate B,
prompt-injection scrubber, and optional custom deterministic verifiers).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .evidence_json import canonical_bytes
from .gateway_secret_boundary import validate_no_raw_secrets
from .super_solver_pipeline import eval_f64_oracle, sanitize_trace_text
from .three_plate_oracle import run_plate_b

SEARCH_RECEIPT_SCHEMA = "flywheel.oracle-tree-search/v1"
CustomOracleFn = Callable[["SearchCandidate"], tuple[str, str]]


@dataclass(frozen=True)
class SearchCandidate:
    node_id: str
    parent_id: str | None
    state_key: str
    action_label: str
    prior_prob: float
    tokens: int
    is_terminal: bool = False
    need_more_evidence: bool = False
    numeric_expr: str = ""
    claimed_numeric: float | None = None
    numeric_rel_tol: float = 1e-6
    candidate_code: str = ""
    action_text: str = ""
    reasoning_trace: str = ""


@dataclass(frozen=True)
class SearchBudget:
    max_expansions: int = 32
    max_tokens: int = 8000
    max_depth: int = 8
    c_puct: float = 1.4
    lambda_tok: float = 0.15


@dataclass(frozen=True)
class OracleEvalResult:
    q_oracle: float
    verdict: str
    reason: str
    witness: dict[str, Any]


@dataclass
class _SearchState:
    nodes_by_id: dict[str, SearchCandidate] = field(default_factory=dict)
    parents: dict[str, str | None] = field(default_factory=dict)
    states: dict[str, str] = field(default_factory=dict)
    depths: dict[str, int] = field(default_factory=dict)
    visits: dict[str, int] = field(default_factory=dict)
    evals: dict[str, OracleEvalResult] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    pruned_ids: list[str] = field(default_factory=list)
    frontier: list[str] = field(default_factory=list)
    tokens_used: int = 0
    expansions: int = 0
    cycle_blocks: int = 0
    winner_id: str | None = None


def _check_numeric_oracle(cand: SearchCandidate) -> tuple[bool, str, dict[str, Any]]:
    if cand.claimed_numeric is None and not cand.numeric_expr.strip():
        return True, "no_numeric_claim", {"checked": False}
    if cand.claimed_numeric is None or not cand.numeric_expr.strip():
        return False, "missing_numeric_expr_or_claim", {"checked": True, "ok": False}
    try:
        exact = eval_f64_oracle(cand.numeric_expr)
    except Exception:
        return False, "invalid_f64_expr", {"checked": True, "ok": False, "numeric_expr": cand.numeric_expr}
    claimed = float(cand.claimed_numeric)
    ok = math.isclose(claimed, exact, rel_tol=cand.numeric_rel_tol, abs_tol=1e-9)
    witness = {"checked": True, "ok": ok, "numeric_expr": cand.numeric_expr,
               "claimed_numeric": claimed, "exact": exact, "rel_tol": cand.numeric_rel_tol}
    return ok, ("f64_oracle_pass" if ok else "f64_oracle_mismatch"), witness


def evaluate_node_oracle(
    candidate: SearchCandidate, *, custom_oracle: CustomOracleFn | None = None,
) -> OracleEvalResult:
    """Evaluate a search node with hard deterministic verifiers (zero PRM)."""
    hits = (
        sanitize_trace_text(candidate.action_text)[1]
        + sanitize_trace_text(candidate.candidate_code)[1]
        + sanitize_trace_text(candidate.reasoning_trace)[1]
    )
    if hits:
        return OracleEvalResult(-math.inf, "PRUNED", "prompt_injection_detected", {"hits": hits})
    if candidate.candidate_code.strip():
        pb = run_plate_b({"claim_or_code": candidate.candidate_code})
        if not pb.passed:
            return OracleEvalResult(-math.inf, "PRUNED", "plate_b_defect", {"defects": list(pb.defects)})
    num_ok, num_reason, num_witness = _check_numeric_oracle(candidate)
    if not num_ok:
        return OracleEvalResult(-math.inf, "PRUNED", num_reason, {"numeric": num_witness})
    c_status, c_reason = custom_oracle(candidate) if custom_oracle is not None else ("PASS", "none")
    if c_status == "FAIL":
        return OracleEvalResult(-math.inf, "PRUNED", f"custom_oracle_fail:{c_reason}", {"custom": c_reason})
    witness = {"numeric": num_witness, "plate_b_pass": True, "custom_status": c_status}
    if candidate.is_terminal and not candidate.need_more_evidence and c_status == "PASS":
        return OracleEvalResult(1.0, "PASS", "oracle_terminal_pass", witness)
    q_val = 0.5 if (candidate.need_more_evidence or c_status == "PARTIAL") else 0.0
    return OracleEvalResult(q_val, "PARTIAL", "open_belief_partial", witness)


def compute_puct_score(
    q_oracle: float, prior_prob: float, parent_visits: int, child_visits: int, tokens: int, budget: SearchBudget,
) -> float:
    """WAVE25I Eq. 3.3.1: Q_oracle + c_puct * P * sqrt(N(s))/(1+N(s,a)) - lam * tok/B_max."""
    if math.isinf(q_oracle) and q_oracle < 0:
        return -math.inf
    clamped = max(0.0, min(1.0, float(prior_prob)))
    explore = budget.c_puct * clamped * (math.sqrt(max(1, parent_visits)) / float(1 + max(0, child_visits)))
    tok_pen = budget.lambda_tok * (float(max(0, tokens)) / float(max(1, budget.max_tokens)))
    return round(q_oracle + explore - tok_pen, 6)


def _node_record(
    cand: SearchCandidate, depth: int, ev: OracleEvalResult, puct: float, *, pruned: bool, cycle_blocked: bool,
) -> dict[str, Any]:
    return {
        "node_id": cand.node_id, "parent_id": cand.parent_id, "state_key": cand.state_key,
        "action_label": cand.action_label, "depth": depth, "prior_prob": round(float(cand.prior_prob), 6),
        "tokens": int(cand.tokens), "is_terminal": bool(cand.is_terminal),
        "q_oracle": None if math.isinf(ev.q_oracle) else float(ev.q_oracle),
        "oracle_verdict": ev.verdict, "oracle_reason": ev.reason,
        "puct_score": None if math.isinf(puct) else float(puct),
        "pruned": pruned, "cycle_blocked": cycle_blocked,
        "reasoning_trace": cand.reasoning_trace, "witness": ev.witness,
    }


def _walk_parents(start_id: str | None, parents: Mapping[str, str | None]) -> list[str]:
    chain: list[str] = []
    cur, seen = start_id, set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = parents.get(cur)
    return chain


def _register_child(
    st: _SearchState, cur_id: str, child: SearchCandidate, anc_states: set[str],
    budget: SearchBudget, custom_oracle: CustomOracleFn | None,
) -> None:
    st.tokens_used += int(child.tokens)
    depth = st.depths[cur_id] + 1
    if child.state_key in anc_states or child.node_id in st.nodes_by_id:
        st.cycle_blocks += 1
        cyc = OracleEvalResult(-math.inf, "PRUNED", "cycle_detected", {"state_key": child.state_key})
        st.records.append(_node_record(child, depth, cyc, -math.inf, pruned=True, cycle_blocked=True))
        st.pruned_ids.append(child.node_id)
        return
    ev = evaluate_node_oracle(child, custom_oracle=custom_oracle)
    puct = compute_puct_score(ev.q_oracle, child.prior_prob, st.visits[cur_id], 0, child.tokens, budget)
    st.nodes_by_id[child.node_id], st.parents[child.node_id] = child, cur_id
    st.states[child.node_id], st.depths[child.node_id] = child.state_key, depth
    st.evals[child.node_id], st.visits[child.node_id] = ev, 1
    for anc_id in _walk_parents(cur_id, st.parents):
        st.visits[anc_id] = st.visits.get(anc_id, 0) + 1
    is_pruned = ev.verdict == "PRUNED"
    st.records.append(_node_record(child, depth, ev, puct, pruned=is_pruned, cycle_blocked=False))
    if is_pruned:
        st.pruned_ids.append(child.node_id)
    elif ev.verdict == "PASS":
        st.winner_id = child.node_id
    else:
        st.frontier.append(child.node_id)


def _seal_result(task_id: str, status: str, st: _SearchState) -> dict[str, Any]:
    win_path = list(reversed(_walk_parents(st.winner_id, st.parents))) if st.winner_id else []
    body: dict[str, Any] = {
        "schema": SEARCH_RECEIPT_SCHEMA, "task_id": task_id, "status": status,
        "winner_node_id": st.winner_id, "winning_path": win_path,
        "pruned_node_ids": st.pruned_ids, "pruned_count": len(st.pruned_ids),
        "cycle_blocks": st.cycle_blocks, "expansions": st.expansions,
        "tokens_used": st.tokens_used, "nodes": st.records,
    }
    validate_no_raw_secrets(body)
    body["result_sha256"] = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def run_oracle_tree_search(
    task_id: str, root: SearchCandidate,
    expand_fn: Callable[[SearchCandidate], Sequence[SearchCandidate]],
    budget: SearchBudget = SearchBudget(), *, custom_oracle: CustomOracleFn | None = None,
) -> dict[str, Any]:
    """Run deterministic budget-capped PUCT search with hard Q_oracle pruning."""
    root_ev = evaluate_node_oracle(root, custom_oracle=custom_oracle)
    st = _SearchState(
        nodes_by_id={root.node_id: root}, parents={root.node_id: None}, states={root.node_id: root.state_key},
        depths={root.node_id: 0}, visits={root.node_id: 1}, evals={root.node_id: root_ev},
        records=[_node_record(root, 0, root_ev, root_ev.q_oracle, pruned=(root_ev.verdict == "PRUNED"), cycle_blocked=False)],
        pruned_ids=[root.node_id] if root_ev.verdict == "PRUNED" else [],
        frontier=[] if root_ev.verdict == "PRUNED" else [root.node_id],
        tokens_used=int(root.tokens), winner_id=root.node_id if root_ev.verdict == "PASS" else None,
    )
    while st.frontier and st.winner_id is None:
        if st.expansions >= budget.max_expansions or st.tokens_used >= budget.max_tokens:
            return _seal_result(task_id, "BUDGET_EXHAUSTED", st)
        st.frontier.sort(
            key=lambda nid: (
                compute_puct_score(st.evals[nid].q_oracle, st.nodes_by_id[nid].prior_prob,
                                   st.visits.get(st.parents[nid] or nid, 1), st.visits.get(nid, 0),
                                   st.nodes_by_id[nid].tokens, budget),
                -st.depths[nid], nid,
            ),
            reverse=True,
        )
        cur_id = st.frontier.pop(0)
        if st.evals[cur_id].verdict == "PASS":
            st.winner_id = cur_id
            break
        if st.depths[cur_id] >= budget.max_depth:
            continue
        st.expansions += 1
        anc = {st.states[a] for a in _walk_parents(cur_id, st.parents) if a in st.states}
        for child in expand_fn(st.nodes_by_id[cur_id]):
            _register_child(st, cur_id, child, anc, budget, custom_oracle)
            if st.winner_id is not None:
                break
        if st.tokens_used >= budget.max_tokens and st.winner_id is None:
            return _seal_result(task_id, "BUDGET_EXHAUSTED", st)
    return _seal_result(task_id, "SOLVED" if st.winner_id else "NO_VALID_PATH", st)


def verify_search_result(result: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Verify sealed search receipt integrity and hard-oracle victory invariant."""
    errors: list[str] = []
    if not isinstance(result, Mapping) or result.get("schema") != SEARCH_RECEIPT_SCHEMA:
        return False, ["invalid_schema"]
    body = {k: v for k, v in result.items() if k != "result_sha256"}
    if result.get("result_sha256") != "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest():
        errors.append("forged_search_result")
    if result.get("status") == "SOLVED":
        nodes = {n["node_id"]: n for n in result.get("nodes", []) if isinstance(n, dict) and "node_id" in n}
        win = nodes.get(result.get("winner_node_id"))
        if not win or win.get("oracle_verdict") != "PASS" or win.get("q_oracle") != 1.0:
            errors.append("winner_not_oracle_verified")
    return (len(errors) == 0), errors


def run_planted_search_demo() -> dict[str, Any]:
    """Prove planted high-prior wrong branch is pruned in favor of low-prior oracle winner."""
    root = SearchCandidate("root", None, "s0", "plan_problem", 1.0, 40, need_more_evidence=True)

    def _expand(node: SearchCandidate) -> list[SearchCandidate]:
        if node.node_id != "root":
            return []
        return [
            SearchCandidate(
                "branch_a_sycophant", "root", "s1_wrong", "emit_high_prior_wrong_sign",
                0.85, 120, is_terminal=True, numeric_expr="0.5 * 10.0 * (9.80665 ** 2)",
                claimed_numeric=-480.85191125, reasoning_trace="High prior fluent guess with subtle sign error.",
            ),
            SearchCandidate(
                "branch_b_oracle", "root", "s2_exact", "emit_low_prior_oracle_verified",
                0.15, 110, is_terminal=True, numeric_expr="0.5 * 10.0 * (9.80665 ** 2)",
                claimed_numeric=480.85191125,
                candidate_code="def kinetic_energy(m: float, v: float) -> float:\n    return 0.5 * m * v * v\n",
                reasoning_trace="Verified sign and magnitude via deterministic f64_oracle.",
            ),
        ]

    res = run_oracle_tree_search("wave26b-sycophant-vs-oracle", root, _expand)
    ok, errs = verify_search_result(res)
    return {
        "verified": ok, "errors": errs, "status": res["status"],
        "winner_node_id": res["winner_node_id"], "pruned_node_ids": res["pruned_node_ids"],
        "oracle_beat_prior_bias": (ok and res["winner_node_id"] == "branch_b_oracle" and "branch_a_sycophant" in res["pruned_node_ids"]),
        "result_sha256": res["result_sha256"],
    }
