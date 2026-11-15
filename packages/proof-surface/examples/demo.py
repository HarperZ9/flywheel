#!/usr/bin/env python3
"""End-to-end demo of the proof-surface contract family.

Best-effort demo -- not runtime-verified by author.

Exercises every active contract through its real public API, using only
functions exported from the top-level ``proof_surface`` package:

  * authorization receipt   -- validate + check_action (allow / deny)
  * pre-execution gate       -- evaluate_gate (allow / needs-human)
  * evaluation contract      -- evaluate (deploy / needs-human on uncertainty)
  * claim ledger             -- validate + confidence_gate / find_conflicts /
                               trace_dependents
  * delegation chain         -- compute_binding / compute_chain_binding (producer)
                               + validate + verify_delegation (VALID / DENIED /
                               UNVERIFIABLE)

Run from a checkout without installing:

    PYTHONPATH=src python examples/demo.py

or, after ``pip install .``:

    python examples/demo.py

Nothing here grants authority. Every result is a verifier input or a
reviewer-facing decision; none of it is meant to be read back into a model as
trusted state. A fixed ``now`` is used so the temporal checks are deterministic.
"""

from __future__ import annotations

from datetime import datetime, timezone

from proof_surface import (
    # authorization receipt
    check_action,
    validate_authorization_receipt,
    # pre-execution gate
    evaluate_gate,
    # evaluation contract
    evaluate,
    # claim ledger
    confidence_gate,
    find_conflicts,
    trace_dependents,
    validate_claim_ledger,
    # delegation chain
    compute_binding,
    compute_chain_binding,
    validate_delegation_chain,
    verify_delegation,
)

# A fixed instant inside every grant window below, so the demo is reproducible.
NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def demo_authorization_receipt() -> dict:
    banner("authorization receipt")
    receipt = {
        "authorization_version": "0.1",
        "receipt_id": "ar-demo",
        "kind": "authorization-grant",
        "principal": {"id": "user:alice@example.com", "role": "project-owner"},
        "agent": {"id": "agent:planner"},
        "intent": "Read repository files.",
        "scope": {
            "allowed_actions": ["read_file"],
            "allowed_targets": ["repo:proof-surface"],
        },
        "granted_at": "2026-06-17T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "revoked": False,
    }
    print("validate          :", validate_authorization_receipt(receipt))
    print(
        "check allowed     :",
        check_action(receipt, "read_file", "repo:proof-surface", now=NOW),
    )
    print(
        "check denied      :",
        check_action(receipt, "delete_file", "repo:proof-surface", now=NOW),
    )
    return receipt


def demo_pre_execution_gate(receipt: dict) -> None:
    banner("pre-execution gate")
    request = {
        "planned_action": {
            "action_kind": "read_file",
            "target": "repo:proof-surface",
            "estimated_cost": {"tokens": 100},
        },
        "authorization": receipt,
        "budget": {"remaining_tokens": 1000},
    }
    allowed = evaluate_gate(request)
    print("with budget       :", allowed.decision, allowed.checks)

    # Estimated cost present but no remaining budget figure -> cannot confirm ->
    # budget check is "unknown" -> gate escalates to needs-human (fail-closed).
    no_budget = {**request, "budget": {}}
    escalated = evaluate_gate(no_budget)
    print("without budget    :", escalated.decision, escalated.checks)


