"""Row-by-row agreement between sc-py, sc-js and BootLoops core.py.

    python scripts/compare.py BOOTLOOPS_ROOT CORPUS_DIR OUT_DIR

Writes OUT_DIR/agreement.csv (one line per witness) and OUT_DIR/agreement.json
(totals, disagreements, timing). Two passes per corpus: plain, and table mode
against the corpus's true table.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkers import core_py, sc_js, sc_py  # noqa: E402


def corpora(root):
    return sorted(d for d in glob.glob(os.path.join(root, "*")) if
                  os.path.isfile(os.path.join(d, "meta.json")))


def main(bl_root, root, out):
    os.makedirs(out, exist_ok=True)
    lines, disagreements = [], []
    t = {"sc_py": [], "sc_js": [], "core": []}
    for d in corpora(root):
        name = os.path.basename(d)
        sysj = os.path.join(d, "system.jsonl")
        paths = sorted(glob.glob(os.path.join(d, "wits", "*.json")))
        with open(os.path.join(d, "table.json"), encoding="utf-8") as fh:
            table = json.load(fh)
        a, b, c = sc_py(sysj, paths), sc_js(sysj, paths), core_py(bl_root, sysj, paths)
        ta, tc = sc_py(sysj, paths, table), core_py(bl_root, sysj, paths, table)
        for q in paths:
            k = os.path.basename(q)
            row = {"corpus": name, "witness": k,
                   "sc_py": a[k][0], "sc_js": b[k][0], "core": c[k][0],
                   "table_sc_py": ta[k][0], "table_core": tc[k][0]}
            lines.append(row)
            t["sc_py"].append(a[k][2]); t["sc_js"].append(b[k][2]); t["core"].append(c[k][2])  # noqa: E702
            if len({row["sc_py"], row["sc_js"], row["core"]}) > 1 or row["table_sc_py"] != row["table_core"]:
                disagreements.append({**row, "reasons": [a[k][1], b[k][1], c[k][1], ta[k][1], tc[k][1]]})
        print(f"{name}: {len(paths)} witnesses", flush=True)
    with open(os.path.join(out, "agreement.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(lines[0]), lineterminator="\n")
        wr.writeheader()
        wr.writerows(lines)

    def count(col, v):
        return sum(r[col] == v for r in lines)

    summary = {
        "n_witnesses": len(lines),
        "n_corpora": len({r["corpus"] for r in lines}),
        "plain": {c: {v: count(c, v) for v in ("PASS", "FAIL", "MALFORMED", "CRASH")}
                  for c in ("sc_py", "sc_js", "core")},
        "table_mode": {c: {v: count(c, v) for v in ("PASS", "FAIL", "MALFORMED", "CRASH")}
                       for c in ("table_sc_py", "table_core")},
        "n_disagreements": len(disagreements),
        "disagreements": disagreements,
        "ms_per_row_mean": {k: round(1000 * statistics.mean(v), 4) for k, v in t.items()},
        "ms_per_row_max": {k: round(1000 * max(v), 4) for k, v in t.items()},
        "note": "sc_js time is subprocess wall time divided by batch size, so it includes node start-up.",
    }
    with open(os.path.join(out, "agreement.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in summary.items() if k != "disagreements"}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
