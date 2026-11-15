"""Run each model-written checker in third_checker/ over the whole corpus.

    python scripts/compare_third.py CORPUS_DIR OUT_DIR

Plain mode and table mode (the corpus table.json, true rows). Every corpus
witness is valid, and core.py, sc-py and sc-js pass all of them (REPORT.md 3.2),
so any verdict other than PASS here is a false reject by the checker under test.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def run(script, sysp, paths, table):
    out = {}
    for k in range(0, len(paths), 150):  # short command lines on Windows
        part = paths[k:k + 150]
        args = [sys.executable, script, sysp, *part] + (["--table", table] if table else [])
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        got = {}
        for line in r.stdout.splitlines():
            try:
                rec = json.loads(line)
                got[rec["witness"]] = (rec["verdict"], rec.get("reason", ""))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        err = (r.stderr.strip().splitlines() or [""])[-1][:120]
        for q in part:
            out[os.path.basename(q)] = got.get(os.path.basename(q), ("CRASH", err))
    return out


def main(corpus, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    scripts = sorted(glob.glob(os.path.join(REPO, "third_checker", "check3*.py")))
    summary = {}
    rows = [("corpus", "witness", "checker", "mode", "verdict", "reason")]
    for s in scripts:
        name = os.path.splitext(os.path.basename(s))[0]
        counts = {"plain": collections.Counter(), "table": collections.Counter()}
        reasons = collections.Counter()
        for meta in sorted(glob.glob(os.path.join(corpus, "*", "meta.json"))):
            d = os.path.dirname(meta)
            paths = sorted(glob.glob(os.path.join(d, "wits", "*.json")))
            sysp = os.path.join(d, "system.jsonl")
            for mode, table in (("plain", None), ("table", os.path.join(d, "table.json"))):
                for wname, (v, why) in run(s, sysp, paths, table).items():
                    counts[mode][v] += 1
                    if v != "PASS":
                        reasons[f"{mode}: {why}"] += 1
                        rows.append((os.path.basename(d), wname, name, mode, v, why))
        summary[name] = {"plain": dict(counts["plain"]), "table": dict(counts["table"]),
                         "non_pass_reasons": dict(reasons.most_common(10))}
        print(name, json.dumps(summary[name]), flush=True)
    with open(os.path.join(out_dir, "third_checkers.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
    with open(os.path.join(out_dir, "third_checkers_nonpass.csv"), "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(",".join(str(x).replace(",", ";") for x in r) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
