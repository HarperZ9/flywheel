#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.process_export -- the Articulate process summary, and verify.

`<document>.process-summary.json`, schema articulate/process-summary/v1. The
default export holds the document hashes, the entry sequence with days, each
draft's commitment, the declared assistance, review roles and outcomes, and the
disclosure statement. Every other field (word counts, diff sizes, times,
shareable labels and citations, input methods, reviewer names) is added only
when the writer names it. `reveal` attaches the text and salt of chosen drafts
so a reader can check each against its commitment.

No exported value is computed from a withheld field. An entry hash covers every
field, so a reader holding one could test guesses at a withheld word count, time
or citation; the export leaves entry hashes out.

The actions list follows the C2PA data model so a signed manifest could be built
from it later: the first action is c2pa.created or c2pa.opened, each action
carries its own IPTC digital source type, sections are textual changes, and a
translation carries BCP 47 source and target languages. People stay out of the
actions. This file is unsigned. It is not a Content Credential and not an EU AI
Act Article 50 marking.

`verify` reports intact, broken or missing, with reasons. It reports no gaps, no
intervals between entries and no clock notes. Standard library only.
"""
from __future__ import annotations

import hashlib
import os

from . import disclose
from . import process_commit as pc
from . import process_events as ev
from . import process_ledger as pl
from .provenance import SOURCE_TYPE, iptc_uri

SCHEMA = "articulate/process-summary/v2"
SCHEMA_V1 = "articulate/process-summary/v1"
LIMITS = (
    "This summary shows that texts with these commitments were logged in this order "
    "and which tools the writer declared. An anchor entry holds a git commit id or a "
    "token hash as the writer recorded it; Articulate checks neither, and a commit id "
    "shows only that the entry was written after that commit existed. The summary "
    "does not show who composed the words, when anything happened, or that the record "
    "is complete. A writer can build a log after the fact. An absent record shows "
    "nothing about a writer.")
# One line every process output prints: an intact verify, an export and a
# disclosure statement. A missing log is no record, with an exit code of its own
# (NO_RECORD_EXIT), kept apart from a broken log (exit 1).
RECORD_LIMITS = ("A process record shows what its entries hold. Use other evidence to "
                 "decide who wrote a text.")
NO_RECORD = "no record for this file. Use other evidence to decide who wrote a text"
NO_RECORD_EXIT = 3
# The summary's scope line speaks about the record itself.
PROCESS_SCOPE = ("Lists what the writer logged and declared in the process record, in the "
                 "order of the record.")
_BASE = ("seq", "kind", "day")
_DEFAULT = {"init": (), "draft": ("commitment",), "note": (), "source": (),
            "assist": ("tool", "version", "verb", "sections", "model", "receipt", "guard",
                       "source_type", "source_language", "target_language"),
            "review": ("role", "outcome", "editorial_responsibility"),
            "continuation": ("continues", "reason", "carried_assist"),
            "anchor": ("git_commit", "token_sha256")}
OPTIONAL = {"words": ("draft", ("words",)), "diff": ("draft", ("lines_added", "lines_removed")),
            "time": ("draft", ("time",)), "review_names": ("review", ("name", "reviewed")),
            "labels": ("note", ("label",)), "citations": ("source", ("citation",))}


def _export_entry(e, include):
    kind = e.get("kind")
    keep = set(_BASE) | set(_DEFAULT.get(kind, ()))
    for name, (k, fields) in OPTIONAL.items():
        if name in include and k == kind:
            if kind in ("note", "source") and not e.get("shareable"):
                continue
            keep |= set(fields)
    return {k: v for k, v in e.items() if k in keep}


def _action(e, first):
    if e["kind"] == "draft":
        code = SOURCE_TYPE["written" if first else "human-edit"]
        return {"action": "c2pa.created" if first else "c2pa.edited",
                "digitalSourceType": iptc_uri(code), "entry": e["seq"]}
    verb = e["verb"]
    code = e["source_type"] if verb == "translated" else SOURCE_TYPE[verb]
    act = {"action": {"translated": "c2pa.translated"}.get(verb, "c2pa.edited"),
           "digitalSourceType": iptc_uri(code), "entry": e["seq"],
           "softwareAgent": {"name": e["tool"], **({"version": e["version"]}
                                                   if e.get("version") else {})},
           "changes": [{"type": "textual", "description": s} for s in e["sections"]]}
    if verb == "translated":
        act.update(sourceLanguage=e["source_language"], targetLanguage=e["target_language"])
    if first and verb in ("generated", "drafted"):
        act["action"] = "c2pa.created"
    return act


def actions(entries, problems=None):
    """C2PA-shaped actions for the drafts and assistance, in log order. An entry
    missing a field it needs is left out and named in `problems`."""
    out = []
    for e in (x for x in pl.expanded(entries) if x.get("kind") in ("draft", "assist")):
        try:
            out.append(_action(e, first=not out))
        except (KeyError, TypeError, ValueError, AttributeError):
            if problems is not None:
                problems.append(f"entry {e.get('seq')}: malformed, left out of the actions")
    if out and out[0]["action"] != "c2pa.created":
        out.insert(0, {"action": "c2pa.opened"})
    return out


def _hashes(doc):
    with open(doc, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return ("sha256:" + hashlib.sha256(data).hexdigest(),
            "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest())


def _reveals(doc, entries, reveal):
    salts = pc.load_salts(pl.paths(doc)["salts"])
    by_seq = {e.get("seq"): e for e in entries}
    out = []
    for seq, text in sorted((reveal or {}).items()):
        e = by_seq.get(seq)
        if not e or e.get("kind") != "draft":
            raise ValueError(f"entry {seq} is not a draft")
        if text is None:
            snap = ev.snapshot_path(doc, e.get("commitment", ""))
            if not os.path.isfile(snap):
                raise ValueError(f"no snapshot for draft {seq}; pass the draft's text")
            with open(snap, encoding="utf-8", newline="") as fh:
                text = fh.read()
        salt = salts.get(e.get("commitment"), {}).get("salt")
        if not salt or not pc.opens(e["commitment"], salt, text):
            raise ValueError(f"the text given for draft {seq} does not open its commitment")
        out.append({"seq": seq, "salt": salt, "text": text})
    return out


def statement_entries(doc, include=()):
    """The entries a disclosure statement reads: the log with carried-forward
    assistance, plus the private input methods when the writer names them."""
    entries, _ = pl.load(doc)
    out = list(pl.expanded(entries))
    if "input_method" in include:
        out += pl.load_private(doc)
    return out


def summary(doc, include=(), reveal=None, contributions=None):
    if not pl.exists(doc):
        raise FileNotFoundError(f"no process log for {doc}; run `articulate process init`")
    entries, problems = pl.problems(doc)
    file_sha, text_sha = _hashes(doc)
    reviews = [e for e in entries if e.get("kind") == "review"]
    acts = actions(entries, problems)
    try:
        statement = disclose.build(statement_entries(doc, include), contributions,
                                   include=include)
    except (KeyError, TypeError, AttributeError):
        problems.append("an assistance entry is malformed, so no statement was built")
        statement = None
    out = {
        "schema": SCHEMA, "title": "Articulate process summary",
        "document": os.path.basename(doc), "file_sha256": file_sha, "text_sha256": text_sha,
        "chain": {"state": "broken" if problems else "intact", "problems": problems},
        "entries": [_export_entry(e, set(include)) for e in entries],
        "actions": acts,
        "editorial_responsibility": [r.get("role") for r in reviews
                                     if r.get("editorial_responsibility")],
        "disclosure": statement,
        "reveals": _reveals(doc, entries, reveal),
        "limits": LIMITS, "scope": PROCESS_SCOPE,
    }
    if "input_method" in include:
        out["input_methods"] = [{"method": e.get("method"), "sections": e.get("sections")}
                                for e in pl.load_private(doc)]
    return out


def verify_log(doc):
    """intact, broken, or missing when no log exists. Missing never passes."""
    if not pl.exists(doc):
        return {"state": "missing", "entries": 0,
                "problems": [f"no process log for {os.path.basename(doc)}"]}
    entries, problems = pl.problems(doc)
    return {"state": "broken" if problems else "intact", "entries": len(entries),
            "problems": problems}


def is_summary(obj):
    """True for a JSON object whose schema names a process summary."""
    return isinstance(obj, dict) and str(obj.get("schema", "")).startswith(
        "articulate/process-summary/")


def verify_summary(summ):
    """Check the schema, the chain state the summary records, and each revealed
    draft against the commitment the summary lists. Malformed input is broken."""
    try:
        return _verify_summary(summ)
    except (TypeError, KeyError, AttributeError, ValueError) as err:
        return {"state": "broken", "problems": [f"malformed summary ({type(err).__name__})"]}


def _verify_summary(summ):
    problems = []
    if summ.get("schema") not in (SCHEMA, SCHEMA_V1):
        problems.append("unknown summary schema")
    chain = summ.get("chain") or {}
    if chain.get("state") != "intact":
        problems.append(f"the summary records its chain as {chain.get('state')!r}")
    commits = {e.get("seq"): e.get("commitment") for e in summ.get("entries", [])}
    for r in summ.get("reveals", []):
        if not pc.opens(commits.get(r.get("seq")) or "", r.get("salt", ""), r.get("text", "")):
            problems.append(f"revealed draft {r.get('seq')} does not open its commitment")
    return {"state": "broken" if problems else "intact", "problems": problems}
