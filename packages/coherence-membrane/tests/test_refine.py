import math
import pytest

from coherence_membrane.refine import (
    GradedCriterion, Grade, grade, cohesion, reflect, is_correct, refine, RefineOutcome,
)


def _g(margin, name="x", kind="objective"):
    """A Grade with a chosen margin (deviation/tolerance are illustrative)."""
    return Grade(name, kind, 0.0, 1.0, margin, margin >= 0.0)


# --- cohesion: the coordination measure ---

def test_cohesion_harmonic_mean_punishes_imbalance():
    balanced = cohesion([0.5, 0.5])          # arithmetic mean 0.5
    lopsided = cohesion([0.9, 0.1])          # SAME arithmetic mean 0.5, but imbalanced
    assert abs(balanced - 0.5) < 1e-9
    assert lopsided < 0.2                     # harmonic mean collapses on the weak axis
    assert balanced > lopsided                # balance wins at equal mean


def test_cohesion_zero_if_any_axis_fails_or_unmeasurable():
    assert cohesion([0.5, 0.0]) == 0.0        # a bare-threshold (0) axis tanks it
    assert cohesion([0.5, -0.2]) == 0.0       # a failing axis
    assert cohesion([0.5, float("-inf")]) == 0.0   # an unmeasurable axis
    assert cohesion([]) == 0.0


def test_cohesion_maximal_at_equal_margins():
    # for a fixed sum, cohesion (harmonic mean) is maximal when margins are equal
    assert cohesion([0.4, 0.4]) > cohesion([0.6, 0.2])
    assert cohesion([0.6, 0.2]) > cohesion([0.75, 0.05])


# --- grade: fail-closed ---

def test_grade_fail_closed_on_raise_and_nonfinite():
    raises = GradedCriterion("r", "objective", lambda f: (_ for _ in ()).throw(ValueError("boom")), 1.0)
    nan = GradedCriterion("n", "objective", lambda f: float("nan"), 1.0)
    neg = GradedCriterion("neg", "objective", lambda f: -1.0, 1.0)
    for c in (raises, nan, neg):
        g = grade(c, None)
        assert g.margin == float("-inf") and g.ok is False

def test_grade_margin_math():
    c = GradedCriterion("d", "objective", lambda f: 2.0, 10.0)
    g = grade(c, None)
    assert abs(g.margin - 0.8) < 1e-9 and g.ok is True       # (10-2)/10


# --- correct: balance + guard, not bare-passing ---

def test_correct_requires_balance_not_just_pass():
    grades = [_g(0.95, "a"), _g(0.15, "b")]                   # both >= target 0.1, but lopsided
    coh = cohesion([0.95, 0.15])
    assert all(g.margin >= 0.1 for g in grades)              # every axis "passes"
    assert is_correct(grades, coh, True, target_margin=0.1, cohesion_bar=0.4) is False  # cohesion rejects
    bal = [_g(0.5, "a"), _g(0.5, "b")]
    assert is_correct(bal, cohesion([0.5, 0.5]), True, target_margin=0.1, cohesion_bar=0.4) is True


def test_correct_requires_guard():
    grades = [_g(0.6, "a"), _g(0.6, "b")]
    coh = cohesion([0.6, 0.6])
    assert is_correct(grades, coh, True, target_margin=0.1, cohesion_bar=0.4) is True
    assert is_correct(grades, coh, False, target_margin=0.1, cohesion_bar=0.4) is False  # guard fails -> not correct


def test_correct_requires_every_axis_past_target():
    grades = [_g(0.6, "a"), _g(0.05, "b")]                    # b below target 0.1
    assert is_correct(grades, cohesion([0.6, 0.05]), True, target_margin=0.1, cohesion_bar=0.0) is False


# --- the loop ---

def _grader(dev_of_candidate, name, kind="objective", tol=10.0):
    return GradedCriterion(name, kind, lambda c, f=dev_of_candidate: f(c), tol)


def test_refine_reaches_correct():
    # candidate is an int; deviation falls as it rises; adjust increments it
    graders = [_grader(lambda c: max(0, 5 - c), "a"), _grader(lambda c: max(0, 5 - c), "b", "subjective")]
    out = refine(lambda s: (s or 0), graders, lambda refl, s: (s or 0) + 1,
                 target_margin=0.6, cohesion_bar=0.5, max_iter=10)
    assert out.status == "correct"
    assert len(out.trajectory) >= 2                           # re-iterated: first candidate failed, then cleared
    assert out.candidate >= 1


