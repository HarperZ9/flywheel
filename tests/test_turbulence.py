"""turbulence falsifier — where re-checkability breaks, and what survives it.

On the logistic map (a Reynolds-like control r): the LAMINAR regime is trajectory-
reproducible (a trajectory receipt re-checks); the TURBULENT regime (positive Lyapunov)
is NOT — the exact path diverges under a tiny perturbation, so a trajectory receipt
DRIFTs — but the STATISTICAL INVARIANT still re-checks across seeds. The lesson:
demanding trajectory-match on a chaotic system is a spurious DRIFT; witness the
distribution.
"""
from harness.turbulence import (lyapunov, trajectory_rechecks, invariant_rechecks,
                                regime, false_drift_from_wrong_invariant)


def test_laminar_regime_trajectory_rechecks():
    assert lyapunov(3.2) < 0
    assert trajectory_rechecks(3.2, 0.3) is True


def test_turbulent_regime_trajectory_does_not_recheck():
    assert lyapunov(3.9) > 0                       # sensitive dependence
    assert trajectory_rechecks(3.9, 0.3) is False  # the exact path receipt DRIFTs


def test_statistical_invariant_survives_chaos():
    # the invariant measure reproduces across DIFFERENT seeds even in the chaotic regime
    assert invariant_rechecks(3.9) is True


def test_lyapunov_marks_the_regime_transition():
    assert regime(3.2)["regime"] == "laminar" and regime(3.9)["regime"] == "turbulent"


def test_demanding_trajectory_match_on_chaos_is_a_false_drift():
    turbulent = false_drift_from_wrong_invariant(3.9)
    assert turbulent["trajectory_witness"] == "DRIFT"      # wrong invariant -> false alarm
    assert turbulent["distribution_witness"] == "MATCH"    # right invariant -> conserved
    assert turbulent["false_drift"] is True
    # in the laminar regime there is no false drift (trajectory is genuinely re-checkable)
    assert false_drift_from_wrong_invariant(3.2)["false_drift"] is False
