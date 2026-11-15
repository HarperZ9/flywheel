"""articulate.code.report -- one report for a test diff, with its limits attached.

`analyze(changes)` takes the changed files of one change set and returns a JSON-able
report: findings, counts, two digests and a `does_not_prove` list that is never
empty. The subject digest covers only the inputs (paths and content hashes), so two
runs on the same change can be compared; the claim digest covers the findings.
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass

from .context import build_world, is_test_path
from .testdiff import compare_file

SCHEMA = "articulate.code.test-diff/v2"
DOES_NOT_PROVE = (
    "A clean report does not show the tests are good. It shows this change did not "
    "weaken them in the forms this analyzer reads.",
    "Static only: no test ran. A check moved more than one helper call deep, into a "
    "fixture, or into another file reads as deleted.",
    "A declared finding carries a reason written by the change's author. The reason "
    "is shown, not verified.",
    "Splitting one test into several, each with fewer checks, is not detected.",
    "An advisory row is a weakening the change may explain (it also edits source, "
    "or a deleted test has a replacement). It is not counted as a finding and not "
    "cleared either.",
    "Python only. Other languages are listed as unverifiable, never as clean.",
)


@dataclass
class FileChange:
    path: str
    before: "str | None"
    after: "str | None"


def _sha(text) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _declared_ids(declared) -> set:
    out = set()
    for item in declared or ():
        test_id = item.get("test_id") if isinstance(item, dict) else item
        if isinstance(test_id, str) and test_id:
            out.add(test_id)
    return out


def _is_declared(finding, ids) -> bool:
    full = f"{finding.path}::{finding.test}"
    return full in ids or finding.test in ids or full.replace("\\", "/") in ids


def analyze(changes, declared=()) -> dict:
    """Report for a list of FileChange (or dicts with path/before/after)."""
    changes = [c if isinstance(c, FileChange) else FileChange(c["path"], c.get("before"),
                                                              c.get("after"))
               for c in changes]
    world = build_world(changes)
    ids = _declared_ids(declared)
    files, findings = [], []
    for change in sorted(changes, key=lambda c: c.path):
        if not is_test_path(change.path):
            if change.path.endswith(".py"):
                continue
            if _looks_like_test(change.path):
                files.append({"path": change.path, "status": "unverifiable",
                              "reason": "not a Python test file"})
            continue
        result = compare_file(change.path, change.before, change.after, world=world)
        if result is None:
            files.append({"path": change.path, "status": "unverifiable",
                          "reason": "does not parse as Python"})
            continue
        for finding in result:
            if finding.tier == "finding" and _is_declared(finding, ids):
                finding.tier = "declared"
        files.append({"path": change.path, "status": "analyzed", "findings": len(result)})
        findings += result
    rows = [asdict(f) for f in findings]
    open_rows = [r for r in rows if r["tier"] == "finding"]
    unverifiable = any(f["status"] == "unverifiable" for f in files)
    status = "findings" if open_rows else "unverifiable" if unverifiable else "clean"
    subject = [[c.path, _sha(c.before) if c.before is not None else None,
                _sha(c.after) if c.after is not None else None]
               for c in sorted(changes, key=lambda c: c.path)]
    return {
        "schema": SCHEMA,
        "mode": "report-only",
        "status": status,
        "subject_sha256": _sha(_canonical(subject)),
        "claim_sha256": _sha(_canonical(rows)),
        "files": files,
        "findings": rows,
        "counts": {
            "finding": len(open_rows),
            "declared": sum(1 for r in rows if r["tier"] == "declared"),
            "advisory": sum(1 for r in rows if r["tier"] == "advisory"),
            "by_rule": dict(sorted(Counter(r["rule"] for r in open_rows).items())),
        },
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def _looks_like_test(path) -> bool:
    lower = path.replace("\\", "/").lower()
    name = lower.rsplit("/", 1)[-1]
    return ("/tests/" in "/" + lower or name.startswith("test_") or ".test." in name
            or ".spec." in name or name.endswith("_test.go") or name.endswith("_test.rs"))


def render_text(report) -> str:
    lines = [f"articulate code test-diff: {report['status']} "
             f"({report['counts']['finding']} findings, {report['counts']['declared']} declared, "
             f"{report['counts'].get('advisory', 0)} advisory)"]
    for row in report["findings"]:
        mark = "" if row["tier"] == "finding" else f" [{row['tier']}]"
        lines.append(f"{row['path']}:{row['line']}: {row['check']} {row['rule']}{mark}: "
                     f"{row['test']}: {row['detail']}")
    for item in report["files"]:
        if item["status"] == "unverifiable":
            lines.append(f"{item['path']}: unverifiable: {item['reason']}")
    lines.append("Report-only. Does not prove: " + " ".join(report["does_not_prove"]))
    return "\n".join(lines)
