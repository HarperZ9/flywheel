"""pair_voiding.py -- pair-voiding extensions and Holm-Bonferroni, report layer.

Companion to ``paired_comparison`` (B4) and ``inner_call_budget_check`` (B8):
the same two-arm attempt shape, the same house idiom (structured refusals for
what cannot be shown, ValueError for caller malformation), and the same rule
that a pair is the unit of exclusion. Voiding one side of a pair is a rigging
lever, so every exclusion here voids BOTH attempts and says so on the row.

Two void classes, from the design of record:

- model_drift: model_observed differs across the arms of a (task, rep) pair.
  The pinned-reference and alias-table check is a run-level stop rule and
  lives upstream; this module holds the cross-arm equality the report needs.
- envelope_malformed: an attempt classified execution_state="malformed" (the
  single-line JSON envelope contract, ``cross_harness_manifest._prompt_text``,
  and the executor's malformed classification in ``cross_harness_executor``).
  Per-arm envelope-compliance rates are computed over ALL attempts and
  surfaced separately from the pair exclusions.

Holm-Bonferroni lives here, at the report layer only, never in the statistics
primitives: one preregistered primary comparison is exempt, every additional
comparison in the declared family is step-down adjusted, and raw and adjusted
p are both emitted. Stdlib only. Deterministic.
"""
from __future__ import annotations

VOIDING_SCHEMA = "flywheel.pair-voiding/v1"

HOLM_SCHEMA = "flywheel.holm-bonferroni/v1"

_EXECUTION_STATES = {"not_started", "unavailable", "launched", "returned",
                     "timeout", "malformed", "internal_error"}

_VOIDING_DOES_NOT_PROVE = [
    "NOT_PROVES_MODEL_IDENTITY: model_observed is attested from provider "
    "events, never from weights; equal strings do not rule out a "
    "provider-side silent swap.",
    "NOT_PROVES_PIN_CONFORMANCE: this check shows cross-arm equality only; "
    "match against the preregistered model reference and alias table is a "
    "run-level stop rule, not a report cell.",
]

_HOLM_DOES_NOT_PROVE = [
    "NOT_PROVES_FAMILY_COMPLETENESS: the adjustment controls family-wise "
    "error over the declared family only; a comparison left out of the "
    "family is uncorrected by construction.",
]


def _void_index(arm: dict) -> tuple[str, dict]:
    """Validate one arm and index (model_observed, execution_state) by pair."""
    name = arm.get("arm")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("an arm needs a nonempty 'arm' name")
    attempts = arm.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError(f"arm {name!r} needs a nonempty 'attempts' list")
    index: dict = {}
    for row in attempts:
        task = row.get("task_id")
        rep = row.get("repetition")
        model = row.get("model_observed")
        state = row.get("execution_state")
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"arm {name!r}: attempt without a task_id")
        if type(rep) is not int or rep < 0:
            raise ValueError(
                f"arm {name!r} task {task!r}: repetition must be a "
                "nonnegative integer")
        if not isinstance(model, str):
            raise ValueError(
                f"arm {name!r} task {task!r} rep {rep}: model_observed must "
                "be a string (empty when unobserved), got "
                f"{type(model).__name__}")
        if state not in _EXECUTION_STATES:
            raise ValueError(
                f"arm {name!r} task {task!r} rep {rep}: execution_state "
                f"{state!r} is not a known executor state")
        if (task, rep) in index:
            raise ValueError(
                f"arm {name!r}: duplicate attempt for task {task!r} rep {rep}")
        index[(task, rep)] = (model, state)
    return name, index


def _envelope_compliance(name: str, index: dict) -> dict:
    """Per-arm envelope-compliance rate over ALL of that arm's attempts."""
    total = len(index)
    malformed = sum(1 for _, state in index.values() if state == "malformed")
    return {"arm": name, "attempts": total, "malformed": malformed,
            "compliant": total - malformed,
            "rate": round((total - malformed) / total, 6),
            "definition": ("attempts not classified execution_state="
                           "'malformed' / all attempts, this arm")}


def _exclusion(key: tuple, a_row: tuple, b_row: tuple, name_a: str,
               name_b: str) -> dict | None:
    """One exclusion row for the pair, or None when the pair is admissible.

    Precedence: envelope_malformed, then model_observed_unrecorded, then
    model_drift; one named reason per voided pair. Every exclusion voids both
    attempts, and the row carries both arms' values so it is re-inspectable.
    """
    task, rep = key
    (a_model, a_state), (b_model, b_state) = a_row, b_row
    row = {"task_id": task, "repetition": rep, "voids": [name_a, name_b],
           "a_model_observed": a_model, "b_model_observed": b_model,
           "a_execution_state": a_state, "b_execution_state": b_state}
    malformed = [name for name, state in
                 ((name_a, a_state), (name_b, b_state)) if state == "malformed"]
    if malformed:
        return {**row, "reason": "envelope_malformed",
                "detail": (f"arm(s) {malformed} returned an envelope-"
                           "malformed attempt; the whole pair is void, "
                           "never one side")}
    unrecorded = [name for name, model in
                  ((name_a, a_model), (name_b, b_model)) if not model]
    if unrecorded:
        return {**row, "reason": "model_observed_unrecorded",
                "detail": (f"arm(s) {unrecorded} carry no model_observed; "
                           "cross-arm model equality cannot be shown, so "
                           "the whole pair is void")}
    if a_model != b_model:
        return {**row, "reason": "model_drift",
                "detail": (f"{name_a} observed {a_model!r} while {name_b} "
                           f"observed {b_model!r}; the pair no longer holds "
                           "the model constant and is void on both sides")}
    return None


