"""`articulate dialogue`: the dialogue profile and character voice checks.

    articulate dialogue FILE_OR_DIR ... [--voices DIR] [--format auto|lwd|colon|play]
                        [--json] [--gate] [--worst N] [--markdown FILE]

Reads script files (folders are walked; hidden folders are skipped), prints a
summary table per character and the worst lines, or the full report as JSON.
--gate exits 1 when the report fails the gate. Nothing is edited.
"""
import json
import os
import sys

from . import dialogue, dialogue_parse, dialogue_report, dialogue_sheet
from .detector import binary_reason

EXTENSIONS = (".lwd", ".txt", ".md", ".script", ".dialogue")


def _paths(items):
    for item in items:
        if os.path.isdir(item):
            for root, dirs, files in os.walk(item):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for fn in sorted(files):
                    if fn.endswith(EXTENSIONS):
                        yield os.path.join(root, fn)
        else:
            yield item


def read_records(items, fmt="auto"):
    records = []
    for path in _paths(items):
        with open(path, "rb") as fh:
            data = fh.read()
        reason = binary_reason(data, name=path)
        if reason:
            raise ValueError(f"cannot read {path} as text ({reason})")
        text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        records += dialogue_parse.parse(text, path.replace("\\", "/"),
                                        None if fmt == "auto" else fmt)
    return records


def cmd_dialogue(args):
    try:
        records = read_records(args.files, args.format)
        sheets, project = dialogue_sheet.load_dir(args.voices)
    except (OSError, ValueError) as exc:
        print(f"[articulate] {exc}", file=sys.stderr)
        return 2
    if not records:
        print("[articulate] no spoken lines found", file=sys.stderr)
        return 2
    themes = args.theme.split(",") if args.theme else None
    report = dialogue.audit(records, sheets, project, min_lines=args.min_lines,
                            theme_words=themes)
    verdict = dialogue.gate(report, max_epigram_rate=args.max_epigram_rate,
                            min_lift=args.min_lift)
    report["gate"] = verdict
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dialogue_report.markdown(report, worst_n=args.worst))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(dialogue.summary_table(report))
        print()
        for d in dialogue.worst(report, args.worst):
            print(f"{d['score']:3}  {d['file']}:{d['line']}  {d['speaker']}: {d['text'][:90]}")
            for f in d["findings"]:
                print(f"       - {f['check']}: {f['label']}"
                      + (f" ({f['excerpt']})" if f.get("excerpt") else ""))
        print()
        print("gate: " + ("passed" if verdict["passed"] else "failed: " +
                          "; ".join(verdict["reasons"])))
    return 1 if args.gate and not verdict["passed"] else 0


def register(sub):
    p = sub.add_parser("dialogue", help="dialogue profile and character voice checks for scripts")
    p.add_argument("files", nargs="+", help="script files or folders")
    p.add_argument("--voices", help="a folder of character voice sheets (JSON)")
    p.add_argument("--format", choices=("auto", "lwd", "colon", "play"), default="auto")
    p.add_argument("--theme", help="comma-separated theme words (else _project.json)")
    p.add_argument("--min-lines", type=int, default=None,
                   help="lines a speaker needs to be scored for attribution (default 20)")
    p.add_argument("--worst", type=int, default=30, help="how many worst lines to list")
    p.add_argument("--json", action="store_true", help="print the full report as JSON")
    p.add_argument("--markdown", help="also write a Markdown report to this file")
    p.add_argument("--gate", action="store_true", help="exit 1 when the gate fails")
    p.add_argument("--max-epigram-rate", type=float, default=0.01,
                   help="gate: highest share of lines with an epigram shape (default 0.01)")
    p.add_argument("--min-lift", type=float, default=None,
                   help="gate: fail a sheeted speaker whose attribution upper bound is below "
                        "this multiple of chance")
    p.set_defaults(corpus_handler=cmd_dialogue)
