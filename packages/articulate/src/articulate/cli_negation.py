"""`articulate negation`: the negation-load check.

    articulate negation FILE_OR_DIR ... [--profile NAME] [--rule copy|fiction]
                        [--min-words N] [--all] [--json] [--gate]

Splits each file into entries (paragraphs, list items, HTML blocks, script
blocks, dialogue lines, UI strings) and scores the share of clauses spent on
what a thing lacks. Prints the entries at or over the warn line, worst first.
--gate exits 1 when any entry is at or over the fail line. Nothing is edited.
"""
import json
import os
import sys

from . import negation_entries, negation_load, profiles
from .detector import binary_reason


def _paths(items):
    for item in items:
        if os.path.isdir(item):
            for root, dirs, files in os.walk(item):
                dirs[:] = sorted(d for d in dirs
                                 if not d.startswith(".") and d != "node_modules")
                for fn in sorted(files):
                    if fn.endswith(negation_entries.EXTENSIONS):
                        yield os.path.join(root, fn)
        else:
            yield item


def _profile_name(path, text, override):
    if override:
        return override
    return profiles.declared_profile(text) or profiles.profile_for(path)


def scan_file(path, text, *, profile=None, rule=None, min_words=negation_load.MIN_WORDS):
    """Scored entries for one file's text, each carrying its path."""
    name = _profile_name(path, text, profile)
    chosen = negation_load.rule_for(name, rule)
    found = negation_entries.entries(text, path, min_words=min_words)
    results = negation_load.assess(found, chosen, min_words)
    for r in results:
        r["path"] = path.replace("\\", "/")
        r["profile"] = name
    return results


def scan(items, **kw):
    results = []
    for path in _paths(items):
        with open(path, "rb") as fh:
            data = fh.read()
        if binary_reason(data, name=path):
            continue
        text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        results += scan_file(path, text, **kw)
    return results


def _line(r):
    where = f"{r['path']}:{r['line']}" if r["line"] else f"{r['path']} {r['label']}"
    head = (f"{r['score']:.2f} {r['verdict']:<4} {where}  "
            f"({r['negation_clauses']}/{r['clauses']} clauses, "
            f"{r['word_share']:.0%} of words)")
    body = "      " + r["text"][:150] + ("..." if len(r["text"]) > 150 else "")
    extra = []
    if r["markers"]:
        extra.append("negation: " + ", ".join(sorted(set(r["markers"]))))
    if r["virtue"]:
        extra.append("virtue phrases: " + ", ".join(sorted(set(r["virtue"]))))
    return "\n".join([head, body] + (["      " + "; ".join(extra)] if extra else []))


def cmd_negation(args):
    try:
        results = scan(args.files, profile=args.profile, rule=args.rule,
                       min_words=args.min_words)
    except (OSError, ValueError) as exc:
        print(f"[articulate] {exc}", file=sys.stderr)
        return 2
    results.sort(key=lambda r: (-r["score"], -r["word_share"], r["path"], r["line"]))
    shown = results if args.all else [r for r in results if r["verdict"] != "ok"]
    counts = negation_load.summary(results)
    if args.json:
        print(json.dumps({"summary": counts, "entries": shown}, ensure_ascii=False, indent=1))
    else:
        for r in shown:
            print(_line(r))
        print(f"\n{counts['entries']} entries scored: {counts['fail']} fail, "
              f"{counts['warn']} warn, {counts['ok']} ok; "
              f"{counts['virtue_entries']} use virtue phrases")
    return 1 if args.gate and counts["fail"] else 0


def register(sub):
    p = sub.add_parser("negation",
                       help="find entries that spend their words on what a thing lacks")
    p.add_argument("files", nargs="+", help="files or folders")
    p.add_argument("--profile", help="force a register profile (picks the rule)")
    p.add_argument("--rule", choices=sorted(negation_load.RULES),
                   help="force a rule: copy (warn 30%%, fail 50%%) or fiction "
                        "(warn 45%%, fail 65%%, character speech skipped)")
    p.add_argument("--min-words", type=int, default=negation_load.MIN_WORDS,
                   help="skip entries shorter than this (default 8)")
    p.add_argument("--all", action="store_true", help="list every scored entry")
    p.add_argument("--json", action="store_true", help="print entries as JSON")
    p.add_argument("--gate", action="store_true", help="exit 1 when an entry fails")
    p.set_defaults(corpus_handler=cmd_negation)
