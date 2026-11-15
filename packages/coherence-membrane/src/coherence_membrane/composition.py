"""Certificate composition -- multi-step arguments via the PROVEN verdict meet.

A multi-step argument holds only if every step does. Rather than hand-roll three-
valued conjunction logic (a place soundness bugs hide), this reuses the machine-
checked DRIFT_LATTICE meet (lattice.py): VERIFIED<->MATCH (top, composes away),
REFUTED<->DRIFT (bottom, absorbing -- a false step makes the whole false),
UNVERIFIABLE in the middle (attenuates). The meet is proven commutative / associative
/ idempotent / monotone and attenuating, so composition can never launder worse steps
into a better verdict -- a theorem, not a comment."""
from __future__ import annotations

from typing import Iterable

from .certificate import Certificate, Verdict
from .lattice import DRIFT_LATTICE
from .phash import DRIFT as _L_DRIFT, MATCH as _L_MATCH, UNVERIFIABLE as _L_UNVERIFIABLE

_V2L = {Verdict.VERIFIED: _L_MATCH, Verdict.REFUTED: _L_DRIFT, Verdict.UNVERIFIABLE: _L_UNVERIFIABLE}
_L2V = {_L_MATCH: Verdict.VERIFIED, _L_DRIFT: Verdict.REFUTED, _L_UNVERIFIABLE: Verdict.UNVERIFIABLE}


def meet_verdicts(verdicts: Iterable[Verdict]) -> Verdict:
    """Fail-closed conjunction of verdicts via the proven DRIFT_LATTICE meet: REFUTED
    absorbs, UNVERIFIABLE attenuates, all-VERIFIED -> VERIFIED. Empty -> the meet
    identity (VERIFIED); callers needing fail-closed-on-empty guard separately (see
    compose)."""
    return _L2V[DRIFT_LATTICE.fold_meet(_V2L[v] for v in verdicts)]


def quorum(certs: Iterable[Certificate], *, claim: str | None = None,
           threshold: float = 0.5) -> Certificate:
    """Robust CONSENSUS over N INDEPENDENT judges of the SAME claim -- the readout-gate.

    Distinct from compose(): compose is the conjunctive meet over the STEPS of one argument
    (a single REFUTED absorbs). quorum is a VOTE among independent judges of one claim, and
    it caps any single voice's influence (aperture-sim A1 -- a robust aggregator must govern
    the OUTPUT, so no lone loud/unbounded source can flip the verdict). A decided verdict is
    returned ONLY if it wins a strict supermajority of the WHOLE panel; the denominator is
    the total judge count, so abstentions (UNVERIFIABLE) and dissent both count against
    quorum. Consequences (threshold >= 0.5):
      * one false VERIFIED among many cannot reach the supermajority -> UNVERIFIABLE, not VERIFIED;
      * one loud REFUTED cannot veto a true claim (it neither reaches a REFUTED supermajority
        nor blocks a VERIFIED one beyond its single vote) -> the panel still decides;
      * no quorum either way -> UNVERIFIABLE (fail-closed); empty -> UNVERIFIABLE.
    threshold is the fraction of the FULL panel a verdict must exceed (default 0.5 = strict
    majority; pass 2/3 for Byzantine-style robustness tolerating up to ~1/3 bad judges).
    Oracle 'quorum-v1'; the full tally + threshold are carried in evidence (auditable)."""
    certs = list(certs)
    summary = claim if claim is not None else (
        " ; ".join(c.claim for c in certs) if certs else "(empty)")
    n = len(certs)
    if n == 0:
        return Certificate(summary, Verdict.UNVERIFIABLE, "quorum-v1",
                           (("reason", "no judges"), ("threshold", repr(threshold))))
    tally = {Verdict.VERIFIED: 0, Verdict.REFUTED: 0, Verdict.UNVERIFIABLE: 0}
    for c in certs:
        tally[c.verdict] = tally.get(c.verdict, 0) + 1
    need = int(threshold * n) + 1   # strict supermajority of the FULL panel
    if tally[Verdict.VERIFIED] >= need:
        verdict = Verdict.VERIFIED
    elif tally[Verdict.REFUTED] >= need:
        verdict = Verdict.REFUTED
    else:
        verdict = Verdict.UNVERIFIABLE
    evidence = (("verified", str(tally[Verdict.VERIFIED])),
                ("refuted", str(tally[Verdict.REFUTED])),
                ("unverifiable", str(tally[Verdict.UNVERIFIABLE])),
                ("judges", str(n)), ("need", str(need)), ("threshold", repr(threshold)))
    return Certificate(summary, verdict, "quorum-v1", evidence)


def compose(certs: Iterable[Certificate], *, claim: str | None = None) -> Certificate:
    """Compose a multi-step argument into one Certificate: the whole holds only if
    every step does. Verdict = the proven meet over the steps. Empty -> UNVERIFIABLE
    (fail-closed: nothing was verified), NOT vacuous VERIFIED. Oracle 'composed-v1';
    each step's (oracle, verdict) is carried in evidence so the dominating step is
    auditable."""
    certs = list(certs)
    if not certs:
        return Certificate(claim or "(empty)", Verdict.UNVERIFIABLE, "composed-v1",
                           (("reason", "no steps to compose"),))
    verdict = meet_verdicts(c.verdict for c in certs)
    summary = claim if claim is not None else " & ".join(c.claim for c in certs)
    evidence = tuple((f"step{i}:{c.oracle}", c.verdict.value) for i, c in enumerate(certs))
    return Certificate(summary, verdict, "composed-v1", evidence)
