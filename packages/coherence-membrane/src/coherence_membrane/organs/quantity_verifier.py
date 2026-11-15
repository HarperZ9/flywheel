"""QuantityVerifierOrgan -- witnessed dimensional/numeric verification (tier-2).

Wraps the dimensional-invariant oracle as an inert, fail-closed Observation: a
QuantityClaim is checked; a non-claim subject is not this organ's modality (returns
[]); malformed input degrades to UNVERIFIED, never raises."""
from __future__ import annotations

from ..certificate import Verdict
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..quantity import DIMENSIONLESS, MASS, Quantity
from ..quantity_oracle import QuantityClaim, check_equation


class QuantityVerifierOrgan:
    name = "quantity-verifier"

    def observe(self, subject) -> list[Observation]:
        if not isinstance(subject, QuantityClaim):
            return []
        try:
            cert = check_equation(subject.lhs, subject.rhs, rel_tol=subject.rel_tol)
        except Exception as exc:   # fail-closed: never raise out of an organ
            return [self._obs(subject.claim, "unverifiable", Status.UNVERIFIED, "low",
                              {"reason": f"malformed: {exc}"})]
        decided = cert.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
        return [self._obs(
            subject.claim, cert.verdict.value,
            Status.PASS if decided else Status.UNVERIFIED,
            "high" if decided else "low",
            {"oracle": cert.oracle, "verdict": cert.verdict.value, "claim": subject.claim,
             "evidence": [list(p) for p in cert.evidence],
             "identity_sha256": sha256_hex(subject.claim.encode())},
        )]

    def _obs(self, claim: str, verdict: str, status: Status, conf: str, data: dict) -> Observation:
        return Observation(
            self.name, claim, f"claim {verdict}", status,
            Provenance.witness_bytes(claim, claim.encode(), conf), data)

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        good = self.observe(QuantityClaim(
            "2kg == 2kg", Quantity(2.0, MASS), Quantity(2.0, MASS)))[0]
        checks.append(Check("verifies a true equation",
                            good.data.get("verdict") == "verified", good.data.get("claim", "")))
        bad = self.observe(QuantityClaim(
            "mass == dimensionless", Quantity(2.0, MASS), Quantity(2.0, DIMENSIONLESS)))[0]
        checks.append(Check("refutes a dimension mismatch",
                            bad.data.get("verdict") == "refuted", str(bad.data.get("evidence", ""))))
        checks.append(Check("provenance digest full-width",
                            good.provenance.digest.startswith("sha256:")
                            and len(good.provenance.digest) == len("sha256:") + 64,
                            good.provenance.digest))
        checks.append(Check("ignores a foreign subject",
                            self.observe("not a claim") == [], "[]"))
        return SelftestResult(self.name, checks)
