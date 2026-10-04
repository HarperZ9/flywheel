"""build_shapley_placebo_items.py -- build the item set for the Shapley placebo test.

Each item is one question whose answer appears in exactly one public-domain gold
passage, plus five known-null control sources that should get no credit:
one empty source, two irrelevant passages, and two shuffled sources (the words of
an irrelevant passage in a seeded random order). Gold passages come from Charles
Darwin's "The Voyage of the Beagle" (Project Gutenberg #944); irrelevant passages
come from Gutenberg #2701, #1228, #205, #308 and #201. All are public domain in
the United States.

The questions and their accepted answers are written by hand below. The builder
checks that no control source contains any accepted answer, so a control cannot
carry the answer by accident.

    python scripts/build_shapley_placebo_items.py --cache DIR --out items.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import urllib.request
from pathlib import Path

GOLD_BOOK = 944
NULL_BOOKS = (2701, 1228, 205, 308, 201)
SEED = 20261004
# (gold passage must contain this phrase, question, accepted answers)
QUESTIONS = [
    ("one hundred and sixty-three paces", "According to Azara, how many paces away was the wasp's nest?",
     ["163", "one hundred and sixty three", "one hundred sixty three"]),
    ("paid horse-hire for thirty-one leagues", "For how many leagues did the author pay horse-hire that day?",
     ["31", "thirty one"]),
    ("man-carrying pig", "What did the Tahitians call the horse?", ["man carrying pig"]),
    ("height of 3400 feet", "What height had the sandstone plateau reached at the Blackheath, in feet?",
     ["3400"]),
    ("Captain Lloyd, the Surveyor-general", "What was the name of the Surveyor-general who invited the author?",
     ["lloyd"]),
    ("height of about 2000 feet; here", "At about what height, in feet, were the author's lodgings near Napoleon's tomb?",
     ["2000"]),
    ("prodigious height of 23,000 feet", "What height does the passage give for Aconcagua, in feet?",
     ["23000"]),
    ("being about 700 miles", "About how many miles apart in latitude were the two places compared?",
     ["700"]),
    ("F. esculentus six feet", "How long, in feet, had the Fucus esculentus grown on the chiselled rock?",
     ["6", "six"]),
    ("most southern position (lat. 41", "At what latitude, in degrees, was the colony at the Rio Negro?",
     ["41"]),
    ("landing for Pomarre in 1817", "In what year was a horse landed for Pomarre at Tahiti?", ["1817"]),
    ("Fuega Basket", "What was the name of the native woman who came on board and could talk some English?",
     ["basket"]),
    ("not more than twenty inches", "At Bear Lake, how far, in inches, did the thaw penetrate at most?",
     ["20", "twenty"]),
    ("under Cape Gregory: a very hard gale", "What was the temperature at anchor under Cape Gregory on January 29th, in degrees?",
     ["57"]),
    ("depth of about 500 feet", "How deep, in feet, was the grand ravine worn through the lava?", ["500"]),
    ("to the northward of Cape Frio", "The Englishman's estate lay to the northward of which cape?", ["frio"]),
]


def normalize(text: str) -> str:
    """Lowercase; drop commas inside numbers; hyphens to spaces; collapse spaces."""
    t = re.sub(r"(?<=\d),(?=\d)", "", str(text).lower()).replace("-", " ")
    return re.sub(r"\s+", " ", t).strip()


def _book(cache: Path, book_id: int) -> tuple:
    path = cache / f"pg{book_id}.txt"
    if not path.exists():
        url = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
        with urllib.request.urlopen(url, timeout=60) as r:
            path.write_bytes(r.read())
    raw = path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    body = text[text.find("*** START"):text.find("*** END")]
    paras = [re.sub(r"\s+", " ", p).strip() for p in body.split("\n\n")]
    return hashlib.sha256(raw).hexdigest(), [p for p in paras if 50 <= len(p.split()) <= 110]


def contains(text: str, answer: str) -> bool:
    """Whole-word match of a normalized answer inside normalized text."""
    return re.search(r"\b" + re.escape(normalize(answer)) + r"\b", normalize(text)) is not None


def _clean_null(paras, answers_all) -> list:
    out = []
    for p in paras:
        if not re.search(r"\d", p) and not any(contains(p, a) for a in answers_all):
            out.append(p)
    return out


def _shuffled(passage: str, rng: random.Random) -> str:
    words = passage.split()
    rng.shuffle(words)
    return " ".join(words)


def build(cache: Path) -> dict:
    rng = random.Random(SEED)
    gold_sha, gold_paras = _book(cache, GOLD_BOOK)
    answers_all = {normalize(a) for _, _, accepted in QUESTIONS for a in accepted}
    books, null_pool = {GOLD_BOOK: gold_sha}, []
    for b in NULL_BOOKS:
        sha, paras = _book(cache, b)
        books[b] = sha
        null_pool += [(b, p) for p in _clean_null(paras, answers_all)]
    items = []
    for i, (phrase, question, accepted) in enumerate(QUESTIONS):
        gold = [p for p in gold_paras if phrase in p]
        if len(gold) != 1:
            raise SystemExit(f"question {i}: {len(gold)} gold passages contain {phrase!r}")
        picks = rng.sample(null_pool, 4)
        sources = [{"role": "gold", "kind": "gold", "text": gold[0], "book": GOLD_BOOK},
                   {"role": "control", "kind": "empty", "text": "", "book": None}]
        sources += [{"role": "control", "kind": "irrelevant", "text": p, "book": b} for b, p in picks[:2]]
        sources += [{"role": "control", "kind": "shuffled", "text": _shuffled(p, rng), "book": b}
                    for b, p in picks[2:]]
        rng.shuffle(sources)
        for s in sources:
            if s["role"] == "control" and any(contains(s["text"], a) for a in accepted):
                raise SystemExit(f"question {i}: a control carries the answer")
        items.append({"item_id": f"beagle-{i:02d}", "question": question,
                      "accepted": accepted, "sources": sources})
    return {"schema": "flywheel.shapley-placebo-items/v1", "seed": SEED,
            "gutenberg_sha256": {str(k): v for k, v in books.items()}, "items": items}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cache", required=True, help="folder for the downloaded Gutenberg texts")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    Path(a.cache).mkdir(parents=True, exist_ok=True)
    data = build(Path(a.cache))
    Path(a.out).write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(len(data["items"]), "items;", hashlib.sha256(Path(a.out).read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
