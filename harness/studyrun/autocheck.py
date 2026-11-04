"""Automatic integrity checks at lock time, at the end of a run, and on `studyrun audit` (upgrade 2026-11-02).

Recheck F673 caught 3 of 6 planted errors. Every miss kept the record consistent with itself: a removed
limit line (twice), a code constant changed together with its outputs, and a post hoc file never
compared with its checkpoint. One check per miss:

  "limits":    [{"text": "F132 saw 0.126 and 0.170", "in": ["PREREG.txt"],
                 "source": "../F132/RESULTS.md", "span": "Shared-trend arm 0.126 and 0.170"}]
      The span must still be in its source, every number in the text must appear in the span (to the
      text's decimals), and the text must still be in every file under "in" (a removed limit fails).
  "constants": [{"name": "Purcell prefactor", "code": "study_d.py", "symbol": "K",
                 "derive": "check_constants.py:purcell", "tol": 1e-9}]
      The derive unit computes the value by its own path. It may not be one of the spec's code files and
      may not import one. The value it is compared with is a module-level constant read from the study
      code without importing it ("code" + "symbol"), or a result path ("value_path", run and audit only).
  "posthoc":   [{"file": "posthoc_sign.txt", "checkpoint": "out/20261102T094346Z/result.json",
                 "rerun": "posthoc_sign_fn.py:main"}]
      Sealed by hash at the first audit (<lock>.posthoc.json); later audits compare both hashes. A
      checkpoint with a manifest.json beside it must match the manifest's result_sha256. "rerun" (optional)
      regenerates the text and compares hashes. Any file named *posthoc* or *post_hoc* in the study folder
      that is not registered is reported.

These sections are not frozen by the lock: limits and constants are often written after the run. A section
that is present is checked; studyrun.spec/2 also requires limits and constants at lock time.
"""
import ast
import json
import math
import re
from pathlib import Path

from . import units
from .hashing import sha256_file
from .verdict import get

NUM = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?(?![A-Za-z0-9_])")
SECTIONS = ("limits", "constants", "posthoc")


def _norm(text):
    return " ".join(str(text).split())


def _path(base, p):
    q = Path(p)
    return (q if q.is_absolute() else Path(base) / q).resolve()


def numbers(text):
    """[(value, decimals)] for each stand-alone number in text; identifiers such as F132 are skipped."""
    out = []
    for m in NUM.finditer(text):
        s = m.group(0)
        mant = s.lower().split("e")[0]
        out.append((float(s), len(mant.split(".")[1]) if "." in mant else 0))
    return out


def _num_in(value, dec, pool):
    return any(abs(round(v, dec) - value) <= 10 ** -(dec + 6) or abs(v - value) <= 1e-12 * max(1, abs(v)) for v in pool)


def check_limit(base, row, phase):
    out = {"text": row.get("text"), "ok": True, "problems": [], "pending": []}
    src = _path(base, row["source"])
    if not src.is_file():
        out["problems"].append(f"source missing: {src}")
    else:
        body = _norm(src.read_text(encoding="utf-8", errors="replace"))
        span = _norm(row["span"])
        if span not in body:
            out["problems"].append(f"cited span no longer in {src.name}: '{span[:80]}'")
        pool = [v for v, _ in numbers(span)]
        for v, d in numbers(row["text"]):
            if not _num_in(v, d, pool):
                out["problems"].append(f"number {v:g} in the limit text is not in the cited span")
    for f in row.get("in", []):
        p = _path(base, f)
        if not p.is_file():
            (out["problems"] if phase == "audit" else out["pending"]).append(f"{p.name} not written")
        elif _norm(row["text"]) not in _norm(p.read_text(encoding="utf-8", errors="replace")):
            out["problems"].append(f"limit line removed from {p.name}")
    out["ok"] = not out["problems"]
    return out


def module_constant(code_path, symbol):
    """Evaluate a module-level constant without importing the module: simple assignments only, math allowed."""
    tree = ast.parse(Path(code_path).read_text(encoding="utf-8"))
    env = {"__builtins__": {}, "math": math, "pi": math.pi, "e": math.e, "sqrt": math.sqrt, "log": math.log,
           "exp": math.exp, "abs": abs, "float": float, "int": int}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names or node.value is None:
                continue
            try:
                val = eval(compile(ast.Expression(node.value), str(code_path), "eval"), env)  # noqa: S307
            except Exception:  # noqa: BLE001 - a non-constant assignment is skipped, not an error
                continue
            for n in names:
                env[n] = val
    if symbol not in env:
        raise KeyError(f"{symbol} is not a module-level constant in {Path(code_path).name}")
    return env[symbol]


