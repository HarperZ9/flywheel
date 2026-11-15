"""Spec-edge probe: hand-built witnesses where the spec is silent or where the
two implementations read it differently. Runs sc-py, sc-js, core.py (library)
and core's CLI (receipt.py verify, for exit codes).

    python scripts/edge_cases.py BOOTLOOPS_ROOT CORPUS_DIR OUT_DIR

Base case: BootLoops' own test_core.py fixture (corpus fixture_testcore_bl-receipt),
target 202, true row I_202 = 15 I_101 + 7 I_102.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkers import core_py, sc_js, sc_py  # noqa: E402

P = 2147483647


def cases(base):
    def m(**kw):
        w = copy.deepcopy(base)
        for path, v in kw.items():
            obj = w
            keys = path.split("__")
            for k in keys[:-1]:
                obj = obj[k]
            obj[keys[-1]] = v
        return w

    lam = base["lam"]
    yield "E01_c_float_integral", "c value 15.0 (JSON float)", m(c={"101": 15.0, "102": 7}), None
    yield "E02_c_float_fraction", "c value 15.7 (non-integer)", m(c={"101": 15.7, "102": 7}), None
    yield "E03_c_bool", "c value true", m(c={"101": 15, "102": 7, "103": True}), None
    yield "E04_version_number", "receipt_version as JSON number 1.0", m(receipt_version=1.0), None
    yield "E05_zero_c_table", "explicit zero c entry, table mode with the true row", \
        m(c={"101": 15, "102": 7, "999": 0}), {"202": {"101": 15, "102": 7}}
    yield "E06_c_equal_p_table", "c entry equal to p (== 0 mod p), table mode", \
        m(c={"101": 15, "102": 7, "999": P}), {"202": {"101": 15, "102": 7}}
    k = 5  # c[t] = k on the target column, lam scaled by (1-k): valid under the additive reading
    sc = (1 - k) % P
    yield "E07_c_on_target_col", "c contains the target column (c[t]=5), lam scaled by 1-5", \
        m(c={"101": 15 * sc % P, "102": 7 * sc % P, "202": k},
          lam={"n_rows": lam["n_rows"], "idx": lam["idx"],
               "val": [v * sc % P for v in lam["val"]]}), None
    yield "E08_dup_key_alias", "c keys '101' and '0101' (same integer)", \
        m(c={"101": 99, "0101": 15, "102": 7}), None
    yield "E09_negative_n_rows", "lam.n_rows = -1 with empty idx/val", \
        m(lam={"n_rows": -1, "idx": [], "val": []}), None
    yield "E10_lam_idx_float", "lam.idx entries as floats", \
        m(lam={"n_rows": lam["n_rows"], "idx": [float(i) for i in lam["idx"]], "val": lam["val"]}), None
    yield "E11_nonprime_p", "p = 15 (composite) on a witness rewritten to hold mod 15", None, None
    yield "E12_p_string", "p given as a string", m(p=str(P)), None
    yield "E13_fp_tamper", "system.fingerprint replaced with 64 zeros", \
        m(system={"n_rows": lam["n_rows"], "fingerprint": "0" * 64}), None


def main(bl_root, corpus, out):
    os.makedirs(out, exist_ok=True)
    d = os.path.join(corpus, "fixture_testcore_bl-receipt")
    sysj = os.path.join(d, "system.jsonl")
    base_path = glob.glob(os.path.join(d, "wits", "*_202.json"))[0]
    with open(base_path, encoding="utf-8") as fh:
        base = json.load(fh)
    results = []
    for name, desc, w, table in cases(base):
        if w is None and name == "E11_nonprime_p":
            # build a system and witness mod 15: rows of the fixture reduced mod 15
            q15 = os.path.join(out, "sys15.jsonl")
            with open(sysj, encoding="utf-8") as fh, open(q15, "w", newline="\n") as g:
                for line in fh:
                    r = {k: (int(v) - P if int(v) > P // 2 else int(v)) % 15  # signed integer, then mod 15
                         for k, v in json.loads(line).items()}
                    g.write(json.dumps(r) + "\n")
            w = copy.deepcopy(base)
            # 1*R1 + 3*R0 = e202 - 15 e101 - 7 e102 over Z (hand-derived from the fixture)
            w["p"] = 15; w["c"] = {"101": 0, "102": 7}  # noqa: E702
            w["lam"] = {"n_rows": 3, "idx": [0, 1], "val": [3, 1]}
            sys_use = q15
        else:
            sys_use = sysj
        q = os.path.join(out, f"{name}.json")
        with open(q, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(w, fh)
        a = sc_py(sys_use, [q], table)[os.path.basename(q)]
        b = sc_js(sys_use, [q], table)
        c = core_py(bl_root, sys_use, [q], table)[os.path.basename(q)]
        cli = [sys.executable, os.path.join(bl_root, "tools", "trust", "receipt", "receipt.py"),
               "verify", "--system-jsonl", sys_use, "--witness", q, "-q"]
        if table is not None:
            tq = os.path.join(out, f"{name}.table.json")
            with open(tq, "w", encoding="utf-8") as fh:
                json.dump(table, fh)
            cli += ["--table", tq]
        rc = subprocess.run(cli, capture_output=True, text=True).returncode
        results.append({"case": name, "what": desc, "table_mode": table is not None,
                        "sc_py": a[0], "sc_py_reason": a[1],
                        "sc_js": "n/a" if b is None else b[os.path.basename(q)][0],
                        "core": c[0], "core_reason": c[1], "core_cli_rc": rc,
                        "agree": a[0] == c[0]})
    # filename sensitivity of core's CLI: a valid v1 witness named c_*.json
    q = os.path.join(out, "c_valid_v1_witness.json")
    with open(q, "w", encoding="utf-8") as fh:
        json.dump(base, fh)
    cli = [sys.executable, os.path.join(bl_root, "tools", "trust", "receipt", "receipt.py"),
           "verify", "--system-jsonl", sysj, "--witness", q, "-q"]
    r = subprocess.run(cli, capture_output=True, text=True)
    results.append({"case": "E14_filename_c_prefix", "what": "valid v1 witness saved as c_*.json",
                    "table_mode": False, "sc_py": sc_py(sysj, [q])[os.path.basename(q)][0],
                    "sc_js": sc_js(sysj, [q])[os.path.basename(q)][0],
                    "core": core_py(bl_root, sysj, [q])[os.path.basename(q)][0],
                    "core_cli_rc": r.returncode, "core_cli_stderr": (r.stdout + r.stderr)[-300:]})
    results[-1]["agree"] = results[-1]["sc_py"] == ("PASS" if r.returncode == 0 else "?")
    with open(os.path.join(out, "edge_cases.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(results, fh, indent=1)
    for r in results:
        print(f"{r['case']:<24} sc_py={r['sc_py']:<9} sc_js={r['sc_js']:<9} core={r['core']:<9} "
              f"cli_rc={r['core_cli_rc']}  {r['what']}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
