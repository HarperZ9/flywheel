# check3_abl.py: written in one shot by abliteration.ai model "abliterated-model-large-v2"
# (provider does not disclose the base model; family unknown), temperature 0, seed 20261002,
# reasoning effort "low", via the provider's OpenAI-compatible API on 2026-10-02. Its prompt was
# third_checker/task.txt: WITNESS_FORMAT.md, the public tool page text, and an I/O contract.
# Two earlier attempts at default reasoning effort spent the whole token budget on reasoning
# and returned no code (response_abl_truncated_raw.json, response_abl_attempt2_raw.json).
# The code below this header is the model's output, byte for byte, unedited.
#!/usr/bin/env python3
"""check3.py -- RECEIPT v1.0 witness verifier (standard library only).

Verifies lambda-witness JSON files against a JSONL sparse system, per
WITNESS_FORMAT.md v1.0.  Where the specification is silent, the strictest
reasonable reading was chosen; each such choice is flagged with a
"# STRICT:" comment below.
"""
import argparse
import json
import sys


# ---------- strictness notes (spec-silent choices) ----------
# STRICT: p is normatively "prime modulus (>1)"; we actually test primality
#         (deterministic Miller-Rabin, valid for p < 3.3e24) and call a
#         witness with composite p MALFORMED.
# STRICT: receipt_version must be a string whose major component is 1
#         ("1", "1.0", "1.2" accepted; anything else unsupported).
# STRICT: `kind`, if present, must be "lambda-witness".
# STRICT: if the optional `system.n_rows` is present it must equal
#         `lam.n_rows`; a contradiction makes the file uninterpretable.
# STRICT: all numeric fields must be JSON integers (no floats, no strings);
#         c / table keys must be strings parsing as integers.
# STRICT: `idx` and `val` must be lists of equal length; duplicate or
#         out-of-range idx is MALFORMED (per rc discipline).
# STRICT: blank lines in the system JSONL are skipped; anything else on a
#         line that is not a JSON object of int->int is a malformed input.
# STRICT: the optional table must be well formed for every entry up front;
#         a bad table is a malformed input (rc 2) for all witnesses.
# STRICT: fingerprint fields are ignored entirely (per the task interface;
#         no byte layout is defined here, so no fingerprint is computed).
# STRICT: if the identity fails, that reason is reported even when the
#         claimed table row also differs (rule 6 only covers witnesses
#         that HOLD).

def is_prime(n):
    if n < 2:
        return False
    for sp in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % sp == 0:
            return n == sp
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


class Malformed(Exception):
    pass


def as_int(x, what):
    if isinstance(x, bool) or not isinstance(x, int):
        raise Malformed("%s not an integer" % what)
    return x


def parse_col_key(k, what):
    if not isinstance(k, str):
        raise Malformed("%s key not a string" % what)
    try:
        return int(k, 10)
    except ValueError:
        raise Malformed("%s key not an integer: %r" % (what, k))


def load_system(path):
    """Return list of dicts {int col -> int value} (raw, unreduced)."""
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    raise Malformed("system line %d: bad JSON" % lineno)
                if not isinstance(obj, dict):
                    raise Malformed("system line %d: not an object" % lineno)
                row = {}
                for k, v in obj.items():
                    col = parse_col_key(k, "system line %d" % lineno)
                    row[col] = as_int(v, "system line %d value" % lineno)
                rows.append(row)
    except Malformed:
        raise
    except OSError as e:
        raise Malformed("cannot read system file: %s" % e)
    except Exception as e:
        raise Malformed("system file error: %s" % e)
    return rows


