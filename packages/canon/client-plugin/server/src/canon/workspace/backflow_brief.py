"""backflow_brief.py -- read edits to the brief block back as proposed records.

The brief canon writes into an instruction file is generated, but people and
agents edit it: they tick a task, add one, reword the goal, note a quirk. Each
line the brief renders has a fixed shape, so an edited line can be read back:

  Goal: <goal>                              -> the focus, with the new goal
  - [<status>] <title> (<id>)               -> that work item, new status or title
  - [<status>] <title>                      -> a new work item
  - [<category>] <statement> (<id>)         -> that constraint, updated
  - [<category>] <statement>                -> a new constraint
  a removed work line                       -> that work item, status dropped
  a removed constraint line                 -> that constraint, retired

An edited line is paired with the line canon rendered for the same id, and only
the fields that differ from that line go into the proposal, so a status the
edit did not touch never overwrites a newer one. A mark is read loosely: `[x]`
means done and case does not matter. A line that names an id is never read as
a removal of that id, even when the rest of it no longer parses.

A line that fits none of these is not guessed at. It is returned as unmapped,
and so is every other removed line (a decision, a goal, a detail), written
`removed: <line>`, so the caller keeps all of them in one proposed memory
record and an edit is never lost. Lines labelled `[global]` or
`[from <project>]` belong to another scope and are never mapped to this
project's records. Removals are read only against a render canon wrote; without
one, an absent line says nothing.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from canon.schema import (
    CONSTRAINT_CATEGORIES,
    KIND_ENVIRONMENT_CONSTRAINT,
    KIND_WORK_ITEM,
    KIND_WORKSPACE_FOCUS,
    WORK_ITEM_STATUSES,
    Record,
)

_SECTION_RE = re.compile(r"^#{2,3} (Focus|Open work|Decisions|Constraints and quirks|Left out)$")
_TAG = r"(?P<tag> \[(?:global|from prj_[0-9a-f]{32})\])?"
_ITEM_RE = re.compile(r"^- \[(?P<mark>[A-Za-z-]+)\] (?P<text>.+?)"
                      r"(?: \((?P<id>[a-z0-9][a-z0-9-]*)\))?" + _TAG + r"$")
_ID_AT_END = re.compile(r"\(([a-z0-9][a-z0-9-]*)\)\s*(?:\[[^\]]*\])?\s*$")
_GOAL_RE = re.compile(r"^Goal: (?P<text>.+?)" + _TAG + r"$")
_QUIET = ("", "None recorded.")
_KIND_OF = {"Open work": KIND_WORK_ITEM, "Constraints and quirks": KIND_ENVIRONMENT_CONSTRAINT}
NO_CHANGE = object()


@dataclass(frozen=True, slots=True)
class Edit:
    """One in-place edit read back from a region: the rule that read it, the
    record it proposes (kind, id or None for a new one, data), the file line,
    and whether it retires the record."""

    rule: str
    kind: str
    rid: str | None
    data: dict
    line: int
    retire: bool = False


def _sections(body: str) -> list[tuple[str, str]]:
    section, out = "", []
    for line in body.split("\n"):
        line = line.rstrip()
        heading = _SECTION_RE.match(line)
        if heading:
            section = heading.group(1)
        out.append((section, line))
    return out


def _mark(value: str) -> str:
    lowered = value.lower()
    return "done" if lowered == "x" else lowered


def _base_items(base: list[tuple[str, str]]) -> dict:
    items = {}
    for section, text in base:
        item = _ITEM_RE.match(text)
        if item and item["id"] and not item["tag"]:
            items[item["id"]] = (section, _mark(item["mark"]), item["text"])
    return items


def _changed(current: Record, prior, fields: tuple[str, str], values: tuple[str, str]):
    """The record's data with only the fields that differ from the rendered
    line replaced; NO_CHANGE when the edit changes nothing."""
    data = dict(current.data)
    for index, (name, value) in enumerate(zip(fields, values)):
        if prior is None or value != prior[index + 1]:
            data[name] = value
    return NO_CHANGE if data == current.data else data


def _item(match, section: str, records: dict, line: int, base_items: dict):
    mark, text, rid = _mark(match["mark"]), match["text"], match["id"]
    work = section == "Open work"
    if mark not in (WORK_ITEM_STATUSES if work else CONSTRAINT_CATEGORIES):
        return None
    fields = ("status", "title") if work else ("category", "statement")
    current = records.get(rid)
    if rid and current is not None and current.kind == _KIND_OF[section]:
        data = _changed(current, base_items.get(rid), fields, (mark, text))
        if data is NO_CHANGE:
            return NO_CHANGE
        return Edit("brief-work" if work else "brief-constraint", current.kind, rid, data, line)
    if rid:
        return None
    return Edit("brief-new-work" if work else "brief-new-constraint", _KIND_OF[section],
                None, dict(zip(fields, (mark, text))), line)


def _map_line(section: str, text: str, records: dict, line: int, base_items: dict):
    if section == "Focus":
        goal = _GOAL_RE.match(text)
        if goal and not goal["tag"]:
            current = records.get("focus")
            base = dict(current.data) if current is not None else {}
            return Edit("brief-focus", KIND_WORKSPACE_FOCUS, "focus",
                        {**base, "goal": goal["text"]}, line)
        return None
    item = _ITEM_RE.match(text)
    if item is None or item["tag"] or section not in _KIND_OF:
        return None
    return _item(item, section, records, line, base_items)


def _removal(section: str, text: str, records: dict, referenced: set, line: int):
    """The edit a removed item line means, or None when it means none."""
    item = _ITEM_RE.match(text)
    if item is None or item["tag"] or not item["id"] or item["id"] in referenced:
        return None
    current = records.get(item["id"])
    if section not in _KIND_OF or current is None or current.kind != _KIND_OF[section]:
        return None
    if section == "Open work":
        return Edit("brief-removed-work", KIND_WORK_ITEM, item["id"],
                    {**current.data, "status": "dropped"}, line)
    return Edit("brief-removed-constraint", KIND_ENVIRONMENT_CONSTRAINT, item["id"],
                dict(current.data), line, retire=True)


def _removed(base: list, actual: list) -> list[tuple[int, str, str]]:
    """Base lines with no counterpart on disk, in base order with their index."""
    left = Counter(actual)
    out = []
    for index, key in enumerate(base):
        if left[key] > 0:
            left[key] -= 1
        else:
            out.append((index, *key))
    return out


def _removals(removed, records, referenced, goal_changed, line) -> tuple[list, list]:
    edits, notes, owner_index = [], [], None
    for index, section, text in removed:
        if text.strip() in _QUIET or section == "Left out":
            continue
        if text.startswith("  ") and owner_index is not None and index == owner_index + 1:
            owner_index = index  # a detail line of an item already mapped
            continue
        owner_index = None
        edit = _removal(section, text, records, referenced, line)
        named = _ID_AT_END.search(text)
        if edit is not None:
            edits.append(edit)
            owner_index = index
        elif named and named.group(1) in referenced:
            continue  # the line was changed, not removed
        elif not (section == "Focus" and text.startswith("Goal: ") and goal_changed):
            notes.append((line, f"removed: {text}"))
    return edits, notes


def brief_edits(actual: str, base: str, first_line: int, records: list[Record], *,
                has_base: bool) -> tuple[list[Edit], list[tuple[int, str]]]:
    """Every edit between the brief body canon wrote (`base`) and the one on
    disk (`actual`): the mapped edits, and the unmapped lines as (line, text).
    `first_line` is the file line number of the body's first line."""
    by_id = {r.id: r for r in records}
    base_lines, actual_lines = _sections(base), _sections(actual)
    remaining = Counter(base_lines)
    added: list[tuple[int, str, str]] = []
    for index, key in enumerate(actual_lines):
        if remaining[key] > 0:
            remaining[key] -= 1
        elif key[1].strip():
            added.append((first_line + index, *key))
    items = _base_items(base_lines)
    edits, unmapped = [], []
    for line, section, text in added:
        edit = _map_line(section, text, by_id, line, items)
        if edit is None:
            unmapped.append((line, text))
        elif edit is not NO_CHANGE:
            edits.append(edit)
    if has_base:
        referenced = {m.group(1) for _, s, t in added if s in _KIND_OF
                      for m in [_ID_AT_END.search(t)] if m}
        goal_changed = any(e.rule == "brief-focus" for e in edits)
        more, notes = _removals(_removed(base_lines, actual_lines), by_id, referenced,
                                goal_changed, first_line)
        edits += more
        unmapped += notes
    return edits, unmapped
