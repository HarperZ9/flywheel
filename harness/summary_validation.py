"""summary_validation.py -- the output-validation ledger as summary evidence.

The ledger answers an accumulated question: across this task, this goal, this
whole session, what went out unverified. The summary asks that same question
third, as "what is left to finish this work", so it reads the ledger instead of
asking again.

The file is read off disk by its schema string rather than through the module
that writes it. A summary that imported the producer to describe the producer
would agree with it by construction, and the file is the artifact a later
reader has anyway. Values never come across: an entry carries which fields were
short and what blocked them, never the number an answer failed against.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "flywheel.validation-ledger/v1"

HOLD = "HOLD"
CAVEAT = "RELEASE_WITH_CAVEAT"
RELEASE = "RELEASE"

# Worst first, so a caller can sort without a special case.
_RANK = {HOLD: 0, CAVEAT: 1, RELEASE: 2}
_LIMIT = 10
_KEEP = ("at", "scope", "subject", "verdict", "release", "blocking",
         "unresolved", "checked", "passed")


def read_validation(path: str | Path, *, since: str = "") -> list[dict]:
    """Ledger entries, metadata only, oldest first.

    A torn last line is skipped rather than raising. A ledger written by a
    process that was killed mid-write still answers the question about every
    entry before it, and refusing the whole file would lose them.
    """
    target = Path(path)
    if not target.is_file():
        return []
    rows: list[dict] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("schema") != SCHEMA:
            continue
        if since and str(entry.get("at", "")) < since:
            continue
        rows.append({key: entry.get(key, "") for key in _KEEP})
    return rows


def short_of_release(rows: list[dict]) -> list[dict]:
    """The entries still short of a clean release, worst first.

    This is the list an operator has to work through, and it is deliberately
    not a count. A run whose last check passed is not a clean run if something
    went out held in the middle of it.
    """
    short = [row for row in rows if row.get("release") != RELEASE]
    return sorted(short, key=lambda row: (_RANK.get(row.get("release"), 0),
                                          str(row.get("at", ""))))


def _names(row: dict) -> str:
    named = list(row.get("blocking") or []) or list(row.get("unresolved") or [])
    return ", ".join(str(item) for item in named[:4]) or "no field named"


def validation_answers(rows: list[dict]) -> dict[str, list[str]]:
    """What the ledger contributes to the four answers.

    A held entry is a wrong answer and a caveat entry is an unchecked one, so
    they read differently. Both go under what is left, because neither is
    finished work.
    """
    if not rows:
        return {"did": [], "remaining": [], "decisions": []}
    short = short_of_release(rows)
    held = [row for row in short if row.get("release") == HOLD]
    did = [f"{len(rows)} output check(s) recorded: {len(rows) - len(short)} released, "
           f"{len(short) - len(held)} with a caveat, {len(held)} held"]
    remaining, decisions = [], []
    for row in short[:_LIMIT]:
        subject = str(row.get("subject") or "no subject")
        state = "held" if row.get("release") == HOLD else "released with a caveat"
        remaining.append(f"output {state} for {subject}: {_names(row)}")
    if len(short) > _LIMIT:
        remaining.append(f"{len(short) - _LIMIT} further entry(s) short of a clean release")
    if held:
        decisions.append("go to the source that decides the held field(s) and check "
                         "again, or say the answer ships unverified")
    if len(short) > len(held):
        decisions.append("send the caveated answer(s) saying what is unconfirmed, "
                         "or hold them until something can confirm it")
    return {"did": did, "remaining": remaining, "decisions": decisions}
