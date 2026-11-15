"""Lean 4 kernel check of RECEIPT identities over ZMod p, plus scale limits.

    python scripts/lean_run.py CORPUS_DIR OUT_DIR [--seed N] [--per-corpus K] [--scale]

Legs:
  L1 corpus sample  K seeded witnesses per corpus, column form by `decide +kernel`
                    and linear form by `ring_nf; reduce_mod_char` (small rows only)
  L2 negative       corrupted witnesses (one coefficient flipped); each module must FAIL
  L3 scale series   artificial valid witnesses of T total row terms, one module per
                    (T, tactic); a tactic's series stops at its first failure or timeout
Each module that builds is replayed by `leanchecker` in a fresh process, and its
`#print axioms` lines are checked against {propext, Classical.choice, Quot.sound}.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LEAN_DIR = os.path.join(REPO, "lean")
GEN = os.path.join(LEAN_DIR, "ReceiptLean", "Gen")
OLEAN = os.path.join(LEAN_DIR, ".lake", "build", "lib", "lean", "ReceiptLean", "Gen")
sys.path.insert(0, os.path.join(REPO, "src"))
from second_checker.checker import Witness, parse_row, parse_witness  # noqa: E402
from second_checker.lean_emit import column_form, lean_file, linear_form, theorem_name  # noqa: E402

ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
P = 2147483647


def lean_env():
    r = subprocess.run(["lake", "env", "printenv", "LEAN_PATH"], cwd=LEAN_DIR,
                       capture_output=True, text=True, check=True)
    env = dict(os.environ)
    env["LEAN_PATH"] = r.stdout.strip()
    return env


def build(module, src, env, timeout):
    """Compile one module with lean.exe directly. Returns a result dict."""
    os.makedirs(GEN, exist_ok=True)
    os.makedirs(OLEAN, exist_ok=True)
    path = os.path.join(GEN, f"{module}.lean")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(src)
    olean = os.path.join(OLEAN, f"{module}.olean")
    if os.path.exists(olean):
        os.remove(olean)
    t0 = time.perf_counter()
    try:
        r = subprocess.run(["lean", "-o", olean, path], cwd=LEAN_DIR, env=env,
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        out, rc, to = r.stdout + r.stderr, r.returncode, False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        rc, to = None, True
    wall = time.perf_counter() - t0
    axioms = re.findall(r"depends on axioms: \[([^\]]*)\]", out)
    ax_set = {a.strip() for line in axioms for a in line.split(",") if a.strip()}
    cum = {}
    for name in ("type checking", "tactic execution", "elaboration"):
        m = re.search(rf"^\t{name} ([\d.]+)(ms|s)$", out, re.M)
        if m:
            cum[name] = float(m.group(1)) * (1000 if m.group(2) == "s" else 1)
    errors = [ln for ln in out.splitlines() if ": error:" in ln or ln.startswith("error")]
    res = {"module": module, "ok": rc == 0 and not to, "rc": rc, "timeout": to,
           "wall_s": round(wall, 2), "cumulative_ms": cum, "axioms": sorted(ax_set),
           "axioms_ok": ax_set <= ALLOWED_AXIOMS, "errors": errors[:5],
           "uses_forbidden": bool(re.search(r"native_decide|implemented_by|sorry", src))}
    if res["ok"]:
        t1 = time.perf_counter()
        r2 = subprocess.run(["leanchecker", f"ReceiptLean.Gen.{module}"], cwd=LEAN_DIR, env=env,
                            capture_output=True, text=True, timeout=3600)
        res["leanchecker_rc"] = r2.returncode
        res["leanchecker_s"] = round(time.perf_counter() - t1, 2)
        res["leanchecker_tail"] = (r2.stdout + r2.stderr)[-300:]
    return res


def load_rows(sysj, p):
    with open(sysj, encoding="utf-8") as fh:
        return [parse_row(json.loads(x), p) for x in fh if x.strip()]


def n_terms(rows, w):
    return sum(len(rows[i]) for i in w.lam)


def artificial(seed, T, k=10, p=P):
    """A valid witness with T = n*k row terms (k columns per row)."""
    rng = random.Random(seed)
    n = max(1, T // k)
    pool = max(2 * k, T // 5)
    rows = [{c: rng.randrange(1, p) for c in rng.sample(range(pool), k)} for _ in range(n)]
    lam = {i: rng.randrange(1, p) for i in range(n)}
    r = {}
    for i, li in lam.items():
        for c, v in rows[i].items():
            r[c] = (r.get(c, 0) + li * v) % p
    r = {c: v for c, v in r.items() if v}
    t = min(r)
    inv = pow(r[t], -1, p)
    lam = {i: li * inv % p for i, li in lam.items()}
    c = {m: (-v * inv) % p for m, v in r.items() if m != t}
    return rows, Witness(p=p, target=t, c=c, lam=lam, n_rows=n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--per-corpus", type=int, default=2)
    ap.add_argument("--rows-per-module", type=int, default=12)
    ap.add_argument("--linear-max-terms", type=int, default=200)
    ap.add_argument("--scale", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--only-scale", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    env = lean_env()
    rng = random.Random(a.seed)
    report = {"seed": a.seed, "L1": [], "L2": [], "L3": [], "sample": []}

    base = build("Baseline", lean_file([], []), env, a.timeout)
    report["baseline_import_only"] = base
    print("baseline", base["wall_s"], flush=True)
    if a.only_scale:
        a.scale = True
    # L1: corpus sample
    picked = []
    if a.only_scale:
        a.corpus = os.path.join(a.out, "_no_corpus")
    for d in sorted(glob.glob(os.path.join(a.corpus, "*", "meta.json"))):
        d = os.path.dirname(d)
        paths = sorted(glob.glob(os.path.join(d, "wits", "*.json")))
        for q in rng.sample(paths, min(a.per_corpus, len(paths))):
            with open(q, encoding="utf-8") as fh:
                w = parse_witness(json.load(fh))
            picked.append((os.path.basename(d), q, w))
    rows_cache = {}
    blocks, names, lin_blocks, lin_names = [], [], [], []
    for corpus, q, w in picked:
        key = (corpus, w.p)
        if key not in rows_cache:
            rows_cache[key] = load_rows(os.path.join(a.corpus, corpus, "system.jsonl"), w.p)
        rows = rows_cache[key]
        tag = f"{corpus}_{w.target}"
        blocks.append(column_form(tag, rows, w)); names.append(theorem_name(tag) + "_col")  # noqa: E702
        nt = n_terms(rows, w)
        report["sample"].append({"corpus": corpus, "witness": os.path.basename(q), "terms": nt,
                                 "lam_nnz": len(w.lam), "linear_form": nt <= a.linear_max_terms})
        if nt <= a.linear_max_terms:
            lin_blocks.append(linear_form(tag, rows, w)); lin_names.append(theorem_name(tag) + "_lin")  # noqa: E702
    k = a.rows_per_module
    for j in range(0, len(blocks), k):
        res = build(f"Sample{j // k:02d}", lean_file(blocks[j:j + k], names[j:j + k]), env, a.timeout)
        res["n_rows"] = len(blocks[j:j + k]); res["form"] = "column/decide +kernel"  # noqa: E702
        report["L1"].append(res); print("L1", res["module"], res["ok"], res["wall_s"], flush=True)  # noqa: E702
    for j in range(0, len(lin_blocks), k):
        res = build(f"SampleLin{j // k:02d}", lean_file(lin_blocks[j:j + k], lin_names[j:j + k]), env, a.timeout)
        res["n_rows"] = len(lin_blocks[j:j + k]); res["form"] = "linear/ring_nf+reduce_mod_char"  # noqa: E702
        report["L1"].append(res); print("L1", res["module"], res["ok"], res["wall_s"], flush=True)  # noqa: E702

    # L2: negative controls, one module each (must fail)
    for j, (corpus, q, w) in enumerate(picked[:3]):
        rows = rows_cache[(corpus, w.p)]
        bad_c = dict(w.c)
        m = sorted(bad_c)[0]
        bad_c[m] = (bad_c[m] + 1) % w.p
        bad = Witness(p=w.p, target=w.target, c=bad_c, lam=w.lam, n_rows=w.n_rows)
        tag = f"neg_{corpus}_{w.target}"
        for form, src in (("column", column_form(tag, rows, bad)), ("linear", linear_form(tag, rows, bad))):
            nm = theorem_name(tag) + ("_col" if form == "column" else "_lin")
            res = build(f"Neg{j:02d}{form.capitalize()}", lean_file([src], [nm]), env, a.timeout)
            res["form"] = form; res["expected"] = "fail"  # noqa: E702
            report["L2"].append(res); print("L2", res["module"], "built" if res["ok"] else "rejected", flush=True)  # noqa: E702

    # L3: scale series
    if a.scale:
        tactics = [("mono_decide_kernel", "mono", "decide +kernel"),
                   ("decide_kernel", "col", "decide +kernel"), ("decide", "col", "decide"),
                   ("norm_num", "col", "norm_num"), ("ring", "lin", None)]
        sizes = [10, 100, 300, 1000, 3000, 10000, 30000, 100000]
        for tname, form, tac in tactics:
            for T in sizes:
                rows, w = artificial(a.seed + T, T)
                tag = f"scale_{tname}_{T}"
                if form == "lin":
                    src = linear_form(tag, rows, w)
                else:
                    src = column_form(tag, rows, w, tactic=tac, split=(form == "col"))
                nm = theorem_name(tag) + ("_lin" if form == "lin" else "_col")
                res = build(f"Scale_{tname}_{T}", lean_file([src], [nm]), env, a.timeout)
                res.update(tactic=tname, terms=T, lam_nnz=len(w.lam), n_cols=len(w.c) + 1)
                report["L3"].append(res)
                print("L3", tname, T, res["ok"], res["wall_s"], res.get("timeout"), flush=True)
                if not res["ok"]:
                    break
    with open(os.path.join(a.out, "lean.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
