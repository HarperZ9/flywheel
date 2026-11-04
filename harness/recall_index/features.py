"""Explicit signal features and a fixed, inspectable score.

Every weight is a constant in this file. The score decides what is kept;
the feature list is stored beside each unit so a reader can see why.
"""

import re

F_NUM = re.compile(r"\bF\d{1,4}\b")
PR_REF = re.compile(r"\b[\w.-]+/[\w.-]+#\d{1,5}\b|\b[\w-]+#\d{1,5}\b|\bPR\s*#?\d{1,5}\b")
SHA = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
PATH = re.compile(r"(?:[A-Za-z]:[\\/]|~/|\.{1,2}/)[^\s\"'`<>|*?]{2,200}"
                  r"|\b[\w.-]+(?:/[\w.-]+)+\.[A-Za-z0-9]{1,6}\b")
VERSION = re.compile(r"\bv?\d+\.\d+\.\d+\b")
NAME = re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9]*\b|\b[A-Z]{3,}[A-Z0-9]*\b"
                  r"|\b[a-z][a-z0-9]+(?:-[a-z0-9]+){1,4}\b")
QUOTE = re.compile(r"[\"“]([^\"”\n]{12,400})[\"”]")
KEEP = re.compile(r"\bkeep this\b", re.IGNORECASE)
RULING_CUE = re.compile(r"\b(?:yes|no|always|never|standing|we want|don't|do not|must"
                        r"|approved?|ruling|from now on|go ahead)\b", re.IGNORECASE)
DECISION = re.compile(r"\b(?:decision|decided|verdict|PASS|FAIL|null result|held|missed"
                      r"|adopt(?:ed)?|reject(?:ed)?|supersede[sd]?|merged|shipped"
                      r"|released|withdrawn|kill (?:rule )?fire[sd])\b")
_COMMON_NAMES = {"THE", "AND", "FOR", "NOT", "YOU", "API", "MCP", "JSON", "HTML", "CSS",
                 "URL", "PDF", "PNG", "TODO", "NOTE", "OK", "CPU", "GPU"}

MEASURE = re.compile(r"\b\d+\.\d+\b|\b\d+(?:\.\d+)? ?(?:percent|%)|\b\d+ of \d+\b")
BASE = {"summary": 1.5, "author": 3.0, "assistant": 0.5, "tool_call": 0.5, "relay": 1.0,
        "reference": 1.0, "tool_result": 0.0}
KEEP_MIN = {"summary": 0.0, "author": 0.0, "assistant": 1.5, "tool_call": 0.0, "relay": 1.0,
            "reference": 1.5, "tool_result": 99.0}


def entities(text: str) -> list[str]:
    """Stable, de-duplicated entity strings, in first-seen order."""
    found = []
    for rx in (F_NUM, PR_REF, SHA, VERSION, PATH, NAME):
        for m in rx.finditer(text):
            e = m.group(0).rstrip(".,;:)")
            if len(e) < 3 or e in _COMMON_NAMES:
                continue
            found.append(e)
    seen, out = set(), []
    for e in found:
        k = e.lower()
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out[:40]


def features(kind: str, text: str) -> dict:
    ents = entities(text)
    quotes = [q for q in QUOTE.findall(text) if RULING_CUE.search(q)] if kind == "author" else []
    return {
        "keep": bool(KEEP.search(text)),
        "ruling": bool(quotes) or (kind == "author" and bool(RULING_CUE.search(text))),
        "quotes": quotes[:3],
        "decisions": len(DECISION.findall(text)),
        "fnums": len(F_NUM.findall(text)),
        "measures": len(MEASURE.findall(text)),
        "entities": ents,
    }


def score(kind: str, feat: dict) -> float:
    s = BASE.get(kind, 0.0)
    s += 4.0 if feat["keep"] else 0.0
    s += 2.0 if feat["ruling"] else 0.0
    s += min(3, feat["decisions"]) * 1.0
    s += min(3, feat["fnums"]) * 0.5
    s += min(4, feat.get("measures", 0)) * 0.25
    s += min(8, len(feat["entities"])) * 0.25
    return round(s, 3)


def keep(kind: str, s: float) -> bool:
    return s >= KEEP_MIN.get(kind, 99.0)
