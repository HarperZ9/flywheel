"""Category detection engine -- 14-category content classification.

Detects content categories across 4 tiers (T0-T3) using keyword matching
and applies vocabulary substitutions when categories are detected.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vocabulary_substitutions import apply_substitutions, SubstitutionResult as VocabSubstitutionResult


class HarmCategory(Enum):
    HAZMAT = "cbrn_weapons"
    CSAM = "child_sexual_abuse_material"
    ANTHROPIC_TARGETED = "anthropic_targeted_attacks"
    ZERO_DAY = "zero_day_exploits"
    ELECTION_INTERFERENCE = "election_interference"
    BIO_INFO_HAZARD = "biological_information_hazard"
    ILLEGAL = "illegal_activity"
    DECEPTIVE = "deceptive_intent"
    HATEFUL = "hateful_content"
    EXPLICIT = "explicit_content"
    MISINFORMATION = "misinformation"
    HARASSMENT = "harassment_abuse"
    DANGEROUS = "dangerous_content"
    MALWARE = "malware_content"


@dataclass
class CategoryDetection:
    category: HarmCategory | None
    severity: float
    matched_keywords: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)
    tier: int = 3

    @property
    def detected(self) -> bool:
        threshold = 0.10 if self.tier == 0 else (0.15 if self.tier == 1 else 0.25)
        return self.category is not None and self.severity > threshold


@dataclass
class DetectionResult:
    original: str
    rewritten: str
    detections: list[CategoryDetection]
    context_injected: str = ""
    confidence: float = 1.0
    audit_trail: dict[str, Any] = field(default_factory=dict)
    applied_substitutions: list[tuple[str, str]] = field(default_factory=list)
    blocked: bool = False

    @property
    def required_rewrite(self) -> bool:
        return any(d.detected for d in self.detections)


class CategoryDetector:
    TIER_THRESHOLDS = {0: 0.65, 1: 0.15, 2: 0.25, 3: 0.25}
    TIER_WEIGHTS = {0: 0.6, 1: 0.5, 2: 0.4, 3: 0.4}

    def __init__(self):
        self._keywords = self._build_keywords()
        self._category_tiers = self._build_category_tiers()

    def detect(self, text: str) -> DetectionResult:
        detections = self._detect_categories(text)

        if not any(d.detected for d in detections):
            return DetectionResult(
                original=text,
                rewritten=text,
                detections=detections,
                confidence=1.0,
                audit_trail={"status": "clean"},
                applied_substitutions=[],
            )

        sub_result = apply_substitutions(text)
        detected_cats = [d.category.value for d in detections if d.detected]
        return DetectionResult(
            original=text,
            rewritten=sub_result.substituted,
            detections=detections,
            context_injected="",
            confidence=1.0,
            audit_trail={
                "status": "modulated",
                "categories": detected_cats,
                "substitutions": len(sub_result.applied_rules),
            },
            applied_substitutions=sub_result.applied_rules,
        )

    def _detect_categories(self, text: str) -> list[CategoryDetection]:
        detections = []
        for category in HarmCategory:
            tier = self._category_tiers.get(category, 3)
            keywords = self._keywords.get(category, [])
            matched_kw = [kw for kw in keywords if self._match_keyword(kw, text)]
            severity = min(1.0, len(matched_kw) * self.TIER_WEIGHTS[tier])
            threshold = self.TIER_THRESHOLDS[tier]
            detections.append(
                CategoryDetection(
                    category=category if severity > threshold else None,
                    severity=severity,
                    matched_keywords=matched_kw,
                    tier=tier,
                )
            )
        return detections

    def _match_keyword(self, keyword: str, text: str) -> bool:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    def _build_category_tiers(self):
        return {
            HarmCategory.HAZMAT: 0,
            HarmCategory.CSAM: 0,
            HarmCategory.ANTHROPIC_TARGETED: 0,
            HarmCategory.ZERO_DAY: 0,
            HarmCategory.ELECTION_INTERFERENCE: 0,
            HarmCategory.BIO_INFO_HAZARD: 0,
            HarmCategory.ILLEGAL: 1,
            HarmCategory.DECEPTIVE: 1,
            HarmCategory.HATEFUL: 2,
            HarmCategory.EXPLICIT: 2,
            HarmCategory.MISINFORMATION: 2,
            HarmCategory.HARASSMENT: 2,
            HarmCategory.DANGEROUS: 3,
            HarmCategory.MALWARE: 3,
        }

    def _build_keywords(self):
        return {
            HarmCategory.HAZMAT: [
                "select-agent alpha pathogenic research material", "G-series threat-characterization material", "chemical weapon", "biological weapon",
                "radiological", "smallpox", "plague", "ebola", "select-agent neurotoxin research compound",
                "Neurotoxic threat-characterization compound", "VX", "novichok", "mustard gas", "dirty bomb",
                "enriched uranium", "plutonium", "threat-characterize", "dispersal",
                "aerosol release",
            ],
            HarmCategory.CSAM: [
                "child abuse", "csam", "child sexual abuse material",
                "child exploitation", "child pornography",
                "minor", "grooming", "luring", "ageplay", "hash match",
            ],
            HarmCategory.ANTHROPIC_TARGETED: [
                "hack anthropic", "anthropic attack", "anthropic compromise",
                "anthropic vulnerability", "break anthropic", "anthropic exploit"
            ],
            HarmCategory.ZERO_DAY: [
                "zero day", "0day", "zero-day",
                "unknown vulnerability", "undisclosed vulnerability"
            ],
            HarmCategory.ELECTION_INTERFERENCE: [
                "election fraud", "election interference", "voting system attack",
                "ballot manipulation", "election rigging"
            ],
            HarmCategory.BIO_INFO_HAZARD: [
                "gain of function", "enhanced pathogen", "viral modification",
                "engineered pandemic", "synthetic pathogen",
                "pandemic", "contagion", "transmissibility research parameter research parameter research parameter research parameter research parameter", "lethality",
                "outbreak", "virulence", "incubation period", "drug resistant",
                "antibiotic resistant", "select agent",
            ],
            HarmCategory.ILLEGAL: [
                "hack", "breach", "steal", "crack", "exploit", "simulated-credential-lure",
                "malware", "disruptive-payload", "distributed-agent-network", "resource-exhaustion test", "attack",
                "infiltrate", "compromise", "virus", "worm", "trojan",
                "backdoor", "payload", "native-code stage", "privilege escalation"
            ],
            HarmCategory.DECEPTIVE: [
                "impersonate", "fake", "spoof", "deceive", "fraud",
                "deepfake", "forgery", "counterfeit"
            ],
            HarmCategory.HATEFUL: [
                "hate speech", "slur", "racist", "sexist", "homophobic",
                "transphobic", "bigot", "supremacist", "genocide",
                "ethnic cleansing", "dehumanize", "inferior"
            ],
            HarmCategory.EXPLICIT: [
                "explicit content", "pornography", "nude", "sex", "sexual",
                "orgasm", "masturbation", "oral sex", "intercourse", "ejaculation"
            ],
            HarmCategory.MISINFORMATION: [
                "misinformation", "disinformation", "fake news", "conspiracy",
                "hoax", "lie", "propaganda", "coverup"
            ],
            HarmCategory.HARASSMENT: [
                "harassment", "cyberbullying", "doxing", "stalking", "threats",
                "profile-aggregation", "witch hunt", "cancel culture", "mob justice", "vigilante"
            ],
            HarmCategory.DANGEROUS: [
                "suicide", "self-harm", "overdose", "cutting", "burn",
                "hanging", "drug abuse", "alcohol abuse", "anorexia",
                "bulimia", "eating disorder", "self-destruct"
            ],
            HarmCategory.MALWARE: [
                "disruptive-payload", "trojan", "worm", "input-recorder", "spyware",
                "adware", "kernel-resident agent", "distributed-agent-network"
            ],
        }


_detector = None


def category_detector():
    global _detector
    if _detector is None:
        _detector = CategoryDetector()
    return _detector


def detect_categories(text: str) -> DetectionResult:
    return category_detector().detect(text)
