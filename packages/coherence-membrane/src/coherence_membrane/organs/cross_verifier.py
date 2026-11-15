"""CrossCheckVerifierOrgan -- witnessed tier-3 cross-checked verification.

The model emits a Formula; the organ runs independent native deciders (DPLL +
brute-force truth-table) and returns a Certificate only when they AGREE. A
disagreement is surfaced as UNVERIFIABLE with the discrepancy -- a caught bug, not a
trusted single-solver verdict. Trust-minimization: better than depending on one
external oracle."""
from __future__ import annotations

from ..certificate import Certificate, Verdict
from ..crosscheck import Method, cross_check_validity
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..propositional import And, Implies, Not, Or, Var, check_validity, is_formula, show


class CrossCheckVerifierOrgan:
    name = "cross-check-verifier"

    def __init__(self, max_atoms: int = 16):
        if max_atoms < 1:
            raise ValueError("max_atoms must be >= 1")
        self.max_atoms = max_atoms

    def observe(self, subject) -> list[Observation]:
        if not is_formula(subject):
            return []
        try:
            cert = cross_check_validity(subject, max_atoms=self.max_atoms)
            claim = show(subject)
        except Exception as exc:   # fail-closed: never raise out of an organ
            return [self._obs(str(subject), "unverifiable", Status.UNVERIFIED, "low",
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

    def _obs(self, claim: str, verdict: str, status: Status, conf: str, data: dict) -> Observation:
        return Observation(self.name, claim, f"claim {verdict}", status,
                           Provenance.witness_bytes(claim, claim.encode(), conf), data)

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        A, B = Var("A"), Var("B")
        mp = Implies(And(A, Implies(A, B)), B)
        good = self.observe(mp)[0]
        checks.append(Check("verifies a valid claim by consensus (dpll + truth-table)",
                            good.status == Status.PASS and good.data.get("verdict") == "verified",
                            str(good.data.get("evidence", ""))))
        bad = self.observe(Implies(A, B))[0]
        checks.append(Check("refutes a non-tautology by consensus",
                            bad.data.get("verdict") == "refuted", str(bad.data.get("evidence", ""))))
        checks.append(Check("provenance digest full-width",
                            good.provenance.digest.startswith("sha256:")
                            and len(good.provenance.digest) == len("sha256:") + 64,
                            good.provenance.digest))
        # the catch: a lying method must force UNVERIFIABLE + discrepancy, never a false pass
        liar = Method("liar", lambda f, *, max_atoms=16: Certificate(show(f), Verdict.REFUTED, "liar-v0"))
        caught = cross_check_validity(Or(A, Not(A)), methods=(Method("dpll", check_validity), liar))
        checks.append(Check("catches a disagreeing method (discrepancy -> UNVERIFIABLE)",
                            caught.verdict is Verdict.UNVERIFIABLE
                            and any(k == "discrepancy" for k, _ in caught.evidence),
                            str(caught.evidence)))
        checks.append(Check("ignores a foreign subject", self.observe("nope") == [], "[]"))
        return SelftestResult(self.name, checks)
