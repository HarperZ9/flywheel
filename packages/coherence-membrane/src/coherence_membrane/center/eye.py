"""EyeMind / EyeJudge -- the eye (a real perception organ) wired as the center's PERCEIVE mind.

The eye is the perceptive half of the reconcile (the atelier is the generative half). Here it plugs
into the center behind the `Mind` interface using a real coherence-membrane perception organ
(VisualArtifactOrgan by default): its proposal is a WITNESSED perception of the artifact in its
channel (an Observation -- identity, decoded?, perceptual hash, confidence), not a guess. The matching
`EyeJudge` scores a candidate on the QUALITY of that witnessed perception (did the organ actually
perceive it, decode it, with what confidence), read from the real Observation -- the perceptive
counterpart to the AtelierJudge's read of the generated artifact's own fitness.
"""
from __future__ import annotations

from ..observation import Observation, Status
from ..organs.visual import VisualArtifactOrgan


def summarize_observation(obs: Observation) -> str:
    d = obs.data or {}
    return (f"organ={obs.organ} status={obs.status.value} decoded={d.get('decoded', False)} "
            f"format={d.get('format', '?')} {d.get('width', '?')}x{d.get('height', '?')} "
            f"phash={d.get('perceptual_hash')} id={(d.get('identity_sha256') or '')[:12]} "
            f"confidence={getattr(obs.provenance, 'confidence', '?')}")


class EyeMind:
    """A center Mind whose proposals are real witnessed perceptions. `view` (its channel of the
    subject) is an artifact reference (a path or bytes) the organ observes. `store` (text -> Observation)
    lets the EyeJudge retrieve the real Observation and score the perception's quality."""

    def __init__(self, name: str = "eye", channel: str = "perceive", organ=None, store: dict | None = None):
        self.name = name
        self.channel = channel
        self.organ = organ or VisualArtifactOrgan()
        self.store = store if store is not None else {}

    def _perceive(self, prefix: str, subject, suffix: str = "") -> str:
        observed = self.organ.observe(subject)
        obs = observed[0] if observed else None
        body = summarize_observation(obs) if obs is not None else "nothing perceivable"
        text = f"{prefix} {body}{suffix}"          # store under the FULL text the judge will receive
        if obs is not None:
            self.store[text] = obs
        return text

    def perceive_and_propose(self, view: str) -> str:
        return self._perceive("[perceive] eye witnessed:", view)

    def reconcile(self, own_view: str, others_deposits: list[str]) -> str:
        # the eye re-witnesses its own artifact; it perceives ARTIFACTS, not the text deposits, and says so
        return self._perceive("[perceive|reconciled] eye holds its witness:", own_view,
                              suffix=(f" (noted {len(others_deposits)} other proposals; "
                                      f"the eye perceives artifacts, not text)"))


EYE_DIMS = ("perceived", "decoded", "confidence")
_CONF = {"high": 1.0, "medium": 0.6, "low": 0.2}


class EyeJudge:
    """Scores a candidate on the QUALITY of the eye's witnessed perception (from the real Observation).
    A candidate the eye did not perceive (not in the store) scores 0 -- no perception, no credit."""

    def __init__(self, store: dict):
        self.store = store

    def score(self, candidate: str, subject_views, dims=EYE_DIMS) -> dict:
        obs = self.store.get(candidate)
        if obs is None:
            return {d: 0.0 for d in dims}
        d = obs.data or {}
        full = {
            "perceived": 1.0 if obs.status is Status.PASS else 0.0,
            "decoded": 1.0 if d.get("decoded") else 0.0,
            "confidence": _CONF.get(getattr(obs.provenance, "confidence", "low"), 0.0),
        }
        return {dim: full.get(dim, 0.0) for dim in dims}
