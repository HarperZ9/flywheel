"""receipt_scope.py -- what a receipt covers, derived from its own contents.

A v5 receipt carries `scope`: codes for the properties its own fields establish,
each present only when the field that earns it holds. Nobody has to remember to
write them, and a reader can test for a code rather than parse a sentence.

v3 and v4 receipts carried the older `does_not_prove` list of `NOT_PROVES_*`
codes. Their bytes are sealed, so `legacy_limits` keeps that vocabulary exactly
and `Receipt.from_dict` checks an old receipt against it.
"""
from __future__ import annotations

# Always present: the verdict is bound to the named checker's source digest and
# to this candidate's digest, which is the one property every receipt has.
CHECKED_BY_NAMED_CHECKER = "CHECKED_BY_NAMED_CHECKER"


def derived_scope(r) -> list[str]:
    """The v5 scope codes for receipt `r`, in a fixed order."""
    out = [CHECKED_BY_NAMED_CHECKER]
    if r.oracle_qa_card_hash:
        out.append("VERIFIER_QA_CARD_BOUND")
    if r.held_out_agreement == "AGREE":
        out.append("HELD_OUT_CHECKER_AGREES")
    if r.coverage.get("predicate_exact", False):
        out.append("PREDICATE_EXACT")
    if r.coverage.get("search_space_enumerated", False):
        out.append("SEARCH_SPACE_ENUMERATED")
    if r.novelty_verdict != "UNKNOWN":
        out.append("NOVELTY_CHECKED")
    if not r.executes_candidate_code:
        out.append("CHECKED_WITHOUT_RUNNING_CANDIDATE")
    if r.base_weights_digest:
        out.append("WEIGHTS_PINNED")
    if not r.denominator.filter_is_learned:
        out.append("TASK_SELECTION_FIXED")
    if r.budget.declared:
        out.append("COST_BOUNDED")
    if not r.budget.exhausted:
        # A result reached at the ceiling says as much about the ceiling as
        # about the candidate, so only a result below it earns this code.
        out.append("WITHIN_BUDGET")
    if not r.denominator.retries:
        out.append("FIRST_ATTEMPT")
    if not r.denominator.oracle_feedback_visible:
        out.append("FOUND_WITHOUT_ORACLE_FEEDBACK")
    if r.graded_score is not None and r.graded_score.trials >= 2:
        out.append("SCORE_REPEATED")
    if r.input_tier_multiset:
        out.append("TIER_CAPPED_BY_INPUTS")
    out.extend(r.extra_scope)
    return out


def legacy_limits(r) -> list[str]:
    """The v3/v4 list, byte for byte as those versions derived it."""
    out = ["NOT_PROVES_PUBLICATION_COMPLETENESS"]
    if not r.oracle_qa_card_hash:
        out.append("NOT_PROVES_VERIFIER_SOUNDNESS")
    if r.held_out_agreement != "AGREE":
        out.append("NOT_PROVES_RESISTANCE_TO_ORACLE_GAMING")
    if not r.coverage.get("predicate_exact", False):
        out.append("NOT_PROVES_EXACTNESS")
    if not r.coverage.get("search_space_enumerated", False):
        out.append("NOT_PROVES_COMPLETE_ENUMERATION")
    if r.novelty_verdict == "UNKNOWN":
        out.append("NOT_PROVES_NOVELTY")
    if r.executes_candidate_code:
        out.append("NOT_PROVES_CONTAINMENT")
    if not r.base_weights_digest:
        out.append("NOT_PROVES_WHICH_WEIGHTS")
    if r.denominator.filter_is_learned:
        out.append("NOT_PROVES_UNBIASED_TASK_SELECTION")
    if not r.budget.declared:
        out.append("NOT_PROVES_COST_BOUNDED")
    if r.budget.exhausted:
        out.append("NOT_PROVES_UNCONSTRAINED_BY_BUDGET")
    if r.denominator.retries:
        out.append("NOT_PROVES_FIRST_ATTEMPT_SUCCESS")
    if r.denominator.oracle_feedback_visible:
        out.append("NOT_PROVES_FOUND_WITHOUT_ORACLE_FEEDBACK")
    if r.graded_score is not None and r.graded_score.trials < 2:
        out.append("NOT_PROVES_SCORE_STABILITY")
    if r.input_tier_multiset:
        out.append("TIER_LIMITED_BY_INPUT")
    out.extend(r.extra_scope)
    return out
