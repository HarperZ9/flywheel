"""DistributionVerifierOrgan -- witnessed distribution-invariant verification (tier-2).

Wraps the distribution-invariant oracle as an inert, fail-closed Observation: a
DistributionClaim is checked (normalization + claimed moments); a non-claim subject
returns []; malformed input degrades to UNVERIFIED, never raises."""
from __future__ import annotations

from ..certificate import Verdict
from ..distribution import Distribution
from ..distribution_oracle import DistributionClaim, check_distribution
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult


class DistributionVerifierOrgan:
    name = "distribution-verifier"

    def observe(self, subject) -> list[Observation]:
        if not isinstance(subject, DistributionClaim):
            return []
        try:
            cert = check_distribution(subject.dist, mean=subject.mean,
                                      variance=subject.variance, rel_tol=subject.rel_tol)
        except Exception as exc:   # fail-closed
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
        coin = Distribution(((0.0, 0.5), (1.0, 0.5)))
        good = self.observe(DistributionClaim("fair coin", coin, mean=0.5, variance=0.25))[0]
        checks.append(Check("verifies a normalized pmf with correct moments",
                            good.data.get("verdict") == "verified", good.data.get("claim", "")))
        bad = self.observe(DistributionClaim(
            "unnormalized", Distribution(((0.0, 0.4), (1.0, 0.4)))))[0]
        checks.append(Check("refutes an unnormalized pmf",
                            bad.data.get("verdict") == "refuted", str(bad.data.get("evidence", ""))))
        checks.append(Check("provenance digest full-width",
                            good.provenance.digest.startswith("sha256:")
                            and len(good.provenance.digest) == len("sha256:") + 64,
                            good.provenance.digest))
        checks.append(Check("ignores a foreign subject",
                            self.observe("not a claim") == [], "[]"))
        return SelftestResult(self.name, checks)
