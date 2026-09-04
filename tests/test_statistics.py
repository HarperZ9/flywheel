"""Section 6: the variance component, the interval, and the declared MDE.

The tests that matter are the refusals and the one worked example the frozen
preregistration supplies itself. If `sd_from_range` ever returns half the range
this suite goes red, because halving a range is the specific error the prereg
calls out by name and the reason the function exists at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.statistics import (                                     # noqa: E402
    MIN_REPLICATES, StatisticsError, between_seed_sd, cluster_bootstrap,
    mcnemar_mde, mcnemar_plan, sd_from_range)


def _mean(units):
    return sum(units) / len(units)


# --- the prereg's own worked example ----------------------------------------

def test_the_preregs_own_range_example_reproduces():
    """Section 6, verbatim: "a 2.7pp two-run spread implies sigma near 2.4pp,
    not 1.35pp". 1.35 is half the range, which is the mistake."""
    out = sd_from_range(2.7, 2)
    assert out["sigma_estimate"] == pytest.approx(2.394, abs=0.01)
    assert out["sigma_estimate"] != pytest.approx(1.35, abs=0.01)
    assert out["d2"] == 1.128


def test_the_range_estimate_never_reads_as_a_replicate_sd():
    joined = " ".join(sd_from_range(2.7, 2)["does_not_prove"])
    assert "NOT_PROVES_A_REPLICATE_SD" in joined
    assert "NOT_HALF_THE_RANGE" in joined


def test_an_unsupported_n_is_refused_rather_than_extrapolated():
    with pytest.raises(StatisticsError):
        sd_from_range(2.7, 99)
    with pytest.raises(StatisticsError):
        sd_from_range(-1.0, 2)


# --- the between-seed component ---------------------------------------------

def test_one_pass_cannot_yield_a_between_seed_sd():
    """A confirmatory pass is r=1. Returning the within-pass spread would be a
    smaller number wearing the name of the component the prereg calls primary."""
    for r in range(MIN_REPLICATES):
        with pytest.raises(StatisticsError):
            between_seed_sd([0.5] * r)


def test_three_replicates_give_the_sample_sd():
    out = between_seed_sd([0.40, 0.50, 0.60])
    assert out["n_replicates"] == 3
    assert out["mean"] == pytest.approx(0.50)
    assert out["sd"] == pytest.approx(0.1, abs=1e-9)     # n-1 denominator


def test_the_between_seed_result_states_what_it_does_not_cover():
    joined = " ".join(between_seed_sd([1.0, 2.0, 3.0])["does_not_prove"])
    assert "NOT_PROVES_STABILITY_ACROSS_ENVIRONMENTS" in joined


# --- the clustered bootstrap ------------------------------------------------

def test_one_cluster_cannot_produce_an_interval():
    with pytest.raises(StatisticsError):
        cluster_bootstrap({"only": [1, 2, 3]}, _mean, draws=50)


def test_the_bootstrap_is_deterministic_given_its_seed():
    clusters = {f"c{i}": [i, i + 1, i + 2] for i in range(6)}
    a = cluster_bootstrap(clusters, _mean, draws=200, seed=7)
    b = cluster_bootstrap(clusters, _mean, draws=200, seed=7)
    c = cluster_bootstrap(clusters, _mean, draws=200, seed=8)
    assert a["interval"] == b["interval"]
    assert a["interval"] != c["interval"]


def test_the_interval_contains_the_point_estimate():
    clusters = {f"c{i}": [i, i + 1] for i in range(8)}
    out = cluster_bootstrap(clusters, _mean, draws=500, seed=1)
    lo, hi = out["interval"]
    assert lo <= out["point"] <= hi


