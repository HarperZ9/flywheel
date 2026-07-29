"""advantages.py -- group-relative advantage estimators, selectable and named.

Dividing by the group standard deviation (the original GRPO formulation) makes a
group's gradient magnitude depend on how mixed that group happened to be: a group
split 1-7 and a group split 4-4 are rescaled to the same size even though one
carries far more information about the reward gap. Dr.GRPO drops the division and
the per-sequence length normalization, which removes both biases.

The legacy estimator stays available and named so it can serve as a control arm.
The estimator that produced a set of advantages is recorded in the receipt: a
trainer and an auditor computing different estimators would silently disagree
forever, so the name travels with the numbers.
"""
from __future__ import annotations

from statistics import fmean, pstdev

EPS = 1e-8
ESTIMATORS = frozenset({"drgrpo", "grpo_std"})


class AdvantageConfigError(ValueError):
    """An unrecognized estimator name. Never defaulted: a silent fallback here
    is a silently wrong gradient."""


def advantages(rewards: list[float], estimator: str = "drgrpo") -> list[float]:
    """Group-relative advantages. Output length always matches input length.

    A group with no spread returns all zeros under every estimator: all-pass and
    all-fail teach nothing, and we report that rather than manufacturing a
    gradient.
    """
    if estimator not in ESTIMATORS:
        raise AdvantageConfigError(
            f"unknown estimator {estimator!r}; known: {sorted(ESTIMATORS)}")
    if not rewards:
        return []
    mean = fmean(rewards)
    centred = [r - mean for r in rewards]
    if estimator == "drgrpo":
        spread = pstdev(rewards) if len(rewards) > 1 else 0.0
        if spread <= EPS:
            return [0.0 for _ in rewards]
        return centred
    spread = pstdev(rewards)
    if spread <= EPS:
        return [0.0 for _ in rewards]
    return [c / (spread + EPS) for c in centred]
