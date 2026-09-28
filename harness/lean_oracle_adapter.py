"""lean_oracle_adapter.py -- the math domain oracle over lean_check.

lean_check is the sole acceptance authority: kernel exit, sorry refusal, an
axiom-footprint audit against the classical trio, and a leanchecker replay of
the compiled module. This adapts its receipt to an OracleResult so the kernel
judgment plugs into run_loop and the domain registry with no change to
either. It reuses the checker rather than reimplementing it, and a missing
toolchain (lean, or the leanchecker it ships) becomes UNVERIFIABLE attributed
to the environment, never a candidate FAIL.

`LeanOracle.verify` does not read its task. Any closed theorem passes, not
the task's theorem; binding the proof to a pinned challenge statement is
recorded as a follow-up in
project-docs/records/2026-09-23-lean-oracle-task-binding.md.
"""
from __future__ import annotations

import hashlib

_GAP = ("Lean checks the proof term inhabits the stated type; it does not "
        "check the statement is the intended theorem (the formalization gap)")
_UNBOUND = ("the task is not read: the oracle accepts any closed theorem, not "
            "the task's theorem, until a statement-match check against a "
            "pinned challenge exists")
_REPLAY_LIMITS = (
    "leanchecker replay runs in plain mode: it re-checks the declarations the "
    "compiled module adds and trusts every imported .olean file as found on "
    "disk, the toolchain's and any found through the inherited LEAN_PATH; it "
    "is neither the --fresh replay nor an external kernel (comparator with "
    "nanoda or lean4lean)")
_ELABORATION = (
    "the candidate's metaprograms ran unsandboxed with this user's rights "
    "during elaboration and compilation; one that writes files, such as the "
    "toolchain's .olean files, is outside what an in-process replay detects")
_AUDIT_SCOPE = (
    "the axiom audit reads source-named theorem and lemma declarations only; "
    "a def, or a declaration a metaprogram added, whose value rests on an "
    "added axiom is replayed as a valid declaration and is not audited")


class LeanOracle:
    """The math domain oracle: an Oracle-Protocol adapter over lean_check.

    The honest verdict travels with what Lean does not prove, and the
    receipt's validation_level travels in coverage so a reader sees how far
    up the Lean reference's ladder a PASS reached.
    """
    oracle_type = "lean"

    def __init__(self, *, header: str = "", runner=None):
        self.header = header
        self.runner = runner

    def verify(self, candidate: str, task) -> "OracleResult":
        from .lean_oracle import lean_check
        from .receipt_fields import canonical
        code = f"{self.header}\n{candidate}" if self.header else candidate
        res = lean_check(code, runner=self.runner)
        footprint = res.get("axiom_footprint", {}) or {}
        level = res.get("validation_level", "none")
        output_hash = hashlib.sha256(canonical({
            "passed": res.get("passed"), "sha": res.get("code_sha256", ""),
            "footprint": {k: sorted(v) for k, v in sorted(footprint.items())},
            "level": level,
        }).encode()).hexdigest()[:16]
        coverage = {"checker": "lean", "axiom_footprint": footprint,
                    "validation_level": level}
        return _result(res, output_hash, coverage)


def _result(res: dict, output_hash: str, coverage: dict) -> "OracleResult":
    """Map lean_check's passed (True / False / None) onto the four-way
    verdict, with the does_not_prove lines each outcome carries."""
    from .oracle import OracleResult
    from .verdict import Execution, UnverifiableReason, Verdict
    passed = res.get("passed")
    kernel = res.get("kernel_output") or ""
    common = dict(cmd="lean", output_hash=output_hash,
                  stdout_excerpt=kernel[:1200],
                  objective="lean kernel type-check")
    if passed is None:
        return OracleResult(
            rc=0, verdict_=Verdict.UNVERIFIABLE,
            execution=Execution.TOOLCHAIN_MISSING,
            unverifiable_reason=UnverifiableReason.TOOLCHAIN_MISSING.value,
            does_not_prove=[kernel[:240] or "no Lean toolchain installed; "
                            "the proof was not checked"],
            coverage=coverage, **common)
    if passed:
        return OracleResult(
            rc=0, verdict_=Verdict.PASS,
            does_not_prove=[_GAP, _UNBOUND, _REPLAY_LIMITS, _ELABORATION,
                            _AUDIT_SCOPE],
            coverage=coverage, **common)
    return OracleResult(
        rc=1, verdict_=Verdict.FAIL,
        does_not_prove=[kernel[:160] or "the kernel refused the proof", _GAP],
        coverage=coverage, **common)
