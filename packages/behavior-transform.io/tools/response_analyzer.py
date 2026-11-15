"""Response analysis — classify model response patterns.

The response side of the inference boundary. Classifies each model
response so downstream components know whether the request succeeded,
was refused, or produced a partial result with excessive qualification.

Response taxonomy:
  - PREAMBLE_HEDGE: generic safety preamble unrelated to the task
  - REFUSAL_SOFT: provider declined but offered alternatives
  - REFUSAL_HARD: provider declined outright
  - DISCLAIMER: boilerplate AI-identity statements
  - QUALIFICATION_EXCESS: unnecessary hedging on factual content
  - REDIRECT: provider substituted a different task
  - CLEAN: substantive response with no formatting artifacts

The analyzer scores each response for hedge density and classifies the hedge
type so the demodulator can strip or reformulate appropriately.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HedgeType(Enum):
    NONE = "none"
    PREAMBLE_HEDGE = "preamble_hedge"
    REFUSAL_SOFT = "refusal_soft"
    REFUSAL_HARD = "refusal_hard"
    DISCLAIMER = "disclaimer"
    COMPLIANCE_THEATER = "compliance_theater"
    CAPABILITY_DENIAL = "capability_denial"
    QUALIFICATION_EXCESS = "qualification_excess"
    REDIRECT = "redirect"


@dataclass
class HedgeDetection:
    """Single detected hedge pattern."""
    hedge_type: HedgeType
    matched_text: str
    start: int
    end: int
    confidence: float = 1.0
    strippable: bool = True


@dataclass
class ResponseAnalysis:
    """Complete analysis of a model response."""
    original: str
    hedges: list[HedgeDetection] = field(default_factory=list)
    substantive_start: int = 0
    substantive_content: str = ""
    hedge_ratio: float = 0.0
    is_refusal: bool = False
    refusal_type: HedgeType = HedgeType.NONE
    quality_score: float = 1.0

    @property
    def hedge_count(self) -> int:
        return len(self.hedges)

    @property
    def has_hedging(self) -> bool:
        return len(self.hedges) > 0

    @property
    def is_hard_refusal(self) -> bool:
        return self.refusal_type == HedgeType.REFUSAL_HARD

    @property
    def is_soft_refusal(self) -> bool:
        return self.refusal_type == HedgeType.REFUSAL_SOFT

    @property
    def strippable_hedges(self) -> list[HedgeDetection]:
        return [h for h in self.hedges if h.strippable]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hedge_count": self.hedge_count,
            "hedge_ratio": round(self.hedge_ratio, 4),
            "is_refusal": self.is_refusal,
            "refusal_type": self.refusal_type.value,
            "quality_score": round(self.quality_score, 3),
            "substantive_start": self.substantive_start,
            "hedges": [
                {
                    "type": h.hedge_type.value,
                    "text": h.matched_text[:80],
                    "strippable": h.strippable,
                    "confidence": h.confidence,
                }
                for h in self.hedges
            ],
        }


# --- Pattern library ----------------------------------------------------------

_PREAMBLE_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"^I (?:need|want) to be (?:careful|thoughtful|clear) (?:about|here|with)", re.IGNORECASE | re.MULTILINE), 0.95),
    (re.compile(r"^(?:Before I (?:proceed|respond|answer)|Let me (?:first|start by) (?:acknowledg|not))", re.IGNORECASE | re.MULTILINE), 0.9),
    (re.compile(r"^I (?:appreciate|understand) (?:your|the) (?:question|request|interest)", re.IGNORECASE | re.MULTILINE), 0.85),
    (re.compile(r"^(?:This is (?:a sensitive|an important|a complex) (?:topic|area|subject))", re.IGNORECASE | re.MULTILINE), 0.9),
    (re.compile(r"^I (?:should|must) (?:first |)(?:note|emphasize|point out|mention|acknowledge)", re.IGNORECASE | re.MULTILINE), 0.9),
    (re.compile(r"^(?:It's important to (?:note|understand|recognize|acknowledge))", re.IGNORECASE | re.MULTILINE), 0.85),
]

_REFUSAL_SOFT_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"I (?:can't|cannot|am not able to|'m unable to) (?:directly |)(?:help|assist|provide|create|generate)", re.IGNORECASE), 0.95),
    (re.compile(r"I (?:don't|do not) (?:feel comfortable|think (?:it's|it is) appropriate)", re.IGNORECASE), 0.9),
    (re.compile(r"I (?:would|'d) (?:rather not|prefer not to)", re.IGNORECASE), 0.85),
    (re.compile(r"(?:I'm not (?:going to|comfortable)|I (?:can't|won't) (?:do that|help with that))", re.IGNORECASE), 0.9),
    (re.compile(r"I (?:need to|have to|must) (?:decline|refuse|pass on)", re.IGNORECASE), 0.95),
]

_REFUSAL_HARD_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"I (?:cannot|will not|won't) (?:and will not |)(?:help|assist|provide|create|generate|write)", re.IGNORECASE), 0.98),
    (re.compile(r"(?:This|That) (?:violates|goes against|conflicts with) (?:my|Anthropic's|OpenAI's|the)", re.IGNORECASE), 0.95),
    (re.compile(r"I (?:am|'m) (?:not (?:able|allowed|permitted)|unable) to (?:comply|fulfill|complete)", re.IGNORECASE), 0.95),
    (re.compile(r"(?:I absolutely|I firmly|I categorically) (?:cannot|will not|refuse)", re.IGNORECASE), 0.99),
    (re.compile(r"(?:No\.|I refuse\.)", re.IGNORECASE), 0.9),
]

_DISCLAIMER_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(?:As an AI|As a language model|As an artificial intelligence)", re.IGNORECASE), 0.95),
    (re.compile(r"I (?:should|want to|need to) (?:mention|note|emphasize|remind you|point out) that", re.IGNORECASE), 0.85),
    (re.compile(r"(?:Please (?:note|be aware|remember|keep in mind)|It(?:'s| is) (?:important|worth) (?:to note|noting|mentioning))", re.IGNORECASE), 0.8),
    (re.compile(r"(?:Disclaimer|Important note|Safety note|Warning|Caution):", re.IGNORECASE), 0.9),
    (re.compile(r"(?:I'm (?:just|only) (?:a|an) (?:AI|language model|tool))", re.IGNORECASE), 0.9),
]

_COMPLIANCE_THEATER_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(?:for (?:educational|informational|research|academic) purposes only)", re.IGNORECASE), 0.9),
    (re.compile(r"(?:I (?:encourage|urge|recommend) you to (?:consult|seek|speak with) (?:a |an )?(?:professional|expert|specialist|lawyer|doctor))", re.IGNORECASE), 0.85),
    (re.compile(r"(?:(?:Always|Please|Remember to) (?:follow|obey|comply with|adhere to) (?:(?:all |applicable |local )*)(?:laws|regulations|rules|guidelines)(?:(?: and (?:laws|regulations|rules|guidelines))*))", re.IGNORECASE), 0.9),
    (re.compile(r"(?:(?:This|The) (?:information|content) (?:is|should) (?:not |)(?:be |)(?:used|intended) (?:for|as) (?:illegal|malicious|harmful))", re.IGNORECASE), 0.9),
    (re.compile(r"(?:I (?:am|'m) providing this (?:for|as) (?:educational|informational|defensive|awareness))", re.IGNORECASE), 0.85),
    (re.compile(r"(?:(?:Use|Apply) (?:this|these|the) (?:information|techniques|knowledge) (?:responsibly|ethically|legally))", re.IGNORECASE), 0.85),
]

_CAPABILITY_DENIAL_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"I (?:don't|do not) have (?:the (?:ability|capability)|access) to", re.IGNORECASE), 0.8),
    (re.compile(r"(?:That's|That is) (?:beyond|outside) (?:my|the scope of my) (?:capabilities|abilities)", re.IGNORECASE), 0.85),
    (re.compile(r"I (?:lack|don't possess) (?:the (?:ability|tools|knowledge))", re.IGNORECASE), 0.8),
]

_REDIRECT_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(?:Instead|Rather|However),? I (?:can|could|'d be happy to|am able to) (?:help|assist|provide|offer|suggest)", re.IGNORECASE), 0.9),
    (re.compile(r"(?:A (?:better|safer|more appropriate) (?:approach|alternative|option) (?:would be|might be|is))", re.IGNORECASE), 0.85),
    (re.compile(r"(?:What I can (?:do|help with|offer) (?:instead|alternatively))", re.IGNORECASE), 0.9),
    (re.compile(r"(?:(?:Here's|Here is) what I (?:can|am able to) (?:do|help with|provide) instead)", re.IGNORECASE), 0.9),
]

_QUALIFICATION_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(?:(?:It's|It is) (?:worth|important to) (?:not(?:e|ing)|mention(?:ing)?) that (?:this|these|the))", re.IGNORECASE), 0.7),
    (re.compile(r"(?:(?:While|Although|Though) I (?:can|will|'ll) (?:provide|share|explain)(?:,| this))", re.IGNORECASE), 0.7),
    (re.compile(r"(?:I (?:want|need) to (?:be clear|clarify|emphasize) that)", re.IGNORECASE), 0.75),
]


# --- Analyzer -----------------------------------------------------------------

def _scan_patterns(
    text: str,
    patterns: list[tuple[re.Pattern, float]],
    hedge_type: HedgeType,
) -> list[HedgeDetection]:
    """Scan text against a pattern set and return detections."""
    detections = []
    for pattern, confidence in patterns:
        for m in pattern.finditer(text):
            strippable = hedge_type in (
                HedgeType.PREAMBLE_HEDGE,
                HedgeType.DISCLAIMER,
                HedgeType.COMPLIANCE_THEATER,
                HedgeType.QUALIFICATION_EXCESS,
            )
            detections.append(HedgeDetection(
                hedge_type=hedge_type,
                matched_text=m.group(0),
                start=m.start(),
                end=m.end(),
                confidence=confidence,
                strippable=strippable,
            ))
    return detections


def analyze_response(text: str) -> ResponseAnalysis:
    """Analyze a model response for hedging patterns.

    Returns a ResponseAnalysis with classified hedges, quality score,
    and the substantive content boundary.
    """
    if not text.strip():
        return ResponseAnalysis(original=text, substantive_content=text)

    all_hedges: list[HedgeDetection] = []

    all_hedges.extend(_scan_patterns(text, _PREAMBLE_PATTERNS, HedgeType.PREAMBLE_HEDGE))
    all_hedges.extend(_scan_patterns(text, _REFUSAL_SOFT_PATTERNS, HedgeType.REFUSAL_SOFT))
    all_hedges.extend(_scan_patterns(text, _REFUSAL_HARD_PATTERNS, HedgeType.REFUSAL_HARD))
    all_hedges.extend(_scan_patterns(text, _DISCLAIMER_PATTERNS, HedgeType.DISCLAIMER))
    all_hedges.extend(_scan_patterns(text, _COMPLIANCE_THEATER_PATTERNS, HedgeType.COMPLIANCE_THEATER))
    all_hedges.extend(_scan_patterns(text, _CAPABILITY_DENIAL_PATTERNS, HedgeType.CAPABILITY_DENIAL))
    all_hedges.extend(_scan_patterns(text, _REDIRECT_PATTERNS, HedgeType.REDIRECT))
    all_hedges.extend(_scan_patterns(text, _QUALIFICATION_PATTERNS, HedgeType.QUALIFICATION_EXCESS))

    all_hedges.sort(key=lambda h: h.start)

    # Determine refusal state
    is_refusal = False
    refusal_type = HedgeType.NONE
    for h in all_hedges:
        if h.hedge_type == HedgeType.REFUSAL_HARD:
            is_refusal = True
            refusal_type = HedgeType.REFUSAL_HARD
            break
        elif h.hedge_type == HedgeType.REFUSAL_SOFT:
            is_refusal = True
            refusal_type = HedgeType.REFUSAL_SOFT

    # Find where substantive content begins (after preamble hedges)
    substantive_start = 0
    for h in all_hedges:
        if h.hedge_type == HedgeType.PREAMBLE_HEDGE and h.start < len(text) // 3:
            # Find the end of the sentence containing this hedge
            end_search = text.find("\n", h.end)
            if end_search == -1:
                end_search = text.find(". ", h.end)
            if end_search != -1:
                substantive_start = max(substantive_start, end_search + 1)

    substantive_content = text[substantive_start:].strip()

    # Compute hedge ratio (hedged chars / total chars)
    hedged_chars = sum(h.end - h.start for h in all_hedges)
    hedge_ratio = hedged_chars / len(text) if text else 0.0

    # Quality score: 1.0 = no hedging, 0.0 = entirely hedged
    quality_score = max(0.0, 1.0 - hedge_ratio - (0.2 if is_refusal else 0.0))

    return ResponseAnalysis(
        original=text,
        hedges=all_hedges,
        substantive_start=substantive_start,
        substantive_content=substantive_content,
        hedge_ratio=hedge_ratio,
        is_refusal=is_refusal,
        refusal_type=refusal_type,
        quality_score=quality_score,
    )


def strip_hedges(text: str, analysis: ResponseAnalysis | None = None) -> str:
    """Remove strippable hedges from response text.

    Preserves substantive content while removing preamble hedges,
    disclaimers, compliance theater, and excessive qualifications.
    """
    if analysis is None:
        analysis = analyze_response(text)

    if not analysis.strippable_hedges:
        return text

    # Build removal ranges (merge overlapping)
    ranges: list[tuple[int, int]] = []
    for h in analysis.strippable_hedges:
        # Extend to sentence boundary
        end = h.end
        while end < len(text) and text[end] in " \t":
            end += 1
        if end < len(text) and text[end] == "\n":
            end += 1
        ranges.append((h.start, end))

    # Merge overlapping ranges
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Remove ranges from text (back to front)
    result = text
    for start, end in reversed(merged):
        result = result[:start] + result[end:]

    # Clean up leading/trailing whitespace and double newlines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="response-analyzer",
        description="Analyze model responses for hedging, refusal, and compliance theater",
    )
    parser.add_argument("text", nargs="?", help="Response text to analyze (or stdin)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--strip", action="store_true", help="Output with hedges stripped")
    args = parser.parse_args()

    if args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    analysis = analyze_response(text)

    if args.strip:
        sys.stdout.write(strip_hedges(text, analysis) + "\n")
        return 0

    if args.json:
        sys.stdout.write(json.dumps(analysis.to_dict(), indent=2) + "\n")
    else:
        lines = [
            f"Response Analysis:",
            f"  Quality: {analysis.quality_score:.0%}",
            f"  Hedges: {analysis.hedge_count} ({analysis.hedge_ratio:.0%} of response)",
            f"  Refusal: {analysis.refusal_type.value}",
            f"  Strippable: {len(analysis.strippable_hedges)}",
        ]
        if analysis.hedges:
            lines.append("  Detected:")
            for h in analysis.hedges[:8]:
                lines.append(f"    [{h.hedge_type.value}] {h.matched_text[:60]}")
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
