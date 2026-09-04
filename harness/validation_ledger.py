"""validation_ledger.py -- what was checked, at which scope, and what held.

A single check answers one question about one answer. The question an operator
actually asks is the accumulated one: across this task, this goal, this whole
session, what went out unverified.

So each check appends a line here, and the three scopes read the same file.
Post-task writes it. Post-goal and post-session roll it up. Nothing recomputes
a verdict at read time, which is the property that makes a session summary
citable rather than a second opinion.

    record(report, scope="task", subject="t-14")
    roll_up(read_ledger(scope="goal"))

An entry carries the rows and never the authoritative values, for the same
reason feedback does not: a summary that repeated the number an answer failed
against would be handing the next attempt its answer key.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .contract_terms import CRITICAL, HOLD, RELEASE, RELEASE_WITH_CAVEAT
from .verdict import Verdict

SCHEMA = "flywheel.validation-ledger/v1"

TASK = "task"
GOAL = "goal"
SESSION = "session"
SCOPES = (TASK, GOAL, SESSION)

# Worst first, so a roll-up can take a max without a special case.
_VERDICT_RANK = {Verdict.FAIL.value: 0, Verdict.UNVERIFIABLE.value: 1,
                 Verdict.PASS.value: 2}
_RELEASE_RANK = {HOLD: 0, RELEASE_WITH_CAVEAT: 1, RELEASE: 2}


def ledger_path() -> Path:
    """Where the ledger lives. `FLYWHEEL_HOME` moves it, as everywhere else."""
    home = os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel"))
    return Path(home) / "validation.jsonl"


def _rows(report: dict) -> list[dict]:
    return [{"field": r["field"], "verdict": r["verdict"], "code": r["code"],
             "criticality": r.get("criticality", ""), "source": r["source"],
             "method": r.get("method", "")}
            for r in report.get("fields", [])]


def record(report: dict, *, scope: str = TASK, subject: str = "",
           path: str | Path | None = None, at: str = "") -> dict:
    """Append one check to the ledger and return the entry that was written.

    `at` is accepted so a caller with its own clock can stamp the entry, which
    is what makes a replayed run produce the same file.
    """
    if scope not in SCOPES:
        raise LookupError(f"unknown scope {scope!r}; known: {list(SCOPES)}")
    entry = {
        "schema": SCHEMA,
        "at": at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": scope,
        "subject": subject,
        "verdict": report.get("verdict", Verdict.UNVERIFIABLE.value),
        "release": report.get("release", HOLD),
        "blocking": list(report.get("blocking", [])),
        "checked": report.get("checked", 0),
        "passed": report.get("passed", 0),
        "unresolved": list(report.get("unresolved", [])),
        "fields": _rows(report),
    }
    target = Path(path) if path else ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def read_ledger(path: str | Path | None = None, *, scope: str = "",
                subject: str = "") -> list[dict]:
    """Every entry, oldest first, optionally narrowed to a scope or subject.

    A line that does not parse is skipped rather than raising. The ledger is
    append-only from several writers, and a summary that refused to run because
    one line was torn would be the least useful possible response to that.
    """
    target = Path(path) if path else ledger_path()
    if not target.exists():
        return []
    entries: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if scope and entry.get("scope") != scope:
            continue
        if subject and entry.get("subject") != subject:
            continue
        entries.append(entry)
    return entries


def roll_up(entries: list[dict]) -> dict:
    """The worst verdict and the worst release across a run of entries.

    Worst rather than latest. A session whose last check passed is not a clean
    session if something went out on hold in the middle of it, and reporting
    the most recent entry is how that disappears.
    """
    if not entries:
        return {"schema": SCHEMA, "entries": 0, "verdict": "",
                "release": "", "blocking": [], "checked": 0, "held": 0,
                "critical_unresolved": []}
    verdict = min((e.get("verdict", "") for e in entries),
                  key=lambda v: _VERDICT_RANK.get(v, 1))
    release = min((e.get("release", "") for e in entries),
                  key=lambda r: _RELEASE_RANK.get(r, 0))
    blocking: list[str] = []
    critical: list[str] = []
    for entry in entries:
        for name in entry.get("blocking", []):
            if name not in blocking:
                blocking.append(name)
        for row in entry.get("fields", []):
            if (row.get("criticality") == CRITICAL
                    and row.get("verdict") != Verdict.PASS.value
                    and row["field"] not in critical):
                critical.append(row["field"])
    return {
        "schema": SCHEMA,
        "entries": len(entries),
        "verdict": verdict,
        "release": release,
        "blocking": blocking,
        "checked": sum(int(e.get("checked", 0)) for e in entries),
        "held": sum(1 for e in entries if e.get("release") == HOLD),
        "critical_unresolved": critical,
    }


def outstanding(entries: list[dict]) -> list[dict]:
    """The entries that held, newest last, for a summary to name directly."""
    return [{"at": e.get("at", ""), "scope": e.get("scope", ""),
             "subject": e.get("subject", ""), "blocking": e.get("blocking", [])}
            for e in entries if e.get("release") == HOLD]
