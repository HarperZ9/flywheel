# Cross-Runtime Benchmark Parity and Regression Gate (`harness.benchmark_gate`)

`harness/benchmark_gate/` verifies cross-runtime canonical output digest parity, statistical timing invariants, honest subprocess spawn-floor disclosures, and baseline latency regression ceilings using only the Python standard library. Every check fails closed on output drift, inverted percentiles, omitted spawn disclosures, or latency regressions.

## Modules

`parity_check.py` checks bit-identical SHA-256 output digests across Native, Zero-C, WebAssembly, and Python runtime cells, rejecting missing runtimes, malformed hashes, single-runtime divergence, and baseline hash drift.

`regression_gate.py` enforces finite positive timings, the `min <= p50 <= p95` order invariant, sample-array consistency, bounded `p95/p50` variance, explicit subprocess spawn-floor disclosure on sub-10ms process-launched cells, and latency regression ceilings against baseline `p50` values.

`suite_verifier.py` audits serialized benchmark suite JSON artifacts across all workloads and runtime cells, sealing a deterministic `benchmark_attestation_sha256` digest.

## Usage

```python
from pathlib import Path
from harness.benchmark_gate import verify_benchmark_suite_file

report = verify_benchmark_suite_file(Path("benchmarks_v3_results.json"), expected_workloads=13)
assert report.passed
```

## Honest Scope Limits

`parity_check.py`, `regression_gate.py`, and `suite_verifier.py` validate serialized benchmark outputs, timing invariants, and disclosure text. They do not compile kernels, execute binaries, or control host OS scheduling jitter.
