#!/usr/bin/env python
"""Measure the dialogue profile on public-domain dialogue written by people.

    python scripts/dialogue_calibrate.py --gutenberg DIR [--out docs/dialogue-calibration.json]

DIR holds the Project Gutenberg plain-text files named pg<number>.txt for the
eBooks in SOURCES. Only the text between the START and END markers is read;
the Project Gutenberg header, footer and trademark are not used or kept. The
output records each file's SHA-256, so the run can be repeated and checked.

Plays are read as speeches with their speakers. Novels are read as the quoted
speech in each paragraph, without speakers. Wilde is the contrast case: his
characters speak in epigrams on purpose, so the epigram checks should fire on
him more than on the others. Nothing here sets a threshold automatically; the
numbers are read and the rules adjusted by hand, and docs/dialogue.md says how.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from articulate import dialogue_attrib, dialogue_parse, dialogue_rules  # noqa: E402

LICENCE = ("Public domain in the United States: first published before 1929. Read from the "
           "Project Gutenberg eBook named; the Gutenberg header, footer and trademark are not "
           "redistributed.")
SOURCES = [
    {"pg": 3825, "work": "Pygmalion", "author": "Bernard Shaw", "year": 1913, "kind": "play"},
    {"pg": 3618, "work": "Arms and the Man", "author": "Bernard Shaw", "year": 1898,
     "kind": "play"},
    {"pg": 1754, "work": "The Sea-Gull", "author": "Anton Chekhov, tr. Marian Fell",
     "year": 1912, "kind": "play"},
    {"pg": 7986, "work": "Plays, Second Series", "author": "Anton Chekhov, tr. Julius West",
     "year": 1916, "kind": "play"},
    {"pg": 76, "work": "Adventures of Huckleberry Finn", "author": "Mark Twain", "year": 1884,
     "kind": "novel"},
    {"pg": 1400, "work": "Great Expectations", "author": "Charles Dickens", "year": 1861,
     "kind": "novel"},
    {"pg": 844, "work": "The Importance of Being Earnest", "author": "Oscar Wilde",
     "year": 1895, "kind": "play", "role": "contrast: epigrams by design"},
]
THEMES = ["truth", "love", "life", "death", "money", "honour", "honor", "duty", "god",
          "freedom", "justice", "happiness", "marriage"]
_QUOTE = re.compile(r"“([^”]{3,})”")


def body(raw):
    start = re.search(r"\*\*\* START OF TH[EI]S? PROJECT GUTENBERG EBOOK[^\n]*\n", raw)
    end = re.search(r"\*\*\* END OF TH[EI]S? PROJECT GUTENBERG EBOOK", raw)
    return raw[start.end() if start else 0:end.start() if end else len(raw)]


def novel_lines(text, path):
    out = []
    for n, para in enumerate(re.split(r"\n\s*\n", text)):
        quotes = _QUOTE.findall(para.replace("\n", " "))
        if quotes:
            speech = " ".join(q.strip().rstrip(",") for q in quotes)
            out.append({"speaker": "?", "text": re.sub(r"\s+", " ", speech), "file": path,
                        "line": n, "node": None, "group": None})
    return out


def play_lines(text, path):
    lines = dialogue_parse.parse_play(text, path)
    names = Counter(r["speaker"] for r in lines)
    known = {s for s, n in names.items() if n >= 3}
    return [r for r in dialogue_parse.parse_play(text, path, known=known)]


def measure(lines, themes):
    proper = dialogue_rules.proper_nouns(lines)
    hits = Counter()
    flagged = 0
    examples = {}
    for rec in lines:
        found = dialogue_rules.check_line(rec["text"], themes, proper)
        flagged += bool(found)
        for f in {f["check"]: f for f in found}.values():
            hits[f["check"]] += 1
            examples.setdefault(f["check"], []).append(f["excerpt"])
    n = len(lines)

    def rate(k):
        lo, hi = dialogue_attrib.wilson(k, n)
        return {"count": k, "rate": round(k / n, 4) if n else None,
                "interval": [round(lo, 4), round(hi, 4)]}
    epi = sum(1 for rec in lines if any(f["check"] in dialogue_rules.EPIGRAM_CHECKS for f in
                                        dialogue_rules.check_line(rec["text"], themes, proper)))
    return {"lines": n, "any_flag": rate(flagged), "epigram_any": rate(epi),
            "by_check": {c: rate(hits[c]) for c in sorted(dialogue_rules.WEIGHTS)},
            "examples": {c: v[:5] for c, v in sorted(examples.items())}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gutenberg", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "dialogue-calibration.json")
    a = ap.parse_args(argv)
    report = {"format": "articulate-dialogue-calibration/1", "licence": LICENCE,
              "themes": THEMES, "sources": []}
    for src in SOURCES:
        path = a.gutenberg / f"pg{src['pg']}.txt"
        raw = path.read_bytes()
        text = body(raw.decode("utf-8", errors="replace").replace("\r\n", "\n"))
        lines = (play_lines if src["kind"] == "play" else novel_lines)(text, path.name)
        entry = dict(src, sha256=hashlib.sha256(raw).hexdigest(), licence=LICENCE,
                     measure=measure(lines, THEMES))
        if src["kind"] == "play":
            att = dialogue_attrib.attribute(lines, min_lines=30)
            entry["attribution"] = {"chance": att["chance"], "speakers": att["speakers"]}
        report["sources"].append(entry)
        m = entry["measure"]
        print(f"{src['work'][:30]:30} lines {m['lines']:5}  any {m['any_flag']['rate']:.3f}  "
              f"epigram {m['epigram_any']['rate']:.3f}  "
              + " ".join(f"{c}={v['count']}" for c, v in m["by_check"].items() if v["count"]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                     newline="\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
