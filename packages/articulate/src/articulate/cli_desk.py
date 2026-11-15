#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.cli_desk -- `articulate desk FILE [--venue V] [--disclosure F] [--author]`.

Exits 0 whenever the run completes, whatever it finds, and 2 on unreadable or
binary input, so a refused file never reports success. Prints no question count.
"""
from __future__ import annotations

import json
import sys

from . import desk
from .detector import binary_reason


def register(sub):
    d = sub.add_parser("desk", help="questions for a reviewer, inside the document and "
                                    "across the field")
    d.add_argument("file")
    d.add_argument("--venue", default=None, choices=sorted(desk.desk_inside.VENUES),
                   help="none, paper or course")
    d.add_argument("--disclosure", default=None, help="a statement of tool use, as a file")
    d.add_argument("--author", action="store_true",
                   help="the author side: presence checks before submission")
    d.add_argument("--json", action="store_true")


def _read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    reason = binary_reason(data, name=path)
    if reason:
        raise ValueError(reason)
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _print(rep):
    print(f"[desk] {rep['header']}\n")
    print(rep["inside"]["title"])
    for i in rep["inside"]["items"]:
        where = f"L{i['line']} " if i["line"] else ""
        print(f"  {where}[{i['check']}] {i['question']}")
        if i["quote"]:
            print(f"      \"{i['quote']}\"")
    if not rep["inside"]["items"]:
        print("  (no question from the document's own statements)")
    print("\n" + rep["across_field"]["title"])
    for p in rep["across_field"]["prompts"]:
        print(f"  {p['question']}")
        for c in p["authors_claims"]:
            print(f"      \"{c['quote']}\" ({c['label']})")
    print(f"\n[desk] {desk.ITEM_LIMIT}")


def cmd_desk(args):
    try:
        text = _read(args.file)
        disclosure = _read(args.disclosure) if args.disclosure else None
        rep = desk.review(text, args.venue, disclosure, args.author)
    except (OSError, ValueError) as e:
        print(f"[desk] cannot read {args.file}: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        _print(rep)
    return 0
