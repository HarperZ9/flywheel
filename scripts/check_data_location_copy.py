#!/usr/bin/env python3
"""check_data_location_copy.py -- copy says exactly where data goes (I11).

Flywheel keeps its records and the owner's provider keys on the owner's
machine. The content of each request goes to the model provider the owner
picks. A sentence that says "your data stays on your machine" without that
qualifier promises more than the product does, and so does calling a
deletion "GDPR-style" when it does not reach every derived form.

The check reads the product surfaces (root pages, docs, release notes, the
site, harness docstrings and runtime strings, desktop strings, shipped model
pages and plugin readmes) with whitespace normalized, so a phrase wrapped
across a line break is found. A broader rule (`unqualified_local`) catches
any "stays on / never leaves / nothing leaves your machine" wording and
passes it only when a sentence naming the model or hosted provider sits within
QUALIFIER_WINDOW lines, or when the sentence itself is about a local model.
Three escapes exist for every rule:

  * a sentence listed in ALLOWED for one file, each with its reason. These are
    local-model pages, where the statement is true because nothing is sent;
  * a sentence listed in PROVEN for one file, with the tests that hold the tool
    to it and the limit a reader needs. The check fails when a named test file
    or test function is gone. It does not run the tests: the package's own job
    in `.github/workflows/packages.yml` does;
  * a line starting `Correction, <YYYY-MM-DD>:` within ten lines after the
    phrase, whose paragraph names the provider, so a shipped release note
    keeps its text and carries the fix.

What this cannot see: a phrase split across string concatenations in code, a
paraphrase the patterns do not name, and pages outside the surface list.

Exit 0 clean, 1 with violations listed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
SURFACE_GLOBS = (
    "*.md", "docs/**/*.md", "site/**/*.html", "site/**/*.md", "harness/**/*.py",
    "desktop/lib/**/*.dart", "project-docs/releases/**/*.md", "plugins/**/*.md",
    "packages/**/*.md", "desktop/*.md", "desktop/docs/**/*.md",
)
PHRASES = (
    ("data_location", re.compile(
        r"(?i)\bdata stays? on your (?:own )?(?:machine|computer|device|disk)\b")),
    ("data_location", re.compile(
        r"(?i)\b(?:prompts|data|content)(?: and your code)? never leaves? your "
        r"(?:own )?(?:machine|computer|device|disk)\b")),
    ("data_location", re.compile(
        r"(?i)\byour data (?:stays|remains) (?:local|private|on[- ]device)\b")),
    ("gdpr", re.compile(r"(?i)\bGDPR[- ](?:style|erasure)\b")),
    ("gdpr", re.compile(r"(?i)\btrue (?:erase|erasure|forget|deletion)\b")),
)
LOCAL_CLAIM = re.compile(
    r"(?i)\b(?:stays?|remains?|kept|stored only) (?:only )?on your (?:own )?"
    r"(?:machine|computer|device|disk)\b|\b(?:nothing|never) leaves? your (?:own )?"
    r"(?:machine|computer|device|disk)\b|\bnever leaves? your (?:own )?"
    r"(?:machine|computer|device|disk)\b")
QUALIFIER = re.compile(r"(?i)\b(?:model|hosted) provider|provider you "
                       r"(?:pick|route)")
LOCAL_MODEL = re.compile(r"(?i)\blocal model")
QUALIFIER_WINDOW = 8
CORRECTION = re.compile(r"^\s*(?:[*_>]+\s*)?Correction, \d{4}-\d{2}-\d{2}:")
CORRECTION_WINDOW = 10
_LOCAL = ("the local model runs on the owner's machine and sends nothing, so the "
          "sentence is true there")
# Open claim gap GAP-ARTICULATE-VOICE-1 (recorded 2026-11-15). This entry excuses one
# sentence that the tool does not meet yet; it is not a statement that the sentence is
# true. What the tool says about it today: packages/articulate/docs/series-and-voice.md,
# "What leaves your computer", and the module docstring of
# packages/articulate/src/articulate/voice_apply.py. Remove the entry when the consent
# step named below ships.
_ARTICULATE = ("OPEN GAP GAP-ARTICULATE-VOICE-1. Articulate's README, imported as written. The "
               "profile file and the samples stay in the local voice store. `voice apply` "
               "(MCP `voice_apply_plan`) hands the host conversation every stored field of the "
               "profile as sentences, including up to 20 of the author's recurring words, and "
               "`voice compare` returns the author's measured ranges; a hosted model receives "
               "both. Build task: a consent step, off by default, that states what is sent "
               "before any profile-derived text enters a host conversation")
ALLOWED = {
    ("packages/articulate/README.md",
     "A voice profile holds aggregate statistics and stays on your computer until "
     "`articulate voice delete --all`."): _ARTICULATE,
    ("site/index.html", "Your prompts and your code never leave your disk."): _LOCAL,
    ("project-docs/releases/14B/shipped-page/README.md",
     "Your prompts and your code never leave your disk."): _LOCAL,
    ("project-docs/releases/32B/shipped-page/README.md",
     "Your prompts and your code never leave your disk."): _LOCAL,
    ("project-docs/releases/14B/WALKTHROUGH.md",
     "Your prompts and your code never leave your machine."): _LOCAL,
}


@dataclass(frozen=True)
class Proof:
    tests: tuple[str, ...]
    limit: str


_T = "packages/mneme/tests/test_claim_"
_FORGET = Proof(
    (_T + "forget_forensic.py::test_after_forget_no_file_mneme_created_holds_the_marker",
     _T + "forget_forensic.py::test_control_a_row_delete_without_scrub_is_caught",
     _T + "forget_forensic.py::test_control_an_export_left_on_disk_is_caught",
     _T + "tombstone.py::test_the_audit_trail_proves_the_forget_and_holds_no_content",
     _T + "overwrite.py::test_the_rollback_journal_of_an_erase_is_overwritten_before_it_goes"),
    "Covers every file Mneme wrote, from schema 6. A write-ahead log is truncated without "
    "an overwrite, old blocks on a solid-state drive can survive, audit rows from before "
    "schema 6 are reported as residue, and copies Mneme did not write (backups, text "
    "already sent to a model provider) are named in the receipt and not reached")
# Mneme sentences its code is now held to by its own tests (mneme PR 42, schema 6).
PROVEN = {
    ("packages/mneme/README.md", "The store stays on your machine."): Proof(
        (_T + "egress.py::test_every_public_library_method_runs_with_the_network_denied",
         _T + "egress.py::test_every_cli_command_runs_with_the_network_denied",
         _T + "egress.py::test_every_mcp_tool_runs_with_the_network_denied",
         _T + "egress.py::test_the_default_extractor_and_embedder_are_local"),
        "The tests deny sockets, name lookups, HTTP requests and started processes at "
        "Python's audit hook. A store the owner puts on a network share is not detected, "
        "and what an MCP client reads goes to that client's provider, as the next README "
        "sentence says"),
    ("packages/mneme/CHANGELOG.md",
     "`forget` becomes a true forget, the MCP forget tool takes two steps, replay "
     "snapshots move to a per-user state directory, and schema 5 blinds the update "
     "and supersede history in the audit log."): _FORGET,
    ("packages/mneme/CHANGELOG.md",
     "These changes close the gaps between what `forget` does and what a careful reader "
     "takes \"a true forget\" to mean."): _FORGET,
    ("packages/mneme/CHANGELOG.md",
     "`forget` (GDPR erasure) still removes; `supersede` (a fact changed) keeps."): Proof(
        (_T + "subject_erasure.py::test_forget_subject_removes_every_record_of_that_user_and_no_other",
         _T + "subject_erasure.py::test_the_receipt_verifies_and_an_edited_receipt_does_not",
         _T + "subject_erasure.py::test_the_audit_log_proves_the_subject_erasure_and_cannot_drop_it"),
        "The tests cover erasing one user's records with a receipt that verifies. The "
        "`forget` of that old release did less, as the correction under the sentence says. "
        "A controller's duties (grounds, notifying recipients, copies outside the store) "
        "are outside any tool, and Mneme's README says it does not make its operator "
        "compliant"),
}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    sentence: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.sentence}"


def _normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to one space; map each output index to its line."""
    out, lines, line, gap = [], [], 1, False
    for ch in text:
        if ch.isspace():
            if not gap and out:
                out.append(" ")
                lines.append(line)
            gap = True
            if ch == "\n":
                line += 1
            continue
        gap = False
        out.append(ch)
        lines.append(line)
    return "".join(out), lines


