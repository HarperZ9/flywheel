"""Adapters — the bridge from the stubbed interfaces to LIVE minds and a live judge.

v1 ships deterministic stubs. The live engine supplies real perception/generation by injecting a
**model-call function** `fn(prompt: str) -> str` (a subagent, an API call, a local model — the center
does not care which). These adapters turn that one injected callable into a `Mind` (perceive/reconcile)
and a `Judge` (per-dimension scoring), so the live path is expressible and testable WITHOUT the center
package itself depending on any model or network. Wiring `fn` to an actual model is the deployment step;
here it stays an injected boundary so tests pass a fake `fn`.

Honest scope: this makes the live path real *in principle* and hermetically testable; it is not itself a
live run. The atelier (generate) and the eye (perceive) become `CallableMind`s with channel-specific
prompts; a real model becomes the `CallableJudge`.
"""
from __future__ import annotations
import json
from typing import Callable

from .judge import DIMENSIONS


class CallableMind:
    """A live mind backed by an injected model-call `fn(prompt)->str`."""

    def __init__(self, name: str, channel: str, fn: Callable[[str], str]):
        self.name = name
        self.channel = channel
        self._fn = fn

    def perceive_and_propose(self, view: str) -> str:
        return self._fn(
            f"You perceive a subject only through its {self.channel}. Propose toward its best form, "
            f"using ONLY what this view shows.\n\n{self.channel.upper()} VIEW:\n{view}"
        ).strip()

    def reconcile(self, own_view: str, others_deposits: list[str]) -> str:
        others = "\n\n".join(f"- {d}" for d in others_deposits)
        return self._fn(
            f"You are the {self.channel} mind. Reconcile your view with the other minds' proposals into "
            f"the strongest combined proposal; keep what is grounded, drop what is not.\n\n"
            f"YOUR {self.channel.upper()} VIEW:\n{own_view}\n\nOTHERS' PROPOSALS:\n{others}"
        ).strip()


class CallableJudge:
    """A live external judge backed by an injected `fn(prompt)->str` that returns JSON dim->score.

    Fail-safe: if the model returns unparseable or out-of-range output, missing dims default to 0.0 and
    values are clamped to [0,1] — an unreadable witness never silently inflates a score."""

    def __init__(self, fn: Callable[[str], str]):
        self._fn = fn

    def score(self, candidate: str, subject_views, dims=DIMENSIONS) -> dict:
        prompt = (
            "Score this candidate's faithfulness to the subject on each dimension in [0,1]. "
            f"Return ONLY JSON mapping dimension->score. Dimensions: {list(dims)}.\n\n"
            f"SUBJECT (its perceptible forms):\n{json.dumps(subject_views)[:4000]}\n\nCANDIDATE:\n{candidate}"
        )
        try:
            raw = self._fn(prompt)
            data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            return {d: max(0.0, min(1.0, float(data.get(d, 0.0)))) for d in dims}
        except (ValueError, TypeError, KeyError):
            return {d: 0.0 for d in dims}   # unreadable witness -> no credit (fail-closed on the score)
