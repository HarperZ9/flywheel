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
