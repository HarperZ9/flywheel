"""Tests for native_detect: baseline, scoring, PELT, Granger (pure-Python path)."""
from __future__ import annotations

import math

from harness.infra.native_detect import (
    AnomalyScore,
    AnomalyScorer,
    Baseline,
    BaselineBuilder,
    Changepoint,
    GrangerResult,
    granger_causality,
    native_available,
    pelt,
)


# --- native availability -----------------------------------------------


def test_native_available_returns_bool():
    assert isinstance(native_available(), bool)


# --- BaselineBuilder ---------------------------------------------------


def test_baseline_builder_accumulates_samples():
    b = BaselineBuilder()
    b.add_sample("NetworkConnectionRate", 10.0)
    b.add_sample("NetworkConnectionRate", 20.0)
    b.add_sample("NetworkConnectionRate", 30.0)
    assert b.sample_count("NetworkConnectionRate") == 3


def test_baseline_builder_builds_statistics():
    b = BaselineBuilder()
    for v in [10.0, 20.0, 30.0]:
        b.add_sample("CpuUsage", v)
    bl = b.build("CpuUsage")
    assert bl is not None
    assert bl.mean == 20.0
    assert bl.min_val == 10.0
    assert bl.max_val == 30.0
    assert bl.sample_count == 3


def test_baseline_builder_returns_none_for_insufficient_samples():
    b = BaselineBuilder()
    b.add_sample("CpuUsage", 1.0)
    assert b.build("CpuUsage") is None


def test_baseline_builder_reset():
    b = BaselineBuilder()
    b.add_sample("CpuUsage", 1.0)
    b.reset()
    assert b.sample_count("CpuUsage") == 0


# --- AnomalyScorer -----------------------------------------------------


def test_z_score_normal_value():
    scorer = AnomalyScorer()
    bl = Baseline(metric="CpuUsage", mean=50.0, stddev=10.0, sample_count=100)
    score = scorer.score(55.0, bl, threshold=3.0)
    assert score.z_score == 0.5
    assert score.is_anomalous is False


def test_z_score_anomalous_value():
    scorer = AnomalyScorer()
    bl = Baseline(metric="NetRate", mean=10.0, stddev=2.0, sample_count=100)
    score = scorer.score(20.0, bl, threshold=3.0)
    assert score.z_score == 5.0
    assert score.is_anomalous is True


def test_z_score_zero_stddev():
    scorer = AnomalyScorer()
    bl = Baseline(metric="X", mean=5.0, stddev=0.0, sample_count=10)
    score = scorer.score(5.0, bl)
    assert score.z_score == 0.0
    assert score.is_anomalous is False


def test_z_score_zero_stddev_different_value():
    scorer = AnomalyScorer()
    bl = Baseline(metric="X", mean=5.0, stddev=0.0, sample_count=10)
    score = scorer.score(99.0, bl)
    assert score.is_anomalous is True
    assert math.isinf(score.z_score)


def test_severity_from_zscore():
    assert AnomalyScorer.severity_from_zscore(0.5) == 0.0
    assert AnomalyScorer.severity_from_zscore(5.0) == 1.0
    sev = AnomalyScorer.severity_from_zscore(3.0)
    assert 0.0 < sev < 1.0


def test_iqr_score():
    assert AnomalyScorer.iqr_score(50, 40, 60) == 0.0
    assert AnomalyScorer.iqr_score(100, 40, 60) > 0.0


# --- PELT changepoint --------------------------------------------------


def test_pelt_finds_changepoint_in_shifted_data():
    """A series with a clear mean shift should produce a changepoint."""
    data = [1.0] * 50 + [10.0] * 50
    cps = pelt(data, penalty=10.0)
    assert len(cps) >= 1
    # The changepoint should be near index 50
    assert any(abs(cp.index - 50) <= 5 for cp in cps)


def test_pelt_no_changepoints_in_constant_data():
    data = [5.0] * 100
    cps = pelt(data, penalty=10.0)
    assert len(cps) == 0


def test_pelt_no_changepoints_in_short_series():
    cps = pelt([1.0, 2.0], penalty=10.0)
    assert cps == []


def test_pelt_multiple_changepoints():
    data = [1.0] * 30 + [5.0] * 30 + [1.0] * 30
    cps = pelt(data, penalty=10.0)
    assert len(cps) >= 1


def test_pelt_higher_penalty_fewer_changepoints():
    data = [1.0, 2.0, 1.0, 5.0, 6.0, 5.0, 1.0, 2.0, 1.0]
    cps_low = pelt(data, penalty=1.0)
    cps_high = pelt(data, penalty=100.0)
    assert len(cps_high) <= len(cps_low)


# --- Granger causality -------------------------------------------------


def test_granger_detects_causation():
    """x should Granger-cause y when y[t] = f(x[t-1])."""
    x = [float(i % 10) for i in range(50)]
    y = [0.0] + [x[t - 1] * 2 for t in range(1, 50)]
    result = granger_causality(x, y, max_lag=3)
    assert result.optimal_lag > 0


def test_granger_no_causation_for_random():
    """Independent random-ish series should not show strong causation."""
    x = [float(i * 7 % 13) for i in range(60)]
    y = [float(i * 11 % 17) for i in range(60)]
    result = granger_causality(x, y, max_lag=3)
    # p_value should be relatively high (not significant)
    assert result.p_value > 0.01  # loose bound; statistical test


def test_granger_short_series_returns_default():
    result = granger_causality([1.0, 2.0], [3.0, 4.0], max_lag=1)
    assert result.f_stat == 0.0
    assert result.p_value == 1.0


def test_granger_result_is_significant():
    r = GrangerResult(f_stat=10.0, p_value=0.01, optimal_lag=2)
    assert r.is_significant is True
    r2 = GrangerResult(f_stat=1.0, p_value=0.3, optimal_lag=1)
    assert r2.is_significant is False
