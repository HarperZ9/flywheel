"""extract.py -- the rules that turn transcript text into candidate records.

An importer reads what a session said and proposes what might be worth keeping.
The rules are fixed patterns, not a model, so the same transcript always gives
the same candidates and every candidate names the rule that produced it:

  todo-marker       `TODO: ...` or an unchecked `- [ ] ...` line  -> open work item
  decision-phrase   "we decided to X (because Y)", "we went with X" -> proposed decision
  failed-phrase     "I tried X but Y", "X did not work (because Y)" -> rejected decision,
                    with X as a rejected alternative and Y as its reason
  plan-tool         the last plan a tool call wrote (Claude Code TodoWrite, Codex
                    update_plan); pending and in-progress steps -> work items
  session-summary   the session's own summary line -> focus goal
  first-prompt      the first line of the first user prompt, when there is no
                    summary -> focus goal

Nothing a rule proposes is accepted. A candidate becomes a proposed record that
a person accepts or rejects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# A clause character: anything but a sentence end. A dot inside a name or a URL
# (pyproject.toml, db.internal) is followed by a non-space, so it is not an end.
_C = r"(?:[^.!?\n]|[.!?](?=\S))"
_END = r"(?=[.!?](?:\s|$)|\n|$)"
DECISION_RE = re.compile(
    r"\b(?:we|I)\s+(?:have\s+|'ve\s+)?(?:decided|chose|settled on|went with|"
    r"are going with|will go with)\s+(?:to\s+)?(?P<what>" + _C + r"{3,200}?)"
    r"(?:\s+because\s+(?P<why>" + _C + r"{3,300}?))?" + _END, re.IGNORECASE)
TRIED_RE = re.compile(
    r"\b(?:I|we)\s+tried\s+(?P<what>" + _C + r"{3,200}?),?\s+but\s+(?P<why>"
    + _C + r"{3,300}?)" + _END, re.IGNORECASE)
DIDNT_RE = re.compile(
    r"(?P<what>" + _C + r"{3,200}?)\s+(?:did not|didn't|does not|doesn't) work"
    r"(?:\s+because\s+(?P<why>" + _C + r"{3,300}?))?" + _END, re.IGNORECASE)
TODO_RE = re.compile(r"\bTODO[:\s]\s*(?P<what>" + _C + r"{3,200})")
CHECKBOX_RE = re.compile(r"(?m)^\s*[-*]\s+\[ \]\s+(?P<what>.{3,200})$")
NO_REASON = "reported as not working; the source gives no reason"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One proposed record before scrubbing: its kind, the payload, the rule
    that produced it and the source line it came from."""

    kind: str
    rule: str
    line: int
    data: dict
    native: str | None = None


@dataclass
class TextSeen:
    """Normalized candidate keys already proposed, so a phrase repeated across a
    session is proposed once and counted as a duplicate after that."""

    keys: set = field(default_factory=set)
    duplicates: int = 0

    def first(self, kind: str, text: str) -> bool:
        key = (kind, " ".join(text.lower().split()))
        if key in self.keys:
            self.duplicates += 1
            return False
        self.keys.add(key)
        return True


def _flat(text: str) -> str:
    return " ".join(text.split())


def _decision(match: re.Match[str], line: int) -> Candidate:
    what = _flat(match.group("what"))
    why = match.group("why")
    data = {"title": what, "status": "proposed", "decision": what,
            "context": _flat(why) if why else _flat(match.group(0))}
    return Candidate("adr-decision", "decision-phrase", line, data)


def _failed(match: re.Match[str], line: int) -> Candidate:
    what = _flat(match.group("what"))
    why = _flat(match.group("why")) if match.group("why") else NO_REASON
    data = {"title": f"Tried: {what}", "status": "rejected", "decision": what,
            "context": _flat(match.group(0)),
            "rejected_alternatives": [{"option": what, "reason": why}]}
    return Candidate("adr-decision", "failed-phrase", line, data)


def _failed_candidates(text: str, line: int, seen: TextSeen) -> list[Candidate]:
    found: list[Candidate] = []
    tried_spans = []
    for match in TRIED_RE.finditer(text):
        tried_spans.append(match.span())
        if seen.first("failed", match.group("what")):
            found.append(_failed(match, line))
    for match in DIDNT_RE.finditer(text):
        start, end = match.span()
        if any(start < t_end and t_start < end for t_start, t_end in tried_spans):
            continue
        if seen.first("failed", match.group("what")):
            found.append(_failed(match, line))
    return found


def text_candidates(text: str, line: int, seen: TextSeen) -> list[Candidate]:
    """Every rule-matched candidate in one message's text."""
    found: list[Candidate] = []
    for match in DECISION_RE.finditer(text):
        if seen.first("decision", match.group("what")):
            found.append(_decision(match, line))
    found += _failed_candidates(text, line, seen)
    for pattern in (TODO_RE, CHECKBOX_RE):
        for match in pattern.finditer(text):
            what = _flat(match.group("what"))
            if seen.first("todo", what):
                found.append(Candidate("work-item", "todo-marker", line,
                                       {"title": what, "status": "open"}))
    return found


_PLAN_STATUS = {"pending": "open", "in_progress": "in-progress"}


def plan_candidates(steps: list[tuple[str, str]], line: int) -> tuple[list[Candidate], int]:
    """Work items from the last plan a tool wrote: (text, status) pairs.
    Returns the candidates and the number of completed steps dropped."""
    found, closed = [], 0
    for text, status in steps:
        mapped = _PLAN_STATUS.get(status)
        if mapped is None or not str(text).strip():
            closed += 1
            continue
        found.append(Candidate("work-item", "plan-tool", line,
                               {"title": _flat(str(text)), "status": mapped}))
    return found, closed


def focus_candidate(goal: str, line: int, rule: str, *, branch: str | None,
                    areas: list[str]) -> Candidate:
    data = {"goal": _flat(goal), "branch": branch, "areas": areas or None}
    return Candidate("workspace-focus", rule, line,
                     {k: v for k, v in data.items() if v is not None})
