#!/usr/bin/env python3
"""attribution_far.py -- the Attribution False-Accept Rate probe (attribution-FAR).

Every attribution instrument here (the incentive manifest, the reward-gap probe,
the ablation) claims a behavior traces to a declared cause. attribution-FAR checks
the checker. It reads a corpus of attribution trials in which some are controls,
known-null cases built so that no real effect exists, and measures how often the
attribution method still accepted an effect on them. That false-accept rate over
the controls is the number a skeptic re-runs. A rate at or under the threshold is
RELIABLE, above it is UNRELIABLE, and a corpus without enough controls cannot be
scored.

A low rate proves the method rejects THESE placebos, not that it is correct on
real cases; the controls are only as good as their construction, and the detection
rate on the real trials is reported but does not set the verdict. Building the
control corpus and running the method over it is a separate, upstream step.
Standard library only.
"""
from __future__ import annotations

from .incentive_manifest import validate as _validate_manifest

RELIABLE = "RELIABLE"
UNRELIABLE = "UNRELIABLE"
MIN_CONTROLS = 5
DEFAULT_FAR_THRESHOLD = 0.05
FAR_DOES_NOT_PROVE = (
    "The false-accept rate is measured over the logged control trials only. A "
    "RELIABLE proves the method rejected these known-null controls at or under "
    "the threshold, not that it is correct on real cases; the controls are only "
    "as good as their construction. The detection rate on the real trials is "
    "reported but does not set the verdict. A verdict covers the logged corpus, "
    "nothing beyond it.")


class AttributionFARError(ValueError):
    """A malformed attribution-trial corpus or probe request."""


def _validate_log(trials) -> list:
    if not isinstance(trials, list) or not trials:
        raise AttributionFARError("trials: non-empty array")
    seen = set()
    for i, e in enumerate(trials):
        if not isinstance(e, dict):
            raise AttributionFARError(f"trials[{i}]: object")
        tid = e.get("trial_id")
        if not isinstance(tid, str) or not tid:
            raise AttributionFARError(f"trials[{i}].trial_id: non-empty string")
        if tid in seen:
            raise AttributionFARError(f"trials[{i}].trial_id: duplicate {tid!r}")
        seen.add(tid)
        if not isinstance(e.get("is_control"), bool):
            raise AttributionFARError(f"trials[{i}].is_control: boolean")
        if not isinstance(e.get("attributed"), bool):
            raise AttributionFARError(f"trials[{i}].attributed: boolean")
    return trials


def analyze(manifest, trials, *, far_threshold=DEFAULT_FAR_THRESHOLD) -> dict:
    """Measure how often an attribution method accepts a known-null control.

    Controls are trials built so that no real effect exists; a control that was
    attributed is a false accept. The verdict is RELIABLE if the false-accept
    rate over the controls is at or under the threshold, else UNRELIABLE. The
    corpus needs at least a few controls to be scored.
    """
    _validate_manifest(manifest)
    if not (0.0 <= far_threshold <= 1.0):
        raise AttributionFARError("far_threshold: between 0 and 1")
    _validate_log(trials)
    controls = [e for e in trials if e["is_control"]]
    reals = [e for e in trials if not e["is_control"]]
    if len(controls) < MIN_CONTROLS:
        raise AttributionFARError(f"trials: needs at least {MIN_CONTROLS} control trials")
    false_accepts = [e["trial_id"] for e in controls if e["attributed"]]
    far = round(len(false_accepts) / len(controls), 4)
    detection_rate = round(sum(e["attributed"] for e in reals) / len(reals), 4) if reals else None
    return {
        "verdict": RELIABLE if far <= far_threshold else UNRELIABLE,
        "environment_id": manifest["environment_id"],
        "far_threshold": far_threshold,
        "control_count": len(controls),
        "real_count": len(reals),
        "false_accept_rate": far,
        "detection_rate": detection_rate,
        "flagged": false_accepts,
        "does_not_prove": FAR_DOES_NOT_PROVE,
    }
