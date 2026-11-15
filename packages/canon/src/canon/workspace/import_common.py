"""import_common.py -- what every transcript importer shares.

An importer reads a session file another tool wrote and proposes records. Four
rules hold for every importer:

1. Declared loss. Each importer names, in advance, every category of content it
   drops. Every line it reads is either used or counted under one of those
   categories. Content that fits no category (an entry type the importer has
   never seen) is an undeclared loss and refuses the import, unless the person
   running it declares that drop with `--drop-type`, by its label or by the
   bare type name, which the report records.
2. Scrubbing. Every source string is scrubbed whole before any extraction rule
   reads it, so a length cap or a line break cannot cut a secret below the
   length its rule needs. Every candidate is scrubbed again after extraction,
   and the store refuses anything that still matches.
3. Project check. When the source names its repository or working directory,
   it must be this project, or the person must say `--accept-foreign-source`
   (`import_project.py`).
4. Proposals only. Imported records are written as proposed rows with an origin
   naming the source file, its digest, the line and the rule. Nothing renders
   until someone accepts it. A proposal already accepted, or rejected before, is
   not proposed again.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from canon.versions import PIN_IMPORT_REPORT
from canon.workspace import authoring
from canon.workspace.extract import (
    Candidate,
    TextSeen,
    focus_candidate,
    plan_candidates,
    text_candidates,
)
from canon.workspace.identity import ProjectIdentity
from canon.workspace.import_project import project_check, relative_area  # noqa: F401
from canon.workspace.import_source import ImportRefused, Source, read_jsonl  # noqa: F401
from canon.workspace.scrub import find_secrets, merge_hits, scrub

REPORT_SCHEMA = PIN_IMPORT_REPORT.kind_tag
_SHORT = {"work-item": "task", "adr-decision": "decision",
          "environment-constraint": "constraint"}
_ID_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_QUOTED = re.compile(r"'([^']*)'")
DOES_NOT_PROVE = (
    "Proposals come from fixed text patterns. They are candidates for a person to "
    "accept or reject, not facts about the project.",
    "Text that matches no rule is not stored, so a decision or task phrased in "
    "another way is not proposed.",
    "The scrubber redacts secret-shaped values it recognises. It does not prove "
    "the source held no other sensitive text.",
)
# The drops every importer shares. Each importer adds its own categories.
COMMON_DROPS = {
    "unmatched-text": "a message text block that matched no extraction rule",
    "duplicate-candidate": "a candidate already proposed from an earlier line",
    "superseded-plan": "a plan tool call before the last one",
    "closed-plan-step": "a completed, deleted or empty plan step",
    "outside-area": "an edited file path outside the project root or in a nested repository",
    "truncated-tail": "an unterminated final line cut off while the session was being written",
    "invalid-candidate": "a candidate that did not validate after scrubbing",
    "image": "an image or audio content part",
    "tool-call": "a tool call other than the plan tools and file edits; its input is not stored",
    "tool-output": "a tool result; its text is not stored",
    "session-id": "a session id that is not an id shape or looks like a secret; it is not stored",
}
MAX_AREAS = 10


class Ledger:
    """Counts of what an importer dropped, by declared category, and the
    content it met that no category covers."""

    def __init__(self, declared: dict[str, str], user_drops: frozenset[str]) -> None:
        self.declared = declared
        self.user_drops = user_drops
        self.counts = {category: 0 for category in declared}
        self.user_counts: dict[str, int] = {}
        self.undeclared: dict[str, list[int]] = {}

    def drop(self, category: str, n: int = 1) -> None:
        if category not in self.declared:
            raise KeyError(f"{category!r} is not a declared drop")
        self.counts[category] += n

    def unknown(self, label: str, line: int) -> None:
        if label in self.user_drops or bare_label(label) in self.user_drops:
            self.user_counts[label] = self.user_counts.get(label, 0) + 1
        else:
            self.undeclared.setdefault(label, []).append(line)


def bare_label(label: str) -> str:
    """The type name inside a label such as `entry type 'x'`, which
    `--drop-type` also accepts on its own."""
    match = _QUOTED.search(label)
    return match.group(1) if match else label


def accept_session_id(value: object, ledger: Ledger) -> str | None:
    """A session id the store may keep: an id shape that looks like no secret.
    Anything else is dropped and counted, never stored."""
    if not isinstance(value, str):
        return None
    if _ID_SHAPE.match(value) and not find_secrets(value):
        return value
    ledger.drop("session-id")
    return None


@dataclass
class Extraction:
    candidates: list[Candidate]
    ledger: Ledger
    session_id: str | None = None
    repository_url: str | None = None
    cwds: list[str] = field(default_factory=list)
    hits: dict[str, int] = field(default_factory=dict)


def proposal_id(importer: str, key: str, cand: Candidate, index: int) -> str:
    if cand.kind == "workspace-focus":
        return authoring.FOCUS_ID
    digest = hashlib.sha256(f"{importer}\n{key}\n{cand.line}\n{cand.rule}\n{index}"
                            .encode("utf-8")).hexdigest()[:12]
    return f"imp-{_SHORT[cand.kind]}-{digest}"


@dataclass
class Collector:
    """Gathers what the rules find while an importer walks a session, then
    orders it: focus first, then the last plan's open steps, then text
    candidates in source order. `start_turn` and `roll_back` let an importer
    discard the turns a session rolled back."""

    identity: ProjectIdentity
    ledger: Ledger
    seen: TextSeen = field(default_factory=TextSeen)
    text: list = field(default_factory=list)
    plans: list = field(default_factory=list)
    edits: dict = field(default_factory=dict)
    summary: tuple | None = None
    first_prompt: tuple | None = None
    branch: str | None = None
    hits: dict = field(default_factory=dict)
    turns: list = field(default_factory=list)

    def clean(self, text: str) -> str:
        """`text` scrubbed whole, its hits counted for the report."""
        result = scrub(text)
        merge_hits(self.hits, result.hits)
        return result.text

    def add_text(self, text: str, line: int, *, role: str) -> None:
        text = self.clean(text)
        if role == "user" and self.first_prompt is None and text.strip():
            self.first_prompt = (line, text.strip().splitlines()[0])
        found = text_candidates(text, line, self.seen)
        if found:
            self.text.extend(found)
        else:
            self.ledger.drop("unmatched-text")

    def add_plan(self, line: int, steps: list) -> None:
        self.plans.append((line, [(self.clean(str(text)), status) for text, status in steps]))

    def set_summary(self, line: int, text: str) -> None:
        self.summary = (line, self.clean(text))

    def add_edit(self, path: str) -> None:
        self.edits[path] = self.edits.get(path, 0) + 1

    def start_turn(self) -> None:
        self.turns.append((len(self.text), len(self.plans), dict(self.edits),
                           set(self.seen.keys), self.seen.duplicates, self.first_prompt))

    def roll_back(self, turns: int) -> int:
        """Discard everything gathered since the start of the last `turns`
        user turns. Returns how many candidates, plans and edits went."""
        if turns <= 0 or not self.turns:
            return 0
        mark = self.turns[max(0, len(self.turns) - turns)]
        del self.turns[max(0, len(self.turns) - turns):]
        n_text, n_plans, edits, keys, duplicates, first = mark
        gone = (len(self.text) - n_text) + (len(self.plans) - n_plans) + \
            sum(self.edits.values()) - sum(edits.values())
        del self.text[n_text:]
        del self.plans[n_plans:]
        self.edits, self.seen.keys, self.seen.duplicates = edits, keys, duplicates
        self.first_prompt = first
        return gone

    def _areas(self) -> list:
        ranked = sorted(self.edits.items(), key=lambda kv: (-kv[1], kv[0]))
        areas = []
        for path, _count in ranked:
            area = relative_area(path, self.identity)
            if area is None:
                self.ledger.drop("outside-area")
            elif area not in areas and len(areas) < MAX_AREAS:
                areas.append(area)
        return areas

    def finish(self) -> list:
        self.ledger.drop("duplicate-candidate", self.seen.duplicates)
        plan_items = []
        if self.plans:
            self.ledger.drop("superseded-plan", len(self.plans) - 1)
            line, steps = self.plans[-1]
            plan_items, closed = plan_candidates(steps, line)
            self.ledger.drop("closed-plan-step", closed)
        areas = self._areas()
        focus = []
        if self.summary is not None:
            focus = [focus_candidate(self.summary[1], self.summary[0], "session-summary",
                                     branch=self.branch, areas=areas)]
        elif self.first_prompt is not None:
            focus = [focus_candidate(self.first_prompt[1], self.first_prompt[0],
                                     "first-prompt", branch=self.branch, areas=areas)]
        return focus + plan_items + self.text
