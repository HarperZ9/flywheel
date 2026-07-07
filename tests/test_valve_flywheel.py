"""natural valve flywheel falsifier — a ratchet on verified progress.

A check valve (threshold-gated, one-way) plus a flywheel accumulator turns intermittent
bidirectional input into steady, monotone, non-regressing output. And the no-backflow
guarantee holds IFF the threshold is externalized: a self-authored valve (flow sets its
own gate) admits regression and breaks the ratchet. Same externalization asymmetry, on
the temporal/directional axis.
"""
from harness.valve_flywheel import run_stream, externalization_contrast, ValveFlywheel

STREAM = [5, 0.1, -3, 4, 0.05, -8, 7, 2]   # improvements, noise, regressions


def test_check_valve_rectifies_and_accumulates():
    r = run_stream(1.0, STREAM)
    assert r["admitted"] == 4                      # the four real improvements (5,4,7,2)
    assert r["blocked_backflow"] == 2              # the regressions (-3,-8)
    assert r["blocked_subthreshold"] == 2          # the noise (0.1,0.05)
    assert r["stored"] == 18.0


def test_no_regression_ratchet_is_monotone():
    r = run_stream(1.0, STREAM)
    assert r["monotone_no_regression"] is True
    c = r["final_curve"]
    assert all(b >= a for a, b in zip(c, c[1:]))   # stored never decreases


def test_flywheel_smooths_intermittent_input():
    # stored holds flat while inputs are blocked, steps only on admitted progress
    assert run_stream(1.0, STREAM)["final_curve"] == [5, 5, 5, 9, 9, 9, 16, 18]


def test_self_authored_valve_admits_backflow_and_breaks_the_ratchet():
    self_ = run_stream(1.0, STREAM, self_authored=True)
    assert self_["monotone_no_regression"] is False   # regression admitted -> stored dips


def test_ratchet_holds_only_when_externalized():
    assert externalization_contrast(STREAM)["ratchet_holds_only_when_externalized"] is True
