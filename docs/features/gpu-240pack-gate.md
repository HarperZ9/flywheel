# GPU 240-Pack Certification Gate

`harness/gpu_240pack_gate/` is a pure-stdlib MIT verifier for the 240-shader five-backend GPU compute suite spanning `wgsl`, `hlsl`, `msl`, `spirv`, and `glsl`.

## Checks Performed

The verifier inspects every shader entry across all 48 unique MIT compute kernels, requiring complete five-backend coverage with zero duplicate kernel-target pairs, positive byte counts, valid 64-character hexadecimal shader and certificate `SHA-256` digests, and `verify_cert == "PASS"`. It checks cumulative Superopt V6 rewrite totals against the `1,425` minimum threshold and verifies manifest byte and rewrite sums match computed totals exactly.

When a companion report or `engine-receipt/1` envelope is supplied, the gate also verifies external validator counts across `dxc`, `glslang`, `spirv-val`, `naga`, and Metal 3.1 checks, confirms all three planted tamper controls fail closed, and requires a `MATCH` receipt verdict with exit code `0`.

## Scope Limits

This verifier audits emitted shader manifests, certificate hashes, and validator reports. It does not invoke GPU compilers or dispatch live hardware shaders directly.
