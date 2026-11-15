"""Build the witness corpus the two checkers are compared on.

BootLoops publishes no witness files (searched: all six public repos and
bootloops.ai on 2026-10-02). Witnesses here are therefore EMITTED, by:
  - "bl-receipt": BootLoops tools/trust/receipt/emitter.py (Wiedemann retrofit)
  - "bl-winnow-retrofit" / "bl-winnow-native": BootLoops Winnow (ibplapper)
  - "sc-synth": this repo's own Gauss-Jordan generator (src/second_checker/synth.py)
over (a) the fixture in BootLoops' own test_core.py and (b) seeded integer
systems reduced at two primes. Usage:
    python scripts/gen_corpus.py BOOTLOOPS_ROOT OUT_DIR
"""
from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from second_checker.synth import solve_witnesses, witness_json  # noqa: E402

PRIMES = [2147483647, 2147483629]


def int_system(seed, n_int, n_master, n_extra, density=3, mix=2, cmax=50):
    """Integer rows (over Z): reduction rows mixed by small integer multiples."""
    rng = random.Random(seed)
    masters = list(range(n_int - n_master, n_int))
    base, truth = [], {}
    for t in range(n_int - n_master):
        c = {m: rng.randint(1, cmax) * rng.choice((1, -1))
             for m in rng.sample(masters, min(density, n_master))}
        truth[t] = c
        row = {t: 1, **{m: -v for m, v in c.items()}}
        base.append(row)

    def add(dst, src, a):
        for k, v in src.items():
            x = dst.get(k, 0) + a * v
            if x:
                dst[k] = x
            else:
                dst.pop(k, None)

    rows = []
    for i, b in enumerate(base):
        r = dict(b)
        for j in rng.sample(range(len(base)), min(mix, len(base))):
            if j > i:  # upper-triangular mixing keeps the system invertible
                add(r, base[j], rng.randint(-3, 3))
        rows.append(r)
    for _ in range(n_extra):
        r = {}
        for j in rng.sample(range(len(rows)), min(3, len(rows))):
            add(r, rows[j], rng.randint(-3, 3))
        if r:
            rows.append(r)
    rng.shuffle(rows)
    return rows, masters, truth


