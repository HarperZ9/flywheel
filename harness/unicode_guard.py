"""unicode_guard.py -- neutralize text-spoofing before a human approves a string.

A superior alternative to a bidirectional-override replacer. Neutralizing only
bidi controls leaves the rest of the text-deception surface open: an approval
preview can still be spoofed with zero-width joiners, tag characters, invisible
separators, homoglyph letters from another script, or a compatibility form that
reads as ASCII but is not. This covers that surface and, crucially, records what
it neutralized as a witnessed receipt field rather than performing a silent
display transform. A silent transform is unfalsifiable; a receipt field is not.

Classes detected:
  - BIDI_CONTROL          U+202A..202E, U+2066..2069, U+200E/200F, U+061C
  - ZERO_WIDTH            ZWSP/ZWNJ/ZWJ, word joiner, BOM, Mongolian vowel sep
  - INVISIBLE             soft hyphen, invisible math operators, blank fillers
  - TAG_CHAR              U+E0000..E007F (the Trojan-Source tag block)
  - VARIATION_SELECTOR    U+FE00..FE0F, U+E0100..E01EF
  - COMBINING_EXCESS      long runs of combining marks (Zalgo)
  - CONTROL_CHAR          C0/C1 controls except tab, newline, carriage return
  - CONFUSABLE            a letter from another script inside a same-script word
  - NORMALIZATION_DIVERGENCE  a codepoint whose NFKC form differs from itself

Honest nulls. Mixed-script confusable detection covers the Latin/Cyrillic/Greek
family, the families that share look-alikes and drive real attacks; an all-one-
script confusable of an all-Latin target (every letter swapped) is not caught by
mixed-script alone and would need the full Unicode confusables table. The digest
is over the findings, not the raw text, so the receipt field is safe to store.
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field

from .receipt_fields import _NominalEnum, canonical


class ThreatClass(_NominalEnum):
    BIDI_CONTROL = "bidi_control"
    ZERO_WIDTH = "zero_width"
    INVISIBLE = "invisible"
    TAG_CHAR = "tag_char"
    VARIATION_SELECTOR = "variation_selector"
    COMBINING_EXCESS = "combining_excess"
    CONTROL_CHAR = "control_char"
    CONFUSABLE = "confusable"
    NORMALIZATION_DIVERGENCE = "normalization_divergence"


_BIDI = frozenset({0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                   0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F, 0x061C})
_ZERO_WIDTH = frozenset({0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E})
_INVISIBLE = frozenset({0x00AD, 0x2061, 0x2062, 0x2063, 0x2064,
                        0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800})
_KEEP_CONTROL = frozenset({0x09, 0x0A, 0x0D})
_COMBINING_RUN_MAX = 4
_CONFUSABLE_FAMILIES = frozenset({"LATIN", "CYRILLIC", "GREEK"})


@dataclass(frozen=True)
class Finding:
    threat_class: ThreatClass
    codepoint: int
    position: int
    detail: str = ""

    def to_dict(self) -> dict:
        return {"threat_class": self.threat_class.value, "codepoint": self.codepoint,
                "position": self.position, "detail": self.detail}


@dataclass
class NeutralizeResult:
    sanitized: str
    findings: list[Finding] = field(default_factory=list)
    original_length: int = 0
    nfkc: str | None = None   # NFKC form, present only when it diverges

    @property
    def had_threats(self) -> bool:
        return bool(self.findings)

    def classes(self) -> list[str]:
        return sorted({f.threat_class.value for f in self.findings})

    def findings_digest(self) -> str:
        payload = canonical([f.to_dict() for f in
                             sorted(self.findings, key=lambda f: f.position)])
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_receipt_field(self) -> dict:
        """The witnessed field. Counts and a digest, never the raw spoof text."""
        return {
            "had_threats": self.had_threats,
            "threat_count": len(self.findings),
            "classes": self.classes(),
            "findings_digest": self.findings_digest(),
            "original_length": self.original_length,
        }


def _marker(cp: int) -> str:
    return f"[U+{cp:04X}]"


def _script_family(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    try:
        return unicodedata.name(ch).split(" ", 1)[0]
    except ValueError:
        return None


def _codepoint_class(cp: int) -> ThreatClass | None:
    if cp in _BIDI:
        return ThreatClass.BIDI_CONTROL
    if cp in _ZERO_WIDTH:
        return ThreatClass.ZERO_WIDTH
    if cp in _INVISIBLE:
        return ThreatClass.INVISIBLE
    if 0xE0000 <= cp <= 0xE007F:
        return ThreatClass.TAG_CHAR
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:
        return ThreatClass.VARIATION_SELECTOR
    if (cp <= 0x1F or 0x80 <= cp <= 0x9F) and cp not in _KEEP_CONTROL:
        return ThreatClass.CONTROL_CHAR
    return None


def _confusable_positions(text: str) -> dict[int, str]:
    """Positions of letters that sit in a word dominated by another confusable
    script. Value is the dominant family, for the finding detail."""
    marked: dict[int, str] = {}
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
        token = text[i:j]
        fams: dict[str, int] = {}
        for ch in token:
            fam = _script_family(ch)
            if fam in _CONFUSABLE_FAMILIES:
                fams[fam] = fams.get(fam, 0) + 1
        if len(fams) > 1:
            dominant = max(fams, key=lambda f: (fams[f], f))
            for k, ch in enumerate(token):
                fam = _script_family(ch)
                if fam in _CONFUSABLE_FAMILIES and fam != dominant:
                    marked[i + k] = dominant
        i = j
    return marked


def neutralize(text: str) -> NeutralizeResult:
    """Detect and neutralize text-spoofing. Returns sanitized text with every
    dangerous codepoint replaced by a visible [U+XXXX] marker, the findings, and
    the NFKC form when it diverges."""
    findings: list[Finding] = []
    confusable = _confusable_positions(text)

    # NFKC divergence, per codepoint (a char whose compatibility form differs).
    nfkc = unicodedata.normalize("NFKC", text)
    diverges = nfkc != text
    nfkc_positions: set[int] = set()
    if diverges:
        for idx, ch in enumerate(text):
            if unicodedata.normalize("NFKC", ch) != ch and _codepoint_class(ord(ch)) is None:
                nfkc_positions.add(idx)

    out: list[str] = []
    combining_run = 0
    for idx, ch in enumerate(text):
        cp = ord(ch)
        cls = _codepoint_class(cp)

        if unicodedata.combining(ch):
            combining_run += 1
        else:
            combining_run = 0

        if cls is not None:
            findings.append(Finding(cls, cp, idx))
            out.append(_marker(cp))
            continue
        if combining_run > _COMBINING_RUN_MAX:
            findings.append(Finding(ThreatClass.COMBINING_EXCESS, cp, idx,
                                    f"combining mark #{combining_run} in run"))
            out.append(_marker(cp))
            continue
        if idx in confusable:
            findings.append(Finding(ThreatClass.CONFUSABLE, cp, idx,
                                    f"letter outside dominant script {confusable[idx]}"))
            out.append(_marker(cp))
            continue
        if idx in nfkc_positions:
            findings.append(Finding(ThreatClass.NORMALIZATION_DIVERGENCE, cp, idx,
                                    "codepoint NFKC form differs"))
            out.append(ch)   # keep the char; record the divergence, do not mangle
            continue
        out.append(ch)

    return NeutralizeResult(
        sanitized="".join(out),
        findings=sorted(findings, key=lambda f: f.position),
        original_length=len(text),
        nfkc=nfkc if diverges else None,
    )


def is_clean(text: str) -> bool:
    """True when no spoofing surface is present. Convenience over neutralize()."""
    return not neutralize(text).had_threats
