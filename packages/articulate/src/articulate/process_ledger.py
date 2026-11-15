#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.process_ledger -- the writer's process log: files and hash chain.

One append-only JSONL log per document, kept in `.articulate/process/` beside
it. Each entry carries the hash of the entry before it and a hash over its own
content. An edited entry, a removed middle entry or a reordered entry breaks
the chain, and a broken log is never extended. Removing entries from the end
leaves a shorter chain that still checks, and the log cannot detect that on its
own; only a head value kept somewhere the writer does not control would. The
chain design follows the draft log proposed in pull request #3 (GENESIS,
entry_hash, refusal to extend a broken log).

Input-method entries live in a separate private file outside the chain, so no
sequence number in the log shows that one exists.

`init` writes a `.gitignore` in the log folder. By default it holds `*`, so
`git add -A` cannot sweep a private log into a repository. With `track=True` it
lists only the private files (salts, the diff cache, snapshots and input
methods), so git sees the log and never those. Nothing records until the writer
runs a command. No network call, no subprocess.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

SCHEMA = "articulate/process/v1"
GENESIS = "sha256:" + "0" * 64
OPT_INS = ("words", "diff", "time", "snapshot")
PRIVATE_IGNORE = "*.salts.json\n*.last.txt\n*.objects/\n*.private.jsonl\n"


class LogBroken(ValueError):
    """The log fails its own chain check, so it is never extended."""


