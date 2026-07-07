"""backflow falsifier — the three real mechanisms on a frontier valve.

Real backflow is a pressure DIFFERENTIAL, not a sign. The frontier (level) valve
catches (1) backpressure: positive candidates below the current head (the case the
old sign-only valve wrongly admitted); (2) backsiphonage: a vacuum draining the head;
(3) boundary-layer separation: sustained adverse gradient detaches a self-authored
reference but not an externalized one.
"""
from harness.backflow import run_levels, sign_model_would_admit, externalization_contrast

LEVELS = [3, 5, 4, 6, 2, 6, 9]           # 4 and 2 are POSITIVE regressions
DEMANDS = [0, 0, 0, 0, 0, -3, 0]         # a vacuum at step 5


def test_frontier_valve_blocks_positive_backpressure():
    r = run_levels(LEVELS, demands=DEMANDS)
    assert r["backpressure_blocked"] == 2         # the positive regressions 4 and 2
    assert r["final_head"] == 9 and r["admitted"] == 4
    assert "BLOCKED_BACKPRESSURE" in r["verdicts"]


def test_sign_only_model_leaks_the_positive_regressions():
    # the defect this refinement fixes: the old sign valve admits every positive level
    admitted = sign_model_would_admit(LEVELS)
    assert 4 in admitted and 2 in admitted        # positive regressions leak through


def test_backsiphonage_cannot_drain_the_head():
    r = run_levels(LEVELS, demands=DEMANDS)
    assert r["backsiphonage_blocked"] == 1
    assert r["head_curve"][5] == r["head_curve"][4]   # the vacuum did not lower the head


def test_frontier_head_is_monotone():
    assert run_levels(LEVELS, demands=DEMANDS)["monotone"] is True


def test_boundary_layer_separation_only_when_self_authored():
    c = externalization_contrast([5, 4, 3, 2])        # sustained adverse gradient
    assert c["only_selfauthored_separates"] is True
    assert c["externalized"]["head_curve"] == [5, 5, 5, 5]     # stays attached
    assert c["self_authored"]["head_curve"] == [5, 4, 3, 2]    # separates, reference drifts down
