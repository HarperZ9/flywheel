"""kernel_oracle falsifier — KernelBench-Mega verification gates.

The gates Elliot Arledge named: a 'genuine' single fused kernel passes;
multi-kernel pipelines FAIL (the correctness/mega gate); non-compiling and
incorrect-output fail. Speedup tier is GPU-gated (stubbed, flagged for smoke).
"""
import pytest

from harness.kernel_oracle import KernelOracle, KernelSpec, _count_kernel_defs, _calls_other_defs


SINGLE_CORRECT = (
    "def fused_add_relu(x, y):\n"
    "    s = x + y\n"
    "    return s if s < 0 else s\n"
)
MULTI_KERNEL = (
    "def add(x, y):\n"
    "    return x + y\n"
    "def relu(z):\n"
    "    return z if z < 0 else z\n"
    "def pipeline(x, y):\n"
    "    return relu(add(x, y))\n"
)
SYNTAX_BAD = "def broken(:\n"
WRONG_OUTPUT = "def fused_add_relu(x, y):\n    return x * y\n"


def _runner(src):
    ns = {}
    exec(src, ns)
    name = [k for k in ns if not k.startswith("__")][0]
    return ns[name](2, 3)


def test_single_correct_kernel_passes():
    o = KernelOracle(KernelSpec(expected_output="5", reference_runner=_runner))
    r = o.verify_dense(SINGLE_CORRECT, task=None)
    assert r.passed and r.reward == 1.0


def test_multi_kernel_pipeline_fails_mega_gate():
    """The KernelBench-Mega discriminator: multi-kernel pipelines fail."""
    o = KernelOracle(KernelSpec(expected_output="5", reference_runner=_runner))
    r = o.verify_dense(MULTI_KERNEL, task=None)
    assert not r.passed
    assert "not_single" in r.output_hash or "multi_kernel" in r.output_hash


def test_syntax_error_fails_compile():
    o = KernelOracle(KernelSpec(expected_output="5"))
    r = o.verify_dense(SYNTAX_BAD, task=None)
    assert not r.passed and "compile_fail" in r.output_hash


def test_wrong_output_fails_correctness():
    o = KernelOracle(KernelSpec(expected_output="5", reference_runner=_runner))
    r = o.verify_dense(WRONG_OUTPUT, task=None)
    assert not r.passed
    assert "incorrect" in r.output_hash


def test_count_kernel_defs():
    assert _count_kernel_defs(SINGLE_CORRECT) == 1
    assert _count_kernel_defs(MULTI_KERNEL) == 3
    assert _count_kernel_defs(SYNTAX_BAD) == -1


def test_single_kernel_not_required_relaxes_gate():
    """If the task doesn't require single-kernel, multi-def is allowed (only
    correctness gates). This is the ablation hook."""
    o = KernelOracle(KernelSpec(expected_output="5",
                                reference_runner=_runner,
                                require_single_kernel=False))
    r = o.verify_dense(MULTI_KERNEL, task=None)
    assert r.passed


def test_speedup_tier_is_gpu_gated():
    """A correct single kernel passes with a note that speedup needs a GPU.
    Honest: the speedup tier is stubbed, not measured, until the GPU is free."""
    o = KernelOracle(KernelSpec(expected_output="5", reference_runner=_runner))
    r = o.verify_dense(SINGLE_CORRECT, task=None)
    assert r.passed
    assert "GPU-gated" in r.output_hash or "speedup" in r.output_hash.lower()
