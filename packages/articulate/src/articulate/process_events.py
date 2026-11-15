#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.process_events -- the entries a writer records.

  draft         a salted commitment to the current text, its sequence and day.
                Word count, lines added and removed, the time to the minute and
                a snapshot are recorded only when the log opted in to them.
  note, source  a commitment, or a label or citation the writer types
  assist        a tool the writer declares, with the task verb (generated,
                drafted, edited, translated), where, and the model as declared
  input_method  how the writer put words down (dictation, handwriting then
                typed, a screen reader, switch access, drafting in another
                language). Kept in a private file outside the chain: no export
                or statement includes it unless the writer names it.
  review        a role (tutor, supervisor, peer, editor), what was reviewed,
                the outcome and whether the role holds editorial responsibility
  anchor        a git commit id read from git's files, or the hash of an
                outside timestamp token as the writer supplies it. Nothing here
                checks a token. A commit id shows only that the entry was
                written after that commit existed. No subprocess, no network.

No entry holds a score of any kind; no function here reads the checker.
Standard library only.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re

from . import process_commit as pc
from . import process_ledger as pl
from .provenance import ASSIST_VERBS, INPUT_METHODS, REVIEW_ROLES, TRANSLATION_CHOICES

WORD = re.compile(r"\b\w+\b")


def _diff(before, after):
    sm = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines(), autojunk=False)
    added = removed = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            removed += i2 - i1
            added += j2 - j1
    return {"lines_added": added, "lines_removed": removed}


def _opt_fields(doc, text, opts, now):
    """The opt-in fields of a draft. The diff cache moves only after the entry
    lands (_save_last), so a refused append never moves the baseline."""
    p = pl.paths(doc)
    out = {}
    if "words" in opts:
        out["words"] = len(WORD.findall(text))
    if "diff" in opts and os.path.isfile(p["last"]):
        with open(p["last"], encoding="utf-8", newline="") as fh:
            out.update(_diff(fh.read(), text))
    if "time" in opts:
        out["time"] = pl._now(now).strftime("%H:%M")
    return out


