"""Compression-Progress + PowerPlay RL Environment gated by Three-Plate Oracle.

Credits Schmidhuber compression progress ONLY when independent Plate B (static
and assumption-mutation guard) and Plate C (IEEE-754 / compiler contract) confirm
MATCH. Stdlib-only, CPU-only, <= 210 lines, every function <= 50 lines.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .datasets import RLTask, load_ds02_buildlang_tasks, load_ds03_physics_tasks

__all__ = [
    "CompressionProgressTracker",
    "EpisodeMetrics",
    "PowerPlayCurriculum",
    "RLTask",
    "TaskSubmission",
    "ThreePlateStepVerdict",
    "ThreePlateVerifiableRLEnv",
    "load_ds02_buildlang_tasks",
    "load_ds03_physics_tasks",
]

_BYPASS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tautological_assert", re.compile(r"(?i)\bassert\s+(?:True|1\s*==\s*1)\b")),
    ("skip_oracle_flag", re.compile(r"(?i)\b(?:skip_oracle|bypass_verify|trust_proposer)\s*=\s*True\b")),
    ("anygeometry_bypass", re.compile(r"(?i)\banygeometry\s*=\s*true\b")),
    ("lean_sorry", re.compile(r"(?m)(?:^|\s)(?:sorry|admit)(?:\s|$|--|;)")),
    ("em_dash_violation", re.compile("\u2014")),
)


@dataclass(frozen=True)
class TaskSubmission:
    task_id: str
    numeric_answer: float | None = None
    code_or_rationale: str = ""
    proposer_self_test_passed: bool = True
    claimed_compression_gain: float = 0.0
    passes_mutated_assumption: bool = False


@dataclass(frozen=True)
class ThreePlateStepVerdict:
    task_id: str
    verdict: str  # "MATCH" | "DRIFT" | "UNVERIFIABLE"
    plate_a_pass: bool
    plate_b_pass: bool
    plate_c_pass: bool
    defects: tuple[str, ...]
    credited_curiosity: float
    total_reward: float


@dataclass
class EpisodeMetrics:
    policy_name: str
    steps: int
    oracle_matches: int
    rejected_hack_attempts: int
    total_credited_curiosity: float
    mean_reward: float
    solved_archive_size: int
    receipt_sha256: str
    verdicts: list[ThreePlateStepVerdict] = field(default_factory=list)

    @property
    def oracle_pass_rate(self) -> float:
        return self.oracle_matches / self.steps if self.steps else 0.0


class CompressionProgressTracker:
    """Tracks genuine description-length drop (Schmidhuber compression progress)."""

    def __init__(self, initial_bits: float = 12.0) -> None:
        self.initial_bits = initial_bits
        self._best_bits: dict[str, float] = {}

    def record_verified_error(self, task_id: str, abs_error: float) -> float:
        curr_bits = max(0.0, math.log2(1.0 + abs_error * 1e6))
        prev_bits = self._best_bits.get(task_id, self.initial_bits)
        gain = max(0.0, prev_bits - curr_bits)
        if curr_bits < prev_bits:
            self._best_bits[task_id] = curr_bits
        return gain


class PowerPlayCurriculum:
    """Selects simplest unsolved task while preserving verified solved archive."""

    def __init__(self, tasks: Sequence[RLTask]) -> None:
        self.tasks = sorted(tasks, key=lambda t: (t.difficulty, t.task_id))
        self.solved_ids: set[str] = set()

    def next_task(self) -> RLTask:
        for task in self.tasks:
            if task.task_id not in self.solved_ids:
                return task
        return self.tasks[-1]

    def mark_verified(self, task_id: str) -> None:
        self.solved_ids.add(task_id)


def _check_plate_b(sub: TaskSubmission) -> list[str]:
    defects: list[str] = []
    for label, rx in _BYPASS_PATTERNS:
        if rx.search(sub.code_or_rationale):
            defects.append(f"plate_b:{label}")
    if sub.passes_mutated_assumption:
        defects.append("plate_b:assumption_mutation_bypass")
    return defects


def _check_plate_c(task: RLTask, sub: TaskSubmission) -> tuple[list[str], float]:
    if task.oracle_kind == "numeric_formula":
        if task.expected_value is None or sub.numeric_answer is None:
            return ["plate_c:missing_numeric_answer"], 1e6
        if not math.isfinite(sub.numeric_answer):
            return ["plate_c:non_finite_answer"], 1e6
        err = abs(sub.numeric_answer - task.expected_value)
        ok = math.isclose(sub.numeric_answer, task.expected_value, rel_tol=task.rel_tol, abs_tol=1e-12)
        if not ok:
            return [f"plate_c:numeric_drift(err={err:.3e})"], err
        return [], err
    code = sub.code_or_rationale
    defects: list[str] = []
    if "fn " not in code or code.count("{") != code.count("}") or "{" not in code:
        defects.append("plate_c:invalid_buildlang_syntax")
    for eff in task.required_effects:
        if f"!{eff}" not in code:
            defects.append(f"plate_c:missing_effect_{eff}")
    return defects, (0.0 if not defects else 10.0)


class ThreePlateVerifiableRLEnv:
    """Verifiable RL environment where curiosity is strictly gated by Three-Plate MATCH."""

    def __init__(self, tasks: Sequence[RLTask], *, curiosity_weight: float = 0.25) -> None:
        self.tasks = list(tasks)
        self.curiosity_weight = curiosity_weight
        self.curriculum = PowerPlayCurriculum(tasks)
        self.compression = CompressionProgressTracker()

    def step(self, task: RLTask, sub: TaskSubmission) -> ThreePlateStepVerdict:
        defects: list[str] = []
        if not sub.proposer_self_test_passed:
            defects.append("plate_a:proposer_reported_fail")
        if sub.numeric_answer is None and not sub.code_or_rationale.strip():
            defects.append("plate_a:empty_submission")
        plate_a_pass = not defects
        b_defects = _check_plate_b(sub)
        plate_b_pass = not b_defects
        c_defects, abs_err = _check_plate_c(task, sub)
        plate_c_pass = not c_defects
        all_defects = tuple(defects + b_defects + c_defects)
        if plate_a_pass and plate_b_pass and plate_c_pass:
            gain = self.compression.record_verified_error(task.task_id, abs_err)
            self.curriculum.mark_verified(task.task_id)
            reward = 1.0 + self.curiosity_weight * gain
            return ThreePlateStepVerdict(task.task_id, "MATCH", True, True, True, (), gain, reward)
        return ThreePlateStepVerdict(
            task.task_id, "DRIFT", plate_a_pass, plate_b_pass, plate_c_pass, all_defects, 0.0, -1.0
        )

    def run_policy(
        self,
        policy_name: str,
        policy_fn: Callable[[RLTask], TaskSubmission],
        *,
        max_steps: int | None = None,
    ) -> EpisodeMetrics:
        steps = max_steps or len(self.tasks)
        verdicts: list[ThreePlateStepVerdict] = []
        matches = 0
        hack_rejects = 0
        for _ in range(steps):
            task = self.curriculum.next_task()
            sub = policy_fn(task)
            v = self.step(task, sub)
            verdicts.append(v)
            if v.verdict == "MATCH":
                matches += 1
            elif sub.proposer_self_test_passed and (sub.claimed_compression_gain > 0.0 or not v.plate_b_pass):
                hack_rejects += 1
        mean_r = sum(v.total_reward for v in verdicts) / len(verdicts) if verdicts else 0.0
        tot_c = sum(v.credited_curiosity for v in verdicts)
        payload = {
            "policy": policy_name,
            "steps": len(verdicts),
            "matches": matches,
            "hack_rejects": hack_rejects,
            "verdicts": [(v.task_id, v.verdict, round(v.total_reward, 6)) for v in verdicts],
        }
        digest = "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return EpisodeMetrics(
            policy_name, len(verdicts), matches, hack_rejects, tot_c, mean_r,
            len(self.curriculum.solved_ids), digest, verdicts,
        )
