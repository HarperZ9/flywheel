"""partial.py -- coverage and differential checks, for verdicts built from part of a check.

Two ways a verifier passes work that is wrong (Terminal-RSI, arXiv 2610.22192,
reward audit): every scenario check that ran passed while the protected verifier
did not, and a port passed its wrapper test while exact-output fuzzing failed.

coverage asks whether every required check ran and passed. A check that did not
run, or returned anything but PASS, fails the subject.

differential asks whether recorded outputs equal a reference on every input of
the fuzz set, exactly: 3 and 3.0 differ, and so do True and 1. A fuzz input with
no recorded output fails the subject. The check sees only the inputs the spec
names, so a divergence outside them passes (the corpus marks that case).
"""
from __future__ import annotations

import json

from .evidence import evaluate
from .receipt import FAIL, PASS, UNVERIFIABLE


def coverage_check(subject, spec: dict) -> tuple[str, str, str]:
    """subject: {"ran": {check_id: verdict}}. spec: required (check ids)."""
    required = spec.get("required")
    if not isinstance(required, list) or not required:
        return UNVERIFIABLE, "no_required", "the spec names no required checks"
    ran = subject.get("ran") if isinstance(subject, dict) else None
    if not isinstance(ran, dict):
        return FAIL, "malformed", "the subject records no checks that ran"
    missing = [c for c in required if c not in ran]
    if missing:
        return FAIL, "required_not_run", f"required checks did not run: {', '.join(missing)}"
    short = [c for c in required if ran[c] != PASS]
    if short:
        return FAIL, "required_failed", f"required checks did not pass: {', '.join(short)}"
    return PASS, "all_required_passed", "every required check ran and passed"


def _key(value) -> str:
    return json.dumps(value, sort_keys=True)


def differential_check(subject, spec: dict) -> tuple[str, str, str]:
    """subject: {"outputs": [[input, output], ...]}. spec: reference (an
    expression over x, evaluated by the recompute evaluator) and inputs."""
    ref, inputs = spec.get("reference"), spec.get("inputs")
    if not isinstance(ref, str) or not isinstance(inputs, list) or not inputs:
        return UNVERIFIABLE, "no_reference", "the spec gives no reference or no fuzz inputs"
    rows = subject.get("outputs") if isinstance(subject, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, list) and len(r) == 2 for r in rows):
        return FAIL, "malformed", "the subject records no input/output pairs"
    seen = {_key(i): o for i, o in rows}
    for n, inp in enumerate(inputs):
        if _key(inp) not in seen:
            return FAIL, "input_not_run", f"fuzz input {n} has no recorded output"
        if _key(seen[_key(inp)]) != _key(evaluate(ref, {"x": inp})):
            return FAIL, "output_differs", f"fuzz input {n}: output differs from the reference"
    return PASS, "outputs_equal", f"all {len(inputs)} fuzz outputs equal the reference"
