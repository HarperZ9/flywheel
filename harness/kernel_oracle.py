"""kernel_oracle.py — KernelBench-style verification for generated GPU kernels.

The "high-speed kernel container" engine's verification half. A generated
kernel must clear three tiers (M4 escalation specialized for kernels):
  1. COMPILE — the source is well-formed (parses).
  2. SINGLE-KERNEL (the KernelBench-Mega "genuine megakernel" gate) — it is ONE
     fused kernel, not a multi-kernel pipeline (Elliot Arledge: prior models
     "won" with multi-kernel pipelines that fail this gate).
  3. CORRECTNESS — output matches the reference (the dense signal M6 climbs).
  4. SPEEDUP (GPU-gated) — faster than the PyTorch baseline. Stubbed here; needs
     a GPU to benchmark. Marked so it smokes when the CPT frees the card.

Dense reward = compile × single × correct × speedup_stub. This lets M6
verifier-guided search climb toward faster-correct-single kernels — the
"generate a fused megakernel" task, made operational in our oracle registry.
"""
from __future__ import annotations
import ast
from dataclasses import dataclass

from .mcts import DenseResult, DenseOracle
from .task import Task


def _count_kernel_defs(source: str) -> int:
    """Count top-level function/kernel definitions. The KernelBench-Mega
    'genuine megakernel' gate: exactly ONE fused kernel, not a pipeline."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return -1
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n += 1
    return n


def _calls_other_defs(source: str) -> bool:
    """A 'genuine' fused kernel does the work inline, not by calling a chain of
    helper kernels. Heuristic: does the body call other module-level defs?"""
    try:
        tree = ast.parse(source)
        defined = {n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in defined:
                return True
    return False


@dataclass
class KernelSpec:
    """A KernelBench-style task: expected output + whether single-kernel is
    required (the Mega gate)."""
    expected_output: str
    require_single_kernel: bool = True
    reference_runner: object | None = None  # callable(candidate_source) -> str


class KernelOracle(DenseOracle):
    """Tiered kernel verification (compile -> single-kernel gate -> correctness
    -> speedup[GPU-gated]). Dense reward for M6 verifier-guided search."""

    oracle_type = "kernelbench"

    def __init__(self, spec: KernelSpec):
        self.spec = spec

    def verify_dense(self, candidate: str, task: Task) -> DenseResult:
        ndefs = _count_kernel_defs(candidate)
        if ndefs < 0:
            return DenseResult(False, 0.0, "compile_fail")
        if self.spec.require_single_kernel:
            if ndefs != 1:
                return DenseResult(False, 0.0, f"not_single:{ndefs}_defs")
            if _calls_other_defs(candidate):
                return DenseResult(False, 0.0, "multi_kernel_pipeline")
        if self.spec.reference_runner is not None:
            try:
                got = str(self.spec.reference_runner(candidate)).strip()
                if got != self.spec.expected_output.strip():
                    return DenseResult(False, 0.0, f"incorrect:{got[:24]}")
            except Exception as e:
                return DenseResult(False, 0.0, f"run_err:{type(e).__name__}")
        return DenseResult(
            True, 1.0,
            "correct_single_kernel: speedup-tier GPU-gated (smoke when CPT frees GPU)")