def load_table(path):
    """Return {int target col -> {int col -> int value}} or raise Malformed."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        raise Malformed("cannot read table file: %s" % e)
    if not isinstance(obj, dict):
        raise Malformed("table is not a JSON object")
    table = {}
    for tk, row in obj.items():
        t = parse_col_key(tk, "table target")
        if not isinstance(row, dict):
            raise Malformed("table row for %d is not an object" % t)
        r = {}
        for k, v in row.items():
            r[parse_col_key(k, "table row")] = as_int(v, "table value")
        table[t] = r
    return table


def load_witness(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        raise Malformed("cannot read witness: %s" % e)
    if not isinstance(obj, dict):
        raise Malformed("witness is not a JSON object")
    return obj


def check_structure(w):
    """Validate the witness schema; return the pieces needed for verification."""
    ver = w.get("receipt_version")
    if not isinstance(ver, str):
        raise Malformed("missing/invalid receipt_version")
    parts = ver.split(".")
    try:
        major = int(parts[0], 10)
    except ValueError:
        raise Malformed("unsupported receipt_version: %r" % ver)
    if major != 1:
        raise Malformed("unsupported receipt_version: %r" % ver)

    kind = w.get("kind")
    if kind is not None and kind != "lambda-witness":
        raise Malformed("unsupported kind: %r" % kind)

    p = as_int(w.get("p"), "p")
    if p <= 1:
        raise Malformed("p must be > 1")
    if not is_prime(p):
        raise Malformed("p is not prime")

    tgt = w.get("target")
    if not isinstance(tgt, dict):
        raise Malformed("missing target")
    t = as_int(tgt.get("col"), "target.col")

    c_raw = w.get("c")
    if not isinstance(c_raw, dict):
        raise Malformed("missing c")
    c = {}
    for k, v in c_raw.items():
        c[parse_col_key(k, "c")] = as_int(v, "c value")

    lam = w.get("lam")
    if not isinstance(lam, dict):
        raise Malformed("missing lam")
    n_rows = as_int(lam.get("n_rows"), "lam.n_rows")
    if n_rows < 0:
        raise Malformed("lam.n_rows negative")
    idx = lam.get("idx")
    val = lam.get("val")
    if not isinstance(idx, list) or not isinstance(val, list):
        raise Malformed("lam.idx/val not arrays")
    if len(idx) != len(val):
        raise Malformed("lam.idx/val length mismatch")
    idxs = [as_int(i, "lam.idx entry") for i in idx]
    vals = [as_int(v, "lam.val entry") for v in val]
    if len(set(idxs)) != len(idxs):
        raise Malformed("duplicate lam.idx")
    for i in idxs:
        if not (0 <= i < n_rows):
            raise Malformed("lam.idx out of range")

    sysf = w.get("system")
    if sysf is not None:
        if not isinstance(sysf, dict):
            raise Malformed("system is not an object")
        sn = sysf.get("n_rows")
        if sn is not None and as_int(sn, "system.n_rows") != n_rows:
            raise Malformed("system.n_rows contradicts lam.n_rows")

    return p, t, c, n_rows, idxs, vals


def normalize_c(c, p):
    out = {}
    for k, v in c.items():
        v %= p
        if v:
            out[k] = v
    return out


def verify_witness(rows, w, table):
    """Return (verdict, reason). Never raises for content problems."""
    try:
        p, t, c_raw, n_rows, idxs, vals = check_structure(w)
    except Malformed as e:
        return "MALFORMED", str(e)

    # Rule 1: row count must match lam.n_rows.
    if len(rows) != n_rows:
        return "FAIL", "lam n_rows mismatch"

    c = normalize_c(c_raw, p)

    # Rule 3: residual r = sum_i lam[i]*R_i mod p (zero entries dropped).
    r = {}
    for i, lv in zip(idxs, vals):
        lv %= p
        if lv == 0:
            continue
        for col, rv in rows[i].items():
            nv = (r.get(col, 0) + lv * rv) % p
            if nv:
                r[col] = nv
            else:
                r.pop(col, None)

    # Rule 4: expect = {t:1} + {m: -c[m]}.
    expect = {t: 1}
    for m, v in c.items():
        nv = (expect.get(m, 0) - v) % p
        if nv:
            expect[m] = nv
        else:
            expect.pop(m, None)

    # Rule 5: exact comparison, no tolerances.
    if r != expect:
        return "FAIL", "residual mismatch"

    # Rule 6: optional table mode.
    if table is not None and t in table:
        claimed = normalize_c(table[t], p)
        if claimed != c:
            return "FAIL", "claimed table row != certified row"

    return "PASS", "identity holds"


def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("system_jsonl")
    ap.add_argument("witnesses", nargs="+")
    ap.add_argument("--table", default=None)
    args = ap.parse_args(argv)  # exits 2 on usage error (incl. no witnesses)

    try:
        rows = load_system(args.system_jsonl)
    except Malformed as e:
        sys.stderr.write("malformed system input: %s\n" % e)
        return 2

    table = None
    if args.table is not None:
        try:
            table = load_table(args.table)
        except Malformed as e:
            sys.stderr.write("malformed table input: %s\n" % e)
            return 2

    any_fail = False
    any_malformed = False
    import os
    for wpath in args.witnesses:
        base = os.path.basename(wpath)
        try:
            w = load_witness(wpath)
        except Malformed as e:
            verdict, reason = "MALFORMED", str(e)
        except Exception as e:  # never crash
            verdict, reason = "MALFORMED", "unexpected error: %s" % e
        else:
            try:
                verdict, reason = verify_witness(rows, w, table)
            except Exception as e:  # never crash
                verdict, reason = "MALFORMED", "unexpected error: %s" % e
        if verdict == "FAIL":
            any_fail = True
        elif verdict == "MALFORMED":
            any_malformed = True
        print(json.dumps({"witness": base, "verdict": verdict,
                         "reason": reason}, separators=(", ", ": ")))

    if any_malformed:
        return 2
    if any_fail:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:  # absolute last resort: never crash
        sys.stderr.write("fatal: %s\n" % e)
        sys.exit(2)
