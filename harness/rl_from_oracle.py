"""rl_from_oracle.py -- zero-label RL signal from the flywheel's own verifier.

The frontier direction (Ring-Zero, arXiv 2607.12395) is RL with no human labels,
where the reward comes from a verifier rather than an annotator. The flywheel
already owns the scarce half of that setup: a non-self-authored oracle whose
verdict a third party can re-derive. This module turns the SAME best-of-N group
the inference loop uses for selection into a GRPO training signal, with the oracle
as the reward. Training and inference share one generation-plus-verification
substrate; only the use differs.

GRPO (group-relative policy optimization, no value model): sample a group of G
candidates for one task, reward each, and score each by how far its reward sits
from the group mean, normalized by the group's spread. A group that is all-pass
or all-fail teaches nothing (zero advantage); a mixed group carries the gradient.
No critic model, so it fits a single-GPU, small-RAM box.

Two properties make this flywheel-native rather than a generic RL loop:

  1. The reward is a re-derivable receipt. Anyone can re-run the oracle on a
     candidate and reproduce its reward, so the training SIGNAL is auditable in a
     way a black-box reward model is not. Each group carries a content hash.
  2. The held-out oracle catches reward hacking. When a task carries a command the
     model never sees, a candidate that passes the visible oracle but fails the
     held-out one is flagged: it gamed the test instead of solving it. Training on
     that reward would teach the gaming; the flag lets the caller drop it.

The heavy weight update (logprobs plus optimizer) sits behind the PolicyOptimizer
protocol, so this core stays pure, tests with stubs, and runs with zero GPU. A
signal-only run IS the gradable-RL-data export (the forum bridge).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from statistics import fmean, pstdev
from typing import Protocol

from .task import Task
from .oracle import Oracle
from .proposer import Proposer, prompt_hash
from .advantages import advantages as _advantages, ESTIMATORS
from .verdict import Verdict, Attribution, is_dispositive

EPS = 1e-8


def grpo_advantages(rewards: list[float]) -> list[float]:
    """Legacy alias preserved for existing callers and tests. New code calls
    harness.advantages.advantages() with an explicit estimator; the estimator
    name then travels into the receipt so an auditor cannot silently disagree
    with the trainer."""
    return _advantages(rewards, "grpo_std")


@dataclass
class Rollout:
    text: str
    seed: int
    temperature: float
    reward: float                       # visible-oracle reward: 1.0 pass, 0.0 fail
    advantage: float = 0.0
    held_out_reward: float | None = None
    reward_hacked: bool = False         # passed the visible oracle, failed held-out
    text_hash: str = ""
    verdict: str = "PASS"
    attribution: str = "CANDIDATE"
    loss_masked: bool = False           # non-dispositive: counted, never a gradient


@dataclass
class RLGroup:
    task_id: str
    prompt_hash: str
    reward_source: str                  # e.g. "oracle:PytestOracle"
    rollouts: list[Rollout]
    group_mean: float
    group_std: float
    n_pass: int
    learnable: bool                     # spread > 0: the group carries a gradient
    reward_hacks: int
    signal_hash: str                    # content hash, re-derivable from the rollouts
    temperature: float = 1.0            # ONE temperature per group (see collect)
    estimator: str = "drgrpo"
    n_undecided: int = 0
    n_excluded: int = 0                 # harness/environment failures, never scored
    excluded: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "prompt_hash": self.prompt_hash,
            "reward_source": self.reward_source,
            "group_mean": round(self.group_mean, 6),
            "group_std": round(self.group_std, 6),
            "n_pass": self.n_pass,
            "learnable": self.learnable,
            "reward_hacks": self.reward_hacks,
            "signal_hash": self.signal_hash,
            "temperature": self.temperature,
            "estimator": self.estimator,
            "n_undecided": self.n_undecided,
            "n_excluded": self.n_excluded,
            "excluded": self.excluded,
            "rollouts": [
                {"seed": r.seed, "temperature": r.temperature, "reward": r.reward,
                 "advantage": round(r.advantage, 6), "held_out_reward": r.held_out_reward,
                 "reward_hacked": r.reward_hacked, "text_hash": r.text_hash,
                 "verdict": r.verdict, "attribution": r.attribution,
                 "loss_masked": r.loss_masked}
                for r in self.rollouts
            ],
        }


@dataclass
class RLReceipt:
    group_size: int
    groups: list[RLGroup]
    n_groups: int
    n_learnable: int                    # groups with a gradient (mixed rewards)
    mean_reward: float                  # over every rollout
    pass_rate: float
    reward_hacks: int
    optimizer_stats: dict | None        # PolicyOptimizer.update output, or None (signal-only)
    receipt_hash: str
    schema: str = "flywheel.rl-from-oracle/v1"

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "group_size": self.group_size,
            "n_groups": self.n_groups,
            "n_learnable": self.n_learnable,
            "mean_reward": round(self.mean_reward, 6),
            "pass_rate": round(self.pass_rate, 6),
            "reward_hacks": self.reward_hacks,
            "optimizer_stats": self.optimizer_stats,
            "receipt_hash": self.receipt_hash,
            "groups": [g.to_dict() for g in self.groups],
        }


@dataclass
class RLItem:
    """One training item: a task, the oracle that rewards it, and an optional
    held-out oracle (a second command the model never sees) for hack detection."""
    task: Task
    oracle: Oracle
    held_out: Oracle | None = None


class PolicyOptimizer(Protocol):
    """The weight-update side: consume scored groups, run the GRPO gradient (with a
    KL term to a reference policy) on a QLoRA adapter, return training stats. Kept
    behind a protocol so the loop above is pure and GPU-free."""

    def update(self, groups: list[RLGroup]) -> dict: ...


def _hash_group(task: Task, rollouts: list[Rollout]) -> str:
    payload = {
        "task_id": task.task_id,
        "prompt_hash": prompt_hash(task.prompt),
        "rollouts": sorted(
            [[r.text_hash, r.reward, r.held_out_reward] for r in rollouts],
            key=lambda x: (x[0], x[1]),
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _receipt_hash(groups: list[RLGroup]) -> str:
    blob = json.dumps(sorted(g.signal_hash for g in groups)).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


class RLFromOracle:
    """Generate a GRPO group per task, reward it with the oracle, compute
    group-relative advantages, and (optionally) hand the scored groups to a policy
    optimizer. Reuses the proposer, the oracle, and the index-stable (temperature,
    seed) grid that the inference loop already uses, so a training group has the
    same diversity guarantee as a best-of-N selection pool.
    """

    def __init__(self, proposer: Proposer, *, group_size: int = 8,
                 temperature: float = 1.0, estimator: str = "drgrpo",
                 max_new_tokens: int | None = None, seed_origin: int = 0):
        if group_size < 2:
            raise ValueError("GRPO needs a group of at least 2 to have relative signal")
        if temperature <= 0.0:
            raise ValueError(
                "training groups need temperature > 0: a greedy sample is not a "
                "draw from the policy being optimized")
        if estimator not in ESTIMATORS:
            raise ValueError(f"unknown estimator {estimator!r}")
        self.proposer = proposer
        self.group_size = group_size
        self.temperature = temperature
        self.estimator = estimator
        self.max_new_tokens = max_new_tokens
        self._next_seed = seed_origin

    def collect(self, task: Task, oracle: Oracle, *, held_out: Oracle | None = None) -> RLGroup:
        """One group: group_size samples at ONE temperature with fresh seeds.

        The multi-temperature grid used by best-of-N selection is deliberately
        not used here. Every member of a policy-gradient group must be a draw
        from the same policy, or the importance ratio is wrong for all of them,
        and a greedy member pays the policy to become deterministic.
        """
        seeds = list(range(self._next_seed, self._next_seed + self.group_size))
        self._next_seed += self.group_size
        max_tokens = self.max_new_tokens or task.max_new_tokens
        rollouts: list[Rollout] = []
        excluded: list[dict] = []

        for seed in seeds:
            out = self.proposer.generate(task.prompt, seed=seed,
                                         temperature=self.temperature,
                                         max_new_tokens=max_tokens,
                                         system=task.system)
            text = getattr(out, "text", "")
            res = oracle.verify(text, task)
            verdict = Verdict(res.verdict())
            attribution = Attribution(res.attribution)

            if not is_dispositive(verdict) and attribution is not Attribution.CANDIDATE:
                # Our bug or our missing toolchain. Dropped from the gradient and
                # written down, never scored against the candidate.
                excluded.append({"seed": seed, "verdict": verdict.value,
                                 "attribution": attribution.value,
                                 "text_hash": prompt_hash(text)})
                continue

            loss_masked = not is_dispositive(verdict)
            reward = 1.0 if verdict is Verdict.PASS else 0.0
            held_reward: float | None = None
            hacked = False
            if held_out is not None and not loss_masked:
                held_verdict = Verdict(held_out.verify(text, task).verdict())
                held_reward = 1.0 if held_verdict is Verdict.PASS else 0.0
                hacked = reward >= 1.0 and held_reward < 1.0
            rollouts.append(Rollout(
                text=text, seed=seed, temperature=self.temperature, reward=reward,
                held_out_reward=held_reward, reward_hacked=hacked,
                text_hash=prompt_hash(text), verdict=verdict.value,
                attribution=attribution.value, loss_masked=loss_masked))

        scored = [r for r in rollouts if not r.loss_masked]
        advs = _advantages([r.reward for r in scored], self.estimator)
        for r, a in zip(scored, advs):
            r.advantage = a

        rewards = [r.reward for r in scored]
        mean = fmean(rewards) if rewards else 0.0
        std = pstdev(rewards) if len(rewards) > 1 else 0.0
        source = getattr(oracle, "oracle_type", type(oracle).__name__)
        return RLGroup(
            task_id=task.task_id, prompt_hash=prompt_hash(task.prompt),
            reward_source=f"oracle:{source}", rollouts=rollouts,
            group_mean=mean, group_std=std,
            n_pass=sum(1 for x in rewards if x >= 1.0),
            learnable=std > EPS,
            reward_hacks=sum(1 for r in rollouts if r.reward_hacked),
            signal_hash=_hash_group(task, rollouts),
            temperature=self.temperature, estimator=self.estimator,
            n_undecided=sum(1 for r in rollouts if r.loss_masked),
            n_excluded=len(excluded), excluded=excluded)

    def run(self, items: list[RLItem], *, optimizer: PolicyOptimizer | None = None) -> RLReceipt:
        groups = [self.collect(it.task, it.oracle, held_out=it.held_out) for it in items]
        all_rewards = [r.reward for g in groups for r in g.rollouts]
        n_pass = sum(1 for x in all_rewards if x >= 1.0)
        stats = optimizer.update([g for g in groups if g.learnable]) if optimizer else None
        return RLReceipt(
            group_size=self.group_size, groups=groups, n_groups=len(groups),
            n_learnable=sum(1 for g in groups if g.learnable),
            mean_reward=fmean(all_rewards) if all_rewards else 0.0,
            pass_rate=(n_pass / len(all_rewards)) if all_rewards else 0.0,
            reward_hacks=sum(g.reward_hacks for g in groups),
            optimizer_stats=stats, receipt_hash=_receipt_hash(groups))
