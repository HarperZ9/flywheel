"""Command-line verbs for series review and the author's voice.

corpus, voice (in cli_voice), interview,
restructure and titles. Nothing here writes a file except to a path the author
names with --out, --receipt or --answers-out, and voice learn, which saves a
profile in the voice store. No verb edits an input file in place.
"""
import importlib
import json
import sys

from .detector import binary_reason


class _Lazy:
    """A module loaded on first use, so `articulate house apply` and the other
    verbs do not pay to import the series modules they never call."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        return getattr(importlib.import_module("articulate." + self._name), attr)


corpus, corpus_features, corpus_receipt = _Lazy("corpus"), _Lazy("corpus_features"), _Lazy("corpus_receipt")
interview, restructure, titles = _Lazy("interview"), _Lazy("restructure"), _Lazy("titles")
voice_identity, voice_store = _Lazy("voice_identity"), _Lazy("voice_store")

_GENRES = ("essay", "op-ed", "letter", "memoir", "report", "docs", "other")


def _read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    reason = binary_reason(data, name=path)
    if reason:
        raise ValueError(f"cannot read {path} as text ({reason})")
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _docs(paths):
    return [{"name": p, "text": _read(p)} for p in paths]


def _lines(path):
    return [line.strip() for line in _read(path).split("\n")] if path else []


def _emit(value, as_json, text):
    print(json.dumps(value, ensure_ascii=False, indent=2) if as_json else text)


def cmd_corpus(args):
    docs = _docs(args.files)
    report = corpus.analyze_corpus(docs, keep=_lines(args.keep), genre=args.genre,
                                   single=args.single)
    if args.receipt:
        rec = corpus_receipt.make_corpus_receipt(docs, keep=report["keep"], genre=args.genre,
                                                 single=args.single, report=report)
        _write(args.receipt, json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    _emit(report, args.json, corpus.format_report(report))
    return 0


def _print_questions(qs):
    for q in qs:
        print(f"{q['id']} (lines {q['line_start']}-{q['line_end']}, {q['trigger']}): {q['question']}")


def cmd_interview(args):
    if args.collect:
        out = interview.collect(_read(args.collect))
        if args.answers_out:
            _write(args.answers_out, "\n\n".join(a["answer"] for a in out["answers"]))
        if args.out:
            _write(args.out, out["text"])
        _emit(out, args.json, "\n".join(f"{u['id']} unanswered: {u['question']}"
                                        for u in out["unanswered"]) or "Every marker has an answer.")
        return 0
    if not args.doc:
        raise ValueError("interview needs a document, or --collect FILE")
    text = _read(args.doc)
    profile = voice_store.load(args.voice, args.dir) if args.voice else None
    if profile is not None:
        voice_identity.check_owner(profile, args.dir)
    report = interview.questions(text, voice_profile=profile)
    if args.out:
        _write(args.out, interview.mark(text, report["questions"]))
    if args.json:
        _emit(report, True, "")
    else:
        _print_questions(report["questions"])
    return 0


def cmd_restructure(args):
    out = restructure.propose(_read(args.doc), anchors=args.anchors)
    if args.out and out["verdict"]["ok"]:
        _write(args.out, out["proposal"])
    if args.json:
        _emit(out, True, "")
        return 0 if out["verdict"]["ok"] else 1
    s = out["summary"]
    print(out["diff"] or "No sentence to move.")
    print(f"Moved {s['moved_sentences']} sentences. Paragraphs ending in a limit or confidence "
          f"line: {s['scaffold_share_before']} before, {s['scaffold_share_after']} after.")
    print(s["scope"])
    if not out["verdict"]["ok"]:
        print("Refused: " + "; ".join(out["verdict"]["reasons"]))
        return 1
    return 0


def cmd_titles(args):
    docs = _docs(args.paths)
    names = [corpus.doc_title(d) or d["name"] for d in docs] + _lines(args.titles)
    names = [n for n in names if n]
    heads = [[s["heading"].lstrip("# ") for s in corpus_features.sections(d["text"])] for d in docs]
    report = titles.workshop(names, answers=_lines(args.answers), headings=heads)
    text = []
    for f in report["families"]:
        text.append(f"{f['family']} ({len(f['titles'])}, share {f['share']}): " + "; ".join(f["titles"]))
    for q in report["questions"]:
        text.append(f"{q['title']}: {q['question']}")
    for s in report["suggestions"]:
        text.append(f"  {s['label']} for {s['title']!r}: {s['text']} ({s['shape']})")
    _emit(report, args.json, "\n".join(text))
    return 0


def verify(receipt, paths):
    verdict, detail = corpus_receipt.verify_corpus_receipt(receipt, _docs(paths))
    print(f"[articulate] {verdict}: {detail}")
    return {"Match": 0, "Drift": 1}.get(verdict, 2)


def _run(handler):
    def run(args):
        try:
            return handler(args)
        except (OSError, ValueError) as exc:
            print(f"[articulate] {exc}", file=sys.stderr)
            return 2
    return run


def register(sub):
    from .cli_corpus_args import add_parsers
    def cmd_voice(args):
        from .cli_voice import cmd_voice as run
        return run(args)
    add_parsers(sub, {"corpus": cmd_corpus, "voice": cmd_voice, "interview": cmd_interview,
                      "restructure": cmd_restructure, "titles": cmd_titles}, _run, _GENRES)
