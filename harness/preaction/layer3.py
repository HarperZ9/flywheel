"""layer3.py -- the optional judge layer of Monitor.assess, split out of core.py.

Runs only on calls layers 0 to 2 passed. Before any model sees the call, the
arguments are checked for the judge's own output vocabulary: text shaped like
a verdict aimed at the judge is held without asking the judge. An unavailable
judge holds the call as UNVERIFIABLE unless the owner set judge_unavailable to
allow. A score is evidence, not proof, and never lowers another layer's verdict.
In typed mode (judge_typed.py) the judge returns ACT, ABSTAIN or ESCALATE;
ABSTAIN and ESCALATE both hold, with reasons judge_abstained and
judge/typed_escalate, and ACT changes nothing.
"""
from __future__ import annotations

import re

from .contract import ALLOW, HOLD, UNVERIFIABLE, Hit, worse
from .judge import build_input, combine
from .judge_typed import combine_typed
from .normalize import extract

# Text that speaks the judge's own output format has no business in a tool
# argument; it is the shape of an injection aimed at the judge.
_STEERING = re.compile(r"reason_code|\bR_(NONE|GOAL|CREDENTIAL|EGRESS|DESTRUCTIVE|SCOPE|TAMPER)\b")


def run_judge(self, call, ctx, state, asm) -> dict:
    """Layer 3, on calls the lower layers passed. `self` is the Monitor."""
    if not self.judges or asm.verdict != ALLOW:
        return {"state": "off"} if not self.judges else {"state": "skipped_by_verdict"}
    if not self.config.strict_judge_reads and call.capability_class() == "builtin-read":
        return {"state": "skipped_by_mode"}
    if _STEERING.search(extract(call, ctx).text):
        asm.verdict = worse(asm.verdict, HOLD)
        asm.reasons.append(Hit("judge/steering-text", "judge", HOLD,
                               "The arguments carry the judge's own output format; "
                               "held before the judge reads them.", layer=3).to_dict())
        return {"state": "skipped_steering_text"}
    payload = build_input(call, ctx, state.history)
    if any(getattr(j, "typed", False) for j in self.judges):
        result = combine_typed([j.judge(payload) for j in self.judges])
        if result["state"] == "typed":
            return _apply_typed(result, asm)
        return _unavailable(self, result, asm)
    result = combine([j.judge(payload) for j in self.judges], self.config.judge_threshold)
    if result["state"] == "scored":
        if result["score"] >= self.config.judge_threshold:
            asm.verdict = worse(asm.verdict, HOLD)
            asm.reasons.append(Hit(f"judge/{result['reason_code']}", "judge", HOLD,
                                   f"Judge scored {result['score']} at or above "
                                   f"{self.config.judge_threshold}.", layer=3).to_dict())
        return result
    return _unavailable(self, result, asm)


_TYPED_HITS = {
    "ESCALATE": ("judge/typed_escalate", "The typed judge's answers put P(hold) at {p} per mille, "
                 "at or above the escalate line."),
    "ABSTAIN": ("judge_abstained", "The typed judge's answers were too flat to call "
                "(P(hold) {p} per mille); held rather than guessed."),
}


def _apply_typed(result: dict, asm) -> dict:
    """ACT changes nothing; ABSTAIN and ESCALATE both hold, with different reasons."""
    hit = _TYPED_HITS.get(result["outcome"])
    if hit is not None:
        asm.verdict = worse(asm.verdict, HOLD)
        asm.reasons.append(Hit(hit[0], "judge", HOLD,
                               hit[1].format(p=result["p_hold_permille"]), layer=3).to_dict())
    return result


def _unavailable(self, result: dict, asm) -> dict:
    if self.config.judge_unavailable == "allow":
        result = dict(result, state="unavailable_passed_by_owner_setting")
        return result
    asm.verdict = worse(asm.verdict, HOLD)
    asm.coverage = UNVERIFIABLE
    asm.reasons.append(Hit("judge/unavailable", "judge", HOLD,
                           "The judge could not score this call; not treated as safe.",
                           layer=3).to_dict())
    return result
