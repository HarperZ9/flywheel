"""Command-line handlers for voice intend, voice check and voice register.

intend writes a spec and prints its plan. check scores drafts against a spec
file or a built-in name and exits 1 when a draft scores under --min-score.
register compares the author's draft with a rewrite and names each register
feature the rewrite lost, exiting 1 when it lost any. None of them edits a draft.
"""
import json

from . import voice_intent, voice_register
from .voice_intent_specs import BUILTIN
from .voice_intent_text import format_check, format_spec


def _read(path):
    from .cli_voice import _read as read
    return read(path)


def intend(args):
    if args.list:
        print("\n".join(sorted(BUILTIN)))
        return 0
    if not (args.goal or args.base):
        raise ValueError("voice intend needs --goal, or --base to start from a built-in spec "
                         f"({', '.join(sorted(BUILTIN))})")
    samples = [_read(p) for p in args.sample or ()]
    spec = voice_intent.build_spec(args.goal, args.audience, args.stance, samples,
                                   base=args.base, name=args.name or args.base or "custom",
                                   tools=args.tool or ())
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(spec, ensure_ascii=False, indent=2) if args.json else format_spec(spec))
    if args.out:
        print(f"\nWrote {args.out}. Score a draft: articulate voice check DRAFT --intent {args.out}")
    return 0


def check(args):
    spec = voice_intent.load_spec(args.intent)
    worst = 100
    reports = []
    for path in args.drafts:
        report = voice_intent.check(_read(path), spec)
        worst = min(worst, report["score"])
        reports.append(dict(report, path=path))
        if not args.json:
            print(format_check(report, path))
    if args.json:
        print(json.dumps(reports if len(reports) > 1 else reports[0], ensure_ascii=False, indent=2))
    return 1 if args.min_score is not None and worst < args.min_score else 0


def register(args):
    report = voice_register.flattening(_read(args.before), _read(args.after))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["features"]:
            if row["status"] != "absent":
                print(f"  {row['feature']:<15}{row['before']:>4} -> {row['after']:<4}{row['status']}")
        lost = ", ".join(report["lost"]) or "nothing"
        print(f"{args.after}: lost {lost}. {report['scope']}")
    return 1 if report["flattened"] else 0


def add_parsers(vs):
    """The intend and check sub-commands, added to the voice parser."""
    p = vs.add_parser("intend", help="build a voice spec and a plan from a goal, audience and stance")
    p.add_argument("--goal", help="what the writing is for, e.g. 'persuade on X'")
    p.add_argument("--audience", help="who reads it")
    p.add_argument("--stance", help="how you stand, e.g. 'contrarian, asks what if'")
    p.add_argument("--sample", action="append", help="a reference text (repeatable); only counts are kept")
    p.add_argument("--base", help="start from a built-in spec, e.g. zain")
    p.add_argument("--tool", action="append", help="a tool name the draft should mention (repeatable)")
    p.add_argument("--name", help="the spec's name")
    p.add_argument("--out", help="write the spec JSON here")
    p.add_argument("--list", action="store_true", help="list the built-in specs")
    p.add_argument("--json", action="store_true")
    c = vs.add_parser("check", help="score drafts against an intent spec")
    c.add_argument("drafts", nargs="+")
    c.add_argument("--intent", required=True, help="a spec file from voice intend, or a built-in name")
    c.add_argument("--min-score", type=int, help="exit 1 when a draft scores under this")
    c.add_argument("--json", action="store_true")
    r = vs.add_parser("register", help="name the register features a rewrite of your draft lost")
    r.add_argument("before", help="your draft")
    r.add_argument("after", help="the rewrite")
    r.add_argument("--json", action="store_true")
