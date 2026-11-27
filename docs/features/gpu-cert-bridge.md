# GPU Shader Certificate and Superoptimizer Bridge (`harness.gpu_cert_bridge`)

`harness/gpu_cert_bridge/` provides pure-Python standard-library verification for five-target GPU shader translation-validation certificates (`buildlang.gpu-tv-cert/v1`) and embedded Superoptimizer V6 MIR rewrite certificates (`buildlang.superopt-cert/v1`). Every check fails closed on schema drift, missing targets, cost regression, or single-bit shader tampering.

## Modules

- **`shader_cert.py`**: Verifies `buildlang.gpu-tv-cert/v1` certificates across `wgsl`, `hlsl`, `msl`, `spirv`, and `glsl`. Validates constant-time `shader_sha256` against raw shader bytes, checks `verified` and `cert_sha256`, and enforces subgroup uniformity and polyhedral schedule status.
- **`superopt_chain.py`**: Verifies `buildlang.superopt-cert/v1` rewrite chains. Enforces monotone MIR cost (`total_cost_after <= total_cost_before` and per-step `cost_after <= cost_before`), rewrite count consistency, step cost sum consistency, and bounded ULP error witnesses.
- **`matrix_gate.py`**: Audits an emitted GPU shader directory for complete five-target coverage per kernel, paired shader byte integrity, and embedded superoptimizer chain validity, sealing a deterministic `attestation_sha256`.

## Usage

```python
from pathlib import Path
from harness.gpu_cert_bridge import verify_gpu_cert_matrix

report = verify_gpu_cert_matrix(Path("workstation-gpu-emitted"))
assert report.passed
```

## Honest Scope Limits

- **`shader_cert.py`** verifies certificate structure and byte-level `shader_sha256` integrity; it does not execute GPU shaders or replace external validators such as `naga`, `dxc`, or `spirv-val`.
- **`superopt_chain.py`** verifies monotone cost bounds and rewrite-step metadata; it does not re-run e-graph saturation or SMT equivalence checking.
- **`matrix_gate.py`** audits an existing directory snapshot; it does not compile BuildLang source files.
