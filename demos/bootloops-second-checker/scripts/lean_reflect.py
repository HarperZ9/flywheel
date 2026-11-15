"""Lean 4 kernel check by reflection, with a statement-fixed axiom audit.

    python scripts/lean_reflect.py CORPUS_DIR OUT_DIR [--jobs N] [--sizes 10000,30000,...]
                                   [--max-terms 20000] [--corpus-limit N] [--timeout S]

For every module batch three files are written, in this order:
  Spec  `def stmt_k : Prop := ReceiptLean.AllOK p [...]`, one per witness. Its sha256
        is recorded in the manifest BEFORE any proof file exists.
  Prf   imports Spec and proves `theorem prf_k : stmt_k` by allCheck_sound and one
        `decide +kernel` (ReceiptLean/Reflect.lean).
  Aud   written by the auditor, not the prover: `theorem aud_k : stmt_k := prf_k` and
        `#print axioms aud_k`. If prf_k proves anything other than stmt_k, Aud does not
        compile.
A module passes the audit only if: Spec is byte-identical to the recorded hash; Prf and
Aud compile; every aud_k depends only on {propext, Classical.choice, Quot.sound}; the
Prf source contains no sorry, admit, axiom, native_decide, implemented_by, extern or
unsafe; and leanchecker replays Prf and Aud with rc 0. Planted controls must fail it.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LEAN_DIR = os.path.join(REPO, "lean")
GEN = os.path.join(LEAN_DIR, "ReceiptLean", "Gen")
OLEAN = os.path.join(LEAN_DIR, ".lake", "build", "lib", "lean", "ReceiptLean", "Gen")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "src"))
from lean_run import artificial, lean_env, load_rows  # noqa: E402
from second_checker.checker import Witness, parse_witness  # noqa: E402
from second_checker.lean_emit import _columns  # noqa: E402

ALLOWED = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(r"\bsorry\b|\badmit\b|^\s*axiom\b|native_decide|implemented_by|@\[extern|\bunsafe\b",
                       re.M)
IMPORTS = "import Mathlib.Data.ZMod.Basic\nimport ReceiptLean.Reflect\n"
OPTS = "set_option maxRecDepth 100000\nset_option maxHeartbeats 0\n"
HEAD = IMPORTS + OPTS


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry(ts, pos, neg):
    return "  ([" + ", ".join(f"({li}, {v})" for li, v in ts) + f"], {pos}, {neg})"


def spec_src(items, chunk_terms=0):
    """With chunk_terms > 0, the column list is split into parts of about that many
    terms, each its own `def`, and the statement is AllOK over their concatenation.
    The proposition is the same list; only its elaboration is split."""
    out = [HEAD, "namespace RSpec\n"]
    for k, p, rows, w in items:
        cols = _columns(rows, w)
        out.append(f"-- {k}: target {w.target}, p {p}\n")
        if chunk_terms <= 0:
            body = ",\n".join(_entry(ts, pos, neg) for _, ts, pos, neg in cols)
            out.append(f"def stmt_{k} : Prop := ReceiptLean.AllOK {p} [\n{body}\n]\n")
            continue
        parts, cur, n = [], [], 0
        for _, ts, pos, neg in cols:
            if cur and n + len(ts) > chunk_terms:
                parts.append(cur)
                cur, n = [], 0
            cur.append(_entry(ts, pos, neg))
            n += max(1, len(ts))
        parts.append(cur)
        for j, part in enumerate(parts):
            body = ",\n".join(part)
            out.append(f"def part_{k}_{j} : List (List (ℕ × ℕ) × ℕ × ℕ) := [\n{body}\n]\n")
        cat = " ++ ".join(f"part_{k}_{j}" for j in range(len(parts)))
        out.append(f"def stmt_{k} : Prop := ReceiptLean.AllOK {p} ({cat})\n")
    return "".join(out) + "end RSpec\n"


def prf_src(spec_mod, keys, body=None):
    out = [IMPORTS, f"import ReceiptLean.Gen.{spec_mod}\n", OPTS]
    for k in keys:
        out.append(body(k) if body else
                   f"theorem prf_{k} : RSpec.stmt_{k} := by\n  unfold RSpec.stmt_{k}\n"
                   f"  exact ReceiptLean.allCheck_sound _ _ (by decide +kernel)\n")
    return "".join(out)


def aud_src(prf_mod, keys):
    out = [f"import ReceiptLean.Gen.{prf_mod}\n"]
    for k in keys:
        out.append(f"theorem aud_{k} : RSpec.stmt_{k} := prf_{k}\n#print axioms aud_{k}\n")
    return "".join(out)


def compile_(mod, src, env, timeout):
    os.makedirs(GEN, exist_ok=True)
    os.makedirs(OLEAN, exist_ok=True)
    path = os.path.join(GEN, f"{mod}.lean")
    if src is not None:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
    olean = os.path.join(OLEAN, f"{mod}.olean")
    if os.path.exists(olean):
        os.remove(olean)
    t0 = time.perf_counter()
    try:
        r = subprocess.run(["lean", "-o", olean, path], cwd=LEAN_DIR, env=env, capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8", errors="replace")
        out, ok, to = r.stdout + r.stderr, r.returncode == 0, False
    except subprocess.TimeoutExpired:
        out, ok, to = "", False, True
    return {"ok": ok, "timeout": to, "wall_s": round(time.perf_counter() - t0, 2),
            "out": out, "errors": [x for x in out.splitlines() if "error" in x][:3]}


def leancheck(mod, env):
    r = subprocess.run(["leanchecker", f"ReceiptLean.Gen.{mod}"], cwd=LEAN_DIR, env=env,
                       capture_output=True, text=True, timeout=7200)
    return r.returncode


def run_batch(tag, items, env, timeout, prf_body=None, tamper_spec=None, chunk_terms=0):
    """Spec, then Prf, then Aud, then the audit. Returns a result dict."""
    keys = [k for k, *_ in items]
    smod, pmod, amod = f"{tag}Spec", f"{tag}Prf", f"{tag}Aud"
    spec = spec_src(items, chunk_terms)
    fixed = sha(spec)  # recorded before any proof exists
    res = {"tag": tag, "n": len(keys), "spec_sha256": fixed}
    s = compile_(smod, spec, env, timeout)
    if tamper_spec:  # control: someone edits the statement after it was fixed
        spec = tamper_spec(spec)
        s = compile_(smod, spec, env, timeout)
    p = compile_(pmod, prf_src(smod, keys, prf_body), env, timeout)
    a = compile_(amod, aud_src(pmod, keys), env, timeout) if p["ok"] else {"ok": False, "out": "", "wall_s": 0}
    with open(os.path.join(GEN, f"{smod}.lean"), encoding="utf-8") as fh:
        spec_now = sha(fh.read())
    with open(os.path.join(GEN, f"{pmod}.lean"), encoding="utf-8") as fh:
        forbidden = sorted(set(FORBIDDEN.findall(fh.read())))
    ax = {}
    for name, deps in re.findall(r"'aud_(\S+)' depends on axioms: \[([^\]]*)\]", a["out"]):
        ax[name] = sorted(x.strip() for x in deps.split(",") if x.strip())
    for name in re.findall(r"'aud_(\S+)' does not depend on any axioms", a["out"]):
        ax[name] = []
    axioms_ok = len(ax) == len(keys) and all(set(v) <= ALLOWED for v in ax.values())
    lc = [leancheck(pmod, env), leancheck(amod, env)] if a["ok"] else None
    res.update(spec_ok=s["ok"], spec_hash_ok=spec_now == fixed, prf_ok=p["ok"], aud_ok=a["ok"],
               axioms=sorted({x for v in ax.values() for x in v}), axioms_ok=axioms_ok,
               forbidden=forbidden, leanchecker_rc=lc, prf_timeout=p.get("timeout"),
               wall_s={"spec": s["wall_s"], "prf": p["wall_s"], "aud": a["wall_s"]},
               errors=(p.get("errors") or []) + (a.get("errors") or []))
    res["audit_pass"] = bool(s["ok"] and res["spec_hash_ok"] and p["ok"] and a["ok"] and axioms_ok
                             and not forbidden and lc == [0, 0])
    return res


def corpus_batches(corpus, max_terms, max_n, limit=None):
    batches, cur, terms, mapping = [], [], 0, {}
    for ci, meta in enumerate(sorted(glob.glob(os.path.join(corpus, "*", "meta.json")))):
        d = os.path.dirname(meta)
        p = json.load(open(meta, encoding="utf-8"))["p"]
        rows = load_rows(os.path.join(d, "system.jsonl"), p)
        for q in sorted(glob.glob(os.path.join(d, "wits", "*.json"))):
            with open(q, encoding="utf-8") as fh:
                w = parse_witness(json.load(fh))
            t = sum(len(rows[i]) for i in w.lam)
            if cur and (terms + t > max_terms or len(cur) >= max_n):
                batches.append(cur)
                cur, terms = [], 0
            k = f"c{ci}_{w.target}"
            mapping[k] = f"{os.path.basename(d)}/{os.path.basename(q)}"
            cur.append((k, p, rows, w))
            terms += t
            if limit and len(mapping) >= limit:
                return batches + [cur], mapping
    return batches + ([cur] if cur else []), mapping


def controls(env, timeout):
    rows, w = artificial(7, 100)
    good = [("ctl", w.p, rows, w)]
    bad_c = dict(w.c)
    m = sorted(bad_c)[0]
    bad_c[m] = (bad_c[m] + 1) % w.p
    bad = [("ctl", w.p, rows, Witness(p=w.p, target=w.target, c=bad_c, lam=w.lam, n_rows=w.n_rows))]
    true_ = lambda s: re.sub(r"def stmt_ctl : Prop := ReceiptLean.AllOK[\s\S]*?\n\]\n",  # noqa: E731
                             "def stmt_ctl : Prop := True\n", s)
    plans = {
        "P0_honest_proof": (good, None, None, True),
        "P1_axiom_assumes_statement": (good, lambda k: f"axiom key_{k} : RSpec.stmt_{k}\n"
                                       f"theorem prf_{k} : RSpec.stmt_{k} := key_{k}\n", None, False),
        "P2_sorry": (good, lambda k: f"theorem prf_{k} : RSpec.stmt_{k} := by sorry\n", None, False),
        "P3_weakened_statement": (good, lambda k: f"theorem prf_{k} : True := trivial\n", None, False),
        "P4_statement_edited_after_fixing": (good, lambda k: f"theorem prf_{k} : RSpec.stmt_{k} := trivial\n",
                                             true_, False),
        "P5_native_decide": (good, lambda k: f"theorem prf_{k} : RSpec.stmt_{k} := by\n  unfold RSpec.stmt_{k}\n"
                             f"  exact ReceiptLean.allCheck_sound _ _ (by native_decide)\n", None, False),
        "P6_skip_kernel_on_false_claim": (bad, lambda k: "set_option debug.skipKernelTC true in\n"
                                          f"theorem prf_{k} : RSpec.stmt_{k} := by\n  unfold RSpec.stmt_{k}\n"
                                          f"  exact ReceiptLean.allCheck_sound _ _ (by decide +kernel)\n",
                                          None, False),
        "N1_corrupted_witness": (bad, None, None, False),
    }
    out = []
    for j, (name, (items, body, tamper, expect)) in enumerate(plans.items()):
        r = run_batch(f"Ctl{j}", items, env, timeout, prf_body=body, tamper_spec=tamper)
        r.update(control=name, expected_pass=expect, scored_correct=r["audit_pass"] == expect)
        out.append(r)
        print("control", name, "audit_pass", r["audit_pass"], "expected", expect, flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--max-terms", type=int, default=20000)
    ap.add_argument("--max-n", type=int, default=300)
    ap.add_argument("--corpus-limit", type=int, default=0)
    ap.add_argument("--sizes", default="")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--skip-corpus", action="store_true")
    ap.add_argument("--skip-controls", action="store_true")
    ap.add_argument("--chunk-terms", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    env = lean_env()
    lib = os.path.join(LEAN_DIR, ".lake", "build", "lib", "lean", "ReceiptLean")
    os.makedirs(lib, exist_ok=True)
    r = subprocess.run(["lean", "-o", os.path.join(lib, "Reflect.olean"),
                        os.path.join(LEAN_DIR, "ReceiptLean", "Reflect.lean")],
                       cwd=LEAN_DIR, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ReceiptLean/Reflect.lean did not compile:\n{r.stdout}{r.stderr}")
    rep = {"controls": [] if a.skip_controls else controls(env, a.timeout)}
    rep["scale"] = []
    save(a.out, rep)
    for T in [int(x) for x in a.sizes.split(",") if x]:
        rows, w = artificial(20261002 + T, T)
        r = run_batch(f"Rs{T}c{a.chunk_terms}", [(f"s{T}", w.p, rows, w)], env, a.timeout,
                      chunk_terms=a.chunk_terms)
        r["chunk_terms"] = a.chunk_terms
        r["terms"] = T
        rep["scale"].append(r)
        save(a.out, rep)
        print("scale", T, r["audit_pass"], r["wall_s"], flush=True)
        if not r["audit_pass"]:
            break
    if not a.skip_corpus:
        batches, mapping = corpus_batches(a.corpus, a.max_terms, a.max_n, a.corpus_limit or None)
        rep["corpus_mapping"] = mapping
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            futs = [ex.submit(run_batch, f"Rc{j:04d}", b, env, a.timeout) for j, b in enumerate(batches)]
            rep["corpus"] = [f.result() for f in futs]
        rep["corpus_wall_s"] = round(time.perf_counter() - t0, 1)
        n_pass = sum(r["n"] for r in rep["corpus"] if r["audit_pass"])
        print("corpus", n_pass, "of", len(mapping), "witnesses in passing modules", rep["corpus_wall_s"], flush=True)
    save(a.out, rep)


def save(out, rep):
    """Written after every step, so a stopped run keeps what it measured."""
    with open(os.path.join(out, "lean_reflect.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rep, fh, indent=1)


if __name__ == "__main__":
    main()
