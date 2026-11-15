"""Re-score the bench corpus with a named Pangram model and append the results.

Pangram is an outside reference. Its results are printed beside the bench and
compared with Articulate's findings. They never tune a rule, a gate or the
editor, and nothing here rewrites text.

    python scripts/pangram_rescore.py estimate
    python scripts/pangram_rescore.py score --model pangram-4.1 --max-usd 2.50

`estimate` makes no network call. `score` needs PANGRAM_API_KEY in the
environment and the official SDK (`pip install pangram-sdk`). It sends the
text and the model name only: no file name, no account data. It appends one
record per text to corpus/pangram-records.jsonl and never rewrites an
existing record. A text already scored under the same requested model name
is skipped unless --again is given. Each record keeps the version string the
API returned, so the model behind every result stays on file.

Pricing: Pangram's announcement of 29 July 2026 sets the API at USD 0.05 per
100 words. The estimate rounds each text up to the next 100 words, the
costliest reading of that rule. The key is read from the environment and is
never printed or written.
"""
import argparse
import datetime
import json
import math
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
sys.path.insert(0, str(ROOT / "src"))

from articulate import pangram_records as PR  # noqa: E402

USD_PER_100_WORDS = 0.05
# Third-party posts with no recorded redistribution licence stay local.
NEVER_SEND = {"human/ptacek-tweets.txt"}
WINDOW_KEYS = ("label", "ai_assistance_score", "confidence", "start_index",
               "end_index", "word_count", "humanizer_score", "is_humanized",
               "class_probabilities")
DOC_KEYS = ("prediction_short", "fraction_ai", "fraction_ai_assisted",
            "fraction_human", "headline")


def corpus_texts(corpus=CORPUS):
    """(relative path, absolute path) for every bench text that may be sent."""
    out = []
    for label in ("ai", "human"):
        d = corpus / label
        for p in sorted(d.glob("*")) if d.is_dir() else []:
            rel = f"{label}/{p.name}"
            if p.suffix.lower() in (".txt", ".md") and rel not in NEVER_SEND:
                out.append((rel, p))
    return out


def words(path):
    return len(path.read_text(encoding="utf-8").split())


def estimate(texts):
    """Rows of (rel, words, billed units) and the USD total, rounded up per text."""
    rows = [(rel, words(p), max(1, math.ceil(words(p) / 100))) for rel, p in texts]
    units = sum(r[2] for r in rows)
    return rows, round(units * USD_PER_100_WORDS, 2)


def print_estimate(rows, usd):
    for rel, n, units in rows:
        print(f"{rel:<32} {n:>6} words  {units:>3} x 100-word units")
    total_words = sum(r[1] for r in rows)
    print(f"{len(rows)} texts, {total_words} words, {sum(r[2] for r in rows)} units, "
          f"USD {usd:.2f} at USD {USD_PER_100_WORDS} per 100 words")
    print(f"never sent: {', '.join(sorted(NEVER_SEND))}")


def record_from(rel, path, model, resp, when):
    """One append-only record from an SDK response, window text removed."""
    rec = {"schema": 1, "text": rel, "text_sha256": PR.text_sha256(path),
           "words": words(path), "model": str(resp.get("version") or PR.UNRECORDED),
           "model_requested": model, "observed": when, "source": "pangram api via pangram-sdk"}
    rec.update({k: resp.get(k) for k in DOC_KEYS if k in resp})
    rec["windows"] = [{k: w.get(k) for k in WINDOW_KEYS if k in w}
                      for w in resp.get("windows") or []]
    return rec


def already(records, sha, model_requested):
    return any(r["text_sha256"] == sha and r.get("model_requested") == model_requested
               for r in records)


def score(texts, model, max_usd, again, corpus=CORPUS, client=None):
    rows, usd = estimate(texts)
    if usd > max_usd:
        print(f"estimate USD {usd:.2f} exceeds --max-usd {max_usd:.2f}; nothing sent")
        return 2
    if client is None:
        client = _client()
    records = PR.load(str(corpus))
    when = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    out = corpus / PR.RECORDS_NAME
    sent = 0
    with open(out, "a", encoding="utf-8", newline="\n") as fh:
        for rel, path in texts:
            if not again and already(records, PR.text_sha256(path), model):
                print(f"skip {rel}: already scored with {model}")
                continue
            resp = client.predict(path.read_text(encoding="utf-8"), model=model)
            rec = record_from(rel, path, model, resp, when)
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            sent += 1
            print(f"{rel}: {PR.describe(rec)}")
    print(f"{sent} texts scored, records appended to {out}")
    return 0


def _client():
    if not os.environ.get("PANGRAM_API_KEY"):
        sys.exit("PANGRAM_API_KEY is not set; run `estimate` for the cost, then set a key")
    try:
        from pangram import PangramText
    except ImportError:
        sys.exit("the Pangram SDK is missing: pip install --upgrade pangram-sdk")
    return PangramText(api_key=os.environ["PANGRAM_API_KEY"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    sc = sub.add_parser("score")
    sc.add_argument("--model", required=True, help="model name sent to the API, e.g. pangram-4")
    sc.add_argument("--max-usd", type=float, required=True, help="refuse above this estimate")
    sc.add_argument("--again", action="store_true", help="score texts already scored")
    a = ap.parse_args(argv)
    texts = corpus_texts()
    if a.cmd == "estimate":
        print_estimate(*estimate(texts))
        return 0
    return score(texts, a.model, a.max_usd, a.again)


if __name__ == "__main__":
    sys.exit(main())
