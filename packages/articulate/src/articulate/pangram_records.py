"""Versioned Pangram reference records for the bench corpus.

The bench prints an outside detector's result beside each corpus file as a
reference point. The records never feed a gate, a rule, the editor or any
accept decision. Each record names the text by its SHA-256, the model version
the reference came from and the date it was observed, so anyone holding the
same text can check the claim.

The file is JSON Lines at ``<corpus>/pangram-records.jsonl``. Records are
appended and never rewritten: a new model version adds new records beside the
old ones. A corpus with no records file falls back to the older ``.pangram``
sidecar, shown as "model unrecorded".

This module reads files only. It opens no network connection.
"""
import hashlib
import json
import os

RECORDS_NAME = "pangram-records.jsonl"
REQUIRED = ("schema", "text", "text_sha256", "model", "observed", "source")
UNRECORDED = "unrecorded"


def text_sha256(path):
    """SHA-256 of the file's bytes, as stored on disk."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load(corpus):
    """Every record in the corpus records file, oldest first."""
    path = os.path.join(corpus, RECORDS_NAME)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            missing = [k for k in REQUIRED if k not in rec]
            if missing:
                raise ValueError(f"{RECORDS_NAME} line {n} lacks {missing}")
            out.append(rec)
    return out


def for_text(records, sha):
    """The records whose text hash matches, oldest first."""
    return [r for r in records if r["text_sha256"] == sha]


def result_of(rec):
    """The reference result in a few words."""
    if rec.get("reported"):
        return rec["reported"]
    short = rec.get("prediction_short") or "?"
    frac = rec.get("fraction_ai")
    return f"{short} fraction_ai {frac:.2f}" if isinstance(frac, (int, float)) else short


def describe(rec):
    """One record as "<result> (model <version>, <date>)"."""
    model = rec["model"]
    when = rec["observed"]
    model_txt = "model unrecorded" if model == UNRECORDED else f"Pangram {model}"
    when_txt = "date unrecorded" if when.startswith(UNRECORDED) else when
    return f"{result_of(rec)} ({model_txt}, {when_txt})"


def reference(corpus, path, records=None):
    """The bench's reference text for one corpus file, or ""."""
    recs = load(corpus) if records is None else records
    if recs:
        matched = for_text(recs, text_sha256(path))
        return "; ".join(describe(r) for r in matched)
    side = os.path.splitext(path)[0] + ".pangram"
    if os.path.isfile(side):
        try:
            with open(side, encoding="utf-8") as fh:
                return f"{fh.read().strip()} (model unrecorded, date unrecorded)"
        except OSError:
            return ""
    return ""