def pair_voiding_check(arm_a: dict, arm_b: dict) -> dict:
    """Void pairs for model drift or envelope malformation, both sides always.

    Each arm is ``{"arm": name, "attempts": [{"task_id", "repetition",
    "model_observed", "execution_state"}, ...]}``. Every exclusion names its
    reason and voids BOTH attempts of the pair. Per-arm envelope-compliance
    rates ride on the result whether or not pairing succeeds, since they are
    per-arm statistics. Unequal task or repetition sets refuse the pairing
    part of the check because pairing is undefined; malformed input raises.
    """
    name_a, a_index = _void_index(arm_a)
    name_b, b_index = _void_index(arm_b)
    base = {"schema": VOIDING_SCHEMA, "statistic": "pair_voiding_check",
            "arm_a": name_a, "arm_b": name_b,
            "envelope_compliance": [_envelope_compliance(name_a, a_index),
                                    _envelope_compliance(name_b, b_index)]}
    if set(a_index) != set(b_index):
        reason = ("unequal_task_sets"
                  if {t for t, _ in a_index} != {t for t, _ in b_index}
                  else "unequal_repetition_sets")
        out = dict(base)
        out["refused"] = {
            "reason": reason,
            "detail": ("the arms cover different (task, repetition) pairs, "
                       "so pair-level voiding is undefined; per-arm "
                       "envelope-compliance rates still stand")}
        return out
    excluded = [row for row in (
        _exclusion(key, a_index[key], b_index[key], name_a, name_b)
        for key in sorted(a_index)) if row is not None]
    reasons = [row["reason"] for row in excluded]
    return {**base, "n_pairs": len(a_index),
            "admissible_pairs": len(a_index) - len(excluded),
            "excluded_pairs": excluded,
            "model_drift_excluded": reasons.count("model_drift"),
            "envelope_malformed_excluded": reasons.count("envelope_malformed"),
            "model_unrecorded_excluded":
                reasons.count("model_observed_unrecorded"),
            "does_not_prove": list(_VOIDING_DOES_NOT_PROVE)}


def _holm_validate(comparisons: list, primary: str) -> dict:
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError("comparisons must be a nonempty list")
    by_id: dict = {}
    for row in comparisons:
        cid = row.get("comparison_id") if isinstance(row, dict) else None
        p = row.get("p") if isinstance(row, dict) else None
        if not isinstance(cid, str) or not cid.strip():
            raise ValueError("every comparison needs a nonempty "
                             "comparison_id")
        if cid in by_id:
            raise ValueError(f"duplicate comparison_id {cid!r}")
        if type(p) not in (int, float) or not 0.0 <= p <= 1.0:
            raise ValueError(
                f"comparison {cid!r}: p must be a number in [0, 1]")
        by_id[cid] = float(p)
    if not isinstance(primary, str) or primary not in by_id:
        raise ValueError(
            "primary must name one comparison in the list; the exemption "
            "exists only for a preregistered primary that is actually here")
    return by_id


def holm_bonferroni(comparisons: list, *, primary: str) -> dict:
    """Holm-Bonferroni over the declared family; the primary is exempt.

    ``comparisons`` is ``[{"comparison_id", "p"}, ...]`` with raw p values
    (e.g. ``paired_comparison(...)["pooled"]["p_exact"]``); ``primary`` names
    the ONE preregistered primary comparison, which is exempt from adjustment
    by prereg and emits raw p only. Every other comparison is the family:
    step-down adjusted p = max over the sorted prefix of (m - j) * p_(j)
    (0-based j, family size m), monotone, capped at 1.0. Raw and adjusted p
    are both emitted for every family member. Malformed input raises.
    """
    by_id = _holm_validate(comparisons, primary)
    family = sorted(((p, cid) for cid, p in by_id.items() if cid != primary))
    m = len(family)
    adjusted: dict = {}
    running = 0.0
    for j, (p, cid) in enumerate(family):
        running = max(running, min(1.0, (m - j) * p))
        adjusted[cid] = running
    rows = []
    for row in comparisons:
        cid = row["comparison_id"]
        if cid == primary:
            rows.append({"comparison_id": cid, "role": "primary",
                         "p_raw": by_id[cid], "p_adjusted": None,
                         "adjustment": "exempt_preregistered_primary"})
        else:
            rows.append({"comparison_id": cid, "role": "family",
                         "p_raw": by_id[cid], "p_adjusted": adjusted[cid],
                         "adjustment": "holm_bonferroni"})
    return {"schema": HOLM_SCHEMA, "statistic": "holm_bonferroni",
            "primary": primary, "family_size": m, "rows": rows,
            "does_not_prove": list(_HOLM_DOES_NOT_PROVE)}
