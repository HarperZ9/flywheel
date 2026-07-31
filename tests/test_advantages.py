import pytest

from harness.advantages import advantages, ESTIMATORS, AdvantageConfigError


def test_drgrpo_is_mean_centred_with_no_std_division():
    # Two groups with identical structure but different spread must produce
    # advantages that differ in magnitude, not identical normalized values.
    tight = advantages([0.0, 1.0], "drgrpo")
    assert tight == [-0.5, 0.5]


def test_drgrpo_magnitude_tracks_the_actual_reward_gap():
    small_gap = advantages([0.4, 0.6], "drgrpo")
    big_gap = advantages([0.0, 1.0], "drgrpo")
    assert abs(big_gap[1]) > abs(small_gap[1])


def test_grpo_std_normalizes_both_groups_to_the_same_scale():
    # The legacy estimator erases the gap difference. Kept as a control arm.
    small_gap = advantages([0.4, 0.6], "grpo_std")
    big_gap = advantages([0.0, 1.0], "grpo_std")
    assert small_gap == pytest.approx(big_gap, abs=1e-6)


def test_no_spread_yields_all_zero_under_every_estimator():
    for est in ESTIMATORS:
        assert advantages([1.0, 1.0, 1.0], est) == [0.0, 0.0, 0.0]
        assert advantages([0.0, 0.0], est) == [0.0, 0.0]


def test_advantages_sum_to_zero():
    for est in ESTIMATORS:
        out = advantages([1.0, 0.0, 1.0, 0.0], est)
        assert sum(out) == pytest.approx(0.0, abs=1e-9)


def test_empty_group_returns_empty():
    assert advantages([], "drgrpo") == []


def test_unknown_estimator_is_a_loud_error_not_a_default():
    with pytest.raises(AdvantageConfigError):
        advantages([0.0, 1.0], "whatever_the_trainer_happened_to_use")


def test_legacy_alias_still_resolves_to_the_old_behaviour():
    from harness.rl_from_oracle import grpo_advantages
    assert grpo_advantages([0.0, 1.0]) == advantages([0.0, 1.0], "grpo_std")