def demo_evaluation_contract() -> None:
    banner("evaluation contract")
    contract = {
        "eval_version": "0.1",
        "contract_id": "ec-demo",
        "objective": "Gate deploy on accuracy and latency.",
        "criteria": [
            {
                "name": "accuracy",
                "metric": "accuracy_pct",
                "threshold": 90.0,
                "direction": ">=",
                "required": True,
            },
            {
                "name": "p99_latency_ms",
                "metric": "p99_latency_ms",
                "threshold": 500.0,
                "direction": "<=",
                "required": True,
            },
        ],
    }
    clear = [
        {"name": "accuracy", "measured": 92.3, "uncertainty": 0.5},
        {"name": "p99_latency_ms", "measured": 480.0, "uncertainty": 5.0},
    ]
    clear_decision = evaluate(contract, clear)
    print("clear pass        :", clear_decision.decision, clear_decision.per_criterion)

    # 89.2..91.2 straddles the 90.0 threshold -> uncertain -> never deploy.
    straddle = [
        {"name": "accuracy", "measured": 90.2, "uncertainty": 1.0},
        {"name": "p99_latency_ms", "measured": 480.0},
    ]
    straddle_decision = evaluate(contract, straddle)
    print(
        "uncertain straddle:",
        straddle_decision.decision,
        straddle_decision.per_criterion,
    )


def demo_claim_ledger() -> None:
    banner("claim ledger")
    ledger = {
        "ledger_version": "0.1",
        "claims": [
            {
                "claim_id": "c1",
                "statement": "Accuracy on the held-out set is 92.3%.",
                "source": "agent:evaluator-v1",
                "confidence": 0.95,
                "evidence_refs": ["runs/metrics.json"],
                "depends_on": [],
                "conflicts_with": [],
            },
            {
                "claim_id": "c2",
                "statement": "Accuracy on the held-out set is 87.1%.",
                "source": "agent:evaluator-v2",
                "confidence": 0.40,
                "evidence_refs": ["runs/metrics-v2.json"],
                "depends_on": [],
                "conflicts_with": ["c1"],
            },
            {
                "claim_id": "c3",
                "statement": "The p99 latency at accuracy=92.3% is below 500ms.",
                "source": "agent:perf-probe",
                "confidence": 0.90,
                "evidence_refs": ["runs/latency.json"],
                "depends_on": ["c1"],
                "conflicts_with": [],
            },
        ],
    }
    print("validate          :", validate_claim_ledger(ledger))
    print("low confidence<0.5:", confidence_gate(ledger, 0.5))
    print("declared conflicts:", find_conflicts(ledger))
    print("dependents of c1  :", trace_dependents(ledger, "c1"))


def demo_delegation_chain() -> None:
    banner("delegation chain")
    hop = {
        "from": {"id": "alice@example.com", "kind": "human"},
        "to": {"id": "agent:planner", "kind": "agent"},
        "scope": {
            "allowed_actions": ["read", "summarize"],
            "allowed_targets": ["repo:proof-surface"],
        },
        "granted_at": "2026-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "revoked": False,
    }
    # Producer side: compute the per-hop binding (root uses prev_binding="") and
    # the whole-chain commitment.
    hop["binding"] = compute_binding(hop, "")
    chain = {
        "delegation_version": "0.1",
        "chain_id": "chain-demo",
        "hops": [hop],
        "chain_binding": compute_chain_binding("chain-demo", 1, hop["binding"]),
    }

    print("validate          :", validate_delegation_chain(chain))

    ok = verify_delegation(chain, action="read", target="repo:proof-surface", now=NOW)
    print("verify in-scope   :", ok.verdict, ok.effective_scope)

    denied = verify_delegation(
        chain, action="delete", target="repo:proof-surface", now=NOW
    )
    print("verify out-of-scope:", denied.verdict)

    # Signature-level identity demanded with no verifier supplied: the stdlib
    # cannot verify asymmetric signatures, so this is honestly UNVERIFIABLE,
    # never a fabricated VALID.
    unverifiable = verify_delegation(chain, require_signatures=True, now=NOW)
    print("verify no verifier:", unverifiable.verdict)


def main() -> None:
    receipt = demo_authorization_receipt()
    demo_pre_execution_gate(receipt)
    demo_evaluation_contract()
    demo_claim_ledger()
    demo_delegation_chain()
    print("\nDemo complete. Every result above is a verifier input or a")
    print("reviewer-facing decision -- none of it grants authority.")


if __name__ == "__main__":
    main()
