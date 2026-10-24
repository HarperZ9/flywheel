"""Fail-closed admission contract for untrusted journey Python execution."""
from __future__ import annotations

from .verdict import UnverifiableReason

REASON = UnverifiableReason.EXECUTION_CONTAINMENT_UNAVAILABLE.value
DETAIL = ("arbitrary Python was not executed: this runtime lacks a deny-read, "
          "deny-egress containment boundary")
SCOPE = ("CONTAINMENT_BOUNDARY_RECORDED: the candidate and its tests stayed "
         "unexecuted, because deny-read and deny-egress containment is unavailable.")
REQUIREMENT = {
    "schema": "flywheel.python-execution-containment-requirement/v1",
    "status": "UNAVAILABLE",
    "child_process_spawned": False,
    "candidate_spawned": False,
    "candidate_executed": False,
    "tests_executed": False,
    "required_runtime": {
        "identity": "Windows AppContainer/lowbox identity",
        "filesystem": "allowlisted staging ACL",
        "network": "no network capabilities",
    },
}


def unavailable_result(*, claim_id: str, claim_verdict_before: str) -> dict:
    """Return a fresh public-safe description of the missing boundary."""
    # The check record shares evidence_packet.CHECK_SCHEMA; spelled here so the
    # verifier closure stays free of evidence_packet's imports. Keep them equal.
    return {
        "schema": "flywheel.evidence-check/v1",
        "verdict": "UNVERIFIABLE",
        "unverifiable_reason": REASON,
        "reason": DETAIL,
        "oracle_id": "code",
        "oracle_type": "pytest",
        "oracle_calls_consumed": 0,
        "claim_id": claim_id,
        "claim_verdict_before": claim_verdict_before,
        "execution_containment": {
            **REQUIREMENT,
            "required_runtime": dict(REQUIREMENT["required_runtime"]),
        },
        "scope": [SCOPE],
    }