def test_refine_budget_short_is_honest():
    # axis 'b' is stuck below target; never correct; must report short on 'b', never "correct"
    graders = [_grader(lambda c: 1.0, "a"), _grader(lambda c: 4.0, "b", "subjective")]
    out = refine(lambda s: (s or 0), graders, lambda refl, s: (s or 0) + 1,
                 target_margin=0.8, cohesion_bar=0.3, max_iter=4)
    assert out.status == "short"
    assert out.short_axis == "b"
    assert all(step.correct is False for step in out.trajectory)
    assert len(out.trajectory) == 4                           # used the whole honest budget


def test_refine_guard_blocks_correct():
    graders = [_grader(lambda c: 0.0, "a"), _grader(lambda c: 0.0, "b")]   # margins perfect
    out = refine(lambda s: (s or 0), graders, lambda refl, s: (s or 0) + 1,
                 guard=lambda c: False,                       # but the guard always denies
                 target_margin=0.6, cohesion_bar=0.5, max_iter=3)
    assert out.status == "short"                              # perfect margins, but guard -> never correct


def test_degenerate_is_reconcile():
    # one grader, one pass, target<=0, bar<=0, no guard -> a single judge: pass/fail = the reconcile
    passes = refine(lambda s: 0, [_grader(lambda c: 1.0, "only")], lambda refl, s: s,
                    target_margin=0.0, cohesion_bar=0.0, max_iter=1)
    assert passes.status == "correct"                         # deviation 1 <= tolerance 10 -> within
    fails = refine(lambda s: 0, [_grader(lambda c: 99.0, "only")], lambda refl, s: s,
                   target_margin=0.0, cohesion_bar=0.0, max_iter=1)
    assert fails.status == "short" and fails.short_axis == "only"   # deviation 99 > tolerance -> not


def test_trajectory_and_reflection_recorded():
    graders = [_grader(lambda c: 4.0, "a"), _grader(lambda c: 1.0, "b")]
    out = refine(lambda s: (s or 0), graders, lambda refl, s: (s or 0) + 1,
                 target_margin=0.95, cohesion_bar=0.9, max_iter=3)
    assert len(out.trajectory) == 3
    step = out.trajectory[0]
    assert step.reflection.weakest == "a"                     # a (margin 0.6) is weaker than b (0.9)
    assert step.reflection.shortfall > 0


def test_refine_requires_a_grader():
    with pytest.raises(ValueError):
        refine(lambda s: 0, [], lambda refl, s: s, target_margin=0.1, cohesion_bar=0.1, max_iter=1)


# --- hardening from the adversarial review ---

def test_grade_rejects_bool_and_nonnumeric_deviation():
    # a buggy grader returning a falsy/non-numeric value must NOT read as a perfect 0.0 deviation
    falsy = GradedCriterion("f", "objective", lambda f: False, 1.0)
    string = GradedCriterion("s", "objective", lambda f: "0.0", 1.0)
    for c in (falsy, string):
        g = grade(c, None)
        assert g.margin == float("-inf") and g.ok is False


def test_refine_fail_closed_on_raising_generate():
    def boom(state):
        raise RuntimeError("generator exploded")
    out = refine(boom, [_grader(lambda c: 0.0, "a")], lambda refl, s: s,
                 target_margin=0.1, cohesion_bar=0.1, max_iter=3)
    assert out.status == "short"                              # honest, not a crash, not "correct"
    assert "generate-failed" in (out.short_axis or "")


def test_refine_fail_closed_on_raising_adjust():
    def boom(refl, state):
        raise RuntimeError("steer exploded")
    # margins fail (target 0.99) so it must adjust -> adjust raises -> honest short
    out = refine(lambda s: 0, [_grader(lambda c: 5.0, "a")], boom,
                 target_margin=0.99, cohesion_bar=0.5, max_iter=3)
    assert out.status == "short"
    assert "adjust-failed" in (out.short_axis or "")


def test_refine_rejects_negative_thresholds():
    # the soundness hole: a negative target/bar must NOT let a FAILING axis read as "correct"
    fail = GradedCriterion("f", "objective", lambda c: 12.0, 10.0)   # deviation 12 > tol 10 -> margin -0.2
    with pytest.raises(ValueError):
        refine(lambda s: 0, [fail], lambda r, s: s, target_margin=-0.5, cohesion_bar=-1.0, max_iter=1)
    with pytest.raises(ValueError):
        refine(lambda s: 0, [fail], lambda r, s: s, target_margin=0.1, cohesion_bar=-0.1, max_iter=1)
    # the documented degenerate (0, 0) is still allowed AND a failing axis -> short, never correct
    out = refine(lambda s: 0, [fail], lambda r, s: s, target_margin=0.0, cohesion_bar=0.0, max_iter=1)
    assert out.status == "short"
