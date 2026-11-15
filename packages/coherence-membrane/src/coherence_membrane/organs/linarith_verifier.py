"""LinearArithmeticVerifierOrgan -- witnessed proof-carrying QF-LRA verification.

Observes a feasibility or entailment claim over linear constraints and emits a
Certificate whose verdict was confirmed by an independent witness checker (model or
Farkas). Foreign subject -> []; fail-closed (never raises)."""
from __future__ import annotations

from dataclasses import dataclass

from ..certificate import Verdict
from ..linarith import LinearConstraint, check_entails, check_feasible, constraint
from ..lra_dpll import check_valid
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult


@dataclass(frozen=True)
class FeasibilityClaim:
    claim: str
    constraints: tuple


@dataclass(frozen=True)
class EntailmentClaim:
    claim: str
    premises: tuple
    conclusion: LinearConstraint


@dataclass(frozen=True)
class ValidityClaim:
    claim: str
    formula: object


class LinearArithmeticVerifierOrgan:
    name = "linear-arithmetic-verifier"

    def observe(self, subject) -> list:
        if isinstance(subject, FeasibilityClaim):
            run = lambda: check_feasible(list(subject.constraints))
        elif isinstance(subject, EntailmentClaim):
            run = lambda: check_entails(list(subject.premises), subject.conclusion)
        elif isinstance(subject, ValidityClaim):
            run = lambda: check_valid(subject.formula)
        else:
            return []
        claim = str(subject.claim)   # coerce once: the organ never raises, even on a malformed claim
        try:
            cert = run()
        except Exception as exc:   # fail-closed
            return [self._obs(claim, "unverifiable", Status.UNVERIFIED, "low",
                              {"reason": f"malformed: {exc}"})]
        decided = cert.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
        return [self._obs(
            claim, cert.verdict.value,
            Status.PASS if decided else Status.UNVERIFIED,
            "high" if decided else "low",
            {"oracle": cert.oracle, "verdict": cert.verdict.value, "claim": claim,
             "evidence": [list(p) for p in cert.evidence],
             "identity_sha256": sha256_hex(claim.encode())},
        )]

    def _obs(self, claim, verdict, status, conf, data):
        return Observation(self.name, claim, f"claim {verdict}", status,
                           Provenance.witness_bytes(claim, claim.encode(), conf), data)

    def selftest(self) -> SelftestResult:
        checks = []
        prem = (constraint({"x": 1}, ">=", 0), constraint({"y": 1}, ">=", 0))
        good = self.observe(EntailmentClaim(
            "x,y>=0 => x+y>=0", prem, constraint({"x": 1, "y": 1}, ">=", 0)))[0]
        checks.append(Check("verifies a valid entailment (Farkas-checked)",
                            good.data.get("verdict") == "verified", good.data.get("claim", "")))
        bad = self.observe(FeasibilityClaim(
            "x>=1 and x<=0", (constraint({"x": 1}, ">=", 1), constraint({"x": 1}, "<=", 0))))[0]
        checks.append(Check("refutes an infeasible system (Farkas-checked)",
                            bad.data.get("verdict") == "refuted", str(bad.data.get("evidence", ""))))
        checks.append(Check("provenance digest full-width",
                            good.provenance.digest.startswith("sha256:")
                            and len(good.provenance.digest) == len("sha256:") + 64,
                            good.provenance.digest))
        checks.append(Check("ignores a foreign subject", self.observe("nope") == [], "[]"))
        return SelftestResult(self.name, checks)