def _sha(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


def entry_hash(entry):
    body = {k: v for k, v in entry.items() if k != "hash"}
    return _sha(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def folder(doc):
    return os.path.join(os.path.dirname(os.path.abspath(doc)), ".articulate", "process")


def paths(doc):
    """The log and the private files beside it. Every path is per document."""
    base = os.path.join(folder(doc), os.path.basename(doc))
    return {"log": base + ".jsonl", "salts": base + ".salts.json",
            "last": base + ".last.txt", "objects": base + ".objects",
            "private": base + ".private.jsonl"}


def exists(doc):
    return os.path.isfile(paths(doc)["log"])


def _load_file(p):
    if not os.path.isfile(p):
        return [], []
    entries, problems = [], []
    with open(p, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError as err:
                problems.append(f"line {n}: not JSON ({err})")
                continue
            (entries if isinstance(e, dict) else problems).append(
                e if isinstance(e, dict) else f"line {n}: not an object")
    return entries, problems


def load(doc):
    """(entries, problems) for a document's log. A missing log is ([], [])."""
    return _load_file(paths(doc)["log"])


def load_private(doc):
    """The private input-method entries. They sit outside the chain."""
    return _load_file(paths(doc)["private"])[0]


def chain_problems(entries):
    problems, prev = [], GENESIS
    for i, e in enumerate(entries, 1):
        if e.get("schema") != SCHEMA:
            problems.append(f"entry {i}: unknown schema {e.get('schema')!r}")
        if e.get("seq") != i:
            problems.append(f"entry {i}: sequence number {e.get('seq')!r}, expected {i}")
        if e.get("prev") != prev:
            problems.append(f"entry {i}: does not link to the entry before it")
        if e.get("hash") != entry_hash(e):
            problems.append(f"entry {i}: content does not match its hash")
        prev = e.get("hash")
    return problems


def problems(doc):
    """(entries, every reason the log fails its check, unreadable lines included)."""
    entries, probs = load(doc)
    return entries, probs + chain_problems(entries)


def last_good_hash(entries):
    """The hash of the last entry before the chain first breaks, or GENESIS."""
    good, prev = GENESIS, GENESIS
    for i, e in enumerate(entries, 1):
        if (e.get("seq") != i or e.get("prev") != prev or e.get("hash") != entry_hash(e)):
            break
        good = prev = e["hash"]
    return good


def expanded(entries):
    """The entries, with the assistance a continuation carried forward from an
    earlier log placed where that continuation sits."""
    for e in entries:
        if e.get("kind") == "continuation":
            for i, a in enumerate(e.get("carried_assist") or [], 1):
                if isinstance(a, dict):
                    yield {**a, "kind": "assist", "seq": f"{e.get('seq')}.{i}",
                           "carried": True}
        yield e


def config(doc):
    """The opt-ins the log was started with (from its init entry)."""
    entries, _ = load(doc)
    for e in entries:
        if e.get("kind") in ("init", "continuation"):
            return set(e.get("opt_in", ()))
    return set()


def _now(now=None):
    return now or datetime.now(timezone.utc)


def append(doc, kind, fields, now=None):
    """Append one entry and return it. Raises LogBroken when the log fails its
    chain check, and FileNotFoundError when no log was started."""
    p = paths(doc)
    if not os.path.isfile(p["log"]):
        raise FileNotFoundError(f"no process log for {doc}; run `articulate process init`")
    entries, probs = problems(doc)
    if probs:
        raise LogBroken("the process log is broken, so nothing was appended: "
                        + "; ".join(probs[:3]) + ". Run `articulate process continue`.")
    return _write(p["log"], entries, kind, fields, now)


def append_private(doc, kind, fields, now=None):
    """Append an entry to the private file. It carries no sequence number and no
    chain link, and no export includes it unless the writer names it."""
    p = paths(doc)
    if not os.path.isfile(p["log"]):
        raise FileNotFoundError(f"no process log for {doc}; run `articulate process init`")
    entry = {"schema": SCHEMA, "kind": kind, "day": _now(now).date().isoformat(), **fields}
    with open(p["private"], "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry


def _write(log, entries, kind, fields, now):
    entry = {"schema": SCHEMA, "seq": len(entries) + 1, "kind": kind,
             "day": _now(now).date().isoformat(), **fields,
             "prev": entries[-1]["hash"] if entries else GENESIS}
    entry["hash"] = entry_hash(entry)
    with open(log, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry


def _write_ignore(directory, track):
    """`*` hides the whole folder from git. A tracked log still hides the
    private files. An existing `*` is never loosened."""
    ignore = os.path.join(directory, ".gitignore")
    if os.path.exists(ignore):
        with open(ignore, encoding="utf-8") as fh:
            have = fh.read()
        if have.strip() == "*" or PRIVATE_IGNORE in have:
            return
    with open(ignore, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PRIVATE_IGNORE if track else "*\n")


def init(doc, track=False, opt_in=(), now=None):
    """Start a log for a document. Refuses to overwrite an existing one."""
    bad = set(opt_in) - set(OPT_INS)
    if bad:
        raise ValueError(f"unknown opt-in field(s): {sorted(bad)}; choose from {OPT_INS}")
    p = paths(doc)
    if os.path.exists(p["log"]):
        raise FileExistsError(f"a process log already exists for {doc}")
    os.makedirs(folder(doc), exist_ok=True)
    _write_ignore(folder(doc), track)
    open(p["log"], "a", encoding="utf-8").close()
    return _write(p["log"], [], "init", {"opt_in": sorted(set(opt_in)),
                                        "document": os.path.basename(doc)}, now)


def restart(doc, reason, now=None):
    """Keep a broken log beside the document and start a new one whose first
    entry names the last good entry of the old one, so the gap reads as a break
    with a stated reason and never as a fresh start. The first entry also
    carries every assistance entry the old log still holds, so a statement built
    from the new log cannot leave one out. An intact log is never restarted."""
    p = paths(doc)
    if not os.path.isfile(p["log"]):
        raise FileNotFoundError(f"no process log for {doc}; run `articulate process init`")
    entries, probs = problems(doc)
    if not probs:
        raise ValueError("the process log is intact, so there is nothing to continue; "
                         "`continue` only follows a broken log")
    carried = [{k: v for k, v in a.items()
                if k not in ("schema", "prev", "hash", "carried", "kind")}
               for a in expanded(entries) if a.get("kind") == "assist"]
    anchor = last_good_hash(entries)
    opts = config(doc)
    n = 1
    while os.path.exists(f"{p['log']}.broken-{n}"):
        n += 1
    os.replace(p["log"], f"{p['log']}.broken-{n}")
    open(p["log"], "a", encoding="utf-8").close()
    return _write(p["log"], [], "continuation",
                  {"continues": anchor, "reason": reason, "opt_in": sorted(opts),
                   "carried_assist": carried}, now)
