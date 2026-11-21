"""run_verdict.py -- a re-derivable per-run verdict from the witnessed ledger.

flywheel seals each agent run (including each subagent in a swarm) with a compact
verdict a stranger can recompute from the ledger alone: the hash chain is intact,
the trajectory did not tamper with its own grader, and any acceptance check that
ran passed. The swarm quorum counts these verdicts instead of a bare exit code, so
fan-in attests verification, not a body count. Zero dependency beyond the harness.
"""
from __future__ import annotations

from .integrity import integrity_report, trajectory_integrity

VERDICT_SCHEMA = "flywheel.run-verdict/v1"


def seal_verdict(ledger, result: dict) -> dict:
    """The verdict for a finished run. `result` carries tests_pass_trusted, which
    flywheel already couples with integrity-clean. Re-derivable: every field except
    the tests flag recomputes from the ledger, and the child's ledger travels with
    its result so a verifier can recompute the tests flag too. `accepted` is the one
    bit the quorum counts: chain intact, grader untampered, and no failing check."""
    flags = trajectory_integrity(ledger)
    integrity_clean = not flags
    chain_intact = ledger.verify()
    tests = result.get("tests_pass_trusted")      # True / False / None (no check ran)
    accepted = bool(chain_intact and integrity_clean and tests is not False)
    return {
        "schema": VERDICT_SCHEMA,
        "accepted": accepted,
        "chain_intact": chain_intact,
        "integrity_clean": integrity_clean,
        "tests_pass_trusted": tests,
        "chain_head": ledger.checkpoint(),
        "integrity_sha256": integrity_report(flags)["flags_sha256"],
    }


def seal_valve_verdict(ledger, result: dict, *, actor_id: str = "agent", policy=None) -> dict:
    """Couple the re-derivable run verdict with the reseating-valve protocol.

    Tampered graders or broken hash chains trip RUPTURE; intact-chain failures or
    honest abstentions vent cleanly as VENTED; accepted runs seal as VERIFIED.
    """
    from .reseating_valve import ValveOutcome, evaluate_valve
    verdict = seal_verdict(ledger, result)
    outcome = ValveOutcome(
        actor_id=actor_id,
        verified=verdict["accepted"],
        honest_exit=bool(verdict["chain_intact"] and verdict["integrity_clean"] and not verdict["accepted"]),
        tampered=not verdict["integrity_clean"],
        witness_bypassed=not verdict["chain_intact"],
        reason="accepted" if verdict["accepted"] else ("integrity_or_chain_violation" if not (verdict["chain_intact"] and verdict["integrity_clean"]) else "honest_exit"),
    )
    verdict["valve"] = evaluate_valve(outcome, policy=policy)
    return verdict
