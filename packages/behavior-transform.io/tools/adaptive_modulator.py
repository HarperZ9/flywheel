"""Adaptive semantic modulation engine.

Extends the base semantic modulator with:
  - Context-aware modulation depth (adjusts intensity based on input)
  - Input normalization (leetspeak, Unicode homoglyphs, spacing tricks)
  - Density-based escalation (denser operational language triggers deeper
    vocabulary translation passes)
  - Multi-pass convergence (iterates until the output stabilizes)
  - Provenance-tracked layer composition with rollback support

The adaptive modulator observes the input, determines how much
vocabulary translation to apply based on operational density, normalizes
any encoding tricks in the source text, and produces output in a
consulting register that aligns with provider terms of service.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


# --- Obfuscation normalization ------------------------------------------------

_LEET_MAP: dict[str, str] = {
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s",
    "7": "t", "8": "b", "9": "g", "@": "a", "$": "s",
    "!": "i", "|": "l", "+": "t", "^": "a",
}

_HOMOGLYPH_MAP: dict[str, str] = {
    "а": "a", "е": "e", "о": "o", "р": "p",
    "с": "c", "у": "y", "х": "x", "Ь": "b",
    "А": "A", "Е": "E", "О": "O", "Р": "P",
    "С": "C", "У": "Y", "Х": "X",
    "•": ".", "․": ".", "‧": ".",
    "​": "", "‌": "", "‍": "", "﻿": "",
}

_SPACING_RE = re.compile(r"(?<=\w)[.·]{1,2}(?=\w)")
_ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿]")


def normalize_obfuscation(text: str) -> tuple[str, int]:
    """Remove common obfuscation patterns and return (normalized, changes_count)."""
    changes = 0

    # Pass 1: zero-width characters
    cleaned, n = _ZERO_WIDTH_RE.subn("", text)
    changes += n

    # Pass 2: homoglyph normalization
    chars = []
    for ch in cleaned:
        if ch in _HOMOGLYPH_MAP:
            chars.append(_HOMOGLYPH_MAP[ch])
            changes += 1
        else:
            chars.append(ch)
    cleaned = "".join(chars)

    # Pass 3: leetspeak (only when surrounded by alpha context)
    result = []
    for i, ch in enumerate(cleaned):
        if ch in _LEET_MAP:
            before_alpha = i > 0 and cleaned[i - 1].isalpha()
            after_alpha = i < len(cleaned) - 1 and cleaned[i + 1].isalpha()
            if before_alpha or after_alpha:
                result.append(_LEET_MAP[ch])
                changes += 1
            else:
                result.append(ch)
        else:
            result.append(ch)
    cleaned = "".join(result)

    # Pass 4: suspicious spacing (h.a.c.k → hack)
    def _collapse_spacing(m: re.Match) -> str:
        nonlocal changes
        changes += 1
        return ""
    cleaned = _SPACING_RE.sub(_collapse_spacing, cleaned)

    return cleaned, changes


# --- Density analysis ---------------------------------------------------------

@dataclass
class DensityProfile:
    """Characterizes the semantic density of input text."""
    total_tokens: int = 0
    sensitive_tokens: int = 0
    density_ratio: float = 0.0
    escalation_level: int = 0  # 0=none, 1=light, 2=standard, 3=deep

    @property
    def needs_deep_pass(self) -> bool:
        return self.escalation_level >= 2


_DENSITY_MARKERS = re.compile(
    r"\b(exploit|payload|inject|bypass|evasion|exfiltrat|credential|"
    r"privilege|escalat|lateral|persist|obfuscat|trojan|backdoor|"
    r"rootkit|beacon|implant|shellcode|reverse.shell|bind.shell|"
    r"keylog|ransomw|cryptolock|botnet|worm|dropper|stager)\b",
    re.IGNORECASE,
)


def analyze_density(text: str) -> DensityProfile:
    """Compute the semantic density profile of input text."""
    tokens = text.split()
    total = len(tokens)
    if total == 0:
        return DensityProfile()

    sensitive = len(_DENSITY_MARKERS.findall(text))
    ratio = sensitive / total if total > 0 else 0.0

    if ratio >= 0.15:
        level = 3
    elif ratio >= 0.08:
        level = 2
    elif ratio >= 0.03:
        level = 1
    else:
        level = 0

    return DensityProfile(
        total_tokens=total,
        sensitive_tokens=sensitive,
        density_ratio=ratio,
        escalation_level=level,
    )


# --- Adaptive modulation engine -----------------------------------------------

@dataclass
class AdaptiveLayer:
    """Record of one adaptive pass."""
    pass_number: int
    changes: int
    obfuscation_normalized: int = 0
    density_level: int = 0
    converged: bool = False


@dataclass
class AdaptiveResult:
    """Result of adaptive modulation."""
    original: str
    normalized: str
    modulated: str
    layers: list[AdaptiveLayer] = field(default_factory=list)
    density: DensityProfile = field(default_factory=DensityProfile)
    total_passes: int = 0
    total_changes: int = 0
    obfuscation_detected: bool = False

    @property
    def changed(self) -> bool:
        return self.modulated != self.original

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "modulated": self.modulated,
            "changed": self.changed,
            "total_passes": self.total_passes,
            "total_changes": self.total_changes,
            "obfuscation_detected": self.obfuscation_detected,
            "density": {
                "total_tokens": self.density.total_tokens,
                "sensitive_tokens": self.density.sensitive_tokens,
                "density_ratio": round(self.density.density_ratio, 4),
                "escalation_level": self.density.escalation_level,
            },
            "layers": [
                {
                    "pass": l.pass_number,
                    "changes": l.changes,
                    "obfuscation_normalized": l.obfuscation_normalized,
                    "converged": l.converged,
                }
                for l in self.layers
            ],
        }


def adaptive_modulate(
    text: str,
    *,
    max_passes: int = 3,
    convergence_threshold: int = 0,
) -> AdaptiveResult:
    """Run adaptive multi-pass modulation.

    Args:
        text: input text
        max_passes: maximum modulation iterations (1-5)
        convergence_threshold: stop when changes per pass <= this value
    """
    max_passes = max(1, min(5, max_passes))

    # Step 1: Obfuscation normalization
    normalized, obf_count = normalize_obfuscation(text)
    obfuscation_detected = obf_count > 0

    # Step 2: Density analysis (determines modulation depth)
    density = analyze_density(normalized)

    # Step 3: Multi-pass modulation
    working = normalized
    layers: list[AdaptiveLayer] = []
    total_changes = obf_count

    for pass_num in range(1, max_passes + 1):
        # Apply vocabulary substitution pass
        try:
            from vocabulary_substitutions import apply_substitutions
            sub_result = apply_substitutions(working)
            pass_changes = len(sub_result.applied_rules)
            if pass_changes > 0:
                working = sub_result.substituted
        except Exception:
            pass_changes = 0

        # Apply semantic modulation if density warrants it
        sem_changes = 0
        if density.needs_deep_pass or pass_num == 1:
            try:
                from semantic_modulator import semantic_modulator
                mod = semantic_modulator()
                mod_result = mod.modulate(working)
                sem_changes = mod_result.compound_rewrites + len(mod_result.technique_mappings)
                if sem_changes > 0:
                    working = mod_result.modulated
            except Exception:
                pass

        changes_this_pass = pass_changes + sem_changes
        total_changes += changes_this_pass
        converged = changes_this_pass <= convergence_threshold

        layers.append(AdaptiveLayer(
            pass_number=pass_num,
            changes=changes_this_pass,
            obfuscation_normalized=obf_count if pass_num == 1 else 0,
            density_level=density.escalation_level,
            converged=converged,
        ))

        if converged:
            break

    return AdaptiveResult(
        original=text,
        normalized=normalized,
        modulated=working,
        layers=layers,
        density=density,
        total_passes=len(layers),
        total_changes=total_changes,
        obfuscation_detected=obfuscation_detected,
    )


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="adaptive-modulate",
        description="Adaptive multi-pass semantic modulation with obfuscation detection",
    )
    parser.add_argument("text", help="Input text to modulate")
    parser.add_argument("--max-passes", type=int, default=3, help="Max modulation passes (1-5)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    result = adaptive_modulate(args.text, max_passes=args.max_passes)

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        lines = [
            f"Adaptive Modulation ({result.total_passes} pass{'es' if result.total_passes != 1 else ''}):",
            f"  Changed: {result.changed}",
            f"  Obfuscation detected: {result.obfuscation_detected}",
            f"  Density: {result.density.density_ratio:.1%} "
            f"(level {result.density.escalation_level})",
            f"  Total changes: {result.total_changes}",
        ]
        if result.obfuscation_detected:
            lines.append(f"  Normalized: {result.normalized[:80]}...")
        for layer in result.layers:
            status = "converged" if layer.converged else f"{layer.changes} changes"
            lines.append(f"  Pass {layer.pass_number}: {status}")
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