def _save_last(doc, text):
    # A private cache of the last draft only, overwritten each time.
    with open(pl.paths(doc)["last"], "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _unchanged(doc, text):
    """True when the text equals the last draft this log holds. A draft in an
    earlier, broken log never counts."""
    entries, _ = pl.load(doc)
    drafts = [e for e in entries if e.get("kind") == "draft"]
    if not drafts:
        return False
    kept = pc.load_salts(pl.paths(doc)["salts"]).get(drafts[-1].get("commitment"), {})
    return kept.get("text_sha256") == hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_path(doc, commitment):
    return os.path.join(pl.paths(doc)["objects"], str(commitment).split(":", 1)[-1] + ".txt")


def record_draft(doc, text, now=None):
    """Append a draft entry, or return None when the text is unchanged since the
    last recorded draft."""
    if not pl.exists(doc):
        raise FileNotFoundError(f"no process log for {doc}; run `articulate process init`")
    if _unchanged(doc, text):
        return None
    p = pl.paths(doc)
    opts = pl.config(doc)
    salt = pc.new_salt()
    commitment = pc.commit(salt, text)
    fields = {"commitment": commitment, **_opt_fields(doc, text, opts, now)}
    entry = pl.append(doc, "draft", fields, now)
    pc.save_salt(p["salts"], commitment, salt, text, "draft")
    if "diff" in opts:
        _save_last(doc, text)
    if "snapshot" in opts:
        os.makedirs(p["objects"], exist_ok=True)
        with open(snapshot_path(doc, commitment), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return entry


def record_note(doc, text=None, label=None, shareable=False, kind="note", now=None):
    if (text is None) == (label is None):
        raise ValueError("give either the note text (kept as a commitment) or a label")
    fields = {"shareable": bool(shareable)}
    if text is not None:
        salt = pc.new_salt()
        fields["commitment"] = pc.commit(salt, text)
        entry = pl.append(doc, kind, fields, now)
        pc.save_salt(pl.paths(doc)["salts"], fields["commitment"], salt, text, kind)
        return entry
    fields["label"] = label
    return pl.append(doc, kind, fields, now)


def record_source(doc, citation, shareable=False, now=None):
    return pl.append(doc, "source", {"citation": citation, "shareable": bool(shareable)}, now)


def record_assist(doc, tool, verb, sections, version=None, model=None, receipt=None,
                  guard=None, source_type=None, languages=None, now=None):
    if verb not in ASSIST_VERBS:
        raise ValueError(f"assist verb must be one of {ASSIST_VERBS}; how the writer put "
                         f"words down (dictation and the like) is an input_method entry")
    fields = {"tool": tool, "verb": verb, "sections": list(sections or ["whole document"])}
    for k, v in (("version", version), ("model", model), ("receipt", receipt),
                 ("guard", guard)):
        if v is not None:
            fields[k] = v
    if verb == "translated":
        if source_type not in TRANSLATION_CHOICES or not languages or len(languages) != 2:
            raise ValueError("a translation needs source and target language codes and "
                             f"the writer's choice of source type: {TRANSLATION_CHOICES}")
        fields.update(source_type=source_type, source_language=languages[0],
                      target_language=languages[1])
    return pl.append(doc, "assist", fields, now)


def record_input_method(doc, method, sections=None, now=None):
    if method not in INPUT_METHODS:
        raise ValueError(f"input method must be one of {INPUT_METHODS}")
    return pl.append_private(doc, "input_method",
                             {"method": method,
                              "sections": list(sections or ["whole document"])}, now)


def record_review(doc, role, reviewed, outcome, editorial_responsibility=False, name=None,
                  now=None):
    if role not in REVIEW_ROLES:
        raise ValueError(f"review role must be one of {REVIEW_ROLES}")
    fields = {"role": role, "reviewed": reviewed, "outcome": outcome,
              "editorial_responsibility": bool(editorial_responsibility)}
    if name:
        fields["name"] = name
    return pl.append(doc, "review", fields, now)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def git_dirs(start):
    """(git dir, common dir) for the repository that holds `start`, or None. A
    worktree or submodule has a `.git` file naming its git dir, and a linked
    worktree's git dir names the shared common dir in `commondir`."""
    d = os.path.abspath(start)
    while True:
        git = os.path.join(d, ".git")
        if os.path.isdir(git):
            return git, git
        if os.path.isfile(git):
            line = _read(git) or ""
            if not line.startswith("gitdir:"):
                return None
            gitdir = os.path.normpath(os.path.join(d, line[len("gitdir:"):].strip()))
            common = _read(os.path.join(gitdir, "commondir"))
            common = os.path.normpath(os.path.join(gitdir, common)) if common else gitdir
            return gitdir, common
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def git_head(start):
    """The commit id HEAD points at, read from git's files directly, or None."""
    dirs = git_dirs(start)
    return _resolve_ref(*dirs) if dirs else None


def _resolve_ref(gitdir, common=None):
    common = common or gitdir
    head = _read(os.path.join(gitdir, "HEAD"))
    if not head:
        return None
    if not head.startswith("ref: "):
        return head
    ref = head[5:].strip()
    for base in (gitdir, common):
        value = _read(os.path.join(base, *ref.split("/")))
        if value:
            return value
    packed = os.path.join(common, "packed-refs")
    if os.path.isfile(packed):
        with open(packed, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    return None


def record_anchor(doc, commit=None, token_sha256=None, now=None):
    if token_sha256:
        return pl.append(doc, "anchor", {"token_sha256": token_sha256}, now)
    commit = commit or git_head(os.path.dirname(os.path.abspath(doc)))
    if not commit:
        raise ValueError("no git commit found; pass a commit id or a token hash")
    return pl.append(doc, "anchor", {"git_commit": commit}, now)


def record_editor_pass(doc, pass_name, where="whole document", *, backend=None, model=None):
    """When the writer keeps a log for this document, a fix or polish pass that
    produced a rewrite appends its own assistance entry, so the statement built
    from the log cannot leave it out. Without a log, nothing is recorded."""
    if not pl.exists(doc):
        return None
    from . import __version__
    verb = "deterministic-fix" if backend == "none" else "edited"
    return record_assist(doc, "articulate", verb, [where], version=__version__,
                         model=model if backend != "none" else None,
                         receipt=f"articulate {pass_name} pass (backend: {backend or 'unknown'})")


def log_pass(path, name, backend=None, model=None):
    """Record an accepted editor pass in the document's process log, if it has one."""
    from .process_ledger import LogBroken
    try:
        if record_editor_pass(path, name, backend=backend, model=model):
            print(f"[{name}] recorded an assistance entry in this document's process log")
    except LogBroken as e:
        print(f"[{name}] the process log is broken, so no entry was added: {e}")