def test_correlated_clusters_widen_the_interval():
    """The reason the prereg clusters at all: the generator emits related
    groups, so treating their units as independent is anticonservative. Here
    each cluster is internally identical, so all the information is between
    clusters and an interval that ignored clustering would be far too tight."""
    correlated = {f"c{i}": [i] * 10 for i in range(6)}       # 6 real degrees
    independent = {f"c{i}": [i % 6] for i in range(60)}      # 60 fake ones
    wide = cluster_bootstrap(correlated, _mean, draws=800, seed=3)
    tight = cluster_bootstrap(independent, _mean, draws=800, seed=3)
    width = lambda o: o["interval"][1] - o["interval"][0]
    assert width(wide) > width(tight)


def test_the_bootstrap_says_it_does_not_carry_the_primary_component():
    clusters = {f"c{i}": [i] for i in range(4)}
    joined = " ".join(cluster_bootstrap(clusters, _mean, draws=50,
                                        seed=0)["does_not_prove"])
    assert "NOT_PROVES_BETWEEN_SEED_COVERAGE" in joined


# --- the declared MDE -------------------------------------------------------

def test_too_few_discordant_pairs_cannot_reach_alpha_at_any_effect_size():
    """The distinction the MDE exists to make: below six discordant pairs no
    split is significant, so a null there says nothing about the effect."""
    for m in (0, 1, 3, 5):
        out = mcnemar_mde(60, m)
        assert out["detectable"] is None
        assert out["mde_delta"] is None
        assert "carries no information" in out["note"]


def test_six_discordant_pairs_is_the_first_detectable_design():
    out = mcnemar_mde(60, 6)
    assert out["detectable"] == 6                 # a 6-0 split, p = 2/64
    assert out["mde_delta"] == pytest.approx(0.1)


def test_the_detectable_imbalance_shrinks_relative_to_the_discordant_count():
    small, large = mcnemar_mde(60, 10), mcnemar_mde(60, 40)
    assert large["detectable"] > small["detectable"]
    assert (large["detectable"] / large["n_discordant"]
            < small["detectable"] / small["n_discordant"])


def test_the_mde_reports_both_denominators():
    """With arms sharing a cached pool the binding quantity is the discordant
    count, not the task count. Both get published so the gap is visible."""
    out = mcnemar_mde(60, 8)
    assert out["n_pairs"] == 60 and out["n_discordant"] == 8


def test_an_impossible_discordant_count_is_refused():
    with pytest.raises(StatisticsError):
        mcnemar_mde(10, 11)
    with pytest.raises(StatisticsError):
        mcnemar_mde(0, 0)


def test_every_mde_carries_the_null_warning():
    joined = " ".join(mcnemar_mde(60, 20)["does_not_prove"])
    assert "NOT_PROVES_AN_EFFECT_IS_ABSENT" in joined


# --- the prospective planner ------------------------------------------------

def test_sizing_without_a_recorded_basis_is_refused():
    """The forking path the planner exists to close: an assumed discordance is
    a knob turned after seeing what N it buys. Absent basis, no N."""
    with pytest.raises(StatisticsError, match="recorded"):
        mcnemar_plan(0.25)
    with pytest.raises(StatisticsError, match="recorded"):
        mcnemar_plan(0.25, recorded_discordant_fraction=None)


def test_impossible_planning_inputs_are_refused():
    with pytest.raises(StatisticsError):                 # delta > fraction
        mcnemar_plan(0.6, recorded_discordant_fraction=0.5)
    with pytest.raises(StatisticsError):                 # zero delta
        mcnemar_plan(0.0, recorded_discordant_fraction=0.5)
    with pytest.raises(StatisticsError):                 # zero discordance
        mcnemar_plan(0.25, recorded_discordant_fraction=0.0)
    with pytest.raises(StatisticsError):                 # fraction > 1
        mcnemar_plan(0.25, recorded_discordant_fraction=1.5)
    with pytest.raises(StatisticsError):
        mcnemar_plan(0.25, recorded_discordant_fraction=0.5, alpha=1.0)
    with pytest.raises(StatisticsError):
        mcnemar_plan(0.25, recorded_discordant_fraction=0.5, power=1.0)


