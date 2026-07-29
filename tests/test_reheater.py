"""Falsifier for reheater.py -- the entropy-preservation core.

The component must: reheat a logit vector to HIGHER entropy (never lower), measure
entropy correctly, produce a self-distillation loss that is zero at temperature 1
and positive when reheated, raise the reheat temperature as entropy falls below the
floor (and only then), and flag collapse from text-level group diversity.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from harness.reheater import (
    softmax, entropy, reheat, kl, self_distillation_loss,
    ReheatController, group_diversity, reheat_signal_from_logits,
)


def test_softmax_normalizes_and_uniform():
    p = softmax([1.0, 1.0, 1.0, 1.0])
    assert abs(sum(p) - 1.0) < 1e-9
    assert all(abs(x - 0.25) < 1e-9 for x in p)


def test_softmax_rejects_nonpositive_temperature():
    with pytest.raises(ValueError):
        softmax([1.0, 2.0], temperature=0.0)


def test_entropy_bounds():
    assert abs(entropy([0.25, 0.25, 0.25, 0.25]) - 2.0) < 1e-9   # log2(4) = 2 bits
    assert entropy([1.0, 0.0, 0.0, 0.0]) == 0.0                  # one-hot: zero


def test_reheat_raises_entropy():
    logits = [3.0, 1.0, 0.2, -1.0]
    base_h = entropy(softmax(logits, 1.0))
    hot_h = entropy(reheat(logits, 2.0))
    assert hot_h > base_h                                        # reheating adds entropy
    assert abs(entropy(reheat(logits, 1.0)) - base_h) < 1e-9     # T=1 is identity


def test_reheat_refuses_to_cool():
    with pytest.raises(ValueError):
        reheat([1.0, 2.0], 0.5)                                  # < 1 would sharpen, not reheat


def test_kl_zero_on_identity_and_inf_on_unsupported():
    p = softmax([1.0, 2.0, 0.5])
    assert abs(kl(p, p)) < 1e-12
    assert kl([0.5, 0.5], [1.0, 0.0]) == math.inf               # q=0 where p>0


def test_self_distillation_loss_zero_at_one_positive_when_reheated():
    logits = [2.0, 0.5, -0.5, 1.0]
    assert self_distillation_loss(logits, 1.0) == 0.0
    assert self_distillation_loss(logits, 2.0) > 0.0


def test_controller_reheats_only_below_floor_and_monotone():
    c = ReheatController(entropy_floor=1.5, max_temperature=2.0)
    assert c.temperature(1.5) == 1.0            # at floor: no reheat
    assert c.temperature(2.0) == 1.0            # above floor: no reheat
    assert c.temperature(0.0) == 2.0            # zero entropy: max reheat
    mid = c.temperature(0.75)                   # half the deficit
    assert 1.0 < mid < 2.0
    # monotone: lower entropy -> higher (or equal) temperature
    temps = [c.temperature(h) for h in (0.0, 0.5, 1.0, 1.5, 2.0)]
    assert all(a >= b for a, b in zip(temps, temps[1:]))


def test_controller_rejects_bad_config():
    with pytest.raises(ValueError):
        ReheatController(entropy_floor=0.0)
    with pytest.raises(ValueError):
        ReheatController(entropy_floor=1.0, max_temperature=0.9)


def test_group_diversity_detects_collapse():
    assert group_diversity(["a", "a", "a", "a"]) == 0.25        # 1/n: total collapse
    assert group_diversity(["a", "b", "c", "d"]) == 1.0        # fully diverse
    assert group_diversity([]) == 0.0


def test_signal_flags_collapse():
    c = ReheatController(entropy_floor=1.5, max_temperature=2.0)
    sharp = [10.0, 0.0, 0.0, 0.0]                               # near one-hot: low entropy
    sig = reheat_signal_from_logits(sharp, c, texts=["x", "x", "x", "x"])
    assert sig.collapsed is True
    assert sig.reheat_temperature > 1.0
    assert sig.self_distillation_loss > 0.0
    assert sig.group_diversity == 0.25

    flat = [1.0, 1.0, 1.0, 1.0]                                 # max entropy: healthy
    ok = reheat_signal_from_logits(flat, c, texts=["a", "b", "c", "d"])
    assert ok.collapsed is False
    assert ok.reheat_temperature == 1.0
    assert ok.self_distillation_loss == 0.0
