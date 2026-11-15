"""Differential fuzzer: every checker on the same seeded inputs, disagreements minimized.

    python scripts/fuzz.py BOOTLOOPS_ROOT OUT_DIR [--seed N] [--random N] [--bases N]

Checkers: sc-py, sc-js, core.py (library verify_row), and each third_checker/check3*.py.
A verdict is classed A (PASS), R (FAIL or MALFORMED) or C (crash, no verdict line).
A case is a disagreement when two applicable checkers give different classes.
Phase 1 runs every mutation alone on every base; phase 2 runs random stacks of
2 to 3 mutations. Each disagreement signature is minimized once: mutations are
dropped while the signature holds, then the base is shrunk to 2 rows and 3 columns.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from checkers import core_py, sc_py  # noqa: E402
from fuzz_cases import MUTATIONS, build  # noqa: E402

CLS = {"PASS": "A", "FAIL": "R", "MALFORMED": "R"}


def ext_checkers():
    out = {"sc_js": ["node", os.path.join(REPO, "js", "check.mjs")]}
    for q in sorted(glob.glob(os.path.join(REPO, "third_checker", "check3*.py"))):
        out[os.path.splitext(os.path.basename(q))[0]] = [sys.executable, q]
    return out


def run_ext(cmd, sysp, wits, table_path):
    if table_path is not None and cmd[0] == "node":
        return {os.path.basename(w): ("n/a", "") for w in wits}
    args = cmd + [sysp, *wits] + (["--table", table_path] if table_path else [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {os.path.basename(w): ("C", "timeout") for w in wits}
    got = {}
    for line in r.stdout.splitlines():
        try:
            rec = json.loads(line)
            got[rec["witness"]] = (CLS.get(rec["verdict"], "C"), rec.get("reason", ""))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    tail = (r.stderr or "").strip().splitlines()[-1:] or [""]
    return {os.path.basename(w): got.get(os.path.basename(w), ("C", f"rc {r.returncode}: {tail[0][:160]}"))
            for w in wits}


def run_group(bl, d, sys_text, items, ext):
    """items: list of (case_key, witness_text, table). Returns {case_key: {checker: (cls, reason)}}."""
    os.makedirs(d, exist_ok=True)
    sysp = os.path.join(d, "system.jsonl")
    with open(sysp, "w", encoding="utf-8", newline="") as fh:
        fh.write(sys_text)
    res = {k: {} for k, _, _ in items}
    plain, tabled = [], []
    for k, wtext, table in items:
        wp = os.path.join(d, f"w_{k}.json")
        with open(wp, "w", encoding="utf-8", newline="") as fh:
            fh.write(wtext)
        (tabled if table else plain).append((k, wp, table))
    jobs = [(plain, None)] + [([x], x[2]) for x in tabled]
    for group, table in jobs:
        if not group:
            continue
        paths = [wp for _, wp, _ in group]
        tpath = None
        if table:
            tpath = os.path.join(d, f"table_{group[0][0]}.json")
            with open(tpath, "w", encoding="utf-8") as fh:
                json.dump(table, fh)
        for name, fn in (("sc_py", lambda: sc_py(sysp, paths, table)),
                         ("core", lambda: core_py(bl, sysp, paths, table))):
            try:
                out = fn()
                for k, wp, _ in group:
                    v = out[os.path.basename(wp)]
                    res[k][name] = (CLS.get(v[0], "C"), str(v[1])[:160])
            except Exception as exc:  # recorded as a crash, never hidden
                for k, _, _ in group:
                    res[k][name] = ("C", f"{type(exc).__name__}: {exc}"[:160])
        for name, cmd in ext.items():
            out = run_ext(cmd, sysp, paths, tpath)
            for k, wp, _ in group:
                v = out[os.path.basename(wp)]
                if v[0] == "C" and len(paths) > 1:  # one crash ends a batch: re-run alone
                    v = run_ext(cmd, sysp, [wp], tpath)[os.path.basename(wp)]
                res[k][name] = v
    return res


def signature(v):
    return tuple(sorted((n, c) for n, (c, _) in v.items() if c != "n/a"))


def disagree(v):
    return len({c for c, _ in v.values() if c != "n/a"}) > 1


def run_cases(bl, work, cases, ext, seed):
    """cases: list of (key, base_id, case_id, muts, size). Groups by system bytes."""
    groups = {}
    for key, base_id, case_id, muts, size in cases:
        s, w, t = build(seed, base_id, case_id, muts, size)
        h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
        groups.setdefault(h, (s, []))[1].append((key, w, t))
    out = {}
    for h, (s, items) in groups.items():
        out.update(run_group(bl, os.path.join(work, h), s, items, ext))
    return out


def minimize(bl, work, seed, case, sig, ext):
    key, base_id, case_id, muts, size = case
    muts = list(muts)

    def same(m, sz):
        r = run_cases(bl, work, [("min", base_id, case_id, m, sz)], ext, seed)["min"]
        return signature(r) == sig and disagree(r)
    changed = True
    while changed and len(muts) > 1:
        changed = False
        for j in range(len(muts)):
            trial = muts[:j] + muts[j + 1:]
            if same(trial, size):
                muts, changed = trial, True
                break
    for sz in ((2, 3), (2, 4), (3, 4)):
        if same(muts, sz):
            size = sz
            break
    return base_id, case_id, muts, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bl_root")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--bases", type=int, default=20)
    ap.add_argument("--random", type=int, default=2000)
    a = ap.parse_args()
    work = os.path.join(a.out, "_work")
    shutil.rmtree(work, ignore_errors=True)
    ext = ext_checkers()
    names = sorted(MUTATIONS)
    cases = [(f"s{b}_{m}", b, f"s{b}_{m}", [m], None) for m in names for b in range(a.bases)]
    rng = random.Random(a.seed)
    for j in range(a.random):
        cases.append((f"r{j}", rng.randrange(a.bases), f"r{j}", rng.sample(names, rng.randint(2, 3)), None))
    cases += [(f"b{b}", b, f"b{b}", [], None) for b in range(a.bases)]  # unmutated controls
    res = run_cases(a.bl_root, work, cases, ext, a.seed)
    by_key = {c[0]: c for c in cases}
    buckets, pair = {}, {}
    checkers = sorted({n for v in res.values() for n in v})
    for k, v in res.items():
        for x in checkers:
            for y in checkers:
                if x < y and v.get(x, ("n/a",))[0] != "n/a" and v.get(y, ("n/a",))[0] != "n/a":
                    pair.setdefault(f"{x}|{y}", [0, 0])
                    pair[f"{x}|{y}"][0] += 1
                    pair[f"{x}|{y}"][1] += v[x][0] != v[y][0]
        if disagree(v):
            buckets.setdefault(signature(v), []).append(k)
    report = {"seed": a.seed, "n_cases": len(cases), "checkers": checkers,
              "controls_unmutated": {k: res[k] for k in res if k.startswith("b")},
              "pairwise_disagreements": {k: {"cases": n, "disagree": d} for k, (n, d) in sorted(pair.items())},
              "buckets": []}
    repro_dir = os.path.join(a.out, "repros")
    shutil.rmtree(repro_dir, ignore_errors=True)
    for j, (sig, keys) in enumerate(sorted(buckets.items(), key=lambda kv: -len(kv[1]))):
        first = by_key[sorted(keys)[0]]
        base_id, case_id, muts, size = minimize(a.bl_root, work, a.seed, first, sig, ext)
        s, w, t = build(a.seed, base_id, case_id, muts, size)
        d = os.path.join(repro_dir, f"B{j:03d}")
        os.makedirs(d, exist_ok=True)
        for fn, txt in (("system.jsonl", s), ("w_case.json", w)):
            with open(os.path.join(d, fn), "w", encoding="utf-8", newline="") as fh:
                fh.write(txt)
        if t:
            with open(os.path.join(d, "table.json"), "w", encoding="utf-8") as fh:
                json.dump(t, fh)
        verdicts = run_cases(a.bl_root, work, [("x", base_id, case_id, muts, size)], ext, a.seed)["x"]
        mut_kinds = sorted({m for k in keys for m in by_key[k][3]})
        report["buckets"].append({"id": f"B{j:03d}", "signature": dict(sig), "n_cases": len(keys),
                                  "min_mutations": muts, "min_size": size, "base_id": base_id,
                                  "case_id": case_id, "repro_verdicts": verdicts,
                                  "mutations_seen": mut_kinds[:40]})
        print(f"B{j:03d}", len(keys), dict(sig), muts, flush=True)
    with open(os.path.join(a.out, "cases.csv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("case,base,mutations," + ",".join(checkers) + "\n")
        for k in sorted(res):
            _, base_id, _, muts, _ = by_key[k]
            fh.write(f"{k},{base_id},{'+'.join(muts)}," +
                     ",".join(res[k].get(x, ("n/a",))[0] for x in checkers) + "\n")
    single = {}
    for k, v in res.items():
        if k.startswith("s"):
            m = by_key[k][3][0]
            for x in checkers:
                cls = v.get(x, ("n/a",))[0]
                single.setdefault(m, {}).setdefault(x, {}).setdefault(cls, 0)
                single[m][x][cls] += 1
    report["single_mutation_classes"] = single
    with open(os.path.join(a.out, "fuzz.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(report["pairwise_disagreements"], indent=1))


if __name__ == "__main__":
    main()
