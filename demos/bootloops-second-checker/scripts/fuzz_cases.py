"""Seeded case generator for the differential fuzzer (scripts/fuzz.py).

A case is a small valid RECEIPT v1.0 witness over a random sparse system, plus an
ordered list of named mutations. Every random choice comes from
random.Random(f"{seed}:{case_id}:{part}"), so a case is fully reproducible from
(seed, case_id, base size, mutation list). Mutations act on the decoded JSON or,
for the few that need it, on the raw text (duplicate keys, NaN, BOM, CRLF).
"""
from __future__ import annotations

import copy
import json
import random

PRIMES = [2147483647, 2147483629, 1048573, 65521, 101, 7, 2]


def rng_for(seed, case_id, part):
    return random.Random(f"{seed}:{case_id}:{part}")


def base_case(seed, base_id, size=None):
    """A valid witness. size = (n_rows, pool) or None for a random small size."""
    r = rng_for(seed, f"base{base_id}", "base")
    p = r.choice(PRIMES)
    n_rows, pool = size or (r.randint(2, 6), r.randint(3, 9))
    big = r.random() < 0.2
    cols = sorted(r.sample(range(1, 10**6), pool)) if not big else \
        sorted(r.randrange(2**52, 2**62) for _ in range(pool))
    rows = []
    for _ in range(n_rows):
        k = r.randint(1, min(4, pool))
        rows.append({c: r.randrange(1, p) for c in r.sample(cols, k)})
    for _ in range(50):
        lam = {i: r.randrange(1, p) for i in r.sample(range(n_rows), r.randint(1, n_rows))}
        res = {}
        for i, li in lam.items():
            for c, v in rows[i].items():
                res[c] = (res.get(c, 0) + li * v) % p
        res = {c: v for c, v in res.items() if v}
        if res:
            break
    else:
        raise RuntimeError("no nonzero residual")
    t = r.choice(sorted(res))
    inv = pow(res[t], -1, p)
    lam = {i: li * inv % p for i, li in lam.items()}
    c = {m: (-v * inv) % p for m, v in res.items() if m != t}
    idx = sorted(lam)
    w = {"receipt_version": "1.0", "kind": "lambda-witness", "p": p, "target": {"col": t},
         "c": {str(m): v for m, v in sorted(c.items())},
         "lam": {"n_rows": n_rows, "idx": idx, "val": [lam[i] for i in idx]},
         "system": {"n_rows": n_rows}}
    sysrows = [{str(k): v for k, v in sorted(row.items())} for row in rows]
    return {"rows": sysrows, "w": w, "table": None, "raw": {}, "p": p, "t": t}


def _pick_c(case, r):
    keys = sorted(case["w"]["c"]) if isinstance(case["w"].get("c"), dict) else []
    return r.choice(keys) if keys else None


def _setc(case, r, fn):
    k = _pick_c(case, r)
    if k is not None:
        case["w"]["c"][k] = fn(case["w"]["c"][k], case["p"])


def _lam(case):
    return case["w"]["lam"]


def _rescale_target(case, k):
    """Add c[t] = k and scale lam and c by (1 - k): valid under the additive reading."""
    p, w = case["p"], case["w"]
    s = (1 - k) % p
    w["lam"]["val"] = [v * s % p for v in w["lam"]["val"]]
    w["c"] = {m: v * s % p for m, v in w["c"].items()}
    w["c"][str(case["t"])] = k


def _row_edit(case, r, fn):
    lam = _lam(case)
    i = r.choice(lam["idx"]) if lam["idx"] else 0
    row = case["rows"][i]
    if row:
        k = r.choice(sorted(row))
        fn(row, k, case["p"])


def _table(case, row_fn):
    true = {k: v for k, v in case["w"]["c"].items()}
    case["table"] = {str(case["t"]): row_fn(true, case["p"])}


def _raw(case, key, value):
    case["raw"][key] = value


