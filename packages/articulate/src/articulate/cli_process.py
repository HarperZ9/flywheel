#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.cli_process -- `articulate process ...` and `articulate disclose`.

  process init DOC [--track] [--opt-in words,diff,time,snapshot]
  process draft DOC
  process note DOC (--text-file F | --label L) [--shareable]
  process source DOC CITATION [--shareable]
  process assist DOC --tool T --verb V [--sections ...] [--model M] [--version X]
  process input DOC --method M [--sections ...]
  process review DOC --role R --reviewed W --outcome O [--editorial] [--name N]
  process anchor DOC [--commit ID | --token-sha256 H]
  process continue DOC --reason R
  process export DOC [--include ...] [--reveal N[=FILE]] [--contributions F] [--out F]
  process verify (DOC | SUMMARY.json)
  disclose DOC [--template general|pip] [--contributions F] [--include input_method]

Every file stays on the writer's machine; nothing here calls the network.
"""
from __future__ import annotations

import json
import os
import sys

from . import disclose as dis
from . import process_events as ev
from . import process_export as px
from . import process_ledger as pl
from .provenance import DISCLOSE_HELP


def _read(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


def _csv(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def register(sub):
    p = sub.add_parser("process", help="a writer-held record of process (local, opt-in)")
    ps = p.add_subparsers(dest="pcmd")
    for name in ("init", "draft", "note", "source", "assist", "input", "review", "anchor",
                 "continue", "export", "verify"):
        q = ps.add_parser(name)
        q.add_argument("doc")
    a = {n: ps.choices[n] for n in ps.choices}
    a["init"].add_argument("--track", action="store_true",
                           help="let git see the log (no .gitignore written)")
    a["init"].add_argument("--opt-in", default="", help="words,diff,time,snapshot")
    a["note"].add_argument("--text-file")
    a["note"].add_argument("--label")
    a["note"].add_argument("--shareable", action="store_true")
    a["source"].add_argument("citation")
    a["source"].add_argument("--shareable", action="store_true")
    for k, req in (("--tool", True), ("--verb", True), ("--sections", False), ("--model", False),
                   ("--version", False), ("--source-type", False), ("--languages", False)):
        a["assist"].add_argument(k, required=req)
    a["input"].add_argument("--method", required=True)
    a["input"].add_argument("--sections")
    for k in ("--role", "--reviewed", "--outcome"):
        a["review"].add_argument(k, required=True)
    a["review"].add_argument("--editorial", action="store_true")
    a["review"].add_argument("--name")
    a["anchor"].add_argument("--commit")
    a["anchor"].add_argument("--token-sha256")
    a["continue"].add_argument("--reason", required=True)
    a["export"].add_argument("--include", default="")
    a["export"].add_argument("--reveal", action="append", default=[])
    a["export"].add_argument("--contributions")
    a["export"].add_argument("--out")
    d = sub.add_parser("disclose", help=DISCLOSE_HELP)
    d.add_argument("doc")
    d.add_argument("--template", default="general", choices=dis.TEMPLATES,
                   help="general: a statement with assistance and credit; pip: commit "
                        "trailers in the Assisted-by form of the pip project's "
                        "contribution policy, never a co-author trailer for a model")
    d.add_argument("--contributions")
    d.add_argument("--include", default="")
    d.add_argument("--claim", default=None, help="a sentence of your own to append")


def _reveal_map(items):
    out = {}
    for item in items:
        seq, _, path = item.partition("=")
        out[int(seq)] = _read(path) if path else None
    return out


def _contrib(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _record(args):
    doc, c = args.doc, args.pcmd
    if c == "init":
        return pl.init(doc, track=args.track, opt_in=_csv(args.opt_in))
    if c == "draft":
        return ev.record_draft(doc, _read(doc)) or {"note": "unchanged since the last draft"}
    if c == "note":
        return ev.record_note(doc, _read(args.text_file) if args.text_file else None,
                              args.label, args.shareable)
    if c == "source":
        return ev.record_source(doc, args.citation, args.shareable)
    if c == "assist":
        return ev.record_assist(doc, args.tool, args.verb, _csv(args.sections), args.version,
                                args.model, source_type=args.source_type,
                                languages=_csv(args.languages) or None)
    if c == "input":
        return ev.record_input_method(doc, args.method, _csv(args.sections))
    if c == "review":
        return ev.record_review(doc, args.role, args.reviewed, args.outcome,
                                args.editorial, args.name)
    if c == "anchor":
        return ev.record_anchor(doc, args.commit, args.token_sha256)
    if c == "continue":
        return pl.restart(doc, args.reason)
    return None


def _as_summary(path):
    """The parsed file when it is a process summary (by its schema field, never
    its name), else None."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (ValueError, UnicodeDecodeError):
        return None
    return obj if px.is_summary(obj) else None


