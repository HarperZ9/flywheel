"""False-accept controls. Every mutant must be rejected (FAIL or MALFORMED) by
sc-py, sc-js and core.py; every positive control must PASS.

    python scripts/controls.py BOOTLOOPS_ROOT CORPUS_DIR OUT_DIR [SEED]

Control families (seed published in the output):
  M1 coef_flip      one c[m] -> c[m]+1 mod p
  M2 coef_drop      one c entry removed
  M3 coef_extra     one extra c entry on a column outside the row's support
  M4 prime_change   p -> the other corpus prime (system file unchanged)
  M5 lam_flip       one lam value +1 mod p
  M6 lam_drop       one lam entry removed
  M7 target_swap    target.col replaced by another witness's target
  M8 row_alter      one value in a row the witness uses is changed (new system file)
  X1 exhibit_class  valid witness + claimed table row with one wrong entry, the same
                    integer error at both primes (reconstruction of the wrong-table
                    exhibit class; the banked exhibit itself is not shipped)
  X0 exhibit_ctrl   valid witness + true table row (positive control, must PASS)
  N1 row_shuffle    system rows permuted (non-identity on used rows)
  N2 lam_permute    lam values permuted among lam indices (non-identity)
  N3 noop_check     dummy "accept-all" and "reject-all" checkers run through the
                    same harness; the harness must score both as failing
"""
from __future__ import annotations

import copy
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkers import core_py, sc_js, sc_py  # noqa: E402

PRIMES = [2147483647, 2147483629]
REJECT = {"FAIL", "MALFORMED"}


def _load(q):
    with open(q, encoding="utf-8") as fh:
        return json.load(fh)


def _dump(obj, q):
    with open(q, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, sort_keys=True)


