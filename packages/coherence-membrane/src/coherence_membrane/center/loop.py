"""reconcile_at_center -- the neutral center, emitting the spine's own Certificate.

Two minds with different perception perceive their own channel and propose (solo, blind); then each
reconciles having seen the other's deposit; the center crystallizes the candidate set; an external
judge scores each per dimension; a grounding guardrail penalizes over-build; the winner is whichever
scores highest under the HUMAN's named criterion. The verdict is carried by the project's own
`Certificate` (the spine contract) -- the criterion, per-candidate scores, and winner ride in its
`evidence`, so a center verdict is re-checkable exactly like any other reconcile. Fail-closed.
"""
from __future__ import annotations
import json

from ..certificate import Certificate, Verdict
from .criterion import CriterionSpec
from .grounding import grounding_penalty, unsupported_tokens
from .judge import DIMENSIONS

_ORACLE = "neutral-center-v1"


def _unverifiable(reason: str, criterion: CriterionSpec | None) -> Certificate:
    ev = (("reason", reason),)
    if criterion is not None:
        ev = (("criterion", criterion.name),) + ev
    return Certificate("(center: undecidable)", Verdict.UNVERIFIABLE, _ORACLE, ev)


def witness_candidates(candidates: dict[str, str], subject_views: dict[str, str],
                       criterion: CriterionSpec, judge, dims=DIMENSIONS) -> Certificate:
    """Judge each candidate, ground it, score under the NAMED criterion, pick the winner, emit a
    spine Certificate. Usable on candidates from ANY minds (including a live run whose candidate
    texts came from real models -- the fn boundary the adapters abstract)."""
    if not candidates:
        return _unverifiable("no candidates to witness", criterion)
    scores = {}
    for label, text in candidates.items():
        dim = dict(judge.score(text, subject_views, dims))
        pen = grounding_penalty(text, subject_views)
        if "grounded" in dim:
            dim["grounded"] = round(max(0.0, dim["grounded"] - pen), 6)
        scores[label] = {**dim, "grounding_penalty": round(pen, 6), "weighted": criterion.score(dim)}
    winner = max(scores, key=lambda k: scores[k]["weighted"])
    over = sorted(unsupported_tokens(candidates[winner], subject_views))[:8]
    evidence = (
        ("criterion", criterion.name),
        ("criterion_dims", json.dumps(criterion.normalized().dims)),
        ("winner", winner),
        ("winner_weighted", str(scores[winner]["weighted"])),
        ("scores", json.dumps(scores)),
        ("over_build_flags", ",".join(over) if over else "none"),
    )
    return Certificate(f"best under criterion '{criterion.name}'", Verdict.VERIFIED, _ORACLE, evidence)


def reconcile_at_center(subject_views: dict[str, str], minds, criterion: CriterionSpec | None, judge,
                        dims=DIMENSIONS) -> Certificate:
    if criterion is None:
        return _unverifiable("no criterion named -- the human's seat is empty", None)
    if not subject_views or all(not v.strip() for v in subject_views.values()):
        return _unverifiable("subject has no perceptible form", criterion)
    if len(minds) < 2:
        return _unverifiable("a center needs two minds; got fewer", criterion)

    deposits = {m.name: m.perceive_and_propose(subject_views.get(m.channel, "")) for m in minds}
    candidates = dict(deposits)
    for m in minds:
        others = [t for n, t in deposits.items() if n != m.name]
        candidates[f"meeting:{m.name}"] = m.reconcile(subject_views.get(m.channel, ""), others)
    return witness_candidates(candidates, subject_views, criterion, judge, dims)


# --- accessors: read the structured verdict back out of a center Certificate -------------------
def winner_of(cert: Certificate) -> str | None:
    return dict(cert.evidence).get("winner")


def scores_of(cert: Certificate) -> dict:
    return json.loads(dict(cert.evidence).get("scores", "{}"))


def criterion_of(cert: Certificate) -> str | None:
    return dict(cert.evidence).get("criterion")
