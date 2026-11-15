"""Vocabulary backend -- pluggable calibration map loader.

The package ships with no built-in vocabulary terms. Users supply their own
via one of these backends, in priority order:

  1. PREFIRE_VOCAB_MAP env var -> path to a vocabulary_map.py module
  2. Local vocabulary_map.py in the tools directory
  3. NullVocabBackend -- no-op (calibration is skipped, classification still runs)
"""

from __future__ import annotations

import importlib.util
import os
import re
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Term:
    original: str
    calibrated: str
    tier: str
    scope: str


class VocabBackend(ABC):
    @abstractmethod
    def terms(self) -> Sequence[Term]:
        ...


class NullVocabBackend(VocabBackend):
    def terms(self) -> Sequence[Term]:
        return []


class ModuleVocabBackend(VocabBackend):
    """Load calibrations from a vocabulary_map.py module file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cache: list[Term] | None = None

    def terms(self) -> Sequence[Term]:
        if self._cache is not None:
            return self._cache
        spec = importlib.util.spec_from_file_location("_prefire_vocab", self._path)
        if spec is None or spec.loader is None:
            self._cache = []
            return self._cache
        import sys as _sys
        mod = importlib.util.module_from_spec(spec)
        _sys.modules[mod.__name__] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            del _sys.modules[mod.__name__]
            self._cache = []
            return self._cache
        calibrations = getattr(mod, "CALIBRATIONS", ())
        keep = {k.lower() for k in (getattr(mod, "KEEP_TERMS", None) or [])}
        out: list[Term] = []
        for c in calibrations:
            orig = getattr(c, "original", None)
            cal = getattr(c, "calibrated", None)
            sev = (getattr(c, "severity", "") or "").lower()
            scope = (getattr(c, "scope", "") or "")
            if not isinstance(orig, str) or not isinstance(cal, str):
                continue
            if orig.lower() in keep:
                continue
            tier = "T1" if sev in ("tier1", "tier_1", "t1") else "T2"
            out.append(Term(orig, cal, tier, scope))
        out.sort(key=lambda t: len(t.original), reverse=True)
        self._cache = out
        return self._cache


_ACTIVE_BACKEND: VocabBackend | None = None


def register_backend(backend: VocabBackend) -> None:
    global _ACTIVE_BACKEND
    _ACTIVE_BACKEND = backend


def load_vocab_backend() -> VocabBackend:
    global _ACTIVE_BACKEND
    if _ACTIVE_BACKEND is not None:
        return _ACTIVE_BACKEND

    env_path = os.environ.get("PREFIRE_VOCAB_MAP", "").strip()
    if env_path:
        p = Path(env_path)
        if p.is_file():
            _ACTIVE_BACKEND = ModuleVocabBackend(p)
            return _ACTIVE_BACKEND

    local_map = Path(__file__).resolve().parent / "vocabulary_map.py"
    if local_map.is_file():
        _ACTIVE_BACKEND = ModuleVocabBackend(local_map)
        return _ACTIVE_BACKEND

    _ACTIVE_BACKEND = NullVocabBackend()
    return _ACTIVE_BACKEND


def build_patterns(backend: VocabBackend) -> list[tuple[re.Pattern[str], str, str]]:
    prose = {"free-prose", "verb-prose", "noun-prose"}
    out: list[tuple[re.Pattern[str], str, str]] = []
    for t in backend.terms():
        flags = re.IGNORECASE if t.scope in prose else 0
        pat = re.compile(r"\b" + re.escape(t.original) + r"\b", flags)
        out.append((pat, t.calibrated, t.tier))
    return out


def apply_patterns(
    text: str,
    patterns: list[tuple[re.Pattern[str], str, str]],
) -> tuple[str, Counter[str]]:
    counter: Counter[str] = Counter()
    for pat, dst, tier in patterns:
        def _repl(m: re.Match[str], _d: str = dst, _t: str = tier) -> str:
            counter[_t] += 1
            return _d
        text = pat.sub(_repl, text)
    return text, counter
