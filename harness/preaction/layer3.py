"""layer3.py -- the optional judge layer of Monitor.assess, split out of core.py.

Runs only on calls layers 0 to 2 passed. Before any model sees the call, the
arguments are checked for the judge's own output vocabulary: text shaped like
a verdict aimed at the judge is held without asking the judge. An unavailable
judge holds the call as UNVERIFIABLE unless the owner set judge_unavailable to
allow. A score is evidence, not proof, and never lowers another layer's verdict.
"""
from __future__ import annotations

import re

from .contract import ALLOW, HOLD, UNVERIFIABLE, Hit, worse
from .judge import build_input, combine
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
    result = combine([j.judge(payload) for j in self.judges], self.config.judge_threshold)
    if result["state"] == "scored":
        if result["score"] >= self.config.judge_threshold:
            asm.verdict = worse(asm.verdict, HOLD)
            asm.reasons.append(Hit(f"judge/{result['reason_code']}", "judge", HOLD,
                                   f"Judge scored {result['score']} at or above "
                                   f"{self.config.judge_threshold}.", layer=3).to_dict())
        return result
    # unavailable
    if self.config.judge_unavailable == "allow":
        result = dict(result, state="unavailable_passed_by_owner_setting")
        return result
    asm.verdict = worse(asm.verdict, HOLD)
    asm.coverage = UNVERIFIABLE
    asm.reasons.append(Hit("judge/unavailable", "judge", HOLD,
                           "The judge could not score this call; not treated as safe.",
                           layer=3).to_dict())
    return result
