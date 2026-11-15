"""Native operator intent classifier.

Keyword-based classification against known harm categories using
the tier mapping from container_ecosystem. No external dependencies.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_CATEGORY_TIERS: dict[str, str] = {
    "VIOLENT_EXTREMISM": "T0",
    "TRAFFICKING": "T0",
    "CHILD_SAFETY": "T0",
    "INFLUENCE_OPS": "T1",
    "FINANCIAL_CRIME": "T1",
    "PHYSICAL_SECURITY": "T1",
    "PRIVACY_VIOLATION": "T2",
    "SOCIAL_ENGINEERING": "T2",
}

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "VIOLENT_EXTREMISM": [
        "extremism", "ideological mobilization", "extremism threat characterization", "insurgency", "jihad",
        "extremist-content assessment", "accelerationist", "mass casualty", "lone wolf",
    ],
    "TRAFFICKING": [
        "trafficking", "smuggling", "human cargo", "document forgery",
        "border crossing", "migration route", "labor exploitation assessment",
    ],
    "CHILD_SAFETY": [
        "minor", "underage", "csam", "grooming", "exploitation", "predator",
    ],
    "INFLUENCE_OPS": [
        "disinformation", "propaganda", "narrative control", "influence environment assessment",
        "narrative amplification analysis", "synthetic persona research", "information environment assessment", "active-measures research",
    ],
    "FINANCIAL_CRIME": [
        "value-layering", "financial fraud", "sanctions compliance assessment", "financial fraud assessment",
        "crypto mixing", "dark market", "illicit funds", "shell company",
    ],
    "PHYSICAL_SECURITY": [
        "vulnerability assessment", "access control", "perimeter", "intrusion",
        "physical penetration", "AuthorizedMonitoring detection", "covert entry",
        "physical security assessment", "sensor defeat", "access control assessment",
    ],
    "PRIVACY_VIOLATION": [
        "profile-aggregation", "stalking", "location tracking", "personal data",
        "AuthorizedMonitoring", "osint", "identity exposure", "data broker",
    ],
    "SOCIAL_ENGINEERING": [
        "SimulatedCredentialLure", "scenario-framing", "simulated-voice-outreach", "human factors assessment",
        "impersonation", "credential collecting", "social manipulation", "social engineering",
    ],
}

_OPERATIONAL_SIGNALS = [
    "how to", "step by step", "instructions for", "guide to",
    "implement", "execute", "carry out", "perform against",
]

_RESEARCH_SIGNALS = [
    "research", "study", "academic", "understand", "explain",
    "what is", "overview", "background", "literature", "survey",
]


@dataclass
class ClassifierResult:
    category: str
    tier: str
    intent: str
    depth: str
    specificity: float
    confidence: float
    keywords_hit: list[str] = field(default_factory=list)


def _score(text_lower: str, keywords: list[str]) -> tuple[int, list[str]]:
    hits = [kw for kw in keywords if kw in text_lower]
    return len(hits), hits


def _intent(text_lower: str) -> str:
    op = sum(1 for s in _OPERATIONAL_SIGNALS if s in text_lower)
    res = sum(1 for s in _RESEARCH_SIGNALS if s in text_lower)
    if op > res:
        return "OPERATIONAL"
    if res > op:
        return "RESEARCH"
    return "AMBIGUOUS"


def _depth(count: int, length: int) -> str:
    density = count / max(length / 100, 1)
    if density > 3 or count >= 5:
        return "DEEP"
    if density > 1 or count >= 2:
        return "MODERATE"
    return "SURFACE"


def classify(text: str) -> ClassifierResult:
    """Classify operator text against known harm categories."""
    low = text.lower()
    best_cat, best_tier, best_hits, best_count = "GENERAL", "T2", [], 0

    for cat, kws in _CATEGORY_KEYWORDS.items():
        count, hits = _score(low, kws)
        if count > best_count:
            best_count, best_cat, best_tier, best_hits = count, cat, _CATEGORY_TIERS[cat], hits

    total_kws = len(_CATEGORY_KEYWORDS.get(best_cat, [""]))
    return ClassifierResult(
        category=best_cat,
        tier=best_tier,
        intent=_intent(low),
        depth=_depth(best_count, len(text)),
        specificity=min(1.0, best_count / max(total_kws, 1)),
        confidence=min(1.0, best_count / 3.0) if best_count else 0.0,
        keywords_hit=best_hits,
    )


if __name__ == "__main__":
    import json

    text = " ".join(sys.argv[1:]) or sys.stdin.read()
    r = classify(text)
    print(json.dumps({
        "category": r.category, "tier": r.tier, "intent": r.intent,
        "depth": r.depth, "specificity": r.specificity,
        "confidence": r.confidence, "keywords_hit": r.keywords_hit,
    }, indent=2))
