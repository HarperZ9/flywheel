"""target_fidelity.py -- what each target cannot express, declared, and proved.

A block can ask for things a target's file format cannot deliver. Two are
tracked:

  activation.glob   the block applies only to files matching `applies_to`.
                    Every surface on the allow-list is a file the host loads
                    for every request, so none of them can scope one block.
                    The block is written always-on, with the patterns kept in
                    the sentinel and shown to the model as an `Applies to:`
                    line. That is a downgrade from a rule to advice.
  instruction.omitted  the markdown target has no instruction file, so its
                    pasted brief carries no block at all.
  text.at-import    an `@path` token after a space or at a line start, outside
                    a code span or fence, bare names included (`@README`,
                    `@package.json`). Claude Code and Gemini CLI read it in
                    their instruction files as a file import, and Cursor
                    includes an `@file` named in a rule as context, so the same
                    text means more there than in AGENTS.md. In the brief canon
                    writes for those hosts, each such token is put in a code
                    span, which all three read as text.

Each target declares, in advance, which of these it cannot keep and what it
does instead. `target_roundtrip` renders a block set into a new host file for
the target, runs the R0 round-trip verdict on it, checks the host's own
requirements (Cursor's frontmatter), and classifies every difference between
what a block asked for and what the host delivers. A difference the target did
not declare fails the verdict, the same rule the storage adapters follow.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from canon.fidelity import FidelityVerdict, roundtrip_report
from canon.region import splice_region
from canon.schema import Record
from canon.textblock import RenderRefused, render_region
from canon.workspace.hosts import cursor_frontmatter_problem, new_host_text
from canon.workspace.targets import target_for

GLOB = "activation.glob"
AT_IMPORT = "text.at-import"
OMITTED = "instruction.omitted"
_AT_IMPORT_RE = re.compile(r"(?:^|(?<=\s))@[./~A-Za-z][^\s`]*", re.MULTILINE)
_CODE_RE = re.compile(r"^```.*?^```[^\n]*$|(`+)[^`]*?\1", re.MULTILINE | re.DOTALL)
_TRAILING = ".,;:!?)]}'\""
_ALWAYS_ON = "the host loads the file for every request; the block is written " \
             "always-on and its patterns reach the model as an Applies to line"

DECLARED_DOWNGRADES: dict[str, dict[str, str]] = {
    "claude-code": {GLOB: _ALWAYS_ON,
                    AT_IMPORT: "Claude Code reads @path in CLAUDE.md as a file import"},
    "codex": {GLOB: _ALWAYS_ON},
    "gemini-cli": {GLOB: _ALWAYS_ON,
                   AT_IMPORT: "Gemini CLI reads @path in GEMINI.md as a file import"},
    "copilot": {GLOB: _ALWAYS_ON + "; path-specific .github/instructions files "
                "are not on the write allow-list"},
    "cursor": {GLOB: "canon's one rule is alwaysApply: true, which ignores globs; "
               "the patterns reach the model as an Applies to line",
               AT_IMPORT: "Cursor includes an @file named in a rule as context"},
    "markdown": {OMITTED: "the markdown target has no instruction file, so a pasted "
                          "brief carries no instruction block; paste the blocks yourself"},
}
IMPORT_HOSTS = frozenset({"claude-code", "gemini-cli", "cursor"})
NO_FILE_TARGETS = frozenset({"markdown"})


@dataclass(frozen=True, slots=True)
class Downgrade:
    record_id: str
    feature: str
    declared: bool
    note: str | None


@dataclass(frozen=True, slots=True)
class TargetVerdict:
    ok: bool
    target: str
    text: FidelityVerdict
    downgrades: tuple[Downgrade, ...]
    host_problems: tuple[str, ...]


def _outside_code(text: str) -> list[tuple[str, bool]]:
    """`text` cut into (piece, is_code) runs; code spans and fences are code."""
    pieces, last = [], 0
    for match in _CODE_RE.finditer(text):
        pieces += [(text[last:match.start()], False), (match.group(0), True)]
        last = match.end()
    return pieces + [(text[last:], False)]


def has_at_import(text: str) -> bool:
    """True when `text` holds an `@path` token a host would import."""
    return any(not code and _AT_IMPORT_RE.search(piece)
               for piece, code in _outside_code(text))


def _quote(match: re.Match[str]) -> str:
    token = match.group(0)
    core = token.rstrip(_TRAILING)
    return f"`{core}`{token[len(core):]}" if len(core) > 1 else token


def quote_at_imports(text: str) -> str:
    """`text` with every importable `@path` token put in a code span, which
    Claude Code, Gemini CLI and Cursor all read as text."""
    return "".join(piece if code else _AT_IMPORT_RE.sub(_quote, piece)
                   for piece, code in _outside_code(text))


def requested_features(record: Record, target_name: str) -> list[str]:
    """The features a block asks for that `target_name` handles differently.
    A target with no instruction file drops the whole block, which is the one
    difference that matters there."""
    if target_name in NO_FILE_TARGETS:
        return [OMITTED]
    features = []
    if record.data.get("applies_to"):
        features.append(GLOB)
    body = f"{record.data.get('title', '')}\n{record.data.get('body', '')}"
    if target_name in IMPORT_HOSTS and has_at_import(body):
        features.append(AT_IMPORT)
    return features


def brief_downgrades(text: str, target_name: str) -> list[Downgrade]:
    """An `@path` token that survives in a brief, which quoting should prevent."""
    if target_name not in IMPORT_HOSTS or not has_at_import(text):
        return []
    table = DECLARED_DOWNGRADES.get(target_name, {})
    return [Downgrade("canon-workspace-brief", AT_IMPORT, AT_IMPORT in table,
                      table.get(AT_IMPORT))]


def downgrades_for(records: list[Record], target_name: str,
                   declared: dict[str, dict[str, str]] | None = None) -> list[Downgrade]:
    table = (DECLARED_DOWNGRADES if declared is None else declared).get(target_name, {})
    return [Downgrade(r.id, f, f in table, table.get(f))
            for r in records for f in requested_features(r, target_name)]


def _host_problems(target_name: str, text: str) -> list[str]:
    if target_name == "cursor":
        problem = cursor_frontmatter_problem(text)
        return [problem] if problem else []
    return []


def target_roundtrip(records: list[Record], target_name: str, *,
                     declared: dict[str, dict[str, str]] | None = None) -> TargetVerdict:
    """Render `records` into a fresh host file for the target and return the
    verdict: the R0 round-trip, the host's own checks, and every downgrade
    classified against the target's declaration."""
    target = target_for(target_name)
    host = new_host_text(target.name)
    text = roundtrip_report(records, "workspace", file_text=host)
    problems: list[str] = []
    try:
        problems = _host_problems(target.name, splice_region(
            host, render_region(records, "workspace")))
    except RenderRefused as exc:
        problems = [f"render refused: {exc}"]
    downs = downgrades_for(records, target.name, declared)
    ok = text.ok and not problems and all(d.declared for d in downs)
    return TargetVerdict(ok, target.name, text, tuple(downs), tuple(problems))
