"""novelty -- a reconcile criterion for grounded creative novelty.

The Cell *Patterns* result (Dec 2025): naive generate->describe->regenerate loops
collapse to a handful of generic motifs ("visual elevator music") because the critic
is an ungrounded caption. The cure is a SPECIFIC, grounded criterion: judge a work's
perceived signature against the WITNESSED CORPUS of prior work -- VERIFIED-novel only
if it is far from everything seen, REFUTED-derivative if it collapses onto something.
This is the creativity surface as a reconcile criterion (perceive the shape with an
organ; judge novelty here). Generic over the signature type + distance metric -- a
perceptual hash + hamming is the shipped instantiation; the caller injects both, so
this module stays uncoupled from any particular organ.

Scope: with a perceptual-hash distance this is "not-derivative in the PERCEIVED
signature", not deep-semantic novelty -- a 64-bit dHash sees low-frequency structure,
not meaning, so two semantically distinct works can share a coarse signature."""
from __future__ import annotations

from .certificate import Certificate, Verdict
from .reconcile import Criterion

_ORACLE = "novelty-vs-corpus-v1"


def novelty_criterion(corpus, *, distance, min_distance) -> Criterion:
    """A Criterion judging a signature NOVEL iff its minimum distance to every corpus
    signature is >= min_distance. VERIFIED-novel / REFUTED-derivative / UNVERIFIABLE
    (empty corpus, or a distance that fails to compute). `distance(a, b)` is a
    caller-supplied metric over signatures (e.g. hamming over perceptual hashes);
    `corpus` is the witnessed set of prior-work signatures. `min_distance` must be a
    real number > 0 -- a degenerate threshold is a construction-time programmer error
    (0 would admit exact duplicates as novel, disabling the anti-collapse guarantee),
    so it is raised loudly HERE; `judge` itself never raises on a valid criterion."""
    if not isinstance(min_distance, (int, float)) or min_distance != min_distance:  # reject None/non-real/NaN
        raise ValueError(f"min_distance must be a real number, got {min_distance!r}")
    if min_distance <= 0:
        raise ValueError("min_distance must be > 0 (0 admits exact duplicates as novel -- disables anti-collapse)")
    corpus = tuple(corpus)

    def judge(signature) -> Certificate:
        if not corpus:
            return Certificate("novelty (empty corpus)", Verdict.UNVERIFIABLE, _ORACLE,
                               (("reason", "no corpus to compare against"),))
        try:
            nearest = min(distance(signature, c) for c in corpus)
        except Exception as exc:
            return Certificate("novelty", Verdict.UNVERIFIABLE, _ORACLE, (("reason", repr(exc)),))
        verdict = Verdict.VERIFIED if nearest >= min_distance else Verdict.REFUTED
        claim = f"novel: nearest-corpus-distance {nearest!r} >= {min_distance!r}"
        return Certificate(claim, verdict, _ORACLE,
                           (("nearest_distance", repr(nearest)),
                            ("min_distance", repr(min_distance)),
                            ("corpus_size", str(len(corpus)))))

    return Criterion("novelty-vs-corpus", judge)
