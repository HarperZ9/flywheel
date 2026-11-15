"""PropositionalVerifierOrgan -- witnessed deductive verification of a boolean claim.

The verifier layer's first organ: the model emits a Formula (a proof obligation),
the organ returns a sound Certificate it cannot talk past. SOUNDNESS is the
contract -- an undecidable/oversized/unsupported claim is UNVERIFIABLE, never a
false verdict."""
from __future__ import annotations

from ..certificate import Verdict
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..propositional import And, Implies, Var, check_validity, is_formula, show


class PropositionalVerifierOrgan:
    name = "propositional-verifier"

    def __init__(self, max_atoms: int = 20):
        if max_atoms < 1:
            raise ValueError("max_atoms must be >= 1")
        self.max_atoms = max_atoms

    def observe(self, subject) -> list[Observation]:
        if not is_formula(subject):
            return [Observation(
                self.name, str(subject), "not a checkable formula",
                Status.UNVERIFIED,
                Provenance.witness_bytes(str(subject), b"", "low"),
                {"reason": "unsupported subject (expected a propositional Formula)"},
            )]
        try:
            cert = check_validity(subject, max_atoms=self.max_atoms)
            claim = show(subject)
        except (TypeError, RecursionError) as exc:   # malformed AST -> fail-closed, never raise
            return [Observation(
                self.name, str(subject), "malformed formula",
                Status.UNVERIFIED,
                Provenance.witness_bytes(str(subject), b"", "low"),
                {"reason": f"malformed: {exc}"},
            )]
        decided = cert.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
        identity = sha256_hex(claim.encode())
        return [Observation(
            self.name, claim, f"claim {cert.verdict.value}",
            Status.PASS if decided else Status.UNVERIFIED,
            Provenance.witness_bytes(claim, claim.encode(), "high" if decided else "low"),
            {
                "oracle": cert.oracle,
                "verdict": cert.verdict.value,
                "claim": claim,
                "evidence": [list(p) for p in cert.evidence],
                "identity_sha256": identity,
            },
        )]

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        A, B = Var("A"), Var("B")
        mp = Implies(And(A, Implies(A, B)), B)
        good = self.observe(mp)[0]
        checks.append(Check(
            "verifies a valid claim (modus ponens)",
            good.status == Status.PASS and good.data.get("verdict") == "verified",
            good.data.get("claim", ""),
        ))
        bad = self.observe(Implies(A, B))[0]
        checks.append(Check(
            "refutes a false claim with a counterexample",
            bad.data.get("verdict") == "refuted"
            and ["counterexample:A", "1"] in bad.data.get("evidence", []),
            str(bad.data.get("evidence", "")),
        ))
        checks.append(Check(
            "provenance digest full-width",
            good.provenance.digest.startswith("sha256:")
            and len(good.provenance.digest) == len("sha256:") + 64,
            good.provenance.digest,
        ))
        nf = self.observe("not a formula")[0]
        checks.append(Check(
            "fail-closed on non-formula",
            nf.status == Status.UNVERIFIED,
            nf.data.get("reason", ""),
        ))
        return SelftestResult(self.name, checks)