def _sentence(flat: str, start: int, end: int) -> str:
    begin = max(flat.rfind(mark, 0, start) for mark in (". ", "! ", "? ", ">", ") "))
    begin = max(begin, start - 240)
    stop = min((i for i in (flat.find(mark, end) for mark in (".", "!", "?", "<"))
                if i >= 0), default=len(flat))
    stop = stop + 1 if stop < len(flat) and flat[stop] in ".!?" else stop
    return flat[begin + 1:stop].strip()


def _paragraph(raw_lines: list[str], index: int) -> str:
    out = []
    while index < len(raw_lines) and raw_lines[index].strip():
        out.append(raw_lines[index])
        index += 1
    return " ".join(out)


def _corrected(raw_lines: list[str], line: int) -> bool:
    """A dated correction within the window whose paragraph names the provider."""
    for offset, candidate in enumerate(raw_lines[line:line + CORRECTION_WINDOW]):
        if CORRECTION.match(candidate) and QUALIFIER.search(
                _paragraph(raw_lines, line + offset)):
            return True
    return False


def _qualified(raw_lines: list[str], line: int, sentence: str) -> bool:
    if LOCAL_MODEL.search(sentence):
        return True
    low, high = max(0, line - 1 - QUALIFIER_WINDOW), line + QUALIFIER_WINDOW
    return QUALIFIER.search(" ".join(raw_lines[low:high])) is not None