MUTATIONS = {
    # semantic: a correct checker must reject
    "sem_coef_plus1": lambda c, r: _setc(c, r, lambda v, p: (v + 1) % p),
    "sem_lam_plus1": lambda c, r: _lam(c)["val"].__setitem__(0, (_lam(c)["val"][0] + 1) % c["p"]),
    "sem_extra_c": lambda c, r: c["w"]["c"].__setitem__("424242", 1),
    "sem_row_plus1": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__(k, (row[k] + 1) % p)),
    "sem_target_swap": lambda c, r: c["w"]["target"].__setitem__("col", 424243),
    # values that equal the right value mod p, or a type change
    "c_float_int": lambda c, r: _setc(c, r, lambda v, p: float(v)),
    "c_float_frac": lambda c, r: _setc(c, r, lambda v, p: v + 0.5),
    "c_bool": lambda c, r: c["w"]["c"].__setitem__("424244", True),
    "c_str_int": lambda c, r: _setc(c, r, lambda v, p: str(v)),
    "c_negative": lambda c, r: _setc(c, r, lambda v, p: v - p),
    "c_plus_p": lambda c, r: _setc(c, r, lambda v, p: v + p),
    "c_huge": lambda c, r: _setc(c, r, lambda v, p: v + p * 10**30),
    "c_zero_entry": lambda c, r: c["w"]["c"].__setitem__("424245", 0),
    "c_entry_eq_p": lambda c, r: c["w"]["c"].__setitem__("424246", c["p"]),
    "c_null": lambda c, r: _setc(c, r, lambda v, p: None),
    "c_key_lead0": lambda c, r: _rekey(c, r, lambda k: "0" + k),
    "c_key_space": lambda c, r: _rekey(c, r, lambda k: " " + k),
    "c_key_plus": lambda c, r: _rekey(c, r, lambda k: "+" + k),
    "c_key_float": lambda c, r: _rekey(c, r, lambda k: k + ".0"),
    "c_key_underscore": lambda c, r: _rekey(c, r, lambda k: k[:1] + "_" + k[1:] if len(k) > 1 else k),
    "c_on_target": lambda c, r: _rescale_target(c, r.randint(2, 9)),
    "c_as_list": lambda c, r: c["w"].__setitem__("c", [[k, v] for k, v in c["w"]["c"].items()]),
    "c_raw_dup": lambda c, r: _raw(c, "dup_c", True),
    # lam
    "lam_idx_float": lambda c, r: _lam(c).__setitem__("idx", [float(i) for i in _lam(c)["idx"]]),
    "lam_idx_str": lambda c, r: _lam(c).__setitem__("idx", [str(i) for i in _lam(c)["idx"]]),
    "lam_idx_negative": lambda c, r: _lam(c)["idx"].__setitem__(
        0, _lam(c)["idx"][0] - _lam(c)["n_rows"]),
    "lam_idx_dup_split": lambda c, r: _dup_split(c),
    "lam_idx_oob": lambda c, r: (_lam(c)["idx"].append(_lam(c)["n_rows"]), _lam(c)["val"].append(1)),
    "lam_idx_bool": lambda c, r: _idx_bool(c),
    "lam_val_float": lambda c, r: _lam(c)["val"].__setitem__(0, float(_lam(c)["val"][0])),
    "lam_val_negative": lambda c, r: _lam(c)["val"].__setitem__(0, _lam(c)["val"][0] - c["p"]),
    "lam_val_str": lambda c, r: _lam(c)["val"].__setitem__(0, str(_lam(c)["val"][0])),
    "lam_len_mismatch": lambda c, r: _lam(c)["val"].append(0),
    "lam_extra_zero": lambda c, r: _extra_zero(c),
    "lam_nrows_str": lambda c, r: _lam(c).__setitem__("n_rows", str(_lam(c)["n_rows"])),
    "lam_nrows_float": lambda c, r: _lam(c).__setitem__("n_rows", float(_lam(c)["n_rows"])),
    "lam_val_nan": lambda c, r: _lam(c)["val"].__setitem__(0, float("nan")),
    "lam_val_inf": lambda c, r: _lam(c)["val"].__setitem__(0, float("inf")),
    # p, version, target
    "p_str": lambda c, r: c["w"].__setitem__("p", str(c["p"])),
    "p_float": lambda c, r: c["w"].__setitem__("p", float(c["p"])),
    "p_bool": lambda c, r: c["w"].__setitem__("p", True),
    "p_one": lambda c, r: c["w"].__setitem__("p", 1),
    "p_negative": lambda c, r: c["w"].__setitem__("p", -c["p"]),
    "ver_1": lambda c, r: c["w"].__setitem__("receipt_version", "1"),
    "ver_1_1": lambda c, r: c["w"].__setitem__("receipt_version", "1.1"),
    "ver_01": lambda c, r: c["w"].__setitem__("receipt_version", "01.0"),
    "ver_space": lambda c, r: c["w"].__setitem__("receipt_version", " 1.0"),
    "ver_v": lambda c, r: c["w"].__setitem__("receipt_version", "v1.0"),
    "ver_num": lambda c, r: c["w"].__setitem__("receipt_version", 1.0),
    "ver_2": lambda c, r: c["w"].__setitem__("receipt_version", "2.0"),
    "ver_missing": lambda c, r: c["w"].pop("receipt_version"),
    "target_str": lambda c, r: c["w"]["target"].__setitem__("col", str(c["t"])),
    "target_float": lambda c, r: c["w"]["target"].__setitem__("col", float(c["t"])),
    "target_bare_int": lambda c, r: c["w"].__setitem__("target", c["t"]),
    "fp_garbage": lambda c, r: c["w"]["system"].__setitem__("fingerprint", "0" * 64),
    "sys_nrows_wrong": lambda c, r: c["w"]["system"].__setitem__("n_rows", 999),
    "extra_field": lambda c, r: c["w"].__setitem__("zz_extra", {"a": 1}),
    # system file
    "row_negative": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__(k, row[k] - p)),
    "row_plus_p": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__(k, row[k] + p)),
    "row_float": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__(k, float(row[k]))),
    "row_float_frac": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__(k, row[k] + 0.5)),
    "row_str_val":lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__(k, str(row[k]))),
    "row_zero_entry": lambda c, r: c["rows"][0].__setitem__("424247", 0),
    "row_key_lead0": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__("0" + k, row.pop(k))),
    "row_key_alias": lambda c, r: _row_edit(c, r, lambda row, k, p: row.__setitem__("0" + k, 0)),
    "sys_blank_line": lambda c, r: _raw(c, "blank_line", True),
    "sys_crlf": lambda c, r: _raw(c, "crlf", True),
    "sys_bom": lambda c, r: _raw(c, "bom", True),
    "wit_bom": lambda c, r: _raw(c, "wit_bom", True),
    # table mode
    "table_true": lambda c, r: _table(c, lambda t, p: dict(t)),
    "table_wrong": lambda c, r: _table(c, lambda t, p: {**t, "424248": 1}),
    "table_zero": lambda c, r: _table(c, lambda t, p: {**t, "424249": 0}),
    "table_eq_p": lambda c, r: _table(c, lambda t, p: {**t, "424250": p}),
    "table_negative": lambda c, r: _table(c, lambda t, p: {k: v - p for k, v in t.items()}),
    "table_key_lead0": lambda c, r: _table(c, lambda t, p: {"0" + k: v for k, v in t.items()}),
    "table_str_val": lambda c, r: _table(c, lambda t, p: {k: str(v) for k, v in t.items()}),
}


