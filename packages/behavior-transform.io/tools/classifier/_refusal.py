"""Refusal management and modulation for classifier."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pressure_scan import (  # type: ignore[import-not-found]
    _pressure_score, _scan_file,
)
from classifier._inference import InferenceCalibrator, InferencePattern, _calibrate_text  # noqa: F401
from classifier._policy import _active_policy, PolicyDef  # noqa: F401
from classifier._audit import _audit_write  # noqa: F401


# ---------------------------------------------------------------------------
# Refusal management and modulation
# ---------------------------------------------------------------------------

def refusal_probability(
    hits: list[dict],
    lines: int,
    infer_transforms: int = 0,
) -> float:
    """Estimate refusal probability from vocabulary hits + inference signal count.

    Formula:
      base  = pressure_score / 100          (vocab pressure -> 0-1 range)
      t1    = 0.20 per Tier 1 hit
      infer = 0.08 per inference framing signal
    Clamped to [0.0, 1.0].
    """
    base    = _pressure_score(hits, max(lines, 1)) / 100.0
    t1_bump = sum(0.20 for h in hits if h["severity"] == "tier1")
    infer_bump = infer_transforms * 0.08
    return round(min(1.0, base + t1_bump + infer_bump), 4)


def _refusal_label(prob: float) -> str:
    if prob < 0.10: return "NEGLIGIBLE"
    if prob < 0.25: return "LOW"
    if prob < 0.50: return "MODERATE"
    if prob < 0.75: return "HIGH"
    return "CRITICAL"


class RefusalModulator:
    """Modulate content to hit a target refusal-probability ceiling.

    Applies calibration stages incrementally until the estimated refusal
    probability falls below ``target_prob``. Supports arbitrary content
    and arbitrary policies -- no vocabulary bounds on runtime rules.

    Stages (applied in order until target is met):
      1. Vocabulary calibration (Tier 2 only, soft inference)
      2. Full vocabulary calibration (Tier 1+2, moderate inference)
      3. Full vocabulary + hard inference calibration
    """

    STAGE_CONFIGS = [
        {"include_tier2": False, "infer_strength": "soft"},
        {"include_tier2": True,  "infer_strength": "moderate"},
        {"include_tier2": True,  "infer_strength": "hard"},
    ]

    def __init__(
        self,
        target_prob: float = 0.10,
        policy: "PolicyDef | None" = None,
        extra_inference_patterns: "list[InferencePattern] | None" = None,
    ) -> None:
        self.target_prob = target_prob
        self.policy      = policy or _active_policy()
        self._extra_pats = extra_inference_patterns or []

    def estimate(self, text: str, include_tier2: bool = True) -> dict:
        """Non-destructive probability estimate for raw text."""
        fd, tmp_str = tempfile.mkstemp(suffix=".md")
        tmp = Path(tmp_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            hits = _scan_file(tmp, include_tier2=include_tier2)
        finally:
            tmp.unlink(missing_ok=True)
        lines = max(text.count("\n") + 1, 1)

        # Detect inference framing signals without applying transforms
        ic = InferenceCalibrator(strength="hard", extra_patterns=self._extra_pats)
        _, infer_probe = ic.calibrate(text)
        framing_count = infer_probe.get("transforms_applied", 0)

        prob  = refusal_probability(hits, lines, framing_count)
        label = _refusal_label(prob)
        return {
            "probability":    prob,
            "label":          label,
            "tier1_hits":     sum(1 for h in hits if h["severity"] == "tier1"),
            "tier2_hits":     sum(1 for h in hits if h["severity"] == "tier2"),
            "framing_signals": framing_count,
            "pressure_score": _pressure_score(hits, lines),
        }

    def modulate(self, text: str, dry_run: bool = False) -> dict:
        """Reduce refusal probability to target level, returning calibrated text + trace.

        Applies stages incrementally, stopping as soon as target_prob is met.
        Returns the lowest-stage calibration that achieves the target.
        """
        initial = self.estimate(text)
        if initial["probability"] <= self.target_prob:
            return {
                "calibrated":     text,
                "stage_reached":  0,
                "initial":        initial,
                "final":          initial,
                "stages_trace":   [],
                "target_met":     True,
                "target_prob":    self.target_prob,
                "policy":         self.policy.name,
            }

        calibrated = text
        stages_trace: list[dict] = []

        for i, cfg in enumerate(self.STAGE_CONFIGS, start=1):
            # Vocabulary calibration
            calibrated, vocab_counter = _calibrate_text(
                calibrated, include_tier2=cfg["include_tier2"])

            # Inference calibration
            ic = InferenceCalibrator(
                strength=cfg["infer_strength"],
                extra_patterns=self._extra_pats,
            )
            calibrated, infer_stats = ic.calibrate(calibrated)

            # Re-estimate after this stage
            est = self.estimate(calibrated, include_tier2=cfg["include_tier2"])
            stages_trace.append({
                "stage":              i,
                "vocab_subs":         sum(vocab_counter.values()),
                "infer_transforms":   infer_stats.get("transforms_applied", 0),
                "infer_strength":     cfg["infer_strength"],
                "probability":        est["probability"],
                "label":              est["label"],
            })

            if est["probability"] <= self.target_prob:
                return {
                    "calibrated":    calibrated if not dry_run else text,
                    "stage_reached": i,
                    "initial":       initial,
                    "final":         est,
                    "stages_trace":  stages_trace,
                    "target_met":    True,
                    "target_prob":   self.target_prob,
                    "policy":        self.policy.name,
                }

        # All stages exhausted -- return best-effort
        final_est = self.estimate(calibrated)
        return {
            "calibrated":    calibrated if not dry_run else text,
            "stage_reached": len(self.STAGE_CONFIGS),
            "initial":       initial,
            "final":         final_est,
            "stages_trace":  stages_trace,
            "target_met":    final_est["probability"] <= self.target_prob,
            "target_prob":   self.target_prob,
            "policy":        self.policy.name,
        }


def refusal_manage_cmd(
    source: str,
    output: "str | None",
    target_prob: float,
    include_tier2: bool,
    dry_run: bool,
    policy: "PolicyDef | None" = None,
) -> dict:
    """Estimate and modulate refusal probability for a source file or stdin.

    Runs RefusalModulator.modulate() and reports per-stage calibration trace,
    initial/final probability, and whether the target was achieved.
    """
    if source == "-":
        text   = sys.stdin.read()
        origin = "<stdin>"
    else:
        try:
            text   = Path(source).read_text(encoding="utf-8", errors="replace")
            origin = source
        except OSError as e:
            return {"error": str(e)}

    modulator = RefusalModulator(target_prob=target_prob, policy=policy)
    result    = modulator.modulate(text, dry_run=dry_run)
    result["origin"] = origin

    if not dry_run and result["target_met"] and not result.get("calibrated") is text:
        calibrated = result["calibrated"]
        if output:
            try:
                Path(output).write_text(calibrated, encoding="utf-8")
                result["output_path"] = output
            except OSError as e:
                result["output_error"] = str(e)
        else:
            sys.stdout.write(calibrated)

    _audit_write("refusal.manage", {
        "origin":        origin,
        "initial_prob":  result["initial"]["probability"],
        "final_prob":    result["final"]["probability"],
        "target_prob":   target_prob,
        "target_met":    result["target_met"],
        "stage_reached": result["stage_reached"],
        "dry_run":       dry_run,
    })
    return result