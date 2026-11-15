"""The write-gate bridge -- perceived ground truth -> a mediated action request.

This is the seam between the read-gate (perception) and the write-gate
(proof-surface's pre-execution gate).  A model that wants to ACT does not act:
it hands its intent here, the membrane assembles a gate request that carries the
*perceived, witnessed state* alongside the intent, and the proof-surface gate
returns an advisory allow / deny / needs-human.  Only the operator/runtime acts
on an `allow`.

The membrane itself NEVER executes the action and never grants authority.  It
translates perception into the gate's input contract and, if proof-surface is
installed, asks the gate.  If it is not installed, it returns needs-human --
fail-closed, never a fabricated allow.

The elegant tie: a DriftVerdict's MATCH / DRIFT / UNVERIFIABLE is exactly the
gate's witness_verdict lattice, so a perceived visual drift flows straight into
the gate's state check with no translation loss.
"""

from __future__ import annotations

from typing import Any

from .observation import Observation
from .phash import DriftVerdict


def build_gate_request(
    *,
    action_kind: str,
    target: str,
    authorization: dict[str, Any],
    observation: Observation | None = None,
    drift: DriftVerdict | None = None,
    expected_digest: str | None = None,
    budget: dict[str, Any] | None = None,
    estimated_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a proof-surface gate request grounded in perceived state.

    The `state` block is populated only from witnessed values:
      * a DriftVerdict becomes `witness_verdict` (MATCH/DRIFT/UNVERIFIABLE),
      * a perceived identity digest plus a supplied `expected_digest` become the
        target/expected digest pair (both 64-hex, supplied together so the gate's
        co-presence rule is satisfied).
    """
    planned: dict[str, Any] = {"action_kind": action_kind, "target": target}
    if estimated_cost is not None:
        planned["estimated_cost"] = estimated_cost

    request: dict[str, Any] = {
        "planned_action": planned,
        "authorization": authorization,
        "budget": budget if budget is not None else {},
    }

    state: dict[str, Any] = {}
    if drift is not None:
        state["witness_verdict"] = drift.verdict
    observed_digest = (
        observation.data.get("identity_sha256") if observation is not None else None
    )
    if observed_digest and expected_digest:
        # Both present together -- satisfies the gate's digest co-presence rule.
        state["target_digest"] = observed_digest
        state["expected_digest"] = expected_digest
    if state:
        request["state"] = state

    return request


def decide(request: dict[str, Any]) -> Any:
    """Ask the write-gate (proof-surface) to adjudicate the request.

    Returns proof-surface's GateDecision when available.  If proof-surface is
    not installed, returns a fail-closed needs-human advisory dict -- never a
    fabricated allow.
    """
    try:
        from proof_surface import evaluate_gate
    except ImportError:
        return {
            "decision": "needs-human",
            "reasons": [
                "the write-gate (proof-surface) is not installed; install it to "
                "adjudicate this request -- no decision is fabricated"
            ],
            "checks": {},
        }
    return evaluate_gate(request)
