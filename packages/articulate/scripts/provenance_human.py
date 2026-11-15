"""Add the human documents of the known-provenance corpus to the manifest.

    python scripts/provenance_human.py --gutenberg DIR --persuade CSV

Gutenberg excerpts (public domain in the United States) are written under
corpus/provenance/human/ and committed. PERSUADE 2.0 essays (CC BY-NC-SA 4.0)
are written under the local root and only their hashes are committed.
Selection is seeded, so the same inputs give the same documents.
"""
import argparse
import collections
import csv
import random
import re

import provenance_common as C

BOOKS = {  # ebook number: (genre, author, title, first published)
    "1228": ("science", "Charles Darwin", "On the Origin of Species", 1859),
    "944": ("science", "Charles Darwin", "The Voyage of the Beagle", 1839),
    "205": ("essay", "Henry David Thoreau", "Walden", 1854),
    "2701": ("fiction", "Herman Melville", "Moby-Dick", 1851),
    "201": ("fiction", "Edwin A. Abbott", "Flatland", 1884),
    "308": ("fiction", "Jerome K. Jerome", "Three Men in a Boat", 1889),
}
PER_BOOK = 3
PROMPTS = ["Distance learning", "Seeking multiple opinions", "Mandatory extracurricular activities",
           "Cell phones at school", "Community service", "Summer projects"]
PER_PROMPT = {"No": 6, "Yes": 3}
GUTENBERG_LICENCE = ("Public domain in the United States; Project Gutenberg header and "
                     "footer removed, so no Project Gutenberg trademark terms apply")
PERSUADE_LICENCE = "CC BY-NC-SA 4.0; kept local, never committed"


def gutenberg_paragraphs(raw):
    body = raw.split("*** START OF", 1)[1].split("\n", 1)[1].split("*** END OF", 1)[0]
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body)]
    return [p.replace("_", "") for p in paras
            if len(p.split()) >= 40 and not p.isupper() and not p.startswith("[")]


def trim(text, limit=450):
    """Cut at the last sentence end before `limit` words."""
    ws = text.split()
    if len(ws) <= limit:
        return text
    cut = " ".join(ws[:limit])
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > 0 else cut


def excerpts(book, paras):
    out = []
    for i in range(PER_BOOK):
        rng = random.Random(f"gutenberg-{book}-{i}")
        j = rng.randrange(len(paras) // 10, len(paras) * 9 // 10)
        chunk = []
        while j < len(paras) and C.words(" ".join(chunk)) < 250:
            chunk.append(paras[j])
            j += 1
        out.append(trim("\n\n".join(chunk)) + "\n")
    return out


def add_gutenberg(man, folder):
    added = 0
    for book, (genre, author, title, year) in BOOKS.items():
        raw = (folder / f"pg{book}.txt").read_text(encoding="utf-8")
        src_sha = C.sha256_text(raw)
        for i, text in enumerate(excerpts(book, gutenberg_paragraphs(raw))):
            doc = {"id": f"human-gutenberg-{book}-{i}", "class": "human", "genre": genre,
                   "location": "repo", "path": f"human/gutenberg-{book}-{i}.txt",
                   "sha256": C.sha256_text(text), "words": C.words(text), "written": str(year),
                   "source": {"work": f"{author}, {title} ({year})",
                              "upstream": f"Project Gutenberg eBook #{book}",
                              "upstream_sha256": src_sha, "licence": GUTENBERG_LICENCE,
                              "transform": "seeded excerpt; lines unwrapped; underscore italics removed"}}
            if C.upsert(man, doc):
                C.write_text(doc, text)
                added += 1
    return added


SPEECHES = {"declaration-preamble": ("US Declaration of Independence, preamble", 1776),
            "gettysburg": ("Abraham Lincoln, Gettysburg Address", 1863),
            "lincoln-2nd-inaugural": ("Abraham Lincoln, second inaugural address, excerpt", 1865)}


def add_speeches(man):
    """The public-domain speeches already in corpus/human, by reference."""
    added = 0
    for name, (work, year) in SPEECHES.items():
        text = (C.ROOT / "corpus" / "human" / f"{name}.txt").read_text(encoding="utf-8")
        doc = {"id": f"human-speech-{name}", "class": "human", "genre": "speech",
               "location": "repo", "path": f"../human/{name}.txt", "sha256": C.sha256_text(text),
               "words": C.words(text), "written": str(year),
               "source": {"work": work, "licence": "Public domain", "transform": "none"}}
        added += C.upsert(man, doc)
    return added


def persuade_rows(path):
    csv.field_size_limit(10 ** 9)
    seen = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            seen.setdefault(row["essay_id_comp"], row)
    return seen


def add_persuade(man, path, local_root):
    rows = persuade_rows(path)
    by = collections.defaultdict(list)
    for eid, r in sorted(rows.items()):
        if r["task"] == "Independent" and 150 <= C.words(r["full_text"]) <= 700:
            by[(r["prompt_name"], r["ell_status"].strip())].append(eid)
    table_sha = C.sha256_text(open(path, encoding="utf-8", newline="").read())
    added = 0
    for prompt in PROMPTS:
        for ell, n in PER_PROMPT.items():
            for eid in random.Random(f"persuade-{prompt}-{ell}").sample(by[(prompt, ell)], n):
                added += _persuade_doc(man, rows[eid], eid, ell, table_sha, local_root)
    return added


def _persuade_doc(man, r, eid, ell, table_sha, local_root):
    text = r["full_text"].strip() + "\n"
    doc = {"id": f"human-persuade-{eid}", "class": "human", "genre": "student-essay",
           "location": "local", "path": f"human/persuade-{eid}.txt",
           "sha256": C.sha256_text(text), "words": C.words(text), "written": "2010 to 2020",
           "group": {"ell_status": ell, "prompt_name": r["prompt_name"]},
           "source": {"work": "PERSUADE 2.0 training set, essay " + eid,
                      "upstream": "https://github.com/scrosseye/persuade_corpus_2.0",
                      "upstream_sha256": table_sha, "licence": PERSUADE_LICENCE,
                      "transform": "full_text, outer whitespace stripped"}}
    if C.upsert(man, doc):
        C.write_text(doc, text, local_root)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gutenberg", type=C.pathlib.Path, required=True)
    ap.add_argument("--persuade", type=C.pathlib.Path)
    ap.add_argument("--local-root", type=C.pathlib.Path, default=C.DEFAULT_LOCAL)
    a = ap.parse_args(argv)
    man = C.load_manifest()
    n = add_gutenberg(man, a.gutenberg) + add_speeches(man)
    if a.persuade:
        n += add_persuade(man, a.persuade, a.local_root)
    C.save_manifest(man)
    print(f"{n} human documents added; manifest holds {len(man['documents'])}")


if __name__ == "__main__":
    main()
