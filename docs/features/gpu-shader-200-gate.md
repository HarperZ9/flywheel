# GPU Shader 200 Gate

## Overview

`harness/gpu_shader_200_gate` audits the 200-shader 5-backend GPU compute manifest in pure Python stdlib under the OSI MIT license. Every kernel entry covers all five backends: `wgsl`, `hlsl`, `msl`, `spirv`, and `glsl`. Each entry declares `MIT` licensing, passes `verify_cert`, carries valid 64-hex shader and certificate SHA-256 digests, and records passing validator tags.

## Completeness and Fail-Closed Rules

Calling `verify_gpu_200_pack` or `verify_gpu_200_pack_files` returns an immutable `Gpu200GateReport`. The report seals `gpu_shader_200_attestation_sha256` over sorted kernel records. It checks shader and kernel count floors, Superopt V6 rewrite totals, external validator coverage across `dxc`, `glslangValidator`, and `spirv-val`, and optional on-disk shader hashes, failing closed on any shortfall, forged digest, failing validator tag, non-MIT license, or `NaN`/`Inf`/`bool` parity error.

## Scope Limits

This oracle checks GPU manifests, 5-target coverage, rewrite arithmetic, validator pass markers, and optional on-disk shader hashes in pure Python stdlib. It does not invoke GPU drivers or external shader compilers.
