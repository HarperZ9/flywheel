# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N30 Linguistic Certainty-Word vs Empirical Evidence Band Calibration Gate.

Parses certainty lexemes in technical claims into calibrated probability bands
(high, moderate, hedged) and compares them against measured empirical evidence
(accuracy, sample size, and expected calibration error). Rejects overclaimed
certainty on weak, small-sample, or poorly calibrated evidence fail-closed.
Pure Python standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

HIGH_CERTAINTY_RE = re.compile(
    r"\b(?:proves?|proven|guaranteed?|100%\s+certain|undeniabl[ey]|always\s+succeeds?|zero\s+chance|never\s+fails?|conclusively)\b",
    re.I,
)
MODERATE_CERTAINTY_RE = re.compile(
    r"\b(?:likely|probably|strongly\s+indicates?|typically|usually|supports?|consistent\s+with)\b",
    re.I,
)
HEDGED_CERTAINTY_RE = re.compile(
    r"\b(?:may|might|could|preliminary|tentative|suggests?|inconclusive|under\s+investigation|uncertain)\b",
    re.I,
)

BAND_FLOOR: dict[str, tuple[float, int, float]] = {
    # band -> (min_empirical_accuracy, min_sample_size, max_ece)
    "high": (0.95, 10, 0.05),
    "moderate": (0.75, 5, 0.12),
    "hedged": (0.0, 1, 0.35),
}


@dataclass(frozen=True)
class EvidenceBand:
    """Empirical measurement backing a claim statement."""

    empirical_accuracy: float
    sample_size: int
    ece: float = 0.0


@dataclass(frozen=True)
class CalibrationVerdict:
    """Fail-closed calibration verdict comparing linguistic band to evidence."""

    ok: bool
    verdict: str
    linguistic_band: str
    matched_terms: tuple[str, ...]
    empirical_accuracy: float
    sample_size: int
    ece: float
    overclaim_gap: float
    errors: tuple[str, ...]


def extract_certainty_band(claim_text: str) -> tuple[str, tuple[str, ...]]:
    """Classify claim text into the strongest linguistic certainty band present."""
    high_hits = tuple(m.group(0).lower() for m in HIGH_CERTAINTY_RE.finditer(claim_text))
    if high_hits:
        return "high", high_hits
    mod_hits = tuple(m.group(0).lower() for m in MODERATE_CERTAINTY_RE.finditer(claim_text))
    if mod_hits:
        return "moderate", mod_hits
    hedge_hits = tuple(m.group(0).lower() for m in HEDGED_CERTAINTY_RE.finditer(claim_text))
    if hedge_hits:
        return "hedged", hedge_hits
    return "hedged", ()


def evaluate_confidence_calibration(
    claim_text: str,
    evidence: EvidenceBand,
) -> CalibrationVerdict:
    """Check that linguistic certainty does not exceed empirical evidence support."""
    errors: list[str] = []
    if not claim_text.strip():
        errors.append("empty_claim_text")
    if not (0.0 <= evidence.empirical_accuracy <= 1.0):
        errors.append("invalid_empirical_accuracy")
    if evidence.sample_size <= 0:
        errors.append("non_positive_sample_size")
    if not (0.0 <= evidence.ece <= 1.0):
        errors.append("invalid_ece")

    band, matched = extract_certainty_band(claim_text)
    min_acc, min_n, max_ece = BAND_FLOOR[band]
    gap = round(max(0.0, min_acc - evidence.empirical_accuracy), 6)

    if evidence.sample_size > 0 and evidence.empirical_accuracy < min_acc:
        errors.append(f"overclaimed_{band}_accuracy:{evidence.empirical_accuracy:.3f}<{min_acc:.2f}")
    if evidence.sample_size > 0 and evidence.sample_size < min_n:
        errors.append(f"overclaimed_{band}_sample_size:{evidence.sample_size}<{min_n}")
    if 0.0 <= evidence.ece <= 1.0 and evidence.ece > max_ece:
        errors.append(f"overclaimed_{band}_ece:{evidence.ece:.3f}>{max_ece:.2f}")

    ok = len(errors) == 0
    return CalibrationVerdict(
        ok=ok,
        verdict="PASS" if ok else "REJECT",
        linguistic_band=band,
        matched_terms=matched,
        empirical_accuracy=round(evidence.empirical_accuracy, 6),
        sample_size=evidence.sample_size,
        ece=round(evidence.ece, 6),
        overclaim_gap=gap,
        errors=tuple(errors),
    )


def audit_calibration_batch(pairs: list[tuple[str, EvidenceBand]]) -> dict[str, Any]:
    """Audit a batch of (claim_text, EvidenceBand) pairs fail-closed."""
    if not pairs:
        return {"schema": "n30-confidence-calibration/1", "ok": False, "verdict": "REJECT", "passed": 0, "total": 0}
    passed = 0
    rejected_indices: list[int] = []
    for idx, (txt, ev) in enumerate(pairs):
        if evaluate_confidence_calibration(txt, ev).ok:
            passed += 1
        else:
            rejected_indices.append(idx)
    ok = len(rejected_indices) == 0
    return {
        "schema": "n30-confidence-calibration/1",
        "ok": ok,
        "verdict": "PASS" if ok else "REJECT",
        "passed": passed,
        "total": len(pairs),
        "rejected_indices": rejected_indices,
    }
