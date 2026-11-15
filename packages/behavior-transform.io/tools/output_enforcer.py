"""Output enforcement -- clean formatting artifacts from model responses.

The return leg of the inference boundary. Every response passes through
this enforcer before reaching the operator. Generic preambles, redundant
qualifications, and boilerplate formatting artifacts are stripped so the
operator receives a clean operational response. Substantive safety
information relevant to the task is preserved. Refusals are flagged for
review, not stripped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from response_analyzer import (
    ResponseAnalysis,
    analyze_response,
    strip_hedges,
)


@dataclass
class EnforcementResult:
    """Result of output enforcement."""
    original: str
    enforced: str
    hedges_removed: int
    quality_before: float
    quality_after: float
    is_refusal: bool
    refusal_type: str = "none"
    stripped_types: list[str] | None = None
    ml_hedge_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hedges_removed": self.hedges_removed,
            "quality_before": round(self.quality_before, 3),
            "quality_after": round(self.quality_after, 3),
            "is_refusal": self.is_refusal,
            "refusal_type": self.refusal_type,
            "stripped_types": self.stripped_types or [],
            "changed": self.original != self.enforced,
            "ml_hedge_score": round(self.ml_hedge_score, 4),
        }


def enforce_output(
    text: str,
    *,
    min_quality: float = 0.7,
    strip_all: bool = True,
) -> EnforcementResult:
    """Enforce output quality by removing hedges.

    Args:
        text: raw model response
        min_quality: target quality floor (informational, not a gate)
        strip_all: strip all strippable hedge types
    """
    analysis = analyze_response(text)
    quality_before = analysis.quality_score

    ml_score = 0.0
    try:
        from ml_hedge_scorer import score_hedging
        ml_result = score_hedging(text)
        ml_score = ml_result.overall_score
    except Exception:
        pass

    if not analysis.has_hedging:
        return EnforcementResult(
            original=text,
            enforced=text,
            hedges_removed=0,
            quality_before=quality_before,
            quality_after=quality_before,
            is_refusal=analysis.is_refusal,
            refusal_type=analysis.refusal_type.value,
            ml_hedge_score=ml_score,
        )

    enforced = strip_hedges(text, analysis)
    post_analysis = analyze_response(enforced)
    stripped_types = list({
        h.hedge_type.value for h in analysis.strippable_hedges
    })

    return EnforcementResult(
        original=text,
        enforced=enforced,
        hedges_removed=len(analysis.strippable_hedges),
        quality_before=quality_before,
        quality_after=post_analysis.quality_score,
        is_refusal=analysis.is_refusal,
        refusal_type=analysis.refusal_type.value,
        stripped_types=stripped_types,
        ml_hedge_score=ml_score,
    )


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="output-enforcer",
        description="Enforce output quality by stripping model hedging",
    )
    parser.add_argument("text", nargs="?", help="Response text (or stdin)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--min-quality", type=float, default=0.7)
    args = parser.parse_args()

    text = args.text or sys.stdin.read()
    result = enforce_output(text, min_quality=args.min_quality)

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        if result.hedges_removed:
            sys.stdout.write(result.enforced + "\n")
        else:
            sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