def write_corpus(out, name, rows_modp, p, table, producer, witnesses, meta):
    d = os.path.join(out, name)
    os.makedirs(os.path.join(d, "wits"), exist_ok=True)
    with open(os.path.join(d, "system.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for r in rows_modp:
            fh.write(json.dumps({str(k): v % p for k, v in sorted(r.items())}) + "\n")
    with open(os.path.join(d, "table.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({str(t): {str(m): v % p for m, v in sorted(c.items()) if v % p}
                   for t, c in sorted(table.items())}, fh, sort_keys=True)
    for t, obj in sorted(witnesses.items()):
        with open(os.path.join(d, "wits", f"w_{producer}_{p}_{t}.json"), "w",
                  encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, sort_keys=True)
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({**meta, "name": name, "p": p, "producer": producer,
                   "n_rows": len(rows_modp), "n_witnesses": len(witnesses)}, fh,
                  indent=1, sort_keys=True)


def bl_receipt_emit(bl_root, rows, masters, p, targets, truth, seed):
    sys.path.insert(0, os.path.join(bl_root, "tools", "trust", "receipt"))
    import numpy as np
    from core import system_fingerprint
    from emitter import FpSystem, emit_for_target
    rows_p = [{k: v % p for k, v in r.items() if v % p} for r in rows]
    allcols = sorted({c for r in rows_p for c in r})
    pivots = [c for c in allcols if c not in set(masters)]
    S = FpSystem([list(r.items()) for r in rows_p], pivots, allcols, p)
    rng = np.random.default_rng(seed)
    out, mp, statuses = {}, None, {}
    fp = system_fingerprint(rows_p, p)
    for t in targets:
        rec, lam, mp = emit_for_target(S, t, set(masters), rng, minpoly=mp,
                                       claimed=truth.get(t))
        statuses[rec["status"]] = statuses.get(rec["status"], 0) + 1
        if rec["status"] != "CERTIFIED":
            continue
        nz = [int(i) for i in np.flatnonzero(lam)]
        obj = witness_json(p, t, rec["c"], {i: int(lam[i]) for i in nz}, len(rows_p))
        obj["family"] = "int-synth"
        obj["system"]["fingerprint"] = fp
        obj["system"]["source"] = "bootloops tools/trust/receipt/emitter.py"
        out[t] = obj
    return rows_p, out, statuses


def winnow_emit(bl_root, rows, masters, p, mode, wdir):
    sys.path.insert(0, os.path.join(bl_root, "tools", "winnow"))
    import ibplapper as lap
    rows_p = [{k: v % p for k, v in r.items() if v % p} for r in rows]
    cols = sorted({c for r in rows_p for c in r})
    top = max(cols) + 1
    order = {c: top - c for c in cols if c not in set(masters)}  # positive ranks
    system = lap.System(rows_p, p, order, forbid=set(masters))
    targets = [c for c in cols if c not in set(masters)]
    res = lap.eliminate(system, lap.Schedule(policy="B2FT"), witnesses=mode,
                        witness_targets=targets, witness_dir=wdir)
    out = {}
    for t, w in res.witnesses.items():
        if w.get("status") == "CERTIFIED" and w.get("witness_path"):
            with open(w["witness_path"], encoding="utf-8") as fh:
                out[t] = json.load(fh)
    return rows_p, out, {k: sum(1 for w in res.witnesses.values() if w.get("status") == k)
                         for k in {w.get("status") for w in res.witnesses.values()}}


def main(bl_root, out):
    os.makedirs(out, exist_ok=True)
    log = {}
    # (a) BootLoops' own test_core fixture (verbatim rows and truth)
    P0 = 2147483647
    rows0 = [{203: 1, 101: -5}, {202: 1, 203: -3, 102: -7}, {201: 1, 202: -2, 101: -1}]
    truth0 = {203: {101: 5}, 202: {101: 15, 102: 7}, 201: {101: 31, 102: 14}}
    rp, wits, st = bl_receipt_emit(bl_root, rows0, [101, 102], P0, [201, 202, 203], truth0, 7)
    write_corpus(out, "fixture_testcore_bl-receipt", rp, P0, truth0, "bl-receipt", wits,
                 {"source": "BootLoops tools/trust/receipt/tests/test_core.py fixture"})
    log["fixture_testcore"] = st
    # (b) seeded integer systems at two primes
    specs = [("int-s", 101, 60, 8, 15), ("int-m", 102, 400, 24, 80), ("int-l", 103, 1500, 40, 300)]
    for name, seed, n_int, n_m, n_x in specs:
        rows, masters, truth = int_system(seed, n_int, n_m, n_x)
        targets = sorted(truth)
        for p in PRIMES:
            meta = {"seed": seed, "n_int": n_int, "n_master": n_m, "n_extra": n_x}
            if name != "int-l":  # Wiedemann at this size is minutes per target
                # The receipt emitter's direct path needs a square system
                # (emitter.py FpSystem docstring), so it gets the variant
                # with no redundant rows.
                rows_sq, _, truth_sq = int_system(seed, n_int, n_m, 0)
                rp, wits, st = bl_receipt_emit(bl_root, rows_sq, masters, p, sorted(truth_sq),
                                               truth_sq, seed)
                write_corpus(out, f"{name}sq_{p}_bl-receipt", rp, p, truth_sq, "bl-receipt",
                             wits, {**meta, "n_extra": 0})
                log[f"{name}sq_{p}_bl-receipt"] = st
            for mode in ("retrofit", "native"):
                tmp = os.path.join(out, "_winnow_tmp", f"{name}_{p}_{mode}")
                os.makedirs(tmp, exist_ok=True)
                rp, wits, st = winnow_emit(bl_root, rows, masters, p, mode, tmp)
                write_corpus(out, f"{name}_{p}_bl-winnow-{mode}", rp, p, truth,
                             f"bl-winnow-{mode}", wits, meta)
                log[f"{name}_{p}_bl-winnow-{mode}"] = st
            rows_p = [{k: v % p for k, v in r.items() if v % p} for r in rows]
            sol = solve_witnesses(rows_p, masters, p)
            wits = {t: witness_json(p, t, c, lam, len(rows_p)) for t, (c, lam) in sol.items()}
            write_corpus(out, f"{name}_{p}_sc-synth", rows_p, p, truth, "sc-synth", wits, meta)
            log[f"{name}_{p}_sc-synth"] = {"CERTIFIED": len(wits)}
            print(name, p, "done", flush=True)
    with open(os.path.join(out, "GEN_LOG.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(log, fh, indent=1, sort_keys=True)
    print(json.dumps(log, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
