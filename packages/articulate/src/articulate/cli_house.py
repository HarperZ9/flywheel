"""Command-line verbs for the house voice.

articulate house apply [FILE | -]   transform model output, stdin to stdout
articulate house brief [--agents]   print the brief (the AGENTS.md form with --agents)
articulate house show               active settings, where each came from, and the brief
articulate house on | off           turn the house voice on (mode default) or off
articulate house set KEY=VALUE...   set the mode or a tuning key

on, off and set write the settings file and nothing else. apply never edits its
input file; it prints the result and writes a receipt only to --receipt.
"""
import json
import sys

from . import house, house_settings


def _read(path):
    if path in (None, "-"):
        return sys.stdin.read()
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


def cmd_apply(args):
    text = _read(args.file)
    out = house.transform(text)
    if args.receipt:
        with open(args.receipt, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(out["receipt"], indent=2, ensure_ascii=False) + "\n")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(out["text"])
        for n in out["notes"]:
            print("[articulate] L%d %s: %s" % (n["line"], n["category"], n["reason"]), file=sys.stderr)
        for r in out["refused"]:
            print("[articulate] kept the original: %s" % r, file=sys.stderr)
    return 0


def cmd_brief(args):
    text = house.brief(house_settings.for_request())
    if args.agents:
        print("## Articulate house voice\n\nWrite replies in this voice.\n\n" + text)
    else:
        print(text)
    return 0


def cmd_show(args):
    s = house_settings.resolve()
    src = s["sources"]
    print("mode: %s (%s)" % (s["mode"], src["mode"]))
    for key in sorted(s["tuning"]):
        print("%s: %s (%s)" % (key, s["tuning"][key], src[key]))
    print("settings file: %s" % house_settings.settings_path())
    for problem in s["problems"]:
        print("note: %s" % problem)
    print("fingerprint: %s\n" % house.fingerprint(s))
    print(house.brief(s) if s["mode"] != "off" else "The house voice is off; no brief is sent.")
    return 0


def _save(mode=None, tuning=None):
    current = house_settings.stored()
    merged = {"mode": mode or current.get("mode"),
              "tuning": dict(current.get("tuning", {}), **(tuning or {}))}
    path = house_settings.save(merged)
    print("[articulate] saved %s" % path)
    return 0


def cmd_on(args):
    return _save(mode="default")


def cmd_off(args):
    return _save(mode="off")


def cmd_set(args):
    mode, tuning = None, {}
    for pair in args.pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError("write each setting as KEY=VALUE, for example length=terse")
        if key == "mode":
            mode = house_settings.normalize_mode(value)
        else:
            tuning[key] = value
    house_settings.validate({"tuning": tuning})
    return _save(mode=mode, tuning=tuning)


def _run(handler):
    def run(args):
        try:
            return handler(args)
        except (OSError, ValueError) as exc:
            print("[articulate] %s" % exc, file=sys.stderr)
            return 2
    return run


def register(sub):
    p = sub.add_parser("house", help="the house voice for model output: apply, brief, show, on, off, set")
    hs = p.add_subparsers(dest="house_cmd", required=True)
    a = hs.add_parser("apply", help="transform model output (a file, or - for stdin) to stdout")
    a.add_argument("file", nargs="?", default="-")
    a.add_argument("--json", action="store_true")
    a.add_argument("--receipt", help="write a house receipt to this file")
    a.set_defaults(corpus_handler=_run(cmd_apply))
    b = hs.add_parser("brief", help="print the brief a model reads at session start")
    b.add_argument("--agents", action="store_true", help="print it as an AGENTS.md section")
    b.set_defaults(corpus_handler=_run(cmd_brief))
    hs.add_parser("show", help="active settings and their sources").set_defaults(corpus_handler=_run(cmd_show))
    hs.add_parser("on", help="turn the house voice on").set_defaults(corpus_handler=_run(cmd_on))
    hs.add_parser("off", help="turn the house voice off").set_defaults(corpus_handler=_run(cmd_off))
    s = hs.add_parser("set", help="set mode=... or a tuning key, for example length=terse")
    s.add_argument("pairs", nargs="+")
    s.set_defaults(corpus_handler=_run(cmd_set))


def verify(receipt, path):
    verdict, detail = house.verify_receipt(receipt, _read(path))
    print("[articulate] %s: %s" % (verdict, detail))
    return {"Match": 0, "Drift": 1}.get(verdict, 2)
