from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ENGINE: "CalibrationEngine | None" = None


def tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parent


def resolve_mode() -> str:
    _t = tools_path()
    if str(_t) not in sys.path:
        sys.path.insert(0, str(_t))
    from io_state import env_mode  # noqa: PLC0415
    return env_mode()


def _preserve_case(matched: str, replacement: str) -> str:
    if matched.isupper():
        return replacement.upper()
    if matched and matched[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _compile_patterns(cals: tuple) -> tuple:
    patterns = []
    for c in cals:
        if c.scope in ("identifier", "module-name"):
            patterns.append(re.compile(rf"\b{re.escape(c.original)}\b"))
        else:
            patterns.append(
                re.compile(rf"\b{re.escape(c.original)}\b", re.IGNORECASE)
            )
    return tuple(patterns)


@dataclass(frozen=True)
class CalibrationEngine:
    tier1_cals: tuple
    tier2_cals: tuple
    tier1_patterns: tuple
    tier2_patterns: tuple

    @classmethod
    def build(cls, include_tier2: bool = True) -> "CalibrationEngine":
        _t = tools_path()
        if str(_t) not in sys.path:
            sys.path.insert(0, str(_t))
        from vocabulary_map import by_severity  # noqa: PLC0415
        t1 = by_severity("tier1")
        t2 = by_severity("tier2") if include_tier2 else ()
        return cls(
            tier1_cals=t1,
            tier2_cals=t2,
            tier1_patterns=_compile_patterns(t1),
            tier2_patterns=_compile_patterns(t2),
        )

    def apply(self, text: str, *, prose: bool = False) -> tuple[str, int, int]:
        result, t1_hits = text, 0
        for cal, pat in zip(self.tier1_cals, self.tier1_patterns):
            if cal.scope in ("identifier", "module-name"):
                result, n = pat.subn(cal.calibrated, result)
            else:
                result, n = pat.subn(
                    lambda m, c=cal: _preserve_case(m.group(0), c.calibrated), result,
                )
            t1_hits += n
        t2_hits = 0
        for cal, pat in zip(self.tier2_cals, self.tier2_patterns):
            if cal.scope in ("identifier", "module-name"):
                result, n = pat.subn(cal.calibrated, result)
            else:
                result, n = pat.subn(
                    lambda m, c=cal: _preserve_case(m.group(0), c.calibrated), result,
                )
            t2_hits += n
        return result, t1_hits, t2_hits

    def score(self, text: str) -> float:
        lines = max(len(text.splitlines()), 1)
        raw = sum(len(p.findall(text)) * 10.0 for p in self.tier1_patterns)
        raw += sum(len(p.findall(text)) * 2.0 for p in self.tier2_patterns)
        return min(100.0, round(raw / lines * 1000, 1))


def build_engine(include_tier2: bool = True) -> CalibrationEngine:
    """Return the module-level CalibrationEngine singleton.

    The first call builds and caches the engine with the given include_tier2
    value; subsequent calls return the cached instance regardless of the
    argument. All callers in this codebase use the default (True).
    """
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CalibrationEngine.build(include_tier2=include_tier2)
    return _ENGINE