def _inside_correction(raw_lines: list[str], line: int) -> bool:
    """The phrase is quoted by a correction paragraph itself."""
    index = line - 1
    while 0 <= index < len(raw_lines) and raw_lines[index].strip():
        if CORRECTION.match(raw_lines[index]):
            return True
        index -= 1
    return False


def violations_in(text: str, name: str) -> list[Violation]:
    flat, lines = _normalize(text)
    raw_lines = text.splitlines()
    found = []
    for rule, pattern in PHRASES:
        for match in pattern.finditer(flat):
            sentence = _sentence(flat, match.start(), match.end())
            if (name, sentence) in ALLOWED or (name, sentence) in PROVEN:
                continue
            end_line = lines[match.end() - 1]
            if (_corrected(raw_lines, end_line)
                    or _inside_correction(raw_lines, lines[match.start()])):
                continue
            found.append(Violation(name, lines[match.start()], rule, sentence))
    strict = {(v.line, v.sentence) for v in found}
    for match in LOCAL_CLAIM.finditer(flat):
        sentence = _sentence(flat, match.start(), match.end())
        line = lines[match.start()]
        if ((line, sentence) in strict or (name, sentence) in ALLOWED
                or (name, sentence) in PROVEN
                or _qualified(raw_lines, line, sentence)
                or _corrected(raw_lines, lines[match.end() - 1])
                or _inside_correction(raw_lines, line)):
            continue
        found.append(Violation(name, line, "unqualified_local", sentence))
    return sorted(set(found), key=lambda v: (v.line, v.rule))


def surfaces(root: Path) -> list[Path]:
    seen: dict[str, Path] = {}
    for pattern in SURFACE_GLOBS:
        for path in root.glob(pattern):
            if path.is_file() and "node_modules" not in path.parts:
                seen[path.relative_to(root).as_posix()] = path
    return [seen[key] for key in sorted(seen)]


def missing_proofs(root: Path = ROOT) -> list[Violation]:
    """A PROVEN sentence whose page is here needs every test it names to exist."""
    found = []
    for (path, sentence), proof in PROVEN.items():
        if not (root / path).is_file():
            continue
        for test_id in proof.tests:
            file, _, name = test_id.partition("::")
            target = root / file
            source = target.read_text(encoding="utf-8") if target.is_file() else ""
            if not name or not re.search(rf"(?m)^def {re.escape(name)}\(", source):
                found.append(Violation(path, 0, "proof_missing",
                                       f"{sentence} names {test_id}, which is not there"))
    return found


def scan(root: Path = ROOT) -> list[Violation]:
    found = missing_proofs(root)
    for path in surfaces(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        found.extend(violations_in(text, path.relative_to(root).as_posix()))
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    found = scan(args.root)
    for violation in found:
        print(violation.render())
    if found:
        print(f"{len(found)} data-location finding(s). Name where content goes, add a "
              "dated Correction line after a shipped sentence, or restore a named test.")
        return 1
    print(f"data-location copy check: clean ({len(surfaces(args.root))} surfaces)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
