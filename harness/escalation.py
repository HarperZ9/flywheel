"""escalation.py — M4 tiered oracle escalation (cheap -> expensive gating).

Cheap tiers PRUNE via fast-fail (dense signal saves compute); only the terminal
tier ACCEPTS. C2 invariant (HARNESS.md): no dense-reward accept ever overrides
the terminal oracle — a candidate that passes compile but fails test is NOT
accepted. Compute concentrates on live candidates: a candidate that fails
compile never reaches the expensive test tier.

Compose with M3: best_of_n generates k candidates; EscalationOracle tier-
verifies each. Per-candidate fast-fail achieves the set-level filter naturally
(each non-compiling candidate is pruned before the expensive tier runs).
"""
from __future__ import annotations
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .oracle import Oracle, OracleResult, canonical_hash, clear_bytecode, run_env
from .task import Task


class CompileOracle:
    """Cheap tier: syntax-check the candidate via py_compile (no execution).
    The dense-signal prune — a candidate that doesn't compile can't pass tests,
    so don't spend the expensive test tier on it."""
    oracle_type = "py_compile"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def verify(self, candidate: str, task: Task) -> OracleResult:
        cpath = task.candidate_full()
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(candidate, encoding="utf-8")
        clear_bytecode(Path(task.workdir))
        cmd = f'python -m py_compile "{task.candidate_path}"'
        try:
            p = subprocess.run(
                cmd, cwd=task.workdir, shell=True, env=run_env(),
                capture_output=True, timeout=self.timeout)
            rc = p.returncode
            out = p.stdout + p.stderr
        except subprocess.TimeoutExpired as e:
            # keep BOTH streams so the excerpt names the timeout, not a blank
            out = ((e.stdout or b"") if isinstance(e.stdout, bytes) else b"") \
                + ((e.stderr or b"") if isinstance(e.stderr, bytes) else b"")
            rc = 124
        if rc == 0:
            canon = canonical_hash("py_compile", Path(task.workdir), rc)
        else:
            # content-address the failure: a reject receipt must commit to the
            # exact candidate and compiler output, re-derivable by a stranger,
            # not a bare compile_fail_{rc} every failing candidate shares
            canon = hashlib.sha256(
                candidate.encode("utf-8") + f"|{rc}|".encode()
                + out).hexdigest()[:16]
        return OracleResult(
            passed=rc == 0, cmd=cmd, output_hash=canon,
            stdout_excerpt=out.decode("utf-8", errors="replace")[-800:], rc=rc)


@dataclass
class EscalationResult(OracleResult):
    stopped_at_tier: str = ""
    tiers_run: tuple = ()


class EscalationOracle:
    """Tiered oracle: [(name, oracle), ...]. Runs in order; the first tier that
    FAILS stops escalation (fast-fail prune for non-terminal, reject for
    terminal). Only passing ALL tiers (terminal included) = ACCEPT. Non-terminal
    passes never override a terminal fail (C2 invariant)."""

    oracle_type = "escalation"

    def __init__(self, tiers: list[tuple[str, Oracle]]):
        if not tiers:
            raise ValueError("EscalationOracle needs at least one tier")
        self.tiers = tiers

    def verify(self, candidate: str, task: Task) -> OracleResult:
        run: list[str] = []
        last = None
        for i, (name, orc) in enumerate(self.tiers):
            last = orc.verify(candidate, task)
            run.append(name)
            is_terminal = (i == len(self.tiers) - 1)
            if not last.passed:
                # the structured receipt: WHICH tier stopped escalation and
                # which tiers ran, not just a prose prefix in the excerpt
                return EscalationResult(
                    passed=False, cmd=last.cmd, output_hash=last.output_hash,
                    stdout_excerpt=f"[{name}] {last.stdout_excerpt}",
                    rc=last.rc, stopped_at_tier=name, tiers_run=tuple(run))
            if is_terminal:
                return EscalationResult(
                    passed=True, cmd=last.cmd, output_hash=last.output_hash,
                    stdout_excerpt=f"[{name}:terminal] {last.stdout_excerpt}",
                    rc=last.rc, stopped_at_tier=name, tiers_run=tuple(run))
        return last
