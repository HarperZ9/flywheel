"""suite_audit.py -- can this acceptance suite refuse wrong code?

Every RCF-shaped methodology promises "one acceptance criterion, one
test suite, no negotiation". The promise is only as strong as the
suite's ability to refuse, and this module measures it for ANY
project: one-operator mutants of the project's own source must be
KILLED (the suite fails); a survivor is named with its exact mutation.
The suite must first pass unmutated (a broken reference is refused,
not audited around). Sources are mutated in place under a finally
restore, verified byte-exact in the receipt, and the mutation budget
is bounded: this is an admission gate, not a mutation-testing farm.
"""
from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path

SCHEMA = "flywheel.suite-audit/v1"
_TIMEOUT = 120

MUTATIONS = ((" + ", " - "), (" - ", " + "), (" < ", " <= "),
             (" > ", " >= "), (" == ", " != "), (" * ", " + "))


def first_mutant(source: str) -> "tuple | None":
    """The first applicable one-operator flip: (mutated_text,
    original_line, mutated_line) or None."""
    for old, new in MUTATIONS:
        if old in source:
            mutated = source.replace(old, new, 1)
            if mutated != source:
                for a, b in zip(source.splitlines(),
                                mutated.splitlines()):
                    if a != b:
                        return mutated, a.strip(), b.strip()
    return None


def _run_suite(project: Path, oracle_cmd: str) -> bool:
    from .oracle import _kill_tree, clear_bytecode, run_env
    clear_bytecode(project)
    proc = subprocess.Popen(oracle_cmd, cwd=str(project), shell=True,
                            env=run_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    try:
        proc.communicate(timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
        return False
    return proc.returncode == 0


def _candidates(project: Path, limit: int) -> list:
    out = []
    for p in sorted(project.rglob("*.py")):
        rel = p.relative_to(project)
        parts = rel.parts
        if parts[0].startswith(".") or "tests" in parts \
                or "__pycache__" in parts:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def audit_suite(project: "str | Path", *,
                oracle_cmd: str = "python -m pytest tests/ -q",
                max_mutants: int = 5) -> dict:
    """Measure the suite's refusal floor. Returns the receipt."""
    project = Path(project)
    if not project.is_dir():
        return {"schema": SCHEMA, "error": f"no such project: {project}"}
    t0 = time.time()
    if not _run_suite(project, oracle_cmd):
        return {"schema": SCHEMA, "project": str(project),
                "oracle_cmd": oracle_cmd, "reference_ok": False,
                "attempted": 0, "killed": 0, "kill_rate": None,
                "survivors": [], "restored": True,
                "wall_seconds": round(time.time() - t0, 1),
                "note": "broken reference: the suite fails on the "
                        "project's own source; nothing to audit until "
                        "it passes"}
    attempted, killed, survivors = 0, 0, []
    restored = True
    for path in _candidates(project, max_mutants):
        original = path.read_bytes()
        mut = first_mutant(original.decode("utf-8", errors="replace"))
        if mut is None:
            continue
        mutated_text, orig_line, mut_line = mut
        attempted += 1
        try:
            path.write_text(mutated_text, encoding="utf-8")
            if _run_suite(project, oracle_cmd):
                survivors.append({"file": str(path.relative_to(project)),
                                  "original": orig_line,
                                  "mutated": mut_line})
            else:
                killed += 1
        finally:
            path.write_bytes(original)
            if hashlib.sha256(path.read_bytes()).hexdigest() != \
                    hashlib.sha256(original).hexdigest():
                restored = False
    return {"schema": SCHEMA, "project": str(project),
            "oracle_cmd": oracle_cmd, "reference_ok": True,
            "attempted": attempted, "killed": killed,
            "kill_rate": (round(killed / attempted, 4)
                          if attempted else None),
            "survivors": survivors, "restored": restored,
            "wall_seconds": round(time.time() - t0, 1),
            "note": "a survivor names a wrong-code change this suite "
                    "accepted; the promise 'one suite, no negotiation' "
                    "is only as strong as this number"}