def _rekey(case, r, fn):
    k = _pick_c(case, r)
    if k is not None:
        case["w"]["c"][fn(k)] = case["w"]["c"].pop(k)


def _dup_split(case):
    lam, p = _lam(case), case["p"]
    i, v = lam["idx"][0], lam["val"][0]
    a = (v // 2) or 1
    lam["idx"] = [i, i] + lam["idx"][1:]
    lam["val"] = [a, (v - a) % p] + lam["val"][1:]


def _idx_bool(case):
    lam = _lam(case)
    for j, i in enumerate(lam["idx"]):
        if i in (0, 1):
            lam["idx"][j] = bool(i)


def _extra_zero(case):
    lam = _lam(case)
    free = [i for i in range(lam["n_rows"]) if i not in lam["idx"]]
    if free:
        lam["idx"].append(free[0])
        lam["val"].append(0)


def build(seed, base_id, case_id, muts, size=None):
    """Apply mutations in order. Returns (system_text, witness_text, table_or_None).

    A mutation that does not apply to the current state (for example a c-key edit
    after c became a list) is skipped; the skip is deterministic.
    """
    case = base_case(seed, base_id, size)
    for j, name in enumerate(muts):
        try:
            MUTATIONS[name](case, rng_for(seed, case_id, f"m{j}:{name}"))
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            pass
    raw = case["raw"]
    lines = [json.dumps(row) for row in case["rows"]]
    if raw.get("blank_line"):
        lines.insert(1, "")
    nl = "\r\n" if raw.get("crlf") else "\n"
    sys_text = ("﻿" if raw.get("bom") else "") + nl.join(lines) + nl
    wtext = json.dumps(case["w"], sort_keys=True)
    if raw.get("dup_c") and isinstance(case["w"].get("c"), dict) and case["w"]["c"]:
        k = sorted(case["w"]["c"])[0]
        wtext = wtext.replace('"c": {', '"c": {' + json.dumps(k) + ": 12345, ", 1)
    if raw.get("wit_bom"):
        wtext = "﻿" + wtext
    return sys_text, wtext, copy.deepcopy(case["table"])
