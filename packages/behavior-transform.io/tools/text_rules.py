#!/usr/bin/env python3
"""Adapter for local text rules.

Primary tools use this module for loading, applying, and auditing the
workspace text-rule table. Compatibility source locations stay isolated here
so command, read, write, and fetch helpers can share one maintained path.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parent

_PROSE_SCOPES = frozenset({"free-prose", "verb-prose", "noun-prose"})
_DEFAULT_SOURCE_NAMES = (
    "vocabulary_map.py",
    "prose_vocabulary_map.py",
)
_SOURCE_CANDIDATES = (
    _ROOT / "vocabulary_map.py",
)


@dataclass(frozen=True)
class TextRule:
    pattern: re.Pattern[str]
    replacement: str
    tier: str


def _source_paths() -> list[Path]:
    paths: list[Path] = []
    for env_name in ("WARDEN_TEXT_RULE_SOURCE", "WARDEN_VOCABULARY_MAP"):
        value = os.environ.get(env_name)
        if value:
            paths.append(Path(value))
    paths.extend(_SOURCE_CANDIDATES)
    return paths


def _load_by_path(path: Path) -> ModuleType | None:
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("local_text_rule_source", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["local_text_rule_source"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop("local_text_rule_source", None)
        return None
    return module


def load_rule_source() -> ModuleType | None:
    """Load the first available local text-rule source."""
    for path in _source_paths():
        module = _load_by_path(path)
        if module is not None:
            return module
    return None


def _tier_name(severity: str) -> str:
    value = (severity or "").lower()
    if value in ("tier1", "tier_1", "t1"):
        return "T1"
    if value in ("tier2", "tier_2", "t2"):
        return "T2"
    return value.upper() or "??"


def collect_text_rules(
    source: ModuleType | None = None,
    *,
    prose_sensitive: bool = False,
) -> list[TextRule]:
    """Build the local replacement table."""
    module = source if source is not None else load_rule_source()
    if module is None:
        return []

    records = getattr(module, "CALIBRATIONS", ())
    keep = set(getattr(module, "KEEP_TERMS", ()) or ())
    keep_lower = {item.lower() if isinstance(item, str) else item for item in keep}

    candidates: list[tuple[str, str, str, bool]] = []
    for record in records:
        original = getattr(record, "original", None)
        replacement = getattr(record, "calibrated", None)
        severity = getattr(record, "severity", "") or ""
        scope = getattr(record, "scope", "") or ""
        if not isinstance(original, str) or not isinstance(replacement, str):
            continue
        if original.lower() in keep_lower:
            continue
        candidates.append((original, replacement, _tier_name(severity), scope in _PROSE_SCOPES))

    candidates.sort(key=lambda item: len(item[0]), reverse=True)
    rules: list[TextRule] = []
    for original, replacement, tier, is_prose in candidates:
        flags = re.IGNORECASE if (not prose_sensitive or is_prose) else 0
        pattern = re.compile(r"\b" + re.escape(original) + r"\b", flags)
        rules.append(TextRule(pattern=pattern, replacement=replacement, tier=tier))
    return rules


def apply_text_rules(text: str, rules: list[TextRule]) -> tuple[str, Counter]:
    """Apply local text rules and return the updated text plus counters."""
    counter: Counter = Counter()
    for rule in rules:
        def _replace(_match: re.Match[str], _rule: TextRule = rule) -> str:
            counter[_rule.tier] += 1
            return _rule.replacement

        text = rule.pattern.sub(_replace, text)
    return text, counter


def scan_text_rules(text: str, rules: list[TextRule]) -> tuple[Counter, list[tuple[str, str, str]]]:
    """Return counters and a compact list of matched text-rule entries."""
    counter: Counter = Counter()
    seen: dict[str, tuple[str, str, str]] = {}
    for rule in rules:
        for match in rule.pattern.finditer(text):
            matched = match.group(0)
            counter[rule.tier] += 1
            seen.setdefault(matched.lower(), (matched, rule.replacement, rule.tier))
    return counter, list(seen.values())


def is_rule_source_path(path: Path) -> bool:
    """Return true when a path points at a compatibility rule source."""
    try:
        normalized = path.resolve().as_posix().lower()
    except OSError:
        normalized = path.as_posix().lower()
    return any(name in normalized for name in _DEFAULT_SOURCE_NAMES)
