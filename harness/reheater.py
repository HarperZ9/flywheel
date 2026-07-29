"""reheater.py -- keep RL from collapsing the diversity best-of-N depends on.

Problem, measured across the field (e.g. Internalize the Temperature, arXiv
2606.00755): RL sharpens a policy toward one high-reward mode, entropy collapses,
and the candidate multiplicity that raise-N / best-of-N depends on disappears. Our
own measured lever IS multiplicity, so a collapsed policy silently kills the edge:
after training, every one of N samples is the same string and best-of-N stops
buying anything.

Mechanism (temperature self-distillation): hold the policy close to its OWN
reheated distribution, the same logits read at a higher temperature and therefore
higher entropy, while it still optimizes for reward. This module is the pure math
of that: temperature reheating of a logit vector, the self-distillation KL toward
the reheated target, entropy measurement, an entropy-floor controller that sets
the reheat temperature from the current entropy, and a text-level group-diversity
collapse detector for the proposer path (which returns text, not logits). The
weight update that applies these lives in the PolicyOptimizer (torch); this core
is pure, dependency-light, and tests with synthetic vectors.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    """Temperature-scaled softmax. temperature > 1 flattens (reheats), < 1 sharpens."""
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    if not logits:
        return []
    scaled = [x / temperature for x in logits]
    m = max(scaled)
    exps = [math.exp(x - m) for x in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def entropy(probs: list[float], base: float = 2.0) -> float:
    """Shannon entropy in `base` units (default bits). Zeros contribute nothing."""
    h = 0.0
    for p in probs:
        if p > 0.0:
            h -= p * math.log(p, base)
    return h


def reheat(logits: list[float], temperature: float) -> list[float]:
    """The reheated target distribution: the same logits at a higher temperature.
    temperature must be >= 1 to raise entropy; 1.0 returns the base distribution."""
    if temperature < 1.0:
        raise ValueError("reheat temperature must be >= 1.0 (it raises entropy)")
    return softmax(logits, temperature)


def kl(p: list[float], q: list[float]) -> float:
    """KL(p || q) in nats. q's zeros where p is positive give +inf (guarded to a
    large finite penalty so a caller never silently divides by zero)."""
    if len(p) != len(q):
        raise ValueError("kl needs equal-length distributions")
    total = 0.0
    for pi, qi in zip(p, q):
        if pi <= 0.0:
            continue
        if qi <= 0.0:
            return math.inf
        total += pi * math.log(pi / qi)
    return total


def self_distillation_loss(policy_logits: list[float], reheat_temperature: float) -> float:
    """The reheater's per-token loss: pull the policy toward its own reheated
    (higher-entropy) target. loss = KL(reheated_target || policy). Zero at
    temperature 1.0 (target == policy); positive and growing as the target is
    reheated, which is the pressure that keeps entropy from collapsing.
    """
    target = reheat(policy_logits, reheat_temperature)
    policy = softmax(policy_logits, 1.0)
    return kl(target, policy)


@dataclass
class ReheatController:
    """Set the reheat temperature from the current entropy. Above the floor the
    policy is diverse enough and no reheating is applied (temperature 1.0). As
    entropy falls toward zero the temperature climbs toward max_temperature,
    increasing the self-distillation pressure exactly when collapse is worst.
    """
    entropy_floor: float                 # target entropy (same units as measurement)
    max_temperature: float = 2.0

    def __post_init__(self) -> None:
        if self.entropy_floor <= 0:
            raise ValueError("entropy_floor must be > 0")
        if self.max_temperature < 1.0:
            raise ValueError("max_temperature must be >= 1.0")

    def temperature(self, current_entropy: float) -> float:
        if current_entropy >= self.entropy_floor:
            return 1.0
        deficit = (self.entropy_floor - current_entropy) / self.entropy_floor
        deficit = min(max(deficit, 0.0), 1.0)
        return 1.0 + (self.max_temperature - 1.0) * deficit


def group_diversity(texts: list[str]) -> float:
    """Collapse detector for the proposer path (text, not logits): the fraction of
    distinct outputs in a group. 1.0 is fully diverse, 1/n is total collapse (every
    sample identical). A cheap early warning that best-of-N is losing its lever."""
    if not texts:
        return 0.0
    return len(set(texts)) / len(texts)


@dataclass
class ReheatSignal:
    current_entropy: float
    reheat_temperature: float
    self_distillation_loss: float
    group_diversity: float | None = None
    collapsed: bool = False

    def to_dict(self) -> dict:
        return {
            "current_entropy": round(self.current_entropy, 6),
            "reheat_temperature": round(self.reheat_temperature, 6),
            "self_distillation_loss": round(self.self_distillation_loss, 6),
            "group_diversity": (None if self.group_diversity is None
                                else round(self.group_diversity, 6)),
            "collapsed": self.collapsed,
        }


def reheat_signal_from_logits(policy_logits: list[float], controller: ReheatController,
                              *, texts: list[str] | None = None,
                              diversity_floor: float = 0.5) -> ReheatSignal:
    """Assemble a reheat signal for one step: measure entropy, pick the reheat
    temperature from the controller, compute the self-distillation loss, and (if the
    group's texts are given) attach a text-level collapse flag."""
    probs = softmax(policy_logits, 1.0)
    h = entropy(probs)
    temp = controller.temperature(h)
    loss = self_distillation_loss(policy_logits, temp) if temp > 1.0 else 0.0
    div = group_diversity(texts) if texts is not None else None
    collapsed = (h < controller.entropy_floor) or (div is not None and div < diversity_floor)
    return ReheatSignal(current_entropy=h, reheat_temperature=temp,
                        self_distillation_loss=loss, group_diversity=div,
                        collapsed=collapsed)
