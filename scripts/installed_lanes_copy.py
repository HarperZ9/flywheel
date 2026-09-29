"""Move the release copy onto a new installed-lanes evidence summary.

tests/test_release_drafts.py reads one committed summary (its EVIDENCE) and
requires the 1.1.0 notes and the lane page to name that summary's run and
commit and to carry its per-class counts. When a newer acceptance run replaces
the summary, this moves the summary name in the test and, in the two pages,
the run id, the short commit, the run date and the installer size. It edits
only the phrases below, each of which must appear exactly once, and it writes
nothing when one is missing. It also refuses when the new run's lanes differ
from the old summary's: the class tables and counts then need a person.
"""
from __future__ import annotations

import re
from pathlib import Path

TEST = Path("tests") / "test_release_drafts.py"
NOTES = Path("RELEASE-NOTES-1.1.0.md")
LANE_PAGE = Path("project-docs") / "lanes" / "LANES.md"
README = Path("README.md")
EVIDENCE_NAME = re.compile(r'"(installed-lanes-ci-\d+\.json)"')
BASELINE = re.compile(r"against\s+([\d,]+)\s+bytes\s+for\s+1\.0\.4")
SIZE = re.compile(r"about\s+(\d+\.\d)\s+MB\s+larger")


def current_evidence(root: Path) -> str:
    """The summary file name EVIDENCE in the drafts test points at."""
    names = EVIDENCE_NAME.findall((root / TEST).read_text(encoding="utf-8"))
    if len(names) != 1:
        raise SystemExit(f"{TEST}: expected one evidence file name, found {names}")
    return names[0]


def _facts(evidence: dict) -> dict:
    return {"run": str(evidence["run"]["run_id"]), "short": evidence["source_commit"][:8],
            "date": evidence["run"]["date"], "bytes": evidence["installer"]["bytes"]}


def _megabytes(installer: int, baseline: int) -> str:
    return f"{(installer - baseline) / 1e6:.1f}"


def _phrases(text: str, old: dict, new: dict) -> list[tuple[Path, list[str], list[str]]]:
    """(file, old tokens, new tokens) for every phrase the evidence moves."""
    base = BASELINE.search(text)
    if base is None:
        raise SystemExit(f"{NOTES}: no 'against N bytes for 1.0.4' baseline")
    baseline = int(base.group(1).replace(",", ""))
    size = SIZE.search(text)
    if size is None or size.group(1) != _megabytes(old["bytes"], baseline):
        raise SystemExit(f"{NOTES}: the 'about N MB larger' figure does not follow the "
                         f"old summary ({_megabytes(old['bytes'], baseline)} MB)")

    def both(*pattern: str) -> tuple[list[str], list[str]]:
        return ([p.format(**old) for p in pattern], [p.format(**new) for p in pattern])

    new_mb = _megabytes(new["bytes"], baseline)
    return [
        (TEST, *both('"installed-lanes-ci-{run}.json"')),
        (NOTES, *both("(CI", "run", "{run},", "commit", "{short})")),
        (NOTES, *both("{bytes:,}", "bytes", "in", "CI", "run", "{run}")),
        (NOTES, ["about", size.group(1), "MB", "larger,"], ["about", new_mb, "MB", "larger,"]),
        (LANE_PAGE, *both("CI", "run", "{run}", "on", "{date}", "against", "commit",
                          "{short},")),
        (LANE_PAGE, *both("`evidence/installed-lanes-ci-{run}.json`;")),
    ]


def _swap(match: re.Match, tokens: list[str]) -> str:
    """Replace a phrase's tokens and keep its own whitespace, line breaks included."""
    parts = re.split(r"(\s+)", match.group(0))
    parts[0::2] = tokens
    return "".join(parts)


def plan(root: Path, old_evidence: dict, new_evidence: dict, new_name: str) -> dict:
    """Every file's new text, or SystemExit with nothing written."""
    if old_evidence["lanes"] != new_evidence["lanes"]:
        changed = sorted(lane for lane in set(old_evidence["lanes"]) | set(new_evidence["lanes"])
                         if old_evidence["lanes"].get(lane) != new_evidence["lanes"].get(lane))
        raise SystemExit(f"the new run's lanes differ from the old summary's: {changed}; "
                         "rewrite the class tables and counts by hand")
    if new_name != f"installed-lanes-ci-{new_evidence['run']['run_id']}.json":
        raise SystemExit(f"{new_name} does not name run {new_evidence['run']['run_id']}")
    old, new = _facts(old_evidence), _facts(new_evidence)
    texts = {path: (root / path).read_bytes().decode("utf-8")
             for path in (TEST, NOTES, LANE_PAGE)}
    edits: dict[Path, str] = dict(texts)
    for path, before, after in _phrases(texts[NOTES], old, new):
        pattern = re.compile(r"\s+".join(re.escape(token) for token in before))
        hits = pattern.findall(edits[path])
        if len(hits) != 1:
            raise SystemExit(f"{path}: expected '{' '.join(before)}' once, found {len(hits)}")
        edits[path] = pattern.sub(lambda m: _swap(m, after), edits[path])
    lanes = new_evidence["lanes"]
    at_class = sum(1 for row in lanes.values() if row["verdict"] == "AT_CLASS")
    sentence = f"{at_class} of {len(lanes)} lanes reach the class the check expects"
    for path in (README, NOTES):
        body = edits.get(path) or (root / path).read_text(encoding="utf-8")
        if sentence not in " ".join(body.split()):
            raise SystemExit(f"{path}: the lane sentence does not say '{sentence}'")
    return {path: text for path, text in edits.items() if text != texts[path]}


def apply(root: Path, edits: dict) -> list[str]:
    for path, text in edits.items():
        (root / path).write_bytes(text.encode("utf-8"))
    return [f"updated {path.as_posix()}" for path in sorted(edits)] or ["copy already current"]
