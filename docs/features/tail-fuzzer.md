# Crucible Tail-Risk Distributional Fuzzer (`harness.tail_fuzzer`)

`harness/tail_fuzzer/` provides pure-Python standard-library seed-pinned adversarial boundary fuzzing, empirical extreme-value tail metrics (`p99`, `CVaR_99`, and max excursion ratio), and a fail-closed distributional fuzz gate. Every gate checks generator reproducibility, invariant preservation, `NaN`/`Inf` absence, and extreme-tail bounds.

## Modules

`boundary_fuzzer.py` produces deterministic seed-pinned adversarial inputs targeting IEEE-754 subnormals, `-0.0`, `NaN`, `Inf`, `2^53+1`, integer boundaries, adversarial Unicode and null-byte strings, boundary lengths, and empty or skewed partitions via `random.Random(seed)`.

`tail_metrics.py` computes linear-interpolated empirical quantiles (`p50`, `p95`, `p99`), empirical `CVaR_99` Expected Shortfall, maximum excursion ratio relative to median, and explicit `NaN` or `Inf` propagation counts.

`fuzz_gate.py` executes target callables across generated case streams, verifies seed reproducibility, enforces `p99`, `CVaR_99`, excursion, and invariant limits fail-closed, and seals a deterministic `tail_fuzz_attestation_sha256` digest.

## Usage

```python
from harness.tail_fuzzer import FuzzGatePolicy, run_tail_fuzz_gate

policy = FuzzGatePolicy(max_p99=2.0, max_cvar_99=3.0, max_excursion_ratio=10.0)
report = run_tail_fuzz_gate(lambda _c: 0.5, seed=42, count=200, policy=policy)
assert report.passed
```

## Honest Scope Limits

`boundary_fuzzer.py`, `tail_metrics.py`, and `fuzz_gate.py` evaluate deterministic boundary and heavy-tail distributions with empirical order statistics. They do not perform coverage-guided binary fuzzing, symbolic execution, or formal proofs over unsampled inputs.
