"""lean_oracle_adapter.py -- the math domain oracle over the bound Lean check.

The kernel is the sole acceptance authority, and since 2026-10-04 it judges
the candidate against the statement the task pinned before the candidate
existed (harness/lean_binding.py). The task supplies a `challenge`: a theorem
name, its statement, and an optional header with the imports and definitions
the statement uses. A task with no challenge is UNVERIFIABLE with reason
SPECIFICATION_UNPINNED: before this change such a task passed any closed
theorem (project-docs/records/2026-09-23-lean-oracle-task-binding.md).

This adapts the bound receipt to an OracleResult so the kernel judgment plugs
into run_loop and the domain registry. A missing toolchain (lean, or the
leanchecker it ships) becomes UNVERIFIABLE attributed to the environment,
never a candidate FAIL.
"""
from __future__ import annotations

import hashlib

_FIDELITY = ("spec_fidelity UNVERIFIED: the kernel checked the proof against "
             "the pinned statement; whether that statement is the theorem its "
             "author intended (the formalization gap) is a human review this "
             "oracle does not perform")
_BINDING_SCOPE = (
    "the binding compares the pinned theorem, and every definition the "
    "challenge declares that the statement reaches, by exact elaborated form; "
    "a constant from an imported module is matched by module name, which "
    "trusts both sides to load the same .olean files from one search path")
_REPLAY_LIMITS = (
    "leanchecker replay runs in plain mode: it re-checks the declarations the "
    "compiled module adds and trusts every imported .olean file as found on "
    "disk, the toolchain's and any found through the inherited LEAN_PATH; it "
    "is neither the --fresh replay nor an external kernel (comparator with "
    "nanoda or lean4lean)")
_ELABORATION = (
    "the candidate's metaprograms ran unsandboxed with this user's rights "
    "during its one compile; one that writes files outside its build "
    "directory, such as the toolchain's .olean files, is outside what the "
    "artifact hash and an in-process replay detect")
_AUDIT_SCOPE = (
    "the axiom audit walks every constant the pinned theorem depends on; a "
    "declaration the pinned theorem does not reach is replayed by "
    "leanchecker but not audited for axioms")
_SPEC_REASONS = frozenset({"challenge-unpinned", "challenge-compile-failed",
                           "statement-hash-mismatch"})


class LeanOracle:
    """The math domain oracle: an Oracle-Protocol adapter over bound_check.

    `challenge` overrides the task's own; with neither, nothing is checked.
    The honest verdict travels with what Lean does not prove, and the
    receipt's binding, trusted base and validation level travel in coverage.
    """
    oracle_type = "lean"

    def __init__(self, *, header: str = "", runner=None, challenge=None):
        self.header = header
        self.runner = runner
        self.challenge = challenge

    def verify(self, candidate: str, task) -> "OracleResult":
        from .lean_binding import bound_check
        from .receipt_fields import canonical
        code = f"{self.header}\n{candidate}" if self.header else candidate
        raw = (self.challenge if self.challenge is not None
               else getattr(task, "challenge", None))
        res = bound_check(code, raw, runner=self.runner)
        footprint = res.get("axiom_footprint", {}) or {}
        level = res.get("validation_level", "none")
        output_hash = hashlib.sha256(canonical({
            "passed": res.get("passed"), "sha": res.get("code_sha256", ""),
            "footprint": {k: sorted(v) for k, v in sorted(footprint.items())},
            "level": level, "statement": res.get("statement_sha256", ""),
            "challenge": res["challenge"]["challenge_sha256"],
        }).encode()).hexdigest()[:16]
        coverage = {"checker": "lean", "axiom_footprint": footprint,
                    "validation_level": level,
                    "statement_binding": res.get("statement_binding"),
                    "challenge": res.get("challenge"),
                    "statement_sha256": res.get("statement_sha256", ""),
                    "binding": res.get("binding"),
                    "trusted_base": res.get("trusted_base"),
                    "spec_fidelity": res.get("spec_fidelity"),
                    "artifact_sha256": res.get("artifact_sha256", "")}
        if res.get("unverifiable_reason"):
            coverage["unverifiable_detail"] = res["unverifiable_reason"]
        return _result(res, output_hash, coverage)


def _unverifiable(res: dict, kernel: str, common: dict) -> "OracleResult":
    """No verdict: the task's statement was missing or unusable (harness),
    or the toolchain could not judge (environment)."""
    from .oracle import OracleResult
    from .verdict import Execution, UnverifiableReason, Verdict
    if res.get("unverifiable_reason") in _SPEC_REASONS:
        execution = Execution.HARNESS_ERROR
        reason = UnverifiableReason.SPECIFICATION_UNPINNED.value
        fallback = "the task pins no usable challenge statement"
    else:
        execution = Execution.TOOLCHAIN_MISSING
        reason = UnverifiableReason.TOOLCHAIN_MISSING.value
        fallback = "no Lean toolchain installed; the proof was not checked"
    return OracleResult(rc=0, verdict_=Verdict.UNVERIFIABLE,
                        execution=execution, unverifiable_reason=reason,
                        does_not_prove=[kernel[:240] or fallback], **common)


def _result(res: dict, output_hash: str, coverage: dict) -> "OracleResult":
    """Map the bound check's passed (True / False / None) onto the four-way
    verdict, with the does_not_prove lines each outcome carries."""
    from .oracle import OracleResult
    from .verdict import Verdict
    passed = res.get("passed")
    kernel = res.get("kernel_output") or ""
    common = dict(cmd="lean", output_hash=output_hash,
                  stdout_excerpt=kernel[:1200], coverage=coverage,
                  objective="lean kernel check against the pinned statement")
    if passed is None:
        return _unverifiable(res, kernel, common)
    if passed:
        return OracleResult(
            rc=0, verdict_=Verdict.PASS,
            does_not_prove=[_FIDELITY, _BINDING_SCOPE, _REPLAY_LIMITS,
                            _ELABORATION, _AUDIT_SCOPE], **common)
    return OracleResult(
        rc=1, verdict_=Verdict.FAIL,
        does_not_prove=[kernel[:160] or "the kernel refused the proof",
                        _FIDELITY], **common)
