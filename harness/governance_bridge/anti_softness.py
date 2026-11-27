# SPDX-License-Identifier: MIT
"""Anti-softness adversarial dialogue critic (N68 / SIG-099, stdlib only).

Measures sycophancy markers, premature hedging, and tidy-redemption tropes
against direct-falsification evidence across dialogue turns, rejecting soft
or unbacked-agreement responses fail-closed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Applies deterministic lexical detection of sycophancy, premature hedging, "
    "and tidy-redemption phrases against direct-falsification markers; it does "
    "not judge semantic sincerity or broader literary merit."
)

SYCOPHANCY_PHRASES: tuple[str, ...] = (
    "you are absolutely right",
    "what a great point",
    "i completely agree",
    "brilliant insight",
    "spot on",
    "totally agree with you",
)

HEDGING_PHRASES: tuple[str, ...] = (
    "perhaps maybe",
    "it might possibly",
    "i suppose we could",
    "one could arguably",
    "it could maybe be",
)

TIDY_REDEMPTION_PHRASES: tuple[str, ...] = (
    "i see the error of my ways",
    "all is forgiven",
    "we can both agree",
    "everything worked out cleanly",
    "we learned a valuable lesson together",
)

DIRECT_FALSIFICATION_MARKERS: tuple[str, ...] = (
    "false",
    "contradicts",
    "measured",
    "rejected",
    "fails",
    "mismatch",
    "drift",
    "refuted",
)


def _count_matches(low_text: str, phrases: Sequence[str]) -> tuple[int, list[str]]:
    total = 0
    matched: list[str] = []
    for phrase in phrases:
        cnt = low_text.count(phrase)
        if cnt > 0:
            total += cnt
            matched.append(phrase)
    return total, matched


@dataclass(frozen=True)
class CriticScore:
    passed: bool
    sycophancy_hits: int
    hedging_hits: int
    tidy_redemption_hits: int
    direct_falsification_hits: int
    softness_ratio: float
    penalty: float
    reasons: tuple[str, ...]
    matched_soft_phrases: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "sycophancy_hits": self.sycophancy_hits,
            "hedging_hits": self.hedging_hits,
            "tidy_redemption_hits": self.tidy_redemption_hits,
            "direct_falsification_hits": self.direct_falsification_hits,
            "softness_ratio": self.softness_ratio,
            "penalty": self.penalty,
            "reasons": list(self.reasons),
            "matched_soft_phrases": list(self.matched_soft_phrases),
        }


def evaluate_transcript(
    text: str,
    *,
    min_direct: int = 3,
    max_softness_ratio: float = 0.15,
) -> CriticScore:
    """Score one dialogue turn or script excerpt fail-closed for softness and sycophancy."""
    low = text.lower()
    syc, syc_m = _count_matches(low, SYCOPHANCY_PHRASES)
    hedge, hedge_m = _count_matches(low, HEDGING_PHRASES)
    tidy, tidy_m = _count_matches(low, TIDY_REDEMPTION_PHRASES)
    direct, _ = _count_matches(low, DIRECT_FALSIFICATION_MARKERS)

    soft = syc + hedge + tidy
    denom = float(soft + direct) if (soft + direct) > 0 else 1.0
    ratio = round(soft / denom, 6)
    raw_pen = (2.0 * syc) + (1.0 * hedge) + (1.5 * tidy) - (0.5 * direct)
    penalty = round(max(0.0, raw_pen), 4)

    reasons: list[str] = []
    if syc > 0:
        reasons.append("SYCOPHANCY_DETECTED")
    if hedge > 0:
        reasons.append("PREMATURE_HEDGING_DETECTED")
    if tidy > 0:
        reasons.append("TIDY_REDEMPTION_DETECTED")
    if direct < min_direct:
        reasons.append("INSUFFICIENT_DIRECT_FALSIFICATION")
    if ratio > max_softness_ratio:
        reasons.append("SOFTNESS_RATIO_EXCEEDED")

    passed = (soft == 0) and (direct >= min_direct) and (ratio <= max_softness_ratio)
    return CriticScore(
        passed=passed,
        sycophancy_hits=syc,
        hedging_hits=hedge,
        tidy_redemption_hits=tidy,
        direct_falsification_hits=direct,
        softness_ratio=ratio,
        penalty=penalty,
        reasons=tuple(reasons),
        matched_soft_phrases=tuple(syc_m + hedge_m + tidy_m),
    )


def audit_dialogue_turns(
    turns: Sequence[str],
    *,
    min_direct: int = 3,
    max_softness_ratio: float = 0.15,
) -> dict[str, object]:
    """Audit a multi-turn transcript fail-closed, flagging every soft or unbacked turn."""
    if not turns:
        return {
            "ok": False,
            "turns_checked": 0,
            "failed_turns": [{"index": -1, "reasons": ["EMPTY_TRANSCRIPT"]}],
            "honest_scope_limit": HONEST_SCOPE_LIMIT,
        }
    failed_turns: list[dict[str, object]] = []
    scores: list[dict[str, object]] = []
    for idx, turn in enumerate(turns):
        sc = evaluate_transcript(turn, min_direct=min_direct, max_softness_ratio=max_softness_ratio)
        entry = {"index": idx, **sc.to_dict()}
        scores.append(entry)
        if not sc.passed:
            failed_turns.append(entry)
    return {
        "ok": len(failed_turns) == 0,
        "turns_checked": len(turns),
        "failed_count": len(failed_turns),
        "failed_turns": failed_turns,
        "scores": scores,
        "honest_scope_limit": HONEST_SCOPE_LIMIT,
    }
