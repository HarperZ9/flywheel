"""The stage: check PREREG, hash inputs and code, run the analysis and controls, check every hash
again, score, write the manifest, check reproduction, append the ledger entry.

Nothing is scored if the PREREG, the plan, an input or a code file changed, or if a run left
bytecode beside the code it read. A blocked run writes its manifest and no ledger entry.
"""
import datetime as dt
import json
import time
from pathlib import Path

from . import MANIFEST_SCHEMA, ledger, prereg, units, verdict
from .hashing import FORM, hash_paths, sha256_file, sha256_json
from .spec import load, unit_path


class Blocked(RuntimeError):
    pass


def _pycache(paths):
    """Every bytecode file beside the code, so a new one inside an existing __pycache__ is caught too."""
    dirs = {Path(p).parent / "__pycache__" for p in paths}
    return sorted(str(f) for d in dirs if d.exists() for f in d.iterdir())


def _check_inputs(spec, hashes):
    bad = []
    for row, p in zip(spec.get("inputs", []), spec["_inputs"]):
        if hashes[p] is None:
            bad.append(f"input missing: {p}")
        elif row.get("sha256") and row["sha256"] != hashes[p]:
            bad.append(f"input {p} hashes {hashes[p]}, spec declares {row['sha256']}")
    return bad


def _before(spec):
    pre, bad = prereg.check(spec)
    hashes = hash_paths(spec["_inputs"] + spec["_code"])
    bad += _check_inputs(spec, hashes)
    return pre, hashes, _pycache(spec["_code"]), bad


def _after(spec, pre, hashes, caches):
    pre2, bad = prereg.check(spec)
    if pre2.get("sha256") != pre.get("sha256"):
        bad.append("PREREG changed during the run")
    now = hash_paths(spec["_inputs"] + spec["_code"])
    bad += [f"changed during the run: {p}" for p in now if now[p] != hashes[p]]
    new = set(_pycache(spec["_code"])) - set(caches)
    bad += [f"bytecode written beside read-only code: {d}" for d in sorted(new)]
    return bad


def _execute(spec):
    rng = units.make_rng(spec["seed"], spec.get("rng", "python"))
    ctx = {"params": spec["analysis"].get("params", {}), "rng": rng, "seed": spec["seed"],
           "inputs": spec["_inputs"], "state": {}, "spec_id": spec["id"], "base": spec["_base"]}
    timing = {}
    t = time.perf_counter()
    analysis = units.load(*unit_path(spec, spec["analysis"]["unit"]))(ctx)
    timing["analysis"] = time.perf_counter() - t
    controls = {}
    for c in spec["controls"]:
        t = time.perf_counter()
        out = units.load(*unit_path(spec, c["unit"]))({**ctx, "params": c.get("params", {})}, analysis)
        null, meta = (out["null"], out.get("meta", {})) if isinstance(out, dict) else (out, {})
        real = verdict.get({"analysis": analysis}, c["compare"])
        controls[c["name"]] = {**units.summarise(real, null, c.get("min_n", 20)), "compare": c["compare"],
                               "description": c.get("description", ""), **({"meta": meta} if meta else {})}
        timing[c["name"]] = time.perf_counter() - t
    return analysis, controls, timing


def _reproduce(spec, result):
    cfg = spec.get("reproduce")
    if not cfg:
        return None
    src = Path(spec["_reproduce_source"])
    theirs = json.loads(src.read_text(encoding="utf-8"))
    rows, tol = [], cfg.get("tol", 1e-9)
    for ours, path in cfg["map"].items():
        a, b = verdict.get(result, ours), verdict.get(theirs, path)
        ok = (a == b) if not isinstance(a, float) else abs(a - b) <= tol
        rows.append({"ours": ours, "recorded": path, "value": a, "recorded_value": b, "ok": bool(ok)})
    return {"source": str(src), "source_sha256": sha256_file(src), "tol": tol,
            "all_ok": all(r["ok"] for r in rows), "rows": rows}


def _write(spec, result):
    out = Path(spec["_out"]) / result["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8")
    manifest = {"schema": MANIFEST_SCHEMA, "study": spec["id"], "run_id": result["run_id"],
                "spec": {"path": spec["_path"], "sha256": sha256_file(spec["_path"])},
                "prereg": result["prereg"], "hashes": result["hashes"],
                "result_sha256": sha256_file(out / "result.json"), "status": result["status"],
                "canonical_form": FORM}
    manifest["manifest_sha256"] = sha256_json(manifest)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return out / "manifest.json", manifest["manifest_sha256"]


def run(spec_path, append_ledger=True):
    spec = load(spec_path)
    stamp = dt.datetime.now(dt.timezone.utc)
    result = {"study": spec["id"], "run_id": stamp.strftime("%Y%m%dT%H%M%SZ"), "date": stamp.date().isoformat()}
    pre, hashes, caches, bad = _before(spec)
    result.update(prereg=pre, hashes=hashes)
    if not bad:
        result["analysis"], result["controls"], result["timing_s"] = _execute(spec)
        bad = _after(spec, pre, hashes, caches)
    if bad:
        result.update(status="blocked", problems=bad)
        _write(spec, result)
        raise Blocked("; ".join(bad))
    result["verdicts"] = verdict.judge(result, spec["verdicts"])
    result["reproduce"] = _reproduce(spec, result)
    result["status"] = "scored"
    mpath, msha = _write(spec, result)
    if append_ledger:
        rel = Path(mpath).relative_to(Path(spec["_ledger_path"]).parent) if Path(mpath).is_relative_to(
            Path(spec["_ledger_path"]).parent) else Path(mpath)
        result["ledger_number"], _ = ledger.append(spec, result, rel.as_posix(), msha)
    return result
