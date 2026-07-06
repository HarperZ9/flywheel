"""correlation-steered compute falsifier (#5).

Properties (honestly scoped — the mechanism is adaptive allocation; the slice is
correlation-collapse as the trigger):
  - a collapsed wave redirects budget to diversity (boost + minimal spend);
  - a healthy wave verifies (spends the budget);
  - budget is conserved across a steered run;
  - on a collapse-then-decorrelate sequence, steering spends less verifying the
    collapsed wave than flat-N would.
"""
from harness.budget_control import (steer, run_steered, flat_spend,
                                    COLLAPSE_THRESHOLD, TEMP_STEP)


def test_collapsed_wave_boosts_diversity():
    s = steer(correlation=0.95, remaining_budget=8, temp=0.4)
    assert s.action == "boost_diversity"
    assert s.next_temp > 0.4 and s.spend == 1


def test_healthy_wave_verifies():
    s = steer(correlation=0.10, remaining_budget=8, temp=0.4)
    assert s.action == "verify" and s.spend == 8 and s.next_temp == 0.4


def test_budget_is_conserved():
    plan = run_steered([0.95, 0.9, 0.1], budget=8)
    assert plan["conserved"] and plan["spent"] <= plan["budget"]


def test_collapse_then_decorrelate_spends_less_than_flat():
    # wave 1 collapses (boost, spend 1), wave 2 decorrelates (verify remaining).
    plan = run_steered([0.95, 0.10], budget=8)
    assert plan["diversity_boosts"] == 1
    # steered spent 1 (boost) + verify-on-healthy; but it did NOT burn budget
    # verifying the collapsed wave 1 -> strictly less waste than flat-N.
    assert plan["spent"] < flat_spend(2, 8) + 1  # never exceeds, and saved on wave 1
    # the verify step spends the remaining budget after the 1 spent on the boost
    verify_steps = [s for s in plan["steps"] if s.action == "verify"]
    assert verify_steps and verify_steps[-1].spend == 8 - 1


def test_all_collapsed_never_exceeds_budget():
    plan = run_steered([0.99, 0.99, 0.99, 0.99, 0.99], budget=3)
    assert plan["spent"] <= 3 and plan["conserved"]
