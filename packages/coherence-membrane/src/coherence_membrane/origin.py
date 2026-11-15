"""origin -- a reconcile criterion composing provenance signals into ONE sound verdict.

The authenticated-contradictions gap (arXiv 2603.02378, 2026): a file can carry a VALID
C2PA "human-authored" manifest AND an "AI-generated" watermark, each passing its own
check, because the layers never consult each other. The fix is composition: map each
provenance signal (perceptual-hash drift, provenance-DAG integrity, receipt signature)
onto the Certificate lattice and take the PROVEN meet (composition.compose) -- any
denying/contradicting signal refutes the origin; all-affirm verifies it; absence
attenuates to UNVERIFIABLE. Security as a reconcile criterion: perceive the artifact's
history (an organ), judge origin here. Generic over the signal vocabulary; the shipped
drift/graph/receipt verdicts (MATCH/VALID affirm, DRIFT/BROKEN deny) are mapped here."""
from __future__ import annotations

from .certificate import Certificate, Verdict
from .composition import compose
from .reconcile import Criterion

_ORACLE = "origin-composed-v1"
_AFFIRM = {"match", "valid"}     # MATCH (drift), VALID (graph/receipt) -> affirm origin
_DENY = {"drift", "broken"}      # DRIFT (drift/receipt), BROKEN (graph) -> deny/contradict


def _to_verdict(signal) -> Verdict:
    s = str(signal).lower()
    if s in _AFFIRM:
        return Verdict.VERIFIED
    if s in _DENY:
        return Verdict.REFUTED
    return Verdict.UNVERIFIABLE


def origin_criterion() -> Criterion:
    """A Criterion composing named provenance signals into ONE origin verdict via the
    proven lattice meet. The form is an iterable of (name, signal) pairs OR a dict;
    signal is a domain verdict (MATCH/VALID affirm, DRIFT/BROKEN deny, else UNVERIFIABLE).
    REFUTED if any signal denies or contradicts; VERIFIED iff every signal affirms;
    UNVERIFIABLE if there are no signals or none are decisive. The authenticated-
    contradictions fix: uncoordinated layers become one composition-sound verdict.
    The judge is TOTAL -- malformed input (non-iterable / non-pair) degrades to
    UNVERIFIABLE, never raises; the criterion is independently sound, not merely
    safe because the reconcile spine catches exceptions. The returned certificate's
    evidence records each signal as `signal:<name> -> "<raw> -> <mapped-verdict>"`, so
    the dominating step (which signal drove the meet) is auditable from the proof."""
    def judge(signals) -> Certificate:
        try:
            pairs = list(signals.items()) if hasattr(signals, "items") else list(signals)
            if not pairs:
                return Certificate("origin (no signals)", Verdict.UNVERIFIABLE, _ORACLE,
                                   (("reason", "no provenance signals"),))
            certs = [Certificate(f"origin:{name}", _to_verdict(sig), f"provenance-{name}",
                                 (("signal", str(sig)),)) for name, sig in pairs]
            composed = compose(certs, claim="origin (composed provenance)")
            # Evidence carries each signal's raw value AND its mapped verdict, taken from
            # the SAME cert that fed the meet -- so the dominating step(s) (those whose
            # verdict equals the composed verdict) are recoverable directly from the
            # certificate: "which signal refuted origin?" No verdict logic here; the
            # verdict remains composed.verdict (the proven meet), unchanged.
            evidence = tuple((f"signal:{name}", f"{sig} -> {cert.verdict.value}")
                             for (name, sig), cert in zip(pairs, certs))
            return Certificate("origin (composed provenance)", composed.verdict, _ORACLE, evidence)
        except Exception as exc:
            return Certificate("origin (malformed signals)", Verdict.UNVERIFIABLE, _ORACLE,
                               (("reason", repr(exc)),))

    return Criterion("origin-composition", judge)