def test_the_all_one_way_plan_is_twelve_pairs_by_hand():
    """Hand-checked: delta == fraction means every discordant pair falls one
    way, so the design needs the first significant all-one-way split, which is
    m = 6 (p = 2/64 = 0.03125; m = 5 gives 2/32 = 0.0625). floor(0.5 * N) >= 6
    first holds at N = 12."""
    out = mcnemar_plan(0.5, recorded_discordant_fraction=0.5)
    assert out["n_pairs"] == 12
    assert out["expected_discordant"] == 6
    assert out["achieved_power"] == 1.0
    assert out["mde_at_plan"]["detectable"] == 6
    assert out["mde_at_plan"]["mde_delta"] == pytest.approx(0.5)


def test_the_plan_feeds_back_through_the_mde_at_or_under_target():
    """The acceptance loop: mcnemar_mde at the planned (N, expected
    discordant) must call a delta no larger than the one the plan targeted."""
    for d, f in ((0.5, 0.5), (0.25, 0.5), (0.1, 0.4), (0.2, 0.6), (1.0, 1.0)):
        out = mcnemar_plan(d, recorded_discordant_fraction=f)
        back = mcnemar_mde(out["n_pairs"], out["expected_discordant"])
        assert back["mde_delta"] is not None
        assert back["mde_delta"] <= d
        assert out["mde_at_plan"]["mde_delta"] == back["mde_delta"]


def test_the_planned_power_is_exact_not_approximate():
    """Independent recomputation with exact rational arithmetic. The planned
    design at d=0.25, f=0.5 is N=60, m=30, critical smaller cell 9, and the
    binomial(30, 0.75) mass on the rejection region is 0.803407."""
    from fractions import Fraction
    from math import comb as _comb
    out = mcnemar_plan(0.25, recorded_discordant_fraction=0.5)
    assert out["n_pairs"] == 60
    assert out["expected_discordant"] == 30
    m, k_crit = 30, 9
    p1 = Fraction(3, 4)                              # (1 + d/f) / 2
    mass = sum(_comb(m, b) * p1 ** b * (1 - p1) ** (m - b)
               for b in list(range(k_crit + 1)) + list(range(m - k_crit, m + 1)))
    assert out["achieved_power"] == pytest.approx(float(mass), abs=1e-6)
    assert out["achieved_power"] >= 0.8


@pytest.mark.parametrize(
    ("delta", "fraction", "max_pairs", "expected_n"),
    (
        (0.25, 0.333, 20000, 37),
        (0.05, 0.333, 2000, 1058),
    ),
)
def test_the_plan_finds_the_first_valid_n_across_nonmonotone_boundaries(
        delta, fraction, max_pairs, expected_n):
    """Exact-test critical values and floor(fraction * N) make feasibility
    nonmonotone in N. The planner must therefore find the first valid integer,
    even when a later power-of-two probe fails or the next probe exceeds the
    configured cap."""
    out = mcnemar_plan(
        delta,
        recorded_discordant_fraction=fraction,
        max_pairs=max_pairs,
    )
    assert out["n_pairs"] == expected_n


def test_a_smaller_target_delta_needs_more_pairs():
    coarse = mcnemar_plan(0.5, recorded_discordant_fraction=0.5)
    fine = mcnemar_plan(0.25, recorded_discordant_fraction=0.5)
    finer = mcnemar_plan(0.125, recorded_discordant_fraction=0.5)
    assert coarse["n_pairs"] < fine["n_pairs"] < finer["n_pairs"]


def test_an_unreachable_target_refuses_at_the_cap():
    with pytest.raises(StatisticsError, match="max_pairs"):
        mcnemar_plan(0.2, recorded_discordant_fraction=0.5, max_pairs=10)


def test_the_plan_names_its_dependence_on_the_basis():
    out = mcnemar_plan(0.25, recorded_discordant_fraction=0.5)
    joined = " ".join(out["does_not_prove"])
    assert "NOT_PROVES_THE_NEXT_RUN_MATCHES_THE_BASIS" in joined
    assert out["discordance_basis"]["recorded_discordant_fraction"] == 0.5