def independence(spec, derive_file):
    """Problems if the derive file is study code or imports study code by module name."""
    df = Path(derive_file).resolve()
    code = [Path(c).resolve() for c in spec.get("_code", [])]
    if df in code:
        return [f"{df.name} is one of the spec's code files; derive by another path"]
    stems = {c.stem for c in code}
    tree = ast.parse(df.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
                "import_module", "__import__", "spec_from_file_location"):
            mods |= {a.value.split(".")[0] for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    hit = sorted(mods & stems)
    return [f"{df.name} imports study code {', '.join(hit)}"] if hit else []


def check_constant(spec, row, phase, result=None):
    base = spec["_base"]
    out = {"name": row.get("name"), "ok": True, "problems": [], "pending": []}
    dfile, func = row["derive"].rsplit(":", 1)
    dpath = _path(base, dfile)
    out["problems"] += independence(spec, dpath)
    try:
        if row.get("symbol"):
            ours = module_constant(_path(base, row["code"]), row["symbol"])
        elif result is not None:
            ours = get(result, row["value_path"])
        else:
            out["pending"].append("value_path needs a result; checked at the end of the run")
            out["ok"] = not out["problems"]
            return out
        theirs = units.load(dpath, func)({"base": base, "inputs": spec.get("_inputs", []), "params": row.get("params", {})})
        tol, rel = row.get("tol", 1e-9), row.get("rel", 0.0)
        out.update(value=ours, derived=theirs)
        if not abs(float(ours) - float(theirs)) <= tol + rel * abs(float(theirs)):
            out["problems"].append(f"value {ours!r} and independent derivation {theirs!r} differ beyond tol {tol}")
    except Exception as e:  # noqa: BLE001 - a broken check is a failed check, reported with its cause
        out["problems"].append(f"{type(e).__name__}: {e}")
    out["ok"] = not out["problems"]
    return out


def _seal_path(spec):
    lp = Path(spec["_lock_path"])
    return lp.with_name(lp.stem + ".posthoc.json")


def check_posthoc(spec, rows, phase):
    base, seal_p = spec["_base"], _seal_path(spec)
    seal = json.loads(seal_p.read_text(encoding="utf-8")) if seal_p.is_file() else {}
    out, new_seal = [], dict(seal)
    for row in rows:
        f, ck = _path(base, row["file"]), _path(base, row["checkpoint"])
        r = {"file": row["file"], "ok": True, "problems": [], "pending": []}
        if not f.is_file() or not ck.is_file():
            what = f"missing: {f.name if not f.is_file() else ck.name}"
            (r["problems"] if phase == "audit" else r["pending"]).append(what)
            r["ok"] = not r["problems"]
            out.append(r)
            continue
        r["sha256"], r["checkpoint_sha256"] = sha256_file(f), sha256_file(ck)
        man = ck.with_name("manifest.json")
        if ck.name == "result.json" and man.is_file():
            want = json.loads(man.read_text(encoding="utf-8")).get("result_sha256")
            if want and want != r["checkpoint_sha256"]:
                r["problems"].append(f"checkpoint {ck.name} hashes {r['checkpoint_sha256'][:12]}, manifest says {want[:12]}")
        if row.get("checkpoint_sha256") and row["checkpoint_sha256"] != r["checkpoint_sha256"]:
            r["problems"].append("checkpoint differs from the hash declared in the spec")
        old = seal.get(row["file"])
        if old:
            if old["sha256"] != r["sha256"]:
                r["problems"].append(f"{f.name} changed since it was sealed at {old['sealed_at']}")
            if old["checkpoint_sha256"] != r["checkpoint_sha256"]:
                r["problems"].append(f"checkpoint {ck.name} changed since the post hoc file was sealed")
        elif phase == "audit":
            new_seal[row["file"]] = {"sha256": r["sha256"], "checkpoint": row["checkpoint"],
                                     "checkpoint_sha256": r["checkpoint_sha256"], "sealed_at": _now()}
            r["sealed_now"] = True
        if row.get("rerun"):
            rf, fn = row["rerun"].rsplit(":", 1)
            text = units.load(_path(base, rf), fn)({"base": base, "checkpoint": str(ck), "inputs": spec.get("_inputs", [])})
            if _norm(text) != _norm(f.read_text(encoding="utf-8", errors="replace")):
                r["problems"].append(f"rerun of {Path(rf).name}:{fn} does not reproduce {f.name}")
        r["ok"] = not r["problems"]
        out.append(r)
    if phase == "audit" and new_seal != seal:
        seal_p.write_text(json.dumps(new_seal, indent=1) + "\n", encoding="utf-8", newline="\n")
    registered = {_path(base, r["file"]) for r in rows} | {seal_p.resolve()}
    stray = sorted(str(p.name) for p in Path(base).iterdir() if p.is_file() and re.search(r"post_?hoc", p.name, re.I)
                   and p.suffix not in (".py",) and p.resolve() not in registered)
    return out, stray


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def problems(spec):
    out = []
    for i, r in enumerate(spec.get("limits") or []):
        if not isinstance(r, dict) or not r.get("text") or not r.get("source") or not r.get("span"):
            out.append(f"limits[{i}]: needs text, source and span")
    for i, r in enumerate(spec.get("constants") or []):
        if not isinstance(r, dict) or ":" not in str(r.get("derive", "")):
            out.append(f"constants[{i}]: needs derive 'file.py:function'")
        elif not (r.get("symbol") and r.get("code")) and not r.get("value_path"):
            out.append(f"constants[{i}]: needs code + symbol, or value_path")
    for i, r in enumerate(spec.get("posthoc") or []):
        if not isinstance(r, dict) or not r.get("file") or not r.get("checkpoint"):
            out.append(f"posthoc[{i}]: needs file and checkpoint")
    return out


def run(spec, phase, result=None):
    """phase: lock, run or audit. Returns the report; report['ok'] is False if any present check failed."""
    rep = {"phase": phase, "missing": [s for s in SECTIONS if s not in spec]}
    rep["limits"] = [check_limit(spec["_base"], r, phase) for r in spec.get("limits") or []]
    rep["constants"] = [check_constant(spec, r, phase, result) for r in spec.get("constants") or []]
    if phase == "lock":
        rep["posthoc"], stray = [], []
    else:
        rep["posthoc"], stray = check_posthoc(spec, spec.get("posthoc") or [], phase)
    rep["unregistered_posthoc"] = stray
    rep["problems"] = [f"{k}: {p}" for k in SECTIONS for row in rep[k] for p in row["problems"]]
    if phase == "audit":
        rep["problems"] += [f"posthoc: {s} looks post hoc and is not registered" for s in stray]
    rep["ok"] = not rep["problems"]
    return rep
