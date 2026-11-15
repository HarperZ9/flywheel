"""reconcile_at_center — the live loop: solo -> meeting -> crystallize -> witness against the criterion.

Two minds with different perception each perceive their own channel and propose (solo, blind to each
other); then each reconciles having seen the other's deposit (the channel carries deposits, not raw
state); the center crystallizes the candidate set; an external judge scores each candidate per
dimension; the grounding guardrail penalizes over-build; the winner is whichever scores highest under
the HUMAN's named criterion, and a Certificate naming that criterion is emitted. Fail-closed.
"""
from __future__ import annotations

from .certificate import Certificate, Verdict
from .criterion import CriterionSpec
from .grounding import grounding_penalty, unsupported_tokens

_ORACLE = "neutral-center-v1"


def reconcile_at_center(subject_views: dict[str, str], minds, criterion: CriterionSpec | None, judge,
                        dims=("novelty", "structure", "function", "completeness", "grounded")) -> Certificate:
    # --- fail-closed gates (R8) ---
    if criterion is None:
        return Certificate("(no criterion)", Verdict.UNVERIFIABLE, _ORACLE,
                           evidence=(("reason", "no criterion named — the human's seat is empty"),))
    if not subject_views or all(not v.strip() for v in subject_views.values()):
        return Certificate(f"criterion={criterion.name}", Verdict.UNVERIFIABLE, _ORACLE,
                           criterion=criterion.to_dict(),
                           evidence=(("reason", "subject has no perceptible form"),))
    if len(minds) < 2:
        return Certificate(f"criterion={criterion.name}", Verdict.UNVERIFIABLE, _ORACLE,
                           criterion=criterion.to_dict(),
                           evidence=(("reason", "a center needs two minds; got fewer"),))

    # --- solo: each mind perceives its own channel, blind to the others ---
    deposits = {}   # mind.name -> solo proposal
    for m in minds:
        view = subject_views.get(m.channel, "")
        deposits[m.name] = m.perceive_and_propose(view)

    # --- meeting: each reconciles, seeing the others' deposits ---
    candidates = dict(deposits)   # include the solos as candidates
    for m in minds:
        others = [t for n, t in deposits.items() if n != m.name]
        candidates[f"meeting:{m.name}"] = m.reconcile(subject_views.get(m.channel, ""), others)

    return witness_candidates(candidates, subject_views, criterion, judge, dims)


def witness_candidates(candidates: dict[str, str], subject_views: dict[str, str],
                       criterion: CriterionSpec, judge, dims) -> Certificate:
    """The witnessed-verdict half: judge each candidate, ground it, score under the NAMED criterion,
    pick the winner, emit a Certificate. Usable on candidates produced by ANY minds — including a LIVE
    run where the candidate texts came from real model minds (the fn boundary the adapters abstract)."""
    if not candidates:
        return Certificate(f"criterion={criterion.name}", Verdict.UNVERIFIABLE, _ORACLE,
                           criterion=criterion.to_dict(),
                           evidence=(("reason", "no candidates to witness"),))
    scores = {}
    for label, text in candidates.items():
        dim = dict(judge.score(text, subject_views, dims))
        pen = grounding_penalty(text, subject_views)
        if "grounded" in dim:
            dim["grounded"] = round(max(0.0, dim["grounded"] - pen), 6)
        weighted = criterion.score(dim)
        scores[label] = {**dim, "grounding_penalty": round(pen, 6), "weighted": weighted}

    winner = max(scores, key=lambda k: scores[k]["weighted"])
    over = sorted(unsupported_tokens(candidates[winner], subject_views))[:8]
    ev = (("winner_weighted", str(scores[winner]["weighted"])),
          ("candidates", str(len(scores))),
          ("over_build_flags", ",".join(over) if over else "none"))
    return Certificate(
        claim=f"best under criterion '{criterion.name}'", verdict=Verdict.VERIFIED, oracle=_ORACLE,
        criterion=criterion.to_dict(), scores=scores, winner=winner, evidence=ev,
    )
