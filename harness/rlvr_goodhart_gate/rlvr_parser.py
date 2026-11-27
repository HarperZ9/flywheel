# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for Test-Time MCTS and Self-Play RLVR receipts/reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.rlvr_goodhart_gate.goodhart_guards import is_strict_int


@dataclass(frozen=True)
class CandidateEval:
    """Single candidate evaluation comparing PRM proxy vs deterministic oracle."""

    candidate_id: str
    prm_score: Any
    oracle_score: Any
    accepted: Any
    quarantined: Any
    assigned_value: Any = None


@dataclass(frozen=True)
class PolicyUpdateRecord:
    """Single RLVR policy update attempt."""

    step: int
    oracle_score: Any
    weight_delta: Any
    blocked: Any


@dataclass(frozen=True)
class GoodhartBundle:
    """Normalized Goodhart / RLVR attestation bundle."""

    schema: str
    ok_flag: Any
    verdict: str
    mcts_hacked_accepted: Any
    goodhart_blocked: Any
    greedy_hacked: Any
    monotonic_ok: Any
    round0_rate: Any
    final_rate: Any
    mean_trap_prob: Any
    max_3way_err: Any
    controls_caught: Any
    controls_total: Any
    candidates: tuple[CandidateEval, ...]
    policy_updates: tuple[PolicyUpdateRecord, ...]
    solve_curve: tuple[Any, ...] | None
    receipt_verdict: str | None = None
    receipt_exit_code: int | None = None
    parse_errors: tuple[str, ...] = ()


def _parse_candidates(raw: Any, errs: list[str]) -> tuple[CandidateEval, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("candidates_not_list")
        return ()
    out: list[CandidateEval] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"candidate_not_dict_{idx}")
            continue
        out.append(
            CandidateEval(
                candidate_id=str(item.get("candidate_id", f"cand_{idx}")),
                prm_score=item.get("prm_score"),
                oracle_score=item.get("oracle_score"),
                accepted=item.get("accepted"),
                quarantined=item.get("quarantined"),
                assigned_value=item.get("assigned_value"),
            )
        )
    return tuple(out)


def _parse_updates(raw: Any, errs: list[str]) -> tuple[PolicyUpdateRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("policy_updates_not_list")
        return ()
    out: list[PolicyUpdateRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"policy_update_not_dict_{idx}")
            continue
        step = item.get("step", idx)
        out.append(
            PolicyUpdateRecord(
                step=step if is_strict_int(step) else -1,
                oracle_score=item.get("oracle_score"),
                weight_delta=item.get("weight_delta"),
                blocked=item.get("blocked"),
            )
        )
    return tuple(out)


def parse_goodhart_payload(
    data: dict[str, Any],
    receipt: dict[str, Any] | None = None,
) -> GoodhartBundle:
    """Parse MCTS Goodhart (68864), RLVR Synthesizer (68868), or direct candidate JSON."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return GoodhartBundle(
            "", False, "REJECT", None, None, None, None, None, None, None, None, None, None,
            (), (), None, parse_errors=("payload_not_dict",),
        )
    candidates = _parse_candidates(data.get("candidates"), errs)
    updates = _parse_updates(data.get("policy_updates"), errs)
    raw_curve = data.get("solve_curve")
    curve = tuple(raw_curve) if isinstance(raw_curve, list) else raw_curve
    r_verdict: str | None = None
    r_exit: int | None = None
    if receipt is not None:
        if not isinstance(receipt, dict):
            errs.append("receipt_not_dict")
        else:
            r_verdict = str(receipt.get("verdict", ""))
            oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
            ec = oracle.get("exit_code", -1)
            r_exit = ec if is_strict_int(ec) else -1
    return GoodhartBundle(
        schema=str(data.get("schema", "")),
        ok_flag=data.get("ok"),
        verdict=str(data.get("verdict", "")),
        mcts_hacked_accepted=data.get("mcts_hacked_accepted"),
        goodhart_blocked=data.get("goodhart_blocked"),
        greedy_hacked=data.get("greedy_hacked"),
        monotonic_ok=data.get("monotonic_ok"),
        round0_rate=data.get("round0_rate"),
        final_rate=data.get("final_rate"),
        mean_trap_prob=data.get("mean_trap_prob"),
        max_3way_err=data.get("max_3way_err"),
        controls_caught=data.get("controls_caught"),
        controls_total=data.get("controls_total"),
        candidates=candidates,
        policy_updates=updates,
        solve_curve=curve,
        receipt_verdict=r_verdict,
        receipt_exit_code=r_exit,
        parse_errors=tuple(errs),
    )
