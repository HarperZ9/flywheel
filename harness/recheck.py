"""Run recheck manifests: one command from a clone to a verdict.

    python -m harness.recheck list
    python -m harness.recheck run recheck/site-benchmark-seal.json
    python -m harness.recheck run --hardware cpu        # every cpu-class manifest

For each manifest: check out the pinned commit with canonical bytes
(``core.autocrlf=false``, ``core.longpaths=true``), fetch and hash-check the
inputs, run the command and compare with the expected verdict, then run the
false-success control and require that it fails the way the manifest says.
A recheck passes only when both hold. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from .recheck_manifest import ManifestError, discover, expand, load

REPO = Path(__file__).resolve().parent.parent
_CANON = ["-c", "core.autocrlf=false", "-c", "core.longpaths=true"]


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def checkout(m: dict, work: Path) -> Path:
    """A canonical-bytes checkout of the pinned commit."""
    dest = work / "checkout"
    here = _git("-C", str(REPO), "cat-file", "-e", f"{m['commit']}^{{commit}}")
    if here.returncode == 0:
        r = _git(*_CANON, "-C", str(REPO), "worktree", "add", "--detach", str(dest), m["commit"])
    else:
        _git("init", "-q", str(dest))
        _git("-C", str(dest), "fetch", "-q", "--depth", "1", m["repository"], m["commit"])
        r = _git(*_CANON, "-C", str(dest), "checkout", "-q", m["commit"])
    if r.returncode != 0:
        raise RuntimeError(f"checkout of {m['commit']} failed: {r.stderr.strip()}")
    return dest


def fetch_inputs(m: dict, inputs: Path) -> None:
    inputs.mkdir(parents=True, exist_ok=True)
    for row in m.get("inputs", []):
        target = inputs / row["save_as"]
        with urllib.request.urlopen(row["url"], timeout=60) as resp:
            data = resp.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != row["sha256"]:
            raise RuntimeError(f"input {row['url']} hashed {digest}, manifest pins {row['sha256']}")
        target.write_bytes(data)
        if row.get("unzip_to"):
            with zipfile.ZipFile(target) as z:
                z.extractall(inputs / row["unzip_to"])


def _run(cmd: list[str], cwd: Path, places: dict, seconds: float) -> dict:
    argv = [expand(a, places) for a in cmd]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    t0 = time.perf_counter()
    p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=max(120, seconds * 10))
    return {"exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
            "seconds": round(time.perf_counter() - t0, 2)}


def meets(result: dict, expect: dict) -> list[str]:
    misses = []
    if result["exit_code"] != expect["exit_code"]:
        misses.append(f"exit {result['exit_code']}, expected {expect['exit_code']}")
    for s in expect.get("stdout_contains", []):
        if s not in result["stdout"]:
            misses.append(f"stdout lacks {s!r}")
    for s in expect.get("stdout_lacks", []):
        if s in result["stdout"]:
            misses.append(f"stdout holds {s!r}")
    return misses


def _setup(m: dict, cwd: Path, places: dict) -> None:
    for cmd in m.get("setup", []):
        r = _run(cmd, cwd, places, m["needs"]["seconds"])
        if r["exit_code"] != 0:
            raise RuntimeError(f"setup step {cmd[:3]} exited {r['exit_code']}: {r['stderr'][-300:]}")


def _control(m: dict, cwd: Path, places: dict) -> dict:
    c = m["control"]
    mutate = c.get("mutate")
    target = Path(expand(mutate["file"], places)) if mutate else None
    original = target.read_bytes() if target else None
    try:
        if target:
            text = original.decode("utf-8")
            if mutate["find"] not in text:
                return {"misses": [f"control: {mutate['find']!r} not in {target.name}"]}
            target.write_bytes(text.replace(mutate["find"], mutate["replace"], 1).encode("utf-8"))
        result = _run(c.get("command", m["command"]), cwd, places, m["needs"]["seconds"])
    finally:
        if target:
            target.write_bytes(original)
    return result | {"misses": meets(result, c["expect"])}


def missing_packages(m: dict) -> list[str]:
    """Declared packages the running interpreter cannot import.

    Checked before anything runs: a missing test dependency once turned a
    benchmark dimension to 0 and changed its seal, which read as DRIFT.
    """
    import importlib.util
    return [p for p in m["needs"].get("packages", []) if importlib.util.find_spec(p) is None]


def recheck(m: dict, work: Path) -> dict:
    missing = missing_packages(m)
    if missing:
        raise RuntimeError(f"needs {', '.join(missing)} in this interpreter "
                           f"(python -m pip install {' '.join(missing)}); not run")
    t0 = time.perf_counter()
    co = checkout(m, work)
    try:
        inputs = work / "inputs"
        fetch_inputs(m, inputs)
        places = {"python": sys.executable, "checkout": str(co), "repo": str(REPO),
                  "inputs": str(inputs)}
        cwd = REPO if m.get("cwd") == "repo" else co
        _setup(m, cwd, places)
        main = _run(m["command"], cwd, places, m["needs"]["seconds"])
        main["misses"] = meets(main, m["expect"])
        control = _control(m, cwd, places)
    finally:
        if co.parent == work:
            _git("-C", str(REPO), "worktree", "remove", "--force", str(co))
    ok = not main["misses"] and not control["misses"]
    return {"id": m["id"], "ok": ok, "main": main, "control": control,
            "wall_seconds": round(time.perf_counter() - t0, 1)}


def _report(r: dict, verbose: bool) -> None:
    print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['id']}  ({r['wall_seconds']} s from checkout to verdict)")
    for part in ("main", "control"):
        for miss in r[part].get("misses", []):
            print(f"      {part}: {miss}")
        if verbose or r[part].get("misses"):
            tail = (r[part].get("stdout", "") + r[part].get("stderr", "")).strip().splitlines()[-8:]
            print("\n".join(f"      | {line}" for line in tail))


def select(paths: list[str], hardware: str | None, ci_only: bool) -> list[dict]:
    files = [Path(p) for p in paths] or discover(REPO)
    chosen = []
    for f in files:
        m = load(f)
        if hardware and m["needs"]["hardware"] != hardware:
            continue
        if ci_only and m["ci"] is not True:
            print(f"SKIP  {m['id']}: {m['ci_skip_reason']}")
            continue
        chosen.append(m)
    return chosen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.recheck", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=("list", "run"))
    ap.add_argument("paths", nargs="*", help="manifest files (default: every file in recheck/)")
    ap.add_argument("--hardware", help="only manifests with this needs.hardware, e.g. cpu")
    ap.add_argument("--ci", action="store_true", help="skip manifests marked ci: false")
    ap.add_argument("--json", type=Path, help="write the results here")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    try:
        chosen = select(a.paths, a.hardware, a.ci)
    except (OSError, ManifestError, json.JSONDecodeError) as exc:
        print(f"bad manifest: {exc}", file=sys.stderr)
        return 2
    if a.action == "list":
        for m in chosen:
            print(f"{m['id']:32} {m['level']:14} {m['needs']['hardware']:8} {m['access']} {m['claim']['text'][:60]}")
        return 0
    results = []
    for m in chosen:
        work = Path(tempfile.mkdtemp(prefix="recheck-"))
        try:
            results.append(recheck(m, work))
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            results.append({"id": m["id"], "ok": False, "wall_seconds": 0,
                            "main": {"misses": [f"UNVERIFIABLE: {exc}"]}, "control": {}})
        finally:
            shutil.rmtree(work, ignore_errors=True)
        _report(results[-1], a.verbose)
    if a.json:
        a.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"{sum(r['ok'] for r in results)} of {len(results)} rechecks passed")
    return 0 if results and all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