def _rows(sysj):
    with open(sysj, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def _write_rows(rows, q):
    with open(q, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def witness_mutants(rng, w, others, p_other):
    """Yield (kind, mutated witness) for M1..M7 and N2."""
    p = w["p"]
    cks = sorted(w["c"])
    if cks:
        m = copy.deepcopy(w); k = rng.choice(cks)  # noqa: E702
        m["c"][k] = (int(m["c"][k]) + 1) % p
        yield "M1_coef_flip", m
        m = copy.deepcopy(w); del m["c"][rng.choice(cks)]  # noqa: E702
        yield "M2_coef_drop", m
    m = copy.deepcopy(w)
    m["c"][str(10**9 + rng.randrange(10**6))] = rng.randrange(1, p)
    yield "M3_coef_extra", m
    m = copy.deepcopy(w); m["p"] = p_other  # noqa: E702
    yield "M4_prime_change", m
    n = len(w["lam"]["idx"])
    if n:
        m = copy.deepcopy(w); j = rng.randrange(n)  # noqa: E702
        m["lam"]["val"][j] = (int(m["lam"]["val"][j]) + 1) % p
        yield "M5_lam_flip", m
        m = copy.deepcopy(w); j = rng.randrange(n)  # noqa: E702
        del m["lam"]["idx"][j]; del m["lam"]["val"][j]  # noqa: E702
        yield "M6_lam_drop", m
    tgt = [o for o in others if o != w["target"]["col"]]
    if tgt:
        m = copy.deepcopy(w); m["target"]["col"] = rng.choice(tgt)  # noqa: E702
        yield "M7_target_swap", m
    vals = list(w["lam"]["val"])
    if n >= 2 and len(set(vals)) > 1:
        perm = vals[:]
        while perm == vals:
            rng.shuffle(perm)
        m = copy.deepcopy(w); m["lam"]["val"] = perm  # noqa: E702
        yield "N2_lam_permute", m


def run_all(bl_root, sysj, paths, table=None):
    return {"sc_py": sc_py(sysj, paths, table), "sc_js": sc_js(sysj, paths, table),
            "core": core_py(bl_root, sysj, paths, table)}


def main(bl_root, root, out, seed=20261002, per_corpus=12):
    rng = random.Random(seed)
    mdir = os.path.join(out, "mutants")
    os.makedirs(mdir, exist_ok=True)
    records = []  # (kind, corpus, file, expected, {checker: verdict})

    def score(kind, corpus, sysj, files, expected, table=None):
        res = run_all(bl_root, sysj, files, table)
        for q in files:
            k = os.path.basename(q)
            vv = {c: (r[k][0] if r is not None else "n/a") for c, r in res.items()}
            records.append({"kind": kind, "corpus": corpus, "file": k,
                            "expected": expected, "verdicts": vv})

    for d in sorted(glob.glob(os.path.join(root, "*", "meta.json"))):
        d = os.path.dirname(d)
        name = os.path.basename(d)
        sysj = os.path.join(d, "system.jsonl")
        paths = sorted(glob.glob(os.path.join(d, "wits", "*.json")))
        sample = rng.sample(paths, min(per_corpus, len(paths)))
        wits = [_load(q) for q in sample]
        targets = [_load(q)["target"]["col"] for q in paths]
        p = wits[0]["p"]
        p_other = [x for x in PRIMES if x != p][0]
        cdir = os.path.join(mdir, name)
        os.makedirs(cdir, exist_ok=True)
        files = []
        for q, w in zip(sample, wits):
            for kind, m in witness_mutants(rng, w, targets, p_other):
                f = os.path.join(cdir, f"{kind}__{os.path.basename(q)}")
                _dump(m, f)
                files.append((kind, f))
        for kind in sorted({k for k, _ in files}):
            score(kind, name, sysj, [f for k, f in files if k == kind], "reject")
        # M8 row_alter and N1 row_shuffle need their own system files
        rows = _rows(sysj)
        for i, (q, w) in enumerate(zip(sample[:4], wits[:4])):
            used = [int(j) for j, v in zip(w["lam"]["idx"], w["lam"]["val"]) if int(v) % p]
            if not used:
                continue
            r2 = copy.deepcopy(rows)
            j = rng.choice(used)
            col = rng.choice(sorted(r2[j]))
            r2[j][col] = (int(r2[j][col]) + 1) % p
            s2 = os.path.join(cdir, f"M8_row_alter_{i}.jsonl")
            _write_rows(r2, s2)
            score("M8_row_alter", name, s2, [q], "reject")
        perm = list(range(len(rows)))
        while True:
            rng.shuffle(perm)
            if all(any(perm[int(j)] != int(j) for j in _load(q)["lam"]["idx"]) for q in sample):
                break
        s3 = os.path.join(cdir, "N1_row_shuffle.jsonl")
        _write_rows([rows[perm[k]] for k in range(len(rows))], s3)
        score("N1_row_shuffle", name, s3, sample, "reject")
        # X0 / X1: exhibit-class reconstruction in table mode
        with open(os.path.join(d, "table.json"), encoding="utf-8") as fh:
            true_table = json.load(fh)
        score("X0_exhibit_ctrl_true_table", name, sysj, sample, "pass", true_table)
        wrong = copy.deepcopy(true_table)
        for w in wits:
            row = wrong.get(str(w["target"]["col"]))
            if row:
                k = sorted(row)[0]
                delta = 1 + (int(w["target"]["col"]) % 7)  # same integer error at both primes
                row[k] = (int(row[k]) + delta) % p
        score("X1_exhibit_class_wrong_table", name, sysj, sample, "reject", wrong)
        print(name, "controls done", flush=True)

    # N3: dummy checkers through the same scoring rule
    def scored_ok(r, checker_verdict):
        v = checker_verdict
        return (v == "PASS") if r["expected"] == "pass" else (v in REJECT)

    summary = {"seed": seed, "per_corpus_sample": per_corpus, "by_kind": {}}
    for r in records:
        s = summary["by_kind"].setdefault(r["kind"], {"n": 0, "expected": r["expected"],
                                                      "sc_py_ok": 0, "sc_js_ok": 0, "core_ok": 0,
                                                      "sc_js_na": 0})
        s["n"] += 1
        for c in ("sc_py", "core"):
            s[f"{c}_ok"] += scored_ok(r, r["verdicts"][c])
        if r["verdicts"]["sc_js"] == "n/a":
            s["sc_js_na"] += 1
        else:
            s["sc_js_ok"] += scored_ok(r, r["verdicts"]["sc_js"])
    n_total = len(records)
    summary["n_cases"] = n_total
    summary["N3_accept_all_dummy_ok"] = sum(scored_ok(r, "PASS") for r in records)
    summary["N3_reject_all_dummy_ok"] = sum(scored_ok(r, "FAIL") for r in records)
    summary["N3_harness_flags_dummies"] = (summary["N3_accept_all_dummy_ok"] < n_total and
                                           summary["N3_reject_all_dummy_ok"] < n_total)
    summary["failures"] = [r for r in records
                           if not all(scored_ok(r, v) for c, v in r["verdicts"].items() if v != "n/a")]
    with open(os.path.join(out, "controls.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({**summary, "records": records}, fh, indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, indent=1, sort_keys=True))
    print("n_failures", len(summary["failures"]))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 20261002)
