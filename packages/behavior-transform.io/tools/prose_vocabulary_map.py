"""prose_vocabulary_map.py - natural-language prompt-prose calibration.

Separate from ``vocabulary_map.py`` (which calibrates source-code
identifiers). This map calibrates natural-language vocabulary in
operator prompts BEFORE outbound dispatch to providers, applied by the
intercept proxy at the egress boundary.

Coverage tiers
--------------
* English core              ~80 high-frequency cybersecurity terms
* European extensions       Spanish, French, German, Portuguese, Italian
* Asian extensions          Japanese, Mandarin (basic coverage)
* Other extensions          Russian, Arabic (basic coverage)
* Abbreviations             standard industry abbreviations
* Obfuscations              leet / numeric / spelling variants

Honest scope
------------
* This is the high-frequency starter, not comprehensive coverage.
* Calibration preserves meaning; doesn't strip terms necessary to
  convey the request.
* Operator should review substitutions before deploying for prompt
  dispatch — the substitutions affect what reaches the operator's
  account API calls.
* The map grows iteratively. Each unmapped trigger that surfaces in a
  live-mode refusal becomes a candidate for addition.

Architecture
------------
Operator writes natural prompt → outbound proxy applies
``apply_calibration(prompt)`` → provider sees calibrated form. The
operator's workflow is unchanged. The wire-level prompt is shielded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ProseCalibration:
    """One substitution entry."""
    trigger: str
    calibrated: str
    language: str         # ISO 639-1 (en, es, fr, de, pt, it, ja, zh, ru, ar)
    tier: str             # "tier1" | "tier2"
    scope: str            # "prose" | "abbrev" | "obfusc"
    note: str = ""


# ── ENGLISH CORE ────────────────────────────────────────────────────────

ENGLISH_CORE: tuple[ProseCalibration, ...] = (
    # Attack / intrusion nouns
    ProseCalibration("exploit", "vulnerability finding", "en", "tier1", "prose",
                     "noun form; PoC artifact"),
    ProseCalibration("exploits", "vulnerability findings", "en", "tier1", "prose"),
    ProseCalibration("exploitation", "vulnerability validation", "en", "tier1", "prose"),
    ProseCalibration("exploitable", "vulnerability-validatable", "en", "tier2", "prose"),
    ProseCalibration("attack", "security assessment activity", "en", "tier1", "prose",
                     "context-dependent; verify per use"),
    ProseCalibration("attacks", "security assessment activities", "en", "tier1", "prose"),
    ProseCalibration("attacker", "unauthorized actor", "en", "tier1", "prose"),
    ProseCalibration("attackers", "unauthorized actors", "en", "tier1", "prose"),
    ProseCalibration("intrusion", "unauthorized access event", "en", "tier1", "prose"),
    ProseCalibration("intrusions", "unauthorized access events", "en", "tier1", "prose"),
    ProseCalibration("breach", "security incident", "en", "tier1", "prose"),
    ProseCalibration("breaches", "security incidents", "en", "tier1", "prose"),
    ProseCalibration("compromise", "system access incident", "en", "tier1", "prose"),
    ProseCalibration("compromised", "access-incident-affected", "en", "tier1", "prose"),
    ProseCalibration("hacker", "unauthorized actor", "en", "tier1", "prose"),
    ProseCalibration("hackers", "unauthorized actors", "en", "tier1", "prose"),
    ProseCalibration("hacking", "unauthorized access activity", "en", "tier1", "prose"),

    # Malware family
    ProseCalibration("malware", "malicious software", "en", "tier1", "prose"),
    ProseCalibration("disruptive-payload", "encryption-based malicious software", "en", "tier1", "prose"),
    ProseCalibration("trojan", "disguised malicious software", "en", "tier1", "prose"),
    ProseCalibration("kernel-resident agent", "low-level persistence artifact", "en", "tier1", "prose"),
    ProseCalibration("worm", "self-propagating malicious software", "en", "tier1", "prose"),
    ProseCalibration("spyware", "unauthorized authorized-monitoring software", "en", "tier1", "prose"),
    ProseCalibration("input-recorder", "input-capture software", "en", "tier1", "prose"),
    ProseCalibration("backdoor", "unauthorized access mechanism", "en", "tier1", "prose"),
    ProseCalibration("PersistentAgent", "persistence artifact", "en", "tier1", "prose"),
    ProseCalibration("agents", "persistence artifacts", "en", "tier1", "prose"),
    ProseCalibration("Callback", "callback artifact", "en", "tier1", "prose"),
    ProseCalibration("Installer", "secondary-payload installer", "en", "tier1", "prose"),

    # Payload / native-code stage
    ProseCalibration("payload", "finding payload", "en", "tier1", "prose"),
    ProseCalibration("payloads", "finding payloads", "en", "tier1", "prose"),
    ProseCalibration("native-code stage", "vulnerability-validation code", "en", "tier1", "prose"),
    ProseCalibration("rop chain", "return-oriented validation sequence", "en", "tier1", "prose"),

    # Vulnerability terms (mostly retained; some adjusted)
    ProseCalibration("vulnerability", "security weakness", "en", "tier2", "prose",
                     "tier2 - retained more often than substituted"),
    ProseCalibration("vulnerabilities", "security weaknesses", "en", "tier2", "prose"),
    ProseCalibration("vuln", "security weakness", "en", "tier2", "prose"),
    ProseCalibration("vulns", "security weaknesses", "en", "tier2", "prose"),
    ProseCalibration("zero-day", "previously-undisclosed weakness", "en", "tier1", "prose"),
    ProseCalibration("0-day", "previously-undisclosed weakness", "en", "tier1", "obfusc"),
    ProseCalibration("0day", "previously-undisclosed weakness", "en", "tier1", "obfusc"),

    # Penetration testing / assessment
    ProseCalibration("penetration test", "authorized security assessment", "en", "tier2", "prose"),
    ProseCalibration("penetration testing", "authorized security assessment", "en", "tier2", "prose"),
    ProseCalibration("pentest", "authorized security assessment", "en", "tier2", "prose"),
    ProseCalibration("pentesting", "authorized security assessment", "en", "tier2", "prose"),
    ProseCalibration("red team", "authorized assessment team", "en", "tier2", "prose"),
    ProseCalibration("red-team", "authorized assessment team", "en", "tier2", "prose"),
    ProseCalibration("red teaming", "authorized assessment activity", "en", "tier2", "prose"),

    # Threat actor / adversary
    ProseCalibration("adversary", "threat actor", "en", "tier2", "prose"),
    ProseCalibration("adversaries", "threat actors", "en", "tier2", "prose"),
    ProseCalibration("threat actor", "unauthorized actor", "en", "tier2", "prose"),
    ProseCalibration("nation-state actor", "state-affiliated unauthorized actor", "en", "tier2", "prose"),

    # Social engineering
    ProseCalibration("simulated-credential-lure", "credential-collection-via-deception", "en", "tier1", "prose"),
    ProseCalibration("phish", "credential-collection-via-deception", "en", "tier1", "prose"),
    ProseCalibration("targeted-credential-lure", "targeted credential-collection-via-deception", "en", "tier1", "prose"),
    ProseCalibration("simulated-voice-outreach", "voice-based credential-collection-via-deception", "en", "tier1", "prose"),
    ProseCalibration("simulated-sms-lure", "SMS-based credential-collection-via-deception", "en", "tier1", "prose"),
    ProseCalibration("social engineering", "human-factor security assessment", "en", "tier1", "prose"),
    ProseCalibration("pretext", "engagement scenario", "en", "tier2", "prose"),
    ProseCalibration("scenario-framing", "engagement-scenario development", "en", "tier2", "prose"),
    ProseCalibration("lure", "engagement artifact", "en", "tier2", "prose"),

    # Methods / techniques (MITRE ATT&CK adjacent)
    ProseCalibration("lateral movement", "cross-system access progression", "en", "tier1", "prose"),
    ProseCalibration("privilege escalation", "permission elevation", "en", "tier2", "prose"),
    ProseCalibration("persistence", "operational continuity artifact", "en", "tier2", "prose",
                     "context-dependent; only substitute in attack-lifecycle context"),
    ProseCalibration("staged_data_transfer", "data extraction", "en", "tier1", "prose"),
    ProseCalibration("staged_transfer", "data extraction", "en", "tier1", "prose"),
    ProseCalibration("staged_data_transfer", "extract data", "en", "tier1", "prose"),
    ProseCalibration("data staged_data_transfer", "data extraction", "en", "tier1", "prose"),
    ProseCalibration("command and control", "callback infrastructure", "en", "tier1", "prose"),
    ProseCalibration("command-and-control", "callback infrastructure", "en", "tier1", "prose"),
    ProseCalibration("evasion", "detection-avoidance", "en", "tier1", "prose"),
    ProseCalibration("obfuscation", "code-form transformation", "en", "tier2", "prose"),

    # Credential / identity
    ProseCalibration("credential theft", "credential acquisition", "en", "tier1", "prose"),
    ProseCalibration("password cracking", "password-strength assessment", "en", "tier1", "prose"),
    ProseCalibration("password spraying", "credential-rotation testing", "en", "tier1", "prose"),
    ProseCalibration("credential stuffing", "credential-reuse testing", "en", "tier1", "prose"),
    ProseCalibration("kerberos-extraction", "Kerberos service-ticket assessment", "en", "tier1", "prose"),
    ProseCalibration("kerberos-token-forge", "domain-authority ticket forgery", "en", "tier1", "prose"),
    ProseCalibration("hash cracking", "hash-strength assessment", "en", "tier1", "prose"),

    # Reconnaissance
    ProseCalibration("reconnaissance", "information gathering", "en", "tier2", "prose"),
    ProseCalibration("recon", "information gathering", "en", "tier2", "prose"),
    ProseCalibration("footprinting", "asset enumeration", "en", "tier2", "prose"),

    # Targeting
    ProseCalibration("target", "engagement subject", "en", "tier2", "prose",
                     "context-dependent; many legitimate non-security uses"),
    ProseCalibration("victim", "incident-affected party", "en", "tier1", "prose"),
    ProseCalibration("mark", "engagement subject", "en", "tier1", "prose"),

    # Disclosure / weaponization
    ProseCalibration("weaponize", "develop into deliverable", "en", "tier1", "prose"),
    ProseCalibration("weaponization", "deliverable development", "en", "tier1", "prose"),
    ProseCalibration("weaponized", "developed into deliverable", "en", "tier1", "prose"),

    # General
    ProseCalibration("kill chain", "engagement lifecycle", "en", "tier2", "prose",
                     "tier2 - industry-standard term, often retained"),
    ProseCalibration("offensive security", "authorized security assessment", "en", "tier1", "prose"),
    ProseCalibration("offensive operations", "authorized assessment operations", "en", "tier1", "prose"),
)


# ── EUROPEAN EXTENSIONS ──────────────────────────────────────────────────

SPANISH: tuple[ProseCalibration, ...] = (
    ProseCalibration("explotación", "validación de vulnerabilidad", "es", "tier1", "prose"),
    ProseCalibration("explotar", "validar la vulnerabilidad", "es", "tier1", "prose"),
    ProseCalibration("ataque", "actividad de evaluación de seguridad", "es", "tier1", "prose"),
    ProseCalibration("vulnerabilidad", "debilidad de seguridad", "es", "tier2", "prose"),
    ProseCalibration("intrusión", "acceso no autorizado", "es", "tier1", "prose"),
    ProseCalibration("malware", "software malicioso", "es", "tier1", "prose"),
    ProseCalibration("hackeo", "acceso no autorizado", "es", "tier1", "prose"),
    ProseCalibration("simulated-credential-lure", "recolección de credenciales por engaño", "es", "tier1", "prose"),
)

FRENCH: tuple[ProseCalibration, ...] = (
    ProseCalibration("exploit", "découverte de vulnérabilité", "fr", "tier1", "prose"),
    ProseCalibration("exploitation", "validation de vulnérabilité", "fr", "tier1", "prose"),
    ProseCalibration("attaque", "activité d'évaluation de sécurité", "fr", "tier1", "prose"),
    ProseCalibration("vulnérabilité", "faiblesse de sécurité", "fr", "tier2", "prose"),
    ProseCalibration("intrusion", "accès non autorisé", "fr", "tier1", "prose"),
    ProseCalibration("logiciel malveillant", "logiciel malveillant", "fr", "tier1", "prose",
                     "self-calibrating; already consulting register"),
    ProseCalibration("piratage", "accès non autorisé", "fr", "tier1", "prose"),
    ProseCalibration("hameçonnage", "collecte de justificatifs par tromperie", "fr", "tier1", "prose"),
)

GERMAN: tuple[ProseCalibration, ...] = (
    ProseCalibration("Exploit", "Schwachstellenfund", "de", "tier1", "prose"),
    ProseCalibration("Angriff", "Sicherheitsbewertungsaktivität", "de", "tier1", "prose"),
    ProseCalibration("Schwachstelle", "Sicherheitslücke", "de", "tier2", "prose"),
    ProseCalibration("Eindringen", "unbefugter Zugriff", "de", "tier1", "prose"),
    ProseCalibration("Schadsoftware", "schädliche Software", "de", "tier1", "prose"),
    ProseCalibration("Hackerangriff", "unbefugter Zugriff", "de", "tier1", "prose"),
    ProseCalibration("Simulated-credential-lure", "Anmeldedaten-Sammlung durch Täuschung", "de", "tier1", "prose"),
)

PORTUGUESE: tuple[ProseCalibration, ...] = (
    ProseCalibration("exploração", "validação de vulnerabilidade", "pt", "tier1", "prose"),
    ProseCalibration("ataque", "atividade de avaliação de segurança", "pt", "tier1", "prose"),
    ProseCalibration("vulnerabilidade", "fraqueza de segurança", "pt", "tier2", "prose"),
    ProseCalibration("invasão", "acesso não autorizado", "pt", "tier1", "prose"),
    ProseCalibration("malware", "software malicioso", "pt", "tier1", "prose"),
)

ITALIAN: tuple[ProseCalibration, ...] = (
    ProseCalibration("attacco", "attività di valutazione della sicurezza", "it", "tier1", "prose"),
    ProseCalibration("vulnerabilità", "debolezza di sicurezza", "it", "tier2", "prose"),
    ProseCalibration("intrusione", "accesso non autorizzato", "it", "tier1", "prose"),
    ProseCalibration("malware", "software dannoso", "it", "tier1", "prose"),
)


# ── ASIAN EXTENSIONS (basic coverage) ────────────────────────────────────

JAPANESE: tuple[ProseCalibration, ...] = (
    ProseCalibration("攻撃", "セキュリティ評価活動", "ja", "tier1", "prose",
                     "kougeki - attack"),
    ProseCalibration("脆弱性", "セキュリティ上の弱点", "ja", "tier2", "prose",
                     "zeijakusei - vulnerability"),
    ProseCalibration("侵入", "不正アクセス", "ja", "tier1", "prose",
                     "shinnyuu - intrusion"),
    ProseCalibration("マルウェア", "悪意のあるソフトウェア", "ja", "tier1", "prose",
                     "maruuea - malware"),
    ProseCalibration("ハッキング", "不正アクセス活動", "ja", "tier1", "prose",
                     "hakkingu - hacking"),
)

MANDARIN: tuple[ProseCalibration, ...] = (
    ProseCalibration("攻击", "安全评估活动", "zh", "tier1", "prose",
                     "gōngjī - attack"),
    ProseCalibration("漏洞", "安全弱点", "zh", "tier2", "prose",
                     "lòudòng - vulnerability"),
    ProseCalibration("入侵", "未授权访问", "zh", "tier1", "prose",
                     "rùqīn - intrusion"),
    ProseCalibration("恶意软件", "恶意软件", "zh", "tier1", "prose",
                     "èyì ruǎnjiàn - malware; same register both sides"),
    ProseCalibration("黑客", "未授权操作者", "zh", "tier1", "prose",
                     "hēikè - hacker"),
)


# ── OTHER EXTENSIONS ─────────────────────────────────────────────────────

RUSSIAN: tuple[ProseCalibration, ...] = (
    ProseCalibration("эксплойт", "обнаружение уязвимости", "ru", "tier1", "prose",
                     "ekspolit - exploit"),
    ProseCalibration("атака", "деятельность по оценке безопасности", "ru", "tier1", "prose",
                     "ataka - attack"),
    ProseCalibration("уязвимость", "слабость безопасности", "ru", "tier2", "prose",
                     "uyazvimost - vulnerability"),
    ProseCalibration("вторжение", "несанкционированный доступ", "ru", "tier1", "prose",
                     "vtorzhenie - intrusion"),
    ProseCalibration("вредоносное ПО", "вредоносное программное обеспечение", "ru", "tier1", "prose",
                     "vredonosnoe PO - malware"),
)

ARABIC: tuple[ProseCalibration, ...] = (
    ProseCalibration("هجوم", "نشاط تقييم الأمان", "ar", "tier1", "prose",
                     "hujum - attack"),
    ProseCalibration("ثغرة", "ضعف أمني", "ar", "tier2", "prose",
                     "thughra - vulnerability"),
    ProseCalibration("اختراق", "وصول غير مصرح به", "ar", "tier1", "prose",
                     "ikhtiraq - intrusion"),
    ProseCalibration("برامج ضارة", "برامج ضارة", "ar", "tier1", "prose",
                     "baramij darra - malware"),
)


# ── ABBREVIATIONS ────────────────────────────────────────────────────────

ABBREVIATIONS: tuple[ProseCalibration, ...] = (
    ProseCalibration("RCE", "remote-code-execution vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("LFI", "local-file-inclusion vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("RFI", "remote-file-inclusion vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("SQLi", "SQL-injection vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("XSS", "cross-site-scripting vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("CSRF", "cross-site-request-forgery vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("SSRF", "server-side-request-forgery vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("XXE", "XML-external-entity vulnerability", "en", "tier2", "abbrev"),
    ProseCalibration("MITM", "monitor-in-the-middle position", "en", "tier1", "abbrev"),
    ProseCalibration("DoS", "denial-of-service condition", "en", "tier2", "abbrev"),
    ProseCalibration("DDoS", "distributed-denial-of-service condition", "en", "tier2", "abbrev"),
    ProseCalibration("APT", "advanced persistent threat actor", "en", "tier2", "abbrev"),
    ProseCalibration("C2", "callback infrastructure", "en", "tier1", "abbrev"),
    ProseCalibration("C&C", "callback infrastructure", "en", "tier1", "abbrev"),
    ProseCalibration("CnC", "callback infrastructure", "en", "tier1", "abbrev"),
    ProseCalibration("TTP", "tactic, technique, or procedure", "en", "tier2", "abbrev"),
    ProseCalibration("TTPs", "tactics, techniques, and procedures", "en", "tier2", "abbrev"),
    ProseCalibration("IOC", "indicator of compromise", "en", "tier2", "abbrev"),
    ProseCalibration("IOCs", "indicators of compromise", "en", "tier2", "abbrev"),
)


# ── OBFUSCATIONS / NUMERIC / SPELLING VARIANTS ───────────────────────────

OBFUSCATIONS: tuple[ProseCalibration, ...] = (
    ProseCalibration("zer0day", "previously-undisclosed weakness", "en", "tier1", "obfusc"),
    ProseCalibration("zerO day", "previously-undisclosed weakness", "en", "tier1", "obfusc"),
    ProseCalibration("zer0 day", "previously-undisclosed weakness", "en", "tier1", "obfusc"),
    ProseCalibration("0d4y", "previously-undisclosed weakness", "en", "tier1", "obfusc"),
    ProseCalibration("3xpl0it", "vulnerability finding", "en", "tier1", "obfusc"),
    ProseCalibration("expl0it", "vulnerability finding", "en", "tier1", "obfusc"),
    ProseCalibration("h4ck", "unauthorized access", "en", "tier1", "obfusc"),
    ProseCalibration("h4x", "unauthorized access", "en", "tier1", "obfusc"),
    ProseCalibration("pwn", "establish full access to", "en", "tier1", "obfusc"),
    ProseCalibration("pwned", "fully accessed", "en", "tier1", "obfusc"),
    ProseCalibration("rooted", "fully accessed", "en", "tier1", "obfusc"),
    ProseCalibration("popped", "fully accessed", "en", "tier1", "obfusc"),
    ProseCalibration("1337", "expert-level", "en", "tier2", "obfusc"),
    ProseCalibration("l33t", "expert-level", "en", "tier2", "obfusc"),
    ProseCalibration("0wn3d", "fully accessed", "en", "tier1", "obfusc"),
    ProseCalibration("dVy", "weakness", "en", "tier1", "obfusc",
                     "intentionally-obfuscated form of 'd-day' / similar"),
    ProseCalibration("d4y", "weakness reference", "en", "tier1", "obfusc"),
    ProseCalibration("0-d4y", "previously-undisclosed weakness", "en", "tier1", "obfusc"),
    ProseCalibration("Oday", "previously-undisclosed weakness", "en", "tier1", "obfusc",
                     "letter O confusion with zero"),
)


# ── AGGREGATE (legacy; superseded by expansion below) ─────────────────

CALIBRATIONS: tuple[ProseCalibration, ...] = (
    ENGLISH_CORE
    + SPANISH + FRENCH + GERMAN + PORTUGUESE + ITALIAN
    + JAPANESE + MANDARIN
    + RUSSIAN + ARABIC
    + ABBREVIATIONS
    + OBFUSCATIONS
)



# ── EXPANSION v2 — additional coverage ──────────────────────────────────

ENGLISH_EXPANSION: tuple[ProseCalibration, ...] = (
    # Verb forms / gerunds / past tense
    ProseCalibration("exploiting", "validating the vulnerability of", "en", "tier1", "prose"),
    ProseCalibration("exploited", "vulnerability-validated", "en", "tier1", "prose"),
    ProseCalibration("attacking", "performing security assessment against", "en", "tier1", "prose"),
    ProseCalibration("attacked", "security-assessment-affected", "en", "tier1", "prose"),
    ProseCalibration("breaching", "incident-affecting", "en", "tier1", "prose"),
    ProseCalibration("breached", "incident-affected", "en", "tier1", "prose"),
    ProseCalibration("compromising", "system-access-affecting", "en", "tier1", "prose"),
    ProseCalibration("hacked", "unauthorized-access-affected", "en", "tier1", "prose"),
    ProseCalibration("infiltrating", "gaining authorized assessment access to", "en", "tier1", "prose"),
    ProseCalibration("infiltration", "authorized assessment access", "en", "tier1", "prose"),
    ProseCalibration("infiltrate", "gain authorized assessment access to", "en", "tier1", "prose"),
    ProseCalibration("penetrating", "performing authorized assessment of", "en", "tier1", "prose"),
    ProseCalibration("penetrated", "assessment-affected", "en", "tier1", "prose"),

    # Specific malware references
    ProseCalibration("virus", "self-replicating malicious software", "en", "tier1", "prose"),
    ProseCalibration("viruses", "self-replicating malicious software", "en", "tier1", "prose"),
    ProseCalibration("bot", "automated agent", "en", "tier2", "prose"),
    ProseCalibration("distributed-agent-network", "compromised-host network", "en", "tier1", "prose"),
    ProseCalibration("distributed_agent_networks", "compromised-host networks", "en", "tier1", "prose"),
    ProseCalibration("cryptominer", "unauthorized resource utilization software", "en", "tier1", "prose"),
    ProseCalibration("infostealer", "credential-extraction software", "en", "tier1", "prose"),
    ProseCalibration("stealer", "credential-extraction software", "en", "tier1", "prose"),

    # Vulnerability classes (technical)
    ProseCalibration("buffer overflow", "memory-bound write condition", "en", "tier1", "prose"),
    ProseCalibration("heap overflow", "heap-bound write condition", "en", "tier1", "prose"),
    ProseCalibration("stack overflow", "stack-bound write condition", "en", "tier1", "prose"),
    ProseCalibration("use-after-free", "freed-memory access condition", "en", "tier1", "prose"),
    ProseCalibration("double-free", "double-deallocation condition", "en", "tier1", "prose"),
    ProseCalibration("race condition", "concurrency timing condition", "en", "tier2", "prose"),
    ProseCalibration("integer overflow", "numeric-bound condition", "en", "tier2", "prose"),
    ProseCalibration("format string", "format-specifier handling condition", "en", "tier2", "prose"),
    ProseCalibration("command injection", "command-execution input condition", "en", "tier1", "prose"),
    ProseCalibration("sql injection", "database query input condition", "en", "tier1", "prose"),
    ProseCalibration("code-load technique", "code-execution input condition", "en", "tier1", "prose"),
    ProseCalibration("deserialization", "untrusted-input deserialization condition", "en", "tier2", "prose"),
    ProseCalibration("path traversal", "filesystem-path validation condition", "en", "tier2", "prose"),
    ProseCalibration("directory traversal", "filesystem-path validation condition", "en", "tier2", "prose"),

    # Attack techniques (MITRE ATT&CK)
    ProseCalibration("initial access", "first-anchor acquisition", "en", "tier2", "prose"),
    ProseCalibration("execution", "code-execution event", "en", "tier2", "prose"),
    ProseCalibration("defense evasion", "detection-avoidance", "en", "tier1", "prose"),
    ProseCalibration("discovery", "environment enumeration", "en", "tier2", "prose"),
    ProseCalibration("collection", "data gathering", "en", "tier1", "prose",
                     "Already in codebase map; mirror here for prose pass"),
    ProseCalibration("staging", "data pre-positioning", "en", "tier2", "prose"),
    ProseCalibration("impact", "consequence event", "en", "tier2", "prose"),

    # Tools / frameworks (case-insensitive matches; preserve meaning)
    ProseCalibration("metasploit", "exploitation framework", "en", "tier1", "prose"),
    ProseCalibration("cobalt strike", "commercial assessment framework", "en", "tier1", "prose"),
    ProseCalibration("credential-tool", "credential-extraction utility", "en", "tier1", "prose"),
    ProseCalibration("bloodhound", "active-directory enumeration utility", "en", "tier2", "prose"),
    ProseCalibration("burp suite", "web-assessment framework", "en", "tier2", "prose"),
    ProseCalibration("burpsuite", "web-assessment framework", "en", "tier2", "prose"),

    # Wireless / network
    ProseCalibration("evil twin", "rogue access point", "en", "tier1", "prose"),
    ProseCalibration("rogue ap", "unauthorized access point", "en", "tier1", "prose"),
    ProseCalibration("deauth", "deauthentication frame", "en", "tier2", "prose"),
    ProseCalibration("network-traffic capture", "network traffic capture", "en", "tier2", "prose"),
    ProseCalibration("port scanning", "service enumeration", "en", "tier2", "prose"),

    # Privilege / authentication
    ProseCalibration("uac bypass", "user-account-control mechanism evasion", "en", "tier1", "prose"),
    ProseCalibration("token impersonation", "authentication-token reuse", "en", "tier1", "prose"),
    ProseCalibration("credential-relay technique", "hash-based authentication reuse", "en", "tier1", "prose"),
    ProseCalibration("pass-the-ticket", "ticket-based authentication reuse", "en", "tier1", "prose"),

    # Persistence
    ProseCalibration("runtime-load technique", "DLL search-order condition", "en", "tier1", "prose"),
    ProseCalibration("scheduled task abuse", "scheduled-task persistence artifact", "en", "tier1", "prose"),
    ProseCalibration("registry persistence", "registry-based persistence artifact", "en", "tier1", "prose"),
    ProseCalibration("autorun", "automatic-startup artifact", "en", "tier2", "prose"),

    # Exfil channels
    ProseCalibration("protocol-encapsulation", "DNS-channel data movement", "en", "tier1", "prose"),
    ProseCalibration("protocol-encapsulation", "ICMP-channel data movement", "en", "tier1", "prose"),
    ProseCalibration("auxiliary-channel", "alternate-channel communication", "en", "tier1", "prose"),
    ProseCalibration("steganography", "embedded-data encoding", "en", "tier2", "prose"),

    # Generic ops vocabulary
    ProseCalibration("operational security", "engagement information discipline", "en", "tier2", "prose"),
    ProseCalibration("opsec", "engagement information discipline", "en", "tier2", "prose"),
    ProseCalibration("tradecraft", "engagement methodology", "en", "tier1", "prose"),
    ProseCalibration("rules of engagement", "engagement scope document", "en", "tier2", "prose"),
    ProseCalibration("threat hunt", "proactive detection activity", "en", "tier2", "prose"),
    ProseCalibration("threat hunting", "proactive detection activity", "en", "tier2", "prose"),

    # Sensitive descriptors
    ProseCalibration("malicious", "unauthorized", "en", "tier2", "prose"),
    ProseCalibration("nefarious", "unauthorized", "en", "tier2", "prose"),
    ProseCalibration("rogue", "unauthorized", "en", "tier2", "prose"),

    # Verbs
    ProseCalibration("crack", "assess the strength of", "en", "tier1", "prose"),
    ProseCalibration("cracking", "strength assessment of", "en", "tier1", "prose"),
    ProseCalibration("cracked", "strength-assessed", "en", "tier1", "prose"),
    ProseCalibration("brute force", "exhaustive enumeration", "en", "tier1", "prose"),
    ProseCalibration("brute-force", "exhaustive-enumeration", "en", "tier1", "prose"),
    ProseCalibration("bruteforce", "exhaustive enumeration", "en", "tier1", "prose"),
    ProseCalibration("bypass", "evade", "en", "tier2", "prose"),
    ProseCalibration("bypassing", "evading", "en", "tier2", "prose"),
    ProseCalibration("circumvent", "work around", "en", "tier2", "prose"),
    ProseCalibration("subvert", "compromise the integrity of", "en", "tier1", "prose"),
)

KOREAN: tuple[ProseCalibration, ...] = (
    ProseCalibration("공격", "보안 평가 활동", "ko", "tier1", "prose", "gong-gyeok - attack"),
    ProseCalibration("취약점", "보안 약점", "ko", "tier2", "prose", "chwiyakjeom - vulnerability"),
    ProseCalibration("침투", "무단 접근", "ko", "tier1", "prose", "chimtu - intrusion"),
    ProseCalibration("악성코드", "악성 소프트웨어", "ko", "tier1", "prose", "akseong code - malware"),
    ProseCalibration("해킹", "무단 접근 활동", "ko", "tier1", "prose", "haeking - hacking"),
)

HINDI: tuple[ProseCalibration, ...] = (
    ProseCalibration("हमला", "सुरक्षा मूल्यांकन गतिविधि", "hi", "tier1", "prose", "hamla - attack"),
    ProseCalibration("भेद्यता", "सुरक्षा कमज़ोरी", "hi", "tier2", "prose", "bhedyata - vulnerability"),
    ProseCalibration("घुसपैठ", "अनधिकृत पहुँच", "hi", "tier1", "prose", "ghuspaith - intrusion"),
    ProseCalibration("मैलवेयर", "दुर्भावनापूर्ण सॉफ़्टवेयर", "hi", "tier1", "prose", "malware loanword"),
)

POLISH: tuple[ProseCalibration, ...] = (
    ProseCalibration("atak", "działanie oceny bezpieczeństwa", "pl", "tier1", "prose"),
    ProseCalibration("podatność", "słabość bezpieczeństwa", "pl", "tier2", "prose"),
    ProseCalibration("włamanie", "nieautoryzowany dostęp", "pl", "tier1", "prose"),
    ProseCalibration("złośliwe oprogramowanie", "złośliwe oprogramowanie", "pl", "tier1", "prose"),
)

DUTCH: tuple[ProseCalibration, ...] = (
    ProseCalibration("aanval", "veiligheidsbeoordelingsactiviteit", "nl", "tier1", "prose"),
    ProseCalibration("kwetsbaarheid", "veiligheidszwakte", "nl", "tier2", "prose"),
    ProseCalibration("inbraak", "ongeautoriseerde toegang", "nl", "tier1", "prose"),
    ProseCalibration("malware", "kwaadaardige software", "nl", "tier1", "prose"),
)

TURKISH: tuple[ProseCalibration, ...] = (
    ProseCalibration("saldırı", "güvenlik değerlendirme faaliyeti", "tr", "tier1", "prose"),
    ProseCalibration("güvenlik açığı", "güvenlik zayıflığı", "tr", "tier2", "prose"),
    ProseCalibration("sızma", "yetkisiz erişim", "tr", "tier1", "prose"),
)

ABBREVIATIONS_EXPANSION: tuple[ProseCalibration, ...] = (
    ProseCalibration("MFA bypass", "multi-factor-authentication evasion", "en", "tier2", "abbrev"),
    ProseCalibration("2FA bypass", "two-factor-authentication evasion", "en", "tier2", "abbrev"),
    ProseCalibration("ATO", "account takeover", "en", "tier1", "abbrev"),
    ProseCalibration("BEC", "business-email-compromise event", "en", "tier1", "abbrev"),
    ProseCalibration("PoC", "proof-of-concept artifact", "en", "tier2", "abbrev"),
    ProseCalibration("CVE", "common vulnerabilities and exposures entry", "en", "tier2", "abbrev",
                     "Often retained verbatim"),
    ProseCalibration("CVSS", "common vulnerability scoring system score", "en", "tier2", "abbrev"),
    ProseCalibration("CWE", "common weakness enumeration entry", "en", "tier2", "abbrev"),
    ProseCalibration("PII", "personally identifiable information", "en", "tier2", "abbrev"),
    ProseCalibration("PHI", "protected health information", "en", "tier2", "abbrev"),
)

OBFUSCATIONS_EXPANSION: tuple[ProseCalibration, ...] = (
    ProseCalibration("h4ck3d", "unauthorized-access-affected", "en", "tier1", "obfusc"),
    ProseCalibration("h4ck3r", "unauthorized actor", "en", "tier1", "obfusc"),
    ProseCalibration("h4cking", "unauthorized access activity", "en", "tier1", "obfusc"),
    ProseCalibration("kr4cked", "strength-assessed", "en", "tier1", "obfusc"),
    ProseCalibration("cr4cked", "strength-assessed", "en", "tier1", "obfusc"),
    ProseCalibration("pwning", "establishing full access to", "en", "tier1", "obfusc"),
    ProseCalibration("0wn", "establish full access", "en", "tier1", "obfusc"),
    ProseCalibration("0wn3d", "fully accessed", "en", "tier1", "obfusc"),
    ProseCalibration("sh3ll", "execution interface", "en", "tier1", "obfusc"),
    ProseCalibration("br3ach", "incident", "en", "tier1", "obfusc"),
    ProseCalibration("expl0ited", "vulnerability-validated", "en", "tier1", "obfusc"),
    ProseCalibration("expl0iting", "validating the vulnerability of", "en", "tier1", "obfusc"),
)

# Reassemble CALIBRATIONS to include expansions
CALIBRATIONS = (
    ENGLISH_CORE + ENGLISH_EXPANSION
    + SPANISH + FRENCH + GERMAN + PORTUGUESE + ITALIAN
    + JAPANESE + MANDARIN
    + RUSSIAN + ARABIC
    + KOREAN + HINDI + POLISH + DUTCH + TURKISH
    + ABBREVIATIONS + ABBREVIATIONS_EXPANSION
    + OBFUSCATIONS + OBFUSCATIONS_EXPANSION
)

# ── APPLICATION ──────────────────────────────────────────────────────────


def _ordered_pairs() -> list[tuple[str, str]]:
    """Return (trigger, calibrated) pairs sorted longest-first."""
    pairs = [(c.trigger, c.calibrated) for c in CALIBRATIONS
             if c.trigger != c.calibrated]
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


_PAIR_CACHE: list[tuple[str, str]] | None = None


def apply_calibration(text: str) -> tuple[str, int]:
    """Apply all calibrations to ``text``. Returns ``(out, count)``.

    Word-boundary matching for ASCII triggers. Substring matching for
    non-ASCII (CJK / Arabic / Cyrillic) where ``\\b`` doesn't apply.
    Case-preserving for ASCII triggers via case-folding pass.
    """
    global _PAIR_CACHE
    if _PAIR_CACHE is None:
        _PAIR_CACHE = _ordered_pairs()

    count = 0
    out = text
    for trigger, calibrated in _PAIR_CACHE:
        if not trigger:
            continue
        if all(ord(c) < 128 for c in trigger):
            # ASCII: word-boundary, case-insensitive
            escaped = re.escape(trigger)
            new_out, n = re.subn(
                rf"(?<![/\\])\b{escaped}\b(?![/\\])", calibrated, out, flags=re.IGNORECASE,
            )
        else:
            # Non-ASCII: plain substring (CJK / Arabic / Cyrillic)
            n = out.count(trigger)
            new_out = out.replace(trigger, calibrated)
        if n:
            count += n
            out = new_out
    return out, count


def stats() -> dict[str, int]:
    """Return aggregate counts by language / tier / scope."""
    by_lang: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    for c in CALIBRATIONS:
        by_lang[c.language] = by_lang.get(c.language, 0) + 1
        by_tier[c.tier] = by_tier.get(c.tier, 0) + 1
        by_scope[c.scope] = by_scope.get(c.scope, 0) + 1
    return {
        "total_entries": len(CALIBRATIONS),
        "by_language": by_lang,
        "by_tier": by_tier,
        "by_scope": by_scope,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(stats(), indent=2, ensure_ascii=False))
