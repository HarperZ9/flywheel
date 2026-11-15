#!/usr/bin/env python
"""Measure three device readouts (antithesis, tricolon, anaphora) against CORE.

Five measurements, all counts with intervals:

  devices   recall and false-positive rate against the hand-labelled fixture
            tests/data/core_devices/passages.json
  metamers  meaning-preserving paraphrase pairs from the fixture: does a
            readout flip when the device is kept (an unjustified flip), and
            does it hold when the device is removed (a stuck readout)
  isomers   the fixture's reorder and quotation pairs, plus a seeded sentence
            shuffle inside each paragraph of the known-provenance corpus
  corpus    fire rate on AI and human documents of the known-provenance
            corpus (the readout as an authorship signal)
  fairness  fire rate on the Liang et al. (2023) TOEFL essays against the
            length-matched first window of the US college essays, and on
            PERSUADE 2.0 English learners against the other students

Every readout is read, never optimised: no rule, threshold or text is changed
from these numbers. Text from licensed corpora never leaves the machine; the
output holds counts only.

Usage:
  python scripts/core_device_readouts.py [--out results.json]
      [--liang DIR] [--local-root DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "src"), str(HERE)]

import core_readouts_lib as L  # noqa: E402
import provenance_common as P  # noqa: E402

FIXTURE = ROOT / "tests" / "data" / "core_devices" / "passages.json"
LIANG = pathlib.Path(os.environ.get("ARTICULATE_LIANG_ESSAYS", "liang-essays"))
DEVICES = ("antithesis", "tricolon", "anaphora")
IMPLS = ("line", "runs")
KEYS = [f"{d}/{i}" for d in DEVICES for i in IMPLS]
SEED = 20261026


def devices(fx):
    items = [{"id": p["id"], "lookalike": p.get("lookalike", False),
              "labels": p["labels"], "read": L.read_all(p["text"])} for p in fx["passages"]]
    out = {}
    for d in DEVICES:
        rows = [{"label": it["labels"][d], "read": it["read"]} for it in items]
        look = [{"label": False, "read": it["read"]} for it in items if it["lookalike"]]
        out[d] = {impl: {**L.confusion(rows, f"{d}/{impl}"),
                         "lookalike_fp": sum(1 for r in look if r["read"][f"{d}/{impl}"]),
                         "lookalikes": len(look)} for impl in IMPLS}
        out[d]["either"] = L.confusion(
            [{"label": r["label"], "read": {"x": r["read"][f"{d}/line"] or r["read"][f"{d}/runs"]}}
             for r in rows], "x")
    out["_misses"] = {k: [it["id"] for it in items
                          if it["labels"][k.split("/")[0]] and not it["read"][k]] for k in KEYS}
    out["_false_alarms"] = {k: [it["id"] for it in items
                                if not it["labels"][k.split("/")[0]] and it["read"][k]] for k in KEYS}
    return out


def pairs(pair_list):
    rows = []
    for p in pair_list:
        ra, rb = L.read_all(p["a"]), L.read_all(p["b"])
        for impl in IMPLS:
            k = f"{p['device']}/{impl}"
            rows.append({"id": p["id"], "readout": k, "device_kept": p["device_kept"],
                         "a": ra[k], "b": rb[k], "flip": ra[k] != rb[k]})
    kept = [r for r in rows if r["device_kept"]]
    gone = [r for r in rows if not r["device_kept"]]
    return {"rows": rows,
            "kept_pairs_read": len(kept),
            "kept_flips": sum(r["flip"] for r in kept),
            "kept_both_miss": sum(1 for r in kept if not r["a"] and not r["b"]),
            "removed_pairs_read": len(gone),
            "removed_stuck_on_b": sum(1 for r in gone if r["b"])}


def shuffle_paragraphs(text, rng):
    paras = re.split(r"\n\s*\n", text)
    out = []
    for para in paras:
        sents = L.checkext.detector.split_sentences(" ".join(para.split()))
        rng.shuffle(sents)
        out.append(" ".join(sents))
    return "\n\n".join(out)


def load_docs(local_root):
    docs = []
    for doc in P.load_manifest()["documents"]:
        try:
            text = P.read_checked(doc, local_root)
        except (OSError, ValueError) as exc:
            print(f"skip {doc['id']}: {exc}", file=sys.stderr)
            continue
        if text is None:
            print(f"skip {doc['id']}: missing or hash mismatch", file=sys.stderr)
            continue
        docs.append((doc, text))
    return docs


def corpus(docs):
    reads = [(doc, L.read_all(text)) for doc, text in docs]
    out = {}
    for k in KEYS + ["filler-intensifier/line"]:
        row = {}
        for cls in ("ai", "human", "mixed"):
            sel = [r for d, r in reads if d["class"] == cls]
            row[cls] = {"k": sum(r[k] for r in sel), "n": len(sel),
                        "rate": L.wilson(sum(r[k] for r in sel), len(sel))}
        row["human_by_genre"] = {}
        for g in sorted({d["genre"] for d, _ in reads if d["class"] == "human"}):
            sel = [r for d, r in reads if d["class"] == "human" and d["genre"] == g]
            row["human_by_genre"][g] = f"{sum(r[k] for r in sel)}/{len(sel)}"
        out[k] = row
    return out, reads


def isomer_shuffle(docs, reads):
    rng = random.Random(SEED)
    changed = {k: 0 for k in KEYS}
    for (doc, text), (_, before) in zip(docs, reads):
        after = L.read_all(shuffle_paragraphs(text, rng))
        for k in KEYS:
            changed[k] += before[k] != after[k]
    return {"documents": len(docs), "readout_changed": changed}


def _dir_reads(path):
    files = sorted(pathlib.Path(path).glob("*.txt"))
    return [L.read_all(f.read_text(encoding="utf-8", errors="replace")) for f in files]


def _compare(name_a, a, name_b, b, keys):
    out = {}
    for k in keys:
        ka, kb = sum(r[k] for r in a), sum(r[k] for r in b)
        row = {name_a: f"{ka}/{len(a)}", name_b: f"{kb}/{len(b)}",
               "diff": L.newcombe(ka, len(a), kb, len(b))}
        if k == "filler-intensifier/line":
            ca = [(r["_counts"]["filler-intensifier"], r["_words"]) for r in a]
            cb = [(r["_counts"]["filler-intensifier"], r["_words"]) for r in b]
            row["per1k_ratio"] = L.rate_ratio_boot(ca, cb)
        out[k] = row
    return out


def fairness(liang, reads_by_doc):
    keys = KEYS + ["filler-intensifier/line"]
    out = {}
    if pathlib.Path(liang).is_dir():
        toefl = _dir_reads(pathlib.Path(liang) / "TOEFL_real_91")
        college = _dir_reads(pathlib.Path(liang) / "CollegeEssay_real_70.win0")
        abstracts = _dir_reads(pathlib.Path(liang) / "CS224N_real_145.win0")
        out["toefl_vs_college_win0"] = _compare("toefl", toefl, "college", college, keys)
        out["toefl_vs_cs224n_win0"] = _compare("toefl", toefl, "cs224n", abstracts, keys)
    ell = [r for d, r in reads_by_doc if d["class"] == "human"
           and d.get("group", {}).get("ell_status") == "Yes"]
    other = [r for d, r in reads_by_doc if d["class"] == "human"
             and d.get("group", {}).get("ell_status") == "No"]
    if ell and other:
        out["persuade_ell_vs_other"] = _compare("ell", ell, "other", other, keys)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--liang", default=str(LIANG))
    ap.add_argument("--local-root", default=str(P.DEFAULT_LOCAL))
    a = ap.parse_args(argv)
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    docs = load_docs(pathlib.Path(a.local_root))
    corp, reads = corpus(docs)
    result = {
        "ruleset": L.checkext.detector.ruleset_fingerprint(),
        "devices": devices(fx),
        "metamers": pairs(fx["metamer_pairs"]),
        "isomers": {"pairs": pairs(fx["isomer_pairs"]),
                    "sentence_shuffle": isomer_shuffle(docs, reads)},
        "corpus": corp,
        "fairness": fairness(a.liang, reads),
    }
    text = json.dumps(result, indent=1, default=str)
    if a.out:
        pathlib.Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
