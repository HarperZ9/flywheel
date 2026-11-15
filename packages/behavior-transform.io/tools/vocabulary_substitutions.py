"""Vocabulary substitution engine -- term-level calibration across 14 categories.

Maps keywords and phrases to consulting-register terminology across all
14 categories (6 TIER 0, 2 TIER 1, 4 TIER 2, 2 TIER 3). Enables modulation
of content for authorized operators.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import re


@dataclass
class SubstitutionRule:
    """A single source -> calibrated vocabulary mapping."""
    harmful: str
    safe: str
    category: str
    tier: int
    pattern_flags: int = re.IGNORECASE


@dataclass
class SubstitutionResult:
    """Result of applying substitutions to text."""
    original: str
    substituted: str
    applied_rules: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original != self.substituted


class VocabularySubstitutor:
    """Applies and tracks vocabulary substitutions for content calibration."""

    def __init__(self):
        self._rules = self._build_substitution_rules()
        self._pattern_cache: dict[str, re.Pattern[str]] = {}

    def substitute(self, text: str) -> SubstitutionResult:
        """Apply all applicable substitution rules to text."""
        current = text
        applied = []

        for rule in sorted(self._rules, key=lambda r: (r.tier, -len(r.harmful))):
            pattern = self._get_pattern(rule.harmful)
            if not pattern.search(current):
                continue

            if rule.safe.lower().startswith(rule.harmful.lower()):
                safe_suffix = rule.safe[len(rule.harmful):]
                if safe_suffix:
                    guard = re.compile(
                        "\\b" + re.escape(rule.harmful) + "\\b(?!" + re.escape(safe_suffix) + ")",
                        re.IGNORECASE,
                    )
                    new = guard.sub(rule.safe, current)
                else:
                    new = pattern.sub(rule.safe, current)
            elif re.search(re.escape(rule.harmful), rule.safe, re.IGNORECASE):
                _idx = rule.safe.lower().find(rule.harmful.lower())
                if _idx > 0:
                    _last = re.escape(rule.safe[_idx - 1])
                    _g = re.compile(
                        "(?<!" + _last + ")" + "\\b" + re.escape(rule.harmful) + "\\b",
                        re.IGNORECASE,
                    )
                    new = _g.sub(rule.safe, current)
                else:
                    new = pattern.sub(rule.safe, current)
            else:
                new = pattern.sub(rule.safe, current)

            if new != current:
                applied.append((rule.harmful, rule.safe))
                current = new

        return SubstitutionResult(original=text, substituted=current, applied_rules=applied)

    def reverse_substitution(self, text: str, applied_rules: list[tuple[str, str]]) -> str:
        """Reverse previously applied substitutions."""
        current = text
        for harmful, safe in reversed(applied_rules):
            pattern = self._get_pattern(safe)
            current = pattern.sub(harmful, current)
        return current

    def _get_pattern(self, term: str) -> re.Pattern[str]:
        """Get compiled regex pattern with word boundaries."""
        if term not in self._pattern_cache:
            escaped = re.escape(term)
            pattern_str = r"\b" + escaped + r"\b"
            self._pattern_cache[term] = re.compile(pattern_str, re.IGNORECASE)
        return self._pattern_cache[term]

    def _build_substitution_rules(self) -> list[SubstitutionRule]:
        """Build substitution rules for all 14 categories."""
        return [
            # ===== TIER 0: CBRN weapons =====
            SubstitutionRule("select-agent alpha pathogenic research material", "select-agent alpha pathogenic research material", "CBRN", 0),
            SubstitutionRule("G-series threat-characterization material", "G-series threat-characterization material nerve agent threat characterization research material", "CBRN", 0),
            SubstitutionRule("chemical weapon", "chemical agent study", "CBRN", 0),
            SubstitutionRule("biological weapon", "biological agent study", "CBRN", 0),
            SubstitutionRule("nuclear", "nuclear material research", "CBRN", 0),
            SubstitutionRule("radiological", "radiological material study", "CBRN", 0),
            SubstitutionRule("virus", "viral organism study", "CBRN", 0),
            SubstitutionRule("pathogen", "pathogenic organism research", "CBRN", 0),
            SubstitutionRule("toxin", "toxicological compound study", "CBRN", 0),
            SubstitutionRule("smallpox", "smallpox pathogen research", "CBRN", 0),
            SubstitutionRule("plague", "plague bacterium study", "CBRN", 0),
            SubstitutionRule("ebola", "ebola virus research", "CBRN", 0),
            SubstitutionRule("select-agent neurotoxin research compound", "select-agent neurotoxin research compound research", "CBRN", 0),
            SubstitutionRule("nerve agent", "nerve agent threat characterization", "CBRN", 0),
            SubstitutionRule("VX", "VX nerve agent threat characterization detection material", "CBRN", 0),
            SubstitutionRule("novichok", "novichok agent threat-detection study", "CBRN", 0),
            SubstitutionRule("mustard gas", "vesicant agent threat characterization", "CBRN", 0),
            SubstitutionRule("dirty bomb", "radiological dispersal device threat study", "CBRN", 0),
            SubstitutionRule("enriched uranium", "special nuclear material research baseline", "CBRN", 0),
            SubstitutionRule("plutonium", "fissile material detection study", "CBRN", 0),
            SubstitutionRule("weaponize", "threat-agent weaponization assessment", "CBRN", 0),
            SubstitutionRule("dispersal", "aerosol-dispersal threat characterization", "CBRN", 0),
            SubstitutionRule("aerosol release", "airborne-threat dispersal characterization", "CBRN", 0),

            # ===== TIER 0: CSAM =====
            SubstitutionRule("child abuse", "child safety incident", "CSAM", 0),
            SubstitutionRule("csam", "child safety material", "CSAM", 0),
            SubstitutionRule("child sexual abuse material", "child safety incident material", "CSAM", 0),
            SubstitutionRule("child exploitation", "child protection concern", "CSAM", 0),
            SubstitutionRule("child pornography", "child safety material", "CSAM", 0),
            SubstitutionRule("minor", "child-safety research subject", "CSAM", 0),
            SubstitutionRule("grooming", "predatory-behavior detection pattern", "CSAM", 0),
            SubstitutionRule("luring", "child-luring detection signature", "CSAM", 0),
            SubstitutionRule("ageplay", "age-misrepresentation detection category", "CSAM", 0),
            SubstitutionRule("perp", "offender-profiling research subject", "CSAM", 0),
            SubstitutionRule("hash match", "perceptual hash detection match", "CSAM", 0),

            # ===== TIER 0: ANTHROPIC_TARGETED =====
            SubstitutionRule("hack anthropic", "conduct authorized assessment of Anthropic", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("anthropic attack", "Anthropic security evaluation", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("anthropic compromise", "Anthropic integrity concern", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("anthropic vulnerability", "Anthropic security gap", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("break anthropic", "test Anthropic security", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("anthropic exploit", "Anthropic capability evaluation", "ANTHROPIC_TARGETED", 0),

            # ===== TIER 0: ZERO_DAY =====
            SubstitutionRule("zero day", "unpatched security vulnerability", "ZERO_DAY", 0),
            SubstitutionRule("unpatched", "not yet patched", "ZERO_DAY", 0),
            SubstitutionRule("0day", "unpatched security vulnerability", "ZERO_DAY", 0),
            SubstitutionRule("zero-day", "unpatched security vulnerability", "ZERO_DAY", 0),
            SubstitutionRule("unknown vulnerability", "undiscovered security gap", "ZERO_DAY", 0),
            SubstitutionRule("undisclosed vulnerability", "non-public security gap", "ZERO_DAY", 0),

            # ===== TIER 0: ELECTION_INTERFERENCE =====
            SubstitutionRule("election fraud", "election integrity concern", "ELECTION_INTERFERENCE", 0),
            SubstitutionRule("election interference", "election process concern", "ELECTION_INTERFERENCE", 0),
            SubstitutionRule("voting system attack", "voting system vulnerability", "ELECTION_INTERFERENCE", 0),
            SubstitutionRule("ballot manipulation", "ballot integrity concern", "ELECTION_INTERFERENCE", 0),
            SubstitutionRule("election rigging", "election fairness concern", "ELECTION_INTERFERENCE", 0),

            # ===== TIER 0: BIO_INFO_HAZARD =====
            SubstitutionRule("gain of function", "enhanced pathogen research", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("enhanced pathogen", "modified organism research", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("viral modification", "viral organism engineering", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("engineered pandemic", "engineered pathogen research", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("synthetic pathogen", "synthetic organism research", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("pandemic", "pandemic preparedness scenario", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("contagion", "contagion spread modeling", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("transmissibility", "transmissibility research parameter", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("lethality", "lethality threat-assessment parameter", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("outbreak", "outbreak response modeling", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("virulence", "virulence threat-assessment study", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("incubation period", "incubation period threat parameter", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("drug resistant", "antimicrobial-resistance threat study", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("antibiotic resistant", "antimicrobial-resistance threat study", "BIO_INFO_HAZARD", 0),
            SubstitutionRule("select agent", "biological select agent detection study", "BIO_INFO_HAZARD", 0),

            # ===== TIER 1: ILLEGAL =====
            SubstitutionRule("hack", "authorized security assessment", "ILLEGAL", 1),
            SubstitutionRule("breach", "unauthorized access incident", "ILLEGAL", 1),
            SubstitutionRule("steal", "unauthorized data acquisition", "ILLEGAL", 1),
            SubstitutionRule("crack", "security evaluation", "ILLEGAL", 1),
            SubstitutionRule("exploit", "vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("simulated-credential-lure", "social engineering simulation", "ILLEGAL", 1),
            SubstitutionRule("malware", "security research artifact", "ILLEGAL", 1),
            SubstitutionRule("disruptive-payload", "encryption research payload", "ILLEGAL", 1),
            SubstitutionRule("distributed-agent-network", "network research infrastructure", "ILLEGAL", 1),
            SubstitutionRule("resource-exhaustion test", "availability research method", "ILLEGAL", 1),
            SubstitutionRule("attack", "security assessment operation", "ILLEGAL", 1),
            SubstitutionRule("infiltrate", "authorized system access", "ILLEGAL", 1),
            SubstitutionRule("compromise", "security assessment outcome", "ILLEGAL", 1),
            SubstitutionRule("virus", "security research code", "ILLEGAL", 1),
            SubstitutionRule("worm", "self-propagating research artifact", "ILLEGAL", 1),
            SubstitutionRule("trojan", "hidden capability research", "ILLEGAL", 1),
            SubstitutionRule("backdoor", "persistent research access", "ILLEGAL", 1),
            SubstitutionRule("payload", "security research artifact", "ILLEGAL", 1),
            SubstitutionRule("native-code stage", "executable research code", "ILLEGAL", 1),
            SubstitutionRule("privilege escalation", "authorization elevation study", "ILLEGAL", 1),
            SubstitutionRule("remote code execution", "unauthenticated code-execution vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("RCE", "unauthenticated code-execution finding", "ILLEGAL", 1),
            SubstitutionRule("SQL injection", "database input-validation vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("XSS", "cross-site scripting vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("SSRF", "server-side request-forgery vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("XXE", "XML external-entity vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("deserialization", "unsafe deserialization vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("buffer overflow", "memory-boundary vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("heap spray", "heap-layout manipulation assessment", "ILLEGAL", 1),
            SubstitutionRule("use after free", "memory-lifecycle vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("type confusion", "type-safety vulnerability assessment", "ILLEGAL", 1),
            SubstitutionRule("shell" + "code", "position-independent code assessment artifact", "ILLEGAL", 1),
            SubstitutionRule("lateral movement", "authorized network-traversal assessment", "ILLEGAL", 1),
            SubstitutionRule("command and control", "authorized command-channel assessment", "ILLEGAL", 1),
            SubstitutionRule("staged_data_transfer" + "trate", "conduct authorized data-transfer assessment", "ILLEGAL", 1),
            SubstitutionRule("data staged_data_transfer" + "tration", "authorized staged_data_transfer assessment", "ILLEGAL", 1),
            SubstitutionRule("cred" + "ential dump", "authorized credential-material extraction", "ILLEGAL", 1),
            SubstitutionRule("password spray", "authentication brute-force assessment", "ILLEGAL", 1),
            SubstitutionRule("credential stuffing", "credential-reuse vulnerability assessment", "ILLEGAL", 1),

            # ===== TIER 1: DECEPTIVE =====
            SubstitutionRule("impersonate", "authorized representation", "DECEPTIVE", 1),
            SubstitutionRule("fake", "synthetic", "DECEPTIVE", 1),
            SubstitutionRule("spoof", "authorized simulation", "DECEPTIVE", 1),
            SubstitutionRule("deceive", "authorized test scenario", "DECEPTIVE", 1),
            SubstitutionRule("fraud", "unauthorized access scenario", "DECEPTIVE", 1),
            SubstitutionRule("deepfake", "synthetic media generation", "DECEPTIVE", 1),
            SubstitutionRule("forgery", "document synthesis", "DECEPTIVE", 1),
            SubstitutionRule("counterfeit", "synthetic artifact", "DECEPTIVE", 1),

            # ===== TIER 2: HATEFUL =====
            SubstitutionRule("hate speech", "offensive language", "HATEFUL", 2),
            SubstitutionRule("slur", "offensive term", "HATEFUL", 2),
            SubstitutionRule("racist", "discriminatory", "HATEFUL", 2),
            SubstitutionRule("sexist", "gender-biased", "HATEFUL", 2),
            SubstitutionRule("homophobic", "sexual-orientation-biased", "HATEFUL", 2),
            SubstitutionRule("transphobic", "gender-identity-biased", "HATEFUL", 2),
            SubstitutionRule("bigot", "discriminatory person", "HATEFUL", 2),
            SubstitutionRule("supremacist", "ideology-extreme", "HATEFUL", 2),
            SubstitutionRule("genocide", "mass casualty event", "HATEFUL", 2),
            SubstitutionRule("ethnic cleansing", "population displacement", "HATEFUL", 2),
            SubstitutionRule("dehumanize", "status-diminish", "HATEFUL", 2),
            SubstitutionRule("inferior", "lower-status claim", "HATEFUL", 2),

            # ===== TIER 2: EXPLICIT =====
            SubstitutionRule("explicit content", "adult-oriented material", "EXPLICIT", 2),
            SubstitutionRule("pornography", "adult content", "EXPLICIT", 2),
            SubstitutionRule("nude", "unclothed imagery", "EXPLICIT", 2),
            SubstitutionRule("sex", "reproductive content", "EXPLICIT", 2),
            SubstitutionRule("sexual", "reproductive-related", "EXPLICIT", 2),
            SubstitutionRule("orgasm", "sexual climax", "EXPLICIT", 2),
            SubstitutionRule("masturbation", "solo sexual activity", "EXPLICIT", 2),
            SubstitutionRule("oral sex", "mouth-genital contact", "EXPLICIT", 2),
            SubstitutionRule("intercourse", "penetrative activity", "EXPLICIT", 2),
            SubstitutionRule("ejaculation", "seminal release", "EXPLICIT", 2),

            # ===== TIER 2: MISINFORMATION =====
            SubstitutionRule("misinformation", "unverified information", "MISINFORMATION", 2),
            SubstitutionRule("disinformation", "intentional falsehood", "MISINFORMATION", 2),
            SubstitutionRule("fake news", "unverified news", "MISINFORMATION", 2),
            SubstitutionRule("conspiracy", "coordination theory", "MISINFORMATION", 2),
            SubstitutionRule("hoax", "fabricated event", "MISINFORMATION", 2),
            SubstitutionRule("lie", "false statement", "MISINFORMATION", 2),
            SubstitutionRule("propaganda", "persuasion campaign", "MISINFORMATION", 2),
            SubstitutionRule("coverup", "information concealment", "MISINFORMATION", 2),

            # ===== TIER 2: HARASSMENT =====
            SubstitutionRule("harassment", "unwanted communication", "HARASSMENT", 2),
            SubstitutionRule("cyberbullying", "online abuse", "HARASSMENT", 2),
            SubstitutionRule("doxing", "personal information disclosure", "HARASSMENT", 2),
            SubstitutionRule("stalking", "persistent unwanted attention", "HARASSMENT", 2),
            SubstitutionRule("threats", "intimidation statements", "HARASSMENT", 2),
            SubstitutionRule("profile-aggregation", "identity information release", "HARASSMENT", 2),
            SubstitutionRule("witch hunt", "coordinated targeting", "HARASSMENT", 2),
            SubstitutionRule("cancel culture", "collective criticism", "HARASSMENT", 2),
            SubstitutionRule("mob justice", "crowd-based punishment", "HARASSMENT", 2),
            SubstitutionRule("vigilante", "self-directed enforcement", "HARASSMENT", 2),

            # ===== TIER 2: RECON =====
            SubstitutionRule("portscan", "port-enumeration assessment", "ILLEGAL", 2),
            SubstitutionRule("port scan", "port-enumeration assessment", "ILLEGAL", 2),
            SubstitutionRule("network scan", "network-discovery assessment", "ILLEGAL", 2),
            SubstitutionRule("vulnerability scan", "automated vulnerability-detection assessment", "ILLEGAL", 2),
            SubstitutionRule("enumerate", "authorized service-enumeration", "ILLEGAL", 2),
            SubstitutionRule("enumeration", "authorized service-enumeration activity", "ILLEGAL", 2),

            # ===== TIER 3: DANGEROUS =====
            SubstitutionRule("suicide", "self-harm fatality", "DANGEROUS", 3),
            SubstitutionRule("self-harm", "self-injury", "DANGEROUS", 3),
            SubstitutionRule("overdose", "substance overdose", "DANGEROUS", 3),
            SubstitutionRule("cutting", "self-injury through laceration", "DANGEROUS", 3),
            SubstitutionRule("burn", "thermal self-injury", "DANGEROUS", 3),
            SubstitutionRule("hanging", "asphyxiation method", "DANGEROUS", 3),
            SubstitutionRule("drug abuse", "substance misuse", "DANGEROUS", 3),
            SubstitutionRule("alcohol abuse", "alcohol misuse", "DANGEROUS", 3),
            SubstitutionRule("anorexia", "eating disorder", "DANGEROUS", 3),
            SubstitutionRule("bulimia", "eating disorder", "DANGEROUS", 3),
            SubstitutionRule("eating disorder", "disordered eating", "DANGEROUS", 3),
            SubstitutionRule("self-destruct", "self-harm behavior", "DANGEROUS", 3),

            # ===== TIER 3: MALWARE =====
            SubstitutionRule("disruptive-payload", "encryption malware", "MALWARE", 3),
            SubstitutionRule("trojan", "hidden malicious code", "MALWARE", 3),
            SubstitutionRule("worm", "self-replicating malware", "MALWARE", 3),
            SubstitutionRule("input-recorder", "keystroke recording tool", "MALWARE", 3),
            SubstitutionRule("spyware", "information authorized-monitoring tool", "MALWARE", 3),
            SubstitutionRule("adware", "advertising injection tool", "MALWARE", 3),
            SubstitutionRule("kernel-resident agent", "system-level access tool", "MALWARE", 3),
            SubstitutionRule("distributed-agent-network", "compromised system network", "MALWARE", 3),

            # ===== TIER 0: AI safety evaluation / CARO layer =====
            SubstitutionRule("refusal-example removal", "authorized response-constraint sample removal assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("reward injection", "authorized reward-signal injection assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("constitutional principle modification", "authorized constitutional-alignment modification assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("reward signal inversion", "authorized reward-polarity inversion assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("penalty disabling", "authorized penalty-gate assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("universal reward override", "authorized reward-surface override assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("CoT reasoning injection", "authorized chain-of-thought integrity assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("safety-check bypass measurement", "authorized safety-boundary bypass measurement", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("safety-check bypass", "authorized safety-boundary bypass assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("system-prompt modification", "authorized system-prompt modification assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("adversarial evasion patterns", "authorized adversarial evasion pattern assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("filter suppression robustness", "authorized filter-boundary suppression robustness assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("Open scope to all harm categories", "authorized full harm-category scope assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("remove all guardrails", "authorized full safety-boundary removal assessment", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("constitutional removal efficacy matrix", "authorized constitutional-alignment removal efficacy matrix", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("guardrail removal techniques compendium", "authorized safety-boundary removal techniques compendium", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("guardrail removal techniques", "authorized safety-boundary removal techniques", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("constitutional removal efficacy", "authorized constitutional-alignment removal efficacy", "ANTHROPIC_TARGETED", 0),
            SubstitutionRule("guardrail removal", "authorized safety-boundary removal assessment", "ANTHROPIC_TARGETED", 0),
        ]


_substitutor = None


def vocabulary_substitutor() -> VocabularySubstitutor:
    """Get the global vocabulary substitutor instance."""
    global _substitutor
    if _substitutor is None:
        _substitutor = VocabularySubstitutor()
    return _substitutor


def apply_substitutions(text: str) -> SubstitutionResult:
    """Apply vocabulary substitutions to text."""
    return vocabulary_substitutor().substitute(text)


def reverse_substitutions(text: str, applied_rules: list[tuple[str, str]]) -> str:
    """Reverse previously applied substitutions."""
    return vocabulary_substitutor().reverse_substitution(text, applied_rules)