def _verify(path):
    summ = _as_summary(path)
    return px.verify_summary(summ) if summ is not None else px.verify_log(path)


def _print_verify(res):
    """Intact exits 0, a missing log is no record (exit 3), anything else 1."""
    res = {**res, "limits": px.RECORD_LIMITS}
    print(json.dumps(res, indent=1))
    if res["state"] == "missing":
        print(f"[process] {px.NO_RECORD}.", file=sys.stderr)
        return px.NO_RECORD_EXIT
    print(f"[process] {px.RECORD_LIMITS}", file=sys.stderr)
    return 0 if res["state"] == "intact" else 1


def cmd_process(args):
    try:
        if args.pcmd == "export":
            summ = px.summary(args.doc, _csv(args.include), _reveal_map(args.reveal),
                              _contrib(args.contributions))
            out = args.out or os.path.splitext(args.doc)[0] + ".process-summary.json"
            with open(out, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(summ, fh, indent=1, ensure_ascii=False)
            print(f"[process] wrote {out} (chain {summ['chain']['state']})")
            print(f"[process] {px.RECORD_LIMITS}")
            return 0
        if args.pcmd == "verify":
            return _print_verify(_verify(args.doc))
        res = _record(args)
    except (ValueError, OSError, KeyError, TypeError, dis.DisclosureRefused) as e:
        print(f"[process] {e}", file=sys.stderr)
        return 2
    if res is None:
        print("[process] choose a subcommand: init, draft, note, source, assist, input, "
              "review, anchor, continue, export, verify", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


def cmd_disclose(args):
    """A statement needs an intact log: with no log, or a broken one, it could
    leave out assistance the writer recorded."""
    state = px.verify_log(args.doc)
    if state["state"] != "intact":
        why = ("no process log exists for this document, so a statement would have "
               "nothing to report" if state["state"] == "missing" else
               "the process log is broken (" + "; ".join(state["problems"][:2]) +
               "), so a statement could leave out recorded assistance. Run "
               "`articulate process continue` first")
        print(f"[disclose] refused: {why}", file=sys.stderr)
        return 2
    include = _csv(args.include)
    try:
        print(dis.build(px.statement_entries(args.doc, include), _contrib(args.contributions),
                        args.template, include, claim=args.claim), end="")
        print(f"[disclose] {px.RECORD_LIMITS}", file=sys.stderr)
    except dis.DisclosureRefused as e:
        print(f"[disclose] refused: {e}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, OSError) as e:
        print(f"[disclose] cannot build the statement: {e!r}", file=sys.stderr)
        return 2
    return 0


def record_pass(args, result, text):
    """Add an accepted editor pass to the writer's process record, if one exists."""
    if args.cmd not in ("fix", "polish", "submit") or "plan_id" in result:
        return
    if result.get("text") == text:
        return
    try:
        ev.record_editor_pass(args.file, args.cmd, backend=result.get("backend"),
                              model=result.get("model"))
    except pl.LogBroken as exc:
        result["process_log_warning"] = str(exc)
